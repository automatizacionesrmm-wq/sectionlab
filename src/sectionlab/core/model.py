"""Section geometry model.

A section is one outer contour plus an optional inner contour (hollow templates), always in
millimetres, with the axis convention of spec S9: x to the right, y upward, origin free.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Point:
    """A vertex in millimetres."""

    x: float
    y: float


@dataclass
class Contour:
    """An ordered ring of vertices.

    ``closed`` is False when the drawn path never returned to its first vertex; the closing
    edge is implicit, so it is never stored as a duplicated final point.
    """

    points: list[Point]
    closed: bool = True


@dataclass(frozen=True)
class TemplateSpec:
    """Which parametric template produced a section, with the parameters used."""

    kind: str
    params: dict[str, float] = field(default_factory=dict)


@dataclass
class Section:
    """A single cross-section: one outer contour and an optional inner one."""

    outer: Contour
    inner: Contour | None = None
    template: TemplateSpec | None = None


def signed_area(contour: Contour) -> float:
    """Shoelace area of the vertex ring; the sign encodes the winding direction.

    The point list is always treated as a ring, even for an open path, because winding only
    matters once the contour is closed.
    """
    points = contour.points
    if len(points) < 3:
        return 0.0
    total = 0.0
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        total += current.x * following.y - following.x * current.y
    return total / 2.0


def normalize_ccw(contour: Contour) -> Contour:
    """Return the contour wound counter-clockwise (decision D3); clockwise input is accepted."""
    if signed_area(contour) < 0.0:
        return Contour(points=list(reversed(contour.points)), closed=contour.closed)
    return Contour(points=list(contour.points), closed=contour.closed)
