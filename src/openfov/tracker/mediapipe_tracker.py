"""MediaPipe FaceLandmarker implementation of `Tracker`.

Uses MediaPipe's 478-landmark face mesh in VIDEO mode with
`output_facial_transformation_matrixes=True`. The pose comes from Google's
weighted Procrustes fit of all 478 landmarks against a canonical face — much
more stable than solvePnP on a handful of keypoints.

Threading is owned by the surrounding pipeline; this module is plain Python.
"""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision

from openfov.tracker.base import Pose6DOF, Tracker, TrackerResult, TrackerSettings

logger = logging.getLogger(__name__)

# Sparse subset of the 478 landmarks used for the UI overlay (eyes, nose,
# mouth, face oval). The pose itself uses all 478 internally.
_PREVIEW_INDICES: tuple[int, ...] = (
    1, 10, 33, 61, 152, 263, 291,
    127, 234, 356, 454, 132, 58, 288, 397, 162, 389,
    159, 145, 386, 374,
)


def _default_model_path() -> Path:
    """Resolve the bundled `face_landmarker.task` model.

    Honors the `OPENFOV_MODEL_PATH` env var for development. Otherwise
    delegates to the same resource-resolver the UI uses (`asset_path`),
    which correctly handles both dev checkouts and packaged Nuitka /
    PyInstaller builds. Before this delegation, this function used
    `Path(__file__).parents[3]` — which resolved correctly in dev but
    pointed one directory ABOVE the bundle in a Nuitka build, causing
    the famous "missing model file, please reinstall" error users hit
    in v0.1.0-rc1 even though the model was actually bundled."""

    import os

    env = os.environ.get("OPENFOV_MODEL_PATH")
    if env:
        return Path(env)
    # Local import: tracker module shouldn't pull in Qt-flavored UI
    # helpers at top level. asset_path itself has no Qt deps.
    from openfov.ui.resources import asset_path
    return asset_path("models", "face_landmarker.task")


def euler_yxz_from_matrix(rotation: np.ndarray) -> tuple[float, float, float]:
    """Tait-Bryan YXZ decomposition → (yaw, pitch, roll) in degrees.

    - yaw   = rotation about world Y (vertical) → look left/right
    - pitch = rotation about world X (horizontal) → nod up/down
    - roll  = rotation about world Z (forward) → tilt head sideways
    """
    sy = math.sqrt(rotation[0, 2] ** 2 + rotation[2, 2] ** 2)
    if sy > 1e-6:
        pitch = math.atan2(-rotation[1, 2], sy)
        yaw = math.atan2(rotation[0, 2], rotation[2, 2])
        roll = math.atan2(rotation[1, 0], rotation[1, 1])
    else:
        pitch = math.atan2(-rotation[1, 2], sy)
        yaw = math.atan2(-rotation[2, 0], rotation[0, 0])
        roll = 0.0
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


