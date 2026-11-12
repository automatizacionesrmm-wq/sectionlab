"""Dimensions as user-placed annotations (specs S3, S4, S5, S7, S10).

The value of a dimension is never stored: it is measured from the geometry every time, so the
number on screen and the drawing cannot disagree. What is stored is what the dimension refers
to (two anchors), which kind of measure it is, and how far from the measured entity its line
sits. Everything here is millimetres and free of Qt so the rules are testable without a screen.
"""

from __future__ import annotations

import pytest

from sectionlab.core.dimensions import (
    ANCHOR_EDGE,
    ANCHOR_VERTEX,
    HORIZONTAL,
    SEGMENT_LENGTH,
    VERTICAL,
    Anchor,
    Dimension,
    axis,
    boundary,
    is_editable,
    measure,
    normal,
    remap,
)
from sectionlab.core.model import Point

RECTANGLE = [Point(0, 0), Point(120, 0), Point(120, 80), Point(0, 80)]
# An L profile: five edges, so anchors can sit on non-consecutive vertices.
ELL = [Point(0, 0), Point(40, 0), Point(40, 30), Point(25, 30), Point(25, 60), Point(0, 60)]


def segment_dimension(index: int, kind: str = SEGMENT_LENGTH, identifier: int = 1) -> Dimension:
    """A dimension whose anchors are the two endpoints of one ring segment."""
    return Dimension(
        id=identifier,
        first=Anchor(ANCHOR_VERTEX, index),
        second=Anchor(ANCHOR_VERTEX, (index + 1) % len(RECTANGLE)),
        kind=kind,
        offset_mm=10.0,
    )


def between(first: int, second: int, kind: str) -> Dimension:
    return Dimension(
        id=7,
        first=Anchor(ANCHOR_VERTEX, first),
        second=Anchor(ANCHOR_VERTEX, second),
        kind=kind,
        offset_mm=4.0,
    )


# --- anchors ---------------------------------------------------------------------------


def test_a_vertex_anchor_is_that_vertex() -> None:
    assert Anchor(ANCHOR_VERTEX, 2).point(RECTANGLE) == Point(120, 80)


def test_an_edge_anchor_walks_its_segment() -> None:
    assert Anchor(ANCHOR_EDGE, 0, 0.5).point(RECTANGLE) == Point(60, 0)
    assert Anchor(ANCHOR_EDGE, 0, 0.25).point(RECTANGLE) == Point(30, 0)


def test_the_closing_edge_anchor_wraps_to_the_first_vertex() -> None:
    assert Anchor(ANCHOR_EDGE, 3, 0.5).point(RECTANGLE) == Point(0, 40)


def test_an_anchor_outside_the_ring_is_refused() -> None:
    dimension = between(0, 9, HORIZONTAL)
    assert is_editable(RECTANGLE, dimension) == (False, "out_of_range")


# --- measure ---------------------------------------------------------------------------


def test_a_segment_dimension_measures_its_euclidean_length() -> None:
    triangle = [Point(0, 0), Point(30, 40), Point(0, 40)]
    slanted = Dimension(1, Anchor(ANCHOR_VERTEX, 0), Anchor(ANCHOR_VERTEX, 1), SEGMENT_LENGTH, 5.0)
    assert measure(triangle, slanted) == pytest.approx(50.0)


def test_a_horizontal_dimension_measures_the_projection_on_x() -> None:
    dimension = between(0, 2, HORIZONTAL)
    assert measure(RECTANGLE, dimension) == pytest.approx(120.0)


def test_a_vertical_dimension_measures_the_projection_on_y() -> None:
    dimension = between(0, 2, VERTICAL)
    assert measure(RECTANGLE, dimension) == pytest.approx(80.0)


def test_any_two_vertices_can_be_measured_not_only_consecutive_ones() -> None:
    dimension = between(0, 3, VERTICAL)
    assert measure(ELL, dimension) == pytest.approx(30.0)
    assert measure(ELL, between(1, 4, HORIZONTAL)) == pytest.approx(15.0)


def test_the_measure_ignores_the_direction_the_anchors_were_picked_in() -> None:
    assert measure(RECTANGLE, between(2, 0, HORIZONTAL)) == pytest.approx(120.0)
    assert measure(RECTANGLE, between(2, 0, VERTICAL)) == pytest.approx(80.0)


# --- axis and boundary -----------------------------------------------------------------


def test_the_axis_of_an_axis_aligned_segment_has_no_rounding_noise() -> None:
    assert axis(RECTANGLE, segment_dimension(0)) == Point(1.0, 0.0)
    assert axis(RECTANGLE, segment_dimension(1)) == Point(0.0, 1.0)


def test_the_axis_of_a_segment_running_leftwards_points_left() -> None:
    assert axis(RECTANGLE, segment_dimension(2)) == Point(-1.0, 0.0)


