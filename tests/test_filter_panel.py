"""FilterPanel slider-range + tooltip + clamping tests."""

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


def test_slider_ranges_are_useful(qapp) -> None:  # noqa: ARG001
    """Sliders should reject values that just defeat the filter or
    freeze the view. Useful range only."""
    from openfov.ui.filter_panel import FilterPanel

    fp = FilterPanel()
    cutoff = fp._cutoff_sliders["yaw"]   # noqa: SLF001
    beta = fp._beta_sliders["yaw"]       # noqa: SLF001

    # min_cutoff: 0.05 Hz .. 5.00 Hz at scale 100
    assert cutoff.minimum() == 5
    assert cutoff.maximum() == 500

    # beta: 0.000 .. 0.300 at scale 1000
    assert beta.minimum() == 0
    assert beta.maximum() == 300


def test_set_params_clamps_out_of_range(qapp) -> None:  # noqa: ARG001
    """A profile saved with an out-of-range value (e.g. min_cutoff=10
    from an older version) gets clamped on load — both the slider AND
    the panel's internal params snap to the new bound, so what the
    filter sees matches what the user sees."""
    from openfov.filtering.pipeline import AxisFilterParams
    from openfov.ui.filter_panel import FilterPanel

    fp = FilterPanel()
    fp.set_params("yaw", AxisFilterParams(min_cutoff=10.0, beta=0.7))
    # Both clamped down.
    assert fp._params["yaw"].min_cutoff == pytest.approx(5.0)   # noqa: SLF001
    assert fp._params["yaw"].beta == pytest.approx(0.3)         # noqa: SLF001
    # Slider position matches.
    assert fp._cutoff_sliders["yaw"].value() == 500             # noqa: SLF001
    assert fp._beta_sliders["yaw"].value() == 300               # noqa: SLF001


def test_help_link_present_and_opens_dialog(qapp, monkeypatch) -> None:  # noqa: ARG001
    """The Smoothing panel should expose a 'What is this?' link that
    opens a tuning-guide dialog. We monkeypatch QMessageBox.information
    so the test doesn't actually pop a modal."""
    from PySide6.QtWidgets import QLabel, QMessageBox

    from openfov.ui.filter_panel import FilterPanel

    fp = FilterPanel()
    links = [w for w in fp.findChildren(QLabel) if "What is this?" in (w.text() or "")]
    assert links, "Help link not found"

    captured: list[tuple[str, str]] = []

    def fake_info(_parent, title, body, *args, **kwargs):  # noqa: ANN001, ARG001
        captured.append((title, body))
        return QMessageBox.Ok

    monkeypatch.setattr(QMessageBox, "information", fake_info)
    fp._show_help()  # noqa: SLF001 — directly invoke the slot
    assert len(captured) == 1
    title, body = captured[0]
    assert "Smoothing" in title
    assert "min_cutoff" in body
    assert "beta" in body
    # "One Euro" reference removed everywhere user-facing.
    assert "One Euro" not in title
    assert "One Euro" not in body


def test_sliders_carry_per_control_tooltip(qapp) -> None:  # noqa: ARG001
    from openfov.ui.filter_panel import FilterPanel

    fp = FilterPanel()
    cutoff = fp._cutoff_sliders["yaw"]   # noqa: SLF001
    beta = fp._beta_sliders["yaw"]       # noqa: SLF001
    assert "smoother at rest" in cutoff.toolTip()
    assert "snappier fast turns" in beta.toolTip()
