"""Frozen entry point: run the application code from the folder beside the executable.

The bundle freezes only the heavy runtime (CPython, Qt, scipy, numpy, shapely); the
`sectionlab` package is deliberately *not* frozen, so an update replaces `app/sectionlab`
(a few dozen kilobytes) instead of downloading the whole bundle again. This launcher is
what the frozen executable runs: it puts that folder first on `sys.path` and then starts
the real entry point.

Run from a source checkout it resolves the same way, to `src`, which keeps the file
testable without a frozen build.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_FOLDER = "app"


def code_root() -> Path:
    """Folder that holds the `sectionlab` package: `app` when frozen, `src` otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / APP_FOLDER
    return Path(__file__).resolve().parents[1] / "src"


def runtime_dependencies() -> list[object]:
    """Name the frozen runtime the application expects; never called.

    The analyser cannot follow the import of `sectionlab`, which happens at run time from
    `app/`, so it would otherwise freeze an executable with no Qt, scipy or shapely. These
    imports are what the graph is built from; the application imports resolve
    from `app/` when the executable starts.
    """
    import numpy  # noqa: F401
    import PySide6.QtCore  # noqa: F401
    import PySide6.QtGui  # noqa: F401
    import PySide6.QtWidgets  # noqa: F401
    import sectionproperties.analysis  # noqa: F401
    import sectionproperties.pre.geometry  # noqa: F401
    import shapely.geometry  # noqa: F401

    return []


def main(argv: list[str] | None = None) -> int:
    root = code_root()
    if not root.is_dir():
        raise SystemExit(f"SectionLab: no se encontró el código de la aplicación en {root}")
    root_text = str(root)
    if root_text in sys.path:
        sys.path.remove(root_text)
    sys.path.insert(0, root_text)

    from sectionlab.__main__ import main as app_main

    return app_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
