"""Dead-zone filter tests.

The tracking dead-zone is the post-stage that locks output against
sub-threshold movement. Key invariants to verify:

1. threshold=0 → pass-through
2. First sample is returned as-is (we have no "last" yet)
3. Sub-threshold deltas hold the last output (zero jitter at rest)
4. Above-threshold deltas advance the output by (delta - threshold),
   not the full delta — no step-jumps at crossover
5. Direction reversal works symmetrically
6. Reset clears the last-output state
"""

from __future__ import annotations

import pytest

from openfov.filtering.dead_zone import DeadZone


def test_threshold_zero_is_passthrough() -> None:
    f = DeadZone(threshold=0.0)
    for v in (1.0, 1.0001, -3.0, 100.0):
        assert f(v) == v


def test_first_sample_is_returned_as_is() -> None:
    f = DeadZone(threshold=1.0)
    assert f(42.0) == 42.0


def test_sub_threshold_jitter_is_held() -> None:
    """The exact use case: head still, MediaPipe wobbles ±0.1°,
    threshold is 0.2°. Output should be perfectly locked."""
    f = DeadZone(threshold=0.2)
    f(10.0)
    # All these are within ±0.2 of 10.0 → output held.
    assert f(10.1) == 10.0
    assert f(9.9) == 10.0
    assert f(10.19) == 10.0
    assert f(9.81) == 10.0


def test_above_threshold_advances_by_excess() -> None:
    """When the input crosses the threshold, the output advances by
    (delta - threshold), preserving sign. This is the key property —
    a naive dead-zone would advance by the full delta at crossover,
    producing a step-jump exactly equal to the threshold."""
    f = DeadZone(threshold=0.5)
    f(10.0)
    # delta = +2.0, threshold = 0.5 → new last = input - threshold = 11.5
    assert f(12.0) == pytest.approx(11.5)
    # delta from 11.5 is -3.5 → new last = input + threshold = 8.5
    assert f(8.0) == pytest.approx(8.5)


def test_negative_direction_symmetric() -> None:
    f = DeadZone(threshold=0.3)
    f(0.0)
    # delta = -1.0 → new last = input + threshold = -0.7
    assert f(-1.0) == pytest.approx(-0.7)
    # Within ±0.3 of -0.7 → held.
    assert f(-0.5) == pytest.approx(-0.7)
    # Above threshold the other way: delta = +1.0 - (-0.7) = 1.7 > 0.3
    # → new last = 1.0 - 0.3 = 0.7
    assert f(1.0) == pytest.approx(0.7)


def test_continuous_motion_trails_by_threshold() -> None:
    """A smoothly-moving input → output trails by exactly the threshold."""
    f = DeadZone(threshold=0.1)
    f(0.0)
    # Each step is +1.0 (well above the 0.1 threshold).
    out1 = f(1.0)
    out2 = f(2.0)
    out3 = f(3.0)
    # Each output should be input - threshold (the trailing offset).
    assert out1 == pytest.approx(0.9)
    assert out2 == pytest.approx(1.9)
    assert out3 == pytest.approx(2.9)


def test_reset_clears_state() -> None:
    f = DeadZone(threshold=1.0)
    f(10.0)
    f(10.5)  # held — output is 10.0
    f.reset()
    # First sample after reset should pass through, not be measured
    # against the stale 10.0.
    assert f(50.0) == 50.0


def test_threshold_change_takes_effect_immediately() -> None:
    """Mutating `threshold` between calls (as the UI does when the
    slider moves) must apply on the next sample."""
    f = DeadZone(threshold=1.0)
    f(0.0)
    assert f(0.5) == 0.0  # held with threshold=1.0
    f.threshold = 0.1
    # Same 0.5 input now exceeds the new 0.1 threshold.
    # delta from last (0.0) is 0.5, excess is 0.4, new last = 0.5 - 0.1 = 0.4.
    assert f(0.5) == pytest.approx(0.4)
