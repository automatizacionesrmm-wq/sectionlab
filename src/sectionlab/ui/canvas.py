"""Drawing canvas: contours, vertex handles, snapping and undo.

Scene coordinates are millimetres with the y axis pointing down, so the model y axis is
negated on the way in and out. Every edit is a snapshot pushed onto a `QUndoStack`, which
keeps undo/redo exact for small sections (spec S8, S14).
"""

from __future__ import annotations

from dataclasses import replace
from math import cos, hypot, radians, sin
from typing import Mapping

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QLineEdit,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
)

from sectionlab.core.model import Contour, Point, Section
from sectionlab.core.precision import format_value
from sectionlab.core.sketch import SketchError, set_segment_length
from sectionlab.core.snap import SnapKind, apply_ortho, candidates, find_snap
from sectionlab.core.units import Unit, from_mm, to_mm
from sectionlab.ui import strings
from sectionlab.ui import theme as ui_theme
from sectionlab.ui.dimensions import Dimension, dimensions_for

OUTER = "outer"
INNER = "inner"

SNAP_TOLERANCE_PX = 8.0
NODE_RADIUS_PX = 3.0
NODE_HIT_PX = 9.0
# The selected vertex gets a ring and its index, because a 3 px dot alone is not readable.
SELECTED_RING_PX = 6.5
# Distance from the contour to the dimension line, and how far the extension lines run.
DIM_OFFSET_PX = 26.0
DIM_GAP_PX = 4.0
DIM_HIT_PX = 13.0
SNAP_GLYPH_PX = 5.5
# Clicking this close to the first vertex closes the polyline, like an object snap target.
CLOSE_HIT_PX = 14.0
ZOOM_STEP = 1.15
MIN_SCALE = 0.01
MAX_SCALE = 1000.0
# The view pans freely: a fixed, very large world keeps the scrollbar ranges usable
# while the scrollbars themselves stay hidden (spec S3).
WORLD_HALF_MM = 500_000.0
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


def current_palette() -> dict[str, str]:
    """The colour tokens currently in force (Qt owns the `palette` name on widgets)."""
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


