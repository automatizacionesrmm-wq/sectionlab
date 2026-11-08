"""Template selector with parameter form (spec S10).

Parameters are typed in the active unit and converted to millimetres before the template is
built, so the stored geometry is always millimetres (spec S2).
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sectionlab.core.templates import TemplateKind, default_params, parameters
from sectionlab.core.units import Unit, from_mm, to_mm
from sectionlab.ui import strings

_PARAMETER_DECIMALS = 3


class TemplatePanel(QWidget):
    """Pick a template, edit its parameters, and apply it to the drawing."""

    applied = Signal(str, object)
    convertRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._unit = Unit.MM
        self._spins: dict[str, QDoubleSpinBox] = {}
        self._mm: dict[str, float] = {}
        self._rendered: dict[str, float] = {}

        self._kind = QComboBox(self)
        for kind in TemplateKind:
            self._kind.addItem(strings.label_for(kind.value), kind.value)
        self._kind.currentIndexChanged.connect(self._rebuild_form)

        self._group = QGroupBox(strings.label_for("template_mode"), self)
        self._form_host = QWidget(self._group)
        self._form = QFormLayout(self._form_host)
        self._form.setContentsMargins(0, 0, 0, 0)
        group_layout = QVBoxLayout(self._group)
        group_layout.addWidget(self._form_host)

        self._apply = QPushButton(strings.label_for("template_mode"), self)
        self._apply.setText(strings.label_for("apply"))

        self._convert = QPushButton(strings.label_for("free_mode"), self)
        self._convert.setText(strings.label_for("free_mode"))

        layout = QVBoxLayout(self)
        layout.addWidget(self._kind)
        layout.addWidget(self._group)
        layout.addWidget(self._apply)
        layout.addWidget(self._convert)

        self._apply.clicked.connect(self._emit_applied)
        self._convert.clicked.connect(self.convertRequested.emit)
        self._rebuild_form()

    def kind(self) -> str:
        return str(self._kind.currentData())

    def set_kind(self, kind: str) -> None:
        index = self._kind.findData(kind)
        if index >= 0:
            self._kind.setCurrentIndex(index)

    def set_unit(self, unit: Unit) -> None:
        """Re-render the parameter values in the new unit without touching the section."""
        self._mm = self.params()
        self._unit = unit
        for key, spin in self._spins.items():
            value = round(from_mm(self._mm[key], unit), _PARAMETER_DECIMALS)
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
            self._rendered[key] = value

    def set_params(self, values: Mapping[str, float]) -> None:
        """Show the given millimetre parameters."""
        for key, spin in self._spins.items():
            if key in values:
                value = round(from_mm(float(values[key]), self._unit), _PARAMETER_DECIMALS)
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
                self._mm[key] = float(values[key])
                self._rendered[key] = value

    def params(self) -> dict[str, float]:
        """The typed parameters, in millimetres.

        Untouched fields keep the millimetre value they were built from, so switching units
        back and forth never accumulates rounding drift.
        """
        values: dict[str, float] = {}
        for key, spin in self._spins.items():
            if key in self._mm and self._rendered.get(key) == spin.value():
                values[key] = self._mm[key]
            else:
                values[key] = to_mm(spin.value(), self._unit)
        return values

    def _rebuild_form(self) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._spins = {}
        self._mm = {}
        self._rendered = {}
        kind = TemplateKind(self.kind())
        defaults = default_params(kind)
        for param in parameters(kind):
            spin = QDoubleSpinBox(self._form_host)
            spin.setDecimals(_PARAMETER_DECIMALS)
            spin.setRange(param.minimum if param.minimum > 0 else -1e6, 1e6)
            spin.setSingleStep(1.0)
            value = round(from_mm(defaults[param.key], self._unit), _PARAMETER_DECIMALS)
            spin.setValue(value)
            self._spins[param.key] = spin
            self._mm[param.key] = defaults[param.key]
            self._rendered[param.key] = value
            self._form.addRow(strings.label_for(param.key), spin)

    def _emit_applied(self) -> None:
        self.applied.emit(self.kind(), self.params())
