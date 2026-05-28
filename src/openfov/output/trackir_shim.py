"""TrackIR.exe dummy-process lifecycle manager.

Some games (Falcon BMS, parts of MSFS) require a process named
`TrackIR.exe` to be running before they'll initialize head tracking — even
when NPClient.dll itself loads fine. OpenFOV ships a tiny dummy executable
that just sleeps; we launch it while tracking is active and terminate it
when we stop.

If NaturalPoint's *real* TrackIR is already running (rare for users of
OpenFOV, but possible), we yield to it and don't spawn our own duplicate.

The child is placed in a Windows Job Object configured with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so even if OpenFOV crashes hard the
dummy dies with it. No orphan processes.

Cross-platform safety: on non-Windows this module becomes a no-op so
tests/CI on Linux/macOS can import freely."""

from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from openfov.output.npclient_bootstrap import bundled_bin_dir

logger = logging.getLogger(__name__)

DUMMY_NAME = "TrackIR.exe"


def _is_windows() -> bool:
    return sys.platform == "win32"


def dummy_path() -> Path:
    return bundled_bin_dir() / DUMMY_NAME


# ---------------------------------------------------------------------------
# Windows Job Object plumbing — used to guarantee the child dies with us.
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _CreateJobObjectW = _kernel32.CreateJobObjectW
    _CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _CreateJobObjectW.restype = wintypes.HANDLE

    _SetInformationJobObject = _kernel32.SetInformationJobObject
    _SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    _SetInformationJobObject.restype = wintypes.BOOL

    _AssignProcessToJobObject = _kernel32.AssignProcessToJobObject
    _AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _AssignProcessToJobObject.restype = wintypes.BOOL

    _OpenProcess = _kernel32.OpenProcess
    _OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _OpenProcess.restype = wintypes.HANDLE

    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]
    _CloseHandle.restype = wintypes.BOOL

    _JobObjectExtendedLimitInformation = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001


    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_void_p),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]


    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]


    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


    def _make_kill_on_close_job() -> wintypes.HANDLE | None:
        """Create an anonymous Job Object configured to kill its children
        when the last handle (ours) is closed. The last handle closes when
        our process exits — clean or crashed. So no orphans."""
        job = _CreateJobObjectW(None, None)
        if not job:
            logger.warning("CreateJobObject failed: err=%d", ctypes.get_last_error())
            return None
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _SetInformationJobObject(
            job, _JobObjectExtendedLimitInformation,
            ctypes.byref(info), ctypes.sizeof(info),
        )
        if not ok:
            logger.warning("SetInformationJobObject failed: err=%d", ctypes.get_last_error())
            _CloseHandle(job)
            return None
        return job


    def _assign_pid_to_job(job: wintypes.HANDLE, pid: int) -> bool:
        rights = _PROCESS_SET_QUOTA | _PROCESS_TERMINATE
        proc = _OpenProcess(rights, False, pid)
        if not proc:
            logger.warning("OpenProcess(pid=%d) failed: err=%d", pid, ctypes.get_last_error())
            return False
        try:
            ok = _AssignProcessToJobObject(job, proc)
            if not ok:
                logger.warning(
                    "AssignProcessToJobObject failed: err=%d", ctypes.get_last_error()
                )
            return bool(ok)
        finally:
            _CloseHandle(proc)


def is_external_trackir_running() -> bool:
    """True if a different (non-our) TrackIR.exe is already running.

    We can't perfectly distinguish ours from a real one by process name
    alone — both would be `TrackIR.exe`. We use the executable path: if any
    `TrackIR.exe` process is running from a directory other than our
    bundled bin dir, we consider that external."""
    if not _is_windows():
        return False
    try:
        import psutil
    except ImportError:
        # Without psutil we can't enumerate; assume nothing external.
        return False

    our_path = dummy_path().resolve()
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            name = proc.info.get("name")
            if not name or name.lower() != DUMMY_NAME.lower():
                continue
            exe = proc.info.get("exe")
            if not exe:
                continue
            if Path(exe).resolve() != our_path:
                logger.info("External TrackIR.exe already running at %s; yielding.", exe)
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return False


