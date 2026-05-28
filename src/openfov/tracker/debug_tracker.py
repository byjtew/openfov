"""Deterministic sine-wave tracker for tests and offline pipeline validation.

Produces a smooth periodic pose without ever touching a camera or MediaPipe.
Useful for: smoke-testing the output writer, UI development without a
webcam, CI environments."""

from __future__ import annotations

import math

import numpy as np

from openfov.tracker.base import Pose6DOF, Tracker, TrackerResult, TrackerSettings


class DebugSineTracker(Tracker):
    """Generates pose values that trace Lissajous-like figures across the axes.

    Yaw and pitch run at different frequencies so a graph of one against the
    other traces a Lissajous curve — useful for spotting axis crosstalk in
    output."""

    def __init__(self, yaw_amp: float = 30.0, pitch_amp: float = 15.0) -> None:
        self._yaw_amp = yaw_amp
        self._pitch_amp = pitch_amp
        self._started = False

    def start(self, settings: TrackerSettings) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def step(self, frame_bgr: np.ndarray, ts_ms: int) -> TrackerResult:
        if not self._started:
            raise RuntimeError("DebugSineTracker.step() before start()")
        t = ts_ms / 1000.0
        return TrackerResult(
            pose=Pose6DOF(
                yaw=self._yaw_amp * math.sin(2 * math.pi * 0.4 * t),
                pitch=self._pitch_amp * math.sin(2 * math.pi * 0.28 * t),
                roll=5.0 * math.sin(2 * math.pi * 0.7 * t),
            ),
            detected=True,
            confidence=1.0,
            landmarks_2d=None,
            inference_ms=0.05,
        )
