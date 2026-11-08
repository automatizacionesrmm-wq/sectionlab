"""Vertex table behaviour: unit-aware edition of typed coordinates (spec S7)."""

from __future__ import annotations

import pytest

from sectionlab.core.model import Contour, Point, Section
from sectionlab.core.templates import TemplateKind, build_section
from sectionlab.core.units import Unit
from sectionlab.ui import strings
from sectionlab.ui.vertex_table import INNER, OUTER, VertexTable, parse_coordinate


@pytest.fixture()
def section() -> Section:
    return Section(
        outer=Contour(
            points=[Point(0, 0), Point(100, 0), Point(100, 100), Point(0, 100)]
        )
    )


@pytest.fixture()
def table(qtbot) -> VertexTable:
    widget = VertexTable()
    qtbot.addWidget(widget)
    return widget


def flat(point_a: float, point_b: float) -> tuple[float, float]:
    return (point_a, point_b)


def test_parse_coordinate_accepts_a_comma_separator() -> None:
    assert parse_coordinate("12,5", Unit.MM) == pytest.approx(12.5)


def test_parse_coordinate_converts_to_millimetres() -> None:
    assert parse_coordinate("2", Unit.CM) == pytest.approx(20.0)
    assert parse_coordinate("1", Unit.IN) == pytest.approx(25.4)


def test_headers_are_spanish(table: VertexTable) -> None:
    labels = [table.horizontalHeaderItem(column).text() for column in range(table.columnCount())]
    assert labels[:2] == [strings.label_for("contour"), strings.label_for("index")]
    assert labels[2:] == ["X", "Y"]


def test_every_vertex_becomes_a_row(table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.MM, 2)
    assert table.rowCount() == 4
    assert table.values() == [(OUTER, 0), (OUTER, 1), (OUTER, 2), (OUTER, 3)]


def test_rows_are_numbered_from_one(table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.MM, 2)
    assert table.item(0, 0).text() == strings.label_for("outer_contour")
    assert table.item(0, 1).text() == "1"


def test_values_are_shown_in_the_active_unit(table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.CM, 1)
    assert table.item(1, 2).text() == "10.0"


def test_decimal_setting_controls_the_display(table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.MM, 0)
    assert table.item(1, 2).text() == "100"


def test_inner_contour_rows_come_after_the_outer_ones(table: VertexTable) -> None:
    hollow = build_section(TemplateKind.RECT_HOLLOW)
    table.show_section(hollow, Unit.MM, 2)
    keys = table.values()
    assert keys[0] == (OUTER, 0)
    assert (INNER, 0) in keys
    assert keys.index((INNER, 0)) > keys.index((OUTER, 0))


def test_editing_a_cell_reports_millimetres(qtbot, table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.CM, 1)
    with qtbot.waitSignal(table.vertexEdited, timeout=200) as blocker:
        table.item(1, 2).setText("25,5")
    assert blocker.args == [OUTER, 1, 255.0, 0.0]


def test_invalid_text_is_reverted(qtbot, table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.MM, 2)
    table.item(0, 2).setText("abc")
    assert table.item(0, 2).text() == "0.00"
    assert table.item(0, 3).text() == "0.00"


def test_unchanged_value_is_only_reformatted(qtbot, table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.MM, 2)
    with qtbot.assertNotEmitted(table.vertexEdited, wait=50):
        table.item(1, 2).setText("100.000")
    assert table.item(1, 2).text() == "100.00"


def test_selecting_a_vertex_highlights_its_row(table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.MM, 2)
    assert table.select_vertex(OUTER, 2) is True
    assert table.selected_vertex() == (OUTER, 2)


def test_selecting_a_missing_vertex_reports_failure(table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.MM, 2)
    assert table.select_vertex(OUTER, 9) is False


def test_row_selection_notifies_the_canvas(qtbot, table: VertexTable, section: Section) -> None:
    table.show_section(section, Unit.MM, 2)
    with qtbot.waitSignal(table.vertexActivated, timeout=200) as blocker:
        table.select_vertex(OUTER, 1)
    assert blocker.args == [OUTER, 1]


def test_empty_section_has_no_rows(table: VertexTable) -> None:
    table.show_section(Section(outer=Contour(points=[])), Unit.MM, 2)
    assert table.rowCount() == 0
    assert table.selected_vertex() is None
