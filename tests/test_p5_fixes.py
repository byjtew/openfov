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


def test_pipeline_set_ui_active_toggles_flag() -> None:
    """The visibility gate defaults to active (no behavior change) and
    flips off when the window reports itself hidden/minimized."""
    from openfov.output.manager import OutputManager
    from openfov.runtime.pipeline import PipelineThread
    from openfov.tracker.debug_tracker import DebugSineTracker

    p = PipelineThread(DebugSineTracker(), OutputManager(), camera_index=0)
    assert p._ui_active is True
    p.set_ui_active(False)
    assert p._ui_active is False
    p.set_ui_active(True)
    assert p._ui_active is True


def test_pipeline_set_preview_active_is_independent_of_ui_active() -> None:
    """Pausing the preview must not touch the visibility gate, and vice
    versa — they gate different emits (frame_ready vs. everything)."""
    from openfov.output.manager import OutputManager
    from openfov.runtime.pipeline import PipelineThread
    from openfov.tracker.debug_tracker import DebugSineTracker

    p = PipelineThread(DebugSineTracker(), OutputManager(), camera_index=0)
    assert p._preview_active is True
    p.set_preview_active(False)
    assert p._preview_active is False
    assert p._ui_active is True  # visibility gate untouched
    p.set_preview_active(True)
    assert p._preview_active is True


def test_main_window_pause_preview_toggles_pipeline(qapp, monkeypatch, tmp_path) -> None:
    """The Pause-preview button flips the pipeline's preview gate and its
    own label without disturbing the visibility gate."""
    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))
    from openfov.output.manager import OutputManager
    from openfov.persistence.profiles import Profile
    from openfov.runtime.pipeline import PipelineThread
    from openfov.tracker.debug_tracker import DebugSineTracker
    from openfov.ui.main_window import MainWindow

    win = MainWindow(initial_profile=Profile(name="Default"))
    pipeline = PipelineThread(DebugSineTracker(), OutputManager(), camera_index=0)
    win.attach_pipeline(pipeline)

    win._btn_pause_preview.setChecked(True)  # fires toggled(True)
    assert win._preview_paused is True
    assert pipeline._preview_active is False
    assert win._btn_pause_preview.text() == "Resume preview"

    win._btn_pause_preview.setChecked(False)
    assert win._preview_paused is False
    assert pipeline._preview_active is True
    assert win._btn_pause_preview.text() == "Pause preview"

    win.allow_close()
    win.close()


def test_camera_reader_joins_cleanly() -> None:
    """Regression: the reader's stop Event must not be named `_stop`, which
    shadowed threading.Thread._stop — an internal method join() calls during
    teardown. The shadowing made every shutdown raise 'Event object is not
    callable' and skip the rest of pipeline cleanup."""
    import threading

    from openfov.runtime.pipeline import _CameraReader, _FrameSlot

    stop = threading.Event()
    reader = _CameraReader(lambda: None, _FrameSlot(), stop)
    reader.start()
    stop.set()
    reader.join(timeout=2.0)  # raised TypeError before the fix
    assert not reader.is_alive()


def test_pipeline_toggle_tracking_flips_flag() -> None:
    """The toggle hotkey target flips inference on/off; set_tracking_enabled
    sets it directly. PipelineStats defaults to enabled."""
    from openfov.output.manager import OutputManager
    from openfov.runtime.pipeline import PipelineStats, PipelineThread
    from openfov.tracker.debug_tracker import DebugSineTracker

    p = PipelineThread(DebugSineTracker(), OutputManager(), camera_index=0)
    assert p._tracking_enabled is True
    p.toggle_tracking()
    assert p._tracking_enabled is False
    p.toggle_tracking()
    assert p._tracking_enabled is True
    p.set_tracking_enabled(False)
    assert p._tracking_enabled is False
    assert PipelineStats().tracking_enabled is True


def test_pipeline_accepts_anti_contention_kwargs() -> None:
    """Constructor surface for the OpenCV thread cap + affinity mode."""
    from openfov.output.manager import OutputManager
    from openfov.runtime.pipeline import PipelineThread
    from openfov.tracker.debug_tracker import DebugSineTracker

    p = PipelineThread(
        DebugSineTracker(),
        OutputManager(),
        camera_index=0,
        cv_thread_cap=2,
        cpu_affinity_mode="isolate",
    )
    assert p._cv_thread_cap == 2
    assert p._cpu_affinity_mode == "isolate"
