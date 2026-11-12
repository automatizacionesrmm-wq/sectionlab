"""Canvas behaviour: drawing, snapping, editing and undo (specs S8, S14)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QWheelEvent

from sectionlab.core.dimensions import (
    ANCHOR_VERTEX,
    HORIZONTAL,
    SEGMENT_LENGTH,
    VERTICAL,
    Anchor,
)
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


# ------------------------------------------------------------ placed dimensions (S1, S3)


def place(canvas: CanvasView, first: int, second: int, kind: str, offset_mm: float = 12.0):
    return canvas.add_dimension(
        Anchor(ANCHOR_VERTEX, first), Anchor(ANCHOR_VERTEX, second), kind, offset_mm=offset_mm
    )


def place_segment(canvas: CanvasView, index: int, kind: str = SEGMENT_LENGTH):
    count = len(canvas.section().outer.points)
    return place(canvas, index, (index + 1) % count, kind)


def mouse_event(kind: QEvent.Type, point) -> QMouseEvent:
    return QMouseEvent(
        kind,
        QPointF(point),
        QPointF(point),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_a_section_starts_without_any_dimension(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    assert canvas.dimensions() == []


def test_a_placed_dimension_is_measured_from_the_geometry(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    place_segment(canvas, 0)
    assert [canvas._dimension_text(item) for item in canvas.dimensions()] == ["100.00"]


def test_a_dimension_is_written_in_the_active_unit(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    place_segment(canvas, 0)
    canvas.set_display(Unit.CM, 2)
    assert canvas._dimension_text(canvas.dimensions()[0]) == "10.00"
    canvas.set_display(Unit.MM, 1)
    assert canvas._dimension_text(canvas.dimensions()[0]) == "100.0"


def test_dimensions_can_be_switched_off_without_losing_them(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    place_segment(canvas, 0)
    place_segment(canvas, 1)
    assert canvas.dimensions_visible()
    canvas.set_dimensions_visible(False)
    assert not canvas.dimensions_visible()
    assert len(canvas.dimensions()) == 2


def test_the_centroid_and_its_axes_are_kept_for_the_painter(canvas: CanvasView) -> None:
    assert canvas.centroid() is None
    canvas.set_centroid(50.0, 60.0, angle_deg=12.5)
    assert canvas.centroid() == (50.0, 60.0, 12.5)
    canvas.set_centroid(None)
    assert canvas.centroid() is None


def test_the_edited_value_highlights_the_matching_dimension(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    place_segment(canvas, 0)
    canvas.set_value_highlight(100.0, "b")
    assert canvas.value_highlight() == (100.0, "b")
    assert canvas._dimension_text(canvas.dimensions()[0]) == "b = 100.00"


def test_a_template_section_can_carry_its_own_dimension(canvas: CanvasView) -> None:
    canvas.set_section(build_section(TemplateKind.RECTANGLE, {"b": 200.0, "h": 100.0}))
    canvas.set_editable(False)
    place(canvas, 0, 1, HORIZONTAL)
    assert canvas._dimension_text(canvas.dimensions()[0]) == "200.00"


def test_the_drawing_renders_with_dimensions_axes_and_a_centroid(canvas: CanvasView) -> None:
    """Paint the whole foreground once: dimensions, guides, X/Y labels and a centroid.

    Rendering is what catches an error inside the painter, which no state assertion sees.
    """
    canvas.set_section(build_section(TemplateKind.RECTANGLE, {"b": 200.0, "h": 100.0}))
    canvas.set_centroid(0.0, 50.0, angle_deg=15.0)
    canvas.set_value_highlight(200.0, "b")
    canvas.set_editable(True)
    place(canvas, 0, 1, HORIZONTAL)
    canvas.fit_to_content()
    canvas._snap_kind = SnapKind.ENDPOINT
    canvas._cursor_scene = QPointF(100.0, -40.0)
    canvas.snapped_point(QPointF(100.0, -40.0))
    canvas.select_vertex(OUTER, 1)
    pixmap = canvas.grab()
    assert not pixmap.isNull()
    image = pixmap.toImage()
    colours = {
        image.pixelColor(x, y).name()
        for x in range(0, image.width(), 7)
        for y in range(0, image.height(), 7)
    }
    assert tokens(Theme.DARK)["centroid"].lower() in colours
    assert len(colours) > 5


# ------------------------------------------------------ a dimension drives (S5, S6, S9)


def test_placing_a_dimension_and_driving_it_is_one_undo_step(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    dimension = place_segment(canvas, 0)
    assert canvas.undo_stack().undoText() == strings.label_for("undo_dimension_add")
    assert canvas.drive_dimension(dimension.id, 150.0) is True
    assert canvas.section().outer.points[1] == Point(150, 0)
    assert canvas.undo_stack().undoText() == strings.label_for("undo_dimension")
    canvas.undo_stack().undo()
    assert canvas.section().outer.points[1] == Point(100, 0)
    assert len(canvas.dimensions()) == 1


def test_a_driven_value_is_read_back_from_the_geometry(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    dimension = place_segment(canvas, 0)
    canvas.drive_dimension(dimension.id, 250.0)
    assert canvas._dimension_text(canvas.dimensions()[0]) == "250.00"


@pytest.mark.parametrize(
    ("index", "length", "code"),
    [
        (3, 10.0, "closing_segment"),
        (0, 0.0, "non_positive"),
        (0, 100.0, "unchanged"),
    ],
)
def test_a_refused_drive_reports_its_reason(canvas: CanvasView, index, length, code) -> None:
    canvas.set_section(free_section())
    dimension = place_segment(canvas, index)
    seen: list[str] = []
    canvas.editRejected.connect(seen.append)
    assert canvas.drive_dimension(dimension.id, length) is False
    assert seen == [code]


def test_a_slanted_segment_dimension_is_reference_only(canvas: CanvasView) -> None:
    canvas.set_section(Section(outer=Contour(points=[Point(0, 0), Point(30, 40), Point(0, 40)])))
    dimension = place_segment(canvas, 0)
    assert canvas.can_drive(dimension) is False
    assert canvas.begin_dimension_edit(dimension) is False
    seen: list[str] = []
    canvas.editRejected.connect(seen.append)
    assert canvas.drive_dimension(dimension.id, 60.0) is False
    assert seen == ["slanted_segment"]


def test_a_dimension_on_a_template_moves_its_parameter(canvas: CanvasView) -> None:
    canvas.set_section(build_section(TemplateKind.RECTANGLE, {"b": 200.0, "h": 100.0}))
    canvas.set_editable(False)
    dimension = place(canvas, 0, 1, HORIZONTAL)
    assert canvas.drive_dimension(dimension.id, 300.0) is True
    assert canvas.section().template.params["b"] == pytest.approx(300.0)
    assert max(point.x for point in canvas.section().outer.points) == pytest.approx(300.0)
    assert canvas._dimension_text(canvas.dimensions()[0]) == "300.00"


def test_a_dimension_a_template_cannot_drive_is_refused(canvas: CanvasView) -> None:
    canvas.set_section(build_section(TemplateKind.I_PROFILE))
    canvas.set_editable(False)
    dimension = place(canvas, 3, 4, VERTICAL)
    seen: list[str] = []
    canvas.editRejected.connect(seen.append)
    assert canvas.can_drive(dimension) is False
    assert canvas.drive_dimension(dimension.id, 120.0) is False
    assert seen == ["not_drivable"]


def test_deleting_a_selected_dimension_is_undoable(canvas: CanvasView, qtbot) -> None:
    canvas.set_section(free_section())
    dimension = place_segment(canvas, 0)
    canvas.select_dimension(dimension.id)
    qtbot.keyClick(canvas, Qt.Key.Key_Delete)
    assert canvas.dimensions() == []
    assert canvas.undo_stack().undoText() == strings.label_for("undo_dimension_delete")
    canvas.undo_stack().undo()
    assert [item.id for item in canvas.dimensions()] == [dimension.id]


def test_dragging_the_text_moves_the_line_and_not_the_geometry(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.fit_to_content()
    dimension = place_segment(canvas, 0)
    centre = canvas._dimension_box(dimension).center()
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, centre))
    target = canvas.mapFromScene(QPointF(50.0, -30.0))
    canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, target))
    canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, target))
    moved = canvas.dimensions()[0]
    assert moved.offset_mm == pytest.approx(-30.0, abs=0.5)
    assert canvas.section().outer.points[1] == Point(100, 0)


# ------------------------------------------------------------------ editor (S5, S7)


def test_double_clicking_a_dimension_opens_its_editor_prefilled(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    dimension = place_segment(canvas, 0)
    centre = canvas._dimension_box(dimension).center()
    canvas.mouseDoubleClickEvent(mouse_event(QEvent.Type.MouseButtonDblClick, centre))
    assert canvas.has_dimension_editor()
    editor = canvas._dimension_editor
    assert editor is not None
    assert editor.text() == "100.00"
    editor.setText("125")
    editor.returnPressed.emit()
    assert not canvas.has_dimension_editor()
    assert canvas.section().outer.points[1] == Point(125, 0)


def test_the_unit_typed_is_the_unit_read_back(canvas: CanvasView) -> None:
    """A dimension typed in centimetres must read back as the same number."""
    canvas.set_section(free_section())
    dimension = place_segment(canvas, 0)
    canvas.set_display(Unit.CM, 2)
    assert canvas.begin_dimension_edit(dimension) is True
    assert canvas._dimension_editor is not None
    canvas._dimension_editor.setText("25")
    canvas._dimension_editor.returnPressed.emit()
    assert canvas._dimension_text(canvas.dimensions()[0]) == "25.00"
    canvas.set_display(Unit.IN, 3)
    assert canvas._dimension_text(canvas.dimensions()[0]) == "9.843"


def test_a_dimension_typed_as_text_is_parsed_in_the_active_unit(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    dimension = place_segment(canvas, 0)
    canvas.set_display(Unit.CM, 2)
    assert canvas.begin_dimension_edit(dimension) is True
    editor = canvas._dimension_editor
    assert editor is not None
    editor.setText("2,5")
    editor.returnPressed.emit()
    assert canvas.section().outer.points[1] == Point(25.0, 0)


def test_a_dimension_that_is_not_a_number_is_refused(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    dimension = place_segment(canvas, 0)
    seen: list[str] = []
    canvas.editRejected.connect(seen.append)
    assert canvas.begin_dimension_edit(dimension) is True
    editor = canvas._dimension_editor
    assert editor is not None
    editor.setText("ancho")
    editor.returnPressed.emit()
    assert seen == ["not_a_number"]
    assert canvas.section().outer.points[1] == Point(100, 0)


def test_escape_abandons_a_dimension_edit(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    dimension = place_segment(canvas, 0)
    assert canvas.begin_dimension_edit(dimension) is True
    canvas.close_dimension_editor()
    assert canvas.has_dimension_editor() is False
    assert canvas.section().outer.points[1] == Point(100, 0)


# ------------------------------------------------- references follow the geometry (S10)


def test_inserting_a_vertex_keeps_the_dimension_attached(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    place_segment(canvas, 1)
    canvas.add_vertex(50.0, 0.0, index=0)
    kept = canvas.dimensions()[0]
    assert (kept.first.index, kept.second.index) == (2, 3)


def test_deleting_the_anchored_vertex_drops_the_dimension_and_says_so(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    place_segment(canvas, 0)
    dropped: list[int] = []
    canvas.dimensionsDropped.connect(dropped.append)
    canvas.delete_vertex(OUTER, 0)
    assert canvas.dimensions() == []
    assert dropped == [1]


# ------------------------------------------------------------ the dimension tool (S2)


def test_a_click_on_an_edge_measures_that_edge_in_two_clicks(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.fit_to_content()
    assert canvas.begin_dimension_tool() is True
    edge = canvas.mapFromScene(QPointF(50.0, 0.0))
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, edge))
    assert len(canvas.pending_anchors()) == 2
    outside = canvas.mapFromScene(QPointF(50.0, -25.0))
    canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, outside))
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, outside))
    assert len(canvas.dimensions()) == 1
    dimension = canvas.dimensions()[0]
    assert dimension.kind == SEGMENT_LENGTH
    assert dimension.offset_mm == pytest.approx(-25.0, abs=0.5)
    assert canvas.pending_anchors() == ()


def test_two_vertices_make_a_distance_dimension(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.fit_to_content()
    canvas.begin_dimension_tool()
    first = canvas.mapFromScene(QPointF(0.0, 0.0))
    second = canvas.mapFromScene(QPointF(100.0, -100.0))
    outside = canvas.mapFromScene(QPointF(160.0, -50.0))
    for point in (first, second):
        canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, point))
    canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, outside))
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, outside))
    dimension = canvas.dimensions()[0]
    assert dimension.kind == HORIZONTAL
    assert canvas._dimension_text(dimension) == "100.00"


def test_escape_leaves_the_tool(canvas: CanvasView, qtbot) -> None:
    canvas.set_section(free_section())
    assert canvas.begin_dimension_tool() is True
    assert canvas.is_placing_dimension() is True
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    assert canvas.is_placing_dimension() is False


def test_the_tool_needs_a_section(canvas: CanvasView) -> None:
    assert canvas.begin_dimension_tool() is False


# ------------------------------------------------------- alignment guides (S12)


def test_guides_lock_the_cursor_to_a_vertex_coordinate(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.reset_view()
    assert canvas.guides_visible()
    point, kind = canvas.snapped_point(QPointF(103.0, -40.0))
    assert kind is None
    assert point.x == pytest.approx(100.0)
    assert canvas.guides_label().startswith("X con")


def test_a_snap_point_wins_over_a_guide(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.reset_view()
    point, kind = canvas.snapped_point(QPointF(1.0, -1.0))
    assert kind is SnapKind.ENDPOINT
    assert point == Point(0.0, 0.0)
    assert canvas.current_guides() == []


def test_guides_can_be_switched_off(canvas: CanvasView) -> None:
    canvas.set_section(free_section())
    canvas.reset_view()
    canvas.set_guides_visible(False)
    point, kind = canvas.snapped_point(QPointF(103.0, -40.0))
    assert kind is None
    assert point.x == pytest.approx(103.0)
    assert canvas.current_guides() == []


# ------------------------------------------------- CAD input on a picked edge (spec S9)


def rectangle_canvas(qtbot):
    canvas = CanvasView()
    qtbot.addWidget(canvas)
    canvas.resize(600, 400)
    canvas.set_section(
        Section(outer=Contour(points=[Point(0, 0), Point(100, 0), Point(100, 60), Point(0, 60)], closed=True))
    )
    canvas.set_editable(True)
    canvas.fit_to_content()
    return canvas


def click_edge(canvas, x: float, y: float) -> None:
    scene_pos = QPointF(x, -y)
    point = canvas.mapFromScene(scene_pos)
    qtbot_press(canvas, point)


def qtbot_press(canvas, point) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(point),
        canvas.viewport().mapToGlobal(QPointF(point)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(event)


def test_clicking_an_edge_selects_that_segment(qtbot) -> None:
    canvas = rectangle_canvas(qtbot)
    click_edge(canvas, 50.0, 0.0)
    assert canvas.selected_segment() == ("outer", 0)


def test_typing_a_number_on_a_selected_edge_changes_its_length(qtbot) -> None:
    canvas = rectangle_canvas(qtbot)
    canvas.add_dimension(
        Anchor(ANCHOR_VERTEX, 0), Anchor(ANCHOR_VERTEX, 1), SEGMENT_LENGTH, offset_mm=10.0
    )
    click_edge(canvas, 50.0, 0.0)
    qtbot.keyClick(canvas, Qt.Key.Key_1)
    assert canvas.has_dimension_editor()
    for key in (Qt.Key.Key_5, Qt.Key.Key_0):
        qtbot.keyClick(canvas._dimension_editor, key)
    qtbot.keyClick(canvas._dimension_editor, Qt.Key.Key_Return)
    points = canvas.section().outer.points
    assert points[1].x == pytest.approx(150.0)
    assert canvas.undo_stack().undoText() == strings.label_for("undo_dimension")


def test_typing_a_number_on_a_slanted_edge_is_refused(qtbot) -> None:
    canvas = CanvasView()
    qtbot.addWidget(canvas)
    canvas.resize(600, 400)
    canvas.set_section(
        Section(outer=Contour(points=[Point(0, 0), Point(100, 0), Point(100, 60), Point(0, 120)], closed=True))
    )
    canvas.set_editable(True)
    canvas.fit_to_content()
    canvas.add_dimension(
        Anchor(ANCHOR_VERTEX, 2), Anchor(ANCHOR_VERTEX, 3), SEGMENT_LENGTH, offset_mm=10.0
    )
    refused: list[str] = []
    canvas.editRejected.connect(refused.append)
    canvas.select_segment("outer", 2)  # the slanted one
    qtbot.keyClick(canvas, Qt.Key.Key_9)
    assert canvas.has_dimension_editor() is False
    assert refused == ["segment_not_editable"]


def test_selecting_a_vertex_drops_the_picked_edge(qtbot) -> None:
    canvas = rectangle_canvas(qtbot)
    click_edge(canvas, 50.0, 0.0)
    canvas.select_vertex("outer", 2)
    assert canvas.selected_segment() is None
