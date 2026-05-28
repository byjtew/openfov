"""Pipeline thread.

Owns the capture loop end-to-end:

    Camera ─▶ Tracker ─▶ One Euro filter ─▶ Axis mapper ─▶ OutputManager
                              │
                              └──▶ UI (via Qt signals)

Runs on a dedicated QThread so the Qt main thread stays responsive even
if MediaPipe inference takes longer than a single UI tick.

Settings updates (sensitivity, invert, filter params, curve, neutral
recenter) come in via threadsafe methods that mutate the next iteration's
state — no Qt slot wiring required.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QThread, Signal

from openfov.filtering.pipeline import AxisFilterParams, PerAxisFilters
from openfov.mapping.axis_mapper import AxisMapper, AxisSettings
from openfov.output.manager import GameOutputProfile, OutputManager
from openfov.runtime.camera import CameraSource
from openfov.tracker.base import Pose6DOF, Tracker, TrackerSettings

logger = logging.getLogger(__name__)


def _bump_thread_priority(thread: threading.Thread) -> None:
    """Bump a Python `threading.Thread` to HIGH priority on Windows.

    Python's `threading` doesn't expose OS thread priority; we go
    through SetThreadPriority via ctypes. Best-effort — failure is
    logged at debug level and the thread keeps running at default
    priority. The point is to keep the camera-reader thread from
    losing scheduler contests with iRacing's render thread when the
    game pegs the CPU/GPU."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        # ident is set after start(); fall back to native_id when present.
        thread_id = getattr(thread, "native_id", None) or thread.ident
        if thread_id is None:
            return
        OpenThread = kernel32.OpenThread
        OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        OpenThread.restype = wintypes.HANDLE
        SetThreadPriority = kernel32.SetThreadPriority
        SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        SetThreadPriority.restype = wintypes.BOOL
        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL
        THREAD_SET_INFORMATION = 0x0020
        THREAD_QUERY_INFORMATION = 0x0040
        THREAD_PRIORITY_ABOVE_NORMAL = 1
        h = OpenThread(
            THREAD_SET_INFORMATION | THREAD_QUERY_INFORMATION,
            False,
            thread_id,
        )
        if not h:
            return
        try:
            SetThreadPriority(h, THREAD_PRIORITY_ABOVE_NORMAL)
        finally:
            CloseHandle(h)
    except Exception as exc:
        logger.debug("Could not raise thread priority: %s", exc)


