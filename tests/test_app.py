"""Main window flow: templates, validation blocking, unit display and files (S5–S15)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QThread, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDockWidget, QMessageBox

from sectionlab.core.model import Contour, Point, Section
from sectionlab.core.precision import format_full
from sectionlab.core.snap import SNAP_KINDS, SnapKind
from sectionlab.core.templates import TemplateKind
from sectionlab.core.units import Unit
from sectionlab.ui import strings
from sectionlab.core.dimensions import (
    ANCHOR_VERTEX,
    HORIZONTAL,
    SEGMENT_LENGTH,
    Anchor,
)
from sectionlab.ui.app import MainWindow

ANCHOR_0 = Anchor(ANCHOR_VERTEX, 0)
ANCHOR_1 = Anchor(ANCHOR_VERTEX, 1)
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
    assert len(actions) == 21  # 16 commands plus one button per snap family (spec S13)
    for action in actions:
        assert not action.icon().isNull(), action.text()


def test_the_drawing_fills_the_window(window: MainWindow) -> None:
    # The central widget holds the update banner above the drawing, so the drawing keeps
    # every pixel the banner is not using.
    assert window.canvas.parentWidget() is window.centralWidget()
    assert window.update_banner.parentWidget() is window.centralWidget()


def test_every_inspector_is_a_movable_dock(window: MainWindow) -> None:
    assert len(window._docks) == 3
    for dock in window._docks:
        features = dock.features()
        assert features & QDockWidget.DockWidgetFeature.DockWidgetMovable
        assert features & QDockWidget.DockWidgetFeature.DockWidgetFloatable
        assert features & QDockWidget.DockWidgetFeature.DockWidgetClosable


def test_the_drawing_keeps_the_window_when_the_panels_hide(window: MainWindow) -> None:
    window.set_panels_visible(False)
    assert not window.panels_visible()
    assert not window.action_panels.isChecked()
    assert window.canvas.isVisibleTo(window)
    window.set_panels_visible(True)
    assert window.panels_visible()
    assert window.action_panels.isChecked()


def test_hiding_one_panel_unchecks_the_toggle(window: MainWindow, qtbot) -> None:
    window.show()
    with qtbot.waitExposed(window):
        pass
    window._docks[0].hide()
    assert not window.action_panels.isChecked()
    assert window.panels_visible()
    for dock in window._docks:
        dock.show()
    assert window.action_panels.isChecked()


def test_one_shortcut_press_restores_the_panels_it_found_missing(
    window: MainWindow, qtbot
) -> None:
    """F9 must add back what is closed, not finish hiding what is left."""
    window.show()
    with qtbot.waitExposed(window):
        pass
    for dock in window._docks:
        dock.hide()
    assert not window.panels_visible()

    window.action_panels.trigger()

    assert window.all_panels_visible()
    assert window.action_panels.isChecked()

    window.action_panels.trigger()

    assert not window.panels_visible()


def test_the_panels_menu_can_reopen_the_one_that_was_closed(window: MainWindow, qtbot) -> None:
    window.show()
    with qtbot.waitExposed(window):
        pass
    closed = window._docks[1]
    closed.hide()

    reopen = window._panel_actions[1]
    assert reopen.isCheckable()
    assert not reopen.isChecked()
    reopen.trigger()

    assert not closed.isHidden()
    assert reopen.isChecked()


def test_the_status_bar_explains_how_to_bring_the_panels_back(
    window: MainWindow, qtbot
) -> None:
    window.show()
    with qtbot.waitExposed(window):
        pass
    assert window._panels_hint.isHidden()

    window.set_panels_visible(False)

    assert not window._panels_hint.isHidden()
    assert "F9" in window._panels_hint.text()

    window.set_panels_visible(True)

    assert window._panels_hint.isHidden()


def test_the_view_menu_can_hide_the_dimensions(window: MainWindow) -> None:
    assert window.dimensions_visible()
    assert window.action_dimensions.isChecked()
    window.action_dimensions.setChecked(False)
    assert not window.dimensions_visible()
    window.set_dimensions_visible(True)
    assert window.action_dimensions.isChecked()


def test_the_canvas_writes_numbers_in_the_unit_the_panels_accept(window: MainWindow) -> None:
    """The dimensions, the panels and the results all speak the active unit (spec S2)."""
    window.canvas.set_section(
        Section(
            outer=Contour(
                points=[Point(0, 0), Point(100, 0), Point(100, 100), Point(0, 100)],
                closed=True,
            )
        )
    )
    assert window.calculate_now() is True
    window.canvas.add_dimension(ANCHOR_0, ANCHOR_1, SEGMENT_LENGTH, offset_mm=10.0)
    assert window.canvas._dimension_text(window.canvas.dimensions()[0]) == "100.00"

    window.set_unit(Unit.CM)
    assert window.canvas.display_unit() is Unit.CM
    assert window.canvas._dimension_text(window.canvas.dimensions()[0]) == "10.00"
    window.set_unit(Unit.MM)
    assert window.canvas._dimension_text(window.canvas.dimensions()[0]) == "100.00"


def test_every_panel_shows_the_unit_its_values_were_converted_to(window: MainWindow) -> None:
    window.apply_template(TemplateKind.RECTANGLE.value)
    assert window.calculate_now() is True
    window.set_unit(Unit.CM)
    # 100 mm is 10 cm: the value, the symbol and the vertex table all agree.
    assert window.results_table.item(0, 1).text() == "200.00"
    assert window.results_table.item(0, 2).text() == "cm²"
    assert window.results_table.item(1, 2).text() == "cm"
    assert window.vertex_table.item(1, 2).text() == "10.00"
    window.set_unit(Unit.MM)
    assert window.results_table.item(0, 2).text() == "mm²"


def test_a_refused_dimension_is_explained_in_the_status_bar(window: MainWindow) -> None:
    assert window.apply_template(TemplateKind.RECTANGLE.value)
    window.canvas.editRejected.emit("read_only")
    assert window._message_label.text() == strings.dimension_message("read_only")


def test_a_dimension_edit_invalidates_the_previous_results(window: MainWindow) -> None:
    window.canvas.set_section(
        Section(
            outer=Contour(
                points=[Point(0, 0), Point(100, 0), Point(100, 100), Point(0, 100)],
                closed=True,
            )
        )
    )
    assert window.calculate_now() is True
    assert window.properties() is not None
    dimension = window.canvas.add_dimension(ANCHOR_0, ANCHOR_1, SEGMENT_LENGTH, offset_mm=10.0)
    assert window.canvas.drive_dimension(dimension.id, 150.0) is True
    assert window.properties() is None
    assert window.canvas.section().outer.points[1] == Point(150, 0)


# -------------------------------------- template sections become free geometry (spec S10)


def test_a_template_section_can_become_editable_geometry(window: MainWindow) -> None:
    assert window.apply_template(TemplateKind.RECTANGLE.value) is True
    before = window.section().outer.points
    assert window.canvas.is_editable() is False

    assert window.convert_to_free_geometry() is True
    assert window.section().template is None
    assert window.section().outer.points == before
    assert window.canvas.is_editable() is True
    # The vertex table accepts edits and a placed dimension drives the geometry in place.
    assert window.vertex_table.isEnabled() is True
    dimension = window.canvas.add_dimension(ANCHOR_0, ANCHOR_1, SEGMENT_LENGTH, offset_mm=10.0)
    assert window.canvas.drive_dimension(dimension.id, 150.0) is True
    assert window.section().outer.points[1] == Point(150, 0)


def test_converting_a_template_is_one_undo_step(window: MainWindow) -> None:
    window.apply_template(TemplateKind.RECTANGLE.value)
    window.convert_to_free_geometry()
    assert window.canvas.undo_stack().undoText() == strings.label_for("undo_convert")
    window.canvas.undo_stack().undo()
    assert window.section().template is not None
    # Undo crosses back into template mode: the vertices lock again and the panel returns.
    assert window.canvas.is_editable() is False
    assert window.template_mode() is True
    window.canvas.undo_stack().redo()
    assert window.canvas.is_editable() is True
    assert window.template_mode() is False


def test_the_template_inspector_leaves_with_the_template(window: MainWindow) -> None:
    dock = window._dock_by_name["template"]
    assert not dock.isHidden()
    window.apply_template(TemplateKind.RECTANGLE.value)
    assert not dock.isHidden()
    window.convert_to_free_geometry()
    assert dock.isHidden()
    assert dock.toggleViewAction().isEnabled() is False
    # F9 still brings back the inspectors that apply, and only those.
    window.set_panels_visible(True)
    assert dock.isHidden()
    assert window.all_panels_visible() is True


def test_a_free_section_cannot_be_converted_again(window: MainWindow) -> None:
    assert window.convert_to_free_geometry() is False


def test_the_focused_template_parameter_names_its_dimension(window: MainWindow) -> None:
    window.apply_template(TemplateKind.RECTANGLE.value)
    assert window.template_panel.focus_parameter("b") is True
    assert window.canvas.value_highlight() is not None
    _, name = window.canvas.value_highlight()
    assert name == strings.label_for("b")
    window.template_panel.focus_parameter("h")
    assert window.canvas.value_highlight()[1] == strings.label_for("h")


# ------------------------------------------------- inspectors you can actually move (S8)


def test_the_inspectors_start_on_both_sides(window: MainWindow) -> None:
    window.resize(1200, 800)
    assert window.dockWidgetArea(window._dock_by_name["template"]) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.dockWidgetArea(window._dock_by_name["vertices"]) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.dockWidgetArea(window._dock_by_name["results"]) == Qt.DockWidgetArea.RightDockWidgetArea


def test_dragging_a_header_docks_the_panel_on_the_side_it_was_dropped(window: MainWindow) -> None:
    window.resize(1200, 800)
    dock = window._dock_by_name["results"]
    header = dock.titleBarWidget()
    left_drop = window.mapToGlobal(QPoint(40, 200))
    start = window.mapToGlobal(QPoint(window.width() - 40, 200))
    header.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            QPointF(start),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    header.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(10, 10),
            QPointF(left_drop),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    header.mouseReleaseEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(10, 10),
            QPointF(left_drop),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert window.dockWidgetArea(dock) == Qt.DockWidgetArea.LeftDockWidgetArea


def test_a_panel_dropped_outside_the_window_floats_and_comes_back(window: MainWindow) -> None:
    window.resize(1200, 800)
    dock = window._dock_by_name["vertices"]
    window.move_panel(dock, QPoint(-400, -400))
    assert dock.isFloating() is True
    window.toggle_panel_float(dock)
    assert dock.isFloating() is False
    assert window.dockWidgetArea(dock) != Qt.DockWidgetArea.NoDockWidgetArea


def test_the_header_menu_offers_both_sides_and_floating(window: MainWindow) -> None:
    menu = window.panel_menu(window._dock_by_name["results"], QPoint(0, 0))
    labels = [action.text() for action in menu.actions() if action.text()]
    assert strings.label_for("panel_left") in labels
    assert strings.label_for("panel_right") in labels
    assert strings.label_for("panel_float") in labels
    assert strings.label_for("panel_hide") in labels


def test_selecting_a_vertex_on_the_drawing_selects_its_row(window: MainWindow) -> None:
    window.apply_template(TemplateKind.RECTANGLE.value)
    window.canvas.select_vertex("outer", 2)
    assert window.vertex_table.selected_vertex() == ("outer", 2)
    # The mirror must not echo back and forth.
    seen: list[tuple[str, int]] = []
    window.canvas.vertexSelected.connect(lambda contour, index: seen.append((contour, index)))
    window.canvas.select_vertex("outer", 2)
    assert seen == []


# ------------------------------------------------------- in-app updates (specs S1-S3, S7)


def rectangle_release(version: str = "9.9.9"):
    from sectionlab.core.update import Asset, Release

    return Release(
        version=version,
        tag=f"v{version}",
        notes="notas",
        assets=(
            Asset(name=f"SectionLab-{version}-code.zip", url="https://example.test/code.zip"),
        ),
    )


def test_the_title_and_the_about_box_name_the_running_version(window: MainWindow) -> None:
    from sectionlab import __version__

    assert __version__ in window.windowTitle()
    text = window.about_text()
    assert __version__ in text
    assert "github.com/automatizacionesrmm-wq/sectionlab" in text
    assert strings.label_for("about_license") in text


def test_a_newer_release_is_announced_without_a_dialog(window: MainWindow, qtbot) -> None:
    window._fetch = lambda: rectangle_release("9.9.9")
    assert window.update_banner.isHidden()
    assert window.check_for_updates() is True
    qtbot.waitUntil(lambda: not window.update_banner.isHidden(), timeout=2000)
    assert "9.9.9" in window.update_banner.version_text()
    assert strings.label_for("update_available") in window.update_banner.version_text()
    assert window.offered_release().version == "9.9.9"


def test_lying_about_the_version_offers_nothing(window: MainWindow, qtbot) -> None:
    from sectionlab import __version__

    window._fetch = lambda: rectangle_release(__version__)
    window.check_for_updates()
    qtbot.waitUntil(lambda: window._checker is None, timeout=2000)
    assert window.update_banner.isHidden()
    assert window.offered_release() is None
    assert strings.label_for("up_to_date") in window._message_label.text()


def test_mas_tarde_hides_the_banner_for_this_session(window: MainWindow, qtbot) -> None:
    window._fetch = lambda: rectangle_release()
    window.check_for_updates()
    qtbot.waitUntil(lambda: not window.update_banner.isHidden(), timeout=2000)
    window.update_banner._later.click()
    assert window.update_banner.isHidden()
    assert window.offered_release() is not None


def test_an_automatic_check_that_fails_says_nothing(window: MainWindow, qtbot) -> None:
    from sectionlab.core.update import UpdateError

    def offline():
        raise UpdateError("check_failed")

    window._fetch = offline
    before = window._message_label.text()
    window.check_for_updates(automatic=True)
    qtbot.waitUntil(lambda: window._checker is None, timeout=2000)
    assert window._message_label.text() == before
    assert window.update_banner.isHidden()


def test_a_manual_check_that_fails_explains_itself(window: MainWindow, qtbot) -> None:
    from sectionlab.core.update import UpdateError

    def offline():
        raise UpdateError("check_failed")

    window._fetch = offline
    window.check_for_updates()
    qtbot.waitUntil(lambda: window._checker is None, timeout=2000)
    assert window._message_label.text() == strings.update_message("check_failed")
    assert window.last_check_text().startswith(strings.label_for("update_state_failed"))


def test_the_help_menu_offers_both_entries(window: MainWindow) -> None:
    menus = {action.text(): action.menu() for action in window.menuBar().actions()}
    help_menu = menus[strings.label_for("menu_help")]
    labels = [action.text() for action in help_menu.actions()]
    assert strings.label_for("check_updates") in labels
    assert strings.label_for("about") in labels


# ------------------------------------------------- applying an update (specs S4-S6)


def code_archive(path, version: str = "9.9.9"):
    import zipfile

    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("sectionlab/__init__.py", f'__version__ = "{version}"\n')
        bundle.writestr("sectionlab/nuevo.py", "nuevo\n")
    return path


@pytest.fixture()
def installed(tmp_path, monkeypatch):
    app_dir = tmp_path / "SectionLab" / "app"
    (app_dir / "sectionlab").mkdir(parents=True)
    (app_dir / "sectionlab" / "__init__.py").write_text('__version__ = "0.1.2"\n', encoding="utf-8")
    monkeypatch.setattr(MainWindow, "_installation_app_dir", lambda self: app_dir)
    return app_dir


def test_applying_a_patch_replaces_the_package_and_keeps_a_backup(
    window: MainWindow, installed, tmp_path
) -> None:
    archive = code_archive(tmp_path / "code.zip")
    window._release = rectangle_release("9.9.9")
    window._on_patch_downloaded(str(archive))
    assert (installed / "sectionlab" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "9.9.9"\n'
    assert (installed / "sectionlab.bak" / "__init__.py").is_file()
    assert strings.label_for("update_done") in window._message_label.text()
    assert window.offered_release() is None


def test_a_broken_archive_leaves_the_installation_alone(window: MainWindow, installed, tmp_path) -> None:
    broken = tmp_path / "code.zip"
    broken.write_bytes(b"no es un zip")
    window._release = rectangle_release()
    window._on_patch_downloaded(str(broken))
    assert (installed / "sectionlab" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "0.1.2"\n'
    assert not (installed / "sectionlab.bak").exists()
    assert strings.label_for("update_failed") in window._message_label.text()


def test_a_development_checkout_is_never_patched(window: MainWindow, tmp_path) -> None:
    window._release = rectangle_release()
    window._on_patch_downloaded(str(code_archive(tmp_path / "code.zip")))
    assert strings.update_message("not_installed") in window._message_label.text()


def test_restarting_relaunches_the_same_executable(window: MainWindow, monkeypatch) -> None:
    import sys as system

    launched: list[bool] = []

    def relaunch() -> bool:
        launched.append(True)
        return True

    monkeypatch.setattr(window, "_relaunch", relaunch)
    monkeypatch.setattr(system, "frozen", True, raising=False)
    assert window.restart_application() is True
    assert launched == [True]


def test_no_release_means_nothing_to_apply(window: MainWindow) -> None:
    assert window.apply_update() is False


def test_a_release_without_a_code_archive_offers_the_installer(window: MainWindow, qtbot, tmp_path) -> None:
    from sectionlab.core.update import Asset, Release

    installer_bytes = b"instalador"
    window._opener = lambda url, headers: __import__("io").BytesIO(installer_bytes)
    window._updates_dir = tmp_path / "updates"
    window._release = Release(
        version="9.9.9",
        tag="v9.9.9",
        assets=(Asset(name="SectionLab-9.9.9-setup.exe", url="https://example.test/setup.exe"),),
    )
    assert window.apply_update() is True
    qtbot.waitUntil(lambda: window._downloader is None, timeout=2000)
    downloaded = tmp_path / "updates" / "SectionLab-9.9.9-setup.exe"
    assert downloaded.read_bytes() == installer_bytes
    assert strings.label_for("installer_ready") in window._message_label.text()


# ------------------------------------------------- editing a template (spec S9)


def test_a_typed_parameter_survives_being_applied(window: MainWindow, qtbot) -> None:
    """The panel is the source of truth while a template is edited: it must keep 200."""
    combo = window.template_panel._kind
    combo.setCurrentIndex(combo.findData(TemplateKind.I_PROFILE.value))
    qtbot.wait(250)
    window.template_panel._spins["b"].setValue(200.0)
    qtbot.wait(300)
    assert window.template_panel._spins["b"].value() == 200.0
    assert window.section().template.params["b"] == pytest.approx(200.0)


def test_applying_a_template_keeps_the_offered_update(window: MainWindow) -> None:
    window._release = rectangle_release("9.9.9")
    assert window.apply_template(TemplateKind.I_PROFILE.value) is True
    assert window.offered_release() is not None


def test_an_invalid_parameter_explains_itself_without_a_dialog(qtbot, monkeypatch) -> None:
    """Typing an intermediate invalid value must not steal the keyboard with a dialog."""
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2])))
    main = MainWindow(AppSettings(), interactive=True)
    qtbot.addWidget(main)
    invalid = {"h": 200.0, "b": 4.0, "tw": 6.0, "tf": 10.0}
    assert main.apply_template(TemplateKind.I_PROFILE.value, invalid) is False
    assert warnings == []
    assert main._message_label.text()


def test_a_frozen_install_knows_its_own_app_folder(window: MainWindow, monkeypatch) -> None:
    """Regression: the updater refused every real installation with `not_installed`."""
    import sys as system
    from pathlib import Path

    import sectionlab

    monkeypatch.setattr(system, "frozen", True, raising=False)
    expected = Path(sectionlab.__file__).resolve().parent.parent
    assert window._installation_app_dir() == expected


def test_picking_a_segment_explains_that_it_takes_typed_input(window: MainWindow) -> None:
    open_section(window)
    window.canvas.select_segment("outer", 0)
    assert window._message_label.text() == strings.label_for("segment_selected_hint")


def test_a_failed_check_says_so_in_the_about_box_and_the_log(window: MainWindow, qtbot, tmp_path) -> None:
    """A silent automatic failure has to leave evidence somewhere we can read later."""
    from sectionlab.core.update import UpdateError

    log = tmp_path / "updates.log"
    window.check_log_path = lambda: log

    def offline():
        raise UpdateError("check_failed", "getaddrinfo failed for api.github.com")

    window._fetch = offline
    window.check_for_updates(automatic=True)
    qtbot.waitUntil(lambda: window._checker is None, timeout=2000)

    assert window._message_label.text() != strings.label_for("checking_updates")  # no nagging...
    text = window.last_check_text()
    assert strings.label_for("update_state_failed") in text
    assert "getaddrinfo failed" in text
    assert "getaddrinfo failed" in log.read_text(encoding="utf-8")


def test_the_about_box_reports_the_last_successful_check(window: MainWindow, qtbot, tmp_path) -> None:
    window.check_log_path = lambda: tmp_path / "updates.log"
    window._fetch = lambda: rectangle_release("9.9.9")
    window.check_for_updates(automatic=True)
    qtbot.waitUntil(lambda: window._checker is None, timeout=2000)
    assert strings.label_for("update_state_offered") in window.last_check_text()
    assert window.last_check_text() in window.about_text()


def test_a_manual_check_while_one_is_running_says_so(window: MainWindow) -> None:
    """Never do nothing silently: a second click must answer."""
    window._checker = _RunningThread(window)
    assert window.check_for_updates() is False
    assert window._message_label.text() == strings.label_for("checking_in_flight")


class _RunningThread(QThread):
    def isRunning(self) -> bool:  # noqa: N802 - Qt override
        return True


def test_a_new_window_has_no_check_history(window: MainWindow) -> None:
    assert window.last_check_text() == strings.label_for("update_state_never")


def test_destroying_the_window_cancels_the_automatic_check(qtbot) -> None:
    """A scheduled check must die with its window, not fire into a deleted C++ object."""
    from sectionlab.ui.app import AUTO_CHECK_DELAY_MS

    calls: list[int] = []
    window = MainWindow(AppSettings(), interactive=True)
    window._fetch = lambda: calls.append(1) or rectangle_release("9.9.9")
    window.show()
    window.close()
    window.deleteLater()
    qtbot.wait(AUTO_CHECK_DELAY_MS + 400)
    assert calls == []


def test_a_manual_check_that_finds_nothing_new_says_so_out_loud(qtbot, monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: seen.append(a[2])))
    main = MainWindow(AppSettings(), interactive=True)
    qtbot.addWidget(main)
    main.check_log_path = lambda: __import__("pathlib").Path("/tmp/sectionlab-test-updates.log")
    main._fetch = lambda: rectangle_release("0.1.0")
    main.check_for_updates()
    qtbot.waitUntil(lambda: main._checker is None, timeout=2000)
    assert strings.label_for("up_to_date") in main._message_label.text()
    assert seen and "0.1.0" in seen[0]


def test_a_manual_check_that_fails_opens_a_dialog_naming_the_log(qtbot, monkeypatch) -> None:
    from sectionlab.core.update import UpdateError

    seen: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: seen.append(a[2])))
    main = MainWindow(AppSettings(), interactive=True)
    qtbot.addWidget(main)
    main.check_log_path = lambda: __import__("pathlib").Path("/tmp/sectionlab-test-updates.log")

    def offline():
        raise UpdateError("check_failed", "getaddrinfo failed")

    main._fetch = offline
    main.check_for_updates()
    qtbot.waitUntil(lambda: main._checker is None, timeout=2000)
    assert seen and "updates.log" in seen[0] and "getaddrinfo failed" in seen[0]


# ------------------------------------------------- dimensioning from the window (S1, S2, S6)


def free_rectangle(window: MainWindow) -> None:
    window.canvas.set_section(
        Section(
            outer=Contour(
                points=[Point(0, 0), Point(100, 0), Point(100, 60), Point(0, 60)],
                closed=True,
            )
        )
    )


def test_the_window_offers_a_dimension_tool(window: MainWindow) -> None:
    assert window.action_dimension_tool.shortcut() == QKeySequence("D")
    free_rectangle(window)
    window.action_dimension_tool.setChecked(True)
    assert window.dimension_tool_active() is True
    window.action_dimension_tool.setChecked(False)
    assert window.dimension_tool_active() is False


def test_the_tool_needs_a_section(window: MainWindow) -> None:
    window.action_dimension_tool.setChecked(True)
    assert window.dimension_tool_active() is False
    assert not window.action_dimension_tool.isChecked()
    assert window._message_label.text() == strings.label_for("dimension_needs_section")


def test_the_status_bar_explains_the_tool_steps(window: MainWindow) -> None:
    free_rectangle(window)
    window.action_dimension_tool.setChecked(True)
    assert window._message_label.text() == strings.label_for("dimension_tool_first")
    window.canvas.dimensionStepChanged.emit(1)
    assert window._message_label.text() == strings.label_for("dimension_tool_second")
    window.canvas.dimensionStepChanged.emit(2)
    assert window._message_label.text() == strings.label_for("dimension_tool_place")


def test_leaving_the_tool_with_escape_clears_the_action(window: MainWindow) -> None:
    free_rectangle(window)
    window.action_dimension_tool.setChecked(True)
    window.canvas.cancel_dimension_tool()
    assert window.action_dimension_tool.isChecked() is False


def test_a_placed_dimension_is_announced(window: MainWindow) -> None:
    free_rectangle(window)
    window.canvas.add_dimension(ANCHOR_0, ANCHOR_1, SEGMENT_LENGTH, offset_mm=10.0)
    assert window._message_label.text() == strings.label_for("dimension_placed")


def test_guides_can_be_switched_off_from_the_view_menu(window: MainWindow) -> None:
    assert window.action_guides.isChecked()
    assert window.guides_visible()
    window.action_guides.setChecked(False)
    assert window.guides_visible() is False
    assert window.action_guides.shortcut() == QKeySequence("Ctrl+L")


def test_a_guide_names_its_reference_in_the_status_bar(window: MainWindow) -> None:
    free_rectangle(window)
    window.canvas.guidesChanged.emit("X con v1")
    assert window._snap_label.text() == "X con v1"
    # A snap is exact, so it takes the space from the guide.
    window.canvas.snapChanged.emit("ENDPOINT")
    assert window._snap_label.text() == strings.label_for("snap_endpoint")
    window.canvas.guidesChanged.emit("")


def test_dimensions_travel_with_the_document(window: MainWindow, tmp_path) -> None:
    free_rectangle(window)
    window.canvas.add_dimension(ANCHOR_0, ANCHOR_1, SEGMENT_LENGTH, offset_mm=10.0)
    target = tmp_path / "dimensioned.sectionlab"
    window.save_document(target)
    window.canvas.set_section(Section(outer=Contour(points=[])))
    assert window.canvas.dimensions() == []
    assert window.open_document(target) is True
    assert len(window.canvas.dimensions()) == 1
    assert window.canvas._dimension_text(window.canvas.dimensions()[0]) == "100.00"


def test_a_dimension_edit_moves_the_template_parameter_form(window: MainWindow) -> None:
    assert window.apply_template(TemplateKind.RECTANGLE.value) is True
    dimension = window.canvas.add_dimension(
        Anchor(ANCHOR_VERTEX, 0), Anchor(ANCHOR_VERTEX, 1), HORIZONTAL, offset_mm=20.0
    )
    assert window.canvas.drive_dimension(dimension.id, 300.0) is True
    assert window.section().template.params["b"] == pytest.approx(300.0)
    assert window.template_panel.params()["b"] == pytest.approx(300.0)


def test_dropping_a_dimension_is_explained(window: MainWindow) -> None:
    free_rectangle(window)
    window.canvas.add_dimension(ANCHOR_0, ANCHOR_1, SEGMENT_LENGTH, offset_mm=10.0)
    window.canvas.delete_vertex("outer", 0)
    assert window._message_label.text() == f"1 {strings.label_for('dimension_dropped')}"


def test_switching_template_kind_drops_the_placed_dimensions(window: MainWindow) -> None:
    assert window.apply_template(TemplateKind.RECTANGLE.value) is True
    window.canvas.add_dimension(ANCHOR_0, ANCHOR_1, HORIZONTAL, offset_mm=20.0)
    assert len(window.canvas.dimensions()) == 1
    assert window.apply_template(TemplateKind.CIRCLE.value) is True
    assert window.canvas.dimensions() == []
    assert strings.label_for("dimension_dropped") in window._message_label.text()


def test_rebuilding_the_same_template_keeps_its_dimensions(window: MainWindow) -> None:
    assert window.apply_template(TemplateKind.RECTANGLE.value) is True
    dimension = window.canvas.add_dimension(ANCHOR_0, ANCHOR_1, HORIZONTAL, offset_mm=20.0)
    assert window.apply_template(TemplateKind.RECTANGLE.value, {"b": 300.0, "h": 80.0}) is True
    assert [item.id for item in window.canvas.dimensions()] == [dimension.id]


# ------------------------------------------------- the snap buttons (spec S13)


@pytest.fixture()
def snap_store(monkeypatch) -> None:
    """Keep the persisted snap state out of the developer's own preferences."""
    from PySide6.QtCore import QSettings

    from sectionlab.ui import settings as settings_module

    monkeypatch.setattr(settings_module, "ORGANIZATION", "SectionLabTests")
    monkeypatch.setattr(settings_module, "APPLICATION", "snaps")
    QSettings("SectionLabTests", "snaps").clear()


