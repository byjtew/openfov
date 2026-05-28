"""NPClient bootstrap helpers — registry read/write are exercised on
Windows only; everywhere else they no-op cleanly.

These tests deliberately don't touch the *real* HKCU key — they only
verify the path-resolution + cross-platform safety properties. End-to-end
registry validation belongs in an integration test on Windows CI."""

from __future__ import annotations

import sys
from pathlib import Path

from openfov.output import npclient_bootstrap as bootstrap


def test_bundled_bin_dir_respects_env_override(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "custom_bin"
    target.mkdir()
    monkeypatch.setenv("OPENFOV_BIN_DIR", str(target))
    resolved = bootstrap.bundled_bin_dir()
    assert resolved == target.resolve()


def test_bundled_bin_dir_default_under_repo() -> None:
    """In a dev checkout, the default points at resources/bin under repo root."""
    # Make sure no override is active.
    import os

    os.environ.pop("OPENFOV_BIN_DIR", None)
    p = bootstrap.bundled_bin_dir()
    assert p.name == "bin"
    assert p.parent.name == "resources"


def test_read_registry_no_op_off_windows() -> None:
    """On Linux/macOS CI, read_registry_path returns None without raising."""
    if sys.platform == "win32":
        # We can't safely assert on Windows without potentially clobbering
        # real state. Just verify the function call doesn't raise.
        try:
            bootstrap.read_registry_path()
        except Exception as exc:
            raise AssertionError(f"read_registry_path raised on Windows: {exc}") from exc
    else:
        assert bootstrap.read_registry_path() is None


def test_remove_registry_no_op_off_windows() -> None:
    if sys.platform != "win32":
        assert bootstrap.remove_registry_path() is False


def test_write_registry_no_op_off_windows() -> None:
    """On non-Windows the write should silently no-op (logged, not raised)."""
    if sys.platform != "win32":
        bootstrap.write_registry_path("/tmp/nowhere")  # should not raise
