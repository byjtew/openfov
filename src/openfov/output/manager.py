"""OutputManager — orchestrates the freestanding output stack.

Composes:
- UdpJsonWriter     (dispatches each pose as JSON over UDP)

Plus per-game settings carried over from the FreeTrack era: GameID + 8-byte
XOR encryption key. These are no-ops for the UDP sink but `set_game(profile)`
still validates them so `GameOutputProfile` stays meaningful.

Lifecycle is two-phase:
    mgr = OutputManager()
    mgr.start()                       # opens the UDP socket
    mgr.set_game(iracing_profile)     # (no-op for UDP)
    mgr.write(pose)                   # call every tracker frame
    mgr.stop()                        # tears down in reverse order

Idempotent — start() and stop() can be called repeatedly without harm."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from openfov.output.udp_json import UdpJsonWriter
from openfov.tracker.base import Pose6DOF

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameOutputProfile:
    """Per-game wire-format tuning for the output stack.

    `game_id` is the value games pass to NP_RegisterProgramProfileID; our
    NPClient writes it back into shared memory's `GameID` field. The
    `encryption_key` is what NPClient XORs onto the returned pose for
    games that expect TrackIR-style encryption (most modern titles don't —
    leave it zero).
    """

    game_id: int = 0
    encryption_key: bytes = b"\x00" * 8


class OutputManager:
    """Owner of the full output stack."""

    def __init__(self) -> None:
        self._writer = UdpJsonWriter()
        self._running = False
        self._current_profile: GameOutputProfile | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    # -- lifecycle ------------------------------------------------------

    def start(self, *, force_register: bool = False) -> None:
        """Bring the output stack up. Safe to call multiple times.

        `force_register` is accepted for backward compatibility with callers
        from the FreeTrack era; it has no effect on the UDP sink."""
        if self._running:
            return
        self._writer.open()
        self._running = True
        logger.info("OutputManager started")

    def stop(self) -> None:
        if not self._running:
            return
        self._writer.close()
        self._running = False
        logger.info("OutputManager stopped")

    def __enter__(self) -> OutputManager:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # -- per-game settings ---------------------------------------------

    def set_game(self, profile: GameOutputProfile) -> None:
        """Switch GameID + XOR encryption key. These are no-ops for the UDP
        sink, but the encryption key is still length-validated so an invalid
        GameOutputProfile is caught here rather than passed silently."""
        if self._current_profile == profile:
            return
        self._writer.set_game_id(profile.game_id)
        self._writer.set_encryption_key(profile.encryption_key)
        self._current_profile = profile
        logger.info("Output profile -> game_id=%d", profile.game_id)

    def set_camera_dimensions(self, width: int, height: int) -> None:
        """Update the CamWidth/CamHeight fields — some games use these as
        diagnostic info or for native-resolution display alongside pose."""
        self._writer.set_camera_dimensions(width, height)

    # -- per-frame ------------------------------------------------------

    def write(self, pose: Pose6DOF) -> None:
        """Push one pose. If the manager isn't running yet, drops silently
        — caller doesn't need a `if running:` guard around it."""
        if not self._running:
            return
        self._writer.write(pose)


__all__ = ["GameOutputProfile", "OutputManager"]
