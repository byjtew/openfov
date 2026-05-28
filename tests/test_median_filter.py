"""Median filter tests."""

from __future__ import annotations

from openfov.filtering.median import MedianFilter


def test_window_1_is_passthrough() -> None:
    f = MedianFilter(window=1)
    for v in (1.0, -3.5, 100.0):
        assert f(v) == v


def test_window_3_returns_input_until_buffer_fills() -> None:
    """Single sample → output is that sample. Two samples → median of
    the two (the larger / second one with our sorted-middle approach)."""
    f = MedianFilter(window=3)
    assert f(1.0) == 1.0
    # With 2 samples [1, 2], sorted middle index 1 = 2.0
    assert f(2.0) == 2.0


def test_window_3_rejects_single_frame_spike() -> None:
    """The killer feature: a single outlier surrounded by normal values
    gets the middle vote and is suppressed."""
    f = MedianFilter(window=3)
    f(10.0)
    f(10.0)
    # Spike sandwiched between two normal values.
    assert f(1000.0) == 10.0  # median of [10, 10, 1000] = 10
    # Recovers cleanly on the next normal sample.
    assert f(10.0) == 10.0  # median of [10, 1000, 10] = 10


def test_window_3_follows_real_trends() -> None:
    """A genuine monotonic trend should pass through with one frame of
    lag (the median of three monotonic values is the middle one)."""
    f = MedianFilter(window=3)
    f(1.0)
    f(2.0)
    assert f(3.0) == 2.0
    assert f(4.0) == 3.0
    assert f(5.0) == 4.0


def test_even_window_is_promoted_to_odd() -> None:
    """We disallow even windows — they bias the median upward without
    benefit. window=4 should become 5."""
    f = MedianFilter(window=4)
    assert f.window == 5


def test_window_clamped_to_max_7() -> None:
    f = MedianFilter(window=999)
    assert f.window == 7


def test_reset_clears_buffer() -> None:
    f = MedianFilter(window=3)
    f(10.0)
    f(10.0)
    f.reset()
    # After reset, first sample comes back as-is rather than being
    # averaged with stale 10.0s.
    assert f(50.0) == 50.0


def test_window_below_1_clamps() -> None:
    f = MedianFilter(window=0)
    assert f.window == 1
    f2 = MedianFilter(window=-5)
    assert f2.window == 1