def test_every_snap_family_has_a_button_and_they_start_on(window: MainWindow) -> None:
    actions = window.snap_actions()
    assert list(actions) == list(SNAP_KINDS)
    assert all(action.isChecked() for action in actions.values())
    assert all(action.isCheckable() for action in actions.values())
    assert window.enabled_snaps() == SNAP_KINDS


def test_a_snap_button_switches_only_its_own_family_off(window: MainWindow) -> None:
    window.snap_actions()[SnapKind.MIDPOINT].setChecked(False)
    assert SnapKind.MIDPOINT not in window.enabled_snaps()
    assert set(window.enabled_snaps()) == set(SNAP_KINDS) - {SnapKind.MIDPOINT}
    assert window.canvas.enabled_snaps() == frozenset(SNAP_KINDS) - {SnapKind.MIDPOINT}
    window.snap_actions()[SnapKind.MIDPOINT].setChecked(True)
    assert window.enabled_snaps() == SNAP_KINDS


def test_the_snap_state_is_remembered_between_runs(snap_store) -> None:
    from sectionlab.ui.settings import load_settings

    first = MainWindow(AppSettings(), interactive=True)
    first.snap_actions()[SnapKind.CENTER].setChecked(False)
    first.deleteLater()
    assert SnapKind.CENTER not in load_settings().snaps

    second = MainWindow(load_settings(), interactive=True)
    assert second.snap_actions()[SnapKind.CENTER].isChecked() is False
    assert second.snap_actions()[SnapKind.ENDPOINT].isChecked() is True
    assert SnapKind.CENTER not in second.enabled_snaps()
    second.deleteLater()
