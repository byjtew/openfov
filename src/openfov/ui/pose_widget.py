"""Pose indicator widget — a flat smiley disc that rotates with the head.

A single circular plane (the smiley face) lives at z=0 in object space.
The face is drawn as a filled disc; eyes and mouth are baked-in features
on that disc. We apply the user's yaw/pitch/roll rotation to the plane
and project to screen, so the disc tilts/turns the way your head does.
No lighting, no depth sort, no mesh: just a few polygons and a
polyline. Cheap to paint (~1 ms even on integrated graphics).

Coordinates: +X right, +Y up, +Z toward viewer. The disc faces +Z when
neutral.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt, Slot
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from openfov.runtime.pipeline import PipelineStats
from openfov.tracker.base import Pose6DOF


# --- Face geometry, parametric. Built once at import-time. ----------------

_FACE_RADIUS = 1.0
_FACE_POINTS = 48           # perimeter sample count

_EYE_OFFSET_X = 0.34
_EYE_OFFSET_Y = 0.30
_EYE_RADIUS = 0.11
_EYE_POINTS = 14

_SMILE_HALF_WIDTH = 0.42
_SMILE_DROP = 0.34          # how far below center the smile sits at the ends
_SMILE_CURVE_DROP = 0.62    # bottom of the smile (the curve's deepest point)
_SMILE_POINTS = 18


def _circle_3d(cx: float, cy: float, r: float, n: int) -> np.ndarray:
    """N-point sample around a circle in the z=0 plane."""
    thetas = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
    xs = cx + r * np.cos(thetas)
    ys = cy + r * np.sin(thetas)
    zs = np.zeros_like(xs)
    return np.column_stack([xs, ys, zs])


def _smile_3d() -> np.ndarray:
    """Sample a downward-opening parabolic arc in the z=0 plane."""
    ts = np.linspace(-1.0, 1.0, _SMILE_POINTS)
    xs = _SMILE_HALF_WIDTH * ts
    # y interpolates between -SMILE_DROP at the corners and -SMILE_CURVE_DROP
    # at the middle: a simple quadratic gives the smile shape.
    ys = -_SMILE_DROP - (_SMILE_CURVE_DROP - _SMILE_DROP) * (1.0 - ts ** 2)
    zs = np.zeros_like(xs)
    return np.column_stack([xs, ys, zs])


_FACE_VERTS = _circle_3d(0.0, 0.0, _FACE_RADIUS, _FACE_POINTS)
_LEFT_EYE_VERTS = _circle_3d(-_EYE_OFFSET_X, _EYE_OFFSET_Y, _EYE_RADIUS, _EYE_POINTS)
_RIGHT_EYE_VERTS = _circle_3d(_EYE_OFFSET_X, _EYE_OFFSET_Y, _EYE_RADIUS, _EYE_POINTS)
_SMILE_VERTS = _smile_3d()


# --- Grid baked into the disc -------------------------------------------
#
# A few horizontal + vertical lines clipped to the face's circular outline.
# Sampled densely so their projection bends smoothly as the disc tilts.
# Without these, the disc reads as a uniform blob from extreme angles and
# you can't tell which way it's facing.

_GRID_LINE_SAMPLES = 18
_GRID_OFFSETS = (-0.70, -0.35, 0.0, 0.35, 0.70)  # × radius


def _grid_lines_3d() -> list[np.ndarray]:
    """Build one numpy (Nx3) sample array per grid line. Lines are
    clipped to the disc circle so they never poke out the side."""
    lines: list[np.ndarray] = []
    r = _FACE_RADIUS
    for x0_norm in _GRID_OFFSETS:
        x0 = x0_norm * r
        y_extent = math.sqrt(max(r * r - x0 * x0, 0.0))
        if y_extent <= 1e-3:
            continue
        ys = np.linspace(-y_extent, +y_extent, _GRID_LINE_SAMPLES)
        xs = np.full_like(ys, x0)
        zs = np.zeros_like(xs)
        lines.append(np.column_stack([xs, ys, zs]))
    for y0_norm in _GRID_OFFSETS:
        y0 = y0_norm * r
        x_extent = math.sqrt(max(r * r - y0 * y0, 0.0))
        if x_extent <= 1e-3:
            continue
        xs = np.linspace(-x_extent, +x_extent, _GRID_LINE_SAMPLES)
        ys = np.full_like(xs, y0)
        zs = np.zeros_like(xs)
        lines.append(np.column_stack([xs, ys, zs]))
    return lines


_GRID_LINES = _grid_lines_3d()


# --- Math helpers ---------------------------------------------------------


def _rotation_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    """Same Tait-Bryan YXZ rotation as the tracker uses.
    +yaw = look left, +pitch = up, +roll = left ear down."""
    y = math.radians(yaw_deg)
    p = math.radians(pitch_deg)
    r = math.radians(roll_deg)
    cy, sy = math.cos(y), math.sin(y)
    cp, sp = math.cos(p), math.sin(p)
    cr, sr = math.cos(r), math.sin(r)
    ry = np.array([[ cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
    return ry @ rx @ rz


# --- Widget ---------------------------------------------------------------


# Platform palette (matches resources/ui/openfov.qss).
_FACE_FILL = QColor(82, 196, 174)        # teal accent
_FACE_FILL_LOST = QColor(60, 90, 100)    # dimmed teal when no face detected
_FACE_OUTLINE = QColor(26, 93, 84)
_INK = QColor(14, 18, 23)                # eyes + smile (matches app background)
_GRID = QColor(14, 18, 23, 70)           # same ink, ~28% alpha — readable but subtle


class PoseWidget(QWidget):
    """A 2D smiley disc whose plane rotates with the head."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(220, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet("background-color: #0a0d10;")
        self._pose = Pose6DOF()
        self._detected = False

    @Slot(object, object, object)
    def update_pose(
        self, _raw: Pose6DOF, mapped: Pose6DOF, stats: "PipelineStats"
    ) -> None:
        """Connected to PipelineThread.pose_ready. We show the *mapped*
        pose (post-curve) so the user sees what iRacing will see."""
        self._pose = mapped
        self._detected = stats.detected
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        radius_px = min(w, h) * 0.36   # disc radius on screen when flat-on

        # Subtle horizon cross-hair so the rotation is readable when the
        # disc happens to land dead-center.
        painter.setPen(QPen(QColor(30, 36, 42), 1, Qt.DashLine))
        painter.drawLine(8, int(cy), w - 8, int(cy))
        painter.drawLine(int(cx), 8, int(cx), h - 8)

        # Rotate every geometry sample by the user's pose, then project.
        R = _rotation_matrix(self._pose.yaw, self._pose.pitch, self._pose.roll)

        def project(verts: np.ndarray) -> QPolygonF:
            rotated = verts @ R.T
            # Weak perspective: push back by 4 disc-radii, divide by depth.
            # That gives a perceptible-but-not-extreme foreshortening.
            depth = rotated[:, 2] + 4.0
            scale = (radius_px * 4.0) / depth
            sx = cx + rotated[:, 0] * scale
            sy = cy - rotated[:, 1] * scale  # Qt's Y is down; flip
            return QPolygonF([QPointF(float(x), float(y)) for x, y in zip(sx, sy)])

        face_poly = project(_FACE_VERTS)
        left_eye_poly = project(_LEFT_EYE_VERTS)
        right_eye_poly = project(_RIGHT_EYE_VERTS)
        smile_poly = project(_SMILE_VERTS)

        # Face fill + outline.
        fill = _FACE_FILL if self._detected else _FACE_FILL_LOST
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(_FACE_OUTLINE, 1.5))
        painter.drawPolygon(face_poly)

        # Faint orthogonal grid baked into the disc plane — distorts with
        # the disc, makes 3D rotation legible even when the smile alone
        # would look like a flat blob.
        grid_pen = QPen(_GRID)
        grid_pen.setWidthF(1.0)
        grid_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(grid_pen)
        painter.setBrush(Qt.NoBrush)
        for line_verts in _GRID_LINES:
            painter.drawPolyline(project(line_verts))

        # Eyes — solid dark circles.
        painter.setBrush(QBrush(_INK))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(left_eye_poly)
        painter.drawPolygon(right_eye_poly)

        # Smile — open polyline, not filled.
        pen = QPen(_INK)
        pen.setWidthF(max(2.2, radius_px / 26.0))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(smile_poly)

        # "no face" label when tracking is lost.
        if not self._detected:
            painter.setPen(QColor(240, 200, 60))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                self.rect().adjusted(0, 0, 0, -6),
                Qt.AlignBottom | Qt.AlignHCenter,
                "no face",
            )


__all__ = ["PoseWidget"]
