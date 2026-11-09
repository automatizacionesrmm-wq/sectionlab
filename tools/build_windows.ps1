# Build the Windows testable package: a frozen runtime, the application code beside it,
# a ZIP of the whole folder and, when Inno Setup is installed, the installer (spec S17, S20).
#
# Requirements: Python 3.12, uv, PyInstaller through the build extra and, for the
# installer, Inno Setup 6 (ISCC.exe).
# Usage (from the repository root, in PowerShell):
#   tools\build_windows.ps1
#
# The artifacts land in dist\:
#   SectionLab\                      the runnable folder (SectionLab.exe plus _internal and app)
#   SectionLab-<version>-windows.zip  that folder, for a portable copy
#   SectionLab-<version>-code.zip     only app\sectionlab, the archive an update needs
#   SectionLab-<version>-setup.exe    the installer, which upgrades in place

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

uv sync --extra build
uv run pyinstaller --noconfirm --clean packaging/sectionlab.spec

# The runtime is frozen; the application code ships beside the executable.
uv run python tools/assemble_app.py

$version = (uv run python -c "import sectionlab; print(sectionlab.__version__)").Trim()
$zip = "dist/SectionLab-$version-windows.zip"
Compress-Archive -Path "dist/SectionLab/*" -DestinationPath $zip -Force

$iscc = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
    & $iscc "/DAppVersion=$version" "packaging\sectionlab.iss" | Out-Null
    Write-Host "Installer: dist\SectionLab-$version-setup.exe"
} else {
    Write-Warning "Inno Setup not found: the installer was skipped (install Inno Setup 6)"
}

Write-Host "Build ready: dist\SectionLab\SectionLab.exe"
Write-Host "ZIP: $zip"
