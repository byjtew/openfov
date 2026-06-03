"""Tests for the UDP/JSON pose writer (output/udp_json.py).

The writer sends one JSON datagram per pose to the configured target. We
bind a real loopback UDP socket and assert on the bytes received — no mocks.
"""

from __future__ import annotations

import json
import socket

import pytest

from openfov.output.udp_json import UdpJsonWriter
from openfov.tracker.base import Pose6DOF


def _bind_receiver() -> socket.socket:
    """A loopback UDP socket on an ephemeral port, ready to recvfrom()."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    return sock


def test_write_sends_rotation_json(monkeypatch) -> None:
    receiver = _bind_receiver()
    try:
        port = receiver.getsockname()[1]
        monkeypatch.setenv("OPENFOV_UDP_TARGET", f"udp://127.0.0.1:{port}")
        with UdpJsonWriter() as writer:
            writer.write(Pose6DOF(yaw=1.5, pitch=-2.0, roll=3.25, x=10.0, y=20.0, z=30.0))
            data, _ = receiver.recvfrom(4096)
        payload = json.loads(data.decode("utf-8"))
        # rotation only, OpenFOV native convention, no negation.
        assert payload == {"rotation": [1.5, -2.0, 3.25]}
        assert writer.writes_committed == 1
        assert writer.writes_dropped == 0
    finally:
        receiver.close()


def test_write_before_open_is_silent() -> None:
    writer = UdpJsonWriter()
    writer.write(Pose6DOF(yaw=10.0))  # no socket yet — must not raise
    assert writer.writes_committed == 0


def test_is_open_reflects_lifecycle(monkeypatch) -> None:
    monkeypatch.setenv("OPENFOV_UDP_TARGET", "udp://127.0.0.1:4242")
    writer = UdpJsonWriter()
    assert not writer.is_open
    writer.open()
    assert writer.is_open
    writer.close()
    assert not writer.is_open


def test_compat_noops_do_not_raise(monkeypatch) -> None:
    """OutputManager calls these; they're meaningless for UDP but must exist."""
    monkeypatch.setenv("OPENFOV_UDP_TARGET", "udp://127.0.0.1:4242")
    with UdpJsonWriter() as writer:
        writer.set_game_id(1001)
        writer.set_camera_dimensions(1280, 720)
        writer.set_encryption_key(b"\x00" * 8)


def test_encryption_key_length_still_validated(monkeypatch) -> None:
    """Preserve the 8-byte invariant so GameOutputProfile stays meaningful."""
    monkeypatch.setenv("OPENFOV_UDP_TARGET", "udp://127.0.0.1:4242")
    with UdpJsonWriter() as writer, pytest.raises(ValueError):
        writer.set_encryption_key(b"\x01\x02\x03")