class _FrameSlot:
    """Single-slot threadsafe frame buffer with "latest wins" semantics.

    The reader thread `put()`s freshly-read frames. If the consumer
    hasn't `take()`n the previous one yet, the new frame overwrites it
    — we never want stale frames sitting in a queue while the camera
    keeps delivering new ones. This is the right policy for live video:
    iRacing only cares about the most recent pose, not the backlog.
    """

    __slots__ = ("_event", "_frame", "_lock")

    def __init__(self) -> None:
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._event = threading.Event()

    def put(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frame = frame
            self._event.set()

    def take(self, timeout: float | None = None) -> np.ndarray | None:
        """Wait up to `timeout` seconds for a frame; return it and clear
        the slot. Returns None on timeout."""
        if not self._event.wait(timeout):
            return None
        with self._lock:
            frame = self._frame
            self._frame = None
            self._event.clear()
        return frame

    def clear(self) -> None:
        with self._lock:
            self._frame = None
            self._event.clear()


class _CameraReader(threading.Thread):
    """Background thread that reads frames from the camera as fast as
    the device delivers them and posts each to a `_FrameSlot`.

    Why a separate thread: `cv2.VideoCapture.read()` blocks the calling
    thread for up to one frame interval (16 ms @ 60 fps, 33 ms @ 30 fps).
    Running it inline with MediaPipe inference means the two stages
    serialize and add their latencies — they should run in parallel.

    The reader does NOT own the camera lifecycle. The main pipeline
    thread is still responsible for opening/closing/reopening (so the
    existing hot-plug retry logic stays in one place). When the camera
    is closed, the reader idles harmlessly until it's reopened.

    `get_camera` is a callable returning the *current* CameraSource so
    that set_camera_index() can swap the device without rebuilding the
    reader thread. The reader reads through the callable on every
    iteration, picking up the new device transparently.
    """

    def __init__(
        self,
        get_camera,
        slot: _FrameSlot,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="OpenFOV-CameraReader", daemon=True)
        self._get_camera = get_camera
        self._slot = slot
        self._stop = stop_event
        # Main thread reads these for hot-plug detection + perf telemetry.
        # No lock — int reads/writes are atomic in CPython; a stale value
        # by one frame doesn't matter for either use case.
        self.consecutive_fails = 0
        self.last_read_ms = 0.0

    def run(self) -> None:
        while not self._stop.is_set():
            cam = self._get_camera()
            if cam is None or not cam.is_open:
                # Wait for the main thread to reopen the device.
                self._stop.wait(0.05)
                continue
            t0 = time.perf_counter()
            try:
                ok, frame = cam.read()
            except Exception as exc:
                logger.debug("Reader thread camera.read raised: %s", exc)
                ok, frame = False, None
            if not ok or frame is None:
                self.consecutive_fails += 1
                # Tiny back-off so we don't spin if the device is dead.
                self._stop.wait(0.005)
                continue
            self.consecutive_fails = 0
            self.last_read_ms = (time.perf_counter() - t0) * 1000.0
            self._slot.put(frame)


@dataclass
class PipelineStats:
    fps: float = 0.0
    inference_ms: float = 0.0
    detected: bool = False
    camera_connected: bool = True

    # Per-stage timings (rolling average, ms). Surfaced for the
    # "where is my time going?" diagnostic question. With pipelining,
    # `read_ms` happens on the reader thread in parallel with
    # inference — so the *effective* per-cycle cost is roughly
    # max(read_ms, inference_ms), not the sum.
    read_ms: float = 0.0
    # Time the main thread spent waiting for a frame to arrive in the
    # slot. High wait_ms → inference is finishing faster than the
    # camera produces frames (you're capture-bound). Near-zero wait_ms
    # → inference is the bottleneck.
    wait_ms: float = 0.0


class PipelineThread(QThread):
    """Background head-tracking pipeline.

    Signals (all emitted from the worker thread; UI connects with
    `Qt.QueuedConnection`):

    - `frame_ready(np.ndarray BGR, np.ndarray|None landmarks_2d)` — every
      tracker frame, regardless of detection state. Subscribers use this
      for the live preview overlay.
    - `pose_ready(Pose6DOF raw, Pose6DOF mapped, PipelineStats stats)` —
      every frame after the tracker has run. `raw` is pre-mapping (used
      by the 3D widget so it shows tracker output, not what the curves
      have done to it). `mapped` is what we wrote to FT_SharedMem.
    - `camera_status(bool, str)` — emitted whenever the camera transitions
      between connected and disconnected. Surface this to the UI status
      bar (the pipeline keeps retrying automatically).
    - `error(str)` — fatal pipeline error; the thread is about to exit.
    """

    frame_ready = Signal(object, object)
    pose_ready = Signal(object, object, object)
    camera_status = Signal(bool, str)
    error = Signal(str)

    # Hot-plug tunables. We treat ~0.5s of read failures as "disconnected"
    # and then attempt reopens on the device every retry interval (with a
    # cap so we don't burn CPU on a permanently-missing camera).
    _DISCONNECT_AFTER_FAILS = 15
    _RETRY_INTERVAL_S = 0.5
    _MAX_RETRY_INTERVAL_S = 5.0

    # UI-update throttle. The pipeline produces poses as fast as MediaPipe
    # can run (50-80 Hz typical). The UI doesn't need that — repainting at
    # ~30 Hz is plenty. Skipping the emit when we just emitted prevents
    # the Qt event queue from backing up with 2.8 MB BGR frames.
    _UI_EMIT_INTERVAL_S = 1.0 / 30.0

    def __init__(
        self,
        tracker: Tracker,
        output: OutputManager,
        camera_index: int = 0,
        camera_width: int = 1280,
        camera_height: int = 720,
        inference_max_dim: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tracker = tracker
        self._output = output
        self._camera = CameraSource(index=camera_index, width=camera_width, height=camera_height)
        self._inference_max_dim = inference_max_dim

        self._filters = PerAxisFilters()
        self._mapper = AxisMapper()

        # Neutral calibration — set by the first detection or on F9/recenter.
        self._neutral: tuple[float, float, float, float, float, float] | None = None
        self._recenter_requested = False
        self._paused = False
        self._running = False

        # Optional game-output profile. None means write to FT_SharedMem
        # with GameID=0 (game-agnostic).
        self._game_output: GameOutputProfile | None = None

        # Hot-plug state.
        self._consecutive_fails = 0
        self._camera_was_connected = False
        self._retry_backoff_s = self._RETRY_INTERVAL_S
        self._last_retry_at = 0.0

        # UI emit throttle state.
        self._last_ui_emit_at = 0.0

    # -- thread-safe control surface ----------------------------------

    def request_recenter(self) -> None:
        """Capture the next frame's raw pose as the new neutral."""
        self._recenter_requested = True

    def set_neutral(self, pose: Pose6DOF) -> None:
        """Set the neutral pose directly (used by the setup wizard, which
        captures it during calibration). The pipeline applies it from the
        next frame onward; no recenter is needed."""
        self._neutral = (
            pose.yaw, pose.pitch, pose.roll, pose.x, pose.y, pose.z,
        )
        self._recenter_requested = False
        self._filters.reset()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def stop(self) -> None:
        self._running = False

    def set_camera_index(self, index: int) -> None:
        """Switch cameras. Takes effect on the next iteration; the worker
        closes and reopens the device under the hood."""
        # Closing here is safe even if the worker thread is currently
        # blocked in read() — OpenCV releases cleanly.
        self._camera.close()
        self._camera = CameraSource(
            index=index, width=self._camera.width, height=self._camera.height
        )
        # Reset failure counters so the new device gets a fair chance.
        self._consecutive_fails = 0
        self._retry_backoff_s = self._RETRY_INTERVAL_S

    def update_axis_settings(self, axis: str, settings: AxisSettings) -> None:
        self._mapper.update(axis, settings)

    def update_filter_params(self, axis: str, params: AxisFilterParams) -> None:
        self._filters.update_params(axis, params)

    def set_game_output(self, profile: GameOutputProfile | None) -> None:
        self._game_output = profile
        if profile is not None:
            self._output.set_game(profile)

    # -- main loop -----------------------------------------------------

    def run(self) -> None:
        # Initial open is best-effort: if the camera isn't present at startup
        # we still launch the pipeline and let the hot-plug retry loop pick
        # it up when the user plugs it in. Only the tracker/output failing
        # is fatal.
        camera_initially_open = self._camera.open()
        if camera_initially_open:
            self._camera_was_connected = True
            self.camera_status.emit(True, f"Camera {self._camera.index} connected")
        else:
            self.camera_status.emit(
                False,
                f"Camera {self._camera.index} not available - will retry",
            )

        try:
            self._tracker.start(
                TrackerSettings(max_inference_dim=self._inference_max_dim)
            )
        except Exception as exc:
            self._camera.close()
            self.error.emit(f"Tracker init failed: {exc}")
            return

        self._output.start()
        if self._game_output is not None:
            self._output.set_game(self._game_output)
        if camera_initially_open:
            actual_w, actual_h = self._camera.actual_size
            self._output.set_camera_dimensions(actual_w, actual_h)

        self._running = True
        t0 = time.monotonic()
        frame_count = 0
        stats_window_start = t0
        stats_window_frames = 0
        last_inference_ms = 0.0

        # Rolling averages for per-stage telemetry. Updated every cycle;
        # printed via a periodic INFO log so users can see where time
        # is going. Simple EMA (alpha=0.1) gives a smooth-ish ~10-frame
        # window without keeping a history buffer.
        avg_read_ms = 0.0
        avg_wait_ms = 0.0
        avg_infer_ms = 0.0
        last_diag_log_at = t0

        # Bump the pipeline thread's OS priority. Under heavy iRacing
        # GPU/CPU load the default Normal priority loses scheduler
        # contests with the game's render thread, which is what causes
        # the "44 fps when gaming, 60 fps idle" behavior. HighPriority
        # gives the inference loop a tighter time budget without
        # starving anything (we're <10% CPU even at 60 Hz).
        try:
            self.setPriority(QThread.HighPriority)
        except (AttributeError, RuntimeError) as exc:
            logger.debug("setPriority(High) failed: %s", exc)

        # Spin up the reader thread. It runs as long as the pipeline
        # does and tries to keep `_frame_slot` populated with the latest
        # camera frame. Inference runs here in the main pipeline thread
        # and overlaps with the next camera read in the background.
        # The reader looks up `self._camera` dynamically via the lambda
        # so set_camera_index() swaps cleanly without rebuilding it.
        frame_slot = _FrameSlot()
        reader_stop = threading.Event()
        reader = _CameraReader(lambda: self._camera, frame_slot, reader_stop)
        reader.start()
        _bump_thread_priority(reader)
        # Snapshot the writer's commit/drop counters so we can compute
        # the *delta* per 5-second diagnostic window — gives the user
        # the actual write rate, separate from inference rate.
        ft_writer = self._output._writer
        last_commits = ft_writer.writes_committed
        last_drops = ft_writer.writes_dropped

        try:
            while self._running:
                # ----------------- hot-plug retry path -------------------
                if not self._camera.is_open:
                    now = time.monotonic()
                    if now - self._last_retry_at >= self._retry_backoff_s:
                        self._last_retry_at = now
                        # CameraSource.open() catches OpenCV errors and
                        # returns False, but defend against anything else
                        # that escapes — a transient camera glitch must
                        # never kill the pipeline thread.
                        try:
                            opened = self._camera.open()
                        except Exception as exc:
                            logger.warning(
                                "Camera reopen attempt raised: %s — will retry",
                                exc,
                            )
                            opened = False
                        if opened:
                            self._consecutive_fails = 0
                            self._retry_backoff_s = self._RETRY_INTERVAL_S
                            self._camera_was_connected = True
                            actual_w, actual_h = self._camera.actual_size
                            self._output.set_camera_dimensions(actual_w, actual_h)
                            self.camera_status.emit(
                                True, f"Camera {self._camera.index} reconnected"
                            )
                            self._filters.reset()
                            self._neutral = None  # force recenter on first detection
                            frame_slot.clear()  # discard stale frame
                            reader.consecutive_fails = 0
                        else:
                            # Exponential-ish backoff up to a ceiling.
                            self._retry_backoff_s = min(
                                self._retry_backoff_s * 1.5,
                                self._MAX_RETRY_INTERVAL_S,
                            )
                    # Still no camera — emit an empty stats frame so the UI
                    # status bar updates, then idle briefly.
                    self.pose_ready.emit(
                        Pose6DOF(),
                        Pose6DOF(),
                        PipelineStats(
                            fps=0.0,
                            inference_ms=last_inference_ms,
                            detected=False,
                            camera_connected=False,
                        ),
                    )
                    QThread.msleep(80)
                    continue

                # ----------------- normal frame path ---------------------
                # Wait for a fresh frame from the reader thread. The slot
                # always holds the most recent frame; if the camera is
                # delivering faster than inference can consume, older
                # frames are dropped automatically (good — we want fresh
                # data in iRacing, not a backlog).
                t_wait_start = time.perf_counter()
                frame = frame_slot.take(timeout=0.1)
                wait_ms = (time.perf_counter() - t_wait_start) * 1000.0

                if frame is None:
                    # No frame in 100 ms. Either the camera is briefly
                    # paused or it's gone. Check the reader's failure
                    # counter; if it's high, treat as disconnected and
                    # let the retry path above try to reopen.
                    if reader.consecutive_fails >= self._DISCONNECT_AFTER_FAILS:
                        if self._camera_was_connected:
                            self.camera_status.emit(
                                False,
                                f"Camera {self._camera.index} disconnected - retrying",
                            )
                            self._camera_was_connected = False
                        self._camera.close()
                        reader.consecutive_fails = 0
                        self._retry_backoff_s = self._RETRY_INTERVAL_S
                        self._last_retry_at = time.monotonic()
                    # Otherwise just spin — the reader will populate the
                    # slot soon.
                    continue

                ts_ms = int((time.monotonic() - t0) * 1000)
                try:
                    result = self._tracker.step(frame, ts_ms)
                except Exception as exc:
                    # A single bad frame (corrupt buffer, transient
                    # MediaPipe hiccup) shouldn't kill the worker. Log
                    # once per second at most, then continue.
                    now_log = time.monotonic()
                    if now_log - getattr(self, "_last_step_err_at", 0.0) > 1.0:
                        logger.warning("Tracker step skipped this frame: %s", exc)
                        self._last_step_err_at = now_log
                    continue
                last_inference_ms = result.inference_ms

                # Rolling averages for the diagnostic log. EMA alpha=0.1
                # ≈ 10-frame window — smooth enough to be readable, fast
                # enough to react when the user changes presets.
                avg_read_ms = avg_read_ms * 0.9 + reader.last_read_ms * 0.1
                avg_wait_ms = avg_wait_ms * 0.9 + wait_ms * 0.1
                avg_infer_ms = avg_infer_ms * 0.9 + last_inference_ms * 0.1

                raw_pose = result.pose
                mapped_pose = Pose6DOF()

                if result.detected:
                    if self._recenter_requested or self._neutral is None:
                        self._neutral = (
                            raw_pose.yaw, raw_pose.pitch, raw_pose.roll,
                            raw_pose.x, raw_pose.y, raw_pose.z,
                        )
                        self._recenter_requested = False
                        self._filters.reset()

                    nx_yaw, nx_pitch, nx_roll, nx_x, nx_y, nx_z = self._neutral
                    neutralized = Pose6DOF(
                        yaw=raw_pose.yaw - nx_yaw,
                        pitch=raw_pose.pitch - nx_pitch,
                        roll=raw_pose.roll - nx_roll,
                        x=raw_pose.x - nx_x,
                        y=raw_pose.y - nx_y,
                        z=raw_pose.z - nx_z,
                    )
                    smoothed = self._filters(neutralized)
                    mapped_pose = self._mapper(smoothed)

                    if not self._paused:
                        self._output.write(mapped_pose)

                # Stats: update fps every ~0.5s.
                frame_count += 1
                stats_window_frames += 1
                now = time.monotonic()
                elapsed = now - stats_window_start
                if elapsed >= 0.5:
                    fps = stats_window_frames / elapsed
                    stats_window_start = now
                    stats_window_frames = 0
                else:
                    fps = stats_window_frames / max(elapsed, 1e-6)

                stats = PipelineStats(
                    fps=fps,
                    inference_ms=last_inference_ms,
                    detected=result.detected,
                    camera_connected=True,
                    read_ms=avg_read_ms,
                    wait_ms=avg_wait_ms,
                )

                # Diagnostic perf log every 5 seconds. Surfaces the
                # bottleneck so we can answer "why isn't this 60 fps?"
                # without instrumenting from scratch. Single INFO line
                # so it doesn't flood the log.
                if now - last_diag_log_at >= 5.0:
                    interval = now - last_diag_log_at
                    last_diag_log_at = now
                    # Delta against the last sample → writes/sec for the
                    # interval. `commits` = poses that actually landed
                    # in FT_SharedMem (and that iRacing would have seen
                    # an update for). `dropped` = mutex contention with
                    # iRacing's read — high drop rate means we should
                    # investigate the writer further.
                    commits_now = ft_writer.writes_committed
                    drops_now = ft_writer.writes_dropped
                    commit_rate = (commits_now - last_commits) / interval
                    drop_rate = (drops_now - last_drops) / interval
                    last_commits = commits_now
                    last_drops = drops_now
                    # DEBUG, not INFO — this fires every 5 seconds for the
                    # life of the pipeline and would dominate a normal user's
                    # logs. Devs / perf investigations flip the logger to
                    # DEBUG to see it.
                    logger.debug(
                        "perf: %.1f fps  read=%.1fms  wait=%.1fms  "
                        "inference=%.1fms  out_writes=%.1f/s  out_drops=%.1f/s",
                        fps, avg_read_ms, avg_wait_ms, avg_infer_ms,
                        commit_rate, drop_rate,
                    )

                # Throttle UI emissions. The output writer above ran every
                # tracker frame; the UI only needs ~30 Hz, and emitting at
                # full inference rate (50-80 Hz) backs up the Qt event
                # queue with 2.8 MB BGR frames the painter can't drain.
                if (now - self._last_ui_emit_at) >= self._UI_EMIT_INTERVAL_S:
                    self._last_ui_emit_at = now
                    self.frame_ready.emit(frame, result.landmarks_2d)
                    self.pose_ready.emit(raw_pose, mapped_pose, stats)
        except Exception as exc:
            logger.exception("Pipeline thread crashed")
            self.error.emit(f"Pipeline error: {exc}")
        finally:
            # Stop the reader before the camera so it doesn't try to
            # read() from a closed device.
            reader_stop.set()
            reader.join(timeout=1.0)
            self._tracker.stop()
            self._camera.close()
            self._output.stop()


# Re-export commonly needed types so callers don't need to import from
# three packages.
__all__ = [
    "AxisFilterParams",
    "AxisSettings",
    "GameOutputProfile",
    "PipelineStats",
    "PipelineThread",
]
