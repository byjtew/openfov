"""Config and profile persistence under %APPDATA%\\OpenFOV\\."""

from openfov.persistence.config import AppConfig, load_app_config, save_app_config
from openfov.persistence.paths import (
    app_config_path,
    app_data_dir,
    profile_path,
    profiles_dir,
)
from openfov.persistence.profiles import (
    Profile,
    delete_profile,
    list_profile_names,
    load_profile,
    save_profile,
)

__all__ = [
    "AppConfig",
    "Profile",
    "app_config_path",
    "app_data_dir",
    "delete_profile",
    "list_profile_names",
    "load_app_config",
    "load_profile",
    "profile_path",
    "profiles_dir",
    "save_app_config",
    "save_profile",
]
