# Contributing to OpenFOV

Thanks for your interest in OpenFOV. This is a small project with a single
maintainer, so the process here is deliberately light. The notes below
should cover everything you need to get a patch landed.

If anything here is unclear or out of date, please open an issue — that's a
useful contribution on its own.

## Development setup

OpenFOV targets **Python 3.12** on Windows. The build/distribution pipeline
(Nuitka + Inno Setup) is Windows-only, and the face-tracking pipeline writes
to Windows shared memory, so a Windows dev box is strongly recommended.
Other platforms may work for editing and unit tests, but most integration
work has to happen on Windows.

```pwsh
# Clone
git clone https://github.com/epalosh/openfov.git
cd openfov

# Create and activate a virtualenv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install in editable mode with dev extras
pip install -e ".[dev]"
```

That installs the runtime dependencies (PySide6, MediaPipe, OpenCV, etc.)
plus the dev tools (`pytest`, `pytest-qt`, `ruff`, `mypy`).

To run the app from source:

```pwsh
python -m openfov
```

## Running tests

```pwsh
pytest
```

The test suite is fast and should pass cleanly on a fresh checkout. If a
test needs a webcam or game-specific I/O, it's gated behind a marker — plain
`pytest` only runs the hermetic subset.

## Code style

We use **ruff** for linting and formatting. Configuration lives in
`pyproject.toml`; there are no extra house rules on top of that.

```pwsh
ruff check .
ruff format .
```

Type hints are encouraged but not required everywhere. `mypy` is installed
as a dev dependency for spot-checking; it isn't run in CI today.

## Commit messages

Keep it simple:

- A clear, single-line summary in the imperative mood ("Fix recenter hotkey
  on Windows 11", not "Fixed recenter hotkey").
- Optional body explaining the *why* if the change isn't obvious from the
  diff. Wrap at ~72 chars.

Conventional Commits are **not** required. Don't bother with `feat:` /
`fix:` prefixes unless you want to.

## Pull requests

- Open the PR against `main`.
- CI must pass before review (it's just ruff + pytest, so this is usually
  quick).
- A single maintainer (epalosh) reviews everything. Reviews are best-effort
  and may take a few days — ping the PR if it's been quiet for over a week.
- Small, focused PRs land much faster than large ones. If you're planning
  something big, open an issue first so we can sanity-check the approach.
- If the change touches the UI, include a screenshot or short clip.

## Where help is especially welcome

- **Support for more games.** iRacing is the primary target today via the
  FreeTrack/NPClient path, but the output stack is meant to be pluggable.
  Adding clean adapters for other sims (Assetto Corsa, ACC, rFactor 2,
  MSFS, DCS, etc.) is high-value work.
- **Additional inference backends.** The MediaPipe FaceLandmarker runs on
  CPU today. OpenVINO and DirectML backends would meaningfully cut latency
  and CPU load on supported hardware. This is mostly self-contained inside
  the tracker module.
- **Bug reports with reproducible setups.** A clear repro, your hardware,
  and a snippet from `%APPDATA%\OpenFOV\openfov.log` is often enough to
  land a fix quickly. See the bug report template for what to include.

## Code of Conduct

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

OpenFOV is MIT-licensed. By submitting a contribution you agree that it
will be released under the same license.
