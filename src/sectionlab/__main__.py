"""Application entry point."""

from __future__ import annotations

import sys

from sectionlab import __version__

USAGE = "SectionLab: propiedades geométricas de secciones transversales"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(argument in {"-h", "--help"} for argument in args):
        print(USAGE)
        return 0
    if any(argument in {"-V", "--version"} for argument in args):
        print(f"SectionLab {__version__}")
        return 0
    if "--self-test" in args:
        return _self_test()

    from sectionlab.ui.app import run

    return run([sys.argv[0], *args] if sys.argv else None)


def _self_test() -> int:
    """Prove the bundled solver works without starting the interface."""
    from sectionlab.core.engine import calculate
    from sectionlab.core.templates import TemplateKind, build_section

    properties = calculate(build_section(TemplateKind.RECTANGLE))
    print(f"area={properties.area:.6f}")
    print(f"ix={properties.ix:.6f}")
    return 0 if abs(properties.area - 20_000.0) < 1e-6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
