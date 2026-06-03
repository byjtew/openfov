"""UDP/JSON pose writer.

Dispatches each 6DOF pose as a JSON datagram over UDP, replacing the
FreeTrack shared-memory path. The destination host:port is read from the
``OPENFOV_UDP_TARGET`` environment variable (see ``persistence.env``).

Wire format — one datagram per pose, ``{"rotation": [heading, pitch, roll]}``
with angles in degrees in OpenFOV's native convention (``+yaw`` = look left,
``+pitch`` = up, ``+roll`` = left ear down). Values default to ``0.0`` when a
pose field is absent.

Sending is fire-and-forget: UDP gives no delivery guarantee, and a transient
socket error must never stall or kill the tracker pipeline, so ``write()``
swallows send failures (counting them) rather than raising.

This writer is cross-platform — unlike FreeTrack it has no Windows-only
plumbing, so the headless pipeline and CI exercise the real send path.
"""

from __future__ import annotations

import json
import logging
import socket

from openfov.persistence.env import udp_target
from openfov.tracker.base import Pose6DOF

logger = logging.getLogger(__name__)


class UdpJsonWriter:
    """Sends 6DOF poses as JSON datagrams over UDP.

    Lifecycle mirrors ``FreeTrackWriter`` so it drops into ``OutputManager``
    without changing callers::

        w = UdpJsonWriter()
        w.open()
        w.write(pose)        # call as often as you have new data
        w.close()            # idempotent

    Telemetry: ``writes_committed`` / ``writes_dropped`` let the pipeline
    surface the actual send rate, same as the FreeTrack path.
    """

    def __init__(self) -> None:
        self._socket: socket.socket | None = None
        self._target: tuple[str, int] | None = None
        self.writes_committed = 0
        self.writes_dropped = 0

    @property
    def is_open(self) -> bool:
        return self._socket is not None

    # -- lifecycle ------------------------------------------------------

    def open(self) -> None:
        """Resolve the target and create the UDP socket. Idempotent."""
        if self._socket is not None:
            return
        self._target = udp_target()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logger.info("UDP/JSON output -> %s:%d", self._target[0], self._target[1])

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self) -> UdpJsonWriter:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- writes ---------------------------------------------------------

    def write(self, pose: Pose6DOF) -> None:
        """Send one pose as ``{"rotation": [yaw, pitch, roll]}``.

        Silent no-op before ``open()``. Send failures are counted in
        ``writes_dropped`` and never propagate."""
        if self._socket is None or self._target is None:
            return
        payload = json.dumps({"rotation": [pose.yaw, pose.pitch, pose.roll]}).encode("utf-8")
        try:
            self._socket.sendto(payload, self._target)
            self.writes_committed += 1
        except OSError as exc:
            # A transient socket error (e.g. ICMP port-unreachable surfacing
            # on a connected datagram socket) must not stall inference.
            self.writes_dropped += 1
            logger.debug("UDP send failed: %s", exc)

    # -- FreeTrack-compat no-ops ---------------------------------------
    # OutputManager and game profiles still call these; they carry no
    # meaning for a UDP/JSON sink, but the methods must exist so callers
    # stay untouched.

    def set_game_id(self, game_id: int) -> None:
        """No-op — game IDs are a FreeTrack/NPClient concept."""

    def set_encryption_key(self, key: bytes) -> None:
        """No-op, but preserve the 8-byte invariant so GameOutputProfile
        validation stays meaningful across the codebase."""
        if len(key) != 8:
            raise ValueError("encryption key must be exactly 8 bytes")

    def set_camera_dimensions(self, width: int, height: int) -> None:
        """No-op — camera dimensions were a shared-memory diagnostic field."""


__all__ = ["UdpJsonWriter"]
