# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows onedir build (spec S17).

Built by tools/build_windows.ps1, which also zips dist/SectionLab. Running this spec on
another platform produces a working build for that platform, which is how the packaging
is smoke tested during development.
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent
# The freeze holds the runtime, not the application: `sectionlab` is excluded here and
# shipped as `app/sectionlab` beside the executable, so an update replaces a few dozen
# kilobytes instead of the whole bundle. packaging/launcher.py bridges the two.
LAUNCHER = ROOT / "packaging" / "launcher.py"
# sectionproperties imports matplotlib (and therefore Pillow) from its analysis module, so
# both ship even though SectionLab never plots. Everything else that sectionproperties only
# needs for notebooks is excluded, together with the GUI backends no desktop build uses.
HIDDEN_IMPORTS: list[str] = ["matplotlib"]

analysis = Analysis(
    [str(LAUNCHER)],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "sectionlab",
        "pytest",
        "pytest_qt",
        "PySide6.QtWebEngineCore",
        "PySide6.Qt3DCore",
        "tkinter",
        "IPython",
        "jupyter",
        "jedi",
        "pandas",
        "xlrd",
        "matplotlib.backends.backend_tkagg",
        "matplotlib.backends.backend_gtk3",
        "matplotlib.backends.backend_gtk4",
        "matplotlib.backends.backend_wx",
        "matplotlib.backends.backend_webagg",
        "matplotlib.backends._backend_tk",
        "matplotlib.tests",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SectionLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="SectionLab",
)