class MediaPipeTracker(Tracker):
    """Default tracker. Robust in normal seated-driver conditions."""

    def __init__(self) -> None:
        self._landmarker: mp_vision.FaceLandmarker | None = None
        self._mirror = True  # frames are mirrored for natural feel; negate yaw/roll
        # MediaPipe's VIDEO mode rejects any ts that doesn't strictly
        # increase. Our caller computes ts from `int(time.monotonic()*1000)`,
        # which can repeat when two iterations land in the same millisecond
        # (fast inference + buffered camera frame). We re-clamp every call
        # so the wrapper is robust regardless of caller behavior.
        self._last_ts_ms = -1
        # Downscale target: longest side in pixels of the frame fed to
        # MediaPipe. None disables downscaling. The pose returned is
        # rotation-only and unaffected by scale; 2D landmarks for the UI
        # overlay are rescaled back to the input frame's coordinate
        # system before returning so the camera-view widget can keep
        # drawing them on the original (un-downscaled) frame.
        self._max_inference_dim: int | None = None

    def start(self, settings: TrackerSettings) -> None:
        if self._landmarker is not None:
            return
        model_path = Path(settings.model_path) if settings.model_path else _default_model_path()
        if not model_path.exists():
            # The model is bundled by the installer. If a user sees this
            # the install is broken and they should reinstall. The env
            # var hint stays only at DEBUG-level diagnostics, not in
            # user-facing error text.
            logger.debug(
                "Model lookup failed (path=%s). Override via OPENFOV_MODEL_PATH "
                "if running from a dev checkout.", model_path,
            )
            raise FileNotFoundError(
                f"OpenFOV is missing a required model file ({model_path.name}). "
                "Please reinstall OpenFOV."
            )
        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            output_facial_transformation_matrixes=True,
            min_face_detection_confidence=settings.min_detection_confidence,
            min_face_presence_confidence=settings.min_presence_confidence,
            min_tracking_confidence=settings.min_tracking_confidence,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
        self._last_ts_ms = -1
        self._max_inference_dim = settings.max_inference_dim

    def stop(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
        self._last_ts_ms = -1

    def step(self, frame_bgr: np.ndarray, ts_ms: int) -> TrackerResult:
        if self._landmarker is None:
            raise RuntimeError("MediaPipeTracker.step() before start()")

        # Guarantee strict monotonic timestamps. If the caller hands us a
        # duplicate or backwards value, bump forward by 1 ms — MediaPipe
        # only requires `>`, not real wall-clock accuracy.
        if ts_ms <= self._last_ts_ms:
            ts_ms = self._last_ts_ms + 1
        self._last_ts_ms = ts_ms

        t0 = time.perf_counter()
        # Original frame dimensions — kept for landmark coordinate rescale
        # back to display space. The downscaled frame is used only for
        # inference and then thrown away.
        h, w = frame_bgr.shape[:2]
        inference_frame = frame_bgr
        if self._max_inference_dim is not None:
            longest = max(w, h)
            if longest > self._max_inference_dim:
                scale = self._max_inference_dim / longest
                new_w = max(1, int(round(w * scale)))
                new_h = max(1, int(round(h * scale)))
                # INTER_AREA is the right choice for downsampling — much
                # less aliasing than bilinear and only marginally slower
                # than INTER_LINEAR on small targets.
                inference_frame = cv2.resize(
                    frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA
                )
        rgb = cv2.cvtColor(inference_frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, ts_ms)
        inference_ms = (time.perf_counter() - t0) * 1000.0

        if not result.facial_transformation_matrixes or not result.face_landmarks:
            return TrackerResult(inference_ms=inference_ms)

        matrix = np.asarray(result.facial_transformation_matrixes[0], dtype=np.float64)
        yaw, pitch, roll = euler_yxz_from_matrix(matrix[:3, :3])

        # The frame is mirrored upstream so users see themselves naturally;
        # negate yaw + roll so "look right" maps to +yaw relative to the
        # on-screen image. Pitch is unaffected by the horizontal flip.
        if self._mirror:
            yaw = -yaw
            roll = -roll

        # Translation column. MediaPipe returns it in the canonical face
        # frame's units, which are roughly centimeters; we convert to mm to
        # match FreeTrack's convention.
        tx = float(matrix[0, 3]) * 10.0
        ty = float(matrix[1, 3]) * 10.0
        tz = float(matrix[2, 3]) * 10.0

        # Build sparse 2D landmark array for the UI overlay.
        face = result.face_landmarks[0]
        preview = np.array(
            [(face[i].x * w, face[i].y * h) for i in _PREVIEW_INDICES],
            dtype=np.float32,
        )

        # Confidence proxy: we don't get a unified score from MediaPipe's
        # VIDEO mode, so report 1.0 for a clean detection. A future revision
        # can derive a real score from landmark visibility.
        return TrackerResult(
            pose=Pose6DOF(yaw=yaw, pitch=pitch, roll=roll, x=tx, y=ty, z=tz),
            detected=True,
            confidence=1.0,
            landmarks_2d=preview,
            inference_ms=inference_ms,
        )
