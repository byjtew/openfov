"""Rolling-window median filter.

Single-axis, stateful. Window is a small odd integer (typically 3 or 5).
At window=1 the filter is a pass-through.

Why this exists: MediaPipe's pose estimator occasionally emits a bad
frame — a single landmark misfire that shifts the Procrustes fit by a
visible amount. The One Euro filter's velocity estimator amplifies that
spike across multiple subsequent frames. A 3-wide median in front of
One Euro reduces a single-frame spike to zero contamination.

Cost: window-1 frames of latency for the middle sample at the current
frame rate. At 30 fps with window=3, that's ~33 ms of added lag. Worth
it for the spike rejection.
"""

from __future__ import annotations

from collections import deque


class MedianFilter:
    """Stateful rolling median over the last `window` samples."""

    def __init__(self, window: int = 1) -> None:
        # Clamp to a sane range. Even windows (2, 4) work but bias the
        # middle index upward and add latency without benefit, so we
        # restrict to odd values in [1, 7].
        w = max(1, int(window))
        if w % 2 == 0:
            w += 1
        self.window = min(w, 7)
        self._buf: deque[float] = deque(maxlen=self.window)

    def reset(self) -> None:
        self._buf.clear()

    def __call__(self, x: float) -> float:
        # Pass-through when window=1 — the filter is effectively disabled
        # at this setting, used as the "off" sentinel by the chained
        # filter wrapper.
        if self.window == 1:
            return x
        self._buf.append(x)
        n = len(self._buf)
        if n == 1:
            return x
        # Sort a tiny list — at window<=7, list.sort is faster than
        # heap-based incremental approaches for the buffer sizes we
        # care about, and the code stays trivial.
        s = sorted(self._buf)
        return s[n // 2]
