"""Dimensions the user places, in millimetres and without Qt (specs S3-S5, S7, S10).

The measured value is never stored: it is read from the geometry every time, so the number on
screen and the drawing cannot disagree. What is stored is what the dimension refers to (two
anchors), which measure it is, and how far from the measured entity its line sits.

An anchor is durable by design: it names a vertex, or a point at parameter ``t`` along an edge,
so a dimension survives the geometry moving and can be remapped when vertices are inserted or
deleted, or when the contour winding is reversed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from sectionlab.core.model import Point

ANCHOR_VERTEX = "vertex"
ANCHOR_EDGE = "edge"

SEGMENT_LENGTH = "segment"
HORIZONTAL = "horizontal"
VERTICAL = "vertical"

TOLERANCE_MM = 1e-9


class DimensionError(ValueError):
    """An unusable dimension; ``code`` is stable English text the interface translates."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Anchor:
    """A durable reference into a vertex ring: a vertex, or a point along one of its edges."""

    kind: str
    index: int
    t: float = 0.0

    def point(self, points: Sequence[Point]) -> Point:
        """The point this anchor names, in millimetres."""
        count = len(points)
        if not 0 <= self.index < count:
            raise DimensionError("out_of_range", "anchor outside the contour")
        if self.kind == ANCHOR_VERTEX:
            return points[self.index]
        if self.kind != ANCHOR_EDGE:
            raise DimensionError("unknown_anchor", f"unknown anchor kind {self.kind!r}")
        start = points[self.index]
        end = points[(self.index + 1) % count]
        return Point(start.x + self.t * (end.x - start.x), start.y + self.t * (end.y - start.y))


@dataclass(frozen=True)
class Dimension:
    """One measurement the user placed, between two anchors."""

    id: int
    first: Anchor
    second: Anchor
    kind: str
    offset_mm: float = 0.0

    @property
    def anchors(self) -> tuple[Anchor, Anchor]:
        return self.first, self.second


def _dot(point: Point, direction: Point) -> float:
    return point.x * direction.x + point.y * direction.y


def _same(first: Point, second: Point, tolerance: float) -> bool:
    return abs(first.x - second.x) <= tolerance and abs(first.y - second.y) <= tolerance


