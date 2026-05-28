#requires -Version 5
<#
.SYNOPSIS
    Build the OpenFOV Inno Setup installer (the `.exe` users download).

.DESCRIPTION
    Two-step process:

    1. Ensures the bundled Microsoft VC++ Redistributable is present at
       installer/redist/vc_redist.x64.exe. If not, downloads it from
       Microsoft's official permalink.
    2. Invokes Inno Setup Compiler (iscc.exe) against openfov.iss to
       produce Output/OpenFOV-<version>-setup.exe.

    Run AFTER build/nuitka_build.ps1 has produced dist/openfov.dist/.
    The VC++ redistributable file is intentionally not committed to git
    -- it's ~25 MB and Microsoft can update it independently of OpenFOV.

.PARAMETER ISCC
    Full path to iscc.exe. Defaults to the standard Inno Setup 6 install
    location.

.PARAMETER SkipRedistDownload
    Skip the auto-download step. Useful in CI where the file is cached
    or staged separately.

.PARAMETER Version
    Version string passed to Inno Setup via /DMyAppVersion. Defaults to
    0.1.0 -- keep in sync with pyproject.toml [project.version].
#>

[CmdletBinding()]
param(
    [string]$ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    [switch]$SkipRedistDownload,
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Robust script-dir lookup (matches the convention in nuitka_build.ps1).
$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $scriptDir) {
    $scriptDir = (Get-Location).Path
}

$root = Resolve-Path (Join-Path $scriptDir "..")
$dist = Join-Path $root "dist\openfov.dist"
$iss  = Join-Path $scriptDir "openfov.iss"
$redistDir  = Join-Path $scriptDir "redist"
$redistFile = Join-Path $redistDir "vc_redist.x64.exe"

# Sanity check the Nuitka output exists.
if (-not (Test-Path $dist)) {
    throw "Missing $dist -- run build/nuitka_build.ps1 first."
}
if (-not (Test-Path $iss)) {
    throw "Missing $iss."
}

# Ensure VC++ Redistributable is bundled. Microsoft's permalink always
# returns the latest 64-bit redist installer; size is ~25 MB.
if (-not $SkipRedistDownload) {
    if (-not (Test-Path $redistDir)) {
        New-Item -ItemType Directory -Path $redistDir | Out-Null
    }
    if (-not (Test-Path $redistFile)) {
        Write-Host "Downloading vc_redist.x64.exe from Microsoft..."
        $url = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
        # Force TLS 1.2 -- older PowerShell defaults to TLS 1.0 which
        # Microsoft's CDN no longer accepts.
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $redistFile -UseBasicParsing
        $sz = (Get-Item $redistFile).Length
        Write-Host ("  -> {0} ({1:N1} MB)" -f $redistFile, ($sz / 1MB))
    } else {
        Write-Host "Using existing $redistFile."
    }
}

# Locate ISCC.
if (-not (Test-Path $ISCC)) {
    throw "Inno Setup Compiler not found at $ISCC. Install Inno Setup 6 from https://jrsoftware.org/isdl.php or pass -ISCC <path>."
}

Write-Host ""
Write-Host "Building installer with Inno Setup..."
Write-Host "  Script:  $iss"
Write-Host "  Dist:    $dist"
Write-Host "  Redist:  $redistFile"
Write-Host "  Version: $Version"
Write-Host ""

& $ISCC "/DMyAppVersion=$Version" $iss
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup build failed (exit $LASTEXITCODE)."
}

$output = Join-Path $scriptDir "Output\OpenFOV-$Version-setup.exe"
if (Test-Path $output) {
    $size = (Get-Item $output).Length
    Write-Host ""
    Write-Host "Installer built successfully:" -ForegroundColor Green
    Write-Host ("  $output ({0:N1} MB)" -f ($size / 1MB))
}
