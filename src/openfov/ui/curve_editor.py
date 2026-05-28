"""Interactive Bezier curve editor.

Drag the green control points to shape per-axis response.

Interaction model:
- Left-click on an anchor and drag to move it.
- Left-click on empty space inserts a new anchor at that location.
- Right-click on an anchor deletes it (endpoints can't be deleted).
- Right-click on empty space does nothing.

Layout (input domain on X, output range on Y, both shown in degrees):

```
        +180 ┤
             │
             │
            0┼──────●──────         <- center anchor
             │
             │
        -180 ┴────────────
            -90    0    +90
```

Live indicator: a small dot tracks `(current_input, current_output)` as
the pipeline emits pose updates, so users can immediately *see* what
their curve does to their motion.

Editing rules:
- Endpoints' X coords are pinned to ±domain; you can drag their Y freely.
- Intermediate anchors can move freely in X within (left_neighbor, right_neighbor)
  and arbitrarily in Y within ±output_clamp.
- Min anchors: 2 (endpoints). Max: 6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from openfov.mapping.curve import CubicBezierCurve, CurvePoint
from openfov.mapping.presets import (
    aggressive_edges,
    deadzone,
    linear,
    soft_center,
)


# Preset list shared with the AxisPanel's dropdown — each entry is
# (label_for_user, factory_taking_domain). The dropdown applies the
# factory at the editor's current domain.
PRESETS: tuple[tuple[str, "callable"], ...] = (
    ("Linear (default)", linear),
    ("Soft center", soft_center),
    ("Aggressive edges", aggressive_edges),
    ("Deadzone (±3°)", lambda d=90.0: deadzone(d, 3.0)),
)


_DOMAIN = 90.0      # X axis: ±90° input
_RANGE = 180.0      # Y axis: ±180° output
_HANDLE_RADIUS = 6
_HIT_RADIUS = 12    # generous hit zone for grab-and-drag


@dataclass
class _Layout:
    """Plot rect in widget coords + axis scale factors."""
    plot: QRectF
    x_scale: float       # px per input unit
    y_scale: float       # px per output unit
    zero_x: float        # widget-x where input=0 lives
    zero_y: float        # widget-y where output=0 lives

    def value_to_point(self, x: float, y: float) -> QPointF:
        return QPointF(self.zero_x + x * self.x_scale,
                       self.zero_y - y * self.y_scale)

    def point_to_value(self, p: QPointF) -> tuple[float, float]:
        x = (p.x() - self.zero_x) / self.x_scale
        y = (self.zero_y - p.y()) / self.y_scale
        return x, y


class CurveEditor(QWidget):
    """Editable cubic Bezier response curve. Emits `changed(CubicBezierCurve)`
    whenever the user drags an anchor or picks a preset.

    Set `live_input` from the pipeline thread to show where the user
    currently *is* on the curve."""

    changed = Signal(object)  # CubicBezierCurve

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.setMaximumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #0d1015;")

        self._curve = linear(domain=_DOMAIN)
        self._drag_index: int | None = None
        self._hover_index: int | None = None
        self._live_input: float | None = None
        self._live_output: float | None = None

        # Sample cache: re-built only when the curve changes (set_curve,
        # _update_point, _insert_point, _remove_point, _set_preset).
        # paintEvent reuses this — without the cache, each paint sampled
        # 181 scalar evaluations, dominating GUI cost.
        self._sample_xs: np.ndarray = np.empty(0)
        self._sample_ys: np.ndarray = np.empty(0)
        self._rebuild_samples()

    _N_SAMPLES = 180

    def _rebuild_samples(self) -> None:
        """Resample the curve into cached x/y arrays. Cheap: one
        vectorized numpy call regardless of anchor count."""
        xs = np.linspace(-_DOMAIN, _DOMAIN, self._N_SAMPLES + 1)
        ys = self._curve.evaluate(xs)
        self._sample_xs = xs
        self._sample_ys = np.asarray(ys, dtype=np.float64)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_curve(self, curve: CubicBezierCurve) -> None:
        """Replace the curve without emitting `changed`. Used when a profile
        is loaded."""
        self._curve = curve
        self._rebuild_samples()
        self.update()

    def curve(self) -> CubicBezierCurve:
        return self._curve

    @Slot(float, float)
    def set_live(self, input_value: float, output_value: float) -> None:
        """Update the live indicator dot. Called every pose-ready emission."""
        self._live_input = input_value
        self._live_output = output_value
        self.update()

    def clear_live(self) -> None:
        self._live_input = None
        self._live_output = None
        self.update()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _layout(self) -> _Layout:
        margin = 10
        plot = QRectF(margin, margin, self.width() - 2 * margin,
                      self.height() - 2 * margin)
        x_scale = plot.width() / (2 * _DOMAIN)
        y_scale = plot.height() / (2 * _RANGE)
        zero_x = plot.center().x()
        zero_y = plot.center().y()
        return _Layout(plot=plot, x_scale=x_scale, y_scale=y_scale,
                       zero_x=zero_x, zero_y=zero_y)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if not self.isEnabled():
            # Mute everything (grid, curve, anchors, live dot) so the
            # editor reads as "off" alongside the rest of a disabled
            # axis panel.
            painter.setOpacity(0.35)
        layout = self._layout()

        # Frame.
        painter.setPen(QPen(QColor(44, 51, 59), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(layout.plot)

        # Grid: zero lines + 45° helpers.
        painter.setPen(QPen(QColor(30, 36, 42), 1, Qt.DashLine))
        painter.drawLine(layout.plot.left(), layout.zero_y,
                         layout.plot.right(), layout.zero_y)
        painter.drawLine(layout.zero_x, layout.plot.top(),
                         layout.zero_x, layout.plot.bottom())
        # ±45° guides on the input axis.
        for x in (-_DOMAIN / 2, _DOMAIN / 2):
            px = layout.zero_x + x * layout.x_scale
            painter.drawLine(QPointF(px, layout.plot.top()),
                             QPointF(px, layout.plot.bottom()))

        # The curve itself — sampled once on curve change, cached.
        path = QPolygonF(
            [
                layout.value_to_point(float(x), float(y))
                for x, y in zip(self._sample_xs, self._sample_ys)
            ]
        )
        pen = QPen(QColor(82, 196, 174), 2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(path)

        # Live indicator (input -> output) — small white dot + dropdown line.
        if self._live_input is not None and self._live_output is not None:
            p = layout.value_to_point(self._live_input, self._live_output)
            painter.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.DotLine))
            painter.drawLine(QPointF(p.x(), layout.zero_y), p)
            painter.drawLine(QPointF(layout.zero_x, p.y()), p)
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawEllipse(p, 3.5, 3.5)

        # Control points.
        for i, cp in enumerate(self._curve.points):
            pt = layout.value_to_point(cp.x, cp.y)
            painter.setBrush(
                QBrush(QColor(200, 248, 220) if i == self._hover_index else QColor(82, 196, 174))
            )
            painter.setPen(QPen(QColor(30, 100, 90), 1))
            painter.drawEllipse(pt, _HANDLE_RADIUS, _HANDLE_RADIUS)

    # ------------------------------------------------------------------
    # Mouse + context menu
    # ------------------------------------------------------------------

    def _index_under(self, pos: QPointF) -> int | None:
        layout = self._layout()
        for i, cp in enumerate(self._curve.points):
            handle = layout.value_to_point(cp.x, cp.y)
            if (pos - handle).manhattanLength() <= _HIT_RADIUS:
                return i
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: D401
        pos = event.position()
        idx = self._index_under(pos)
        if event.button() == Qt.LeftButton:
            if idx is not None:
                # Start dragging an existing anchor.
                self._drag_index = idx
                return
            # Empty space → insert a new anchor at the click location.
            if len(self._curve.points) < self.MAX_ANCHORS:
                layout = self._layout()
                x, y = layout.point_to_value(pos)
                self._insert_point(x, y)
                # Immediately let the user drag the new point. The
                # insert helper places it sorted by x; find it again.
                new_idx = self._index_under(pos)
                self._drag_index = new_idx
        elif event.button() == Qt.RightButton:
            # Right-click on an interior anchor deletes it. Endpoints
            # can't be deleted; right-click on empty space does nothing.
            if idx is not None and 0 < idx < len(self._curve.points) - 1:
                self._remove_point(idx)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: D401
        if self._drag_index is None:
            self._hover_index = self._index_under(event.position())
            self.update()
            return
        layout = self._layout()
        x, y = layout.point_to_value(event.position())
        self._update_point(self._drag_index, x, y)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: D401, ARG002
        self._drag_index = None

    # ------------------------------------------------------------------
    # Curve mutation
    # ------------------------------------------------------------------

    def _update_point(self, index: int, x: float, y: float) -> None:
        points = list(self._curve.points)
        n = len(points)
        # Constrain X: endpoints pinned, interior anchors stay between
        # neighbors with a small minimum gap so the curve remains valid.
        if index == 0:
            x = points[0].x
        elif index == n - 1:
            x = points[-1].x
        else:
            min_x = points[index - 1].x + 1.0
            max_x = points[index + 1].x - 1.0
            x = max(min_x, min(max_x, x))
        # Constrain Y.
        y = max(-_RANGE, min(_RANGE, y))
        points[index] = replace(points[index], x=x, y=y)
        self._curve = CubicBezierCurve(points=points)
        self._rebuild_samples()
        self.update()
        self.changed.emit(self._curve)

    MAX_ANCHORS = 6

    def _insert_point(self, x: float, y: float) -> None:
        points = list(self._curve.points)
        if len(points) >= self.MAX_ANCHORS:
            return
        # Find the insertion index — first existing point with x > target.
        insert_at = next((i for i, cp in enumerate(points) if cp.x > x), len(points))
        if insert_at == 0:
            insert_at = 1  # never before the left endpoint
        elif insert_at == len(points):
            insert_at = len(points) - 1  # never after the right endpoint
        new_point = CurvePoint(
            x=max(points[insert_at - 1].x + 1.0, min(points[insert_at].x - 1.0, x)),
            y=max(-_RANGE, min(_RANGE, y)),
        )
        points.insert(insert_at, new_point)
        try:
            self._curve = CubicBezierCurve(points=points)
        except ValueError:
            return
        self._rebuild_samples()
        self.update()
        self.changed.emit(self._curve)

    def _remove_point(self, index: int) -> None:
        if index <= 0 or index >= len(self._curve.points) - 1:
            return
        points = [p for i, p in enumerate(self._curve.points) if i != index]
        self._curve = CubicBezierCurve(points=points)
        self._rebuild_samples()
        self.update()
        self.changed.emit(self._curve)

    def apply_preset(self, preset_curve: CubicBezierCurve) -> None:
        """Public preset-application path used by the axis panel's
        dropdown. Replaces the curve and emits `changed`."""
        self._set_preset(preset_curve)

    def _set_preset(self, preset_curve: CubicBezierCurve) -> None:
        self._curve = preset_curve
        self._rebuild_samples()
        self.update()
        self.changed.emit(self._curve)


__all__ = ["CurveEditor", "PRESETS"]
