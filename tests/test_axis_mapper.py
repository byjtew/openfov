"""Axis mapper tests: invert → sensitivity → curve → clamp."""

from __future__ import annotations

import pytest

from openfov.mapping.axis_mapper import AxisMapper, AxisSettings
from openfov.mapping.presets import linear, soft_center
from openfov.tracker.base import Pose6DOF


def test_default_passthrough_for_rotation() -> None:
    """Default mapper for rotation axes is identity (within clamp)."""
    mapper = AxisMapper()
    out = mapper(Pose6DOF(yaw=10.0, pitch=-5.0, roll=2.0))
    assert out.yaw == pytest.approx(10.0, abs=1e-6)
    assert out.pitch == pytest.approx(-5.0, abs=1e-6)
    assert out.roll == pytest.approx(2.0, abs=1e-6)


def test_invert_flips_sign() -> None:
    mapper = AxisMapper(
        settings_per_axis={"yaw": AxisSettings(invert=True, curve=linear(90.0))}
    )
    out = mapper(Pose6DOF(yaw=15.0))
    assert out.yaw == pytest.approx(-15.0, abs=1e-6)


def test_sensitivity_applied_before_curve() -> None:
    """Sensitivity scales the *input* to the curve. This contract is what
    makes preset curves transferable between users."""
    mapper = AxisMapper(
        settings_per_axis={"yaw": AxisSettings(sensitivity=2.0, curve=linear(90.0))}
    )
    out = mapper(Pose6DOF(yaw=20.0))
    assert out.yaw == pytest.approx(40.0, abs=1e-6)


def test_clamp_enforced_after_curve() -> None:
    """Soft-center curve at 90° outputs 126°; clamp brings it to 90°."""
    mapper = AxisMapper(
        settings_per_axis={
            "yaw": AxisSettings(sensitivity=1.0, curve=soft_center(90.0), clamp_deg=90.0)
        }
    )
    out = mapper(Pose6DOF(yaw=90.0))
    assert out.yaw == pytest.approx(90.0, abs=1e-3)


def test_translation_default_zero() -> None:
    """The default profile has translation sensitivity=0 (v2 feature).
    Passing translation through the default mapper should return zero."""
    # Default settings for x/y/z aren't installed via AxisMapper defaults;
    # those live in Profile defaults. With raw AxisSettings defaults
    # (sensitivity=1.0), translation passes through. So this test just
    # exercises the configured-zero path:
    mapper = AxisMapper(
        settings_per_axis={
            "x": AxisSettings(sensitivity=0.0, curve=linear(200.0), clamp_deg=0.0),
        }
    )
    out = mapper(Pose6DOF(x=50.0))
    assert out.x == pytest.approx(0.0, abs=1e-6)


def test_unknown_axis_raises() -> None:
    mapper = AxisMapper()
    with pytest.raises(KeyError):
        mapper.update("nope", AxisSettings())


def test_disabled_axis_outputs_zero() -> None:
    """`enabled=False` is the user-facing off-switch — output is 0
    regardless of the rest of the chain."""
    mapper = AxisMapper(
        settings_per_axis={
            "yaw": AxisSettings(
                enabled=False, sensitivity=2.0, curve=linear(90.0),
            ),
        }
    )
    out = mapper(Pose6DOF(yaw=30.0))
    assert out.yaw == 0.0


def test_enabled_axis_passes_through() -> None:
    """Sanity inverse — enabled=True with defaults preserves the input."""
    mapper = AxisMapper(
        settings_per_axis={"yaw": AxisSettings(enabled=True, curve=linear(90.0))},
    )
    out = mapper(Pose6DOF(yaw=30.0))
    assert out.yaw == pytest.approx(30.0)
