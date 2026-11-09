"""Main window flow: templates, validation blocking, unit display and files (S5–S15)."""

from __future__ import annotations

import pytest

from sectionlab.core.model import Contour, Point, Section
from sectionlab.core.precision import format_full
from sectionlab.core.templates import TemplateKind
from sectionlab.core.units import Unit
from sectionlab.ui import strings
from sectionlab.ui.app import MainWindow
from sectionlab.ui.settings import AppSettings
from sectionlab.ui.theme import DARK, LIGHT, Theme

pytestmark = pytest.mark.usefixtures("qtbot")


@pytest.fixture()
def window(qtbot) -> MainWindow:
    main = MainWindow(AppSettings(), interactive=False)
    qtbot.addWidget(main)
    return main


def open_section(window: MainWindow) -> None:
    window.canvas.set_section(
        Section(
            outer=Contour(
                points=[Point(0, 0), Point(100, 0), Point(100, 100)],
                closed=False,
            )
        )
    )


def test_a_new_window_has_nothing_to_show(window: MainWindow) -> None:
    assert window.properties() is None
    assert window.current_unit() is Unit.MM
    assert window.current_decimals() == 2
    assert window.results_table.item(0, 0).text().startswith("Calcula")


def test_applying_a_template_fills_the_canvas_read_only(window: MainWindow) -> None:
    assert window.apply_template(TemplateKind.RECTANGLE.value) is True
    assert window.canvas.is_editable() is False
    assert len(window.section().outer.points) == 4
    assert window.section().template is not None


def test_calculating_shows_results_in_spanish(window: MainWindow) -> None:
    window.apply_template(TemplateKind.RECTANGLE.value)
    assert window.calculate_now() is True
    props = window.properties()
    assert props is not None
    assert props.area == pytest.approx(20_000.0, rel=1e-9)
    assert window.results_table.item(0, 0).text() == "Área"
    assert window.results_table.item(0, 2).text() == "mm²"


def test_impossible_template_parameters_are_reported(window: MainWindow) -> None:
    assert window.apply_template(TemplateKind.RECT_HOLLOW.value, {"t": 200.0}) is False
    assert window.last_error() in strings.PARAMETER_ERROR_MESSAGES.values()
    assert window.section().outer.points == []


def test_open_contour_blocks_calculation_with_a_spanish_message(window: MainWindow) -> None:
    open_section(window)
    assert window.validation_message() is not None
    assert "abierto" in (window.validation_message() or "")
    assert window.calculate_now() is False
    assert window.properties() is None
    assert window.last_error() is not None


def test_self_intersecting_geometry_is_blocked(window: MainWindow) -> None:
    window.canvas.set_section(
        Section(
            outer=Contour(
                points=[Point(0, 0), Point(100, 100), Point(100, 0), Point(0, 100)]
            )
        )
    )
    assert window.calculate_now() is False
    assert "cruza" in (window.last_error() or "")


def test_valid_free_geometry_calculates(window: MainWindow) -> None:
    window.canvas.set_section(
        Section(
            outer=Contour(
                points=[Point(0, 0), Point(100, 0), Point(100, 100), Point(0, 100)]
            )
        )
    )
    assert window.calculate_now() is True
    assert window.properties() is not None


def test_free_geometry_mode_starts_an_empty_drawing(window: MainWindow) -> None:
    window.apply_template(TemplateKind.PIPE.value)
    window.start_free_geometry()
    assert window.canvas.is_editable() is True
    assert window.canvas.is_drawing() is True
    assert window.section().template is None
    assert window.section().outer.points == []


def test_unit_change_only_converts_the_display(window: MainWindow) -> None:
    window.apply_template(TemplateKind.RECTANGLE.value)
    window.calculate_now()
    before = window.section()
    window.set_unit(Unit.CM)
    assert window.section() == before
    assert window.results_table.item(0, 1).text() == "200.00"
    assert window.current_unit() is Unit.CM


def test_vertex_table_follows_the_active_unit(window: MainWindow) -> None:
    window.apply_template(TemplateKind.RECTANGLE.value)
    window.set_unit(Unit.M)
    assert window.vertex_table.item(1, 2).text() == "0.10"


def test_decimals_change_the_display_only(window: MainWindow) -> None:
    window.apply_template(TemplateKind.RECTANGLE.value)
    window.calculate_now()
    window.set_decimals(0)
    assert window.results_table.item(0, 1).text() == "20000"
    window.set_decimals(4)
    assert window.results_table.item(0, 1).text().endswith(".0000")


