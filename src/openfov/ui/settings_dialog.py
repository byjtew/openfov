"""Settings dialog — tabs for the items that don't belong on the main page.

General: autostart + re-run wizard.
Performance: resolution, inference downscale, output extrapolation. Presets
   handle 95% of users; the spinboxes are there for hand-tuning.
Hotkeys: bind/clear recenter + pause.
Output: show the registered NPClient location + path to bundled bin dir.

On Accept, copies the edited state back to the supplied `AppConfig` and
emits `settings_applied()` so the host app can re-apply anything that's
runtime-mutable (hotkeys, camera resolution, perf knobs).
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from openfov.output import bundled_bin_dir, read_registry_path
from openfov.persistence.config import (
    PERFORMANCE_PRESETS,
    AppConfig,
    preset_values_match,
)
from openfov.ui.hotkey_widget import HotkeyButton

_RESOLUTIONS: tuple[tuple[int, int], ...] = (
    (640, 480),
    (1280, 720),
    (1920, 1080),
)


# 0 in the spinbox means "native resolution, no downscale" — maps to
# inference_max_dim=None in AppConfig. The spinbox range covers the
# useful inference sizes; below 160 MediaPipe accuracy starts dropping.
_INFER_DIM_MIN = 0
_INFER_DIM_MAX = 1920


class SettingsDialog(QDialog):
    """Tabbed app-settings dialog."""

    settings_applied = Signal(object)  # the edited AppConfig
    run_wizard_requested = Signal()

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OpenFOV Settings")
        self.resize(560, 420)
        self._config = replace(config)  # edit a copy so Cancel works
        self._original = config

        tabs = QTabWidget(self)
        tabs.addTab(self._make_general_tab(), "General")
        tabs.addTab(self._make_performance_tab(), "Performance")
        tabs.addTab(self._make_hotkeys_tab(), "Hotkeys")
        tabs.addTab(self._make_output_tab(), "Output")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)

        outer = QVBoxLayout(self)
        outer.addWidget(tabs)
        outer.addWidget(buttons)

    # ----- General -----

    def _make_general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._start_with_windows = QCheckBox()
        self._start_with_windows.setChecked(self._config.start_with_windows)
        form.addRow("Start with Windows", self._start_with_windows)

        wizard_btn = QPushButton("Re-run setup wizard...")
        wizard_btn.clicked.connect(lambda: self.run_wizard_requested.emit())
        form.addRow("Setup", wizard_btn)

        return w

    # ----- Performance -----

    def _make_performance_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        # Preset picker. Selecting one populates resolution + inference
        # downscale below; the user can then hand-tune (which flips the
        # preset to "Custom").
        self._preset = QComboBox()
        self._preset.addItem("Performance (low-end CPU)", "performance")
        self._preset.addItem("Balanced (recommended)", "balanced")
        self._preset.addItem("Quality (desktop CPU)", "quality")
        self._preset.addItem("Custom", "custom")
        # Find the index matching the saved preset name.
        for i in range(self._preset.count()):
            if self._preset.itemData(i) == self._config.performance_preset:
                self._preset.setCurrentIndex(i)
                break
        form.addRow("Preset", self._preset)

        # Resolution combo — same options as before, but now under the
        # Performance tab where it logically belongs (each preset binds
        # to a specific resolution).
        self._resolution = QComboBox()
        current_pair = (self._config.camera_width, self._config.camera_height)
        for width, height in _RESOLUTIONS:
            self._resolution.addItem(f"{width} x {height}", (width, height))
            if (width, height) == current_pair:
                self._resolution.setCurrentIndex(self._resolution.count() - 1)
        form.addRow("Capture resolution", self._resolution)

        # Inference downscale. 0 = native resolution.
        self._infer_dim = QSpinBox()
        self._infer_dim.setRange(_INFER_DIM_MIN, _INFER_DIM_MAX)
        self._infer_dim.setSingleStep(16)
        self._infer_dim.setSuffix(" px")
        self._infer_dim.setSpecialValueText("Native (no downscale)")
        self._infer_dim.setValue(
            self._config.inference_max_dim if self._config.inference_max_dim else 0
        )
        form.addRow("Inference downscale", self._infer_dim)

        note = QLabel(
            "<i>OpenFOV asks the camera for 60 fps and falls back to "
            "whatever the device supports (typically 30 fps on older "
            "or integrated webcams). Lower the inference downscale to "
            "use less CPU; raise it for more stable landmarks. iRacing "
            "receives one pose write per inference frame.</i>"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #7a838c;")
        form.addRow(note)

        # Wire the interactions:
        # - Preset change → snap dependent fields.
        # - User edits a dependent field → flip preset to Custom.
        self._preset.activated.connect(self._on_preset_activated)
        self._resolution.activated.connect(self._mark_custom)
        self._infer_dim.valueChanged.connect(self._mark_custom_from_value)

        return w

    def _on_preset_activated(self, _idx: int) -> None:
        preset_id = self._preset.currentData()
        if preset_id == "custom":
            return  # User picked Custom directly — leave existing values.
        spec = PERFORMANCE_PRESETS.get(preset_id)
        if spec is None:
            return
        # Apply the preset to the dependent fields without triggering the
        # "mark custom" handler (we're the source of the change).
        self._resolution.blockSignals(True)
        self._infer_dim.blockSignals(True)
        try:
            pair = (spec["camera_width"], spec["camera_height"])
            for i in range(self._resolution.count()):
                if self._resolution.itemData(i) == pair:
                    self._resolution.setCurrentIndex(i)
                    break
            self._infer_dim.setValue(spec["inference_max_dim"] or 0)
        finally:
            self._resolution.blockSignals(False)
            self._infer_dim.blockSignals(False)

    def _mark_custom(self, _idx: int = 0) -> None:
        # Find the "custom" entry and select it.
        for i in range(self._preset.count()):
            if self._preset.itemData(i) == "custom":
                self._preset.setCurrentIndex(i)
                return

    def _mark_custom_from_value(self, _v: int) -> None:
        self._mark_custom()

    # ----- Hotkeys -----

    def _make_hotkeys_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._recenter_button = HotkeyButton(self._config.hotkey_recenter)
        row1 = QHBoxLayout()
        row1.addWidget(self._recenter_button, 1)
        clear1 = QPushButton("Clear")
        clear1.clicked.connect(self._recenter_button.clear_binding)
        row1.addWidget(clear1)
        wrap1 = QWidget()
        wrap1.setLayout(row1)
        form.addRow("Recenter", wrap1)

        note = QLabel(
            "<i>Hotkeys are global - they work even when iRacing has focus. "
            "Click a binding, then press the key combination you want. "
            "Escape cancels.</i>"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #7a838c;")
        form.addRow(note)

        return w

    # ----- Output -----

    def _make_output_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        bin_dir = bundled_bin_dir()
        bin_lbl = QLabel(str(bin_dir))
        bin_lbl.setStyleSheet("color: #cfeae5; font-family: Consolas;")
        bin_lbl.setWordWrap(True)
        form.addRow("Bundled binaries", bin_lbl)

        reg = read_registry_path() or "(not registered yet)"
        reg_lbl = QLabel(reg)
        reg_lbl.setStyleSheet("color: #cfeae5; font-family: Consolas;")
        reg_lbl.setWordWrap(True)
        form.addRow("NPClient registry", reg_lbl)

        note = QLabel(
            "<i>OpenFOV writes pose data to the FreeTrack shared-memory section "
            "every frame. Games discover the NPClient DLL via a per-user "
            "registry key pointing at the bundled bin directory above. No "
            "system-wide changes; uninstall is clean.</i>"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #7a838c;")
        form.addRow(note)
        return w

    # ----- accept / apply -----

    def _harvest(self) -> AppConfig:
        width, height = self._resolution.currentData()
        infer_dim_raw = self._infer_dim.value()
        infer_dim = infer_dim_raw if infer_dim_raw > 0 else None
        preset_id = self._preset.currentData() or "custom"
        candidate = replace(
            self._config,
            start_with_windows=self._start_with_windows.isChecked(),
            camera_width=int(width),
            camera_height=int(height),
            performance_preset=preset_id,
            inference_max_dim=infer_dim,
            hotkey_recenter=self._recenter_button.binding(),
        )
        # If the spinbox values now actually match one of the named
        # presets (e.g. user picked Custom but ended up on Balanced's
        # exact values), snap the label back. Avoids "Custom" sticking
        # forever after a single experiment.
        if preset_id == "custom":
            for name in PERFORMANCE_PRESETS:
                if preset_values_match(name, candidate):
                    candidate = replace(candidate, performance_preset=name)
                    break
        return candidate

    def _on_apply(self) -> None:
        self._config = self._harvest()
        self.settings_applied.emit(self._config)

    def _on_ok(self) -> None:
        self._config = self._harvest()
        self.settings_applied.emit(self._config)
        self.accept()

    def edited_config(self) -> AppConfig:
        return self._config


__all__ = ["SettingsDialog"]
