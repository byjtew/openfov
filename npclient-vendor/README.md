# NPClient + TrackIR.exe vendor directory

This directory holds the C source for the three native binaries OpenFOV
ships:

- `NPClient.dll` — 32-bit, for legacy 32-bit games that load NaturalPoint's
  TrackIR API.
- `NPClient64.dll` — 64-bit, what iRacing (and most modern games) load.
- `TrackIR.exe` — minimal dummy process. Satisfies games that check for the
  `TrackIR.exe` process existence before initializing head tracking.

## Where the code came from

`npclient.c` is vendored verbatim from
[opentrack/contrib/npclient/npclient.c](https://github.com/opentrack/opentrack/blob/master/contrib/npclient/npclient.c).
That source was originally written by Michal Navratil (uglyDwarf) as part
of [linuxtrack](https://github.com/uglyDwarf/linuxtrack) and is MIT licensed
— see [LICENSE-NPCLIENT.txt](LICENSE-NPCLIENT.txt).

`NPClient.def` is OpenFOV's own; it spells out the NPCLIENT.1–21 ordinal
exports so games that bind by ordinal (rather than name) get the right
function. The ordinal numbers come from public TrackIR API convention.

`trackir.c` is a 30-line dummy program written for OpenFOV.

## Building

Requires MinGW-w64 (both 32- and 64-bit cross-compilers).

```pwsh
pwsh ./build.ps1
```

On a fresh Windows dev machine:

```pwsh
choco install -y mingw      # or:  scoop install mingw
pwsh ./build.ps1
```

On CI (`windows-latest`), MinGW-w64 is preinstalled, so the release
workflow just runs `build.ps1` directly.

Outputs go to `../resources/bin/` for Nuitka to pick up.

## What the DLL does

When a TrackIR-aware game (iRacing, MSFS, DCS, etc.) launches, it reads
`HKCU\Software\NaturalPoint\NATURALPOINT\NPClient Location` to find an
NPClient DLL, then loads it and calls `NP_GetData()` periodically. The
vendored stub opens the `FT_SharedMem` named mapping that OpenFOV writes
to, formats the pose as TrackIR's expected struct, applies the optional
per-game XOR encryption, and returns it.

OpenFOV (the parent app) writes the shared memory; the DLL reads it. There
is no IPC beyond the named mapping and a 16ms-timeout mutex.

## Why NaturalPoint's actual NPClient.dll isn't shipped

This stub provides the same exported API surface as NaturalPoint's
`NPClient.dll`, but the implementation is fully original. We never
distribute, link against, or modify NaturalPoint's own DLL. The TrackIR
API surface (function names, ordinals, calling conventions) is public
knowledge — implementing it is not infringement.

TrackIR is a trademark of NaturalPoint, Inc. OpenFOV is not affiliated
with or endorsed by NaturalPoint.
