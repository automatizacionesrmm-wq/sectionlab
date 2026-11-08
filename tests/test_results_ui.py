"""Results panel behavior: display conversion and full-precision export (S2, S3, S4)."""

from __future__ import annotations

import pytest

from sectionlab.core.engine import SectionProperties, calculate
from sectionlab.core.precision import format_full, format_value
from sectionlab.core.templates import TemplateKind, build_section
from sectionlab.core.units import Unit
from sectionlab.ui.results import ResultsTable, convert, result_rows


@pytest.fixture()
def props() -> SectionProperties:
    return calculate(build_section(TemplateKind.RECTANGLE))


def test_lengths_convert_to_the_active_unit() -> None:
    assert convert("cx", 50.0, Unit.CM) == pytest.approx(5.0)
    assert convert("cx", 25.4, Unit.IN) == pytest.approx(1.0)


def test_areas_inertias_and_moduli_use_their_own_powers() -> None:
    assert convert("area", 645.16, Unit.IN) == pytest.approx(1.0)
    assert convert("ix", 25.4**4, Unit.IN) == pytest.approx(1.0)
    assert convert("sx", 25.4**3, Unit.IN) == pytest.approx(1.0)


def test_angles_and_dimensionless_values_are_untouched() -> None:
    assert convert("principal_angle_deg", 45.0, Unit.IN) == 45.0


def test_every_reported_property_has_a_row(props: SectionProperties) -> None:
    rows = result_rows(props, Unit.MM)
    assert len(rows) == len(SectionProperties.__dataclass_fields__)
    assert all(symbol for _, _, symbol in rows)


def test_table_shows_values_converted_and_rounded(qtbot, props: SectionProperties) -> None:
    table = ResultsTable()
    qtbot.addWidget(table)
    table.show_properties(props, Unit.CM, 2)
    first_row = [table.item(0, column).text() for column in range(3)]
    assert first_row[0] == "Área"
    assert first_row[1] == "200.00"
    assert first_row[2] == "mm²"


def test_table_without_results_explains_itself(qtbot) -> None:
    table = ResultsTable()
    qtbot.addWidget(table)
    table.show_properties(None, Unit.MM, 2)
    assert table.rowCount() == 1
    assert table.item(0, 0).text().startswith("Calcula")


def test_csv_keeps_full_precision_whatever_the_decimals(qtbot, props: SectionProperties) -> None:
    table = ResultsTable()
    qtbot.addWidget(table)
    table.show_properties(props, Unit.MM, 0)
    csv_text = table.csv_text()
    assert table.item(0, 1).text() == format_value(props.area, 0)
    assert csv_text.splitlines()[1] == f"Área,{format_full(props.area)},mm²"
    assert csv_text.splitlines()[0] == "Propiedad,Valor,Unidad"


def test_csv_converts_values_to_the_active_unit(qtbot, props: SectionProperties) -> None:
    table = ResultsTable()
    qtbot.addWidget(table)
    table.show_properties(props, Unit.CM, 2)
    perimeter = convert("perimeter", props.perimeter, Unit.CM)
    assert f"Perímetro,{format_full(perimeter)},mm" in table.csv_text().splitlines()


def test_csv_is_empty_without_results(qtbot) -> None:
    table = ResultsTable()
    qtbot.addWidget(table)
    table.show_properties(None, Unit.MM, 2)
    assert table.csv_text() == ""


def test_copy_uses_tabs_and_full_precision(qtbot, props: SectionProperties) -> None:
    table = ResultsTable()
    qtbot.addWidget(table)
    table.show_properties(props, Unit.MM, 1)
    table.copy_to_clipboard()
    from PySide6.QtGui import QGuiApplication

    text = QGuiApplication.clipboard().text()
    assert text.splitlines()[0] == f"Área\t{format_full(props.area)}\tmm²"
