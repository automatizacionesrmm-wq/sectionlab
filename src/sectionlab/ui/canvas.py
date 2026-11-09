"""Drawing canvas: contours, vertex handles, snapping and undo.

Scene coordinates are millimetres with the y axis pointing down, so the model y axis is
negated on the way in and out. Every edit is a snapshot pushed onto a `QUndoStack`, which
keeps undo/redo exact for small sections (spec S8, S14).
"""

from __future__ import annotations

from dataclasses import replace
from math import hypot
from typing import Mapping

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
)

from sectionlab.core.model import Contour, Point, Section
from sectionlab.core.snap import SnapKind, apply_ortho, candidates, find_snap
from sectionlab.ui import theme as ui_theme

OUTER = "outer"
INNER = "inner"

SNAP_TOLERANCE_PX = 8.0
NODE_RADIUS_PX = 4.0
NODE_HIT_PX = 9.0
ZOOM_STEP = 1.15
MIN_SCALE = 0.01
MAX_SCALE = 1000.0
GRID_STEPS = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0)
MIN_GRID_PX = 7.0

_PALETTE: dict[str, str] = dict(ui_theme.DARK)

_OUTER_PEN = QPen(QColor(_PALETTE["contour"]), 2)
_OUTER_PEN.setCosmetic(True)
_INNER_PEN = QPen(QColor(_PALETTE["inner"]), 1.6, Qt.PenStyle.DashLine)
_INNER_PEN.setCosmetic(True)
_DRAFT_PEN = QPen(QColor(_PALETTE["draft"]), 1.2, Qt.PenStyle.DashLine)
_DRAFT_PEN.setCosmetic(True)


def set_palette(palette: Mapping[str, str]) -> None:
    """Recolour every pen the canvas owns from one theme's tokens."""
    _PALETTE.clear()
    _PALETTE.update(palette)
    _OUTER_PEN.setColor(QColor(_PALETTE["contour"]))
    _INNER_PEN.setColor(QColor(_PALETTE["inner"]))
    _DRAFT_PEN.setColor(QColor(_PALETTE["draft"]))


def palette() -> dict[str, str]:
    return dict(_PALETTE)


class _NodeItem(QGraphicsEllipseItem):
    """Drawn vertex handle: a constant-size dot that knows which vertex it represents."""

    def __init__(self, contour: str, index: int) -> None:
        super().__init__(-NODE_RADIUS_PX, -NODE_RADIUS_PX, 2 * NODE_RADIUS_PX, 2 * NODE_RADIUS_PX)
        self.contour = contour
        self.index = index
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setBrush(QBrush(QColor(_PALETTE["handle"])))
        outline = _PALETTE["contour"] if contour == OUTER else _PALETTE["inner"]
        self.setPen(QPen(QColor(outline), 1.4))
        self.setZValue(10)


class _ContourItem(QGraphicsPathItem):
    """The polylines and hatch-free outline of one contour."""

    def __init__(self, contour: Contour, inner: bool) -> None:
        super().__init__()
        path = QPainterPath()
        points = contour.points
        if points:
            path.moveTo(points[0].x, -points[0].y)
            for point in points[1:]:
                path.lineTo(point.x, -point.y)
            if contour.closed and len(points) > 2:
                path.closeSubpath()
        self.setPath(path)
        self.setPen(_INNER_PEN if inner else _OUTER_PEN)
        if not inner and contour.closed:
            self.setBrush(QBrush(QColor(_PALETTE["contour_fill"])))
        self.setZValue(1)


class _EditCommand(QUndoCommand):
    """Snapshot command: applying a whole section is exact and cheap at this scale."""

    def __init__(self, canvas: "CanvasView", before: Section, after: Section, text: str) -> None:
        super().__init__(text)
        self._canvas = canvas
        self._before = before
        self._after = after

    def redo(self) -> None:  # noqa: D102 - Qt override
        self._canvas._apply_section(self._after)

    def undo(self) -> None:  # noqa: D102 - Qt override
        self._canvas._apply_section(self._before)


