"""Persistence: config and profile TOML round-trip tests.

Uses the `OPENFOV_APPDATA` env var to redirect persistence into a tmp dir."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from openfov.filtering.pipeline import AxisFilterParams
from openfov.mapping.axis_mapper import AxisSettings
from openfov.mapping.presets import soft_center
from openfov.persistence.config import AppConfig, load_app_config, save_app_config
from openfov.persistence.paths import sanitize_profile_name
from openfov.persistence.profiles import (
    Profile,
    delete_profile,
    list_profile_names,
    load_profile,
    save_profile,
)


@pytest.fixture(autouse=True)
def _temp_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))


def test_app_config_defaults_when_no_file() -> None:
    cfg = load_app_config()
    assert cfg.last_profile == "Default"
    assert cfg.camera_index == 0


def test_app_config_roundtrip() -> None:
    cfg = AppConfig(
        last_profile="iRacing GT3",
        camera_index=2,
        camera_width=1920,
        camera_height=1080,
        show_wizard_on_next_launch=False,
        hotkey_recenter="<f10>",
    )
    save_app_config(cfg)
    restored = load_app_config()
    assert restored.last_profile == "iRacing GT3"
    assert restored.camera_index == 2
    assert restored.camera_width == 1920
    assert restored.show_wizard_on_next_launch is False
    assert restored.hotkey_recenter == "<f10>"


def test_app_config_survives_garbage_file(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text("this is not toml :::")
    os.environ["OPENFOV_APPDATA"] = str(tmp_path)
    # Should not raise.
    cfg = load_app_config()
    assert cfg.last_profile == "Default"


def test_profile_default_shape() -> None:
    p = Profile()
    assert p.name == "Default"
    assert p.game_id == "iracing"
    assert set(p.axes.keys()) == {"yaw", "pitch", "roll", "x", "y", "z"}
    # Yaw is on by default; pitch + roll start off so first-time users
    # aren't overwhelmed (only horizontal head-turning maps to the
    # camera until they affirmatively enable the others).
    assert p.axes["yaw"].enabled is True
    assert p.axes["pitch"].enabled is False
    assert p.axes["roll"].enabled is False
    # Translation axes are structurally disabled until v2.
    assert p.axes["x"].enabled is False
    assert p.axes["y"].enabled is False
    assert p.axes["z"].enabled is False
    # Yaw ships with soft-center + 3x sensitivity (fine control near
    # forward view, fast swing at the edges); pitch/roll keep the gentle
    # 0.75 linear default so they feel tame when enabled.
    assert p.axes["yaw"].sensitivity == pytest.approx(3.0)
    assert p.axes["pitch"].sensitivity == pytest.approx(0.75)
    assert p.axes["roll"].sensitivity == pytest.approx(0.75)
    # Soft-center is shallow near zero, so for a small input its output is
    # below the linear (pitch) response — confirms yaw got the soft curve.
    assert p.axes["yaw"].curve(10.0) < p.axes["pitch"].curve(10.0)


def test_app_config_toggle_hotkey_default() -> None:
    from openfov.persistence.config import AppConfig

    assert AppConfig().hotkey_toggle_tracking == "<f10>"


def test_app_config_toggle_hotkey_roundtrip(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))
    from openfov.persistence.config import AppConfig, load_app_config, save_app_config

    cfg = AppConfig(hotkey_toggle_tracking="<f7>")
    save_app_config(cfg)
    assert load_app_config().hotkey_toggle_tracking == "<f7>"


def test_profile_enabled_field_roundtrip(monkeypatch, tmp_path) -> None:
    """An explicit enabled toggle must round-trip through TOML."""
    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))
    from openfov.mapping.axis_mapper import AxisSettings
    from openfov.persistence.profiles import Profile, load_profile, save_profile

    p = Profile(name="EnabledRT")
    p.axes["yaw"] = AxisSettings(enabled=False)
    p.axes["roll"] = AxisSettings(enabled=True)
    save_profile(p)
    back = load_profile("EnabledRT")
    assert back.axes["yaw"].enabled is False
    assert back.axes["roll"].enabled is True


def test_profile_roundtrip() -> None:
    p = Profile(name="iRacing GT3", game_id="iracing")
    p.axes["yaw"] = AxisSettings(invert=True, sensitivity=1.5, curve=soft_center(90.0))
    p.filters["pitch"] = AxisFilterParams(min_cutoff=0.8, beta=0.07)
    save_profile(p)

    restored = load_profile("iRacing GT3")
    assert restored.name == "iRacing GT3"
    assert restored.axes["yaw"].invert is True
    assert restored.axes["yaw"].sensitivity == pytest.approx(1.5)
    assert restored.filters["pitch"].min_cutoff == pytest.approx(0.8)
    assert restored.filters["pitch"].beta == pytest.approx(0.07)
    # Curve must round-trip with reasonable precision.
    assert restored.axes["yaw"].curve(45.0) == pytest.approx(
        p.axes["yaw"].curve(45.0), abs=1e-3
    )


def test_profile_filter_stabilization_fields_roundtrip() -> None:
    """median_window + dead_zone (added in the filter robustness pass)
    must survive a save/load cycle without resetting to defaults."""
    p = Profile(name="StabilizationRT", game_id="iracing")
    p.filters["yaw"] = AxisFilterParams(
        min_cutoff=1.2, beta=0.08, median_window=3, dead_zone=0.25
    )
    p.filters["pitch"] = AxisFilterParams(
        min_cutoff=0.9, beta=0.06, median_window=5, dead_zone=0.10
    )
    save_profile(p)

    restored = load_profile("StabilizationRT")
    assert restored.filters["yaw"].median_window == 3
    assert restored.filters["yaw"].dead_zone == pytest.approx(0.25)
    assert restored.filters["pitch"].median_window == 5
    assert restored.filters["pitch"].dead_zone == pytest.approx(0.10)
    # Other axes get the dataclass defaults — median ON (window=3),
    # dead-zone disabled.
    assert restored.filters["roll"].median_window == 3
    assert restored.filters["roll"].dead_zone == pytest.approx(0.0)


def test_old_profile_without_new_filter_fields_loads_with_defaults() -> None:
    """A pre-existing on-disk profile (one written before median +
    dead-zone existed) must still load. The missing fields fall back
    to defaults — median off, dead-zone 0."""
    import tomli_w

    from openfov.persistence.paths import profile_path

    name = "LegacyShape"
    target = profile_path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    legacy = {
        "name": name,
        "game_id": "iracing",
        "axes": {},
        "filters": {
            "yaw": {"min_cutoff": 1.5, "beta": 0.08, "d_cutoff": 1.0},
        },
    }
    with target.open("wb") as f:
        tomli_w.dump(legacy, f)

    restored = load_profile(name)
    # Existing fields round-trip.
    assert restored.filters["yaw"].min_cutoff == pytest.approx(1.5)
    assert restored.filters["yaw"].beta == pytest.approx(0.08)
    # New fields use dataclass defaults — median ON (window=3),
    # dead-zone disabled.
    assert restored.filters["yaw"].median_window == 3
    assert restored.filters["yaw"].dead_zone == pytest.approx(0.0)


def test_list_and_delete_profiles() -> None:
    save_profile(Profile(name="One"))
    save_profile(Profile(name="Two"))
    save_profile(Profile(name="Three"))
    names = list_profile_names()
    assert names == ["One", "Three", "Two"]
    assert delete_profile("Two") is True
    assert delete_profile("Two") is False
    assert list_profile_names() == ["One", "Three"]


def test_sanitize_profile_name() -> None:
    assert sanitize_profile_name("iRacing GT3") == "iRacing GT3"
    assert sanitize_profile_name("rude/name\\here") == "rude_name_here"
    assert sanitize_profile_name("") == "Unnamed"
    assert sanitize_profile_name("...") == "Unnamed"
