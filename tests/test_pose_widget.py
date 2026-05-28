"""PoseWidget construction + paint exercise.

Rendering correctness is best confirmed visually, but we can lock down
the geometry math + ensure paintEvent runs without throwing across a
representative range of poses."""

from __future__ import annotations

import os
import sys

import numpy as np
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


def test_face_geometry_present() -> None:
    """Smiley disc + eyes + smile vertex sets are built at import time."""
    from openfov.ui.pose_widget import (
        _FACE_VERTS, _LEFT_EYE_VERTS, _RIGHT_EYE_VERTS, _SMILE_VERTS,
    )

    # All in the z=0 plane.
    for verts in (_FACE_VERTS, _LEFT_EYE_VERTS, _RIGHT_EYE_VERTS, _SMILE_VERTS):
        assert verts.shape[1] == 3
        assert (verts[:, 2] == 0.0).all(), "geometry should be flat (z=0)"

    # Disc and eyes are closed loops; smile is an open polyline.
    assert _FACE_VERTS.shape[0] >= 24
    assert _LEFT_EYE_VERTS.shape[0] >= 8
    assert _RIGHT_EYE_VERTS.shape[0] >= 8
    assert _SMILE_VERTS.shape[0] >= 10


def test_rotation_matrix_identity_at_zero() -> None:
    from openfov.ui.pose_widget import _rotation_matrix

    R = _rotation_matrix(0.0, 0.0, 0.0)
    assert np.allclose(R, np.eye(3), atol=1e-9)


def test_rotation_matrix_yaw_pure() -> None:
    """Pure yaw should rotate +X towards +Z (look-left swings the nose left)."""
    from openfov.ui.pose_widget import _rotation_matrix

    R = _rotation_matrix(90.0, 0.0, 0.0)
    # Apply to nose-forward vector (0, 0, 1) — should end up at (1, 0, 0).
    nose = R @ np.array([0.0, 0.0, 1.0])
    assert np.allclose(nose, np.array([1.0, 0.0, 0.0]), atol=1e-6)


def test_paint_does_not_crash_at_extremes(qapp) -> None:  # noqa: ARG001
    """Sweep some big poses through the widget; renderer must stay
    well-behaved (no divide-by-zero, no NaN polygons)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPixmap

    from openfov.runtime.pipeline import PipelineStats
    from openfov.tracker.base import Pose6DOF
    from openfov.ui.pose_widget import PoseWidget

    w = PoseWidget()
    w.resize(240, 200)
    pix = QPixmap(w.size())

    for yaw, pitch, roll in [
        (0, 0, 0),
        (45, 20, -15),
        (-90, -45, 60),
        (170, 0, 0),
        (0, 89, 0),
        (0, 0, 89),
    ]:
        w.update_pose(
            Pose6DOF(),
            Pose6DOF(yaw=yaw, pitch=pitch, roll=roll),
            PipelineStats(fps=30.0, inference_ms=5.0, detected=True, camera_connected=True),
        )
        # Force a paint; this exercises paintEvent indirectly.
        pix.fill()
        w.render(pix, QPoint(0, 0))


def test_not_detected_state_paints_warning(qapp) -> None:  # noqa: ARG001
    from openfov.runtime.pipeline import PipelineStats
    from openfov.tracker.base import Pose6DOF
    from openfov.ui.pose_widget import PoseWidget

    w = PoseWidget()
    w.update_pose(
        Pose6DOF(), Pose6DOF(),
        PipelineStats(fps=0.0, inference_ms=0.0, detected=False, camera_connected=True),
    )
    # Painting should still succeed; we just check no exception.
    w.repaint()
