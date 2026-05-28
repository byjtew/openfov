"""Phase 5 limitation fixes: pipeline.set_neutral, AppConfig.always_on_top
round-trip, MainWindow honors initial always_on_top flag."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp() -> object:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("PySide6 not installed")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_appconfig_always_on_top_roundtrip(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))
    from openfov.persistence.config import AppConfig, load_app_config, save_app_config

    cfg = AppConfig(always_on_top=True)
    save_app_config(cfg)
    back = load_app_config()
    assert back.always_on_top is True


def test_main_window_applies_always_on_top(qapp, monkeypatch, tmp_path) -> None:
    from PySide6.QtCore import Qt

    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))
    from openfov.persistence.profiles import Profile
    from openfov.ui.main_window import MainWindow

    win = MainWindow(initial_profile=Profile(name="Default"), always_on_top=True)
    assert bool(win.windowFlags() & Qt.WindowStaysOnTopHint)
    win.allow_close()
    win.close()


def test_pipeline_set_neutral_stores_value() -> None:
    """set_neutral() should immediately update the internal neutral state
    without waiting for a frame."""
    from openfov.output.manager import OutputManager
    from openfov.runtime.pipeline import PipelineThread
    from openfov.tracker.base import Pose6DOF
    from openfov.tracker.debug_tracker import DebugSineTracker

    p = PipelineThread(DebugSineTracker(), OutputManager(), camera_index=0)
    p.set_neutral(Pose6DOF(yaw=12.0, pitch=-5.0, roll=2.0))
    # internal state — verifying via the contract that recenter is cleared
    # and neutral is populated.
    assert p._neutral is not None
    assert p._neutral[0] == 12.0
    assert p._neutral[1] == -5.0
    assert p._neutral[2] == 2.0
    assert p._recenter_requested is False
