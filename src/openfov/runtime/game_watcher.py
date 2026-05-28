"""Qt wrapper around `games.GameDetector`.

The base detector runs on its own daemon thread and invokes a plain
Python callback. The UI wants Qt signals on the main thread so it can
update status bars and route output-profile changes through queued
connections. This wrapper provides that.

Lifecycle:
    watcher = GameWatcher(BUILTIN_PROFILES)
    watcher.game_changed.connect(my_slot)   # GameProfile | None
    watcher.start()
    ...
    watcher.stop()
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from openfov.games.base import GameDetector, GameProfile


class GameWatcher(QObject):
    """Qt-signal bridge for `GameDetector`.

    Emits `game_changed(GameProfile | None)` on every state transition.
    The signal payload is the *new* active profile (or `None` when no
    registered game is running)."""

    game_changed = Signal(object)

    def __init__(
        self,
        profiles: list[GameProfile],
        poll_interval_s: float = 1.0,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._detector = GameDetector(
            profiles=profiles,
            on_change=self._on_detector_change,
            poll_interval_s=poll_interval_s,
        )

    # The base detector calls into us from its polling thread. We just
    # emit a Qt signal; the receiver should connect via QueuedConnection
    # so the handler runs on the main thread.
    def _on_detector_change(self, profile: GameProfile | None) -> None:
        self.game_changed.emit(profile)

    @property
    def current(self) -> GameProfile | None:
        return self._detector.current

    def start(self) -> None:
        self._detector.start()

    def stop(self) -> None:
        self._detector.stop()


__all__ = ["GameWatcher"]
