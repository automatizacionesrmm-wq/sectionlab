"""Geometry edits driven by a dimension (spec S3).

Pure functions over millimetre points so the rules are testable without Qt. Changing the width
or the height of one axis-aligned segment shifts every vertex after it, which keeps the ring
closed: the drawing stays a section instead of turning into an open path.
"""

from __future__ import annotations

from collections.abc import Sequence

from sectionlab.core.model import Point

TOLERANCE_MM = 1e-9


class SketchError(ValueError):
    """A refused edit; ``code`` lets the interface answer in Spanish (decision D6)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def segment_length(points: Sequence[Point], index: int) -> float:
    """Distance between vertex ``index`` and the next one along the ring."""
    count = len(points)
    if not 0 <= index < count:
        raise SketchError("out_of_range", "segment index outside the contour")
    start = points[index]
    end = points[(index + 1) % count]
    return ((end.x - start.x) ** 2 + (end.y - start.y) ** 2) ** 0.5


def set_segment_length(
    points: Sequence[Point],
    index: int,
    length_mm: float,
    *,
    tolerance: float = TOLERANCE_MM,
) -> list[Point]:
    """Make one axis-aligned segment measure ``length_mm``.

    The segment keeps its direction and every vertex on the far side of it moves with the
    same delta, which is what keeps a rectangle a rectangle and an I profile symmetric.
    Slanted segments and the closing segment are refused, because their length follows from
    the others.
    """
    count = len(points)
    if count < 3:
        raise SketchError("too_few_vertices", "a dimension needs at least three vertices")
    if not 0 <= index < count:
        raise SketchError("out_of_range", "segment index outside the contour")
    if index == count - 1:
        raise SketchError("closing_segment", "the closing segment follows the others")
    if length_mm <= tolerance:
        raise SketchError("non_positive", "a dimension must be greater than zero")

    start = points[index]
    end = points[index + 1]
    dx = end.x - start.x
    dy = end.y - start.y
    horizontal = abs(dy) <= tolerance and abs(dx) > tolerance
    vertical = abs(dx) <= tolerance and abs(dy) > tolerance
    if not horizontal and not vertical:
        raise SketchError("slanted_segment", "only widths and heights can drive the geometry")

    current = abs(dx) if horizontal else abs(dy)
    if abs(current - length_mm) <= tolerance:
        raise SketchError("unchanged", "the dimension already has that value")

    # The section moves on the far side of the edited segment only, so the edges behind it
    # keep their shape: widening a rectangle's bottom edge makes the rectangle wider instead
    # of shearing its left side.
    delta = length_mm - current
    if horizontal:
        direction = 1.0 if dx > 0 else -1.0
        boundary = end.x
        return [
            Point(point.x + delta * direction, point.y)
            if (point.x - boundary) * direction >= -tolerance
            else point
            for point in points
        ]
    direction = 1.0 if dy > 0 else -1.0
    boundary = end.y
    return [
        Point(point.x, point.y + delta * direction)
        if (point.y - boundary) * direction >= -tolerance
        else point
        for point in points
    ]
