"""Tracker abstract base + shared pose / settings dataclasses.

A `Tracker` consumes BGR frames and produces a `TrackerResult` containing
6DOF head pose, detection confidence, optional 2D landmarks for the UI
overlay, and per-frame inference timing. All tracker implementations
(MediaPipe, ONNX, debug-sine, etc.) conform to this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Pose6DOF:
    """Head pose relative to the user's calibrated neutral.

    Angles are degrees. Translation is millimeters. Sign conventions match
    the FreeTrack proto: +yaw = look left, +pitch = up, +roll = left ear
    down. Translation axes are right-handed, +X = right, +Y = up, +Z = away
    from monitor.
    """

    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class TrackerResult:
    """One frame's tracker output."""

    pose: Pose6DOF = field(default_factory=Pose6DOF)
    detected: bool = False
    confidence: float = 0.0
    landmarks_2d: np.ndarray | None = None  # shape (N, 2), pixel coords
    inference_ms: float = 0.0


@dataclass
class TrackerSettings:
    """Knobs the tracker honors. Per-axis filtering / curves / inversion live
    elsewhere in the pipeline; this dataclass is only about the raw pose
    source."""

    min_detection_confidence: float = 0.5
    min_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5

    # Asset path for ML models (MediaPipe needs face_landmarker.task).
    # If None, the tracker resolves the bundled default.
    model_path: str | None = None

    # If set, the tracker downscales each input frame so its longest side
    # is at most this many pixels before running inference. MediaPipe's
    # FaceLandmarker rescales to 256x256 internally anyway, so feeding it
    # smaller images is essentially free in accuracy and cuts cvtColor +
    # detection-pass cost dramatically. None means "no downscale, native
    # resolution."
    max_inference_dim: int | None = None


class Tracker(ABC):
    """Abstract tracker. Concrete subclasses must be safe to use from the
    pipeline thread; they do not own threading themselves."""

    @abstractmethod
    def start(self, settings: TrackerSettings) -> None:
        """Allocate model + state. Idempotent."""

    @abstractmethod
    def step(self, frame_bgr: np.ndarray, ts_ms: int) -> TrackerResult:
        """Process one frame. `ts_ms` is a monotonic millisecond timestamp
        (only required to be monotonically non-decreasing within one
        `start`/`stop` cycle)."""

    @abstractmethod
    def stop(self) -> None:
        """Release model + state. Idempotent."""
