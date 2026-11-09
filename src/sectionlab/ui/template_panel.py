"""Template selector with parameter form (spec S10).

Parameters are typed in the active unit and converted to millimetres before the template is
built, so the stored geometry is always millimetres (spec S2).
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QTimer, Signal
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
_REBUILD_DELAY_MS = 120


class TemplatePanel(QWidget):
    """Pick a template, edit its parameters, and apply it to the drawing.

    Parametric and free-geometry modes stay separate (spec S10): the second button starts a
    new empty drawing, it never converts the current template into editable vertices.
    """

    applied = Signal(str, object)
    freeModeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._unit = Unit.MM
        self._spins: dict[str, QDoubleSpinBox] = {}
        self._mm: dict[str, float] = {}
        self._rendered: dict[str, float] = {}
        self._loading = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_REBUILD_DELAY_MS)
        self._timer.timeout.connect(self._emit_applied)

        self._kind = QComboBox(self)
        for kind in TemplateKind:
            self._kind.addItem(strings.label_for(kind.value), kind.value)
        self._kind.currentIndexChanged.connect(self._on_kind_changed)

        self._group = QGroupBox(self)
        self._form_host = QWidget(self._group)
        self._form = QFormLayout(self._form_host)
        self._form.setContentsMargins(4, 2, 4, 4)
        self._form.setSpacing(7)
        group_layout = QVBoxLayout(self._group)
        group_layout.addWidget(self._form_host)

        self._apply = QPushButton(strings.label_for("apply"), self)
        self._free = QPushButton(strings.label_for("free_mode"), self)
        self._free.setObjectName("ghost")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self._kind)
        layout.addWidget(self._group)
        layout.addWidget(self._apply)
        layout.addWidget(self._free)

        self._apply.clicked.connect(self._emit_applied)
        self._free.clicked.connect(self.freeModeRequested.emit)
        self._rebuild_form()

    def kind(self) -> str:
        return str(self._kind.currentData())

    def set_kind(self, kind: str) -> None:
        index = self._kind.findData(kind)
        if index >= 0:
            self._loading = True
            try:
                self._kind.setCurrentIndex(index)
                self._rebuild_form()
            finally:
                self._loading = False

    def set_unit(self, unit: Unit) -> None:
        """Re-render the parameter values in the new unit without touching the section."""
        self._mm = self.params()
        self._unit = unit
        self._loading = True
        try:
            for key, spin in self._spins.items():
                value = round(from_mm(self._mm[key], unit), _PARAMETER_DECIMALS)
                spin.setValue(value)
                self._rendered[key] = value
        finally:
            self._loading = False

    def set_params(self, values: Mapping[str, float]) -> None:
        """Show the given millimetre parameters."""
        self._loading = True
        try:
            for key, spin in self._spins.items():
                if key in values:
                    value = round(from_mm(float(values[key]), self._unit), _PARAMETER_DECIMALS)
                    spin.setValue(value)
                    self._mm[key] = float(values[key])
                    self._rendered[key] = value
        finally:
            self._loading = False

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
            spin.valueChanged.connect(self._schedule_apply)
            self._form.addRow(strings.label_for(param.key), spin)

    def _on_kind_changed(self) -> None:
        """Switching template redraws at once: the parameters are already valid defaults."""
        self._rebuild_form()
        if not self._loading:
            self._emit_applied()

    def _schedule_apply(self) -> None:
        if not self._loading:
            self._timer.start()

    def _emit_applied(self) -> None:
        self.applied.emit(self.kind(), self.params())
