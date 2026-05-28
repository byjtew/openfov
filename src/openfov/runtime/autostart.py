"""Windows 'Start with Windows' registry helpers.

Writes a single per-user `Run` value pointing at the OpenFOV exe. No HKLM
involvement (which would require UAC); no Task Scheduler entries (which
would survive uninstall).

Lifecycle:
    autostart.set_enabled(True, exe_path="...\\OpenFOV.exe")
    autostart.is_enabled() -> bool
    autostart.set_enabled(False)            # removes the value

When run inside a Nuitka standalone build, the exe path is resolved
automatically. When run from a dev checkout, the caller must supply
`exe_path` (since the dev path is meaningless to a user).

Cross-platform: every public function no-ops cleanly on non-Windows.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_VALUE = "OpenFOV"


def _is_windows() -> bool:
    return sys.platform == "win32"


def _frozen_exe_path() -> Path | None:
    """Resolve the running OpenFOV.exe path when we're inside a Nuitka
    or PyInstaller bundle. Returns None for dev runs (the caller can
    fall back to whatever is appropriate)."""
    if hasattr(sys, "frozen") or getattr(sys, "_MEIPASS", None):
        return Path(sys.argv[0]).resolve()
    return None


def resolve_exe_path() -> Path | None:
    """Best-effort discovery of the OpenFOV.exe to register.

    - Frozen bundle: use the actual exe path.
    - Dev checkout: returns None (caller should disable the feature in UI
      with an informative tooltip, or accept None to fall back to the
      python interpreter — which we explicitly don't do here).
    """
    return _frozen_exe_path()


def is_enabled() -> bool:
    """Read the registry and return True if our autostart value exists."""
    if not _is_windows():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ) as k:
            value, _ = winreg.QueryValueEx(k, _REG_VALUE)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("Could not read autostart key: %s", exc)
        return False


def set_enabled(enabled: bool, exe_path: Path | str | None = None) -> bool:
    """Enable or disable autostart.

    Returns True on success. When `enabled=True`, writes the registry value
    to point at `exe_path` (or auto-resolves from a frozen bundle if not
    supplied). When `enabled=False`, deletes the value.

    No-op + False on non-Windows.
    No-op + False when enabling without a usable exe path (dev runs).
    """
    if not _is_windows():
        return False
    import winreg

    if enabled:
        target = Path(exe_path).resolve() if exe_path else resolve_exe_path()
        if target is None or not target.exists():
            logger.warning(
                "Autostart enable requested but no usable exe path "
                "(dev run? bundle missing?); skipping."
            )
            return False
        # Quote so paths with spaces work when CreateProcess parses Run.
        cmd = f'"{target}"'
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_KEY) as k:
                winreg.SetValueEx(k, _REG_VALUE, 0, winreg.REG_SZ, cmd)
        except OSError as exc:
            logger.error("Failed to write autostart key: %s", exc)
            return False
        logger.info("Autostart enabled -> %s", cmd)
        return True

    # Disable.
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.DeleteValue(k, _REG_VALUE)
        logger.info("Autostart disabled")
        return True
    except FileNotFoundError:
        return True   # not present = already disabled
    except OSError as exc:
        logger.warning("Failed to delete autostart value: %s", exc)
        return False


__all__ = ["is_enabled", "resolve_exe_path", "set_enabled"]
