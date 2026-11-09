"""Where one dimension per segment goes (specs S2-S3), in millimetres and without Qt.

The canvas only translates these anchors into pixels: keeping the arithmetic here means the
placement rules — which segments get a width, a height or a length, on which side of the
contour, and which one can drive the geometry — are tested without a screen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sectionlab.core.model import Point

WIDTH = "width"
HEIGHT = "height"
LENGTH = "length"

TOLERANCE_MM = 1e-9


@dataclass(frozen=True)
class Dimension:
    """One segment's measurement and the side it is written on."""

    index: int
    kind: str
    value: float
    start: Point
    end: Point
    normal: Point
    editable: bool
    closing: bool = False

    @property
    def midpoint(self) -> Point:
        return Point((self.start.x + self.end.x) / 2, (self.start.y + self.end.y) / 2)


def _centre(points: Sequence[Point]) -> Point:
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    return Point((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def _outward(start: Point, end: Point, centre: Point, tolerance: float) -> Point:
    """Unit normal of the segment, pointing away from the middle of the section."""
    dx = end.x - start.x
    dy = end.y - start.y
    length = (dx * dx + dy * dy) ** 0.5
    if length <= tolerance:
        return Point(0.0, 1.0)
    normal = Point(dy / length, -dx / length)
    midpoint = Point((start.x + end.x) / 2, (start.y + end.y) / 2)
    outward = (midpoint.x - centre.x) * normal.x + (midpoint.y - centre.y) * normal.y
    if outward < 0:
        return Point(-normal.x, -normal.y)
    return normal


def dimensions_for(
    points: Sequence[Point],
    *,
    closed: bool = True,
    tolerance: float = TOLERANCE_MM,
) -> list[Dimension]:
    """One dimension per segment, in ring order, skipping degenerate segments.

    The last segment of a closed ring is the closing edge: it is measured but never editable,
    because its length is whatever the other segments leave.
    """
    count = len(points)
    if count < 2:
        return []
    segments = count if closed else count - 1
    centre = _centre(points)
    result: list[Dimension] = []
    for index in range(segments):
        start = points[index]
        end = points[(index + 1) % count]
        dx = end.x - start.x
        dy = end.y - start.y
        if abs(dx) <= tolerance and abs(dy) <= tolerance:
            continue
        if abs(dy) <= tolerance:
            kind = WIDTH
            value = abs(dx)
        elif abs(dx) <= tolerance:
            kind = HEIGHT
            value = abs(dy)
        else:
            kind = LENGTH
            value = (dx * dx + dy * dy) ** 0.5
        closing = closed and index == count - 1
        result.append(
            Dimension(
                index=index,
                kind=kind,
                value=value,
                start=start,
                end=end,
                normal=_outward(start, end, centre, tolerance),
                editable=kind != LENGTH and not closing,
                closing=closing,
            )
        )
    return result
