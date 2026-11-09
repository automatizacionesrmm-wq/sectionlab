"""Background update work and the banner that announces it (specs S2, S3).

The check and the download run off the interface thread; the banner is a plain widget so the
window can be driven from tests without a modal dialog.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from sectionlab.core.update import Asset, Release, UpdateError, download, is_newer
from sectionlab.ui import strings


class UpdateChecker(QThread):
    """Ask GitHub for the newest release without stopping the interface (spec S2)."""

    offered = Signal(object)  # Release newer than the running version
    upToDate = Signal(object)  # Release, not newer than the running version
    failed = Signal(str)  # English code

    def __init__(self, fetch, current: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fetch = fetch
        self._current = current

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            release = self._fetch()
        except UpdateError as error:
            self.failed.emit(error.code)
            return
        except Exception:  # a thread must never raise into Qt
            self.failed.emit("check_failed")
            return
        if is_newer(self._current, release.version):
            self.offered.emit(release)
        else:
            self.upToDate.emit(release)


class UpdateBanner(QFrame):
    """``Hay una versión nueva 0.2.1`` with the two choices, above the drawing (spec S3)."""

    updateRequested = Signal()
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("update_banner")
        self.setVisible(False)

        self._text = QLabel(self)
        self._text.setObjectName("update_text")
        self._primary = QPushButton(strings.label_for("update_now"), self)
        self._primary.setObjectName("update_primary")
        self._later = QPushButton(strings.label_for("update_later"), self)
        self._later.setObjectName("update_later")
        for button in (self._primary, self._later):
            button.setCursor(self.cursor())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 10, 8)
        layout.setSpacing(10)
        layout.addWidget(self._text)
        layout.addStretch(1)
        layout.addWidget(self._primary)
        layout.addWidget(self._later)

        self._primary.clicked.connect(self.updateRequested.emit)
        self._later.clicked.connect(self.dismiss)

    def offer(self, version: str) -> None:
        """Show the notice for one version; does nothing else on its own."""
        self._text.setText(f"{strings.label_for('update_available')} {version}")
        self.setVisible(True)

    def dismiss(self) -> None:
        self.setVisible(False)
        self.dismissed.emit()

    def version_text(self) -> str:
        return self._text.text()

    def offer_version(self, stage: str) -> None:
        """Show what the update is doing right now, e.g. 'Descargando 0.2.1…'."""
        self._text.setText(stage)

    def set_busy(self, busy: bool) -> None:
        self._primary.setEnabled(not busy)
        self._later.setEnabled(not busy)


class UpdateDownloader(QThread):
    """Fetch one release asset without freezing the window (spec S4)."""

    ready = Signal(str)  # the file that is now on disk
    failed = Signal(str)  # English code

    def __init__(self, asset: Asset, target, opener=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._asset = asset
        self._target = target
        self._opener = opener

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            path = download(self._asset, self._target, self._opener)
        except UpdateError as error:
            self.failed.emit(error.code)
            return
        except Exception:  # a thread must never raise into Qt
            self.failed.emit("download_failed")
            return
        self.ready.emit(str(path))
