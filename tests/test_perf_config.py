"""Performance-config tests.

Covers:
- AppConfig round-trips the new perf fields (inference_max_dim, output
  extrapolation toggle + Hz, performance preset).
- Preset spec values match what the dataclass defaults claim ("balanced"
  on a fresh AppConfig() should already report as matching).
- Inference downscale: TOML stores 0 for "native" because tomli_w can't
  encode None — round-trip must preserve None.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openfov.persistence.config import (
    PERFORMANCE_PRESETS,
    AppConfig,
    load_app_config,
    preset_values_match,
    save_app_config,
)


@pytest.fixture(autouse=True)
def _temp_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))


def test_default_appconfig_is_performance_preset() -> None:
    """The dataclass defaults should already match the named preset, so a
    user who never opens Settings doesn't show up as 'Custom'.

    Default is the "performance" preset (1280x720 capture + 320-px
    inference downscale) — chosen so the camera hits its 60 fps sweet
    spot AND MediaPipe inference stays under ~10 ms under iRacing
    load. (Capture resolution is intentionally the same across all
    presets; only inference downscale varies — see PERFORMANCE_PRESETS
    docstring for why.)"""
    cfg = AppConfig()
    assert cfg.performance_preset == "performance"
    assert preset_values_match("performance", cfg)


def test_appconfig_perf_fields_roundtrip() -> None:
    cfg = AppConfig(
        performance_preset="performance",
        camera_width=640,
        camera_height=480,
        inference_max_dim=320,
    )
    save_app_config(cfg)
    restored = load_app_config()
    assert restored.performance_preset == "performance"
    assert restored.camera_width == 640
    assert restored.camera_height == 480
    assert restored.inference_max_dim == 320


def test_inference_max_dim_none_roundtrips_through_zero() -> None:
    """None means "native, no downscale". TOML stores 0, from_dict
    converts back to None."""
    cfg = AppConfig(
        performance_preset="quality",
        inference_max_dim=None,
    )
    save_app_config(cfg)
    restored = load_app_config()
    assert restored.inference_max_dim is None
    assert restored.performance_preset == "quality"


def test_preset_values_match_distinguishes_presets() -> None:
    """Each named preset's spec uniquely identifies itself."""
    for name, spec in PERFORMANCE_PRESETS.items():
        cfg = AppConfig(
            performance_preset=name,
            camera_width=spec["camera_width"],
            camera_height=spec["camera_height"],
            inference_max_dim=spec["inference_max_dim"],
        )
        assert preset_values_match(name, cfg), f"{name} should match its own spec"
        # And not match any of the other named presets (unless two presets
        # share identical specs, which they don't right now).
        for other in PERFORMANCE_PRESETS:
            if other == name:
                continue
            assert not preset_values_match(other, cfg), (
                f"{name}'s spec accidentally matches {other}"
            )


def test_unknown_preset_name_does_not_crash() -> None:
    """preset_values_match returns False for an unknown preset rather
    than throwing — defensive against future renames."""
    cfg = AppConfig(performance_preset="nonexistent")
    assert preset_values_match("nonexistent", cfg) is False


# --- Anti-contention knobs (OpenCV thread cap + CPU affinity) ---------


def test_anti_contention_defaults() -> None:
    """Fresh config caps OpenCV to a couple threads and leaves affinity
    to the OS. These are the safe out-of-the-box values."""
    cfg = AppConfig()
    assert cfg.inference_thread_cap == 2
    assert cfg.cpu_affinity_mode == "auto"


def test_anti_contention_fields_roundtrip() -> None:
    cfg = AppConfig(inference_thread_cap=4, cpu_affinity_mode="isolate")
    save_app_config(cfg)
    restored = load_app_config()
    assert restored.inference_thread_cap == 4
    assert restored.cpu_affinity_mode == "isolate"


def test_anti_contention_knobs_are_preset_independent() -> None:
    """Setting an affinity mode / thread cap must not knock a config off
    its named preset — they're orthogonal to resolution + downscale."""
    cfg = AppConfig(inference_thread_cap=1, cpu_affinity_mode="isolate")
    assert preset_values_match("performance", cfg)


def test_bad_affinity_string_falls_back_to_auto() -> None:
    """A typo in a hand-edited TOML must not leave us in an unknown
    affinity mode — load sanitizes it back to 'auto'."""
    cfg = AppConfig(cpu_affinity_mode="garbage")
    save_app_config(cfg)
    restored = load_app_config()
    assert restored.cpu_affinity_mode == "auto"


def test_negative_thread_cap_clamps_to_zero() -> None:
    cfg = AppConfig(inference_thread_cap=-5)
    save_app_config(cfg)
    restored = load_app_config()
    assert restored.inference_thread_cap == 0
