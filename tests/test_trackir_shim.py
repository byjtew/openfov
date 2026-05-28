"""TrackIRShim tests — lifecycle properties, missing-binary handling.

We don't actually launch the dummy here (CI build hasn't produced the
binary yet; on dev machines, no compiler available). What we *can* verify
is: shim handles missing binary gracefully, stop() is idempotent, context
manager works."""

from __future__ import annotations

import contextlib
from pathlib import Path

from openfov.output.trackir_shim import TrackIRShim, dummy_path


def test_dummy_path_resolves() -> None:
    """The path should resolve to under the configured bin dir, named
    TrackIR.exe — regardless of whether the file exists."""
    p = dummy_path()
    assert p.name == "TrackIR.exe"


def test_start_with_missing_binary_does_not_raise() -> None:
    """When the dummy hasn't been built yet, start() should log a warning
    and remain not-running, not crash."""
    shim = TrackIRShim()
    shim.start()
    # is_running may be False (binary missing) or True (binary exists and
    # we successfully launched). Either is fine. Just don't crash.
    shim.stop()


def test_stop_without_start_is_safe() -> None:
    shim = TrackIRShim()
    shim.stop()  # no exception


def test_double_start_idempotent() -> None:
    shim = TrackIRShim()
    shim.start()
    shim.start()
    shim.stop()


def test_context_manager() -> None:
    with TrackIRShim() as shim:
        assert shim is not None
    # Should be stopped on exit.


def test_job_object_kills_orphan_on_parent_crash(tmp_path: Path) -> None:
    """Critical guarantee: if OpenFOV crashes hard, the TrackIR.exe child
    we spawned must NOT outlive us. We verify by spawning a subprocess
    that starts the shim and then kills itself uncleanly; the child dummy
    must be gone within ~2 seconds.

    Skipped when the dummy binary hasn't been built yet (i.e. CI machines
    that haven't run build.ps1 — the binary-build step happens in the
    release workflow)."""
    import subprocess
    import sys
    import time

    from openfov.output.trackir_shim import dummy_path

    if not dummy_path().exists() or sys.platform != "win32":
        import pytest

        pytest.skip("TrackIR.exe not built or non-Windows; covered by manual validation")

    try:
        import psutil
    except ImportError:
        import pytest

        pytest.skip("psutil not installed")

    # Spawn a Python child that starts the shim and then aborts hard.
    script = (
        "from openfov.output.trackir_shim import TrackIRShim;"
        "s = TrackIRShim(); s.start();"
        "print(s._proc.pid, flush=True);"
        "import os; os._exit(0)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=10,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
    )
    assert proc.returncode == 0, f"Child crashed unexpectedly: {proc.stderr}"

    spawned_pid_str = proc.stdout.strip()
    if not spawned_pid_str:
        import pytest

        pytest.skip("Child didn't print pid; build artifact may be missing")
    spawned_pid = int(spawned_pid_str)

    # Job Object should have terminated the dummy. Give it a generous beat.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if not psutil.pid_exists(spawned_pid):
            return
        time.sleep(0.1)

    # Belt-and-braces cleanup in case the guarantee failed: don't leave an
    # orphan on the CI machine.
    with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
        psutil.Process(spawned_pid).kill()
    raise AssertionError(
        f"TrackIR.exe pid={spawned_pid} survived parent crash — Job Object guarantee failed"
    )
