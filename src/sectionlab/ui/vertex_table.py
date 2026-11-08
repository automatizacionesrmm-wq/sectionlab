"""Vertex table: the typed list of vertices shown next to the canvas (spec S7).

Coordinates are always edited in the active unit and converted to millimetres before the
edit leaves this widget (spec S2).
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from sectionlab.core.model import Contour, Section
from sectionlab.core.precision import format_value
from sectionlab.core.units import Unit, from_mm, to_mm
from sectionlab.ui import strings

OUTER = "outer"
INNER = "inner"
_COLUMNS = 4


def parse_coordinate(text: str, unit: Unit) -> float:
    """Read one typed coordinate in the active unit and return millimetres."""
    normalized = text.strip().replace(",", ".")
    return to_mm(float(normalized), unit)


class VertexTable(QTableWidget):
    """Read-write list of every vertex, with unit-aware edition."""

    vertexEdited = Signal(str, int, float, float)
    vertexActivated = Signal(str, int)

    def __init__(self, parent: QTableWidget | None = None) -> None:
        super().__init__(0, _COLUMNS, parent)
        self.setHorizontalHeaderLabels(
            [
                strings.label_for("contour"),
                strings.label_for("index"),
                "X",
                "Y",
            ]
        )
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, _COLUMNS):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        self._section = Section(outer=Contour(points=[]))
        self._rows: list[tuple[str, int]] = []
        self._unit = Unit.MM
        self._decimals = 2
        self._loading = False
        self.itemChanged.connect(self._on_item_changed)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def show_section(self, section: Section, unit: Unit, decimals: int) -> None:
        """Rebuild every row from the section, in the given unit and precision."""
        self._section = section
        self._unit = unit
        self._decimals = decimals
        self._loading = True
        try:
            self.setRowCount(0)
            self._rows = []
            for name, contour in ((OUTER, section.outer), (INNER, section.inner)):
                if contour is None:
                    continue
                label = strings.label_for(
                    "outer_contour" if name == OUTER else "inner_contour"
                )
                for index, point in enumerate(contour.points):
                    row = self.rowCount()
                    self.insertRow(row)
                    self._rows.append((name, index))
                    name_item = QTableWidgetItem(label)
                    name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    self.setItem(row, 0, name_item)
                    index_item = QTableWidgetItem(str(index + 1))
                    index_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    self.setItem(row, 1, index_item)
                    self.setItem(row, 2, QTableWidgetItem(format_value(from_mm(point.x, unit), decimals)))
                    self.setItem(row, 3, QTableWidgetItem(format_value(from_mm(point.y, unit), decimals)))
        finally:
            self._loading = False

    def values(self) -> list[tuple[str, int]]:
        """Vertex keys, in display order."""
        return list(self._rows)

    def select_vertex(self, contour: str, index: int) -> bool:
        """Select the row of one vertex; returns False when that vertex is not listed."""
        try:
            row = self._rows.index((contour, index))
        except ValueError:
            return False
        self.selectRow(row)
        return True

    def selected_vertex(self) -> tuple[str, int] | None:
        row = self.currentRow()
        if 0 <= row < len(self._rows) and self.selectionModel().hasSelection():
            return self._rows[row]
        return None

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() < 2 or item.row() >= len(self._rows):
            return
        contour, index = self._rows[item.row()]
        point = self._point(contour, index)
        try:
            x = parse_coordinate(self.item(item.row(), 2).text(), self._unit)
            y = parse_coordinate(self.item(item.row(), 3).text(), self._unit)
        except (TypeError, ValueError):
            self._restore(item.row(), contour, index)
            return
        if (x, y) == (point.x, point.y):
            self._restore(item.row(), contour, index)
            return
        self.vertexEdited.emit(contour, index, x, y)

    def _restore(self, row: int, contour: str, index: int) -> None:
        point = self._point(contour, index)
        self._loading = True
        try:
            self.item(row, 2).setText(format_value(from_mm(point.x, self._unit), self._decimals))
            self.item(row, 3).setText(format_value(from_mm(point.y, self._unit), self._decimals))
        finally:
            self._loading = False

    def _point(self, contour: str, index: int):
        section = self._section
        target = section.inner if contour == INNER else section.outer
        assert target is not None
        return target.points[index]

    def _on_selection_changed(self) -> None:
        selected = self.selected_vertex()
        if selected is not None:
            self.vertexActivated.emit(selected[0], selected[1])
