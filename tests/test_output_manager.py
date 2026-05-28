"""OutputManager lifecycle + GameOutputProfile switching tests.

These deliberately don't exercise the Windows-only paths (registry,
TrackIR.exe child process). Those run in CI on `windows-latest` and via
manual end-to-end validation. What we *can* assert cross-platform:
- start()/stop() are idempotent
- set_game() updates state, but doesn't break on no-op
- write() is silent when not running
"""

from __future__ import annotations

import pytest

from openfov.output.manager import GameOutputProfile, OutputManager
from openfov.tracker.base import Pose6DOF


def test_start_stop_idempotent() -> None:
    mgr = OutputManager()
    mgr.start()
    mgr.start()  # no-op
    assert mgr.is_running
    mgr.stop()
    mgr.stop()  # no-op
    assert not mgr.is_running


def test_context_manager() -> None:
    with OutputManager() as mgr:
        assert mgr.is_running
    assert not mgr.is_running


def test_write_without_start_is_silent() -> None:
    mgr = OutputManager()
    mgr.write(Pose6DOF(yaw=10.0))  # no exception


def test_set_game_updates_profile() -> None:
    profile_a = GameOutputProfile(game_id=1001)
    profile_b = GameOutputProfile(game_id=2002, encryption_key=b"\x01\x02\x03\x04\x05\x06\x07\x08")
    with OutputManager() as mgr:
        mgr.set_game(profile_a)
        assert mgr._current_profile == profile_a
        mgr.set_game(profile_b)
        assert mgr._current_profile == profile_b


def test_set_game_same_profile_skips() -> None:
    """Setting the same profile twice should not re-write the writer fields."""
    profile = GameOutputProfile(game_id=1001)
    with OutputManager() as mgr:
        mgr.set_game(profile)
        mgr.set_game(profile)  # no-op path
        assert mgr._current_profile == profile


def test_invalid_encryption_key_rejected() -> None:
    """Encryption keys must be exactly 8 bytes."""
    profile = GameOutputProfile(game_id=1001, encryption_key=b"\x01\x02\x03")
    with OutputManager() as mgr, pytest.raises(ValueError):
        mgr.set_game(profile)
