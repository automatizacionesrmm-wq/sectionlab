"""Application entry point."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from sectionlab.ui.app import run

    return run(sys.argv if argv is None else argv)
