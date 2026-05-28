# Security

OpenFOV is open-source software released as-is under the MIT license.
This file isn't a service contract — it's a guide for people who find
something concerning and aren't sure how to report it.

## What OpenFOV touches

So you know what surface area we're talking about:

- **Your webcam.** Captured frames are processed in-memory and never
  written to disk by default. No frames are sent over the network.
- **A Windows registry key:** `HKCU\Software\NaturalPoint\NATURALPOINT\NPClient Location`.
  Per-user, written on first launch. Points games at OpenFOV's bundled
  `NPClient.dll` so they can read head pose. Removed on uninstall (or
  overwritten if you install another TrackIR-compatible app later).
- **A Windows named shared-memory section** (`FT_SharedMem`) and a
  named mutex (`FT_Mutext`) — the standard FreeTrack interface that
  any game expecting head tracking reads from. Per-session, cleaned up
  on exit.
- **A small bundled `TrackIR.exe` dummy process** that some games check
  for. Launched while OpenFOV is running, killed via a Windows Job
  Object when OpenFOV exits or crashes (no orphans).
- **`%APPDATA%\OpenFOV\` for config + profiles** (TOML files). Left
  intact across uninstalls unless you delete it manually.
- **`%LOCALAPPDATA%\OpenFOV\openfov.lock`** for single-instance
  enforcement.

OpenFOV does **not** require admin rights, does **not** install any
system-wide drivers, and does **not** make any outbound network
connections.

## How to report something

If you spot a vulnerability — anything from a path-traversal bug to a
suspicious dependency to a credential leak — email
**epalosh@icloud.com** with:

- A short description of what you found.
- Steps to reproduce, or a proof-of-concept.
- The OpenFOV version (visible in **Help → About**, or check the
  installer filename / Releases page).

Please don't open a public GitHub issue for security problems until
the fix has shipped. A heads-up via email gives users time to update
before the details are public.

## What to expect

- I'll try to acknowledge reports within about a week. This is a side
  project, so timing isn't guaranteed.
- For genuine issues I'll work on a fix and credit you in the release
  notes (unless you'd rather stay anonymous).
- For things that turn out to be intentional behavior (or out of
  scope) I'll explain why in the reply.

There's no formal bug bounty — just thanks, credit, and a more secure
project. Reporters acting in good faith won't get any legal pushback
from the project for the act of reporting.

## Out of scope

These are things people sometimes flag that aren't security bugs in
OpenFOV itself:

- **SmartScreen warnings on unsigned builds** — expected until the
  SignPath Foundation OSS certificate is in place. The README and
  install docs cover the bypass.
- **MediaPipe / OpenCV / Qt vulnerabilities** — please report upstream
  to those projects. OpenFOV will pick up fixes when we update the
  pinned versions.
- **Antivirus false positives** — packed Python binaries (Nuitka) are
  unfortunately a common false-positive trigger. If you suspect a true
  positive, send the VirusTotal link in your report.

Thanks for helping keep OpenFOV trustworthy.
