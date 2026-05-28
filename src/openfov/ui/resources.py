"""Bundled UI resources — icons, stylesheets — with a single resolver.

In a dev checkout, assets live under `resources/`. In a Nuitka standalone
build, they live next to the exe. The `asset_path()` helper finds them
either way, plus respects an `OPENFOV_RESOURCES` env var override for
tests.
"""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_compiled_build() -> bool:
    """True when running from a packaged binary (Nuitka or PyInstaller).

    - PyInstaller sets `sys.frozen` and `sys._MEIPASS`.
    - Nuitka does neither but attaches a `__compiled__` attribute to
      every compiled module. We check our own module's globals so we
      don't depend on import-time globals or sys.modules juggling.

    Either way, when this returns True we should resolve resources
    relative to the .exe's directory, NOT relative to this source
    file's location (which is meaningless inside a packed binary)."""
    if hasattr(sys, "frozen"):
        return True
    if getattr(sys, "_MEIPASS", None):
        return True
    return "__compiled__" in globals()


@lru_cache(maxsize=1)
def resources_root() -> Path:
    """Find the resources directory at runtime."""
    override = os.environ.get("OPENFOV_RESOURCES")
    if override:
        return Path(override).resolve()
    if _is_compiled_build():
        exe_dir = Path(sys.argv[0]).resolve().parent
        candidate = exe_dir / "resources"
        if candidate.exists():
            return candidate
        return exe_dir
    return Path(__file__).resolve().parents[3] / "resources"


def asset_path(*parts: str) -> Path:
    """Resolve a path under the resources tree."""
    return resources_root().joinpath(*parts)


def app_icon():
    """Returns a QIcon. Loads `resources/icons/openfov.ico` if present, otherwise
    falls back to a runtime-painted placeholder so the app always has *something*.
    """
    from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap

    ico = asset_path("icons", "openfov.ico")
    if ico.exists():
        icon = QIcon(str(ico))
        if not icon.isNull():
            return icon
        logger.warning("openfov.ico failed to load as QIcon; falling back")
    else:
        logger.warning("%s missing; using placeholder", ico)

    # Placeholder fallback.
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QBrush(QColor(52, 174, 158)))
        painter.setPen(QColor(20, 80, 70))
        painter.drawEllipse(2, 2, 60, 60)
        painter.setPen(QColor(240, 248, 250))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(20)
        painter.setFont(font)
        painter.drawText(pix.rect(), 0x84, "FOV")  # AlignCenter
    finally:
        painter.end()
    return QIcon(pix)


def load_stylesheet() -> str:
    """Load the app-wide QSS theme. Returns empty string if missing.

    Performs `{ASSET_NAME}` placeholder substitution so QSS `url(...)`
    references can point at runtime-resolved absolute paths (Qt's QSS
    url resolution is relative to the working directory, not the QSS
    file, so we have to feed it absolute paths)."""
    path = asset_path("ui", "openfov.qss")
    if not path.exists():
        return ""
    try:
        qss = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return ""
    # Forward slashes work cross-platform inside QSS url() and avoid
    # backslash-escape headaches on Windows paths.
    qss = qss.replace("{CHECK_PATH}", asset_path("ui", "check.svg").as_posix())
    qss = qss.replace("{ARROW_DOWN_PATH}", asset_path("ui", "arrow_down.svg").as_posix())
    return qss


__all__ = ["app_icon", "asset_path", "load_stylesheet", "resources_root"]