def _centre(points: Sequence[Point]) -> Point:
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    return Point((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def measure(points: Sequence[Point], dimension: Dimension) -> float:
    """The dimension's current value, read from the geometry."""
    start = dimension.first.point(points)
    end = dimension.second.point(points)
    if dimension.kind == SEGMENT_LENGTH:
        return ((end.x - start.x) ** 2 + (end.y - start.y) ** 2) ** 0.5
    if dimension.kind == HORIZONTAL:
        return abs(end.x - start.x)
    if dimension.kind == VERTICAL:
        return abs(end.y - start.y)
    raise DimensionError("unknown_kind", f"unknown dimension kind {dimension.kind!r}")


def axis(points: Sequence[Point], dimension: Dimension) -> Point:
    """Unit direction the measure projects onto; axis-aligned segments stay exactly aligned.

    The direction runs from the first anchor to the second, which is what makes the second
    anchor's side the side that moves: changing a dimension pushes the geometry away from the
    reference the user picked first.
    """
    if dimension.kind == HORIZONTAL:
        return Point(1.0, 0.0)
    if dimension.kind == VERTICAL:
        return Point(0.0, 1.0)
    if dimension.kind != SEGMENT_LENGTH:
        raise DimensionError("unknown_kind", f"unknown dimension kind {dimension.kind!r}")
    start = dimension.first.point(points)
    end = dimension.second.point(points)
    dx = end.x - start.x
    dy = end.y - start.y
    if abs(dy) <= TOLERANCE_MM:
        return Point(1.0 if dx >= 0 else -1.0, 0.0)
    if abs(dx) <= TOLERANCE_MM:
        return Point(0.0, 1.0 if dy >= 0 else -1.0)
    length = (dx * dx + dy * dy) ** 0.5
    return Point(dx / length, dy / length)


def boundary(points: Sequence[Point], dimension: Dimension) -> float:
    """Signed coordinate, along the axis, of the plane through the second anchor.

    Everything at or beyond this plane is the side the solver moves, so the first anchor is the
    reference that stays put.
    """
    return _dot(dimension.second.point(points), axis(points, dimension))


def normal(points: Sequence[Point], dimension: Dimension) -> Point:
    """Unit normal of the measure, pointing away from the middle of the section."""
    direction = axis(points, dimension)
    perpendicular = Point(direction.y, -direction.x)
    if len(points) < 3:
        return perpendicular
    centre = _centre(points)
    middle = Point(
        (dimension.first.point(points).x + dimension.second.point(points).x) / 2,
        (dimension.first.point(points).y + dimension.second.point(points).y) / 2,
    )
    outward = (middle.x - centre.x) * perpendicular.x + (middle.y - centre.y) * perpendicular.y
    if outward < 0:
        return Point(-perpendicular.x, -perpendicular.y)
    return perpendicular


def is_editable(points: Sequence[Point], dimension: Dimension) -> tuple[bool, str]:
    """Whether a single rule can drive this measure, and why not when it cannot.

    A segment length is only drivable while it is axis-aligned, because the value shown is the
    Euclidean length and the solver moves one axis: a slanted segment would end up measuring
    something the user never typed. The closing edge is reference-only because its length
    follows from the other segments.
    """
    try:
        start = dimension.first.point(points)
        end = dimension.second.point(points)
    except DimensionError as error:
        return False, error.code
    if len(points) < 3:
        return False, "too_few_vertices"

    if dimension.kind == SEGMENT_LENGTH:
        if _is_closing(points, start, end):
            return False, "closing_segment"
        if abs(end.x - start.x) > TOLERANCE_MM and abs(end.y - start.y) > TOLERANCE_MM:
            return False, "slanted_segment"
        if _same(start, end, TOLERANCE_MM):
            return False, "unchanged_anchors"
        return True, ""

    if dimension.kind in (HORIZONTAL, VERTICAL):
        if _same(start, end, TOLERANCE_MM):
            return False, "unchanged_anchors"
        extent = abs(end.x - start.x) if dimension.kind == HORIZONTAL else abs(end.y - start.y)
        if extent <= TOLERANCE_MM:
            return False, "unchanged_anchors"
        return True, ""

    return False, "unknown_kind"


def _is_closing(points: Sequence[Point], start: Point, end: Point) -> bool:
    """True when the anchors are the last vertex and the first one, in that order."""
    return _same(start, points[-1], TOLERANCE_MM) and _same(end, points[0], TOLERANCE_MM)


def remap(
    dimension: Dimension,
    *,
    inserted: int | None = None,
    deleted: int | None = None,
    reversed_ring: int = 0,
) -> Dimension | None:
    """The dimension with its anchors re-indexed after the geometry changed.

    Returns ``None`` when an anchor no longer exists, so the caller can drop the dimension and
    say so instead of pointing at a vertex that belongs to something else.
    """
    first: Anchor | None = dimension.first
    second: Anchor | None = dimension.second

    if inserted is not None:
        first = _after_insert(first, inserted)
        second = _after_insert(second, inserted)
    if deleted is not None:
        first = _after_delete(first, deleted)
        second = _after_delete(second, deleted)
        if first is None or second is None:
            return None
    if reversed_ring:
        first = _after_reverse(first, reversed_ring)
        second = _after_reverse(second, reversed_ring)
    if first is None or second is None:
        return None
    return replace(dimension, first=first, second=second)


def _after_insert(anchor: Anchor, index: int) -> Anchor:
    """A vertex was added before old vertex ``index``; the edge ``index - 1`` was split."""
    if anchor.kind == ANCHOR_VERTEX:
        return anchor if anchor.index < index else Anchor(ANCHOR_VERTEX, anchor.index + 1)
    if anchor.kind != ANCHOR_EDGE:
        return anchor
    if anchor.index == index - 1:
        # The split edge keeps the anchor on whichever half holds the same physical point.
        if anchor.t <= 0.5:
            return Anchor(ANCHOR_EDGE, index - 1, anchor.t * 2)
        return Anchor(ANCHOR_EDGE, index, anchor.t * 2 - 1)
    if anchor.index >= index:
        return Anchor(ANCHOR_EDGE, anchor.index + 1, anchor.t)
    return anchor


def _after_delete(anchor: Anchor, index: int) -> Anchor | None:
    """Old vertex ``index`` is gone, and the two edges around it merged into ``index - 1``."""
    if anchor.kind == ANCHOR_VERTEX:
        if anchor.index == index:
            return None
        return anchor if anchor.index < index else Anchor(ANCHOR_VERTEX, anchor.index - 1)
    if anchor.kind != ANCHOR_EDGE:
        return anchor
    if anchor.index in (index - 1, index):
        return None
    return anchor if anchor.index < index else Anchor(ANCHOR_EDGE, anchor.index - 1, anchor.t)


def _after_reverse(anchor: Anchor, count: int) -> Anchor:
    """The ring was wound the other way round, so indices mirror and edges flip their ``t``."""
    if anchor.kind == ANCHOR_VERTEX:
        return Anchor(ANCHOR_VERTEX, count - 1 - anchor.index)
    if anchor.kind != ANCHOR_EDGE:
        return anchor
    return Anchor(ANCHOR_EDGE, (count - 2 - anchor.index) % count, 1.0 - anchor.t)
