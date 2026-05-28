# WinGet manifest template

These three YAML files are the [WinGet](https://github.com/microsoft/winget-pkgs)
manifest for OpenFOV. Submission flow on each release:

1. Run the GitHub Release workflow. Note the installer's SHA-256 (printed
   in the workflow log, or compute locally with `Get-FileHash`).
2. Fork [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs).
3. Copy these three files (with edits — see below) into
   `manifests/e/epalosh/OpenFOV/<version>/`.
4. Open a PR. The bot validates within a few minutes; reviewers usually
   merge within 1–3 days.

## Per-release edits

In `epalosh.OpenFOV.installer.yaml`:

- `PackageVersion` — match the release tag minus the `v`.
- `InstallerUrl` — direct link to the `.exe` from the release.
- `InstallerSha256` — `(Get-FileHash openfov-x.y.z-setup.exe).Hash` in PowerShell.

In `epalosh.OpenFOV.locale.en-US.yaml` and
`epalosh.OpenFOV.yaml`:

- Update `PackageVersion` to match.

Once merged, `winget install OpenFOV` works for anyone on the latest
WinGet client. No SmartScreen warnings for WinGet installs (the
WinGet client is trusted by Windows).

## Validation locally

Before opening the PR:

```pwsh
winget validate --manifest .\manifests\e\epalosh\OpenFOV\0.9.0\
```

This catches schema errors before the bot does.
