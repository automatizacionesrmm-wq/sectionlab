"""Contour editing (spec S4): the shape operations a CAD offers on a closed ring.

Every function is pure: it takes the ring's points and returns the new ones, or raises
`SketchError` with a code the interface translates. None of them mutate the caller's list, so
the canvas can keep an undo snapshot on both sides of the call.
"""

from __future__ import annotations

import math
from typing import Literal, Sequence

from sectionlab.core.model import Contour, Point, normalize_ccw, signed_area
from sectionlab.core.sketch import SketchError

Axis = Literal["vertical", "horizontal"]

EPSILON = 1e-9
_DEGENERATE_AREA = 1e-6


def _distance(first: Point, second: Point) -> float:
    return math.hypot(second.x - first.x, second.y - first.y)


def _unit(first: Point, second: Point) -> tuple[float, float]:
    length = _distance(first, second)
    if length <= EPSILON:
        return (0.0, 0.0)
    return ((second.x - first.x) / length, (second.y - first.y) / length)


def _line_intersection(
    point: Point, direction: tuple[float, float], other: Point, other_direction: tuple[float, float]
) -> Point:
    """Where two infinite lines meet."""
    cross = direction[0] * other_direction[1] - direction[1] * other_direction[0]
    delta = (other.x - point.x, other.y - point.y)
    factor = (delta[0] * other_direction[1] - delta[1] * other_direction[0]) / cross
    return Point(point.x + direction[0] * factor, point.y + direction[1] * factor)


def _segments_cross(first: tuple[Point, Point], second: tuple[Point, Point]) -> bool:
    """True when two segments cross each other, touching aside."""
    (a, b), (c, d) = first, second

    def orientation(start: Point, end: Point, point: Point) -> float:
        return (end.x - start.x) * (point.y - start.y) - (end.y - start.y) * (point.x - start.x)

    one = orientation(a, b, c)
    two = orientation(a, b, d)
    three = orientation(c, d, a)
    four = orientation(c, d, b)
    return one * two < -EPSILON and three * four < -EPSILON


def crosses_itself(points: Sequence[Point]) -> bool:
    """True when two non-adjacent segments of the ring cross each other."""
    count = len(points)
    if count < 4:
        return False
    edges = [(points[index], points[(index + 1) % count]) for index in range(count)]
    for first in range(count):
        for second in range(first + 2, count):
            if first == 0 and second == count - 1:
                continue  # neighbours through the closing edge
            if _segments_cross(edges[first], edges[second]):
                return True
    return False


def _ring(points: Sequence[Point]) -> list[Point]:
    ring = list(points)
    if len(ring) < 3:
        raise SketchError("too_few_vertices", "A contour needs at least three vertices")
    return ring


def _inverted_turns(ring: Sequence[Point], result: Sequence[Point]) -> list[int]:
    """Indices whose turn flipped outward-in or inward-out, which means a feature inverted.

    A miter offset keeps every convex corner convex and every reflex one reflex. When it does
    not, the distance is wider than that feature and the result would be a shape nobody drew.
    """
    if len(ring) != len(result):
        return []

    def turn(previous: Point, corner: Point, following: Point) -> float:
        return (corner.x - previous.x) * (following.y - corner.y) - (
            corner.y - previous.y
        ) * (following.x - corner.x)

    def sign(value: float) -> int:
        if abs(value) <= EPSILON:
            return 0
        return 1 if value > 0.0 else -1

    flipped: list[int] = []
    count = len(ring)
    for index in range(count):
        before = sign(turn(ring[index - 1], ring[index], ring[(index + 1) % count]))
        after = sign(
            turn(result[index - 1], result[index], result[(index + 1) % count])
        )
        if before != 0 and after != 0 and before != after:
            flipped.append(index)
    return flipped


