"""Per-axis tuning panel.

Each axis (yaw, pitch, roll, x, y, z) gets one of these. Composes:
- invert checkbox
- sensitivity slider
- interactive Bezier curve editor (CurveEditor)

The full `AxisSettings` payload is emitted on `changed` whenever any of
those touch the state — the runtime applies it atomically.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
)

from openfov.mapping.axis_mapper import AxisSettings
from openfov.mapping.curve import CubicBezierCurve
from openfov.ui.curve_editor import PRESETS, CurveEditor
from openfov.ui.widgets import reset_button

_SENS_SCALE = 100  # slider integer 0..500 -> 0.00..5.00
_SENS_DEFAULT = 1.0


def _matches_preset(loaded: CubicBezierCurve, preset: CubicBezierCurve) -> bool:
    """Compare two curves anchor-by-anchor with a small tolerance.

    Floats coming back from TOML can drift by a few ULP, so we use
    `abs <= 1e-3` per field — tight enough to distinguish actually-
    different presets (their anchors differ by tens of degrees) but
    forgiving enough for round-trip noise.
    """
    if len(loaded.points) != len(preset.points):
        return False
    for a, b in zip(loaded.points, preset.points, strict=False):
        if (
            abs(a.x - b.x) > 1e-3
            or abs(a.y - b.y) > 1e-3
            or abs(a.tangent_in - b.tangent_in) > 1e-3
            or abs(a.tangent_out - b.tangent_out) > 1e-3
        ):
            return False
    return True


def _detect_preset_index(curve: CubicBezierCurve) -> int | None:
    """Return the index of the PRESET this curve corresponds to, or
    None if it doesn't match any. The domain used to generate each
    preset must match the curve's domain — we use 90.0, which is the
    same domain the rest of the UI uses when applying presets."""
    for i, (_label, factory) in enumerate(PRESETS):
        if _matches_preset(curve, factory(90.0)):
            return i
    return None


class AxisPanel(QFrame):
    """One axis's tuning controls.

    `changed` fires whenever the user touches anything. Carries the
    canonical `AxisSettings` so the pipeline can do an atomic update."""

    changed = Signal(str, object)  # (axis_name, AxisSettings)

    def __init__(self, axis_name: str, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self._axis = axis_name
        self._label = label
        self._settings = AxisSettings()
        # When the user picks a preset from the dropdown we apply it
        # immediately. To avoid the resulting `changed` from the curve
        # editor flipping the dropdown back to "Custom" by mistake, we
        # gate the "custom on edit" detection with this flag.
        self._applying_preset = False

        # Title row: axis name + enable toggle + invert toggle.
        self._title = QLabel(f"<b>{label}</b>")

        self._enabled_cb = QCheckBox("enabled")
        self._enabled_cb.setToolTip(
            "Turn this axis on/off without losing your other settings.\n"
            "When off, OpenFOV sends 0 for this axis."
        )
        self._enabled_cb.setChecked(self._settings.enabled)
        self._enabled_cb.toggled.connect(self._on_enabled)

        self._invert = QCheckBox("invert")
        self._invert.setToolTip("Flip the sign of this axis.")
        self._invert.toggled.connect(self._on_invert)

        title_row = QHBoxLayout()
        title_row.addWidget(self._title)
        title_row.addStretch(1)
        title_row.addWidget(self._enabled_cb)
        title_row.addSpacing(8)
        title_row.addWidget(self._invert)

        # Sensitivity row: explicit "Sensitivity:" label, slider, value, reset.
        sens_label_widget = QLabel("Sensitivity:")
        sens_label_widget.setMinimumWidth(78)
        self._sens = QSlider(Qt.Horizontal)
        self._sens.setMinimum(0)
        self._sens.setMaximum(5 * _SENS_SCALE)
        self._sens.setValue(int(self._settings.sensitivity * _SENS_SCALE))
        self._sens.setSingleStep(1)
        self._sens.setPageStep(10)
        self._sens.setToolTip(
            "How much your head motion is scaled before the curve.\n"
            "1.00x = no scaling. Range 0.00 .. 3.00."
        )
        self._sens.valueChanged.connect(self._on_sens)
        self._sens_value = QLabel(f"{self._settings.sensitivity:.2f}x")
        self._sens_value.setMinimumWidth(52)
        self._sens_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        sens_row = QHBoxLayout()
        sens_row.setSpacing(8)
        sens_row.addWidget(sens_label_widget)
        sens_row.addWidget(self._sens, stretch=1)
        sens_row.addWidget(self._sens_value)
        sens_row.addWidget(reset_button(
            f"Reset {label.lower()} sensitivity to {_SENS_DEFAULT:.2f}x",
            self._reset_sensitivity,
        ))

        # Curve row: "Curve:" label + preset picker dropdown.
        curve_label_widget = QLabel("Curve:")
        curve_label_widget.setMinimumWidth(78)
        curve_label_widget.setToolTip(
            "Left-click empty space to add a point. Drag an anchor "
            "to move it. Right-click an anchor to remove it."
        )
        self._preset_combo = QComboBox()
        self._preset_combo.setToolTip(
            "Pick a starting shape. The selector switches to 'Custom' "
            "when you edit the curve by hand."
        )
        for preset_label, _factory in PRESETS:
            self._preset_combo.addItem(preset_label)
        self._preset_combo.addItem("Custom")
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)

        curve_row = QHBoxLayout()
        curve_row.setSpacing(8)
        curve_row.addWidget(curve_label_widget)
        curve_row.addWidget(self._preset_combo, stretch=1)

        self._curve_editor = CurveEditor()
        self._curve_editor.set_curve(self._settings.curve)
        self._curve_editor.changed.connect(self._on_curve_changed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)
        outer.addLayout(title_row)
        outer.addLayout(sens_row)
        outer.addLayout(curve_row)
        outer.addWidget(self._curve_editor)

        # Apply the initial enabled state to the row visuals.
        self._apply_enabled_visuals()

    # -- public API ----------------------------------------------------

    def set_settings(self, settings: AxisSettings) -> None:
        """Pull settings into the UI without triggering `changed` storms."""
        self._settings = settings
        self.blockSignals(True)
        try:
            self._enabled_cb.setChecked(settings.enabled)
            self._invert.setChecked(settings.invert)
            self._sens.setValue(int(settings.sensitivity * _SENS_SCALE))
            self._sens_value.setText(f"{settings.sensitivity:.2f}x")
        finally:
            self.blockSignals(False)
        self._curve_editor.blockSignals(True)
        try:
            self._curve_editor.set_curve(settings.curve)
        finally:
            self._curve_editor.blockSignals(False)
        # Match the loaded curve against the known presets. If it
        # matches one (e.g. the freshly-shipped default is `linear`),
        # show that preset name. Otherwise fall back to "Custom" so
        # users with hand-tuned curves see the right label.
        match_idx = _detect_preset_index(settings.curve)
        target_idx = match_idx if match_idx is not None else self._preset_combo.count() - 1
        self._preset_combo.blockSignals(True)
        try:
            self._preset_combo.setCurrentIndex(target_idx)
        finally:
            self._preset_combo.blockSignals(False)
        self._apply_enabled_visuals()

    def settings(self) -> AxisSettings:
        return self._settings

    def axis_name(self) -> str:
        return self._axis

    @Slot(float, float)
    def set_live(self, input_value: float, output_value: float) -> None:
        """Forward to the curve editor's live indicator."""
        self._curve_editor.set_live(input_value, output_value)

    def clear_live(self) -> None:
        self._curve_editor.clear_live()

    # -- internal slots ------------------------------------------------

    @Slot(bool)
    def _on_enabled(self, checked: bool) -> None:
        self._settings = replace(self._settings, enabled=checked)
        self._apply_enabled_visuals()
        self.changed.emit(self._axis, self._settings)

    @Slot(bool)
    def _on_invert(self, checked: bool) -> None:
        self._settings = replace(self._settings, invert=checked)
        self.changed.emit(self._axis, self._settings)

    @Slot(int)
    def _on_sens(self, raw: int) -> None:
        val = raw / _SENS_SCALE
        self._settings = replace(self._settings, sensitivity=val)
        self._sens_value.setText(f"{val:.2f}x")
        self.changed.emit(self._axis, self._settings)

    @Slot(object)
    def _on_curve_changed(self, new_curve: CubicBezierCurve) -> None:
        self._settings = replace(self._settings, curve=new_curve)
        # User-driven edits flip the dropdown to "Custom"; preset-driven
        # edits skip this so the dropdown shows the picked preset name.
        if not self._applying_preset:
            self._preset_combo.blockSignals(True)
            try:
                self._preset_combo.setCurrentIndex(self._preset_combo.count() - 1)
            finally:
                self._preset_combo.blockSignals(False)
        self.changed.emit(self._axis, self._settings)

    @Slot(int)
    def _on_preset_selected(self, idx: int) -> None:
        if idx < 0 or idx >= len(PRESETS):
            # "Custom" entry — do nothing; user keeps their hand-edited curve.
            return
        _label, factory = PRESETS[idx]
        self._applying_preset = True
        try:
            self._curve_editor.apply_preset(factory(90.0))
        finally:
            self._applying_preset = False

    # -- reset handlers ------------------------------------------------

    def _reset_sensitivity(self) -> None:
        self._sens.setValue(int(_SENS_DEFAULT * _SENS_SCALE))
        # _on_sens fires, emits `changed`, updates value label.

    # -- helpers -------------------------------------------------------

    def _apply_enabled_visuals(self) -> None:
        """Dim the per-axis controls when the axis is disabled, so the
        panel reads as 'off' at a glance. The enabled checkbox itself
        stays interactive so the user can flip the axis back on."""
        on = self._settings.enabled
        for w in (
            self._invert, self._sens, self._sens_value,
            self._preset_combo, self._curve_editor,
        ):
            w.setEnabled(on)
        # Dynamic property drives the panel-wide muted look via QSS
        # (`QFrame[axisDisabled="true"]`).
        self.setProperty("axisDisabled", not on)
        # Force QSS re-evaluation since dynamic-property changes don't
        # auto-trigger a restyle.
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


__all__ = ["AxisPanel"]
