"""HotkeyButton + binding-format tests."""

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


def test_format_binding_function_key() -> None:
    from PySide6.QtCore import Qt
    from openfov.ui.hotkey_widget import _format_binding

    assert _format_binding(Qt.Key_F9, Qt.NoModifier) == "<f9>"


def test_format_binding_letter_lowercased() -> None:
    from PySide6.QtCore import Qt
    from openfov.ui.hotkey_widget import _format_binding

    assert _format_binding(Qt.Key_R, Qt.NoModifier) == "r"


def test_format_binding_with_modifiers() -> None:
    from PySide6.QtCore import Qt
    from openfov.ui.hotkey_widget import _format_binding

    binding = _format_binding(
        Qt.Key_R, Qt.ControlModifier | Qt.ShiftModifier
    )
    assert binding == "<ctrl>+<shift>+r"


def test_format_binding_modifier_only_returns_none() -> None:
    from PySide6.QtCore import Qt
    from openfov.ui.hotkey_widget import _format_binding

    assert _format_binding(Qt.Key_Control, Qt.ControlModifier) is None
    assert _format_binding(Qt.Key_Shift, Qt.ShiftModifier) is None


def test_format_binding_special_keys() -> None:
    from PySide6.QtCore import Qt
    from openfov.ui.hotkey_widget import _format_binding

    assert _format_binding(Qt.Key_Space, Qt.NoModifier) == "<space>"
    assert _format_binding(Qt.Key_Escape, Qt.NoModifier) == "<esc>"


def test_format_for_display() -> None:
    from openfov.ui.hotkey_widget import _format_for_display

    assert _format_for_display("<f9>") == "F9"
    assert _format_for_display("<ctrl>+<shift>+r") == "Ctrl + Shift + R"
    assert _format_for_display("") == "(none)"


def test_hotkey_button_initial_label(qapp) -> None:  # noqa: ARG001
    from openfov.ui.hotkey_widget import HotkeyButton

    btn = HotkeyButton(initial_binding="<f9>")
    assert "F9" in btn.text()
    btn2 = HotkeyButton(initial_binding="")
    assert "unbound" in btn2.text().lower()


def test_hotkey_button_clear(qapp) -> None:  # noqa: ARG001
    from openfov.ui.hotkey_widget import HotkeyButton

    captures: list[str] = []
    btn = HotkeyButton(initial_binding="<f9>")
    btn.binding_changed.connect(captures.append)
    btn.clear_binding()
    assert btn.binding() == ""
    assert captures == [""]
