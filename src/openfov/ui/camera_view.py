"""Camera preview widget with landmark overlay.

Receives BGR frames from the pipeline thread plus an optional Nx2 array
of pixel landmarks. Draws green crosses on each landmark and a status
banner when no face is detected.

Aspect-preserving scaling — the frame fits the widget without warping.
"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QImage, QPainter, QPen, QPixmap, QColor
from PySide6.QtWidgets import QLabel, QSizePolicy


class CameraView(QLabel):
    """Black-bg label that paints the latest camera frame + landmarks."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Camera view uses its own dark background so the QSS panel
        # accent doesn't bleed through black borders during scaling.
        self.setStyleSheet("QLabel { background-color: #0a0d10; }")
        self.setText("Waiting for camera...")
        self._frame: np.ndarray | None = None
        self._landmarks: np.ndarray | None = None
        self._detected: bool = False
        self._last_pixmap_size: tuple[int, int] = (0, 0)

    @Slot(object, object)
    def update_frame(self, frame_bgr: np.ndarray, landmarks_2d: np.ndarray | None) -> None:
        self._frame = frame_bgr
        self._landmarks = landmarks_2d
        self._detected = landmarks_2d is not None and len(landmarks_2d) > 0
        self._render()

    def _render(self) -> None:
        if self._frame is None:
            return

        # BGR -> RGB without an extra copy.
        rgb = cv2.cvtColor(self._frame, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()

        # Scale, keep aspect. FastTransformation (nearest-neighbor) over
        # SmoothTransformation (CPU bilinear) — saves 15-25 ms per paint
        # at 1280x720 and looks indistinguishable in a small preview.
        target_w = max(self.width(), 1)
        target_h = max(self.height(), 1)
        pix = QPixmap.fromImage(img).scaled(
            target_w, target_h, Qt.KeepAspectRatio, Qt.FastTransformation
        )

        # Draw landmarks in pixmap-pixel coordinates. We scale the source
        # pixel coords by the same ratio QPixmap.scaled() used.
        if self._landmarks is not None and len(self._landmarks) > 0:
            scale_x = pix.width() / w
            scale_y = pix.height() / h
            painter = QPainter(pix)
            try:
                pen = QPen(QColor(60, 230, 90))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setRenderHint(QPainter.Antialiasing, True)
                for lx, ly in self._landmarks:
                    px = lx * scale_x
                    py = ly * scale_y
                    # Small cross: more legible than a dot at small sizes.
                    painter.drawLine(px - 3, py, px + 3, py)
                    painter.drawLine(px, py - 3, px, py + 3)
            finally:
                painter.end()

        # Status banner overlay if not detected.
        if not self._detected:
            painter = QPainter(pix)
            try:
                painter.setPen(QColor(240, 200, 60))
                font = painter.font()
                font.setPointSize(12)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(
                    pix.rect().adjusted(0, 0, 0, -6),
                    Qt.AlignBottom | Qt.AlignHCenter,
                    "no face detected",
                )
            finally:
                painter.end()

        self.setPixmap(pix)

    def resizeEvent(self, event) -> None:  # noqa: D401
        # Re-render so the pixmap matches the new size.
        super().resizeEvent(event)
        if self._frame is not None:
            self._render()


__all__ = ["CameraView"]
