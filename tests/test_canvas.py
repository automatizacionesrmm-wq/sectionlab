"""Canvas behaviour: drawing, snapping, editing and undo (specs S8, S14)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QWheelEvent

from sectionlab.core.model import Contour, Point, Section
from sectionlab.core.templates import TemplateKind, build_section
from sectionlab.core.snap import SnapKind
from sectionlab.core.units import Unit
from sectionlab.ui import strings
from sectionlab.ui.canvas import (
    GRID_STEPS,
    INNER,
    MAX_SCALE,
    MIN_GRID_PX,
    MIN_SCALE,
    OUTER,
    CanvasView,
    current_palette,
)
from sectionlab.ui.theme import Theme, tokens


@pytest.fixture()
def canvas(qtbot) -> CanvasView:
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(600, 400)
    view.apply_palette(tokens(Theme.DARK))
    return view


def free_section() -> Section:
    return Section(
        outer=Contour(
            points=[Point(0, 0), Point(100, 0), Point(100, 100), Point(0, 100)]
        )
    )


def test_a_new_canvas_is_empty(canvas: CanvasView) -> None:
    assert canvas.section().outer.points == []
    assert canvas.is_drawing() is False


def test_setting_a_section_shows_it_and_clears_undo(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.add_vertex(5, 5)
    assert canvas.undo_stack().count() == 1
    canvas.set_section(free_section())
    assert canvas.undo_stack().count() == 0
    assert len(canvas.section().outer.points) == 4


def test_model_coordinates_round_trip_through_the_scene(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    model, _ = canvas.snapped_point(QPointF(10, -10))
    assert (model.x, model.y) == pytest.approx((10.0, 10.0))


def test_vertices_snap_to_existing_endpoints(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.resetTransform()
    point, kind = canvas.snapped_point(QPointF(0.5, 0.3))
    assert kind is SnapKind.ENDPOINT
    assert (point.x, point.y) == (0.0, 0.0)


def test_snapping_respects_the_pixel_tolerance(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.resetTransform()
    canvas.scale(10, 10)
    far, kind = canvas.snapped_point(QPointF(40, -40))
    assert kind is None
    assert (far.x, far.y) == pytest.approx((40.0, 40.0))


def test_ortho_locks_the_segment_to_the_dominant_axis(canvas: CanvasView) -> None:
    canvas.set_section(Section(outer=Contour(points=[Point(0, 0)], closed=False)))
    canvas.set_ortho(True)
    point, _ = canvas.snapped_point(QPointF(50, -5))
    assert (point.x, point.y) == pytest.approx((50.0, 0.0))


def test_ortho_is_ignored_without_an_open_polyline(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.set_ortho(True)
    point, _ = canvas.snapped_point(QPointF(50, -5))
    assert (point.x, point.y) == pytest.approx((50.0, 5.0))


def test_begin_drawing_starts_an_open_contour(canvas: CanvasView) -> None:
    canvas.set_section(free_section(), fit=False)
    canvas.begin_drawing()
    assert canvas.is_drawing() is True
    assert canvas.section().outer.points == []


def test_adding_vertices_keeps_the_contour_open(canvas: CanvasView) -> None:
    canvas.begin_drawing()
    canvas.add_vertex(0, 0)
    canvas.add_vertex(100, 0)
    assert canvas.section().outer.closed is False
    assert len(canvas.section().outer.points) == 2


def test_closing_the_contour_finishes_the_polyline(canvas: CanvasView) -> None:
    canvas.begin_drawing()
    canvas.add_vertex(0, 0)
    canvas.add_vertex(100, 0)
    canvas.add_vertex(100, 100)
    canvas.close_contour()
    assert canvas.section().outer.closed is True
    assert canvas.is_drawing() is False


def test_cancelling_the_drawing_discards_it(canvas: CanvasView) -> None:
    canvas.begin_drawing()
    canvas.add_vertex(0, 0)
    canvas.add_vertex(10, 0)
    canvas.cancel_drawing()
    assert canvas.section().outer.points == []
    assert canvas.undo_stack().count() == 0


def test_inserting_a_vertex_in_the_middle(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.add_vertex(50, 50, index=2)
    assert [(p.x, p.y) for p in canvas.section().outer.points][2] == (50.0, 50.0)


def test_moving_a_vertex_updates_the_section(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.move_vertex(OUTER, 1, 120, 0)
    assert canvas.section().outer.points[1] == Point(120.0, 0.0)


def test_deleting_a_vertex_updates_the_section(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.delete_vertex(OUTER, 0)
    assert len(canvas.section().outer.points) == 3


def test_every_edit_is_undoable_and_redoable(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.move_vertex(OUTER, 1, 120, 0)
    canvas.undo_stack().undo()
    assert canvas.section().outer.points[1] == Point(100.0, 0.0)
    canvas.undo_stack().redo()
    assert canvas.section().outer.points[1] == Point(120.0, 0.0)


def test_deleting_a_vertex_can_be_undone(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.delete_vertex(OUTER, 2)
    canvas.undo_stack().undo()
    assert len(canvas.section().outer.points) == 4


def test_inner_contour_vertices_are_editable_too(canvas: CanvasView) -> None:
    section = build_section(TemplateKind.RECT_HOLLOW)
    canvas.set_section(section)
    assert section.inner is not None
    canvas.move_vertex(INNER, 0, 1, 1)
    assert canvas.section().inner is not None
    assert canvas.section().inner.points[0] == Point(1.0, 1.0)


def test_template_sections_are_not_editable(canvas: CanvasView) -> None:
    canvas.set_section(build_section(TemplateKind.RECTANGLE))
    canvas.set_editable(False)
    assert canvas.is_editable() is False
    canvas.begin_drawing()
    assert canvas.section().outer.points != []


def test_section_changes_are_announced(canvas: CanvasView, qtbot) -> None:
    canvas.set_section(free_section())
    with qtbot.waitSignal(canvas.sectionChanged, timeout=200):
        canvas.add_vertex(50, 50)


def test_vertex_selection_is_announced(canvas: CanvasView, qtbot) -> None:
    canvas.set_section(free_section())
    with qtbot.waitSignal(canvas.vertexSelected, timeout=200) as blocker:
        canvas.select_vertex(OUTER, 2)
    assert blocker.args == [OUTER, 2]
    assert canvas.selected_vertex() == (OUTER, 2)


def test_clicking_empty_space_starts_a_polyline(canvas: CanvasView, qtbot) -> None:
    canvas.set_section(Section(outer=Contour(points=[])), fit=False)
    canvas.resetTransform()
    qtbot.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(QPointF(10, -10)))
    assert canvas.is_drawing() is True
    assert len(canvas.section().outer.points) == 1


def test_dragging_a_handle_moves_the_vertex(canvas: CanvasView, qtbot) -> None:
    canvas.set_section(free_section(), fit=False)
    canvas.resetTransform()
    canvas.scale(2, 2)
    start = canvas.mapFromScene(QPointF(100, 0))
    qtbot.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas.viewport(), pos=canvas.mapFromScene(QPointF(140, 0)))
    qtbot.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(QPointF(140, 0)))
    assert canvas.section().outer.points[1].x == pytest.approx(140.0, abs=1.0)


def test_delete_key_removes_the_selected_vertex(canvas: CanvasView, qtbot) -> None:
    canvas.set_section(free_section())
    canvas.select_vertex(OUTER, 3)
    qtbot.keyClick(canvas, Qt.Key.Key_Delete)
    assert len(canvas.section().outer.points) == 3


def test_enter_closes_the_polyline(canvas: CanvasView, qtbot) -> None:
    canvas.begin_drawing()
    canvas.add_vertex(0, 0)
    canvas.add_vertex(50, 0)
    canvas.add_vertex(50, 50)
    qtbot.keyClick(canvas, Qt.Key.Key_Return)
    assert canvas.section().outer.closed is True


def test_escape_cancels_the_polyline(canvas: CanvasView, qtbot) -> None:
    canvas.begin_drawing()
    canvas.add_vertex(0, 0)
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    assert canvas.section().outer.points == []


def test_zoom_is_clamped(canvas: CanvasView) -> None:
    for _ in range(80):
        canvas.zoom_in()
    assert canvas.transform().m11() <= 1000.0 + 1e-6
    assert canvas.transform().m11() > 500.0
    for _ in range(200):
        canvas.zoom_out()
    assert canvas.transform().m11() >= 0.01 - 1e-6


def test_fit_shows_the_whole_section(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.fit_to_content()
    visible = canvas.mapToScene(canvas.viewport().rect()).boundingRect()
    assert visible.contains(QPointF(0, 0))
    assert visible.contains(QPointF(100, -100))


def _viewport_point(canvas: CanvasView, x: float, y: float) -> tuple[int, int]:
    point = canvas.mapFromScene(QPointF(x, -y))
    return point.x(), point.y()


def test_the_draft_line_survives_more_vertices(canvas: CanvasView, qtbot) -> None:
    canvas.begin_drawing()
    for x, y in ((0, 0), (100, 0), (100, 100)):
        px, py = _viewport_point(canvas, x, y)
        qtbot.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=type(canvas.viewport().rect().topLeft())(px, py))
    qtbot.mouseMove(canvas.viewport(), pos=type(canvas.viewport().rect().topLeft())(*_viewport_point(canvas, 0, 100)))
    draft = canvas.draft_line()
    assert draft is not None, "la línea guía desaparece después del segundo clic"
    last = canvas.section().outer.points[-1]
    assert draft.line().p1().x() == pytest.approx(last.x)
    assert draft.line().p1().y() == pytest.approx(-last.y)


def test_clicking_the_first_vertex_closes_the_polyline(canvas: CanvasView, qtbot) -> None:
    canvas.begin_drawing()
    for x, y in ((0, 0), (100, 0), (100, 100)):
        px, py = _viewport_point(canvas, x, y)
        qtbot.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=type(canvas.viewport().rect().topLeft())(px, py))
    first = canvas.section().outer.points[0]
    qtbot.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=type(canvas.viewport().rect().topLeft())(*_viewport_point(canvas, first.x, first.y)))
    assert canvas.is_drawing() is False
    assert canvas.section().outer.closed is True
    assert len(canvas.section().outer.points) == 3
    assert canvas.draft_line() is None


def test_the_view_starts_at_two_pixels_per_millimetre(canvas: CanvasView) -> None:
    canvas.reset_view()
    assert canvas.transform().m11() == pytest.approx(2.0)
    assert canvas.pixels_per_mm() == pytest.approx(2.0)


def test_the_grid_step_keeps_the_minor_lines_readable(canvas: CanvasView) -> None:
    canvas.reset_view()
    step = canvas.grid_step()
    assert step in GRID_STEPS
    assert step * canvas.pixels_per_mm() >= MIN_GRID_PX


def test_the_grid_coarsens_when_zoomed_out(canvas: CanvasView) -> None:
    canvas.reset_view()
    near = canvas.grid_step()
    canvas.scale(0.2, 0.2)
    assert canvas.grid_step() > near


def test_switching_theme_keeps_the_geometry(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.apply_palette(tokens(Theme.LIGHT))
    assert canvas.section() == free_section()
    assert len(canvas._nodes) == 4


def test_the_view_has_no_scrollbars_and_pans_freely(canvas: CanvasView) -> None:
    assert canvas.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert canvas.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert canvas.sceneRect().width() >= 100_000.0


def test_panning_moves_the_view_by_the_dragged_pixels(canvas: CanvasView) -> None:
    canvas.reset_view()
    before = canvas.mapToScene(canvas.viewport().rect().center())
    canvas.pan_by(40.0, -25.0)
    after = canvas.mapToScene(canvas.viewport().rect().center())
    assert after.x() == pytest.approx(before.x() - 40.0 / 2.0, abs=1.0)
    assert after.y() == pytest.approx(before.y() + 25.0 / 2.0, abs=1.0)


def test_dragging_with_the_middle_button_pans(canvas: CanvasView) -> None:
    canvas.reset_view()
    before = canvas.mapToScene(canvas.viewport().rect().center())

    def button_event(kind, pos: QPoint) -> QMouseEvent:
        point = QPointF(pos)
        return QMouseEvent(
            kind, point, point, Qt.MouseButton.MiddleButton, Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier,
        )

    start = QPoint(200, 150)
    canvas.mousePressEvent(button_event(QEvent.Type.MouseButtonPress, start))
    assert canvas.is_panning()
    canvas.mouseMoveEvent(button_event(QEvent.Type.MouseMove, start + QPoint(30, 20)))
    canvas.mouseReleaseEvent(button_event(QEvent.Type.MouseButtonRelease, start + QPoint(30, 20)))

    assert not canvas.is_panning()
    after = canvas.mapToScene(canvas.viewport().rect().center())
    assert after.x() == pytest.approx(before.x() - 15.0, abs=1.0)
    assert after.y() == pytest.approx(before.y() - 10.0, abs=1.0)


def test_zooming_keeps_the_point_under_the_cursor(canvas: CanvasView) -> None:
    canvas.reset_view()
    anchor = QPoint(180, 120)
    before = canvas.mapToScene(anchor)
    canvas.zoom_at(anchor, 1.5)
    assert canvas.pixels_per_mm() == pytest.approx(3.0)
    after = canvas.mapToScene(anchor)
    assert after.x() == pytest.approx(before.x(), abs=0.5)
    assert after.y() == pytest.approx(before.y(), abs=0.5)


def test_the_wheel_zooms_towards_the_cursor(canvas: CanvasView) -> None:
    canvas.reset_view()
    position = QPointF(150.0, 100.0)
    before = canvas.mapToScene(position.toPoint())
    wheel = QWheelEvent(
        position,
        QPointF(canvas.viewport().mapToGlobal(position.toPoint())),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    canvas.wheelEvent(wheel)
    assert canvas.pixels_per_mm() > 2.0
    after = canvas.mapToScene(position.toPoint())
    assert after.x() == pytest.approx(before.x(), abs=0.5)
    assert after.y() == pytest.approx(before.y(), abs=0.5)


def test_zooming_stops_at_the_limits(canvas: CanvasView) -> None:
    canvas.reset_view()
    for _ in range(200):
        canvas.zoom_in()
    assert canvas.pixels_per_mm() <= MAX_SCALE
    for _ in range(400):
        canvas.zoom_out()
    assert canvas.pixels_per_mm() >= MIN_SCALE


def test_double_clicking_with_the_middle_button_fits_the_content(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.reset_view()
    near = canvas.pixels_per_mm()
    point = QPointF(150.0, 100.0)
    canvas.mouseDoubleClickEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            point,
            point,
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert canvas.pixels_per_mm() != pytest.approx(near)
    assert canvas.transform().m11() > 0.0


def test_the_navigation_hint_names_the_mouse_gestures() -> None:
    from sectionlab.ui import strings

    hint = strings.label_for("hint_navigate")
    assert "Rueda" in hint and "botón central" in hint


def drawing_canvas(canvas: CanvasView) -> CanvasView:
    canvas.begin_drawing()
    for x, y in [(0, 0), (100, 0), (100, 100), (0, 100)]:
        canvas.add_vertex(float(x), float(y))
    return canvas


def left_press(canvas: CanvasView, x: float, y: float) -> None:
    position = canvas.mapFromScene(QPointF(x, -y))
    point = QPointF(position)
    canvas.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            point,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )


def right_press(canvas: CanvasView) -> None:
    point = QPointF(canvas.viewport().rect().center())
    canvas.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            point,
            point,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )


def test_a_click_near_the_first_vertex_closes_the_contour(canvas: CanvasView) -> None:
    canvas = drawing_canvas(canvas)
    offset = 10.0 / canvas.pixels_per_mm()
    left_press(canvas, offset, 0.0)
    assert not canvas.is_drawing()
    assert canvas.section().outer.closed


def test_a_click_far_from_the_first_vertex_adds_a_vertex(canvas: CanvasView) -> None:
    canvas = drawing_canvas(canvas)
    left_press(canvas, 60.0, 140.0)
    assert canvas.is_drawing()
    assert len(canvas.section().outer.points) == 5


def test_the_first_vertex_is_highlighted_as_the_closing_target(canvas: CanvasView) -> None:
    canvas = drawing_canvas(canvas)
    closing = QColor(current_palette()["ok"])
    assert canvas._nodes[0].brush().color() == closing
    assert canvas._nodes[1].brush().color() != closing


def test_the_context_button_closes_the_contour(canvas: CanvasView) -> None:
    canvas = drawing_canvas(canvas)
    right_press(canvas)
    assert canvas.section().outer.closed
    assert not canvas.is_drawing()


def test_the_context_button_cancels_a_short_polyline(canvas: CanvasView) -> None:
    canvas.begin_drawing()
    canvas.add_vertex(0.0, 0.0)
    right_press(canvas)
    assert not canvas.is_drawing()
    assert canvas.section().outer.points == []


def test_appending_the_first_point_closes_the_polyline(canvas: CanvasView) -> None:
    canvas = drawing_canvas(canvas)
    canvas.add_vertex(0.0, 0.0)
    assert not canvas.is_drawing()
    assert canvas.section().outer.closed
    assert len(canvas.section().outer.points) == 4


def test_a_point_next_to_the_first_one_is_still_appended(canvas: CanvasView) -> None:
    canvas = drawing_canvas(canvas)
    canvas.add_vertex(0.0, 5.0)
    assert canvas.is_drawing()
    assert len(canvas.section().outer.points) == 5


def test_two_points_cannot_close_into_a_contour(canvas: CanvasView) -> None:
    canvas.begin_drawing()
    canvas.add_vertex(0.0, 0.0)
    canvas.add_vertex(100.0, 0.0)
    canvas.add_vertex(0.0, 0.0)
    assert canvas.is_drawing()


# --------------------------------------------------------------- dimensions (specs S2, S4)


def test_the_canvas_measures_every_segment_it_draws(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    assert [round(dimension.value, 3) for dimension in canvas.dimensions()] == [100.0, 100.0, 100.0, 100.0]


def test_a_dimension_is_written_in_the_active_unit(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.set_display(Unit.CM, 2)
    assert [canvas._dimension_text(d) for d in canvas.dimensions()] == ["10.00"] * 4
    canvas.set_display(Unit.MM, 1)
    assert [canvas._dimension_text(d) for d in canvas.dimensions()] == ["100.0"] * 4


def test_dimensions_can_be_switched_off_without_losing_them(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    assert canvas.dimensions_visible()
    canvas.set_dimensions_visible(False)
    assert not canvas.dimensions_visible()
    assert len(canvas.dimensions()) == 4


def test_the_centroid_and_its_axes_are_kept_for_the_painter(canvas: CanvasView) -> None:
    assert canvas.centroid() is None
    canvas.set_centroid(50.0, 60.0, angle_deg=12.5)
    assert canvas.centroid() == (50.0, 60.0, 12.5)
    canvas.set_centroid(None)
    assert canvas.centroid() is None


def test_the_edited_value_highlights_the_matching_dimension(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.set_value_highlight(100.0, "b")
    assert canvas.value_highlight() == (100.0, "b")
    assert canvas._dimension_text(canvas.dimensions()[0]) == "b = 100.00"


def test_a_template_section_still_shows_its_dimensions(canvas: CanvasView) -> None:
    canvas.set_section(build_section(TemplateKind.RECTANGLE, {"width": 200.0, "height": 100.0}))
    assert len(canvas.dimensions()) == 4
    assert sorted({round(d.value, 3) for d in canvas.dimensions()}) == [100.0, 200.0]


def test_the_drawing_renders_with_dimensions_axes_and_a_centroid(canvas: CanvasView) -> None:
    """Paint the whole foreground once: dimensions, X/Y labels, centroid and snap glyph.

    Rendering is what catches an error inside the painter, which no state assertion sees.
    """
    canvas.set_section(build_section(TemplateKind.RECTANGLE, {"width": 200.0, "height": 100.0}))
    canvas.set_centroid(0.0, 50.0, angle_deg=15.0)
    canvas.set_value_highlight(200.0, "b")
    canvas._snap_kind = SnapKind.ENDPOINT
    canvas._cursor_scene = QPointF(100.0, 0.0)
    canvas.select_vertex(OUTER, 1)
    pixmap = canvas.grab()
    assert not pixmap.isNull()
    image = pixmap.toImage()
    colours = {image.pixelColor(x, y).name() for x in range(0, image.width(), 7) for y in range(0, image.height(), 7)}
    # The centroid marker and the dimension text must actually reach the screen.
    assert tokens(Theme.DARK)["centroid"].lower() in colours
    assert len(colours) > 5


# ------------------------------------------------ parametric dimensions (specs S3, S6)


def test_double_clicking_a_dimension_opens_its_editor_prefilled(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.set_display(Unit.CM, 2)
    dimension = canvas.dimensions()[0]
    centre = canvas._dimension_box(dimension).center()
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPointF(centre),
        QPointF(centre),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mouseDoubleClickEvent(event)
    assert canvas.has_dimension_editor()
    editor = canvas._dimension_editor
    assert editor is not None
    assert editor.text() == "10.00"
    editor.setText("12.5")
    editor.returnPressed.emit()
    assert not canvas.has_dimension_editor()
    assert canvas.section().outer.points[1] == Point(125.0, 0)


def test_typing_a_dimension_moves_the_geometry_in_one_undo_step(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    assert canvas.apply_dimension_length(0, 150.0) is True
    points = canvas.section().outer.points
    assert points[0] == Point(0, 0)
    assert points[1] == Point(150, 0)
    assert len(points) == 4
    assert canvas.undo_stack().undoText() == strings.label_for("undo_dimension")
    canvas.undo_stack().undo()
    assert canvas.section().outer.points[1] == Point(100, 0)


def test_the_unit_typed_is_the_unit_read_back(canvas: CanvasView) -> None:
    """A dimension typed in centimetres must read back as the same number (spec S2)."""
    canvas.set_section(free_section())
    canvas.set_display(Unit.CM, 2)
    assert canvas.apply_dimension_length(0, 25.0 * 10) is True
    assert canvas._dimension_text(canvas.dimensions()[0]) == "25.00"
    canvas.set_display(Unit.IN, 3)
    assert canvas._dimension_text(canvas.dimensions()[0]) == "9.843"


@pytest.mark.parametrize(
    ("index", "length", "code"),
    [
        (3, 10.0, "closing_segment"),
        (0, 0.0, "non_positive"),
        (0, 100.0, "unchanged"),
        (9, 10.0, "out_of_range"),
    ],
)
def test_a_refused_dimension_reports_its_reason(canvas: CanvasView, index, length, code) -> None:
    canvas.set_section(free_section())
    seen: list[str] = []
    canvas.editRejected.connect(seen.append)
    assert canvas.apply_dimension_length(index, length) is False
    assert seen == [code]


def test_a_slanted_segment_cannot_be_dimensioned(canvas: CanvasView) -> None:
    canvas.set_section(
        Section(outer=Contour(points=[Point(0, 0), Point(30, 40), Point(0, 40)]))
    )
    seen: list[str] = []
    canvas.editRejected.connect(seen.append)
    assert canvas.apply_dimension_length(0, 60.0) is False
    assert seen == ["slanted_segment"]


def test_a_template_section_sends_the_edit_back_to_its_parameters(canvas: CanvasView) -> None:
    canvas.set_section(build_section(TemplateKind.RECTANGLE, {"width": 200.0, "height": 100.0}))
    canvas.set_editable(False)
    seen: list[str] = []
    canvas.editRejected.connect(seen.append)
    assert canvas.apply_dimension_length(0, 300.0) is False
    assert seen == ["read_only"]
    assert canvas.dimension_at(QPoint(10, 10)) is None


def test_a_dimension_typed_as_text_is_parsed_in_the_active_unit(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.set_display(Unit.CM, 2)
    dimension = canvas.dimensions()[0]
    assert canvas.begin_dimension_edit(dimension) is True
    editor = canvas._dimension_editor
    assert editor is not None
    editor.setText("2,5")
    editor.returnPressed.emit()
    assert canvas.section().outer.points[1] == Point(25.0, 0)


def test_a_dimension_that_is_not_a_number_is_refused(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    seen: list[str] = []
    canvas.editRejected.connect(seen.append)
    dimension = canvas.dimensions()[0]
    assert canvas.begin_dimension_edit(dimension) is True
    editor = canvas._dimension_editor
    assert editor is not None
    editor.setText("ancho")
    editor.returnPressed.emit()
    assert seen == ["not_a_number"]
    assert canvas.section().outer.points[1] == Point(100, 0)


def test_escape_abandons_a_dimension_edit(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    dimension = canvas.dimensions()[0]
    assert canvas.begin_dimension_edit(dimension) is True
    canvas.close_dimension_editor()
    assert canvas.has_dimension_editor() is False
    assert canvas.section().outer.points[1] == Point(100, 0)
