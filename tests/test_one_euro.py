"""One Euro filter sanity tests. Goal isn't to verify the literature — the
algorithm is canonical — but to lock down behaviors the rest of the pipeline
relies on (idempotent first sample, reset clears state, monotonic time, etc.)."""

from __future__ import annotations

import math

import pytest

from openfov.filtering.one_euro import OneEuroFilter


def test_first_sample_passes_through() -> None:
    f = OneEuroFilter()
    assert f(42.0, t=0.0) == 42.0


def test_idle_signal_converges_to_input() -> None:
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    last = 0.0
    for i in range(200):
        last = f(10.0, t=i / 60.0)
    assert last == pytest.approx(10.0, abs=1e-3)


def test_high_frequency_input_is_attenuated() -> None:
    """Very-high-freq noise should be smoothed more than the carrier."""
    f = OneEuroFilter(min_cutoff=0.5, beta=0.0)
    outputs: list[float] = []
    for i in range(200):
        t = i / 60.0
        x = 10.0 + math.sin(2 * math.pi * 20.0 * t)  # 20 Hz noise on a DC signal
        outputs.append(f(x, t=t))
    # After settling, the output's range should be much smaller than the raw
    # ±1.0 of the input noise.
    tail = outputs[100:]
    spread = max(tail) - min(tail)
    assert spread < 0.5  # generous; tightens as cutoff lowers


def test_reset_clears_history() -> None:
    f = OneEuroFilter()
    for i in range(20):
        f(50.0, t=i / 60.0)
    f.reset()
    assert f(0.0, t=10.0) == 0.0


def test_zero_dt_is_safe() -> None:
    """Two samples at the same monotonic timestamp shouldn't divide by zero."""
    f = OneEuroFilter()
    f(1.0, t=0.0)
    out = f(2.0, t=0.0)
    assert math.isfinite(out)
