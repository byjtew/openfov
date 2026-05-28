"""Per-game / per-setup user profile: all the per-axis tuning lives here."""

from __future__ import annotations

import sys
import tomli_w
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from openfov.filtering.pipeline import AxisFilterParams
from openfov.mapping.axis_mapper import AxisSettings
from openfov.mapping.curve import CubicBezierCurve
from openfov.mapping.presets import linear
from openfov.persistence.paths import profile_path, profiles_dir, sanitize_profile_name

_AXES: tuple[str, ...] = ("yaw", "pitch", "roll", "x", "y", "z")


def _default_axis_settings() -> dict[str, AxisSettings]:
    """v1 defaults are tuned for iRacing correct-out-of-the-box.

    All three rotation axes start with `invert=True` — empirically that
    matches iRacing's TrackIR sign convention (head right → look right,
    head up → look up, etc.). Users can uncheck invert on any axis if
    they want the opposite mapping.

    Yaw starts enabled; pitch and roll start disabled. New users almost
    always want yaw first (looking left/right to apex) and find pitch +
    roll disorienting before they've adjusted to head-tracking.

    Sensitivity defaults to 0.75 across the board — slightly below 1:1
    so small head movements don't over-rotate the in-game camera. Users
    can crank it up per-axis once they've found their preferred feel.

    Translation axes are structurally disabled until v2 adds proper
    XYZ support (the AxisMapper short-circuits to 0 when enabled=False)."""
    return {
        "yaw":   AxisSettings(invert=True, sensitivity=0.75, curve=linear(domain=90.0), clamp_deg=90.0, enabled=True),
        "pitch": AxisSettings(invert=True, sensitivity=0.75, curve=linear(domain=90.0), clamp_deg=90.0, enabled=False),
        "roll":  AxisSettings(invert=True, sensitivity=0.75, curve=linear(domain=90.0), clamp_deg=90.0, enabled=False),
        "x": AxisSettings(invert=True, sensitivity=0.75, curve=linear(domain=200.0), clamp_deg=0.0, enabled=False),
        "y": AxisSettings(invert=True, sensitivity=0.75, curve=linear(domain=200.0), clamp_deg=0.0, enabled=False),
        "z": AxisSettings(invert=True, sensitivity=0.75, curve=linear(domain=200.0), clamp_deg=0.0, enabled=False),
    }


def _default_filter_params() -> dict[str, AxisFilterParams]:
    return {axis: AxisFilterParams() for axis in _AXES}


@dataclass
class Profile:
    """One named user profile. All tuning lives here."""

    name: str = "Default"
    game_id: str = "iracing"
    axes: dict[str, AxisSettings] = field(default_factory=_default_axis_settings)
    filters: dict[str, AxisFilterParams] = field(default_factory=_default_filter_params)

    # ---- serialization -----------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "game_id": self.game_id,
            "axes": {
                axis: {
                    "enabled": s.enabled,
                    "invert": s.invert,
                    "sensitivity": s.sensitivity,
                    "clamp_deg": s.clamp_deg,
                    "curve": s.curve.to_list(),
                }
                for axis, s in self.axes.items()
            },
            "filters": {
                axis: {
                    "min_cutoff": p.min_cutoff,
                    "beta": p.beta,
                    "d_cutoff": p.d_cutoff,
                    "median_window": p.median_window,
                    "dead_zone": p.dead_zone,
                }
                for axis, p in self.filters.items()
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "Profile":
        name = str(raw.get("name", "Default"))
        game_id = str(raw.get("game_id", "iracing"))

        axes_raw = raw.get("axes", {}) if isinstance(raw.get("axes"), dict) else {}
        axes = _default_axis_settings()
        if isinstance(axes_raw, dict):
            for axis in _AXES:
                a = axes_raw.get(axis)
                if not isinstance(a, dict):
                    continue
                curve_raw = a.get("curve")
                curve = (
                    CubicBezierCurve.from_list(curve_raw)
                    if isinstance(curve_raw, list)
                    else axes[axis].curve
                )
                axes[axis] = AxisSettings(
                    enabled=bool(a.get("enabled", axes[axis].enabled)),
                    invert=bool(a.get("invert", axes[axis].invert)),
                    sensitivity=float(a.get("sensitivity", axes[axis].sensitivity)),
                    clamp_deg=float(a.get("clamp_deg", axes[axis].clamp_deg)),
                    curve=curve,
                )

        filt_raw = raw.get("filters", {})
        filters = _default_filter_params()
        if isinstance(filt_raw, dict):
            for axis in _AXES:
                f = filt_raw.get(axis)
                if not isinstance(f, dict):
                    continue
                filters[axis] = AxisFilterParams(
                    min_cutoff=float(f.get("min_cutoff", filters[axis].min_cutoff)),
                    beta=float(f.get("beta", filters[axis].beta)),
                    d_cutoff=float(f.get("d_cutoff", filters[axis].d_cutoff)),
                    median_window=int(f.get("median_window", filters[axis].median_window)),
                    dead_zone=float(f.get("dead_zone", filters[axis].dead_zone)),
                )

        return cls(name=name, game_id=game_id, axes=axes, filters=filters)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def load_profile(name: str) -> Profile:
    """Load a profile by name. Returns a default-shaped profile if the
    target file is missing or malformed."""
    target = profile_path(name)
    if not target.exists():
        return Profile(name=name)
    try:
        with target.open("rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return Profile(name=name)
    profile = Profile.from_dict(raw)
    # Honor the on-disk filename as canonical to keep things consistent.
    profile.name = name
    return profile


def save_profile(profile: Profile) -> Path:
    target = profile_path(profile.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as f:
        tomli_w.dump(profile.to_dict(), f)
    return target


def delete_profile(name: str) -> bool:
    target = profile_path(name)
    if target.exists():
        target.unlink()
        return True
    return False


def list_profile_names() -> list[str]:
    """Return the on-disk profile display names, sorted alphabetically."""
    d = profiles_dir()
    return sorted(p.stem for p in d.glob("*.toml"))


__all__ = [
    "Profile",
    "delete_profile",
    "list_profile_names",
    "load_profile",
    "save_profile",
    "sanitize_profile_name",
]
