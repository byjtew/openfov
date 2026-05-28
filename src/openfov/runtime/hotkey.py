"""Global system-wide hotkeys.

pynput's listener runs on its own thread; we marshal callbacks back to
the Qt main thread via signals (QueuedConnection — set up by the UI).

Default bindings come from `AppConfig`. Empty string = unbound.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class GlobalHotkey(QObject):
    """Single-hotkey listener. Multi-hotkey wraps multiple of these.

    The `activated` signal fires on the listener thread; connect with
    `Qt.QueuedConnection` to ensure handlers run on the main thread."""

    activated = Signal()

    def __init__(self, key: str = "<f9>", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._listener: object | None = None

    @property
    def binding(self) -> str:
        return self._key

    def set_binding(self, key: str) -> None:
        """Change the hotkey. Restarts the listener if running."""
        was_running = self._listener is not None
        if was_running:
            self.stop()
        self._key = key
        if was_running and key:
            self.start()

    def start(self) -> None:
        if self._listener is not None or not self._key:
            return
        try:
            from pynput import keyboard
        except ImportError as exc:
            logger.warning("pynput not available, hotkeys disabled: %s", exc)
            return

        try:
            hk = keyboard.GlobalHotKeys({self._key: self._on_hit})
            hk.start()
            self._listener = hk
            logger.debug("Global hotkey %r registered", self._key)
        except Exception as exc:  # noqa: BLE001
            # Invalid key spec, OS denial, etc. Don't crash the app.
            logger.warning("Failed to register hotkey %r: %s", self._key, exc)
            self._listener = None

    def stop(self) -> None:
        if self._listener is None:
            return
        try:
            self._listener.stop()  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.debug("Hotkey stop raised (benign): %s", exc)
        self._listener = None

    def _on_hit(self) -> None:
        self.activated.emit()


__all__ = ["GlobalHotkey"]
