"""Qt application bootstrap and main window shell.

Contains only the window shell for now; the canvas, settings and results panels are
added by their own tasks (T7, T8, T11).
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

APP_NAME = "SectionLab"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 720)
        self.setCentralWidget(QLabel(APP_NAME))


def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
