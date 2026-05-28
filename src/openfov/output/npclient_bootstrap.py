"""NPClient registry bootstrap.

Games look for NPClient.dll via the Windows registry key

    HKEY_CURRENT_USER\\Software\\NaturalPoint\\NATURALPOINT\\NPClient Location

The value should be a path to a *directory* — the game appends `NPClient.dll`
or `NPClient64.dll` and loads the result. We point that key at OpenFOV's
own `bin/` directory so the bundled stub gets loaded.

Per-user (HKCU) — never HKLM — so no UAC, and the install is fully scoped
to whoever runs OpenFOV.

On non-Windows the module exposes the same API but every function becomes
a no-op + log message, so CI on Linux/macOS can import freely.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

REGISTRY_PATH = r"Software\NaturalPoint\NATURALPOINT"
REGISTRY_VALUE = "NPClient Location"


def bundled_bin_dir() -> Path:
    """Resolve the directory that contains NPClient.dll / NPClient64.dll /
    TrackIR.exe at runtime.

    - In a Nuitka standalone build, the binaries live alongside our exe.
    - In a development checkout, they live under `resources/bin/`.
    - The `OPENFOV_BIN_DIR` env var overrides everything (useful for tests).
    """
    import os

    override = os.environ.get("OPENFOV_BIN_DIR")
    if override:
        return Path(override).resolve()

    # Walk up from this file to find the project root, then check the dev
    # path; if the bundled-resources path next to the exe exists, prefer
    # that.
    if hasattr(sys, "frozen") or getattr(sys, "_MEIPASS", None):
        # Nuitka / PyInstaller distribution.
        exe_dir = Path(sys.argv[0]).resolve().parent
        candidate = exe_dir / "resources" / "bin"
        if candidate.exists():
            return candidate
        return exe_dir / "bin"

    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "resources" / "bin"


# ---------------------------------------------------------------------------
# Win32 plumbing (registry I/O via winreg). winreg is part of the stdlib on
# Windows; we wrap each call so non-Windows OSes can import this module
# without ImportError.
# ---------------------------------------------------------------------------


def _is_windows() -> bool:
    return sys.platform == "win32"


def read_registry_path() -> str | None:
    """Return the currently-registered NPClient location, or None if unset."""
    if not _is_windows():
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_READ) as k:
            value, _ = winreg.QueryValueEx(k, REGISTRY_VALUE)
            return str(value) if value else None
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("Could not read NPClient registry key: %s", exc)
        return None


def write_registry_path(path: Path | str) -> None:
    """Point the registry at the given directory. Creates the key tree if
    missing. Idempotent — safe to call on every app launch."""
    if not _is_windows():
        logger.debug("write_registry_path no-op on non-Windows")
        return
    import winreg

    path_str = str(Path(path).resolve())
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH) as k:
            winreg.SetValueEx(k, REGISTRY_VALUE, 0, winreg.REG_SZ, path_str)
        logger.info("NPClient registry set to %s", path_str)
    except OSError as exc:
        logger.error("Failed to write NPClient registry key: %s", exc)
        raise


def remove_registry_path() -> bool:
    """Delete just our `NPClient Location` value (leaves other NaturalPoint
    state intact). Returns True if a value was removed, False if it wasn't
    there to begin with. Called by the uninstaller."""
    if not _is_windows():
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.DeleteValue(k, REGISTRY_VALUE)
        logger.info("NPClient registry value removed")
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("Could not remove NPClient registry value: %s", exc)
        return False


# ---------------------------------------------------------------------------
# High-level orchestration
# ---------------------------------------------------------------------------


def ensure_registered() -> Path:
    """Ensure the NPClient registry key points at our bundled `bin/` dir.

    Returns the path that's now registered. Raises FileNotFoundError if the
    binaries aren't found at the expected location (which means the build
    didn't include them — useful test signal).
    """
    bin_dir = bundled_bin_dir()
    npclient = bin_dir / "NPClient.dll"
    npclient64 = bin_dir / "NPClient64.dll"

    # In development we may be running before build.ps1 has produced the
    # DLLs. Warn but don't fail — useful for UI dev where the game isn't in
    # play anyway. The user-facing message stays generic; the dev-only
    # build instruction is logged at DEBUG.
    if not npclient.exists() and not npclient64.exists():
        if _is_windows():
            logger.warning(
                "NPClient binaries not found in %s — OpenFOV install may be "
                "incomplete. Please reinstall.",
                bin_dir,
            )
            logger.debug(
                "Dev-mode hint: run npclient-vendor/build.ps1 to populate "
                "resources/bin/."
            )
    write_registry_path(bin_dir)
    return bin_dir


__all__ = [
    "REGISTRY_PATH",
    "REGISTRY_VALUE",
    "bundled_bin_dir",
    "ensure_registered",
    "read_registry_path",
    "remove_registry_path",
    "write_registry_path",
]