def test_saving_and_reopening_a_project(window: MainWindow, tmp_path) -> None:
    window.apply_template(TemplateKind.I_PROFILE.value, {"h": 300.0})
    window.set_unit(Unit.CM)
    target = tmp_path / "perfil.sectionlab"
    window.save_document(target)
    assert target.exists()
    assert window.document_path() == target

    window.set_unit(Unit.MM)
    assert window.open_document(target) is True
    assert window.current_unit() is Unit.CM
    assert window.section().template is not None
    assert window.section().template.params["h"] == pytest.approx(300.0)


def test_opening_a_broken_file_reports_it(window: MainWindow, tmp_path) -> None:
    broken = tmp_path / "roto.sectionlab"
    broken.write_text("{", encoding="utf-8")
    assert window.open_document(broken) is False
    assert window.last_error() in strings.DOCUMENT_ERROR_MESSAGES.values()


def test_csv_export_is_full_precision(window: MainWindow, tmp_path) -> None:
    window.apply_template(TemplateKind.RECTANGLE.value)
    assert window.calculate_now() is True
    target = tmp_path / "resultados.csv"
    text = window.export_csv(target)
    assert target.read_text(encoding="utf-8") == text
    props = window.properties()
    assert props is not None
    assert f"Área,{format_full(props.area)},mm²" in text.splitlines()


def test_drawing_an_edit_enables_undo(window: MainWindow) -> None:
    window.canvas.set_section(
        Section(outer=Contour(points=[Point(0, 0), Point(50, 0), Point(50, 50)]))
    )
    window.canvas.set_editable(True)
    assert window.action_undo.isEnabled() is False
    window.canvas.move_vertex("outer", 0, 5.0, 5.0)
    assert window.action_undo.isEnabled() is True


def test_cursor_position_is_shown_in_the_active_unit(window: MainWindow) -> None:
    window.set_unit(Unit.CM)
    window.canvas.cursorMoved.emit(50.0, 20.0)
    assert window._cursor_label.text() == "X 5.00  Y 2.00 cm"


def test_snap_kind_is_translated(window: MainWindow) -> None:
    window.canvas.snapChanged.emit("MIDPOINT")
    assert window._snap_label.text() == strings.label_for("snap_midpoint")
    window.canvas.snapChanged.emit("")
    assert window._snap_label.text() == ""


def test_inserting_a_vertex_is_possible_in_free_mode(window: MainWindow) -> None:
    window.canvas.set_section(
        Section(outer=Contour(points=[Point(0, 0), Point(50, 0), Point(50, 50)]))
    )
    window.canvas.set_editable(True)
    window.canvas.select_vertex("outer", 0)
    window.insert_vertex()
    assert len(window.section().outer.points) == 4


def test_deleting_a_selected_vertex(window: MainWindow) -> None:
    window.canvas.set_section(
        Section(outer=Contour(points=[Point(0, 0), Point(50, 0), Point(50, 50)]))
    )
    window.canvas.set_editable(True)
    window.canvas.select_vertex("outer", 1)
    window.delete_selected_vertex()
    assert len(window.section().outer.points) == 2


def test_a_new_window_starts_in_the_dark_theme(window: MainWindow) -> None:
    assert window.current_theme() is Theme.DARK


def test_toggling_switches_between_the_two_themes(window: MainWindow) -> None:
    window.toggle_theme()
    assert window.current_theme() is Theme.LIGHT
    window.toggle_theme()
    assert window.current_theme() is Theme.DARK


def test_the_theme_reaches_the_application_stylesheet(window: MainWindow) -> None:
    from PySide6.QtWidgets import QApplication

    window.set_theme(Theme.LIGHT)
    assert LIGHT["accent"] in QApplication.instance().styleSheet()
    window.set_theme(Theme.DARK)
    assert DARK["accent"] in QApplication.instance().styleSheet()


def test_choosing_a_template_draws_it_without_pressing_apply(window: MainWindow) -> None:
    combo = window.template_panel._kind
    combo.setCurrentIndex(combo.findData(TemplateKind.I_PROFILE.value))
    assert window.section().template is not None
    assert window.section().outer.points


def test_the_toolbar_offers_icons_for_every_action(window: MainWindow) -> None:
    from PySide6.QtWidgets import QToolBar

    toolbar = window.findChild(QToolBar, "main_toolbar")
    assert toolbar is not None
    actions = [action for action in toolbar.actions() if not action.isSeparator()]
    assert len(actions) == 14
    for action in actions:
        assert not action.icon().isNull(), action.text()
