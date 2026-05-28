"""Autostart helper tests — cross-platform safety + dev-run handling."""

from __future__ import annotations

import sys

from openfov.runtime import autostart


def test_is_enabled_no_op_off_windows() -> None:
    if sys.platform != "win32":
        assert autostart.is_enabled() is False


def test_set_enabled_returns_false_in_dev_run() -> None:
    """Without a frozen exe and without a supplied path, set_enabled(True)
    must refuse and return False — not crash, not write garbage."""
    if sys.platform != "win32":
        # Off-Windows: always False, regardless of args.
        assert autostart.set_enabled(True) is False
        return
    # On Windows, dev run: no frozen exe, no supplied path -> refuse.
    # (We can't test the success path without permanently modifying the
    # user's registry; covered manually on the integration sweep.)
    assert autostart.set_enabled(True) is False


def test_resolve_exe_path_none_in_dev_run() -> None:
    """Dev runs return None so the caller knows to disable the UI."""
    assert autostart.resolve_exe_path() is None
