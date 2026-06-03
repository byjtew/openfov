"""`.env`-backed configuration for the UDP/JSON output.

The UDP output dispatches each pose to a single host:port read from the
``OPENFOV_UDP_TARGET`` environment variable, e.g.::

    OPENFOV_UDP_TARGET=udp://127.0.0.1:4242

The value may be set in the real environment or placed in a ``.env`` file.
``load_dotenv()`` parses a ``.env`` file into ``os.environ`` without
overwriting keys that are already set — so a real environment variable
always wins over the file. The search order for the file (when no explicit
path is given) is:

1. ``$OPENFOV_DOTENV``  (explicit override)
2. ``<cwd>/.env``
3. ``%APPDATA%\\OpenFOV\\.env``  (the per-user app-data dir)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from openfov.persistence.paths import app_data_dir

logger = logging.getLogger(__name__)

#: Where poses go when ``OPENFOV_UDP_TARGET`` is unset or malformed.
DEFAULT_UDP_TARGET: tuple[str, int] = ("127.0.0.1", 4242)

#: The single environment variable that selects the UDP destination.
TARGET_ENV_VAR = "OPENFOV_UDP_TARGET"


def parse_udp_target(value: str) -> tuple[str, int]:
    """Parse ``udp://host:port`` (or a bare ``host:port``) into ``(host, port)``.

    Raises ``ValueError`` if no port can be determined — callers that want a
    fallback should catch it.
    """
    text = value.strip()
    # urlparse needs a scheme to populate .hostname/.port; add one if absent.
    if "://" not in text:
        text = f"udp://{text}"
    parsed = urlparse(text)
    if parsed.hostname is None or parsed.port is None:
        raise ValueError(f"invalid UDP target {value!r} — expected udp://host:port")
    return parsed.hostname, parsed.port


def load_dotenv(path: Path | None = None) -> None:
    """Load ``KEY=VALUE`` pairs from a ``.env`` file into ``os.environ``.

    Existing environment variables are never overwritten. Blank lines and
    ``#`` comments are ignored. A missing file is a silent no-op.
    """
    env_path = path if path is not None else _discover_dotenv()
    if env_path is None or not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read .env file %s: %s", env_path, exc)
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip()


def udp_target() -> tuple[str, int]:
    """Resolve the UDP destination from the environment.

    Returns ``DEFAULT_UDP_TARGET`` (with a warning) if the variable is unset
    or cannot be parsed.
    """
    value = os.environ.get(TARGET_ENV_VAR)
    if not value:
        logger.warning(
            "%s not set — falling back to udp://%s:%d",
            TARGET_ENV_VAR, DEFAULT_UDP_TARGET[0], DEFAULT_UDP_TARGET[1],
        )
        return DEFAULT_UDP_TARGET
    try:
        return parse_udp_target(value)
    except ValueError as exc:
        logger.warning("%s — falling back to default target", exc)
        return DEFAULT_UDP_TARGET


def _discover_dotenv() -> Path | None:
    """Find the first existing ``.env`` per the documented search order."""
    override = os.environ.get("OPENFOV_DOTENV")
    if override:
        return Path(override)
    candidates = [Path.cwd() / ".env", app_data_dir() / ".env"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


__all__ = [
    "DEFAULT_UDP_TARGET",
    "TARGET_ENV_VAR",
    "load_dotenv",
    "parse_udp_target",
    "udp_target",
]
