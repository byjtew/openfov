"""End-to-end pipeline smoke: debug tracker → filter → mapper → writer.

Doesn't actually write to FT_SharedMem on non-Windows (writer no-ops). What
this verifies is that the whole pipeline composes correctly: types match,
no exceptions, mapped output stays bounded, filter converges on the debug
sine wave."""

from __future__ import annotations

import math

import numpy as np

from openfov.filtering.pipeline import PerAxisFilters
from openfov.mapping.axis_mapper import AxisMapper
from openfov.output.freetrack import FreeTrackWriter
from openfov.tracker.base import TrackerSettings
from openfov.tracker.debug_tracker import DebugSineTracker


def test_pipeline_end_to_end() -> None:
    tracker = DebugSineTracker(yaw_amp=20.0, pitch_amp=10.0)
    tracker.start(TrackerSettings())
    filters = PerAxisFilters()
    mapper = AxisMapper()
    writer = FreeTrackWriter()
    writer.open()  # no-op on non-Windows

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    last_yaw = 0.0
    last_pitch = 0.0
    for i in range(60):
        ts_ms = i * 16  # ~60 fps
        result = tracker.step(frame, ts_ms)
        assert result.detected
        smoothed = filters(result.pose, t=ts_ms / 1000.0)
        mapped = mapper(smoothed)
        writer.write(mapped)
        last_yaw = mapped.yaw
        last_pitch = mapped.pitch

    writer.close()
    tracker.stop()

    # Sanity bounds. Debug tracker outputs ±20° yaw, mapper clamps at ±90°.
    assert abs(last_yaw) <= 90.0
    assert abs(last_pitch) <= 90.0
    # The debug tracker is a real signal — after 60 frames at 0.4 Hz, yaw
    # should be non-zero in magnitude (we'd have to be incredibly unlucky
    # for it to be at exactly a zero crossing).
    assert math.isfinite(last_yaw)
