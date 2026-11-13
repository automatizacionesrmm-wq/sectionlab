"""Persistent preferences and the settings dialog (spec S3, S4)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sectionlab import __version__
from sectionlab.core.precision import DEFAULT_DECIMALS, MAX_DECIMALS, MIN_DECIMALS
from sectionlab.core.snap import SNAP_KINDS, SnapKind
from sectionlab.core.units import Unit
from sectionlab.ui import strings
from sectionlab.ui.theme import Theme

ORGANIZATION = "SectionLab"
APPLICATION = "SectionLab"

_UNIT_LABELS = {Unit.MM: "mm", Unit.CM: "cm", Unit.M: "m", Unit.IN: "in"}

_THEME_LABELS = {Theme.DARK: "theme_dark", Theme.LIGHT: "theme_light"}


def unit_label(unit: Unit) -> str:
    """Short symbol for the active unit, as shown next to every value."""
    return _UNIT_LABELS[unit]


@dataclass(frozen=True)
class AppSettings:
    """What the interface remembers between runs."""

    unit: Unit = Unit.MM
    decimals: int = DEFAULT_DECIMALS
    theme: Theme = Theme.DARK
    snaps: tuple[SnapKind, ...] = SNAP_KINDS
    grid: bool = True


def load_settings() -> AppSettings:
    store = QSettings(ORGANIZATION, APPLICATION)
    unit_text = store.value("unit", Unit.MM.value)
    try:
        unit = Unit(str(unit_text))
    except ValueError:
        unit = Unit.MM
    try:
        decimals = int(store.value("decimals", DEFAULT_DECIMALS))
    except (TypeError, ValueError):
        decimals = DEFAULT_DECIMALS
    decimals = min(max(decimals, MIN_DECIMALS), MAX_DECIMALS)
    try:
        theme = Theme(str(store.value("theme", Theme.DARK.value)))
    except ValueError:
        theme = Theme.DARK
    return AppSettings(
        unit=unit,
        decimals=decimals,
        theme=theme,
        snaps=load_snaps(store),
        grid=load_grid(store),
    )


def load_grid(store: QSettings) -> bool:
    """Whether the background grid is shown; a fresh install shows it (spec S7)."""
    if not store.contains("grid"):
        return True
    return str(store.value("grid", "true")).strip().lower() not in ("false", "0", "")


def load_snaps(store: QSettings) -> tuple[SnapKind, ...]:
    """The snap families the user left switched on (spec S13).

    An unset key keeps every family on, so a fresh install snaps like a CAD; an empty value is
    a deliberate choice and stays empty, which is how snapping gets switched off entirely.
    """
    if not store.contains("snaps"):
        return SNAP_KINDS
    stored = {part.strip() for part in str(store.value("snaps", "") or "").split(",")}
    return tuple(kind for kind in SNAP_KINDS if kind.value in stored)


def save_settings(settings: AppSettings) -> None:
    store = QSettings(ORGANIZATION, APPLICATION)
    store.setValue("unit", settings.unit.value)
    store.setValue("decimals", settings.decimals)
    store.setValue("theme", settings.theme.value)
    store.setValue("snaps", ",".join(kind.value for kind in settings.snaps))
    store.setValue("grid", "true" if settings.grid else "false")


class SettingsDialog(QDialog):
    """Choose the active unit and how many decimals the screen shows."""

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(strings.label_for("settings"))
        self._settings = settings
        self._unit = QComboBox(self)
        for unit in Unit:
            self._unit.addItem(unit_label(unit), unit.value)
        self._unit.setCurrentIndex(max(self._unit.findData(settings.unit.value), 0))

        self._decimals = QSpinBox(self)
        self._decimals.setRange(MIN_DECIMALS, MAX_DECIMALS)
        self._decimals.setValue(settings.decimals)

        self._theme = QComboBox(self)
        for theme in (Theme.DARK, Theme.LIGHT):
            self._theme.addItem(strings.label_for(_THEME_LABELS[theme]), theme.value)
        self._theme.setCurrentIndex(max(self._theme.findData(settings.theme.value), 0))

        form = QFormLayout()
        form.addRow(strings.label_for("active_unit"), self._unit)
        form.addRow(strings.label_for("decimals"), self._decimals)
        form.addRow(strings.label_for("theme"), self._theme)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(strings.label_for("apply"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            strings.label_for("cancel")
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        version = QLabel(f"{strings.label_for('version_label')} {__version__}", self)
        version.setObjectName("settings_version")

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(version)
        layout.addWidget(buttons)

    def values(self) -> AppSettings:
        return replace(
            self._settings,
            unit=Unit(self._unit.currentData()),
            decimals=self._decimals.value(),
            theme=Theme(self._theme.currentData()),
        )
