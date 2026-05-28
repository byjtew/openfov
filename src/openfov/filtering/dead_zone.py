"""Tracking dead-zone — zero jitter at rest, no step-jump at crossover.

Naive "epsilon" dead-zones snap the output back to the raw input the
moment |delta| crosses the threshold, which produces a visible one-step
jump exactly equal to the threshold. That feels worse than the jitter it
was supposed to fix.

This implementation tracks the last output and only advances by the
*excess* over the threshold:

    delta = x - last
    if  delta > thr: last = x - thr   (output trails by thr)
    elif delta < -thr: last = x + thr
    else: last unchanged              (held against jitter)

Net effect:
- Holding still: output is perfectly locked, no matter how much MediaPipe
  jitters within the threshold band.
- Moving smoothly: output follows the input, offset by a constant `thr`
  in the direction of motion. No step jumps, no discontinuities.

The constant trailing offset is the cost. Tune `threshold` to the smallest
value that visibly kills the rest-jitter you can see — typically 0.1-0.3°
for head pose angles. 0.0 disables the filter entirely (pass-through).
"""

from __future__ import annotations


class DeadZone:
    """Stateful tracking dead-zone for a single 1D signal."""

    def __init__(self, threshold: float = 0.0) -> None:
        self.threshold = float(threshold)
        self._last: float | None = None

    def reset(self) -> None:
        self._last = None

    def __call__(self, x: float) -> float:
        if self.threshold <= 0.0 or self._last is None:
            self._last = x
            return x
        delta = x - self._last
        if delta > self.threshold:
            self._last = x - self.threshold
        elif delta < -self.threshold:
            self._last = x + self.threshold
        # else: held — output stays at self._last to suppress sub-threshold jitter.
        return self._last
