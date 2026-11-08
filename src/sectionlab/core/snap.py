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
