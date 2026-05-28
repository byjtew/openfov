"""Integration tests for the chained per-axis filter pipeline.

The pipeline is: MedianFilter → OneEuroFilter → DeadZone, per axis.
These tests verify the orchestration glue (PerAxisFilters) rather than
the individual filters (those have dedicated test modules)."""

from __future__ import annotations

import pytest

from openfov.filtering.pipeline import AxisFilterParams, PerAxisFilters
from openfov.tracker.base import Pose6DOF


def test_defaults_first_sample_passes_through() -> None:
    """With default params (median on at window=3, dead-zone off), the
    first sample seen by the chain should still pass straight through —
    a 1-element median equals its input, One Euro returns its first
    sample as-is, and a fresh dead-zone records the first sample without
    clamping. Locks down the "no startup glitches" promise."""
    f = PerAxisFilters()
    p = Pose6DOF(yaw=10.0, pitch=5.0)
    out = f(p, t=0.0)
    assert out.yaw == pytest.approx(10.0)
    assert out.pitch == pytest.approx(5.0)


def test_median_rejects_single_frame_spike_through_chain() -> None:
    """A bad MediaPipe frame (huge spike) should not contaminate the
    output when the median pre-stage is enabled."""
    f = PerAxisFilters({
        "yaw": AxisFilterParams(
            min_cutoff=10.0,  # high cutoff → one euro tracks fast
            beta=0.0,
            median_window=3,
        ),
    })
    # Seed with two clean values so the median buffer fills.
    f(Pose6DOF(yaw=10.0), t=0.0)
    f(Pose6DOF(yaw=10.0), t=0.1)
    # Inject a wild spike.
    spike_out = f(Pose6DOF(yaw=1000.0), t=0.2).yaw
    # Median of [10, 10, 1000] = 10. One Euro will track that → output
    # should be near 10, certainly not near 1000.
    assert spike_out < 50.0


def test_dead_zone_locks_output_against_subthreshold_jitter() -> None:
    """With dead-zone on, sub-threshold input changes should not move
    the output at all."""
    f = PerAxisFilters({
        "yaw": AxisFilterParams(
            min_cutoff=10.0,
            beta=0.0,
            dead_zone=0.5,
        ),
    })
    f(Pose6DOF(yaw=10.0), t=0.0)
    # Many noisy samples within ±0.4 of 10.0 — output should stay locked.
    outputs = []
    for i in range(20):
        ts = (i + 1) / 60.0
        # Alternating jitter inside the dead-zone band.
        jitter = 0.4 if i % 2 == 0 else -0.4
        outputs.append(f(Pose6DOF(yaw=10.0 + jitter), t=ts).yaw)
    # All outputs should be identical (held at first sample's smoothed value).
    spread = max(outputs) - min(outputs)
    assert spread < 0.01


def test_update_params_changes_behavior_live() -> None:
    """update_params() should rebuild the median window if it changes
    and apply new dead-zone / one-euro values on the next sample."""
    f = PerAxisFilters()
    f(Pose6DOF(yaw=10.0), t=0.0)
    f.update_params(
        "yaw",
        AxisFilterParams(min_cutoff=1.0, beta=0.05, median_window=3, dead_zone=1.0),
    )
    # Push 10.0 again — sub-1.0 deltas should now hold. (The chain has
    # one sample memory from before update; second sample after the
    # update will be the first comparison against the new dead-zone.)
    f(Pose6DOF(yaw=10.0), t=0.1)
    out = f(Pose6DOF(yaw=10.3), t=0.2).yaw
    # 0.3 delta is well under the 1.0 dead-zone — held at previous value.
    assert out == pytest.approx(10.0, abs=0.05)


def test_reset_clears_all_three_stages() -> None:
    """reset() must wipe state in median, one euro, and dead-zone."""
    f = PerAxisFilters({
        "yaw": AxisFilterParams(median_window=3, dead_zone=0.5),
    })
    # Burn in some state.
    for i in range(5):
        f(Pose6DOF(yaw=10.0), t=i / 60.0)
    f.reset()
    # First sample after reset should pass through unchanged — confirming
    # all three stages forgot their history.
    out = f(Pose6DOF(yaw=42.0), t=10.0).yaw
    assert out == pytest.approx(42.0)


def test_unknown_axis_raises_keyerror() -> None:
    f = PerAxisFilters()
    with pytest.raises(KeyError):
        f.update_params("nonexistent", AxisFilterParams())


def test_all_six_axes_independently_filtered() -> None:
    """Each axis has its own chain; tweaking one shouldn't affect others."""
    f = PerAxisFilters({
        "yaw": AxisFilterParams(dead_zone=10.0),  # heavy dead-zone on yaw only
    })
    f(Pose6DOF(yaw=0.0, pitch=0.0, roll=0.0), t=0.0)
    out = f(Pose6DOF(yaw=5.0, pitch=5.0, roll=5.0), t=0.1)
    # Yaw is locked by its 10° dead-zone, pitch + roll follow normally.
    assert out.yaw == pytest.approx(0.0, abs=0.5)  # held by dead-zone
    assert out.pitch > 1.0  # one-euro tracking
    assert out.roll > 1.0
