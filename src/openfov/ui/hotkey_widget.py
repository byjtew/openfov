"""Hotkey-binding widget.

The user clicks the widget, then presses the desired key combination —
we capture it via QKeyEvent and translate to a pynput-compatible string
(`<f9>`, `<ctrl>+<shift>+r`, etc.).

Pure-Qt; no global listener is installed while binding — we just sniff
the keypress that hits this focused widget."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPushButton


# Map Qt::Key values to pynput-style key names. Only the keys real users
# actually bind for sim apps — function keys, common modifiers, the few
# special keys (Esc, Space, Tab, Enter). pynput accepts character keys
# verbatim as single-letter strings.
_QT_KEY_TO_PYNPUT = {
    Qt.Key_F1: "<f1>", Qt.Key_F2: "<f2>", Qt.Key_F3: "<f3>", Qt.Key_F4: "<f4>",
    Qt.Key_F5: "<f5>", Qt.Key_F6: "<f6>", Qt.Key_F7: "<f7>", Qt.Key_F8: "<f8>",
    Qt.Key_F9: "<f9>", Qt.Key_F10: "<f10>", Qt.Key_F11: "<f11>", Qt.Key_F12: "<f12>",
    Qt.Key_Space: "<space>",
    Qt.Key_Tab: "<tab>",
    Qt.Key_Backspace: "<backspace>",
    Qt.Key_Escape: "<esc>",
    Qt.Key_Return: "<enter>",
    Qt.Key_Enter: "<enter>",
    Qt.Key_Insert: "<insert>",
    Qt.Key_Delete: "<delete>",
    Qt.Key_Home: "<home>",
    Qt.Key_End: "<end>",
    Qt.Key_PageUp: "<page_up>",
    Qt.Key_PageDown: "<page_down>",
    Qt.Key_Up: "<up>",
    Qt.Key_Down: "<down>",
    Qt.Key_Left: "<left>",
    Qt.Key_Right: "<right>",
}


def _format_binding(key: int, modifiers: Qt.KeyboardModifier) -> str | None:
    """Translate a Qt keypress into a pynput hotkey spec. Returns None for
    a modifier-only press (so we don't bind "just shift")."""
    parts: list[str] = []
    if modifiers & Qt.ControlModifier:
        parts.append("<ctrl>")
    if modifiers & Qt.AltModifier:
        parts.append("<alt>")
    if modifiers & Qt.ShiftModifier:
        parts.append("<shift>")
    if modifiers & Qt.MetaModifier:
        parts.append("<cmd>")  # Win key on Windows

    # Skip modifier-only presses (no main key yet).
    if key in (
        Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, 0,
    ):
        return None

    if key in _QT_KEY_TO_PYNPUT:
        parts.append(_QT_KEY_TO_PYNPUT[key])
    elif Qt.Key_A <= key <= Qt.Key_Z:
        # Lowercase ASCII letter.
        parts.append(chr(key).lower())
    elif Qt.Key_0 <= key <= Qt.Key_9:
        parts.append(chr(key))
    else:
        # Unsupported / hard to roundtrip; refuse rather than emit garbage.
        return None

    return "+".join(parts)


def _format_for_display(binding: str) -> str:
    """Convert pynput spec like '<ctrl>+<shift>+r' to a human label
    'Ctrl + Shift + R'."""
    if not binding:
        return "(none)"
    parts = []
    for token in binding.split("+"):
        if token.startswith("<") and token.endswith(">"):
            parts.append(token[1:-1].replace("_", " ").title())
        else:
            parts.append(token.upper())
    return " + ".join(parts)


class HotkeyButton(QPushButton):
    """Click to enter capture mode; next keypress becomes the new binding."""

    binding_changed = Signal(str)  # pynput-format string; empty = cleared

    def __init__(self, initial_binding: str = "", parent=None) -> None:
        super().__init__(parent)
        self._binding = initial_binding
        self._capturing = False
        self._refresh_label()
        self.clicked.connect(self._enter_capture)
        self.setFocusPolicy(Qt.StrongFocus)

    # -- public --

    def binding(self) -> str:
        return self._binding

    def set_binding(self, binding: str) -> None:
        self._binding = binding
        self._refresh_label()

    def clear_binding(self) -> None:
        self.set_binding("")
        self.binding_changed.emit("")

    # -- behavior --

    def _refresh_label(self) -> None:
        if self._capturing:
            self.setText("press a key...   (Esc to cancel)")
        elif not self._binding:
            self.setText("(unbound)    click to set")
        else:
            self.setText(_format_for_display(self._binding))

    def _enter_capture(self) -> None:
        self._capturing = True
        self.setChecked(True)
        self.setFocus(Qt.MouseFocusReason)
        self._refresh_label()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: D401
        if not self._capturing:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key_Escape:
            self._capturing = False
            self.setChecked(False)
            self._refresh_label()
            return
        binding = _format_binding(event.key(), event.modifiers())
        if binding is None:
            # Modifier-only press — keep waiting.
            return
        self._binding = binding
        self._capturing = False
        self.setChecked(False)
        self._refresh_label()
        self.binding_changed.emit(self._binding)


__all__ = ["HotkeyButton"]
