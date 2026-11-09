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
    ok = abs(properties.area - 20_000.0) < 1e-6
    report = f"area={properties.area:.6f}\nix={properties.ix:.6f}"
    if sys.stdout is None:  # windowed executable: no console to print to
        _report_without_console(report, ok)
    else:
        print(report)
    return 0 if ok else 1


def _report_without_console(report: str, ok: bool) -> None:
    """Show the self-test result in a dialog, for the console-less Windows build."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    application = QApplication.instance() or QApplication([])
    verdict = "Prueba correcta" if ok else "Prueba fallida"
    box = QMessageBox()
    box.setWindowTitle(f"SectionLab {__version__}")
    box.setIcon(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Critical)
    box.setText(verdict)
    box.setInformativeText(report)
    box.exec()
    application.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
