"""Live pose readout.

Large monospace yaw/pitch/roll display + small fps/inference subtext.
Updates from the pipeline thread via Qt signals."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from openfov.runtime.pipeline import PipelineStats
from openfov.tracker.base import Pose6DOF


class PoseReadout(QFrame):
    """Group-box-ish frame showing current pose values + fps."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)

        # Big monospace number rows.
        mono = QFont("Consolas")
        mono.setPointSize(14)
        mono.setStyleHint(QFont.Monospace)

        self._yaw = QLabel("yaw   ---")
        self._pitch = QLabel("pitch ---")
        self._roll = QLabel("roll  ---")
        for w in (self._yaw, self._pitch, self._roll):
            w.setFont(mono)

        sub = QFont("Segoe UI")
        sub.setPointSize(9)
        self._stats = QLabel("waiting for tracker...")
        self._stats.setFont(sub)
        self._stats.setStyleSheet("color: #7a838c;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        layout.addWidget(self._yaw)
        layout.addWidget(self._pitch)
        layout.addWidget(self._roll)
        layout.addSpacing(6)
        layout.addWidget(self._stats)
        layout.addStretch(1)

    @Slot(object, object, object)
    def update_pose(
        self, raw_pose: Pose6DOF, mapped_pose: Pose6DOF, stats: PipelineStats
    ) -> None:
        if stats.detected:
            self._yaw.setText(f"yaw   {mapped_pose.yaw:+7.2f}°")
            self._pitch.setText(f"pitch {mapped_pose.pitch:+7.2f}°")
            self._roll.setText(f"roll  {mapped_pose.roll:+7.2f}°")
            self._stats.setText(
                f"{stats.fps:4.1f} fps  •  {stats.inference_ms:.1f} ms inference"
            )
        else:
            self._yaw.setText("yaw    ---")
            self._pitch.setText("pitch  ---")
            self._roll.setText("roll   ---")
            self._stats.setText(
                f"no face  •  {stats.fps:4.1f} fps  •  {stats.inference_ms:.1f} ms"
            )


__all__ = ["PoseReadout"]