class TrackIRShim:
    """Manages our bundled TrackIR.exe child process.

    Lifecycle:
        shim = TrackIRShim()
        shim.start()      # spawns dummy if no external one already exists
        shim.stop()       # idempotent, terminates child cleanly
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._yielded_to_external = False
        self._job_handle: int | None = None  # Windows Job Object handle

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if not _is_windows():
            return
        if self.is_running:
            return
        if is_external_trackir_running():
            self._yielded_to_external = True
            return

        path = dummy_path()
        if not path.exists():
            logger.warning(
                "TrackIR.exe dummy missing at %s — OpenFOV install may be "
                "incomplete; some games may not initialize head tracking. "
                "Please reinstall.",
                path,
            )
            logger.debug(
                "Dev-mode hint: run npclient-vendor/build.ps1 to build the "
                "dummy binary into resources/bin/."
            )
            return

        # CREATE_NO_WINDOW (0x08000000) — even though the dummy is built
        # with -mwindows and won't show a console, this belt-and-braces
        # prevents any console flicker.
        # CREATE_SUSPENDED (0x00000004) so we can assign to a Job Object
        # before the process gets a chance to run / leak.
        try:
            self._proc = subprocess.Popen(
                [str(path)],
                creationflags=0x08000000 | 0x00000004,  # NO_WINDOW | SUSPENDED
                cwd=str(path.parent),
            )
        except OSError as exc:
            logger.error("Failed to launch TrackIR.exe: %s", exc)
            self._proc = None
            return

        # Create a Job Object configured to kill its members when the last
        # job handle closes. Our handle closes when this Python process
        # exits — clean or crashed. So the dummy can't outlive us.
        self._job_handle = _make_kill_on_close_job()
        if self._job_handle is None or not _assign_pid_to_job(self._job_handle, self._proc.pid):
            logger.warning(
                "TrackIR.exe started but Job Object setup failed; "
                "child may outlive parent on crash. pid=%s",
                self._proc.pid,
            )

        # Resume the process now that the job has its grip.
        self._resume_main_thread()
        logger.info("Launched bundled TrackIR.exe (pid %s)", self._proc.pid)

    def stop(self, timeout: float = 2.0) -> None:
        if self._proc is None:
            self._close_job()
            return
        if self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.warning("TrackIR.exe dummy didn't terminate in %.1fs; killing.", timeout)
                self._proc.kill()
                try:
                    self._proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    logger.error("TrackIR.exe still alive after kill(); leaking.")
            except OSError as exc:
                logger.warning("Error stopping TrackIR.exe: %s", exc)
        self._proc = None
        # Closing the job handle would also kill any survivors. Doing it
        # explicitly tightens timing and frees the kernel object.
        self._close_job()

    def _close_job(self) -> None:
        if self._job_handle is None or sys.platform != "win32":
            return
        _CloseHandle(self._job_handle)
        self._job_handle = None

    def _resume_main_thread(self) -> None:
        """Resume the suspended primary thread of the child. We use ctypes
        rather than introducing a new dep since this is Win32-only."""
        if sys.platform != "win32" or self._proc is None:
            return
        # _proc.pid -> open the process by id, enumerate threads via
        # CreateToolhelp32Snapshot/Thread32First. Simpler approach: use
        # NtResumeProcess via undocumented import. We avoid that.
        # Instead use a Windows API loop on TH32CS_SNAPTHREAD.
        TH32CS_SNAPTHREAD = 0x00000004
        THREAD_SUSPEND_RESUME = 0x0002

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class THREADENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
            ]

        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
        kernel32.Thread32First.restype = wintypes.BOOL
        kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
        kernel32.Thread32Next.restype = wintypes.BOOL
        kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenThread.restype = wintypes.HANDLE
        kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel32.ResumeThread.restype = wintypes.DWORD

        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if not snapshot:
            return
        try:
            entry = THREADENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Thread32First(snapshot, ctypes.byref(entry)):
                return
            target_pid = self._proc.pid
            while True:
                if entry.th32OwnerProcessID == target_pid:
                    h = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, entry.th32ThreadID)
                    if h:
                        kernel32.ResumeThread(h)
                        _CloseHandle(h)
                if not kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                    break
        finally:
            _CloseHandle(snapshot)

    def __enter__(self) -> TrackIRShim:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()


__all__ = ["DUMMY_NAME", "TrackIRShim", "dummy_path", "is_external_trackir_running"]