def chamfer(points: Sequence[Point], index: int, distance: float) -> list[Point]:
    """Replace one vertex with two, `distance` along each of its sides (spec S4).

    The cut never reaches the middle of a side, so two chamfers on the same side can meet but
    cannot overlap.
    """
    ring = _ring(points)
    if distance <= EPSILON:
        return ring
    count = len(ring)
    corner = ring[index % count]
    previous = ring[(index - 1) % count]
    following = ring[(index + 1) % count]
    shortest = min(_distance(corner, previous), _distance(corner, following))
    if distance * 2.0 > shortest + EPSILON:
        raise SketchError(
            "chamfer_too_long", "The chamfer would eat more than half of a side"
        )
    to_previous = _unit(corner, previous)
    to_following = _unit(corner, following)
    start = Point(corner.x + to_previous[0] * distance, corner.y + to_previous[1] * distance)
    end = Point(
        corner.x + to_following[0] * distance, corner.y + to_following[1] * distance
    )
    position = index % count
    return ring[:position] + [start, end] + ring[position + 1 :]


def offset(points: Sequence[Point], distance: float, *, outward: bool) -> list[Point]:
    """A contour parallel to this one, `distance` away (spec S4).

    Offsetting inward is how a hollow section gets its thickness. The result is refused instead
    of returned when it would fold on itself, because broken geometry is worse than a message.
    """
    if distance <= EPSILON:
        return list(points)
    ring = normalize_ccw(Contour(points=_ring(points), closed=True)).points
    count = len(ring)
    sign = 1.0 if outward else -1.0
    shifted: list[tuple[Point, tuple[float, float]]] = []
    for index in range(count):
        start = ring[index]
        end = ring[(index + 1) % count]
        direction = _unit(start, end)
        # For a counter-clockwise ring the outward normal is the direction turned clockwise.
        normal = (direction[1] * sign, -direction[0] * sign)
        shifted.append(
            (
                Point(start.x + normal[0] * distance, start.y + normal[1] * distance),
                direction,
            )
        )

    result: list[Point] = []
    for index in range(count):
        previous_line = shifted[index - 1]
        current_line = shifted[index]
        cross = (
            previous_line[1][0] * current_line[1][1]
            - previous_line[1][1] * current_line[1][0]
        )
        if abs(cross) <= EPSILON:
            # Two collinear sides share one offset vertex, not two touching ones.
            result.append(current_line[0])
            continue
        result.append(
            _line_intersection(
                previous_line[0], previous_line[1], current_line[0], current_line[1]
            )
        )

    before = signed_area(Contour(points=ring, closed=True))
    after = signed_area(Contour(points=result, closed=True))
    if after * before <= 0.0 or abs(after) <= _DEGENERATE_AREA:
        raise SketchError(
            "offset_collapsed", "The offset would collapse the contour"
        )
    if crosses_itself(result):
        raise SketchError(
            "offset_crosses_itself", "The offset would fold the contour on itself"
        )
    inverted = _inverted_turns(ring, result)
    if inverted:
        raise SketchError(
            "offset_too_far",
            "The offset is wider than a feature of the contour: part of it would turn inside out",
        )
    return result


def mirror(points: Sequence[Point], axis: Axis) -> list[Point]:
    """Reflect the contour about the vertical or horizontal line through its centre (spec S4).

    The axis is the centre of the bounding box, so a mirror keeps the section where it is; the
    winding is reversed with the reflection so the contour keeps its orientation.
    """
    ring = _ring(points)
    if axis not in ("vertical", "horizontal"):
        raise SketchError("unknown_axis", "The mirror axis must be vertical or horizontal")
    xs = [point.x for point in ring]
    ys = [point.y for point in ring]
    centre_x = (min(xs) + max(xs)) / 2.0
    centre_y = (min(ys) + max(ys)) / 2.0
    if axis == "vertical":
        flipped = [Point(2.0 * centre_x - point.x, point.y) for point in ring]
    else:
        flipped = [Point(point.x, 2.0 * centre_y - point.y) for point in ring]
    return flipped[::-1]


def rectangle(first: Point, second: Point) -> list[Point]:
    """The four corners of the rectangle that has `first` and `second` as opposite corners."""
    left, right = sorted((float(first.x), float(second.x)))
    bottom, top = sorted((float(first.y), float(second.y)))
    if right - left <= EPSILON or top - bottom <= EPSILON:
        raise SketchError(
            "degenerate_rectangle", "A rectangle needs two different corners"
        )
    return [
        Point(left, bottom),
        Point(right, bottom),
        Point(right, top),
        Point(left, top),
    ]
