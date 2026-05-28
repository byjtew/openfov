"""CurveEditor mutation + serialization tests.

The interactive parts (mouse drag) are best validated with pytest-qt, but
the curve-mutation primitives are pure Python — we test those directly
without faking events. The widget constructs and paints under
QT_QPA_PLATFORM=offscreen."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp() -> object:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("PySide6 not installed")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_default_curve_is_linear(qapp) -> None:  # noqa: ARG001
    from openfov.ui.curve_editor import CurveEditor

    ce = CurveEditor()
    curve = ce.curve()
    assert len(curve.points) == 2
    # Linear-ness: y(x) ~= x across the domain.
    for x in (-90.0, -45.0, 0.0, 45.0, 90.0):
        assert abs(curve(x) - x) < 1e-3


def test_preset_dispatch_changes_curve(qapp) -> None:  # noqa: ARG001
    from openfov.ui.curve_editor import CurveEditor
    from openfov.mapping.presets import soft_center

    captures: list = []
    ce = CurveEditor()
    ce.changed.connect(captures.append)
    ce._set_preset(soft_center(90.0))  # noqa: SLF001 — direct API for test
    assert len(captures) == 1
    assert len(ce.curve().points) == 3
    curve = ce.curve()
    # Soft-center anchors itself at (0, 0) and overshoots ±domain at edges.
    assert abs(curve(0.0)) < 1e-3
    assert curve(90.0) > 90.0    # edge overshoot vs linear identity
    assert curve(-90.0) < -90.0
    # Shallow near center: y(15) should be well below 15 (slope < 1 at 0).
    assert curve(15.0) < 15.0


def test_insert_point_increases_count(qapp) -> None:  # noqa: ARG001
    from openfov.ui.curve_editor import CurveEditor

    ce = CurveEditor()
    assert len(ce.curve().points) == 2
    ce._insert_point(30.0, 20.0)  # noqa: SLF001
    assert len(ce.curve().points) == 3


def test_max_six_anchors(qapp) -> None:  # noqa: ARG001
    from openfov.ui.curve_editor import CurveEditor

    ce = CurveEditor()
    # Add 5 interior points -> 7 total -> last insert ignored.
    for x in (-60, -30, 0, 30, 60, 75):
        ce._insert_point(float(x), 0.0)  # noqa: SLF001
    # Allowed up to 6 anchors. (2 endpoints + 4 interior = 6).
    assert len(ce.curve().points) == 6


def test_remove_interior_point(qapp) -> None:  # noqa: ARG001
    from openfov.ui.curve_editor import CurveEditor

    ce = CurveEditor()
    ce._insert_point(0.0, 0.0)  # noqa: SLF001
    assert len(ce.curve().points) == 3
    ce._remove_point(1)  # noqa: SLF001
    assert len(ce.curve().points) == 2


def test_endpoints_cannot_be_removed(qapp) -> None:  # noqa: ARG001
    from openfov.ui.curve_editor import CurveEditor

    ce = CurveEditor()
    ce._remove_point(0)  # noqa: SLF001 — should be a no-op
    ce._remove_point(1)  # noqa: SLF001 — last index, also a no-op
    assert len(ce.curve().points) == 2


def test_drag_endpoint_keeps_x_pinned(qapp) -> None:  # noqa: ARG001
    from openfov.ui.curve_editor import CurveEditor

    ce = CurveEditor()
    # Move the left endpoint: x should be ignored, y should track.
    ce._update_point(0, 50.0, -45.0)  # noqa: SLF001
    p = ce.curve().points[0]
    assert p.x == -90.0
    assert abs(p.y - (-45.0)) < 1e-6


def test_drag_interior_clamped_between_neighbors(qapp) -> None:  # noqa: ARG001
    from openfov.ui.curve_editor import CurveEditor

    ce = CurveEditor()
    ce._insert_point(0.0, 0.0)  # noqa: SLF001
    # Try dragging the interior anchor past the right endpoint; should clamp.
    ce._update_point(1, 200.0, 30.0)  # noqa: SLF001
    p = ce.curve().points[1]
    assert p.x < 90.0
    assert p.x > -90.0


def test_live_indicator_state(qapp) -> None:  # noqa: ARG001
    from openfov.ui.curve_editor import CurveEditor

    ce = CurveEditor()
    ce.set_live(20.0, 30.0)
    ce.clear_live()  # should not crash