def test_the_boundary_plane_passes_through_the_second_anchor() -> None:
    assert boundary(RECTANGLE, segment_dimension(0)) == pytest.approx(120.0)
    assert boundary(RECTANGLE, between(0, 3, VERTICAL)) == pytest.approx(80.0)


def test_the_boundary_of_a_segment_running_leftwards_is_the_left_anchor() -> None:
    """Segment 2 runs from (120, 80) to (0, 80), so the plane sits at x = 0."""
    assert boundary(RECTANGLE, segment_dimension(2)) == pytest.approx(0.0)


# --- normal ----------------------------------------------------------------------------


def test_the_normal_points_away_from_the_middle_of_the_section() -> None:
    assert normal(RECTANGLE, segment_dimension(0)) == Point(0.0, -1.0)
    assert normal(RECTANGLE, segment_dimension(1)) == Point(1.0, 0.0)
    assert normal(RECTANGLE, segment_dimension(2)) == Point(0.0, 1.0)


# --- editability -----------------------------------------------------------------------


def test_an_axis_aligned_segment_can_drive_the_geometry() -> None:
    assert is_editable(RECTANGLE, segment_dimension(0)) == (True, "")


def test_the_closing_segment_is_reference_only() -> None:
    assert is_editable(RECTANGLE, segment_dimension(3)) == (False, "closing_segment")


def test_a_slanted_segment_is_reference_only() -> None:
    triangle = [Point(0, 0), Point(30, 40), Point(0, 40)]
    slanted = Dimension(1, Anchor(ANCHOR_VERTEX, 0), Anchor(ANCHOR_VERTEX, 1), SEGMENT_LENGTH, 5.0)
    assert is_editable(triangle, slanted) == (False, "slanted_segment")


def test_a_projection_between_two_points_at_the_same_x_is_reference_only() -> None:
    assert is_editable(RECTANGLE, between(0, 3, HORIZONTAL)) == (False, "unchanged_anchors")


def test_a_projection_between_the_same_vertex_is_reference_only() -> None:
    assert is_editable(RECTANGLE, between(1, 1, VERTICAL)) == (False, "unchanged_anchors")


# --- remapping -------------------------------------------------------------------------


def test_inserting_a_vertex_before_an_anchor_pushes_it_forward() -> None:
    moved = remap(segment_dimension(1), inserted=0)
    assert moved is not None
    assert (moved.first.index, moved.second.index) == (2, 3)


def test_inserting_a_vertex_after_an_anchor_leaves_it_alone() -> None:
    moved = remap(segment_dimension(0), inserted=3)
    assert moved is not None
    assert (moved.first.index, moved.second.index) == (0, 1)


def test_inserting_into_the_middle_of_a_measured_edge_keeps_the_anchor_on_it() -> None:
    anchored = Dimension(1, Anchor(ANCHOR_EDGE, 0, 0.25), Anchor(ANCHOR_EDGE, 0, 0.75), SEGMENT_LENGTH, 3.0)
    moved = remap(anchored, inserted=1)
    assert moved is not None
    assert moved.first == Anchor(ANCHOR_EDGE, 0, 0.5)
    assert moved.second == Anchor(ANCHOR_EDGE, 1, 0.5)


def test_deleting_the_anchored_vertex_removes_the_dimension() -> None:
    assert remap(segment_dimension(0), deleted=0) is None


def test_deleting_an_edge_anchor_segment_removes_the_dimension() -> None:
    anchored = Dimension(1, Anchor(ANCHOR_EDGE, 2, 0.5), Anchor(ANCHOR_EDGE, 2, 1.0), SEGMENT_LENGTH, 3.0)
    assert remap(anchored, deleted=2) is None


def test_deleting_a_vertex_behind_an_anchor_pulls_it_back() -> None:
    moved = remap(segment_dimension(2), deleted=0)
    assert moved is not None
    assert (moved.first.index, moved.second.index) == (1, 2)


def test_reversing_the_ring_mirrors_vertex_anchors() -> None:
    moved = remap(segment_dimension(0), reversed_ring=4)
    assert moved is not None
    assert moved.first == Anchor(ANCHOR_VERTEX, 3)
    assert moved.second == Anchor(ANCHOR_VERTEX, 2)


def test_reversing_the_ring_mirrors_edge_anchors_and_their_parameter() -> None:
    anchored = Dimension(1, Anchor(ANCHOR_EDGE, 0, 0.25), Anchor(ANCHOR_EDGE, 0, 0.75), SEGMENT_LENGTH, 3.0)
    moved = remap(anchored, reversed_ring=4)
    assert moved is not None
    assert moved.first == Anchor(ANCHOR_EDGE, 2, 0.75)
    assert moved.second == Anchor(ANCHOR_EDGE, 2, 0.25)


def test_reversing_the_ring_keeps_the_closing_edge_closing() -> None:
    moved = remap(segment_dimension(3), reversed_ring=4)
    assert moved is not None
    assert (moved.first.index, moved.second.index) == (0, 3)
