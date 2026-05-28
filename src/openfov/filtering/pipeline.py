"""Per-axis filtering wrapper.

Chains three filters per pose axis, in order:

    raw → MedianFilter → OneEuroFilter → DeadZone → smoothed

Each stage is independently togglable:

- **MedianFilter**: rolling median over a small window. Rejects single-frame
  outlier spikes (the kind MediaPipe occasionally emits when its
  detection-vs-tracking pass swaps). Off when `median_window == 1`.
- **OneEuroFilter**: adaptive low-pass. The original Casiez/Roussel/Vogel
  filter. Smooths continuous noise without lagging fast motion. Always on
  (this is the central smoothing stage).
- **DeadZone**: tracking dead-zone that locks the output against
  sub-threshold movement. Kills jitter at rest at the cost of a constant
  trailing offset when moving. Off when `dead_zone == 0.0`.

Defaults: median + dead_zone both *off* so behavior matches pre-existing
profiles exactly. Users opt into either stage via the FilterPanel UI."""

from __future__ import annotations

from dataclasses import dataclass

from openfov.filtering.dead_zone import DeadZone
from openfov.filtering.median import MedianFilter
from openfov.filtering.one_euro import OneEuroFilter
from openfov.tracker.base import Pose6DOF

_AXES: tuple[str, ...] = ("yaw", "pitch", "roll", "x", "y", "z")


@dataclass
class AxisFilterParams:
    """Tuning for a single axis. One Euro params drive the central
    smoothing; `median_window` and `dead_zone` are the new robustness
    knobs added when users complained One Euro alone wasn't cutting it."""

    # One Euro Filter — the central adaptive low-pass.
    min_cutoff: float = 1.0
    beta: float = 0.05
    d_cutoff: float = 1.0

    # Outlier rejection (pre-stage). 1 disables (pass-through); 3 or 5
    # enable a small rolling median in front of the smoother. On by
    # default (window=3) — significantly improves output cleanliness
    # by killing single-frame tracker glitches before they contaminate
    # the velocity estimator. May slightly increase processing load.
    median_window: int = 3

    # Tracking dead-zone (post-stage). 0.0 disables. Units match the
    # axis: degrees for yaw/pitch/roll, mm for x/y/z. Off by default.
    dead_zone: float = 0.0


class _AxisChain:
    """The three-stage pipeline for one axis. Holds the stage instances
    so they can be swapped/reset without rebuilding the whole filter."""

    def __init__(self, params: AxisFilterParams) -> None:
        self._median = MedianFilter(window=params.median_window)
        self._one_euro = OneEuroFilter(
            min_cutoff=params.min_cutoff,
            beta=params.beta,
            d_cutoff=params.d_cutoff,
        )
        self._dead_zone = DeadZone(threshold=params.dead_zone)

    def update(self, params: AxisFilterParams) -> None:
        # Median window is structural — if it changed we have to rebuild
        # the deque. For window stays the same we leave the buffered
        # samples in place so a parameter tweak doesn't visibly stutter.
        if self._median.window != max(1, int(params.median_window)):
            self._median = MedianFilter(window=params.median_window)
        self._one_euro.min_cutoff = params.min_cutoff
        self._one_euro.beta = params.beta
        self._one_euro.d_cutoff = params.d_cutoff
        self._dead_zone.threshold = float(params.dead_zone)

    def reset(self) -> None:
        self._median.reset()
        self._one_euro.reset()
        self._dead_zone.reset()

    def __call__(self, x: float, t: float | None = None) -> float:
        return self._dead_zone(self._one_euro(self._median(x), t))


class PerAxisFilters:
    """Smooth a `Pose6DOF` with independent three-stage filter chains
    per axis (median → One Euro → dead-zone)."""

    def __init__(self, params_per_axis: dict[str, AxisFilterParams] | None = None) -> None:
        params = params_per_axis or {}
        self._chains: dict[str, _AxisChain] = {
            axis: _AxisChain(params.get(axis, AxisFilterParams())) for axis in _AXES
        }

    def update_params(self, axis: str, params: AxisFilterParams) -> None:
        if axis not in self._chains:
            raise KeyError(f"unknown axis {axis!r}")
        self._chains[axis].update(params)

    def reset(self) -> None:
        for c in self._chains.values():
            c.reset()

    def __call__(self, pose: Pose6DOF, t: float | None = None) -> Pose6DOF:
        return Pose6DOF(
            yaw=self._chains["yaw"](pose.yaw, t),
            pitch=self._chains["pitch"](pose.pitch, t),
            roll=self._chains["roll"](pose.roll, t),
            x=self._chains["x"](pose.x, t),
            y=self._chains["y"](pose.y, t),
            z=self._chains["z"](pose.z, t),
        )
