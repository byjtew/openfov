"""One Euro Filter (Casiez, Roussel, Vogel — CHI 2012).

Low-lag, low-jitter smoothing for noisy signals like head pose. Two tunables:
- `min_cutoff`: low-frequency cutoff (Hz). Lower = smoother when still,
  more lag when moving.
- `beta`: speed coefficient. Higher = less lag when moving fast, more
  jitter when still.
"""

from __future__ import annotations

import math
import time


def _smoothing_factor(t_elapsed: float, cutoff: float) -> float:
    r = 2.0 * math.pi * cutoff * t_elapsed
    return r / (r + 1.0)


def _exp_smooth(alpha: float, x: float, x_prev: float) -> float:
    return alpha * x + (1.0 - alpha) * x_prev


class OneEuroFilter:
    """Stateful 1D One Euro filter. Reset on calibration / hard pose
    changes so the derivative estimate doesn't carry over stale signal."""

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.01,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self._x_prev: float | None = None
        self._dx_prev: float = 0.0
        self._t_prev: float | None = None

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    def __call__(self, x: float, t: float | None = None) -> float:
        if t is None:
            t = time.monotonic()
        if self._t_prev is None or self._x_prev is None:
            self._t_prev = t
            self._x_prev = x
            self._dx_prev = 0.0
            return x

        t_e = max(t - self._t_prev, 1e-6)
        dx = (x - self._x_prev) / t_e
        a_d = _smoothing_factor(t_e, self.d_cutoff)
        dx_hat = _exp_smooth(a_d, dx, self._dx_prev)

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = _smoothing_factor(t_e, cutoff)
        x_hat = _exp_smooth(a, x, self._x_prev)

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat
