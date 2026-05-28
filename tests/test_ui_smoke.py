"""Qt UI smoke tests.

Constructs every widget in `offscreen` Qt mode — verifies they import
cleanly, instantiate, and accept settings updates without crashing. Doesn't
exercise rendering or user interaction.

Uses `pytest-qt` if available, otherwise falls back to a one-shot
QApplication. Skipped on environments without `PySide6` install."""

from __future__ import annotations

import os
import sys

import pytest

# Force the offscreen platform plugin so tests work in CI / SSH / etc.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp() -> object:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("PySide6 not installed")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_camera_view_imports_and_constructs(qapp) -> None:
    from openfov.ui.camera_view import CameraView

    w = CameraView()
    assert w is not None
    w.deleteLater()


def test_pose_readout(qapp) -> None:
    from openfov.runtime.pipeline import PipelineStats
    from openfov.tracker.base import Pose6DOF
    from openfov.ui.pose_readout import PoseReadout

    w = PoseReadout()
    w.update_pose(Pose6DOF(), Pose6DOF(yaw=10.0, pitch=-5.0, roll=2.0),
                  PipelineStats(fps=30.0, inference_ms=5.5, detected=True))
    w.update_pose(Pose6DOF(), Pose6DOF(), PipelineStats(detected=False))


def test_axis_panel_signals(qapp) -> None:
    from openfov.mapping.axis_mapper import AxisSettings
    from openfov.ui.axis_panel import AxisPanel

    captures: list[tuple[str, AxisSettings]] = []
    panel = AxisPanel(axis_name="yaw", label="Yaw")
    panel.changed.connect(lambda a, s: captures.append((a, s)))

    # Toggle invert; expect one emission.
    panel._invert.setChecked(True)
    assert any(c[1].invert for c in captures)


def test_filter_panel_signals(qapp) -> None:
    from openfov.filtering.pipeline import AxisFilterParams
    from openfov.ui.filter_panel import FilterPanel

    captures: list[tuple[str, AxisFilterParams]] = []
    panel = FilterPanel()
    panel.changed.connect(lambda a, p: captures.append((a, p)))

    panel._cutoff_sliders["yaw"].setValue(50)
    assert any(axis == "yaw" for axis, _ in captures)


def test_profile_bar_loads(qapp, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))
    from openfov.ui.profile_bar import ProfileBar

    bar = ProfileBar(initial_profile_name="Default")
    assert bar.current_name() == "Default"


def test_main_window_constructs(qapp, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENFOV_APPDATA", str(tmp_path))
    from openfov.persistence.profiles import Profile
    from openfov.ui.main_window import MainWindow

    win = MainWindow(initial_profile=Profile(name="Default"))
    assert win.windowTitle() == "OpenFOV"
    win.allow_close()
    win.close()


def test_tray_constructs(qapp) -> None:
    from openfov.ui.tray import Tray

    tray = Tray(qapp)
    assert tray is not None
    tray.deleteLater()
