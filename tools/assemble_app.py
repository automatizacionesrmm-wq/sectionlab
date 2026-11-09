"""Ship the application code beside the frozen bundle, and as its own tiny archive.

The PyInstaller bundle freezes the runtime only (CPython, Qt, scipy, numpy, shapely): the
`sectionlab` package is excluded from the analysis and lives in `app/sectionlab` next to
the executable, where `packaging/launcher.py` finds it. That splits a release into

* the bundle and the installer, which change when a dependency does, and
* `SectionLab-<version>-code.zip`, a few dozen kilobytes that change with every edit.

Usage (after PyInstaller has produced `dist/SectionLab`):

    uv run python tools/assemble_app.py

Updates then only need the code archive extracted into `app/`.
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "sectionlab"
DIST = ROOT / "dist"
BUNDLE = DIST / "SectionLab"
IGNORED = ("__pycache__", "*.pyc", "*.pyo")


def packaged_version() -> str:
    """Read `__version__` without importing anything Qt-dependent."""
    text = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("sectionlab/__init__.py does not define __version__")


def assemble(bundle: Path, package: Path, version: str) -> tuple[Path, Path]:
    """Copy `package` into `bundle/app` and write the code archive beside `bundle`."""
    app_dir = bundle / "app"
    target = app_dir / package.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        package,
        target,
        ignore=shutil.ignore_patterns(*IGNORED),
        ignore_dangling_symlinks=True,
    )

    archive = bundle.parent / f"SectionLab-{version}-code.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle_zip:
        for path in sorted(target.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                bundle_zip.write(path, path.relative_to(app_dir).as_posix())
    return target, archive


def main() -> int:
    if not BUNDLE.is_dir():
        raise SystemExit(f"{BUNDLE} is missing: build the bundle with PyInstaller first")
    version = packaged_version()
    target, archive = assemble(BUNDLE, PACKAGE, version)
    size = archive.stat().st_size
    print(f"Application code: {target}")
    print(f"Code archive: {archive} ({size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
