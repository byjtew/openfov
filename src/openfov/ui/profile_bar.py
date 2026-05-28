"""Profile dropdown + Save / Save As / Rename / Delete.

Owns the file I/O — the main window only listens for the `profile_loaded`
signal and applies the new settings to the runtime."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
)

from openfov.persistence.profiles import (
    Profile,
    delete_profile,
    list_profile_names,
    load_profile,
    save_profile,
)

logger = logging.getLogger(__name__)


class ProfileBar(QFrame):
    """Top-of-window profile chooser. Emits:
    - `profile_loaded(Profile)` when the user switches profiles (or on
      initial load). Listeners apply the contained settings.
    - `request_save(Profile)` when the user clicks Save — the parent owns
      the canonical current Profile state, so it actually writes."""

    profile_loaded = Signal(object)
    request_save = Signal()

    def __init__(self, initial_profile_name: str = "Default", parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(220)
        self._combo.currentTextChanged.connect(self._on_select)

        self._btn_save = QPushButton("Save")
        self._btn_save_as = QPushButton("Save As…")
        self._btn_rename = QPushButton("Rename…")
        self._btn_delete = QPushButton("Delete")

        self._btn_save.clicked.connect(self.request_save.emit)
        self._btn_save_as.clicked.connect(self._on_save_as)
        self._btn_rename.clicked.connect(self._on_rename)
        self._btn_delete.clicked.connect(self._on_delete)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Profile:"))
        layout.addWidget(self._combo, 1)
        layout.addWidget(self._btn_save)
        layout.addWidget(self._btn_save_as)
        layout.addWidget(self._btn_rename)
        layout.addWidget(self._btn_delete)

        self._reload_combo(select_name=initial_profile_name)

    # -- public API ----------------------------------------------------

    def current_name(self) -> str:
        return self._combo.currentText()

    def refresh(self) -> None:
        """Re-read profile list from disk. Keeps current selection if
        still present, otherwise falls back to first entry."""
        current = self._combo.currentText()
        self._reload_combo(select_name=current)

    # -- internal ------------------------------------------------------

    def _reload_combo(self, select_name: str) -> None:
        self._combo.blockSignals(True)
        try:
            self._combo.clear()
            names = list_profile_names()
            if not names:
                names = ["Default"]
                save_profile(Profile(name="Default"))
            self._combo.addItems(names)
            if select_name in names:
                self._combo.setCurrentText(select_name)
        finally:
            self._combo.blockSignals(False)
        # Fire load explicitly so the main window applies settings.
        name = self._combo.currentText()
        try:
            profile = load_profile(name)
            self.profile_loaded.emit(profile)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load profile %r: %s", name, exc)

    @Slot(str)
    def _on_select(self, name: str) -> None:
        if not name:
            return
        try:
            profile = load_profile(name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Profile error", f"Could not load {name!r}: {exc}")
            return
        self.profile_loaded.emit(profile)

    @Slot()
    def _on_save_as(self) -> None:
        new_name, ok = QInputDialog.getText(
            self, "Save profile as", "New profile name:",
        )
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name in list_profile_names():
            if QMessageBox.question(
                self, "Overwrite?",
                f"A profile named '{new_name}' already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return
        # Build a Profile from the current name's loaded state — main
        # window will call back via request_save with current axis state,
        # but for Save-As we just snapshot the current selection.
        try:
            current = load_profile(self._combo.currentText())
            current.name = new_name
            save_profile(current)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Save error", str(exc))
            return
        self._reload_combo(select_name=new_name)

    @Slot()
    def _on_rename(self) -> None:
        old_name = self._combo.currentText()
        new_name, ok = QInputDialog.getText(
            self, "Rename profile", "New name:", text=old_name,
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        if new_name in list_profile_names():
            QMessageBox.warning(self, "Rename", f"'{new_name}' already exists.")
            return
        try:
            p = load_profile(old_name)
            p.name = new_name
            save_profile(p)
            delete_profile(old_name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Rename error", str(exc))
            return
        self._reload_combo(select_name=new_name)

    @Slot()
    def _on_delete(self) -> None:
        name = self._combo.currentText()
        if name == "Default" or len(list_profile_names()) <= 1:
            QMessageBox.information(
                self, "Delete", "Can't delete the last remaining profile.",
            )
            return
        if QMessageBox.question(
            self, "Delete profile",
            f"Permanently delete '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        delete_profile(name)
        self._reload_combo(select_name="Default")


__all__ = ["ProfileBar"]
