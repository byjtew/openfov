"""Global app config — the small set of settings that aren't per-profile."""

from __future__ import annotations

import sys
import tomli_w
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — we require 3.11+ in pyproject
    import tomli as tomllib  # type: ignore[no-redef]

from openfov.persistence.paths import app_config_path


# Performance presets. We hold camera FPS at the standard 30 across the
# board — every consumer USB webcam supports it without pixel-format
# gymnastics, which keeps the device-negotiation path simple and avoids
# the YUY2-vs-MJPG bandwidth dance. The two knobs that actually vary by
# preset are camera resolution (decode cost) and inference downscale
# (MediaPipe cost). Output extrapolation is *not* part of the preset —
# it's an independent toggle, off by default, so users can opt in
# regardless of which preset they picked.
#
# - "performance":  for laptops + integrated webcams. 480p capture, tiny
#                   inference input. Best fit for weak CPUs.
# - "balanced":     the default. 720p capture, 480-wide inference. Good
#                   accuracy + comfortably above the 30 fps camera ceiling
#                   on most modern CPUs.
# - "quality":      desktop CPUs only. Full-res inference for the most
#                   stable landmarks if you've got the cycles.
# - "custom":       user has overridden one of the spinboxes; we keep the
#                   raw values and stop snapping to a preset.
PERFORMANCE_PRESETS: dict[str, dict[str, int | None]] = {
    # All three presets capture at 1280x720 because cameras *vary
    # wildly* on their fps-by-resolution table. Many webcams support
    # 60 fps at 720p but cap at 30 fps at lower resolutions — counter-
    # intuitive but real (verified on the dev hardware). We let the
    # inference downscale be the lever that distinguishes presets;
    # capture stays at the camera's high-fps sweet spot.
    "performance": {
        "camera_width": 1280,
        "camera_height": 720,
        "inference_max_dim": 320,
    },
    "balanced": {
        "camera_width": 1280,
        "camera_height": 720,
        "inference_max_dim": 480,
    },
    "quality": {
        "camera_width": 1280,
        "camera_height": 720,
        "inference_max_dim": None,
    },
}


def preset_values_match(preset: str, cfg: "AppConfig") -> bool:
    """True if the config's perf knobs exactly match the named preset."""
    spec = PERFORMANCE_PRESETS.get(preset)
    if spec is None:
        return False
    return (
        cfg.camera_width == spec["camera_width"]
        and cfg.camera_height == spec["camera_height"]
        and cfg.inference_max_dim == spec["inference_max_dim"]
    )


@dataclass
class AppConfig:
    """Settings that survive across profile switches."""

    last_profile: str = "Default"
    camera_index: int = 0
    # Default capture resolution is 1280x720 — most webcams hit their
    # high-fps mode (60 fps) at this resolution. We pair it with the
    # 320-px inference downscale below so we keep the high frame rate
    # AND get cheap inference.
    camera_width: int = 1280
    camera_height: int = 720
    show_wizard_on_next_launch: bool = True
    start_with_windows: bool = False
    always_on_top: bool = False

    # Performance knobs. Defaults match the "performance" preset — 480p
    # capture + 320-wide inference downscale. We deliberately default
    # to the lighter setting because under iRacing's GPU/CPU load
    # MediaPipe inference grows from 5 ms idle to 15-20 ms on the
    # 480-px (Balanced) preset, dropping us below 60 fps. Performance
    # preset keeps inference around 10 ms under load. Users with a
    # strong CPU can switch to Balanced or Quality in Settings.
    performance_preset: str = "performance"
    inference_max_dim: int | None = 320

    # Hotkey bindings (pynput-format keysym strings).
    hotkey_recenter: str = "<f9>"
    # Reserved for forward compat — pause functionality is currently
    # removed from the UI. Keeping the field so old config.toml files
    # still load cleanly and the binding can be reintroduced later.
    hotkey_pause: str = ""

    def to_dict(self) -> dict[str, object]:
        # TOML doesn't have a native "null" so we store None as 0 for the
        # downscale knob (0 reads back as "native, no downscale" via
        # from_dict). Avoids an `Optional` cell that tomli_w can't encode.
        infer_dim = self.inference_max_dim if self.inference_max_dim is not None else 0
        return {
            "last_profile": self.last_profile,
            "camera": {
                "index": self.camera_index,
                "width": self.camera_width,
                "height": self.camera_height,
            },
            "performance": {
                "preset": self.performance_preset,
                "inference_max_dim": infer_dim,
            },
            "ui": {
                "show_wizard_on_next_launch": self.show_wizard_on_next_launch,
                "always_on_top": self.always_on_top,
            },
            "system": {"start_with_windows": self.start_with_windows},
            "hotkeys": {
                "recenter": self.hotkey_recenter,
                "pause": self.hotkey_pause,
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "AppConfig":
        cam = raw.get("camera", {})
        ui = raw.get("ui", {})
        sysd = raw.get("system", {})
        hk = raw.get("hotkeys", {})
        perf = raw.get("performance", {})
        # `cast` via `or` — defaults defined on the dataclass — keep typing
        # loose since this comes from user-editable TOML.

        # inference_max_dim: 0 in the file means "native resolution, no
        # downscale" (None at runtime). Positive int means a real cap.
        infer_raw = (
            int(perf.get("inference_max_dim", 480)) if isinstance(perf, dict) else 480
        )
        infer_dim: int | None = infer_raw if infer_raw > 0 else None

        return cls(
            last_profile=str(raw.get("last_profile", "Default")),
            camera_index=int(cam.get("index", 0)) if isinstance(cam, dict) else 0,
            camera_width=int(cam.get("width", 1280)) if isinstance(cam, dict) else 1280,
            camera_height=int(cam.get("height", 720)) if isinstance(cam, dict) else 720,
            performance_preset=(
                str(perf.get("preset", "balanced")) if isinstance(perf, dict) else "balanced"
            ),
            inference_max_dim=infer_dim,
            show_wizard_on_next_launch=(
                bool(ui.get("show_wizard_on_next_launch", True))
                if isinstance(ui, dict)
                else True
            ),
            always_on_top=(
                bool(ui.get("always_on_top", False)) if isinstance(ui, dict) else False
            ),
            start_with_windows=(
                bool(sysd.get("start_with_windows", False)) if isinstance(sysd, dict) else False
            ),
            hotkey_recenter=str(hk.get("recenter", "<f9>")) if isinstance(hk, dict) else "<f9>",
            hotkey_pause=str(hk.get("pause", "")) if isinstance(hk, dict) else "",
        )


def load_app_config(path: Path | None = None) -> AppConfig:
    """Load config, falling back to defaults if missing or unparseable."""
    target = path or app_config_path()
    if not target.exists():
        return AppConfig()
    try:
        with target.open("rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return AppConfig()
    return AppConfig.from_dict(raw)


def save_app_config(config: AppConfig, path: Path | None = None) -> None:
    target = path or app_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as f:
        tomli_w.dump(config.to_dict(), f)
