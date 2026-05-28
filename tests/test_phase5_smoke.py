"""Phase 5 smoke: settings dialog + game watcher + main window menu hookups."""

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


@pytest.fixture
def tmp_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))
    return tmp_path


def test_settings_dialog_construct(qapp, tmp_appdata) -> None:
    from openfov.persistence.config import AppConfig
    from openfov.ui.settings_dialog import SettingsDialog

    cfg = AppConfig(
        last_profile="Default",
        camera_width=1280, camera_height=720,
        hotkey_recenter="<f9>",
    )
    dlg = SettingsDialog(cfg)
    assert dlg.windowTitle() == "OpenFOV Settings"


def test_settings_dialog_emits_applied(qapp, tmp_appdata) -> None:
    from openfov.persistence.config import AppConfig
    from openfov.ui.settings_dialog import SettingsDialog

    cfg = AppConfig(camera_width=640, camera_height=480, hotkey_recenter="<f9>")
    dlg = SettingsDialog(cfg)
    captures = []
    dlg.settings_applied.connect(captures.append)
    dlg._on_apply()
    assert len(captures) == 1
    new_cfg = captures[0]
    # User didn't touch anything; values should round-trip unchanged.
    assert new_cfg.camera_width == 640


def test_game_watcher_construct_and_emit(qapp) -> None:
    from openfov.games import IRACING_PROFILE
    from openfov.runtime.game_watcher import GameWatcher

    captures: list = []
    w = GameWatcher([IRACING_PROFILE])
    w.game_changed.connect(captures.append)
    # poll_once is the underlying detector — returns None on a clean
    # machine. We just verify the wrapper doesn't crash.
    assert w.current is None


def test_main_window_has_menu_bar(qapp, tmp_appdata) -> None:
    from openfov.persistence.profiles import Profile
    from openfov.ui.main_window import MainWindow

    win = MainWindow(initial_profile=Profile(name="Default"))
    mb = win.menuBar()
    assert mb is not None
    titles = [a.text().replace("&", "") for a in mb.actions()]
    assert "File" in titles
    assert "Profile" in titles
    assert "View" in titles
    assert "Help" in titles
    win.allow_close()
    win.close()


def test_main_window_request_settings_signal(qapp, tmp_appdata) -> None:
    from openfov.persistence.profiles import Profile
    from openfov.ui.main_window import MainWindow

    win = MainWindow(initial_profile=Profile(name="Default"))
    captures = []
    win.request_settings.connect(lambda: captures.append("settings"))
    win.request_wizard.connect(lambda: captures.append("wizard"))
    win.request_settings.emit()
    win.request_wizard.emit()
    assert captures == ["settings", "wizard"]
    win.allow_close()
    win.close()


def test_on_game_changed_updates_badge(qapp, tmp_appdata) -> None:
    from openfov.games import IRACING_PROFILE
    from openfov.persistence.profiles import Profile
    from openfov.ui.main_window import MainWindow

    win = MainWindow(initial_profile=Profile(name="Default"))
    win.on_game_changed(IRACING_PROFILE)
    assert "iRacing" in win._game_badge.text()
    win.on_game_changed(None)
    assert "no game" in win._game_badge.text().lower()
    win.allow_close()
    win.close()
