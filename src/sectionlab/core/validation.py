"""Contour validation.

Calculation is blocked, saving is not (spec S13). Issues carry stable English codes; the
Spanish sentence the user reads lives in the UI strings module (decision D6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from shapely.geometry import LineString, LinearRing

from sectionlab.core.model import Contour, Point, Section, signed_area

CLOSURE_TOLERANCE_MM = 1e-6


class IssueCode(str, Enum):
    """Why a section cannot be calculated."""

    OPEN_CONTOUR = "OPEN_CONTOUR"
    TOO_FEW_VERTICES = "TOO_FEW_VERTICES"
    DUPLICATE_POINTS = "DUPLICATE_POINTS"
    SELF_INTERSECTION = "SELF_INTERSECTION"
    ZERO_AREA = "ZERO_AREA"


@dataclass(frozen=True)
class ValidationIssue:
    """A blocking problem plus the vertices the drawing should highlight."""

    code: IssueCode
    points: tuple[Point, ...]


def validate_section(section: Section) -> list[ValidationIssue]:
    """Return every blocking issue for the section, outer contour first; empty means valid."""
    issues = list(_validate_contour(section.outer))
    if section.inner is not None:
        issues.extend(_validate_contour(section.inner))
    return issues


def _validate_contour(contour: Contour) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    points = contour.points

    if not contour.closed and points:
        issues.append(ValidationIssue(IssueCode.OPEN_CONTOUR, (points[-1], points[0])))

    if len(points) < 3:
        issues.append(ValidationIssue(IssueCode.TOO_FEW_VERTICES, tuple(points)))
        return issues

    ring = _strip_trailing_closure(points, contour.closed)

    duplicate = _first_duplicate(ring)
    if duplicate is not None:
        issues.append(ValidationIssue(IssueCode.DUPLICATE_POINTS, duplicate))

    crossing = _first_self_intersection(ring)
    if crossing is not None:
        # A self-intersecting ring has no meaningful signed area, so ZERO_AREA is not added.
        issues.append(ValidationIssue(IssueCode.SELF_INTERSECTION, crossing))
        return issues

    if _is_degenerate(ring):
        issues.append(ValidationIssue(IssueCode.ZERO_AREA, ()))

    return issues


def _strip_trailing_closure(points: list[Point], closed: bool) -> list[Point]:
    """Drop an explicit repeat of the first vertex: closure is implicit in the model."""
    if closed and len(points) > 1 and _same_point(points[0], points[-1]):
        return points[:-1]
    return list(points)


def _same_point(first: Point, second: Point) -> bool:
    return (
        abs(first.x - second.x) <= CLOSURE_TOLERANCE_MM
        and abs(first.y - second.y) <= CLOSURE_TOLERANCE_MM
    )


def _first_duplicate(points: list[Point]) -> tuple[Point, Point] | None:
    for index, current in enumerate(points):
        for other in points[index + 1 :]:
            if _same_point(current, other):
                return (current, other)
    return None


def _first_self_intersection(points: list[Point]) -> tuple[Point, ...] | None:
    coordinates = [(point.x, point.y) for point in points]
    try:
        if LinearRing(coordinates).is_simple:
            return None
    except Exception:  # noqa: BLE001 - a degenerate ring must never crash validation
        return None

    crossings: list[Point] = []
    count = len(points)
    for first in range(count):
        first_edge = LineString(
            [
                (points[first].x, points[first].y),
                (points[(first + 1) % count].x, points[(first + 1) % count].y),
            ]
        )
        for second in range(first + 1, count):
            if second - first == 1 or (first == 0 and second == count - 1):
                continue
            second_edge = LineString(
                [
                    (points[second].x, points[second].y),
                    (points[(second + 1) % count].x, points[(second + 1) % count].y),
                ]
            )
            crossings.extend(_intersection_points(first_edge, second_edge))

    unique: list[Point] = []
    for crossing in crossings:
        if not any(_same_point(crossing, known) for known in unique):
            unique.append(crossing)
    return tuple(unique) if unique else ()


def _intersection_points(first: LineString, second: LineString) -> list[Point]:
    shared = first.intersection(second)
    if shared.is_empty:
        return []
    parts = getattr(shared, "geoms", (shared,))
    return [Point(part.x, part.y) for part in parts if part.geom_type == "Point"]


def _is_degenerate(points: list[Point]) -> bool:
    """True when the enclosed area is negligible at the contour's own scale."""
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    extent = max(max(xs) - min(xs), max(ys) - min(ys))
    contour = Contour(points=points)
    return abs(signed_area(contour)) <= CLOSURE_TOLERANCE_MM * max(extent, CLOSURE_TOLERANCE_MM)
