"""Snapping geometry for the drawing canvas (spec S8).

Pure geometry so the rules can be tested without Qt: the canvas only feeds the cursor
position and asks for the nearest candidate.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from sectionlab.core.model import Contour, Point


class SnapKind(str, Enum):
    """Snap families, ordered by priority when two candidates are equally close."""

    ENDPOINT = "ENDPOINT"
    INTERSECTION = "INTERSECTION"
    MIDPOINT = "MIDPOINT"
    CENTER = "CENTER"
    PERPENDICULAR = "PERPENDICULAR"


_PRIORITY = {
    SnapKind.ENDPOINT: 0,
    SnapKind.INTERSECTION: 1,
    SnapKind.MIDPOINT: 2,
    SnapKind.CENTER: 3,
    SnapKind.PERPENDICULAR: 4,
}


@dataclass(frozen=True)
class Snap:
    """A snap candidate: the point to use and the family that produced it."""

    point: Point
    kind: SnapKind
    distance: float = 0.0


def edges(contour: Contour) -> list[tuple[Point, Point]]:
    """Consecutive edges of a contour, including the closing edge when the contour closes."""
    points = list(contour.points)
    pairs = list(zip(points, points[1:]))
    if contour.closed and len(points) > 2:
        pairs.append((points[-1], points[0]))
    return pairs


def midpoint(first: Point, second: Point) -> Point:
    return Point((first.x + second.x) / 2, (first.y + second.y) / 2)


def contour_center(contour: Contour) -> Point:
    """Centre of the contour's bounding box."""
    xs = [point.x for point in contour.points]
    ys = [point.y for point in contour.points]
    return Point((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def segment_intersection(
    first: tuple[Point, Point], second: tuple[Point, Point]
) -> Point | None:
    """Intersection point of two segments, or `None` when they are parallel or disjoint."""
    a, b = first
    e, g = second
    x1, y1, x2, y2 = a.x, a.y, b.x, b.y
    x3, y3, x4, y4 = e.x, e.y, g.x, g.y
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if denominator == 0.0:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denominator
    if not (-1e-12 <= t <= 1 + 1e-12 and -1e-12 <= u <= 1 + 1e-12):
        return None
    return Point(x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def perpendicular_foot(origin: Point, edge: tuple[Point, Point]) -> Point | None:
    """Foot of the perpendicular from `origin` to the edge's segment."""
    start, end = edge
    x1, y1, x2, y2 = start.x, start.y, end.x, end.y
    dx, dy = x2 - x1, y2 - y1
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return None
    t = ((origin.x - x1) * dx + (origin.y - y1) * dy) / length_squared
    if not 0.0 <= t <= 1.0:
        return None
    return Point(x1 + t * dx, y1 + t * dy)


def candidates(contours: Sequence[Contour], anchors: Iterable[Point] = ()) -> list[Snap]:
    """Every snap candidate of the drawing: vertices, midpoints, crossings, centres, feet."""
    found: list[Snap] = []
    all_edges: list[tuple[Point, Point]] = []

    for contour in contours:
        if len(contour.points) < 2:
            continue
        contour_edges = edges(contour)
        all_edges.extend(contour_edges)
        for point in contour.points:
            found.append(Snap(point, SnapKind.ENDPOINT))
        for edge in contour_edges:
            found.append(Snap(midpoint(*edge), SnapKind.MIDPOINT))
        found.append(Snap(contour_center(contour), SnapKind.CENTER))

    for index, first in enumerate(all_edges):
        for second in all_edges[index + 1 :]:
            crossing = segment_intersection(first, second)
            if crossing is not None and crossing not in first and crossing not in second:
                found.append(Snap(crossing, SnapKind.INTERSECTION))

    for anchor in anchors:
        for edge in all_edges:
            foot = perpendicular_foot(anchor, edge)
            if foot is not None:
                found.append(Snap(foot, SnapKind.PERPENDICULAR))

    return found


def find_snap(target: Point, candidates: Sequence[Snap], tolerance: float) -> Snap | None:
    """Nearest candidate within `tolerance`, preferring endpoints on a distance tie."""
    best: Snap | None = None
    for candidate in candidates:
        distance = math.hypot(candidate.point.x - target.x, candidate.point.y - target.y)
        if distance > tolerance:
            continue
        if best is None:
            best = Snap(candidate.point, candidate.kind, distance)
            continue
        if distance < best.distance - 1e-12 or (
            math.isclose(distance, best.distance, abs_tol=1e-12)
            and _PRIORITY[candidate.kind] < _PRIORITY[best.kind]
        ):
            best = Snap(candidate.point, candidate.kind, distance)
    return best


def apply_ortho(origin: Point, target: Point) -> Point:
    """Lock the segment from `origin` to `target` onto the dominant axis."""
    if abs(target.x - origin.x) >= abs(target.y - origin.y):
        return Point(target.x, origin.y)
    return Point(origin.x, target.y)


GUIDE_X = "x"
"""Guide family of a vertical line: it shares an x with an existing reference point."""

GUIDE_Y = "y"
"""Guide family of a horizontal line: it shares a y with an existing reference point."""

_TIE_EPSILON = 1e-12


@dataclass(frozen=True)
class Alignment:
    """A reference line the cursor shares one coordinate with (spec S12).

    `source` is the reference point the guide comes from and `delta` the absolute mismatch
    between the cursor and `coordinate` at the moment the guide was computed. A guide is
    decoration only: it never moves a vertex and never takes part in undo.
    """

    axis: str
    coordinate: float
    source: Point
    delta: float

    def line_end(self, target: Point) -> Point:
        """Point where the guide crosses the cursor, so the canvas ends the dashed line."""
        if self.axis == GUIDE_X:
            return Point(self.coordinate, target.y)
        return Point(target.x, self.coordinate)


def _target_coordinate(target: Point, axis: str) -> float:
    return target.x if axis == GUIDE_X else target.y


def _candidate_coordinate(candidate: Snap, axis: str) -> float:
    return candidate.point.x if axis == GUIDE_X else candidate.point.y


def _precedes(
    better: tuple[float, float, int, float], worse: tuple[float, float, int, float]
) -> bool:
    """Ordering of two candidate guides: mismatch on the axis, distance, then priority.

    The raw coordinate is the last resort, so even two candidates of the same family that tie
    on everything else resolve the same way whatever order the candidates arrive in.
    """
    better_delta, better_distance, better_priority, better_coordinate = better
    worse_delta, worse_distance, worse_priority, worse_coordinate = worse
    if not math.isclose(better_delta, worse_delta, abs_tol=_TIE_EPSILON):
        return better_delta < worse_delta
    if not math.isclose(better_distance, worse_distance, abs_tol=_TIE_EPSILON):
        return better_distance < worse_distance
    if better_priority != worse_priority:
        return better_priority < worse_priority
    if not math.isclose(better_coordinate, worse_coordinate, abs_tol=_TIE_EPSILON):
        return better_coordinate < worse_coordinate
    return False


def _best_guide(
    candidates: Sequence[Snap], target: Point, axis: str, tolerance: float
) -> Alignment | None:
    """Winning guide of one axis, or `None` when no candidate is within `tolerance`."""
    best: Alignment | None = None
    best_key: tuple[float, float, int, float] | None = None
    for candidate in candidates:
        coordinate = _candidate_coordinate(candidate, axis)
        delta = abs(_target_coordinate(target, axis) - coordinate)
        if delta > tolerance:
            continue
        distance = math.hypot(candidate.point.x - target.x, candidate.point.y - target.y)
        key = (delta, distance, _PRIORITY[candidate.kind], coordinate)
        if best_key is not None and not _precedes(key, best_key):
            continue
        best = Alignment(
            axis=axis, coordinate=coordinate, source=candidate.point, delta=delta
        )
        best_key = key
    return best


def alignments(
    candidates: Sequence[Snap], target: Point, tolerance: float
) -> list[Alignment]:
    """At most one guide per axis, vertical first, for the cursor at `target`.

    `tolerance` is a distance in millimetres supplied by the caller. When several candidates
    qualify for the same axis the smallest mismatch wins, ties go to the smaller Euclidean
    distance to `target`, and a full tie falls back to the snap priority, so the result is
    deterministic. Candidates sharing a coordinate collapse onto a single guide.
    """
    found: list[Alignment] = []
    for axis in (GUIDE_X, GUIDE_Y):
        guide = _best_guide(candidates, target, axis, tolerance)
        if guide is not None:
            found.append(guide)
    return found


def apply_alignment(target: Point, guides: Sequence[Alignment]) -> Point:
    """Lock the cursor onto the guides, so an aligned point is exactly aligned."""
    x, y = target.x, target.y
    for guide in guides:
        if guide.axis == GUIDE_X:
            x = guide.coordinate
        elif guide.axis == GUIDE_Y:
            y = guide.coordinate
    if x == target.x and y == target.y:
        return target
    return Point(x, y)
