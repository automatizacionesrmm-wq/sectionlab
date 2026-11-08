"""Results panel: on-screen table, clipboard copy and CSV export.

The panel converts millimetre results into the active unit for display only (S2, S3) and
always exports full precision (S4, D5).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from sectionlab.core.engine import SectionProperties
from sectionlab.core.precision import format_full, format_value, results_to_csv
from sectionlab.core.units import Unit, from_mm, from_mm2, from_mm3, from_mm4
from sectionlab.ui import strings

_LENGTHS = frozenset(
    {
        "perimeter",
        "cx",
        "cy",
        "rx",
        "ry",
        "r1",
        "r2",
        "x_min",
        "x_max",
        "y_min",
        "y_max",
    }
)
_AREAS = frozenset({"area"})
_INERTIAS = frozenset({"ix", "iy", "ixy", "i1", "i2"})
_MODULI = frozenset({"sx", "sy"})


def convert(field: str, value: float, unit: Unit) -> float:
    """Convert one result value from millimetres into the active unit."""
    if field in _LENGTHS:
        return from_mm(value, unit)
    if field in _AREAS:
        return from_mm2(value, unit)
    if field in _INERTIAS:
        return from_mm4(value, unit)
    if field in _MODULI:
        return from_mm3(value, unit)
    return value


def format_length(value_mm: float, unit: Unit, decimals: int) -> str:
    """Format one millimetre value for the screen, in the active unit."""
    return format_value(from_mm(value_mm, unit), decimals)


def result_rows(props: SectionProperties, unit: Unit) -> list[tuple[str, float, str]]:
    """Ordered (label, value in `unit`, unit symbol) rows for every reported property."""
    rows: list[tuple[str, float, str]] = []
    for field in SectionProperties.__dataclass_fields__:
        label, symbol = strings.result_label(field)
        rows.append((label, convert(field, getattr(props, field), unit), symbol))
    return rows


class ResultsTable(QTableWidget):
    """Read-only three-column table: property, value, unit."""

    def __init__(self, parent: QTableWidget | None = None) -> None:
        super().__init__(0, 3, parent)
        self.setHorizontalHeaderLabels(
            [strings.label_for("property"), strings.label_for("value"), strings.label_for("unit")]
        )
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._props: SectionProperties | None = None
        self._unit = Unit.MM
        self.show_properties(None, Unit.MM, 2)

    def show_properties(
        self, props: SectionProperties | None, unit: Unit, decimals: int
    ) -> None:
        """Refresh the table for the given results, unit and visible decimals."""
        self._props = props
        self._unit = unit
        if props is None:
            self.setRowCount(1)
            placeholder = QTableWidgetItem(strings.label_for("no_results"))
            placeholder.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.setItem(0, 0, placeholder)
            self.setSpan(0, 0, 1, 3)
            return

        rows = result_rows(props, unit)
        self.setRowCount(len(rows))
        self.clearSpans()
        for index, (label, value, symbol) in enumerate(rows):
            self.setItem(index, 0, QTableWidgetItem(label))
            value_item = QTableWidgetItem(format_value(value, decimals))
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(index, 1, value_item)
            self.setItem(index, 2, QTableWidgetItem(symbol))

    def csv_text(self) -> str:
        """Full-precision CSV of the current results, independent of visible decimals."""
        if self._props is None:
            return ""
        rows = [
            {
                strings.label_for("property"): label,
                strings.label_for("value"): value,
                strings.label_for("unit"): symbol,
            }
            for label, value, symbol in result_rows(self._props, self._unit)
        ]
        return results_to_csv(rows)

    def copy_to_clipboard(self) -> None:
        """Copy the table as tab-separated full-precision text."""
        if self._props is None:
            return
        lines = [
            "\t".join([label, format_full(value), symbol])
            for label, value, symbol in result_rows(self._props, self._unit)
        ]
        QGuiApplication.clipboard().setText("\n".join(lines))
