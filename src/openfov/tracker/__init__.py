"""Head pose tracking. The `Tracker` interface lets us swap implementations
(MediaPipe today, an ONNX 6DRepNet model later) without touching the rest of
the pipeline."""

from openfov.tracker.base import Pose6DOF, Tracker, TrackerResult, TrackerSettings

__all__ = ["Pose6DOF", "Tracker", "TrackerResult", "TrackerSettings"]