class CanvasView(QGraphicsView):
    """Editable top view of a section, in millimetres."""

    sectionChanged = Signal()
    cursorMoved = Signal(float, float)
    snapChanged = Signal(str)
    vertexSelected = Signal(str, int)
    drawingChanged = Signal(bool)

    def __init__(self, parent: QGraphicsView | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setBackgroundBrush(QBrush(QColor(_PALETTE["canvas"])))
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)

        self._section = Section(outer=Contour(points=[]))
        self._editable = True
        self._ortho = False
        self._nodes: list[_NodeItem] = []
        self._contour_items: list[_ContourItem] = []
        self._rubber: QGraphicsLineItem | None = None
        self._drag: tuple[str, int, _NodeItem, Point] | None = None
        self._drawing = False
        self._selected: tuple[str, int] | None = None
        self._undo = QUndoStack(self)
        self._snap = None
        self._cursor_scene: QPointF | None = None
        self._snap_marker: QGraphicsEllipseItem | None = None
        self._rebuild()

    # ------------------------------------------------------------------ public API

    def section(self) -> Section:
        """The section currently drawn, in millimetres."""
        return self._section

    def undo_stack(self) -> QUndoStack:
        return self._undo

    def set_editable(self, editable: bool) -> None:
        """Free geometry can be edited; template sections are regenerated from parameters."""
        self._editable = editable
        for node in self._nodes:
            node.setVisible(editable)

    def is_editable(self) -> bool:
        return self._editable

    def set_ortho(self, enabled: bool) -> None:
        self._ortho = enabled

    def is_ortho(self) -> bool:
        return self._ortho

    def set_section(self, section: Section, *, record: bool = False, fit: bool = True) -> None:
        """Replace the drawing, optionally as an undoable edit."""
        if record:
            self._commit(section, "section")
        else:
            self._undo.clear()
            self._apply_section(section)
        if fit:
            self.fit_to_content()

    def is_drawing(self) -> bool:
        """True while the outer contour is an open polyline being drawn."""
        return self._drawing

    def begin_drawing(self) -> None:
        """Start an open polyline to be closed with `close_contour`."""
        if not self._editable:
            return
        if self._drawing:
            return
        self.set_section(Section(outer=Contour(points=[], closed=False)), fit=False)
        self._drawing = True
        self.drawingChanged.emit(True)

    def add_vertex(self, x: float, y: float, contour: str = OUTER, index: int | None = None) -> None:
        """Insert a vertex, appending when `index` is `None`."""
        target = self._contour(contour)
        points = list(target.points)
        position = len(points) if index is None else index
        position = max(0, min(position, len(points)))
        points.insert(position, Point(float(x), float(y)))
        self._replace_contour(contour, replace(target, points=points), "add vertex")

    def move_vertex(self, contour: str, index: int, x: float, y: float) -> None:
        """Move an existing vertex to the given millimetre position."""
        target = self._contour(contour)
        points = list(target.points)
        points[index] = Point(float(x), float(y))
        self._replace_contour(contour, replace(target, points=points), "move vertex")

    def delete_vertex(self, contour: str, index: int) -> None:
        """Remove one vertex from the given contour."""
        target = self._contour(contour)
        points = list(target.points)
        del points[index]
        self._replace_contour(contour, replace(target, points=points), "delete vertex")

    def close_contour(self) -> None:
        """Finish the polyline being drawn: the last vertex joins the first one."""
        if not self.is_drawing():
            return
        points = list(self._section.outer.points)
        while len(points) > 2 and points[-1] == points[-2]:
            points.pop()
        self._drawing = False
        contour = replace(self._section.outer, points=points, closed=True)
        self._replace_contour(OUTER, contour, "close contour")
        self.drawingChanged.emit(False)

    def cancel_drawing(self) -> None:
        """Discard the polyline being drawn."""
        if not self._drawing:
            return
        self._drawing = False
        self.set_section(Section(outer=Contour(points=[])), fit=False)
        self.drawingChanged.emit(False)

    def draft_line(self) -> QGraphicsLineItem | None:
        """The dashed guide from the last vertex to the cursor while drawing."""
        return self._rubber

    def selected_vertex(self) -> tuple[str, int] | None:
        return self._selected

    def select_vertex(self, contour: str, index: int) -> None:
        """Highlight one vertex; `vertexSelected` is emitted for the window's vertex table."""
        self._selected = (contour, index)
        self._paint_selection()
        self.vertexSelected.emit(contour, index)

    def clear_selection(self) -> None:
        self._selected = None
        self._paint_selection()
        self.vertexSelected.emit("", -1)

    def pixels_per_mm(self) -> float:
        """Current zoom, used to translate the pixel snap tolerance into millimetres."""
        return max(self.transform().m11(), 1e-9)

    def snapped_point(self, scene_pos: QPointF) -> tuple[Point, SnapKind | None]:
        """Model point under the cursor after snapping and the ortho constraint."""
        model = Point(scene_pos.x(), -scene_pos.y())
        anchor = self._last_vertex()
        if self._ortho and anchor is not None:
            model = apply_ortho(anchor, model)

        tolerance = SNAP_TOLERANCE_PX / self.pixels_per_mm()
        contours = [c for c in (self._section.outer, self._section.inner) if c and c.points]
        found = find_snap(model, candidates(contours), tolerance)
        if found is None:
            return model, None
        return found.point, found.kind

    def fit_to_content(self) -> None:
        """Zoom so the whole section is visible with a margin."""
        rect = self._scene.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            self.reset_view()
            return
        self.fitInView(
            rect.adjusted(-rect.width() * 0.05, -rect.height() * 0.05, rect.width() * 0.05, rect.height() * 0.05),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self.viewport().update()

    def reset_view(self) -> None:
        """The starting view: two pixels per millimetre, centred on the model origin."""
        self.resetTransform()
        self.scale(2.0, 2.0)
        self.centerOn(0.0, 0.0)
        self.viewport().update()

    # -------------------------------------------------------------- model plumbing

    def _contour(self, name: str) -> Contour:
        if name == INNER:
            if self._section.inner is None:
                raise ValueError("the section has no inner contour")
            return self._section.inner
        return self._section.outer

    def _last_vertex(self) -> Point | None:
        points = self._section.outer.points
        if not points or not self._drawing:
            return None
        return points[-1]

    def _replace_contour(self, name: str, contour: Contour, text: str) -> None:
        if name == INNER:
            updated = replace(self._section, inner=contour)
        else:
            updated = replace(self._section, outer=contour)
        self._commit(updated, text)

    def _commit(self, section: Section, text: str) -> None:
        self._undo.push(_EditCommand(self, self._section, section, text))

    def _apply_section(self, section: Section) -> None:
        self._section = section
        self._drawing = not section.outer.closed and bool(section.outer.points)
        self._rebuild()
        self.sectionChanged.emit()

    def _rebuild(self) -> None:
        self._scene.clear()
        self._nodes = []
        self._contour_items = []
        self._rubber = None

        for name, contour, is_inner in (
            (OUTER, self._section.outer, False),
            (INNER, self._section.inner, True),
        ):
            if contour is None or not contour.points:
                continue
            item = _ContourItem(contour, is_inner)
            self._scene.addItem(item)
            self._contour_items.append(item)
            for index, point in enumerate(contour.points):
                node = _NodeItem(name, index)
                node.setPos(point.x, -point.y)
                node.setVisible(self._editable)
                self._scene.addItem(node)
                self._nodes.append(node)
        if self._drawing:
            self._rubber = QGraphicsLineItem()
            self._rubber.setPen(_DRAFT_PEN)
            self._rubber.setZValue(-1)
            self._scene.addItem(self._rubber)
            anchor = self._last_vertex()
            if anchor is not None:
                self._rubber.setLine(anchor.x, -anchor.y, anchor.x, -anchor.y)
        marker = QGraphicsEllipseItem(-5.0, -5.0, 10.0, 10.0)
        marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        marker.setPen(QPen(QColor(_PALETTE["snap"]), 1.6))
        marker.setBrush(Qt.BrushStyle.NoBrush)
        marker.setZValue(20)
        marker.setVisible(False)
        self._scene.addItem(marker)
        self._snap_marker = marker
        self._paint_selection()

    def _paint_selection(self) -> None:
        for node in self._nodes:
            selected = self._selected == (node.contour, node.index)
            colour = _PALETTE["handle_selected"] if selected else _PALETTE["handle"]
            node.setBrush(QBrush(QColor(colour)))

    def _node_at(self, point: QPointF) -> _NodeItem | None:
        cursor = self.mapFromScene(point)
        best: _NodeItem | None = None
        best_distance = NODE_HIT_PX
        for node in self._nodes:
            if not node.isVisible():
                continue
            handle = self.mapFromScene(QPointF(node.pos().x(), node.pos().y()))
            distance = hypot(handle.x() - cursor.x(), handle.y() - cursor.y())
            if distance <= best_distance:
                best, best_distance = node, distance
        return best

    # ---------------------------------------------------------------- drafting surface

    def apply_palette(self, palette: Mapping[str, str]) -> None:
        """Repaint and rebuild after the user switches theme."""
        set_palette(palette)
        self.setBackgroundBrush(QBrush(QColor(_PALETTE["canvas"])))
        self._rebuild()
        self.viewport().update()

    def grid_step(self) -> float:
        """Millimetres between grid lines, chosen so the minor grid stays readable."""
        scale = self.pixels_per_mm()
        for step in GRID_STEPS:
            if step * scale >= MIN_GRID_PX:
                return step
        return GRID_STEPS[-1]

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        painter.fillRect(rect, QColor(_PALETTE["canvas"]))
        step = self.grid_step()
        major_every = 5
        left = step * (rect.left() // step)
        top = step * (rect.top() // step)
        if (rect.width() / step) > 400 or (rect.height() / step) > 400:  # pragma: no cover - guard
            return
        minor = QPen(QColor(_PALETTE["grid_minor"]), 0)
        major = QPen(QColor(_PALETTE["grid_major"]), 0)
        axis = QPen(QColor(_PALETTE["axis"]), 0)
        axis.setCosmetic(True)
        minor.setCosmetic(True)
        major.setCosmetic(True)

        minor_lines, major_lines = [], []
        index = int(round(left / step))
        x = left
        while x <= rect.right():
            target = major_lines if index % major_every == 0 else minor_lines
            target.append((QPointF(x, rect.top()), QPointF(x, rect.bottom())))
            index += 1
            x += step
        index = int(round(top / step))
        y = top
        while y <= rect.bottom():
            target = major_lines if index % major_every == 0 else minor_lines
            target.append((QPointF(rect.left(), y), QPointF(rect.right(), y)))
            index += 1
            y += step

        painter.setPen(minor)
        for a, b in minor_lines:
            painter.drawLine(a, b)
        painter.setPen(major)
        for a, b in major_lines:
            painter.drawLine(a, b)
        painter.setPen(axis)
        if rect.top() <= 0 <= rect.bottom():
            painter.drawLine(QPointF(rect.left(), 0.0), QPointF(rect.right(), 0.0))
        if rect.left() <= 0 <= rect.right():
            painter.drawLine(QPointF(0.0, rect.top()), QPointF(0.0, rect.bottom()))

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        painter.save()
        painter.setWorldMatrixEnabled(False)
        step = self.grid_step()
        major = step * 5
        colour = QColor(_PALETTE["axis_text"])
        painter.setPen(QPen(colour))
        font = painter.font()
        font.setPointSizeF(7.5)
        painter.setFont(font)

        origin = self.mapFromScene(QPointF(0.0, 0.0))
        width, height = self.viewport().width(), self.viewport().height()
        if 0 <= origin.y() <= height:
            start = self.mapFromScene(QPointF(rect.left(), 0.0)).x()
            end = self.mapFromScene(QPointF(rect.right(), 0.0)).x()
            value = int(step * (rect.left() // step))
            x = start
            while x <= end:
                if value and abs(value) % int(major) == 0 and width * 0.02 < x < width * 0.98:
                    painter.drawText(QPoint(int(x) + 3, int(origin.y()) + 12), str(int(value)))
                value += int(step)
                x = self.mapFromScene(QPointF(value, 0.0)).x()
        if 0 <= origin.x() <= width:
            start = self.mapFromScene(QPointF(0.0, rect.top())).y()
            end = self.mapFromScene(QPointF(0.0, rect.bottom())).y()
            value = int(step * (rect.top() // step))
            y = start
            while y <= end:
                if value and abs(value) % int(major) == 0 and height * 0.02 < y < height * 0.98:
                    painter.drawText(QPoint(int(origin.x()) + 5, int(y) - 3), str(int(-value)))
                value += int(step)
                y = self.mapFromScene(QPointF(0.0, value)).y()

        if self._cursor_scene is not None:
            cursor = self.mapFromScene(self._cursor_scene)
            painter.setPen(QPen(QColor(_PALETTE["crosshair"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPoint(cursor.x(), 0), QPoint(cursor.x(), height))
            painter.drawLine(QPoint(0, cursor.y()), QPoint(width, cursor.y()))
            painter.setPen(QPen(QColor(_PALETTE["text_faint"])))
            painter.drawText(QPoint(cursor.x() + 8, cursor.y() - 6), f"{self._cursor_scene.x():.1f}, {-self._cursor_scene.y():.1f}")
        painter.restore()

    # ------------------------------------------------------------- mouse and keys

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._editable:
            scene_pos = self.mapToScene(event.position().toPoint())
            node = self._node_at(scene_pos)
            if node is not None:
                if (
                    self.is_drawing()
                    and node.contour == OUTER
                    and node.index == 0
                    and len(self._section.outer.points) >= 3
                ):
                    self.close_contour()
                    event.accept()
                    return
                self.select_vertex(node.contour, node.index)
                self._drag = (
                    node.contour,
                    node.index,
                    node,
                    self._contour(node.contour).points[node.index],
                )
                event.accept()
                return

            if not self.is_drawing():
                self.clear_selection()
                self.begin_drawing()
            point, _ = self.snapped_point(scene_pos)
            self.add_vertex(point.x, point.y)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        scene_pos = self.mapToScene(event.position().toPoint())
        self._cursor_scene = scene_pos
        point, kind = self.snapped_point(scene_pos)
        self.snapChanged.emit(kind.value if kind is not None else "")
        self.cursorMoved.emit(point.x, point.y)
        if self._snap_marker is not None:
            visible = kind is not None and self._editable
            self._snap_marker.setVisible(visible)
            if visible:
                self._snap_marker.setPos(point.x, -point.y)
        self.viewport().update()

        if self._drag is not None:
            contour, index, node, _ = self._drag
            node.setPos(point.x, -point.y)
            event.accept()
            return

        if self.is_drawing() and self._rubber is not None:
            last = self._section.outer.points[-1]
            self._rubber.setLine(last.x, -last.y, point.x, -point.y)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            contour, index, node, origin = self._drag
            self._drag = None
            moved = Point(node.pos().x(), -node.pos().y())
            if moved != origin:
                self.move_vertex(contour, index, moved.x, moved.y)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.is_drawing() and event.button() == Qt.MouseButton.LeftButton:
            self.close_contour()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.is_drawing():
            self.close_contour()
            event.accept()
            return
        if key == Qt.Key.Key_Escape and self.is_drawing():
            self.cancel_drawing()
            event.accept()
            return
        if key == Qt.Key.Key_Delete and self._selected is not None:
            contour, index = self._selected
            self.delete_vertex(contour, index)
            self.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def zoom_in(self) -> None:
        self._zoom(self.transform().m11() * ZOOM_STEP)

    def zoom_out(self) -> None:
        self._zoom(self.transform().m11() / ZOOM_STEP)

    def _zoom(self, scale: float) -> None:
        if not MIN_SCALE <= scale <= MAX_SCALE:
            return
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scale(scale / self.transform().m11(), scale / self.transform().m11())

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()
