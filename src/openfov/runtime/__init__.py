"""Pipeline orchestration — capture → tracker → filter → mapper → writer.

Threading lives here so individual modules stay free of Qt / threading
concerns. The `PipelineThread` is the head-tracking worker; `CameraSource`
wraps OpenCV with backend selection; `GlobalHotkey` provides system-wide
key bindings."""

from openfov.runtime import autostart
from openfov.runtime.camera import CameraInfo, CameraSource, enumerate_cameras
from openfov.runtime.game_watcher import GameWatcher
from openfov.runtime.hotkey import GlobalHotkey
from openfov.runtime.pipeline import PipelineStats, PipelineThread

__all__ = [
    "CameraInfo",
    "CameraSource",
    "GameWatcher",
    "GlobalHotkey",
    "PipelineStats",
    "PipelineThread",
    "autostart",
    "enumerate_cameras",
]