class _DimensionEditor(QLineEdit):
    """One-line editor for a dimension value; Escape abandons the edit."""

    cancelled = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)


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
    # A refused dimension edit, carrying the English code the status bar translates (D6).
    editRejected = Signal(str)
    dimensionEdited = Signal(int, float)

    def __init__(self, parent: QGraphicsView | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setBackgroundBrush(QBrush(QColor(_PALETTE["canvas"])))
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)
        self.setSceneRect(
            QRectF(
                -WORLD_HALF_MM,
                -WORLD_HALF_MM,
                WORLD_HALF_MM * 2.0,
                WORLD_HALF_MM * 2.0,
            )
        )
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

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
        self._snap_kind: SnapKind | None = None
        self._unit = Unit.MM
        self._decimals = 2
        self._dims_visible = True
        self._centroid: tuple[float, float, float] | None = None
        self._value_highlight: tuple[float, str] | None = None
        self._dimension_editor: QLineEdit | None = None
        self._pan_origin: QPoint | None = None
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

    def set_display(self, unit: Unit, decimals: int) -> None:
        """Render every measurement in the active unit, the one the panels accept."""
        self._unit = unit
        self._decimals = decimals
        self.viewport().update()

    def display_unit(self) -> Unit:
        return self._unit

    def set_dimensions_visible(self, visible: bool) -> None:
        """Show or hide the per-segment dimensions (spec S2)."""
        self._dims_visible = visible
        self.viewport().update()

    def dimensions_visible(self) -> bool:
        return self._dims_visible

    def dimensions(self) -> list[Dimension]:
        """One dimension per segment of the outline, in millimetres."""
        outer = self._section.outer
        if outer is None or len(outer.points) < 2:
            return []
        return dimensions_for(outer.points)

    def set_centroid(self, cx: float | None, cy: float | None = None, *, angle_deg: float = 0.0) -> None:
        """Mark the centroid and its principal axes (spec S4)."""
        self._centroid = None if cx is None or cy is None else (float(cx), float(cy), float(angle_deg))
        self.viewport().update()

    def centroid(self) -> tuple[float, float, float] | None:
        return self._centroid

    def set_value_highlight(self, value_mm: float | None, name: str = "") -> None:
        """Name the dimension the template form is editing, so the two views agree (spec S7)."""
        self._value_highlight = None if value_mm is None else (float(value_mm), name)
        self.viewport().update()

    def value_highlight(self) -> tuple[float, str] | None:
        return self._value_highlight

    def set_section(
        self,
        section: Section,
        *,
        record: bool = False,
        fit: bool = True,
        text: str = "section",
    ) -> None:
        """Replace the drawing, optionally as an undoable edit with its own undo label."""
        if record:
            self._commit(section, text)
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
        """Insert a vertex, appending when `index` is `None`.

        Appending a point that coincides with the first one closes the polyline instead of
        leaving a duplicate: that is what clicking the starting point means.
        """
        target = self._contour(contour)
        if (
            index is None
            and contour == OUTER
            and self._drawing
            and len(target.points) >= 3
            and Point(float(x), float(y)) == target.points[0]
        ):
            self.close_contour()
            return
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
        """Highlight one vertex; `vertexSelected` is emitted for the window's vertex table.

        Selecting what is already selected stays silent, so the table and the drawing can
        mirror each other without echoing the same click back and forth.
        """
        if self._selected == (contour, index):
            return
        self._selected = (contour, index)
        self._paint_selection()
        self.vertexSelected.emit(contour, index)

    def clear_selection(self) -> None:
        if self._selected is None:
            return
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

    def pan_by(self, dx: float, dy: float) -> None:
        """Move the drawing with the mouse: positive `dx` drags the scene to the right."""
        horizontal = self.horizontalScrollBar()
        vertical = self.verticalScrollBar()
        horizontal.setValue(horizontal.value() - int(round(dx)))
        vertical.setValue(vertical.value() - int(round(dy)))
        self.viewport().update()

    def is_panning(self) -> bool:
        return self._pan_origin is not None

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
        self._snap_kind = None
        self._paint_selection()

    def _paint_selection(self) -> None:
        closing = (
            self.is_drawing()
            and len(self._section.outer.points) >= 3
            and self._editable
        )
        for node in self._nodes:
            selected = self._selected == (node.contour, node.index)
            if selected:
                colour = _PALETTE["handle_selected"]
            elif closing and node.contour == OUTER and node.index == 0:
                colour = _PALETTE["ok"]
            else:
                colour = _PALETTE["handle"]
            node.setBrush(QBrush(QColor(colour)))

    def closes_here(self, point: QPointF) -> bool:
        """True when a click lands on the closing target: the first vertex of the polyline."""
        points = self._section.outer.points
        if not self.is_drawing() or len(points) < 3:
            return False
        cursor = self.mapFromScene(point)
        first = self.mapFromScene(QPointF(points[0].x, -points[0].y))
        return hypot(first.x() - cursor.x(), first.y() - cursor.y()) <= CLOSE_HIT_PX

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

    # ------------------------------------------------------------------ painting

    def _device_normal(self, dimension: Dimension) -> QPointF:
        """The dimension's outward normal in device pixels, y axis included."""
        origin = self.mapFromScene(QPointF(dimension.start.x, -dimension.start.y))
        tip = self.mapFromScene(
            QPointF(dimension.start.x + dimension.normal.x, -dimension.start.y - dimension.normal.y)
        )
        dx = tip.x() - origin.x()
        dy = tip.y() - origin.y()
        length = hypot(dx, dy) or 1.0
        return QPointF(dx / length, dy / length)

    def _dimension_text(self, dimension: Dimension) -> str:
        value = format_value(from_mm(dimension.value, self._unit), self._decimals)
        if self._is_highlighted(dimension):
            _, name = self._value_highlight or (0.0, "")
            return f"{name} = {value}" if name else value
        return value

    def _is_highlighted(self, dimension: Dimension) -> bool:
        if self._value_highlight is None:
            return False
        return abs(dimension.value - self._value_highlight[0]) <= 1e-6

    def _dimension_geometry(self, dimension: Dimension) -> tuple[QPointF, QPointF, QPointF]:
        """The two ends of the dimension line and the outward normal in device pixels."""
        normal = self._device_normal(dimension)
        start = self.mapFromScene(QPointF(dimension.start.x, -dimension.start.y))
        end = self.mapFromScene(QPointF(dimension.end.x, -dimension.end.y))
        first = QPointF(start.x() + normal.x() * DIM_OFFSET_PX, start.y() + normal.y() * DIM_OFFSET_PX)
        second = QPointF(end.x() + normal.x() * DIM_OFFSET_PX, end.y() + normal.y() * DIM_OFFSET_PX)
        return first, second, normal

    def _dimension_box(self, dimension: Dimension, metrics=None) -> QRectF:
        """Device rectangle the dimension text occupies; also the target of a double click."""
        if metrics is None:
            metrics = QFontMetricsF(self.font())
        label = self._dimension_text(dimension)
        width = metrics.horizontalAdvance(label)
        height = metrics.height()
        first, second, normal = self._dimension_geometry(dimension)
        middle = QPointF((first.x() + second.x()) / 2, (first.y() + second.y()) / 2)
        centre = QPointF(
            middle.x() + normal.x() * (DIM_GAP_PX + 2.0),
            middle.y() + normal.y() * (DIM_GAP_PX + 2.0),
        )
        return QRectF(centre.x() - width / 2 - 3, centre.y() - height / 2 - 1, width + 6, height + 2)

    def dimension_at(self, position: QPoint) -> Dimension | None:
        """The editable dimension whose text sits under the cursor, if any (spec S3)."""
        if not self._dims_visible or not self._editable:
            return None
        point = QPointF(position)
        for dimension in self.dimensions():
            if not dimension.editable:
                continue
            if self._dimension_box(dimension).adjusted(-6, -6, 6, 6).contains(point):
                return dimension
        return None

    def apply_dimension_length(self, index: int, length_mm: float) -> bool:
        """Make one segment measure ``length_mm`` as a single undoable edit (spec S3)."""
        outer = self._section.outer
        if outer is None:
            return False
        if not self._editable:
            self.editRejected.emit("read_only")
            return False
        try:
            points = set_segment_length(outer.points, index, length_mm)
        except SketchError as error:
            self.editRejected.emit(error.code)
            return False
        self._commit(
            replace(self._section, outer=replace(outer, points=points)),
            strings.label_for("undo_dimension"),
        )
        self.dimensionEdited.emit(index, length_mm)
        return True

    def begin_dimension_edit(self, dimension: Dimension) -> bool:
        """Open a one-line editor over the dimension text, prefilled in the active unit."""
        if not dimension.editable or not self._editable:
            return False
        self.close_dimension_editor()
        editor = _DimensionEditor(self.viewport())
        editor.setObjectName("dimension_editor")
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setText(format_value(from_mm(dimension.value, self._unit), self._decimals))
        editor.setGeometry(self._dimension_box(dimension).toRect().adjusted(-10, -4, 10, 4))
        editor.returnPressed.connect(lambda: self._commit_dimension_edit(dimension, editor))
        editor.cancelled.connect(self.close_dimension_editor)
        editor.show()
        editor.setFocus()
        editor.selectAll()
        self._dimension_editor = editor
        return True

    def close_dimension_editor(self) -> None:
        editor = self._dimension_editor
        self._dimension_editor = None
        if editor is not None:
            editor.hide()
            editor.deleteLater()

    def has_dimension_editor(self) -> bool:
        return self._dimension_editor is not None

    def _commit_dimension_edit(self, dimension: Dimension, editor: QLineEdit) -> None:
        text = editor.text()
        self.close_dimension_editor()
        try:
            value = to_mm(float(text.strip().replace(",", ".")), self._unit)
        except ValueError:
            self.editRejected.emit("not_a_number")
            return
        self.apply_dimension_length(dimension.index, value)

    def _draw_dimensions(self, painter: QPainter) -> None:
        """One dimension per segment, written outside the contour (spec S2)."""
        if not self._dims_visible:
            return
        font = painter.font()
        font.setPointSizeF(8.0)
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        for dimension in self.dimensions():
            first, second, normal = self._dimension_geometry(dimension)
            colour = QColor(_PALETTE["accent"] if self._is_highlighted(dimension) else _PALETTE["dim_text"])
            style = Qt.PenStyle.SolidLine if dimension.editable else Qt.PenStyle.DashLine
            painter.setPen(QPen(colour, 1.0, style))
            start = self.mapFromScene(QPointF(dimension.start.x, -dimension.start.y))
            end = self.mapFromScene(QPointF(dimension.end.x, -dimension.end.y))
            painter.drawLine(first, second)
            for anchor, target in ((start, first), (end, second)):
                painter.drawLine(
                    QPointF(anchor.x() + normal.x() * DIM_GAP_PX, anchor.y() + normal.y() * DIM_GAP_PX),
                    QPointF(target.x() + normal.x() * DIM_GAP_PX, target.y() + normal.y() * DIM_GAP_PX),
                )
            box = self._dimension_box(dimension, metrics)
            painter.fillRect(box, QColor(_PALETTE["canvas"]))
            painter.setPen(QPen(colour))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self._dimension_text(dimension))

    def _draw_axes_labels(self, painter: QPainter, origin: QPoint, width: int, height: int) -> None:
        """Name the two reference axes, so the origin is unmistakable (spec S4)."""
        font = painter.font()
        font.setPointSizeF(8.0)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(_PALETTE["axis_text"])))
        if 0 <= origin.y() <= height:
            painter.drawText(width - 16, int(origin.y()) - 5, "X")
        if 0 <= origin.x() <= width:
            painter.drawText(int(origin.x()) + 7, 15, "Y")
        font.setBold(False)
        painter.setFont(font)

    def _draw_centroid(self, painter: QPainter) -> None:
        """Centroid dot with the two principal axes, labelled 1 and 2 (spec S4)."""
        if self._centroid is None:
            return
        cx, cy, angle = self._centroid
        centre = self.mapFromScene(QPointF(cx, -cy))
        colour = QColor(_PALETTE["centroid"])
        radius = 0.42 * min(self.viewport().width(), self.viewport().height())
        painter.setPen(QPen(colour, 1.0, Qt.PenStyle.DashLine))
        for label, degrees in (("1", angle), ("2", angle + 90.0)):
            dx = cos(radians(degrees)) * radius
            dy = -sin(radians(degrees)) * radius
            painter.drawLine(QPointF(centre.x() - dx, centre.y() - dy), QPointF(centre.x() + dx, centre.y() + dy))
            painter.drawText(QPointF(centre.x() + dx * 1.04, centre.y() + dy * 1.04), label)
        painter.setBrush(QBrush(colour))
        painter.setPen(QPen(colour, 1.0))
        painter.drawEllipse(centre, 3.5, 3.5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(QPointF(centre.x() + 7, centre.y() - 6), "C")

    def _draw_snap(self, painter: QPainter) -> None:
        """Glyph and name of the snap the cursor is on, like an osnap marker (spec S5)."""
        if self._snap_kind is None or self._cursor_scene is None:
            return
        point = self.mapFromScene(self._cursor_scene)
        colour = QColor(_PALETTE["snap"])
        painter.setPen(QPen(colour, 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        size = SNAP_GLYPH_PX
        kind = self._snap_kind
        if kind is SnapKind.ENDPOINT:
            painter.drawRect(QRectF(point.x() - size, point.y() - size, size * 2, size * 2))
        elif kind is SnapKind.MIDPOINT:
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(point.x(), point.y() - size),
                        QPointF(point.x() - size, point.y() + size),
                        QPointF(point.x() + size, point.y() + size),
                    ]
                )
            )
        elif kind is SnapKind.INTERSECTION:
            painter.drawLine(QPointF(point.x() - size, point.y() - size), QPointF(point.x() + size, point.y() + size))
            painter.drawLine(QPointF(point.x() - size, point.y() + size), QPointF(point.x() + size, point.y() - size))
        elif kind is SnapKind.CENTER:
            painter.drawEllipse(point, size, size)
        elif kind is SnapKind.PERPENDICULAR:
            painter.drawLine(QPointF(point.x() - size, point.y() + size), QPointF(point.x() + size, point.y() + size))
            painter.drawLine(QPointF(point.x() - size, point.y() - size), QPointF(point.x() - size, point.y() + size))
        painter.setPen(QPen(colour))
        name = strings.label_for(f"snap_{kind.value.lower()}")
        painter.drawText(QPointF(point.x() + size + 6, point.y() - size - 2), name)

    def _selected_point(self) -> QPointF | None:
        if self._selected is None:
            return None
        name, index = self._selected
        contour = self._section.outer if name == OUTER else self._section.inner
        if contour is None or not 0 <= index < len(contour.points):
            return None
        point = contour.points[index]
        return self.mapFromScene(QPointF(point.x, -point.y))

    def _draw_selected_vertex(self, painter: QPainter) -> None:
        """A ring and the vertex index, because the handle alone is too small to read."""
        point = self._selected_point()
        if point is None:
            return
        colour = QColor(_PALETTE["handle_selected"])
        painter.setPen(QPen(colour, 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(point, SELECTED_RING_PX, SELECTED_RING_PX)
        assert self._selected is not None
        painter.drawText(QPointF(point.x() + SELECTED_RING_PX + 3, point.y() - SELECTED_RING_PX), f"v{self._selected[1]}")

    # ------------------------------------------------------------------ foreground

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

        self._draw_axes_labels(painter, origin, width, height)
        self._draw_centroid(painter)
        self._draw_dimensions(painter)

        if self._cursor_scene is not None:
            cursor = self.mapFromScene(self._cursor_scene)
            painter.setPen(QPen(QColor(_PALETTE["crosshair"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPoint(cursor.x(), 0), QPoint(cursor.x(), height))
            painter.drawLine(QPoint(0, cursor.y()), QPoint(width, cursor.y()))
            painter.setPen(QPen(QColor(_PALETTE["text_faint"])))
            painter.drawText(QPoint(cursor.x() + 8, cursor.y() - 6), f"{self._cursor_scene.x():.1f}, {-self._cursor_scene.y():.1f}")
        self._draw_snap(painter)
        self._draw_selected_vertex(painter)
        painter.restore()

    # ------------------------------------------------------------- mouse and keys

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_origin = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton and self.is_drawing():
            if len(self._section.outer.points) >= 3:
                self.close_contour()
            else:
                self.cancel_drawing()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._editable:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self.closes_here(scene_pos):
                self.close_contour()
                event.accept()
                return
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
        if self._pan_origin is not None:
            current = event.position().toPoint()
            delta = current - self._pan_origin
            self._pan_origin = current
            self.pan_by(delta.x(), delta.y())
            event.accept()
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        self._cursor_scene = scene_pos
        point, kind = self.snapped_point(scene_pos)
        self.snapChanged.emit(kind.value if kind is not None else "")
        self.cursorMoved.emit(point.x, point.y)
        self._snap_kind = kind if self._editable else None
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
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_origin is not None:
            self._pan_origin = None
            self.viewport().unsetCursor()
            event.accept()
            return

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
        if event.button() == Qt.MouseButton.MiddleButton:
            self.fit_to_content()
            event.accept()
            return
        if self.is_drawing() and event.button() == Qt.MouseButton.LeftButton:
            self.close_contour()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            dimension = self.dimension_at(event.position().toPoint())
            if dimension is not None and self.begin_dimension_edit(dimension):
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
        """Zoom in about the middle of the viewport, as the toolbar does."""
        self.zoom_at(self.viewport().rect().center(), ZOOM_STEP)

    def zoom_out(self) -> None:
        """Zoom out about the middle of the viewport."""
        self.zoom_at(self.viewport().rect().center(), 1.0 / ZOOM_STEP)

    def zoom_at(self, anchor: QPoint, factor: float) -> None:
        """Scale about a viewport point so the geometry under the cursor stays put."""
        current = self.transform().m11()
        target = current * factor
        if not MIN_SCALE <= target <= MAX_SCALE:
            return
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        before = self.mapToScene(anchor)
        self.scale(factor, factor)
        after = self.mapToScene(anchor)
        delta = after - before
        self.translate(delta.x(), delta.y())
        self.viewport().update()

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        steps = event.angleDelta().y() / 120.0
        if not steps:
            event.accept()
            return
        anchor = event.position().toPoint()
        self.zoom_at(anchor, ZOOM_STEP**steps)
        event.accept()
