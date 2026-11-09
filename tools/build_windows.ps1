# Build the Windows testable package: an onedir bundle plus a ZIP of that folder (spec S17).
#
# Requirements: Python 3.12, uv, and PyInstaller available through the build extra.
# Usage (from the repository root, in PowerShell):
#   tools\build_windows.ps1
#
# The artifacts land in dist\SectionLab\ and dist\SectionLab-<version>-windows.zip.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

uv sync --extra build
uv run pyinstaller --noconfirm --clean packaging/sectionlab.spec

$version = (uv run python -c "import sectionlab; print(sectionlab.__version__)").Trim()
$zip = "dist/SectionLab-$version-windows.zip"
Compress-Archive -Path "dist/SectionLab/*" -DestinationPath $zip -Force

Write-Host "Build ready: dist\SectionLab\SectionLab.exe"
Write-Host "ZIP: $zip"
