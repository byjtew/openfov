"""Named preset response curves users can pick from the curve editor menu."""

from __future__ import annotations

from openfov.mapping.curve import CubicBezierCurve, CurvePoint


def linear(domain: float = 90.0) -> CubicBezierCurve:
    """y = x. The default."""
    return CubicBezierCurve(
        points=[
            CurvePoint(x=-domain, y=-domain, tangent_in=1.0, tangent_out=1.0),
            CurvePoint(x=+domain, y=+domain, tangent_in=1.0, tangent_out=1.0),
        ]
    )


def soft_center(domain: float = 90.0) -> CubicBezierCurve:
    """Soft response around zero, aggressive at the edges. Common for sim
    racers who want fine control near forward view and quick swing for
    apex-look. Center has shallow slope (0.2) for fine control; the
    edges ramp up to slope 2.5 so big head turns swing the camera fast."""
    return CubicBezierCurve(
        points=[
            CurvePoint(x=-domain, y=-domain * 1.3, tangent_in=2.5, tangent_out=2.5),
            CurvePoint(x=0.0, y=0.0, tangent_in=0.2, tangent_out=0.2),
            CurvePoint(x=+domain, y=+domain * 1.3, tangent_in=2.5, tangent_out=2.5),
        ]
    )


def aggressive_edges(domain: float = 90.0) -> CubicBezierCurve:
    """Higher gain near center and especially at edges. For drivers who want
    the camera to swing fast for big head turns."""
    return CubicBezierCurve(
        points=[
            CurvePoint(x=-domain, y=-domain * 1.7, tangent_in=2.5, tangent_out=2.5),
            CurvePoint(x=-domain * 0.5, y=-domain * 0.6, tangent_in=1.0, tangent_out=1.0),
            CurvePoint(x=0.0, y=0.0, tangent_in=1.0, tangent_out=1.0),
            CurvePoint(x=+domain * 0.5, y=+domain * 0.6, tangent_in=1.0, tangent_out=1.0),
            CurvePoint(x=+domain, y=+domain * 1.7, tangent_in=2.5, tangent_out=2.5),
        ]
    )


def deadzone(domain: float = 90.0, half_width: float = 3.0) -> CubicBezierCurve:
    """Flat zone of ±half_width around zero, then linear elsewhere. Useful
    for users whose neutral pose has small wobble they want to ignore."""
    return CubicBezierCurve(
        points=[
            CurvePoint(x=-domain, y=-domain, tangent_in=1.0, tangent_out=1.0),
            CurvePoint(x=-half_width, y=0.0, tangent_in=0.0, tangent_out=0.0),
            CurvePoint(x=+half_width, y=0.0, tangent_in=0.0, tangent_out=0.0),
            CurvePoint(x=+domain, y=+domain, tangent_in=1.0, tangent_out=1.0),
        ]
    )


# Convenient aliases imported from package root.
linear_curve = linear
soft_center_curve = soft_center
