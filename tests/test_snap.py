"""Snapping rules for free-hand drawing (spec S8)."""

from __future__ import annotations

import math

import pytest

from sectionlab.core.model import Contour, Point
from sectionlab.core.snap import (
    Snap,
    SnapKind,
    apply_ortho,
    candidates,
    contour_center,
    edges,
    find_snap,
    midpoint,
    perpendicular_foot,
    segment_intersection,
)


def square(size: float = 100.0) -> Contour:
    return Contour(
        points=[
            Point(0, 0),
            Point(size, 0),
            Point(size, size),
            Point(0, size),
        ]
    )


def test_closed_contour_edges_include_the_closing_segment() -> None:
    assert len(edges(square())) == 4


def test_open_contour_edges_stop_at_the_last_vertex() -> None:
    open_contour = Contour(
        points=[Point(0, 0), Point(10, 0), Point(10, 10)], closed=False
    )
    assert len(edges(open_contour)) == 2


def test_midpoint_is_the_average_of_the_edge() -> None:
    assert midpoint(Point(0, 0), Point(10, 4)) == Point(5, 2)


def test_center_is_the_bounding_box_center() -> None:
    center = contour_center(square())
    assert (center.x, center.y) == (50.0, 50.0)


def test_crossing_segments_report_their_intersection() -> None:
    crossing = segment_intersection(
        (Point(0, 0), Point(10, 10)), (Point(0, 10), Point(10, 0))
    )
    assert crossing == Point(5, 5)


def test_parallel_segments_do_not_intersect() -> None:
    assert segment_intersection((Point(0, 0), Point(10, 0)), (Point(0, 5), Point(10, 5))) is None


def test_far_segments_do_not_intersect() -> None:
    assert segment_intersection((Point(0, 0), Point(1, 0)), (Point(5, -1), Point(5, 1))) is None


def test_perpendicular_foot_lands_on_the_segment() -> None:
    foot = perpendicular_foot(Point(5, 5), (Point(0, 0), Point(10, 0)))
    assert foot == Point(5, 0)


def test_perpendicular_foot_outside_the_segment_is_ignored() -> None:
    assert perpendicular_foot(Point(50, 5), (Point(0, 0), Point(10, 0))) is None


def test_candidates_include_vertices_midpoints_and_the_center() -> None:
    found = candidates([square()])
    kinds = {candidate.kind for candidate in found}
    assert SnapKind.ENDPOINT in kinds
    assert SnapKind.MIDPOINT in kinds
    assert SnapKind.CENTER in kinds
    assert len([c for c in found if c.kind is SnapKind.ENDPOINT]) == 4


def test_two_crossing_squares_produce_intersection_candidates() -> None:
    first = square(100)
    second = Contour(
        points=[Point(50, -25), Point(150, -25), Point(150, 75), Point(50, 75)]
    )
    found = candidates([first, second])
    assert any(candidate.kind is SnapKind.INTERSECTION for candidate in found)


def test_perpendicular_candidates_are_generated_from_anchors() -> None:
    found = candidates([square()], anchors=[Point(50, 150)])
    feet = [candidate for candidate in found if candidate.kind is SnapKind.PERPENDICULAR]
    assert Point(50, 100) in [candidate.point for candidate in feet]


def test_nearest_candidate_wins() -> None:
    found = [Snap(Point(0, 0), SnapKind.ENDPOINT), Snap(Point(10, 0), SnapKind.ENDPOINT)]
    assert find_snap(Point(1, 0), found, 5.0) == Snap(Point(0, 0), SnapKind.ENDPOINT, 1.0)


def test_candidates_beyond_the_tolerance_are_ignored() -> None:
    found = [Snap(Point(0, 0), SnapKind.ENDPOINT)]
    assert find_snap(Point(50, 0), found, 1.0) is None


def test_endpoints_win_a_distance_tie() -> None:
    tie = [
        Snap(Point(0, 0), SnapKind.PERPENDICULAR),
        Snap(Point(0, 0), SnapKind.ENDPOINT),
    ]
    snapped = find_snap(Point(0, 0), tie, 1.0)
    assert snapped is not None
    assert snapped.kind is SnapKind.ENDPOINT


def test_empty_candidates_snap_nowhere() -> None:
    assert find_snap(Point(0, 0), [], 1.0) is None


def test_ortho_locks_the_dominant_axis() -> None:
    origin = Point(0, 0)
    assert apply_ortho(origin, Point(10, 1)) == Point(10, 0)
    assert apply_ortho(origin, Point(1, 10)) == Point(0, 10)


def test_ortho_keeps_the_farther_axis_on_a_tie() -> None:
    assert apply_ortho(Point(0, 0), Point(5, 5)) == Point(5, 0)


def test_snap_distance_is_euclidean() -> None:
    snapped = find_snap(Point(3, 4), [Snap(Point(0, 0), SnapKind.CENTER)], 10.0)
    assert snapped is not None
    assert math.isclose(snapped.distance, 5.0)
