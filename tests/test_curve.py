"""Cubic Bezier curve evaluation tests."""

from __future__ import annotations

import numpy as np
import pytest

from openfov.mapping.curve import CubicBezierCurve, CurvePoint
from openfov.mapping.presets import aggressive_edges, deadzone, linear, soft_center


def test_two_point_linear_curve_is_actually_linear() -> None:
    curve = linear(domain=90.0)
    for x in [-90.0, -45.0, 0.0, 45.0, 90.0]:
        assert curve(x) == pytest.approx(x, abs=1e-6)


def test_endpoints_are_exact() -> None:
    curve = soft_center(domain=90.0)
    assert curve(-90.0) == pytest.approx(-117.0, abs=1e-3)  # -90 * 1.3
    assert curve(0.0) == pytest.approx(0.0, abs=1e-3)
    assert curve(90.0) == pytest.approx(117.0, abs=1e-3)


def test_out_of_domain_clamps_to_endpoint_y() -> None:
    curve = linear(domain=90.0)
    assert curve(-200.0) == pytest.approx(-90.0, abs=1e-6)
    assert curve(+200.0) == pytest.approx(+90.0, abs=1e-6)


def test_evaluate_vectorized() -> None:
    curve = linear(domain=90.0)
    xs = np.linspace(-90.0, 90.0, 11)
    ys = curve.evaluate(xs)
    assert ys.shape == xs.shape
    assert np.allclose(ys, xs, atol=1e-6)


def test_monotonic_curves_stay_monotonic() -> None:
    curve = soft_center(domain=90.0)
    xs = np.linspace(-90.0, 90.0, 200)
    ys = curve.evaluate(xs)
    assert np.all(np.diff(ys) > -1e-6)


def test_deadzone_flat_region_outputs_zero() -> None:
    curve = deadzone(domain=90.0, half_width=5.0)
    for x in (-3.0, -1.0, 0.0, 1.0, 3.0):
        assert curve(x) == pytest.approx(0.0, abs=0.01)


def test_aggressive_edges_amplifies_extremes() -> None:
    curve = aggressive_edges(domain=90.0)
    assert abs(curve(80.0)) > abs(curve(40.0)) * 1.5


def test_two_point_curve_required() -> None:
    with pytest.raises(ValueError):
        CubicBezierCurve(points=[CurvePoint(x=0.0, y=0.0)])


def test_x_must_be_strictly_increasing() -> None:
    with pytest.raises(ValueError):
        CubicBezierCurve(
            points=[CurvePoint(x=0.0, y=0.0), CurvePoint(x=0.0, y=1.0)]
        )
    with pytest.raises(ValueError):
        CubicBezierCurve(
            points=[CurvePoint(x=1.0, y=0.0), CurvePoint(x=0.0, y=1.0)]
        )


def test_serialization_roundtrip() -> None:
    original = soft_center(domain=90.0)
    serialized = original.to_list()
    restored = CubicBezierCurve.from_list(serialized)
    xs = np.linspace(-90.0, 90.0, 50)
    assert np.allclose(original.evaluate(xs), restored.evaluate(xs), atol=1e-9)
