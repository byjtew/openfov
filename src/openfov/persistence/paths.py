"""Filesystem layout under %APPDATA%\\OpenFOV\\.

```
%APPDATA%\\OpenFOV\\
├── config.toml
└── profiles\\
    ├── Default.toml
    ├── iRacing GT3.toml
    └── ...
```

On non-Windows (CI, dev), `%APPDATA%` is emulated as `~/.config/OpenFOV`.
The `OPENFOV_APPDATA` env var overrides everything — used in tests to point
at a tmp dir."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """Resolve the per-user app-data directory. Creates it if missing."""
    override = os.environ.get("OPENFOV_APPDATA")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            # Last-ditch fallback for very unusual environments. Should not
            # happen on a normal Windows session.
            appdata = str(Path.home() / "AppData" / "Roaming")
        base = Path(appdata) / "OpenFOV"
    else:
        base = Path.home() / ".config" / "OpenFOV"
    base.mkdir(parents=True, exist_ok=True)
    return base


def app_config_path() -> Path:
    return app_data_dir() / "config.toml"


def profiles_dir() -> Path:
    d = app_data_dir() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


_SAFE_NAME = re.compile(r"[^A-Za-z0-9 _\-\.()]")


def sanitize_profile_name(name: str) -> str:
    """Return a filesystem-safe version of the profile name. Spaces and
    common punctuation pass through; anything else is replaced with `_`."""
    cleaned = _SAFE_NAME.sub("_", name).strip().strip(".")
    return cleaned or "Unnamed"


def profile_path(name: str) -> Path:
    """Resolve the on-disk path for a profile by display name."""
    return profiles_dir() / f"{sanitize_profile_name(name)}.toml"
