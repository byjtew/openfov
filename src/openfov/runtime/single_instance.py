"""Single-instance lock.

Two simultaneous OpenFOV instances fight over the same camera, the
`FT_SharedMem` mapping, the NPClient registry key, and the bundled
TrackIR.exe child process (managed via a Windows Job Object). The
result is one of the instances dying mysteriously when the user
fiddles with controls in the other.

We prevent this by holding an exclusive lock on a file under
`%LOCALAPPDATA%\\OpenFOV\\openfov.lock` for the lifetime of the process.
Second launches see the lock as already held and exit early — the
caller can decide whether to surface a "already running" dialog.

Implementation notes:
- Windows: use `msvcr`'s `LK_NBLCK` (non-blocking lock) on a region of
  the file. The OS releases the lock automatically when the process
  dies — even if it crashes uncleanly — so no orphan locks survive a
  segfault.
- Non-Windows: skip; tests / dev run on Linux/mac don't need it.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _lock_path() -> Path:
    """Lock file lives under LocalAppData (not roaming) — it's a per-PC
    lock, not per-user-roaming-profile."""
    base_env = os.environ.get("OPENFOV_LOCK_DIR")
    if base_env:
        base = Path(base_env)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        base = base / "OpenFOV"
    else:
        base = Path.home() / ".cache" / "OpenFOV"
    base.mkdir(parents=True, exist_ok=True)
    return base / "openfov.lock"


class SingleInstanceLock:
    """File-lock-based single-instance gate.

    Usage:
        lock = SingleInstanceLock()
        if not lock.acquire():
            # Another instance is running; bail.
            ...
        # ... app runs ...
        lock.release()        # or rely on process exit
    """

    def __init__(self) -> None:
        self._path = _lock_path()
        self._fd: int | None = None
        self._acquired = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def acquired(self) -> bool:
        return self._acquired

    def acquire(self) -> bool:
        """Try to take the lock. Returns True on success, False if
        another instance already holds it.

        On non-Windows this is a no-op and always returns True (we
        don't need to gate dev / test runs)."""
        if sys.platform != "win32":
            self._acquired = True
            return True
        try:
            # O_RDWR | O_CREAT — opens-or-creates without truncating.
            self._fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as exc:
            logger.warning("Could not open lock file %s: %s", self._path, exc)
            return False

        import msvcrt

        try:
            # LK_NBLCK: try lock, fail if already locked. Lock region
            # size doesn't matter — any non-zero region works as a
            # process-scoped lock.
            msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            # Another instance is holding it.
            os.close(self._fd)
            self._fd = None
            return False

        # Stamp the file with our PID so a diagnostic user can see
        # which process is holding it.
        with contextlib.suppress(OSError):
            os.write(self._fd, f"{os.getpid()}".encode())
        self._acquired = True
        return True

    def release(self) -> None:
        """Best-effort lock release. Called on clean shutdown; Windows
        also auto-releases on process exit (clean or crash)."""
        if not self._acquired:
            return
        if sys.platform == "win32" and self._fd is not None:
            import msvcrt

            try:
                # Seek back to the lock region before unlocking.
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            with contextlib.suppress(OSError):
                os.close(self._fd)
            self._fd = None
        self._acquired = False


__all__ = ["SingleInstanceLock"]
