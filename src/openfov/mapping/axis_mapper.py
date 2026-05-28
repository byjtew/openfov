"""Per-axis pipeline: invert → sensitivity → curve → clamp.

Curves give shape; sensitivity gives uniform scale; invert flips sign. The
order matters: we apply sensitivity *before* the curve so the curve always
sees the same input domain regardless of how the user has scaled it. This
keeps preset curves transferable between users with different sensitivity
preferences."""

from __future__ import annotations

from dataclasses import dataclass, field

from openfov.mapping.curve import CubicBezierCurve
from openfov.mapping.presets import linear_curve
from openfov.tracker.base import Pose6DOF

_AXES: tuple[str, ...] = ("yaw", "pitch", "roll", "x", "y", "z")


@dataclass
class AxisSettings:
    """Per-axis tuning the AxisMapper honors.

    `enabled=False` is the user-facing "off switch" for an axis — the
    mapper outputs zero for that axis regardless of input, without
    losing the user's sensitivity/curve/invert state. Roll defaults
    off so a fresh user doesn't get an unexpected head-tilt response.
    """

    invert: bool = False
    sensitivity: float = 1.0
    curve: CubicBezierCurve = field(default_factory=linear_curve)
    clamp_deg: float = 90.0  # for rotation axes; ignored for translation
    enabled: bool = True


class AxisMapper:
    """Maps a raw `Pose6DOF` (post-filter) into a final output `Pose6DOF`
    using each axis's settings."""

    def __init__(self, settings_per_axis: dict[str, AxisSettings] | None = None) -> None:
        s = settings_per_axis or {}
        self._settings: dict[str, AxisSettings] = {
            axis: s.get(axis, AxisSettings()) for axis in _AXES
        }

    def update(self, axis: str, settings: AxisSettings) -> None:
        if axis not in self._settings:
            raise KeyError(f"unknown axis {axis!r}")
        self._settings[axis] = settings

    def get(self, axis: str) -> AxisSettings:
        return self._settings[axis]

    def __call__(self, pose: Pose6DOF) -> Pose6DOF:
        return Pose6DOF(
            yaw=self._map_axis("yaw", pose.yaw),
            pitch=self._map_axis("pitch", pose.pitch),
            roll=self._map_axis("roll", pose.roll),
            x=self._map_axis("x", pose.x),
            y=self._map_axis("y", pose.y),
            z=self._map_axis("z", pose.z),
        )

    def _map_axis(self, axis: str, value: float) -> float:
        s = self._settings[axis]
        if not s.enabled:
            return 0.0
        if s.invert:
            value = -value
        scaled = value * s.sensitivity
        shaped = float(s.curve.evaluate(scaled))
        if s.clamp_deg > 0:
            shaped = max(-s.clamp_deg, min(s.clamp_deg, shaped))
        return shaped
