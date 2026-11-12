"""Geometry edits driven by a dimension (specs S3-S5, S7).

Pure functions over millimetre points so the rules are testable without Qt. One single rule
serves every kind of dimension: the geometry at or beyond the plane through the dimension's
second anchor slides along the measured axis by exactly the difference, and everything behind
that plane stays put. Sliding a whole side rigidly is what keeps a rectangle a rectangle and an
I profile symmetric.
"""

from __future__ import annotations

from collections.abc import Sequence

from sectionlab.core.dimensions import (
    ANCHOR_VERTEX,
    SEGMENT_LENGTH,
    Dimension,
    Anchor,
    axis,
    boundary,
    is_editable,
    measure,
)
from sectionlab.core.model import Point

TOLERANCE_MM = 1e-9

_REASON_MESSAGES = {
    "closing_segment": "the closing segment follows the others",
    "slanted_segment": "only widths, heights and axis-aligned lengths can drive the geometry",
    "unchanged_anchors": "the two references do not define a distance on that axis",
    "out_of_range": "the dimension points outside the contour",
    "too_few_vertices": "a dimension needs at least three vertices",
    "unknown_kind": "that kind of dimension cannot drive the geometry",
}


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


def set_measure(
    points: Sequence[Point],
    dimension: Dimension,
    target_mm: float,
    *,
    tolerance: float = TOLERANCE_MM,
) -> list[Point]:
    """Make ``dimension`` measure ``target_mm`` by moving one side of the section.

    The reference the user picked first never moves; the side holding the second anchor slides
    away from it. A measure no single rule can satisfy is refused with a code, never guessed.
    """
    if len(points) < 3:
        raise SketchError("too_few_vertices", "a dimension needs at least three vertices")

    editable, reason = is_editable(points, dimension)
    if not editable:
        raise SketchError(reason, _REASON_MESSAGES.get(reason, reason))
    if target_mm <= tolerance:
        raise SketchError("non_positive", "a dimension must be greater than zero")

    current = measure(points, dimension)
    if abs(current - target_mm) <= tolerance:
        raise SketchError("unchanged", "the dimension already has that value")

    direction = axis(points, dimension)
    plane = boundary(points, dimension)
    delta = target_mm - current
    return [
        Point(point.x + delta * direction.x, point.y + delta * direction.y)
        if point.x * direction.x + point.y * direction.y >= plane - tolerance
        else point
        for point in points
    ]


def set_segment_length(
    points: Sequence[Point],
    index: int,
    length_mm: float,
    *,
    tolerance: float = TOLERANCE_MM,
) -> list[Point]:
    """Make one segment of the ring measure ``length_mm``.

    The width and height case of :func:`set_measure`, kept while the canvas still derives one
    dimension per segment; the dimension tool calls ``set_measure`` directly.
    """
    count = len(points)
    if not 0 <= index < count:
        raise SketchError("out_of_range", "segment index outside the contour")
    dimension = Dimension(
        id=0,
        first=Anchor(ANCHOR_VERTEX, index),
        second=Anchor(ANCHOR_VERTEX, (index + 1) % count),
        kind=SEGMENT_LENGTH,
    )
    return set_measure(points, dimension, length_mm, tolerance=tolerance)
