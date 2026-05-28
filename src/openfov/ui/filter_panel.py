"""Per-axis filter tuning.

Three controls per axis:
- min_cutoff (Hz): One Euro low-frequency cutoff. Lower = smoother at
  rest, more lag when moving.
- beta: One Euro speed coefficient. Higher = less lag during fast motion,
  more jitter at rest.
- dead-zone (°): post-filter hysteresis. Locks the output against
  sub-threshold jitter while still. 0 = disabled.

Plus a per-axis median toggle (3-wide rolling median in front of One
Euro) for outlier rejection.

Rotation axes only (yaw, pitch, roll) — translation is deferred."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSlider,
)

from openfov.filtering.pipeline import AxisFilterParams
from openfov.ui.widgets import reset_button

# Slider ranges clipped to the *actually useful* zone. The full
# mathematical range of the One Euro filter is much wider, but values
# outside these ranges either defeat the filter (very high) or freeze
# the view (very low). Defaults: 1.0 / 0.05 — known good for sim racing.
_CUTOFF_SCALE = 100      # int 5..500    -> 0.05..5.00 Hz
_CUTOFF_MIN = 5
_CUTOFF_MAX = 500
_CUTOFF_DEFAULT = 1.0

_BETA_SCALE = 1000       # int 0..300    -> 0.000..0.300
_BETA_MIN = 0
_BETA_MAX = 300
_BETA_DEFAULT = 0.05

# Dead-zone range. Units are degrees for rotation axes. 0.00 disables;
# above ~1.0° starts feeling sticky on small movements. Step 0.01°.
_DZ_SCALE = 100          # int 0..200    -> 0.00..2.00 °
_DZ_MIN = 0
_DZ_MAX = 200
_DZ_DEFAULT = 0.0

# Median is exposed as a simple checkbox: off (window=1) or on (window=3).
# 5-wide is supported in the filter itself but feels too soft on real
# motion at typical webcam rates. Keep the UI tight.
_MEDIAN_ON_WINDOW = 3
_MEDIAN_OFF_WINDOW = 1
_MEDIAN_DEFAULT_WINDOW = 3  # on by default — significantly cleaner output


ROTATION_AXES: tuple[tuple[str, str], ...] = (
    ("yaw", "Yaw"),
    ("pitch", "Pitch"),
    ("roll", "Roll"),
)


# Long-form help shown by the "What is this?" link. Rendered in a
# QMessageBox.information dialog.
_SMOOTHING_HELP_TITLE = "Smoothing & stabilization"
_SMOOTHING_HELP_BODY = (
    "OpenFOV cleans up the small frame-to-frame noise in your head "
    "pose before it gets sent to the game. There are three independent "
    "stages, in order:\n"
    "\n"
    "1. Outlier rejection (Median checkbox)\n"
    "    A 3-sample rolling median in front of the smoother. Single bad "
    "frames from the tracker are thrown away rather than smeared into "
    "the next few frames. May slightly increase processing load. On by "
    "default.\n"
    "\n"
    "2. Adaptive smoothing (min_cutoff + beta sliders)\n"
    "    The central filter — smooths when you're still, relaxes when "
    "you move.\n"
    "\n"
    "    min_cutoff (Hz) — filter strength while you're still.\n"
    "      Lower  =  smoother at rest, more lag when moving.\n"
    "      Higher =  more jitter at rest, less lag when moving.\n"
    "\n"
    "    beta — how the filter relaxes during motion.\n"
    "      Lower  =  filter stays strong even during fast turns (more lag).\n"
    "      Higher =  filter relaxes quickly during fast turns (less lag).\n"
    "\n"
    "3. Dead-zone (slider, degrees)\n"
    "    A hysteresis stage after smoothing. Locks the output if the "
    "movement is below the threshold, eliminating residual rest-jitter. "
    "Above the threshold it follows your head normally, just offset by "
    "the threshold amount. 0.00 disables.\n"
    "\n"
    "Tuning order:\n"
    "  - Try Median on first. Most people notice an immediate quality lift.\n"
    "  - Then tune the smoothing sliders for the right responsiveness.\n"
    "  - Finally, if you still see sub-degree jitter at rest, raise the "
    "dead-zone in 0.05° steps until it disappears.\n"
    "\n"
    "Defaults: median on, min_cutoff=1.0 Hz, beta=0.05, dead-zone=0.0."
)


_CUTOFF_HEADER_TOOLTIP = (
    "Filter strength while still.\n"
    "Lower = smoother at rest, more lag when moving.\n"
    "Range 0.05 - 5.00 Hz, default 1.0."
)

_BETA_HEADER_TOOLTIP = (
    "How fast the filter relaxes during motion.\n"
    "Higher = snappier fast turns, more jitter at rest.\n"
    "Range 0.000 - 0.300, default 0.05."
)

_DZ_HEADER_TOOLTIP = (
    "Dead-zone threshold (degrees).\n"
    "Below the threshold, the output is locked — zero jitter at rest.\n"
    "Above it, the output tracks normally. 0.00 disables."
)

_MEDIAN_TOOLTIP = (
    "3-wide rolling median in front of the smoother.\n"
    "Rejects single-frame tracker glitches.\n"
    "May slightly increase processing load."
)


class FilterPanel(QFrame):
    """Smoothing + stabilization controls for rotation axes. Emits
    `changed(axis, params)` whenever any control moves."""

    changed = Signal(str, object)  # (axis_name, AxisFilterParams)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)

        # Title + a clickable "What is this?" link. Clicking opens a
        # standard modal dialog with the tuning guide — no custom
        # hover popups.
        title = QLabel("<b>Smoothing</b>")
        help_link = QLabel(
            "<a href='#' style='color:#82c4ae; text-decoration:none;'>"
            "What is this?</a>"
        )
        help_link.setCursor(Qt.PointingHandCursor)
        help_link.setToolTip("Open the smoothing tuning guide.")
        help_link.linkActivated.connect(lambda _href: self._show_help())

        self._params: dict[str, AxisFilterParams] = {
            axis: AxisFilterParams() for axis, _ in ROTATION_AXES
        }
        self._cutoff_sliders: dict[str, QSlider] = {}
        self._beta_sliders: dict[str, QSlider] = {}
        self._dz_sliders: dict[str, QSlider] = {}
        self._median_boxes: dict[str, QCheckBox] = {}
        self._cutoff_labels: dict[str, QLabel] = {}
        self._beta_labels: dict[str, QLabel] = {}
        self._dz_labels: dict[str, QLabel] = {}

        grid = QGridLayout()
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        # Title row hosts the bold "Smoothing" label and the "What is
        # this?" help link side-by-side.
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(title)
        title_row.addSpacing(10)
        title_row.addWidget(help_link)
        title_row.addStretch(1)

        # Column layout (10 cols):
        #   0: axis label
        #   1: min_cutoff slider     2: value     3: reset
        #   4: beta slider           5: value     6: reset
        #   7: dead-zone slider      8: value     9: reset
        #  10: median checkbox
        grid.addLayout(title_row, 0, 0, 1, 11)
        cutoff_hdr = QLabel("<i>min_cutoff (Hz)</i>")
        cutoff_hdr.setToolTip(_CUTOFF_HEADER_TOOLTIP)
        grid.addWidget(cutoff_hdr, 1, 1, 1, 1)
        beta_hdr = QLabel("<i>beta</i>")
        beta_hdr.setToolTip(_BETA_HEADER_TOOLTIP)
        grid.addWidget(beta_hdr, 1, 4, 1, 1)
        dz_hdr = QLabel("<i>dead-zone (°)</i>")
        dz_hdr.setToolTip(_DZ_HEADER_TOOLTIP)
        grid.addWidget(dz_hdr, 1, 7, 1, 1)
        median_hdr = QLabel("<i>median</i>")
        median_hdr.setToolTip(_MEDIAN_TOOLTIP)
        grid.addWidget(median_hdr, 1, 10, 1, 1)

        # Rows.
        for row, (axis, label) in enumerate(ROTATION_AXES, start=2):
            grid.addWidget(QLabel(label), row, 0)

            # ----- min_cutoff -----
            cutoff = QSlider(Qt.Horizontal)
            cutoff.setMinimum(_CUTOFF_MIN)
            cutoff.setMaximum(_CUTOFF_MAX)
            cutoff.setSingleStep(1)
            cutoff.setPageStep(10)
            cutoff.setValue(int(self._params[axis].min_cutoff * _CUTOFF_SCALE))
            cutoff.setToolTip(_CUTOFF_HEADER_TOOLTIP)
            cutoff.valueChanged.connect(lambda v, a=axis: self._on_cutoff(a, v))
            self._cutoff_sliders[axis] = cutoff
            grid.addWidget(cutoff, row, 1)

            cutoff_lbl = QLabel(f"{self._params[axis].min_cutoff:.2f}")
            cutoff_lbl.setMinimumWidth(48)
            self._cutoff_labels[axis] = cutoff_lbl
            grid.addWidget(cutoff_lbl, row, 2)

            grid.addWidget(
                reset_button(
                    f"Reset {label.lower()} min_cutoff to {_CUTOFF_DEFAULT:.2f} Hz",
                    lambda a=axis: self._reset_cutoff(a),
                ),
                row, 3,
            )

            # ----- beta -----
            beta = QSlider(Qt.Horizontal)
            beta.setMinimum(_BETA_MIN)
            beta.setMaximum(_BETA_MAX)
            beta.setSingleStep(1)
            beta.setPageStep(10)
            beta.setValue(int(self._params[axis].beta * _BETA_SCALE))
            beta.setToolTip(_BETA_HEADER_TOOLTIP)
            beta.valueChanged.connect(lambda v, a=axis: self._on_beta(a, v))
            self._beta_sliders[axis] = beta
            grid.addWidget(beta, row, 4)

            beta_lbl = QLabel(f"{self._params[axis].beta:.3f}")
            beta_lbl.setMinimumWidth(56)
            self._beta_labels[axis] = beta_lbl
            grid.addWidget(beta_lbl, row, 5)

            grid.addWidget(
                reset_button(
                    f"Reset {label.lower()} beta to {_BETA_DEFAULT:.3f}",
                    lambda a=axis: self._reset_beta(a),
                ),
                row, 6,
            )

            # ----- dead-zone -----
            dz = QSlider(Qt.Horizontal)
            dz.setMinimum(_DZ_MIN)
            dz.setMaximum(_DZ_MAX)
            dz.setSingleStep(1)
            dz.setPageStep(5)
            dz.setValue(int(self._params[axis].dead_zone * _DZ_SCALE))
            dz.setToolTip(_DZ_HEADER_TOOLTIP)
            dz.valueChanged.connect(lambda v, a=axis: self._on_dz(a, v))
            self._dz_sliders[axis] = dz
            grid.addWidget(dz, row, 7)

            dz_lbl = QLabel(f"{self._params[axis].dead_zone:.2f}")
            dz_lbl.setMinimumWidth(48)
            self._dz_labels[axis] = dz_lbl
            grid.addWidget(dz_lbl, row, 8)

            grid.addWidget(
                reset_button(
                    f"Reset {label.lower()} dead-zone to {_DZ_DEFAULT:.2f}°",
                    lambda a=axis: self._reset_dz(a),
                ),
                row, 9,
            )

            # ----- median checkbox -----
            median = QCheckBox()
            median.setToolTip(_MEDIAN_TOOLTIP)
            median.setChecked(self._params[axis].median_window > 1)
            median.toggled.connect(lambda on, a=axis: self._on_median(a, on))
            self._median_boxes[axis] = median
            grid.addWidget(median, row, 10)

        self.setLayout(grid)

    # -- public API ----------------------------------------------------

    def set_params(self, axis: str, params: AxisFilterParams) -> None:
        if axis not in self._params:
            return
        # Clamp to the displayable range. Profiles saved before the range
        # was tightened can carry values outside the slider's bounds.
        clamped = AxisFilterParams(
            min_cutoff=max(
                _CUTOFF_MIN / _CUTOFF_SCALE,
                min(_CUTOFF_MAX / _CUTOFF_SCALE, params.min_cutoff),
            ),
            beta=max(
                _BETA_MIN / _BETA_SCALE,
                min(_BETA_MAX / _BETA_SCALE, params.beta),
            ),
            d_cutoff=params.d_cutoff,
            median_window=int(params.median_window),
            dead_zone=max(
                _DZ_MIN / _DZ_SCALE,
                min(_DZ_MAX / _DZ_SCALE, params.dead_zone),
            ),
        )
        self._params[axis] = clamped
        # Block signals while we re-seed widgets so we don't bounce a
        # synthetic `changed` back to the caller mid-load.
        widgets = (
            self._cutoff_sliders[axis],
            self._beta_sliders[axis],
            self._dz_sliders[axis],
            self._median_boxes[axis],
        )
        for w in widgets:
            w.blockSignals(True)
        try:
            self._cutoff_sliders[axis].setValue(int(clamped.min_cutoff * _CUTOFF_SCALE))
            self._beta_sliders[axis].setValue(int(clamped.beta * _BETA_SCALE))
            self._dz_sliders[axis].setValue(int(clamped.dead_zone * _DZ_SCALE))
            self._median_boxes[axis].setChecked(clamped.median_window > 1)
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._cutoff_labels[axis].setText(f"{clamped.min_cutoff:.2f}")
        self._beta_labels[axis].setText(f"{clamped.beta:.3f}")
        self._dz_labels[axis].setText(f"{clamped.dead_zone:.2f}")

    # -- internal slots ------------------------------------------------

    def _emit(self, axis: str) -> None:
        self.changed.emit(axis, self._params[axis])

    @Slot(str, int)
    def _on_cutoff(self, axis: str, raw: int) -> None:
        val = raw / _CUTOFF_SCALE
        cur = self._params[axis]
        self._params[axis] = AxisFilterParams(
            min_cutoff=val,
            beta=cur.beta,
            d_cutoff=cur.d_cutoff,
            median_window=cur.median_window,
            dead_zone=cur.dead_zone,
        )
        self._cutoff_labels[axis].setText(f"{val:.2f}")
        self._emit(axis)

    @Slot(str, int)
    def _on_beta(self, axis: str, raw: int) -> None:
        val = raw / _BETA_SCALE
        cur = self._params[axis]
        self._params[axis] = AxisFilterParams(
            min_cutoff=cur.min_cutoff,
            beta=val,
            d_cutoff=cur.d_cutoff,
            median_window=cur.median_window,
            dead_zone=cur.dead_zone,
        )
        self._beta_labels[axis].setText(f"{val:.3f}")
        self._emit(axis)

    @Slot(str, int)
    def _on_dz(self, axis: str, raw: int) -> None:
        val = raw / _DZ_SCALE
        cur = self._params[axis]
        self._params[axis] = AxisFilterParams(
            min_cutoff=cur.min_cutoff,
            beta=cur.beta,
            d_cutoff=cur.d_cutoff,
            median_window=cur.median_window,
            dead_zone=val,
        )
        self._dz_labels[axis].setText(f"{val:.2f}")
        self._emit(axis)

    @Slot(str, bool)
    def _on_median(self, axis: str, on: bool) -> None:
        cur = self._params[axis]
        self._params[axis] = AxisFilterParams(
            min_cutoff=cur.min_cutoff,
            beta=cur.beta,
            d_cutoff=cur.d_cutoff,
            median_window=_MEDIAN_ON_WINDOW if on else _MEDIAN_OFF_WINDOW,
            dead_zone=cur.dead_zone,
        )
        self._emit(axis)

    # -- reset handlers ------------------------------------------------

    def _reset_cutoff(self, axis: str) -> None:
        self._cutoff_sliders[axis].setValue(int(_CUTOFF_DEFAULT * _CUTOFF_SCALE))

    def _reset_beta(self, axis: str) -> None:
        self._beta_sliders[axis].setValue(int(_BETA_DEFAULT * _BETA_SCALE))

    def _reset_dz(self, axis: str) -> None:
        self._dz_sliders[axis].setValue(int(_DZ_DEFAULT * _DZ_SCALE))

    # -- help dialog ---------------------------------------------------

    def _show_help(self) -> None:
        QMessageBox.information(self, _SMOOTHING_HELP_TITLE, _SMOOTHING_HELP_BODY)


__all__ = ["FilterPanel"]
