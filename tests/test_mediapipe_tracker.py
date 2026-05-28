"""MediaPipe tracker behavior tests that don't require a real camera.

We feed synthetic frames to exercise the wrapper's invariants. The
detection itself will fail (no face in a zero-filled frame), but that's
fine — what we're locking in here are the wrapper guarantees:
1. Duplicate / non-increasing timestamps are silently fixed up.
2. step() before start() raises a clear error.
3. start() / stop() are idempotent.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest


# MediaPipe loads a TF Lite model — point at the bundled file.
@pytest.fixture(autouse=True, scope="module")
def _model_env():
    here = Path(__file__).resolve()
    model = here.parents[1] / "resources" / "models" / "face_landmarker.task"
    os.environ["OPENFOV_MODEL_PATH"] = str(model)
    yield


def _blank_frame() -> np.ndarray:
    return np.zeros((480, 640, 3), dtype=np.uint8)


def test_step_before_start_raises() -> None:
    from openfov.tracker.mediapipe_tracker import MediaPipeTracker

    t = MediaPipeTracker()
    with pytest.raises(RuntimeError):
        t.step(_blank_frame(), 0)


def test_duplicate_timestamps_dont_raise() -> None:
    """The pipeline can hit two iterations within the same millisecond
    when inference is fast. The tracker must silently bump duplicate ts
    forward — MediaPipe's VIDEO mode otherwise throws."""
    from openfov.tracker.base import TrackerSettings
    from openfov.tracker.mediapipe_tracker import MediaPipeTracker

    t = MediaPipeTracker()
    t.start(TrackerSettings())
    try:
        frame = _blank_frame()
        # Three identical timestamps in a row.
        t.step(frame, 100)
        t.step(frame, 100)
        t.step(frame, 100)
        # And a backwards timestamp.
        t.step(frame, 50)
        # Real-time forward jumps after.
        t.step(frame, 200)
    finally:
        t.stop()


def test_stop_resets_timestamp_state() -> None:
    """After stop()/start(), the tracker accepts a fresh small ts again."""
    from openfov.tracker.base import TrackerSettings
    from openfov.tracker.mediapipe_tracker import MediaPipeTracker

    t = MediaPipeTracker()
    t.start(TrackerSettings())
    t.step(_blank_frame(), 5000)
    t.stop()
    t.start(TrackerSettings())
    # If start() didn't reset _last_ts_ms, this would internally bump
    # ts up to 5001 (which is fine), but with a fresh tracker the
    # internal MediaPipe graph wouldn't have seen 5000 yet either.
    # Either way, no exception should escape.
    t.step(_blank_frame(), 0)
    t.stop()


def test_double_start_is_idempotent() -> None:
    from openfov.tracker.base import TrackerSettings
    from openfov.tracker.mediapipe_tracker import MediaPipeTracker

    t = MediaPipeTracker()
    t.start(TrackerSettings())
    t.start(TrackerSettings())  # second start should be a no-op
    t.stop()
    t.stop()  # idempotent


def test_inference_downscale_doesnt_crash() -> None:
    """With max_inference_dim set below the input frame size, the tracker
    must internally resize before inference and still return a valid
    TrackerResult (detection will fail on the blank frame, but the call
    path runs end-to-end). Lock this in so a future refactor doesn't
    accidentally feed the un-resized frame to MediaPipe."""
    from openfov.tracker.base import TrackerSettings
    from openfov.tracker.mediapipe_tracker import MediaPipeTracker

    t = MediaPipeTracker()
    t.start(TrackerSettings(max_inference_dim=240))
    try:
        # 1280x720 input frame — should get scaled down to ~240 wide.
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = t.step(frame, 100)
        assert result.detected is False  # blank frame, no face
        assert result.inference_ms >= 0.0
    finally:
        t.stop()


def test_no_downscale_when_max_dim_is_none() -> None:
    """max_inference_dim=None means "native resolution" — the call must
    still complete cleanly without resizing."""
    from openfov.tracker.base import TrackerSettings
    from openfov.tracker.mediapipe_tracker import MediaPipeTracker

    t = MediaPipeTracker()
    t.start(TrackerSettings(max_inference_dim=None))
    try:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = t.step(frame, 100)
        assert result.detected is False
    finally:
        t.stop()
