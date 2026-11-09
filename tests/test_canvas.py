"""Canvas behaviour: drawing, snapping, editing and undo (specs S8, S14)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt

from sectionlab.core.model import Contour, Point, Section
from sectionlab.core.templates import TemplateKind, build_section
from sectionlab.core.snap import SnapKind
from sectionlab.ui.canvas import INNER, OUTER, CanvasView


@pytest.fixture()
def canvas(qtbot) -> CanvasView:
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(600, 400)
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
