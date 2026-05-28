"""Piecewise cubic Bezier response curve for one axis.

The curve is defined by an ordered sequence of `CurvePoint`s. Between each
consecutive pair of points we draw a cubic Bezier whose tangent handles are
local to each anchor; this gives users a familiar drag-control-points UX
without surfacing raw handle math.

The curve is C0-continuous at anchors but not necessarily C1. That's the
right call for response curves — users often want a hard kink at the
deadzone boundary and we shouldn't auto-smooth it away.

Evaluation is vectorized over a numpy array of inputs so the UI can render
the live trace at 60 Hz without a per-frame Python loop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class CurvePoint:
    """One anchor on the curve.

    `tangent_in` and `tangent_out` are slopes (dy/dx) of the curve at this
    point on the left and right side respectively. The Bezier segment
    between two anchors uses the right tangent of the first and the left
    tangent of the second."""

    x: float
    y: float
    tangent_in: float = 1.0
    tangent_out: float = 1.0


def _segment_bezier_y(
    x: np.ndarray,
    p0: CurvePoint,
    p1: CurvePoint,
) -> np.ndarray:
    """Evaluate one cubic Bezier segment at the given x values.

    Control points are placed 1/3 of the segment width away from each
    anchor along that anchor's tangent direction. This makes
    `tangent_out`/`tangent_in` behave intuitively as slopes."""
    dx = p1.x - p0.x
    if dx <= 0.0:
        return np.full_like(x, p0.y, dtype=np.float64)

    # Bezier control points.
    c0_x = p0.x + dx / 3.0
    c0_y = p0.y + (dx / 3.0) * p0.tangent_out
    c1_x = p1.x - dx / 3.0
    c1_y = p1.y - (dx / 3.0) * p1.tangent_in

    # Solve cubic Bezier x(t) = x for t per sample, then evaluate y(t).
    # We use bisection — Bezier x-coordinates are monotonic when control
    # x-coords are strictly between anchor x-coords (which they are by
    # construction above).
    t_lo = np.zeros_like(x, dtype=np.float64)
    t_hi = np.ones_like(x, dtype=np.float64)
    for _ in range(30):  # 30 iterations → ~1e-9 precision; cheap
        t_mid = 0.5 * (t_lo + t_hi)
        u = 1.0 - t_mid
        bx = (
            u**3 * p0.x
            + 3.0 * u**2 * t_mid * c0_x
            + 3.0 * u * t_mid**2 * c1_x
            + t_mid**3 * p1.x
        )
        too_low = bx < x
        t_lo = np.where(too_low, t_mid, t_lo)
        t_hi = np.where(too_low, t_hi, t_mid)

    t = 0.5 * (t_lo + t_hi)
    u = 1.0 - t
    return (
        u**3 * p0.y
        + 3.0 * u**2 * t * c0_y
        + 3.0 * u * t**2 * c1_y
        + t**3 * p1.y
    )


@dataclass
class CubicBezierCurve:
    """A piecewise cubic Bezier curve, defined by an ordered list of anchors.

    Domain is the closed interval `[points[0].x, points[-1].x]`. Inputs
    outside the domain are clamped to the endpoints' y values. The curve
    must have at least 2 points and be sorted strictly increasing in x.
    """

    points: list[CurvePoint] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("CubicBezierCurve requires at least 2 points")
        xs = [p.x for p in self.points]
        if any(b <= a for a, b in zip(xs, xs[1:])):
            raise ValueError("CubicBezierCurve points must be strictly increasing in x")

    @property
    def x_min(self) -> float:
        return self.points[0].x

    @property
    def x_max(self) -> float:
        return self.points[-1].x

    def evaluate(self, x: float | Iterable[float] | np.ndarray) -> np.ndarray:
        """Evaluate the curve at one or more x values. Returns an ndarray of
        the same shape as the input (scalars come back as a 0-d array; cast
        with `.item()` if you need a scalar)."""

        x_arr = np.asarray(x, dtype=np.float64)
        scalar_input = x_arr.ndim == 0
        if scalar_input:
            x_arr = x_arr.reshape(1)

        # Clamp out-of-domain values to endpoints.
        x_clamped = np.clip(x_arr, self.x_min, self.x_max)
        result = np.empty_like(x_clamped, dtype=np.float64)

        # Process each segment in one batch.
        for p0, p1 in zip(self.points, self.points[1:]):
            mask = (x_clamped >= p0.x) & (x_clamped <= p1.x)
            if not mask.any():
                continue
            result[mask] = _segment_bezier_y(x_clamped[mask], p0, p1)

        return result.reshape(()) if scalar_input else result

    def __call__(self, x: float) -> float:
        """Convenience for single-scalar evaluation."""
        v = self.evaluate(x)
        return float(v if v.ndim == 0 else v[0])

    # ---- serialization helpers ---------------------------------------

    def to_list(self) -> list[dict[str, float]]:
        """TOML/JSON-friendly representation."""
        return [
            {"x": p.x, "y": p.y, "tangent_in": p.tangent_in, "tangent_out": p.tangent_out}
            for p in self.points
        ]

    @classmethod
    def from_list(cls, raw: list[dict[str, float]]) -> "CubicBezierCurve":
        return cls(
            points=[
                CurvePoint(
                    x=float(p["x"]),
                    y=float(p["y"]),
                    tangent_in=float(p.get("tangent_in", 1.0)),
                    tangent_out=float(p.get("tangent_out", 1.0)),
                )
                for p in raw
            ]
        )


def linear_curve(domain: float = 90.0, slope: float = 1.0) -> CubicBezierCurve:
    """A straight y=slope*x curve over [-domain, +domain]. Used as the
    default for each axis until the user shapes it."""
    return CubicBezierCurve(
        points=[
            CurvePoint(x=-domain, y=-domain * slope, tangent_in=slope, tangent_out=slope),
            CurvePoint(x=+domain, y=+domain * slope, tangent_in=slope, tangent_out=slope),
        ]
    )
