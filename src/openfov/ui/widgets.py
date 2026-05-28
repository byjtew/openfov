"""Small shared UI helpers.

`reset_button` is the consistent inline "reset to default" affordance
that appears next to every adjustable parameter. Rendered as a quiet
text link rather than an icon button so it never competes with the
primary control for attention.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton


def reset_button(tooltip: str, on_click: Callable[[], None]) -> QPushButton:
    """A flat "reset" text link styled by the app QSS via the dynamic
    `reset` property. Wires `on_click` directly to `clicked`."""
    btn = QPushButton("reset")
    btn.setProperty("reset", True)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setFlat(True)
    btn.clicked.connect(lambda _checked=False: on_click())
    # Re-evaluate stylesheet so the [reset="true"] selector applies.
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    return btn


__all__ = ["reset_button"]
