"""Snapping rules for free-hand drawing (spec S8)."""

from __future__ import annotations

import math

import pytest

from sectionlab.core.model import Contour, Point
from sectionlab.core.snap import (
    GUIDE_X,
    GUIDE_Y,
    Alignment,
    Snap,
    SnapKind,
    alignments,
    apply_alignment,
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


def test_no_guide_when_nothing_is_within_the_tolerance() -> None:
    found = [Snap(Point(0, 0), SnapKind.ENDPOINT)]
    assert alignments(found, Point(30, 40), 5.0) == []


def test_empty_candidates_produce_no_guides() -> None:
    assert alignments([], Point(0, 0), 10.0) == []


def test_only_one_axis_can_align() -> None:
    found = [Snap(Point(10, 50), SnapKind.ENDPOINT)]
    guides = alignments(found, Point(12, 0), 5.0)
    assert len(guides) == 1
    assert guides[0].axis == GUIDE_X
    assert guides[0].coordinate == 10.0
    assert guides[0].source == Point(10, 50)
    assert guides[0].delta == 2.0


def test_the_vertical_axis_aligns_independently() -> None:
    found = [Snap(Point(50, 10), SnapKind.MIDPOINT)]
    guides = alignments(found, Point(0, 13), 5.0)
    assert len(guides) == 1
    assert guides[0].axis == GUIDE_Y
    assert guides[0].coordinate == 10.0
    assert guides[0].delta == 3.0


def test_both_axes_align_at_once() -> None:
    found = [
        Snap(Point(10, 0), SnapKind.ENDPOINT),
        Snap(Point(0, 20), SnapKind.ENDPOINT),
    ]
    guides = alignments(found, Point(11, 21), 5.0)
    by_axis = {guide.axis: guide for guide in guides}
    assert len(guides) == 2
    assert by_axis[GUIDE_X].coordinate == 10.0
    assert by_axis[GUIDE_Y].coordinate == 20.0
    assert by_axis[GUIDE_X].delta == 1.0
    assert by_axis[GUIDE_Y].delta == 1.0


def test_the_closest_candidate_wins_on_one_axis() -> None:
    found = [
        Snap(Point(0, 100), SnapKind.ENDPOINT),
        Snap(Point(4, 0), SnapKind.ENDPOINT),
        Snap(Point(9, 50), SnapKind.ENDPOINT),
    ]
    guides = alignments(found, Point(5, 40), 6.0)
    assert len(guides) == 1
    assert guides[0].coordinate == 4.0


def test_a_distance_tie_prefers_the_nearest_candidate() -> None:
    found = [
        Snap(Point(7, 300), SnapKind.ENDPOINT),
        Snap(Point(7, 20), SnapKind.MIDPOINT),
    ]
    guides = alignments(found, Point(5, 5), 2.0)
    assert len(guides) == 1
    assert guides[0].source == Point(7, 20)


def test_a_full_tie_uses_the_snap_priority() -> None:
    found = [
        Snap(Point(7, 500), SnapKind.MIDPOINT),
        Snap(Point(3, 500), SnapKind.ENDPOINT),
    ]
    guides = alignments(found, Point(5, 5), 3.0)
    assert len(guides) == 1
    assert guides[0].axis == GUIDE_X
    assert guides[0].coordinate == 3.0


def test_the_guide_does_not_depend_on_the_candidate_order() -> None:
    found = [
        Snap(Point(7, 500), SnapKind.MIDPOINT),
        Snap(Point(3, 500), SnapKind.ENDPOINT),
    ]
    first = alignments(found, Point(5, 5), 3.0)
    reversed_order = alignments(list(reversed(found)), Point(5, 5), 3.0)
    assert first == reversed_order


def test_the_same_coordinate_never_produces_two_guides() -> None:
    shared = 50.0
    found = [
        Snap(Point(shared, 0), SnapKind.ENDPOINT),
        Snap(Point(shared, 100), SnapKind.MIDPOINT),
        Snap(Point(shared, 50), SnapKind.CENTER),
    ]
    guides = alignments(found, Point(shared, 30), 5.0)
    assert len(guides) == 1
    assert guides[0].source == Point(shared, 50)


def test_a_zero_tolerance_aligns_only_exactly() -> None:
    found = [Snap(Point(10, 10), SnapKind.ENDPOINT)]
    exact = alignments(found, Point(10, 0), 0.0)
    assert len(exact) == 1
    assert exact[0].axis == GUIDE_X
    assert alignments(found, Point(10.5, 0), 0.0) == []


def test_candidates_from_the_drawing_produce_guides() -> None:
    guides = alignments(candidates([square()]), Point(51, 27), 2.0)
    assert len(guides) == 1
    assert guides[0].axis == GUIDE_X
    assert guides[0].coordinate == 50.0


def test_apply_alignment_moves_only_the_aligned_coordinate() -> None:
    guides = [Alignment(axis=GUIDE_X, coordinate=10.0, source=Point(10, 90), delta=1.0)]
    locked = apply_alignment(Point(11, 40), guides)
    assert locked == Point(10, 40)
    assert locked.y == 40.0


def test_apply_alignment_moves_the_horizontal_coordinate() -> None:
    guides = [Alignment(axis=GUIDE_Y, coordinate=20.0, source=Point(90, 20), delta=1.0)]
    assert apply_alignment(Point(40, 21), guides) == Point(40, 20)


def test_apply_alignment_without_guides_returns_the_same_point() -> None:
    target = Point(12.5, -3.25)
    assert apply_alignment(target, []) == target


def test_apply_alignment_locks_both_axes_exactly() -> None:
    found = [
        Snap(Point(10, 0), SnapKind.ENDPOINT),
        Snap(Point(0, 20), SnapKind.ENDPOINT),
    ]
    target = Point(11.25, 21.75)
    locked = apply_alignment(target, alignments(found, target, 5.0))
    assert locked == Point(10, 20)
    assert locked.x == 10.0
    assert locked.y == 20.0


def test_guides_leave_the_candidates_and_the_target_untouched() -> None:
    found = [
        Snap(Point(0, 0), SnapKind.ENDPOINT),
        Snap(Point(50, 50), SnapKind.MIDPOINT),
    ]
    before_candidates = list(found)
    before_points = [(candidate.point.x, candidate.point.y) for candidate in found]
    target = Point(1, 51)
    guides = alignments(found, target, 3.0)
    apply_alignment(target, guides)
    assert found == before_candidates
    assert [(candidate.point.x, candidate.point.y) for candidate in found] == before_points
    assert target == Point(1, 51)


def test_a_guide_meets_the_cursor_where_it_crosses_it() -> None:
    vertical = Alignment(axis=GUIDE_X, coordinate=10.0, source=Point(10, 90), delta=1.0)
    horizontal = Alignment(axis=GUIDE_Y, coordinate=20.0, source=Point(90, 20), delta=1.0)
    cursor = Point(11, 21)
    assert vertical.line_end(cursor) == Point(10, 21)
    assert horizontal.line_end(cursor) == Point(11, 20)



def test_identical_candidates_still_pick_deterministically() -> None:
    found = [
        Snap(Point(7, 500), SnapKind.ENDPOINT),
        Snap(Point(3, 500), SnapKind.ENDPOINT),
    ]
    first = alignments(found, Point(5, 5), 3.0)
    reversed_order = alignments(list(reversed(found)), Point(5, 5), 3.0)
    assert first == reversed_order
