"""System tray icon for OpenFOV.

Right-click menu: Show, Recenter, Pause/Resume, Quit. Closing the main
window hides to tray rather than exiting (per the design spec)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from openfov.ui.resources import app_icon


class Tray(QSystemTrayIcon):
    """Tray icon. Signals out the actions the main app should react to."""

    show_main = Signal()
    recenter = Signal()
    quit_app = Signal()

    def __init__(self, app: QApplication, parent: QObject | None = None) -> None:
        super().__init__(app_icon(), parent)
        self.setToolTip("OpenFOV")

        menu = QMenu()
        self._act_show = QAction("Show OpenFOV", menu)
        self._act_recenter = QAction("Recenter (F9)", menu)
        self._act_quit = QAction("Quit", menu)

        self._act_show.triggered.connect(self.show_main.emit)
        self._act_recenter.triggered.connect(self.recenter.emit)
        self._act_quit.triggered.connect(self.quit_app.emit)

        menu.addAction(self._act_show)
        menu.addSeparator()
        menu.addAction(self._act_recenter)
        menu.addSeparator()
        menu.addAction(self._act_quit)
        self.setContextMenu(menu)

        # Double-click on the tray icon shows the main window.
        self.activated.connect(self._on_activated)

        self._app = app

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.DoubleClick or reason == QSystemTrayIcon.Trigger:
            self.show_main.emit()


__all__ = ["Tray"]
