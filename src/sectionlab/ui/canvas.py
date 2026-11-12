"""Drawing canvas: contours, vertex handles, snapping and undo.

Scene coordinates are millimetres with the y axis pointing down, so the model y axis is
negated on the way in and out. Every edit is a snapshot pushed onto a `QUndoStack`, which
keeps undo/redo exact for small sections (spec S8, S14).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import cos, hypot, radians, sin
from typing import Mapping

from PySide6.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, Signal
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

from sectionlab.core.dimensions import (
    ANCHOR_EDGE,
    ANCHOR_VERTEX,
    HORIZONTAL,
    SEGMENT_LENGTH,
    VERTICAL,
    Anchor,
    Dimension,
    DimensionError,
    is_editable,
    measure,
    normal,
    remap,
)
from sectionlab.core.model import Contour, Point, Section
from sectionlab.core.precision import format_value
from sectionlab.core.edit import rectangle as rectangle_ring
from sectionlab.core.sketch import SketchError, set_measure
from sectionlab.core.snap import (
    GUIDE_X,
    GUIDE_Y,
    SNAP_KINDS,
    SnapKind,
    alignments,
    apply_alignment,
    apply_ortho,
    candidates,
    find_snap,
)
from sectionlab.core.templates import (
    TemplateKind,
    TemplateParameterError,
    build_section,
    parameter_for,
    parameter_override,
)
from sectionlab.core.units import Unit, from_mm, to_mm
from sectionlab.ui import strings
from sectionlab.ui import theme as ui_theme

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
# Clicking this close to an edge selects that segment, as picking a line does in CAD.
SEGMENT_HIT_PX = 7.0
SNAP_GLYPH_PX = 8.0
SNAP_HALO_PX = 5.0
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


def _edge_distance(point: QPoint, start: QPointF, end: QPointF) -> float:
    """Pixel distance from ``point`` to the segment ``start``-``end``."""
    ax, ay = start.x(), start.y()
    dx, dy = end.x() - ax, end.y() - ay
    span = dx * dx + dy * dy
    if span == 0:
        return hypot(point.x() - ax, point.y() - ay)
    t = max(0.0, min(1.0, ((point.x() - ax) * dx + (point.y() - ay) * dy) / span))
    return hypot(point.x() - (ax + t * dx), point.y() - (ay + t * dy))

_PALETTE: dict[str, str] = dict(ui_theme.DARK)



_OUTER_PEN = QPen(QColor(_PALETTE["contour"]), 2)
_OUTER_PEN.setCosmetic(True)
_INNER_PEN = QPen(QColor(_PALETTE["inner"]), 1.6, Qt.PenStyle.DashLine)
_INNER_PEN.setCosmetic(True)
_DRAFT_PEN = QPen(QColor(_PALETTE["draft"]), 1.2, Qt.PenStyle.DashLine)
_DRAFT_PEN.setCosmetic(True)
_BAND_PEN = QPen(QColor(_PALETTE["handle_selected"]), 1.2, Qt.PenStyle.DashLine)
_BAND_PEN.setCosmetic(True)
BAND_CLICK_PX = 4


def _line_hits_rect(line: QLineF, rect: QRectF) -> bool:
    """True when a segment touches the rectangle anywhere."""
    for start, end in (
        (rect.topLeft(), rect.topRight()),
        (rect.topRight(), rect.bottomRight()),
        (rect.bottomRight(), rect.bottomLeft()),
        (rect.bottomLeft(), rect.topLeft()),
    ):
        kind, _ = line.intersect(QLineF(start, end))
        if kind == QLineF.IntersectionType.BoundedIntersection:
            return True
    return rect.contains(line.p1()) or rect.contains(line.p2())


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


@dataclass(frozen=True)
class _Snapshot:
    """Everything one undo step restores: the geometry and the dimensions placed on it."""

    section: Section
    dimensions: tuple[Dimension, ...]


class _EditCommand(QUndoCommand):
    """Snapshot command: applying a whole section is exact and cheap at this scale."""

    def __init__(self, canvas: "CanvasView", before: _Snapshot, after: _Snapshot, text: str) -> None:
        super().__init__(text)
        self._canvas = canvas
        self._before = before
        self._after = after

    def redo(self) -> None:  # noqa: D102 - Qt override
        self._canvas._apply_snapshot(self._after)

    def undo(self) -> None:  # noqa: D102 - Qt override
        self._canvas._apply_snapshot(self._before)


class CanvasView(QGraphicsView):
    """Editable top view of a section, in millimetres."""

    sectionChanged = Signal()
    cursorMoved = Signal(float, float)
    snapChanged = Signal(str)
    vertexSelected = Signal(str, int)
    # A segment picked with the left button, as (contour, index of its first vertex).
    segmentSelected = Signal(str, int)
    drawingChanged = Signal(bool)
    # A refused dimension edit, carrying the English code the status bar translates (D6).
    editRejected = Signal(str)
    dimensionEdited = Signal(int, float)
    dimensionPlaced = Signal(int)
    dimensionSelected = Signal(int)
    dimensionToolChanged = Signal(bool)
    # How many references the tool holds: 0 first, 1 second, 2 place (spec S2).
    dimensionStepChanged = Signal(int)
    # How many dimensions an edit of the geometry had to drop, because their vertex is gone.
    dimensionsDropped = Signal(int)
    # The references the cursor is aligned with, ready for the status bar (spec S12).
    guidesChanged = Signal(str)

    def __init__(self, parent: QGraphicsView | None = None) -> None:
        super().__init__(parent)
        # Typing must reach the drawing, not only the toolbars: CAD input starts on the canvas.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        self._segment: tuple[str, int] | None = None
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
        self._dimensions: list[Dimension] = []
        self._next_dimension_id = 1
        self._selected_dimension: int | None = None
        self._selection: set[tuple[str, int]] = set()
        self._band_origin: QPointF | None = None
        self._band_item: QGraphicsRectItem | None = None
        self._rectangle_armed = False
        self._rectangle_start: Point | None = None
        self._rectangle_preview: QGraphicsRectItem | None = None
        self._dimension_drag: tuple[Dimension, _Snapshot] | None = None
        self._tool_active = False
        self._tool_anchors: list[Anchor] = []
        self._guides_visible = True
        self._guides: list = []
        self._enabled_snaps: frozenset[SnapKind] = frozenset(SNAP_KINDS)
        self._cursor_locked: Point | None = None
        self._cursor_place: Point | None = None
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

    def set_enabled_snaps(self, kinds) -> None:
        """Choose which snap families the cursor may use; an empty set disables snapping (S13)."""
        self._enabled_snaps = frozenset(kinds)
        self.viewport().update()

    def enabled_snaps(self) -> frozenset[SnapKind]:
        return self._enabled_snaps

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
        """Show or hide the dimensions the user placed (spec S1)."""
        self._dims_visible = visible
        self.viewport().update()

    def dimensions_visible(self) -> bool:
        return self._dims_visible

    def dimensions(self) -> list[Dimension]:
        """The dimensions the user placed, in millimetres; nothing is derived (spec S1)."""
        return list(self._dimensions)

    def set_dimensions(self, dimensions, *, record: bool = False, text: str = "dimension") -> None:
        """Replace the placed dimensions, optionally as one undoable edit."""
        placed = tuple(dimensions)
        if record:
            self._commit_snapshot(self._snapshot(dimensions=placed), text)
            return
        fits = [item for item in placed if self._fits(item, len(self._section.outer.points))]
        dropped = len(placed) - len(fits)
        self._dimensions = fits
        self._next_dimension_id = max((item.id for item in self._dimensions), default=0) + 1
        self.viewport().update()
        if dropped:
            self.dimensionsDropped.emit(dropped)

    def dimension(self, identifier: int) -> Dimension | None:
        return next((item for item in self._dimensions if item.id == identifier), None)

    def add_dimension(
        self,
        first: Anchor,
        second: Anchor,
        kind: str,
        *,
        offset_mm: float | None = None,
        record: bool = True,
    ) -> Dimension | None:
        """Place one dimension; ``record`` pushes it as its own undo step."""
        if len(self._section.outer.points) < 3:
            return None
        if not record and not self._editable:
            return None
        placed = Dimension(
            id=self._next_dimension_id,
            first=first,
            second=second,
            kind=kind,
            offset_mm=self._default_offset_mm() if offset_mm is None else float(offset_mm),
        )
        self._next_dimension_id += 1
        if record:
            self._commit_snapshot(
                self._snapshot(dimensions=tuple([*self._dimensions, placed])),
                strings.label_for("undo_dimension_add"),
            )
        else:
            self._dimensions.append(placed)
            self.viewport().update()
        self.dimensionPlaced.emit(placed.id)
        return placed

    def delete_dimension(self, identifier: int) -> bool:
        """Remove one dimension as a single undoable edit (spec S9)."""
        if not any(item.id == identifier for item in self._dimensions):
            return False
        remaining = tuple(item for item in self._dimensions if item.id != identifier)
        self._commit_snapshot(self._snapshot(dimensions=remaining), strings.label_for("undo_dimension_delete"))
        self._selected_dimension = None
        return True

    def select_dimension(self, identifier: int) -> None:
        """Highlight one dimension, and tell the window so it can offer its actions."""
        self._selection = set()
        self._segment = None
        self._selected_dimension = identifier
        self.viewport().update()
        self.dimensionSelected.emit(identifier)

    def selected_dimension(self) -> int | None:
        return self._selected_dimension

    def can_drive(self, dimension: Dimension) -> bool:
        """Whether typing a value for this dimension can move anything (specs S5-S7)."""
        template = self._section.template
        if template is not None:
            try:
                kind = TemplateKind(template.kind)
            except ValueError:
                return False
            return parameter_for(kind, template.params, dimension) is not None
        return is_editable(self._ring(), dimension)[0]

    def drive_dimension(self, identifier: int, target_mm: float) -> bool:
        """Make one dimension measure ``target_mm`` as a single undoable edit (specs S5-S6)."""
        dimension = self.dimension(identifier)
        if dimension is None:
            return False
        if self._section.template is not None:
            return self._drive_template(dimension, target_mm)
        if not self._editable:
            self.editRejected.emit("read_only")
            return False
        try:
            moved = set_measure(self._ring(), dimension, target_mm)
        except SketchError as error:
            self.editRejected.emit(error.code)
            return False
        self._commit(
            replace(self._section, outer=replace(self._section.outer, points=moved)),
            strings.label_for("undo_dimension"),
        )
        self.dimensionEdited.emit(identifier, target_mm)
        return True

    def _drive_template(self, dimension: Dimension, target_mm: float) -> bool:
        """A dimension on a template moves the parameter behind it (spec S6)."""
        template = self._section.template
        assert template is not None
        try:
            kind = TemplateKind(template.kind)
        except ValueError:
            self.editRejected.emit("not_drivable")
            return False
        override = parameter_override(kind, template.params, dimension, target_mm)
        if override is None:
            self.editRejected.emit("not_drivable")
            return False
        try:
            rebuilt = build_section(kind, {**template.params, **override})
        except TemplateParameterError as error:
            self.editRejected.emit(error.code)
            return False
        self._commit(rebuilt, strings.label_for("undo_dimension"))
        self.dimensionEdited.emit(dimension.id, target_mm)
        return True

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
        keep_dimensions: bool = False,
    ) -> None:
        """Replace the drawing, optionally as an undoable edit with its own undo label."""
        if record:
            self._commit(section, text)
        else:
            self._undo.clear()
            self._apply_section(section, keep_dimensions=keep_dimensions)
        if fit:
            self.fit_to_content()

    def snap_kind(self) -> SnapKind | None:
        """The snap family the cursor is on, or None (spec S5)."""
        return self._snap_kind

    def is_drawing(self) -> bool:
        """True while the outer contour is an open polyline being drawn."""
        return self._drawing

    def begin_drawing(self) -> None:
        """Arm the draw command: clicks append vertices until it is closed or left (S1, S2).

        Arming a command no longer empties the section: the window's "new free geometry"
        button does the emptying when that is what was asked.
        """
        if not self._editable:
            return
        if self._drawing:
            return
        outer = self._section.outer
        if outer.closed or not outer.points:
            # A closed section is not extended by clicking: the command starts a fresh trace.
            self.set_section(Section(outer=Contour(points=[], closed=False)), fit=False)
        self._drawing = True
        self._rebuild()
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
        dimensions = self._remapped(inserted=position) if contour == OUTER else None
        self._replace_contour(contour, replace(target, points=points), "add vertex", dimensions)

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
        dimensions = self._remapped(deleted=index) if contour == OUTER else None
        self._replace_contour(contour, replace(target, points=points), "delete vertex", dimensions)

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

    def end_drawing(self) -> None:
        """Leave the draw command and keep what is already traced, as an open contour (S2)."""
        if not self._drawing:
            return
        self._drawing = False
        contour = replace(self._section.outer, closed=False)
        self._replace_contour(OUTER, contour, "end drawing")
        self.drawingChanged.emit(False)

    def draft_line(self) -> QGraphicsLineItem | None:
        """The dashed guide from the last vertex to the cursor while drawing."""
        return self._rubber

    def selected_vertex(self) -> tuple[str, int] | None:
        """The selected vertex when exactly one is; `None` when none or several are."""
        if len(self._selection) != 1:
            return None
        return next(iter(self._selection))

    def has_selection(self) -> bool:
        """True when a vertex, an edge or a dimension is selected (S3)."""
        return bool(self._selection) or self._segment is not None or self._selected_dimension is not None

    def can_delete_selection(self) -> bool:
        """Vertices and dimensions can be deleted; an edge alone cannot (S3)."""
        return bool(self._selection) or self._selected_dimension is not None

    def selected_vertices(self) -> tuple[tuple[str, int], ...]:
        """Every selected vertex, in a stable order (contour name, then index)."""
        return tuple(sorted(self._selection))

    def select_vertex(self, contour: str, index: int) -> None:
        """Highlight one vertex, replacing any other selection.

        Selecting what is already selected stays silent, so the table and the drawing can
        mirror each other without echoing the same click back and forth.
        """
        self.select_vertices([(contour, index)])

    def select_vertices(self, items) -> None:
        """Highlight several vertices at once: `Ctrl+A`, a selection window, or one click."""
        chosen = {(name, int(index)) for name, index in items}
        if chosen == self._selection:
            return
        had_vertex = bool(self._selection)
        self._selection = chosen
        self._segment = None
        self._paint_selection()
        self.viewport().update()
        single = self.selected_vertex()
        if single is None:
            # A multiple selection has no single vertex to show, but the window still needs
            # to know that something is selected (spec S3).
            self.vertexSelected.emit("", -1)
            return
        self.vertexSelected.emit(*single)

    def begin_rectangle_tool(self) -> None:
        """Arm the rectangle: the next two clicks are opposite corners (S4)."""
        if not self._editable:
            return
        self.cancel_rectangle_tool()
        self._rectangle_armed = True
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def cancel_rectangle_tool(self) -> None:
        self._rectangle_armed = False
        self._rectangle_start = None
        if self._rectangle_preview is not None:
            self._scene.removeItem(self._rectangle_preview)
            self._rectangle_preview = None
        self.viewport().unsetCursor()

    def is_placing_rectangle(self) -> bool:
        return self._rectangle_armed

    def replace_outer(self, points, text: str) -> None:
        """Replace the outer ring with the result of an edit tool (S4).

        These operations move or insert vertices, so a dimension anchored by index no longer
        describes the drawing; the dimensions are dropped and the loss is reported.
        """
        lost = len(self._dimensions)
        contour = replace(
            self._section.outer,
            points=[Point(float(point.x), float(point.y)) for point in points],
        )
        self._replace_contour(OUTER, contour, text, dimensions=())
        if lost:
            self.dimensionsDropped.emit(lost)

    def select_all(self) -> int:
        """Select every vertex of the section; returns how many (S3)."""
        items: list[tuple[str, int]] = []
        for name, contour in ((OUTER, self._section.outer), (INNER, self._section.inner)):
            if contour is None:
                continue
            items.extend((name, index) for index in range(len(contour.points)))
        self.select_vertices(items)
        return len(items)

    def delete_selection(self) -> int:
        """Delete the selected dimension, or every selected vertex, as one undo step (S3)."""
        if self._selected_dimension is not None:
            identifier = self._selected_dimension
            self.delete_dimension(identifier)
            return 1
        items = sorted(self._selection, key=lambda item: (item[0], -item[1]))
        if not items:
            return 0
        self._undo.beginMacro(strings.label_for("undo_delete_selection"))
        try:
            for name, index in items:
                contour = self._contour(name)
                if contour is None or not 0 <= index < len(contour.points):
                    continue
                self.delete_vertex(name, index)
        finally:
            self._undo.endMacro()
        self.clear_selection()
        return len(items)

    def clear_selection(self) -> None:
        """Drop every selection: vertices, the picked edge and the picked dimension."""
        had_vertex = bool(self._selection)
        had_dimension = self._selected_dimension is not None
        self._selection = set()
        self._segment = None
        self._selected_dimension = None
        if had_vertex or had_dimension:
            self._paint_selection()
            self.viewport().update()
        if had_vertex:
            self.vertexSelected.emit("", -1)

    def selected_segment(self) -> tuple[str, int] | None:
        """The edge picked with the left button, if any."""
        return self._segment

    def select_segment(self, contour: str, index: int) -> None:
        """Highlight one edge and tell the window, so the status bar can explain the typing."""
        if self._segment == (contour, index):
            return
        had_vertex = bool(self._selection)
        self._selection = set()
        self._segment = (contour, index)
        self._paint_selection()
        if had_vertex:
            self.vertexSelected.emit("", -1)
        self.viewport().update()
        self.segmentSelected.emit(contour, index)

    def segment_at(self, point: QPointF) -> tuple[str, int] | None:
        """Contour and index of the edge under a scene point, within ``SEGMENT_HIT_PX``."""
        cursor = self.mapFromScene(point)
        best: tuple[str, int] | None = None
        best_distance = SEGMENT_HIT_PX
        for name, contour in ((OUTER, self._section.outer), (INNER, self._section.inner)):
            if contour is None or len(contour.points) < 2:
                continue
            count = len(contour.points)
            for index in range(count):
                start = contour.points[index]
                end = contour.points[(index + 1) % count]
                distance = _edge_distance(
                    cursor,
                    self.mapFromScene(QPointF(start.x, -start.y)),
                    self.mapFromScene(QPointF(end.x, -end.y)),
                )
                if distance <= best_distance:
                    best, best_distance = (name, index), distance
        return best

    def pixels_per_mm(self) -> float:
        """Current zoom, used to translate the pixel snap tolerance into millimetres."""
        return max(self.transform().m11(), 1e-9)

    def snapped_point(self, scene_pos: QPointF) -> tuple[Point, SnapKind | None]:
        """Model point under the cursor after the ortho constraint, a snap, or a guide.

        A snap wins over a guide because it is an exact existing point; a guide wins over the
        raw cursor because sharing a coordinate is what the user is aiming at (spec S12).
        """
        model = Point(scene_pos.x(), -scene_pos.y())
        anchor = self._last_vertex()
        fixed_axis: str | None = None
        if self._ortho and anchor is not None:
            model = apply_ortho(anchor, model)
            # Ortho owns one coordinate: a guide on that same axis would fight it, so only the
            # axis ortho left free is allowed to align (spec S12).
            fixed_axis = GUIDE_Y if model.y == anchor.y else GUIDE_X

        tolerance = SNAP_TOLERANCE_PX / self.pixels_per_mm()
        contours = [c for c in (self._section.outer, self._section.inner) if c and c.points]
        found_candidates = candidates(contours)
        found = find_snap(model, found_candidates, tolerance, enabled=self._enabled_snaps)
        if found is not None:
            self._guides = []
            self._cursor_locked = found.point
            self._cursor_place = model
            return found.point, found.kind

        guides = alignments(found_candidates, model, tolerance) if self._guides_visible else []
        if fixed_axis is not None:
            guides = [guide for guide in guides if guide.axis != fixed_axis]
        self._guides = guides
        locked = apply_alignment(model, guides) if guides else model
        self._cursor_locked = locked
        self._cursor_place = locked
        return locked, None

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

    def _replace_contour(
        self,
        name: str,
        contour: Contour,
        text: str,
        dimensions: tuple[Dimension, ...] | None = None,
    ) -> None:
        if name == INNER:
            updated = replace(self._section, inner=contour)
        else:
            updated = replace(self._section, outer=contour)
        self._commit_snapshot(self._snapshot(section=updated, dimensions=dimensions), text)

    def _snapshot(
        self,
        *,
        section: Section | None = None,
        dimensions: tuple[Dimension, ...] | None = None,
    ) -> _Snapshot:
        return _Snapshot(
            section=self._section if section is None else section,
            dimensions=tuple(self._dimensions) if dimensions is None else tuple(dimensions),
        )

    def _commit(self, section: Section, text: str) -> None:
        """Commit a geometry change that leaves the dimensions where they are."""
        self._commit_snapshot(self._snapshot(section=section), text)

    def _commit_snapshot(self, after: _Snapshot, text: str) -> None:
        before = self._snapshot()
        if after == before:
            return
        self._undo.push(_EditCommand(self, before, after, text))

    def _apply_snapshot(self, snapshot: _Snapshot) -> None:
        self._section = snapshot.section
        count = len(snapshot.section.outer.points)
        kept = [item for item in snapshot.dimensions if self._fits(item, count)]
        # Only the incoming snapshot says what should exist: a dimension the user deleted is
        # absent from it on purpose, one whose anchor vanished is present but does not fit.
        dropped = len(snapshot.dimensions) - len(kept)
        self._dimensions = kept
        self._drawing = not snapshot.section.outer.closed and bool(count)
        if self._selected_dimension is not None and not any(
            item.id == self._selected_dimension for item in self._dimensions
        ):
            self._selected_dimension = None
        self._rebuild()
        self.sectionChanged.emit()
        if dropped:
            self.dimensionsDropped.emit(dropped)

    def _apply_section(self, section: Section, *, keep_dimensions: bool = False) -> None:
        """Replace the whole drawing; a different shape invalidates every placed dimension."""
        previous = len(self._dimensions)
        placed = tuple(self._dimensions) if keep_dimensions else ()
        self._apply_snapshot(self._snapshot(section=section, dimensions=placed))
        lost = 0 if keep_dimensions else previous - len(self._dimensions)
        if lost:
            self.dimensionsDropped.emit(lost)

    @staticmethod
    def _fits(dimension: Dimension, count: int) -> bool:
        """A dimension whose anchor indices exist still belongs to this contour."""
        return all(0 <= anchor.index < count for anchor in dimension.anchors)

    def _remapped(self, **change: int) -> tuple[Dimension, ...]:
        """Dimensions re-indexed after a vertex was inserted or deleted (spec S10)."""
        moved = [remap(item, **change) for item in self._dimensions]
        kept = [item for item in moved if item is not None]
        lost = len(moved) - len(kept)
        if lost:
            self.dimensionsDropped.emit(lost)
        return tuple(kept)

    def _ring(self) -> list[Point]:
        outer = self._section.outer
        return list(outer.points) if outer is not None else []

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
            selected = (node.contour, node.index) in self._selection
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

    def _device_point(self, point: Point) -> QPointF:
        return self.mapFromScene(QPointF(point.x, -point.y))

    def _device_direction(self, direction: Point) -> QPointF:
        """A model direction in device pixels, y axis included."""
        origin = self.mapFromScene(QPointF(0.0, 0.0))
        tip = self.mapFromScene(QPointF(direction.x, -direction.y))
        dx = tip.x() - origin.x()
        dy = tip.y() - origin.y()
        length = hypot(dx, dy) or 1.0
        return QPointF(dx / length, dy / length)

    def dimension_frame(
        self, dimension: Dimension
    ) -> tuple[QPointF, QPointF, QPointF, QPointF, QPointF] | None:
        """Device geometry of one dimension: line ends, outward normal and both anchors.

        The line sits ``offset_mm`` away from the measured entity, so the distance the user
        chose survives zooming instead of being a fixed number of pixels (spec S8).
        """
        points = self._ring()
        if not points or not self._fits(dimension, len(points)):
            return None
        try:
            start = self._device_point(dimension.first.point(points))
            end = self._device_point(dimension.second.point(points))
            outward = normal(points, dimension)
        except DimensionError:
            return None
        direction = self._device_direction(outward)
        shift = dimension.offset_mm * self.pixels_per_mm()
        first = QPointF(start.x() + direction.x() * shift, start.y() + direction.y() * shift)
        second = QPointF(end.x() + direction.x() * shift, end.y() + direction.y() * shift)
        return first, second, direction, start, end

    def _dimension_value(self, dimension: Dimension) -> float | None:
        points = self._ring()
        if not points or not self._fits(dimension, len(points)):
            return None
        try:
            return measure(points, dimension)
        except DimensionError:
            return None

    def _dimension_text(self, dimension: Dimension) -> str:
        value = self._dimension_value(dimension)
        if value is None:
            return ""
        label = format_value(from_mm(value, self._unit), self._decimals)
        if self._is_highlighted(value):
            _, name = self._value_highlight or (0.0, "")
            return f"{name} = {label}" if name else label
        return label

    def _is_highlighted(self, value: float | None) -> bool:
        if self._value_highlight is None or value is None:
            return False
        return abs(value - self._value_highlight[0]) <= 1e-6

    def _dimension_box(self, dimension: Dimension, metrics=None) -> QRectF:
        """Device rectangle the dimension text occupies; also the target of a click."""
        if metrics is None:
            metrics = QFontMetricsF(self.font())
        label = self._dimension_text(dimension)
        width = metrics.horizontalAdvance(label)
        height = metrics.height()
        frame = self.dimension_frame(dimension)
        if frame is None:
            return QRectF()
        first, second, direction, _, _ = frame
        middle = QPointF((first.x() + second.x()) / 2, (first.y() + second.y()) / 2)
        centre = QPointF(
            middle.x() + direction.x() * (DIM_GAP_PX + 2.0),
            middle.y() + direction.y() * (DIM_GAP_PX + 2.0),
        )
        return QRectF(centre.x() - width / 2 - 3, centre.y() - height / 2 - 1, width + 6, height + 2)

    def dimension_at(self, position: QPoint) -> Dimension | None:
        """The dimension whose text sits under the cursor, if any (specs S5, S9)."""
        if not self._dims_visible:
            return None
        point = QPointF(position)
        for dimension in self._dimensions:
            box = self._dimension_box(dimension)
            if not box.isNull() and box.adjusted(-6, -6, 6, 6).contains(point):
                return dimension
        return None

    # ------------------------------------------------------------------ dimension tool

    def _default_offset_mm(self) -> float:
        """Put a new dimension line where the derived ones used to sit, 26 px out."""
        return DIM_OFFSET_PX / self.pixels_per_mm()

    def begin_dimension_tool(self) -> bool:
        """Arm the dimension tool: pick a reference, pick another, then place the line."""
        if len(self._ring()) < 3:
            return False
        if self._tool_active:
            return True
        self._tool_active = True
        self._tool_anchors = []
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.dimensionToolChanged.emit(True)
        self.dimensionStepChanged.emit(0)
        self.viewport().update()
        return True

    def cancel_dimension_tool(self) -> None:
        """Leave the tool and forget whatever was half-picked."""
        if not self._tool_active:
            return
        self._tool_active = False
        self._tool_anchors = []
        self.viewport().unsetCursor()
        self.dimensionToolChanged.emit(False)
        self.dimensionStepChanged.emit(0)
        self.viewport().update()

    def is_placing_dimension(self) -> bool:
        return self._tool_active

    def pending_anchors(self) -> tuple[Anchor, ...]:
        return tuple(self._tool_anchors)

    def _tool_click(self, scene_pos: QPointF) -> bool:
        """One click of the dimension tool; returns whether it consumed the click."""
        if len(self._tool_anchors) >= 2:
            pending = self.pending_dimension()
            if pending is None:
                self._tool_anchors = []
                return False
            self.add_dimension(
                pending.first, pending.second, pending.kind, offset_mm=pending.offset_mm
            )
            self._tool_anchors = []
            self.viewport().update()
            return True
        self.snapped_point(scene_pos)  # re-lock at the click itself, guides included
        anchors = self._anchor_at(scene_pos)
        if not anchors:
            return False
        for anchor in anchors:
            if len(self._tool_anchors) < 2:
                self._tool_anchors.append(anchor)
        self.dimensionStepChanged.emit(len(self._tool_anchors))
        self.viewport().update()
        return True

    def _anchor_at(self, scene_pos: QPointF) -> tuple[Anchor, ...]:
        """The references one click selects: a vertex, a whole edge, or a point on an edge."""
        model = self._cursor_locked or Point(scene_pos.x(), -scene_pos.y())
        node = self._node_at(scene_pos)
        if node is not None:
            return (Anchor(ANCHOR_VERTEX, node.index),)
        segment = self.segment_at(scene_pos)
        if segment is None or segment[0] != OUTER:
            return ()
        points = self._ring()
        index = segment[1]
        parameter = self._edge_parameter(index, model)
        if parameter <= 0.0:
            return (Anchor(ANCHOR_VERTEX, index),)
        if parameter >= 1.0:
            return (Anchor(ANCHOR_VERTEX, (index + 1) % len(points)),)
        # One reference per click, the way a CAD picks them: no click ever takes a whole edge,
        # so the user chooses both extremes instead of accepting the line the pointer landed on.
        return (Anchor(ANCHOR_EDGE, index, parameter),)

    def _edge_parameter(self, index: int, point: Point) -> float:
        """Where a click falls along an edge, snapped to an end or the middle when close."""
        points = self._ring()
        start = points[index]
        end = points[(index + 1) % len(points)]
        dx, dy = end.x - start.x, end.y - start.y
        span = dx * dx + dy * dy
        if span <= 1e-12:
            return 0.5
        t = max(0.0, min(1.0, ((point.x - start.x) * dx + (point.y - start.y) * dy) / span))
        for fixed in (0.0, 0.5, 1.0):
            if abs(t - fixed) <= 0.08:
                return fixed
        return round(t, 4)

    def _kind_for(self, first: Anchor, second: Anchor) -> str | None:
        """Which measure these two references describe, the way CAD reads the cursor."""
        points = self._ring()
        try:
            start = first.point(points)
            end = second.point(points)
        except DimensionError:
            return None
        count = len(points)
        if (
            first.kind == ANCHOR_VERTEX
            and second.kind == ANCHOR_VERTEX
            and second.index == (first.index + 1) % count
        ):
            return SEGMENT_LENGTH
        dx = abs(end.x - start.x)
        dy = abs(end.y - start.y)
        if dy <= 1e-6 and dx > 1e-6:
            return HORIZONTAL
        if dx <= 1e-6 and dy > 1e-6:
            return VERTICAL
        cursor = self._cursor_place
        if cursor is None:
            return HORIZONTAL
        middle = Point((start.x + end.x) / 2, (start.y + end.y) / 2)
        return HORIZONTAL if abs(cursor.x - middle.x) >= abs(cursor.y - middle.y) else VERTICAL

    def _offset_from_cursor(self, points: list[Point], dimension: Dimension) -> float:
        """Signed distance from the measured entity to the cursor, along the normal."""
        cursor = self._cursor_place
        if cursor is None:
            return dimension.offset_mm
        try:
            outward = normal(points, dimension)
            start = dimension.first.point(points)
            end = dimension.second.point(points)
        except DimensionError:
            return dimension.offset_mm
        middle = Point((start.x + end.x) / 2, (start.y + end.y) / 2)
        return (cursor.x - middle.x) * outward.x + (cursor.y - middle.y) * outward.y

    def pending_dimension(self) -> Dimension | None:
        """The dimension the tool would place right now, with the cursor as its offset."""
        if len(self._tool_anchors) < 2:
            return None
        kind = self._kind_for(self._tool_anchors[0], self._tool_anchors[1])
        if kind is None:
            return None
        points = self._ring()
        candidate = Dimension(
            id=0,
            first=self._tool_anchors[0],
            second=self._tool_anchors[1],
            kind=kind,
            offset_mm=0.0,
        )
        return replace(candidate, offset_mm=self._offset_from_cursor(points, candidate))

    # ------------------------------------------------------------------ dimensions

    def begin_dimension_edit(self, dimension: Dimension) -> bool:
        """Open a one-line editor over the text, prefilled in the active unit."""
        value = self._dimension_value(dimension)
        if value is None or not self.can_drive(dimension):
            return False
        self.close_dimension_editor()
        editor = _DimensionEditor(self.viewport())
        editor.setObjectName("dimension_editor")
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setText(format_value(from_mm(value, self._unit), self._decimals))
        box = self._dimension_box(dimension)
        if box.isNull():
            return False
        editor.setGeometry(box.toRect().adjusted(-10, -4, 10, 4))
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
        self.drive_dimension(dimension.id, value)

    def _measures_segment(self, dimension: Dimension, index: int, count: int) -> bool:
        """True when this dimension is the length of ring segment ``index``."""
        first, second = dimension.anchors
        if first.kind == ANCHOR_EDGE and second.kind == ANCHOR_EDGE:
            if first.index == index and second.index == index:
                return abs(first.t) <= 1e-9 and abs(second.t - 1.0) <= 1e-9
            return False
        if first.kind == ANCHOR_VERTEX and second.kind == ANCHOR_VERTEX:
            return first.index == index and second.index == (index + 1) % count
        return False

    # ------------------------------------------------------------------ guides

    def set_guides_visible(self, visible: bool) -> None:
        """Show or hide the alignment guides (spec S12)."""
        self._guides_visible = visible
        if not visible:
            self._guides = []
            self.guidesChanged.emit("")
        self.viewport().update()

    def guides_visible(self) -> bool:
        return self._guides_visible

    def current_guides(self) -> list:
        return list(self._guides)

    def guides_label(self) -> str:
        """Name the references the cursor is aligned with, for the status bar."""
        if not self._guides:
            return ""
        return " · ".join(
            f"{'X' if guide.axis == GUIDE_X else 'Y'} con {self._reference_name(guide.source)}"
            for guide in self._guides
        )

    def _reference_name(self, point: Point) -> str:
        for contour in (self._section.outer, self._section.inner):
            if contour is None or not contour.points:
                continue
            for index, vertex in enumerate(contour.points):
                if abs(vertex.x - point.x) <= 1e-6 and abs(vertex.y - point.y) <= 1e-6:
                    return f"v{index}"
            count = len(contour.points)
            for index in range(count):
                start, end = contour.points[index], contour.points[(index + 1) % count]
                if abs((start.x + end.x) / 2 - point.x) <= 1e-6 and abs(
                    (start.y + end.y) / 2 - point.y
                ) <= 1e-6:
                    return "punto medio"
        return "punto de referencia"

    def _draw_guides(self, painter: QPainter) -> None:
        """Dashed reference lines that show what the cursor is aligned with (spec S12)."""
        if not self._guides_visible or not self._guides:
            return
        painter.setPen(QPen(QColor(_PALETTE["snap"]), 1.0, Qt.PenStyle.DotLine))
        width = float(self.viewport().width())
        height = float(self.viewport().height())
        for guide in self._guides:
            if guide.axis == GUIDE_X:
                x = self._device_point(Point(guide.coordinate, 0.0)).x()
                painter.drawLine(QPointF(x, 0.0), QPointF(x, height))
            else:
                y = self._device_point(Point(0.0, guide.coordinate)).y()
                painter.drawLine(QPointF(0.0, y), QPointF(width, y))
            source = self._device_point(guide.source)
            painter.drawLine(QPointF(source.x() - 4, source.y()), QPointF(source.x() + 4, source.y()))
            painter.drawLine(QPointF(source.x(), source.y() - 4), QPointF(source.x(), source.y() + 4))

    def _draw_dimensions(self, painter: QPainter) -> None:
        """Every dimension the user placed, and none other (spec S1)."""
        if not self._dims_visible:
            return
        font = painter.font()
        font.setPointSizeF(8.0)
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        for dimension in self._dimensions:
            self._draw_one_dimension(painter, dimension, metrics)

    def _draw_one_dimension(self, painter: QPainter, dimension: Dimension, metrics) -> None:
        frame = self.dimension_frame(dimension)
        if frame is None:
            return
        first, second, direction, start, end = frame
        value = self._dimension_value(dimension)
        selected = dimension.id == self._selected_dimension
        highlighted = self._is_highlighted(value)
        accent = selected or highlighted
        drivable = self.can_drive(dimension)
        colour = QColor(_PALETTE["accent"] if accent else _PALETTE["dim_text"])
        line = QColor(_PALETTE["accent"] if accent else _PALETTE["dim"])
        style = Qt.PenStyle.SolidLine if drivable else Qt.PenStyle.DashLine
        painter.setPen(QPen(line, 2.0 if selected else 1.0, style))
        painter.drawLine(first, second)
        for anchor, target in ((start, first), (end, second)):
            painter.drawLine(
                QPointF(
                    anchor.x() + direction.x() * DIM_GAP_PX,
                    anchor.y() + direction.y() * DIM_GAP_PX,
                ),
                QPointF(
                    target.x() + direction.x() * DIM_GAP_PX,
                    target.y() + direction.y() * DIM_GAP_PX,
                ),
            )
        box = self._dimension_box(dimension, metrics)
        if box.isNull():
            return
        painter.fillRect(box, QColor(_PALETTE["canvas"]))
        painter.setPen(QPen(colour))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self._dimension_text(dimension))

    def _draw_dimension_preview(self, painter: QPainter) -> None:
        """The dimension the tool would place, following the cursor."""
        pending = self.pending_dimension()
        if pending is None:
            return
        points = self._ring()
        try:
            outward = normal(points, pending)
            start = self._device_point(pending.first.point(points))
            end = self._device_point(pending.second.point(points))
        except DimensionError:
            return
        direction = self._device_direction(outward)
        shift = pending.offset_mm * self.pixels_per_mm()
        first = QPointF(start.x() + direction.x() * shift, start.y() + direction.y() * shift)
        second = QPointF(end.x() + direction.x() * shift, end.y() + direction.y() * shift)
        painter.setPen(QPen(QColor(_PALETTE["accent"]), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(first, second)
        for anchor, target in ((start, first), (end, second)):
            painter.drawLine(anchor, target)
        value = measure(points, pending)
        label = format_value(from_mm(value, self._unit), self._decimals)
        middle = QPointF((first.x() + second.x()) / 2, (first.y() + second.y()) / 2)
        text = QPointF(
            middle.x() + direction.x() * (DIM_GAP_PX + 12.0),
            middle.y() + direction.y() * (DIM_GAP_PX + 12.0),
        )
        painter.drawText(text, label)

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
        """The osnap marker: a bright green glyph on a dark halo, plus the family name (S5).

        A CAD's marker has to be readable over any geometry, so the glyph is drawn twice: a
        thick dark outline first and the green mark on top of it.
        """
        if self._snap_kind is None or self._cursor_scene is None:
            return
        point = self.mapFromScene(self._cursor_scene)
        green = QColor(_PALETTE["snap_marker"])
        halo = QColor(_PALETTE["panel"])
        halo.setAlpha(210)
        size = SNAP_GLYPH_PX
        for colour, width in ((halo, SNAP_HALO_PX), (green, 2.4)):
            pen = QPen(colour, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            self._draw_snap_glyph(painter, self._snap_kind, point, size)
        self._draw_snap_label(painter, point, size, green)

    def _draw_snap_glyph(self, painter: QPainter, kind, point: QPointF, size: float) -> None:
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

    def _draw_snap_label(self, painter: QPainter, point: QPointF, size: float, colour: QColor) -> None:
        """The family name on a chip, so it reads over the grid too."""
        assert self._snap_kind is not None
        name = strings.label_for(f"snap_{self._snap_kind.value.lower()}")
        metrics = QFontMetricsF(painter.font())
        width = metrics.horizontalAdvance(name) + 10
        height = metrics.height() + 2
        left = point.x() + size + 5
        top = point.y() - size - height
        chip = QColor(_PALETTE["panel"])
        chip.setAlpha(220)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(chip))
        painter.drawRoundedRect(QRectF(left, top, width, height), 4, 4)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(colour))
        painter.drawText(QPointF(left + 5, top + metrics.ascent() + 1), name)

    def _selected_point(self) -> QPointF | None:
        chosen = self.selected_vertex()
        if chosen is None:
            return None
        name, index = chosen
        contour = self._section.outer if name == OUTER else self._section.inner
        if contour is None or not 0 <= index < len(contour.points):
            return None
        point = contour.points[index]
        return self.mapFromScene(QPointF(point.x, -point.y))

    def _draw_selected_vertex(self, painter: QPainter) -> None:
        """A ring and the vertex index, because the handle alone is too small to read."""
        colour = QColor(_PALETTE["handle_selected"])
        painter.setPen(QPen(colour, 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for name, index in sorted(self._selection):
            contour = self._contour(name)
            if contour is None or not 0 <= index < len(contour.points):
                continue
            spot = contour.points[index]
            point = self.mapFromScene(QPointF(spot.x, -spot.y))
            painter.drawEllipse(point, SELECTED_RING_PX, SELECTED_RING_PX)
            painter.drawText(
                QPointF(point.x() + SELECTED_RING_PX + 3, point.y() - SELECTED_RING_PX),
                f"v{index}",
            )

    def _draw_selected_segment(self, painter: QPainter) -> None:
        """Draw the picked edge on top, so it reads as selected at any zoom."""
        segment = self._segment
        if segment is None:
            return
        contour = self._contour(segment[0])
        if contour is None or not contour.points:
            return
        count = len(contour.points)
        if not 0 <= segment[1] < count:
            return
        start = contour.points[segment[1]]
        end = contour.points[(segment[1] + 1) % count]
        first = self.mapFromScene(QPointF(start.x, -start.y))
        second = self.mapFromScene(QPointF(end.x, -end.y))
        painter.setPen(QPen(QColor(_PALETTE["handle_selected"]), 2.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPoint(int(first.x()), int(first.y())), QPoint(int(second.x()), int(second.y())))

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
        self._draw_dimension_preview(painter)
        self._draw_guides(painter)

        if self._cursor_scene is not None:
            cursor = self.mapFromScene(self._cursor_scene)
            painter.setPen(QPen(QColor(_PALETTE["crosshair"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPoint(cursor.x(), 0), QPoint(cursor.x(), height))
            painter.drawLine(QPoint(0, cursor.y()), QPoint(width, cursor.y()))
            painter.setPen(QPen(QColor(_PALETTE["text_faint"])))
            painter.drawText(QPoint(cursor.x() + 8, cursor.y() - 6), f"{self._cursor_scene.x():.1f}, {-self._cursor_scene.y():.1f}")
        self._draw_selected_segment(painter)
        self._draw_snap(painter)
        self._draw_selected_vertex(painter)
        painter.restore()

    # ------------------------------------------------------------- mouse and keys

    def _update_band(self, current: QPointF) -> None:
        """Draw the selection window while the button is held (S3)."""
        if self._band_origin is None:
            return
        rect = QRectF(self._band_origin, current).normalized()
        if self._band_item is None:
            fill = QColor(_PALETTE["handle_selected"])
            fill.setAlpha(40)
            self._band_item = QGraphicsRectItem(rect)
            self._band_item.setPen(_BAND_PEN)
            self._band_item.setBrush(QBrush(fill))
            self._band_item.setZValue(3)
            self._scene.addItem(self._band_item)
        else:
            self._band_item.setRect(rect)

    def _finish_band(self, current: QPointF) -> None:
        """A click on empty space deselects; a drag selects what the window covers (S3)."""
        origin = self._band_origin
        self._band_origin = None
        if self._band_item is not None:
            self._scene.removeItem(self._band_item)
            self._band_item = None
        if origin is None:
            return
        start = self.mapFromScene(origin)
        end = self.mapFromScene(current)
        if hypot(end.x() - start.x(), end.y() - start.y()) <= BAND_CLICK_PX:
            self.clear_selection()
            return
        rect = QRectF(origin, current).normalized()
        # Left to right takes what stays inside; right to left takes what it touches.
        self.select_vertices(self._vertices_in(rect, window=current.x() >= origin.x()))

    def _vertices_in(self, rect: QRectF, *, window: bool) -> list[tuple[str, int]]:
        """Vertices inside the rectangle, plus, for a crossing window, the edges it touches."""
        chosen: list[tuple[str, int]] = []
        for name, contour in ((OUTER, self._section.outer), (INNER, self._section.inner)):
            if contour is None or not contour.points:
                continue
            count = len(contour.points)
            for index, point in enumerate(contour.points):
                scene_point = QPointF(point.x, -point.y)
                if rect.contains(scene_point):
                    chosen.append((name, index))
                    continue
                if window:
                    continue
                following = contour.points[(index + 1) % count]
                edge = QLineF(scene_point, QPointF(following.x, -following.y))
                if _line_hits_rect(edge, rect):
                    chosen.append((name, index))
        return chosen

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_origin = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton and self._rectangle_armed:
            self.cancel_rectangle_tool()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._rectangle_armed:
            self.setFocus()
            point, _ = self.snapped_point(self.mapToScene(event.position().toPoint()))
            if self._rectangle_start is None:
                self._rectangle_start = point
                event.accept()
                return
            try:
                corners = rectangle_ring(self._rectangle_start, point)
            except SketchError as error:
                self.editRejected.emit(error.code)
                self.cancel_rectangle_tool()
                event.accept()
                return
            self.cancel_rectangle_tool()
            self.replace_outer(corners, strings.label_for("undo_rectangle"))
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton and self._tool_active:
            self.cancel_dimension_tool()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._tool_active:
            self.setFocus()
            self._tool_click(self.mapToScene(event.position().toPoint()))
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton and self.is_drawing():
            if len(self._section.outer.points) >= 3:
                self.close_contour()
            else:
                self.end_drawing()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._editable:
            self.setFocus()
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
                dimension = self.dimension_at(event.position().toPoint())
                if dimension is not None:
                    self.select_dimension(dimension.id)
                    self._dimension_drag = (dimension, self._snapshot())
                    event.accept()
                    return
                segment = self.segment_at(scene_pos)
                if segment is not None:
                    self.select_segment(*segment)
                    event.accept()
                    return
                # Empty space: a click deselects and a drag opens a selection window (S1, S3).
                self._band_origin = scene_pos
                event.accept()
                return
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
        if self._rectangle_start is not None:
            point, _ = self.snapped_point(scene_pos)
            rect = QRectF(
                QPointF(self._rectangle_start.x, -self._rectangle_start.y),
                QPointF(point.x, -point.y),
            ).normalized()
            if self._rectangle_preview is None:
                self._rectangle_preview = QGraphicsRectItem(rect)
                self._rectangle_preview.setPen(_DRAFT_PEN)
                self._rectangle_preview.setZValue(2)
                self._scene.addItem(self._rectangle_preview)
            else:
                self._rectangle_preview.setRect(rect)
            event.accept()
            return
        if self._band_origin is not None:
            self._update_band(scene_pos)
            event.accept()
            return
        self._cursor_scene = scene_pos
        point, kind = self.snapped_point(scene_pos)
        self.snapChanged.emit(kind.value if kind is not None else "")
        self.guidesChanged.emit(self.guides_label())
        self.cursorMoved.emit(point.x, point.y)
        self._snap_kind = kind
        self.viewport().update()

        if self._dimension_drag is not None:
            dimension, before = self._dimension_drag
            moved = replace(
                dimension, offset_mm=self._offset_from_cursor(self._ring(), dimension)
            )
            self._dimensions = [
                moved if item.id == dimension.id else item for item in self._dimensions
            ]
            self._dimension_drag = (moved, before)
            event.accept()
            return

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

        if event.button() == Qt.MouseButton.LeftButton and self._band_origin is not None:
            self._finish_band(self.mapToScene(event.position().toPoint()))
            event.accept()
            return

        if self._dimension_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            _, before = self._dimension_drag
            self._dimension_drag = None
            after = self._snapshot()
            if after != before:
                self._apply_snapshot(before)
                self._commit_snapshot(after, strings.label_for("undo_dimension"))
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
            if dimension is not None:
                self.select_dimension(dimension.id)
                if not self.begin_dimension_edit(dimension):
                    _, code = is_editable(self._ring(), dimension)
                    self.editRejected.emit(code or "not_drivable")
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.is_drawing():
            self.close_contour()
            event.accept()
            return
        # `Esc` is not handled here: the command it cancels belongs to the window (spec S15),
        # so leaving the key alone lets it travel up to the window that owns the command.
        if key == Qt.Key.Key_Delete:
            if self.delete_selection():
                event.accept()
                return
        if self._begin_segment_typing(event.text()):
            event.accept()
            return
        super().keyPressEvent(event)

    def _begin_segment_typing(self, text: str) -> bool:
        """A digit on the picked edge opens its dimension editor, the way CAD takes input."""
        if not self._editable or self._segment is None or self.is_drawing():
            return False
        if len(text) != 1 or text not in "0123456789,.-":
            return False
        contour, index = self._segment
        if contour != OUTER:
            self.editRejected.emit("segment_not_editable")
            return True
        count = len(self._ring())
        dimension = next(
            (item for item in self._dimensions if self._measures_segment(item, index, count)),
            None,
        )
        if dimension is None:
            # No dimension was placed here, so there is nothing a number could move.
            self.editRejected.emit("segment_not_dimensioned")
            return True
        if not self.can_drive(dimension):
            self.editRejected.emit("segment_not_editable")
            return True
        if not self.begin_dimension_edit(dimension):
            return True
        editor = self._dimension_editor
        if editor is not None:
            editor.setText(text)
            editor.setCursorPosition(len(text))
        return True

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
