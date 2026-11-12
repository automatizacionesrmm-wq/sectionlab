"""A dimension drives the geometry deterministically (spec S3)."""

from __future__ import annotations

import pytest

from sectionlab.core.model import Point
from sectionlab.core.sketch import SketchError, segment_length, set_measure, set_segment_length

RECTANGLE = [Point(0, 0), Point(120, 0), Point(120, 80), Point(0, 80)]


def test_a_width_dimension_widens_the_section_without_shearing_it() -> None:
    points = set_segment_length(RECTANGLE, 0, 150.0)
    assert points == [Point(0, 0), Point(150, 0), Point(150, 80), Point(0, 80)]
    assert segment_length(points, 0) == pytest.approx(150.0)
    # The left side stays vertical, so the section is still a rectangle.
    assert segment_length(points, 3) == pytest.approx(80.0)


def test_a_height_dimension_moves_the_side_it_closes() -> None:
    points = set_segment_length(RECTANGLE, 1, 50.0)
    assert points == [Point(0, 0), Point(120, 0), Point(120, 50), Point(0, 50)]
    assert segment_length(points, 1) == pytest.approx(50.0)


def test_editing_a_segment_that_runs_left_moves_its_own_side() -> None:
    points = set_segment_length(RECTANGLE, 2, 200.0)
    assert points == [Point(-80, 0), Point(120, 0), Point(120, 80), Point(-80, 80)]
    assert segment_length(points, 2) == pytest.approx(200.0)
    assert segment_length(points, 3) == pytest.approx(80.0)


def test_the_closing_segment_cannot_drive_the_geometry() -> None:
    with pytest.raises(SketchError) as refused:
        set_segment_length(RECTANGLE, 3, 10.0)
    assert refused.value.code == "closing_segment"


def test_a_slanted_segment_cannot_drive_the_geometry() -> None:
    triangle = [Point(0, 0), Point(10, 5), Point(0, 10)]
    with pytest.raises(SketchError) as refused:
        set_segment_length(triangle, 0, 20.0)
    assert refused.value.code == "slanted_segment"


@pytest.mark.parametrize("length", [0.0, -5.0])
def test_a_dimension_must_be_greater_than_zero(length: float) -> None:
    with pytest.raises(SketchError) as refused:
        set_segment_length(RECTANGLE, 0, length)
    assert refused.value.code == "non_positive"


def test_an_unchanged_dimension_is_refused() -> None:
    with pytest.raises(SketchError) as refused:
        set_segment_length(RECTANGLE, 0, 120.0)
    assert refused.value.code == "unchanged"


def test_an_index_outside_the_contour_is_refused() -> None:
    with pytest.raises(SketchError) as refused:
        set_segment_length(RECTANGLE, 9, 10.0)
    assert refused.value.code == "out_of_range"


def test_too_few_vertices_is_refused() -> None:
    with pytest.raises(SketchError) as refused:
        set_segment_length([Point(0, 0), Point(10, 0)], 0, 40.0)
    assert refused.value.code == "too_few_vertices"


def test_a_negative_direction_segment_grows_towards_its_own_direction() -> None:
    """The segment from (120,80) to (0,80) runs leftwards, so growing it moves its end left."""
    points = set_segment_length(RECTANGLE, 2, 200.0)
    assert points[3] == Point(-80, 80)
    assert segment_length(points, 2) == pytest.approx(200.0)


# --- one rule for every kind of dimension (specs S3-S5) ---------------------------------

from sectionlab.core.dimensions import (  # noqa: E402
    ANCHOR_EDGE,
    ANCHOR_VERTEX,
    HORIZONTAL,
    SEGMENT_LENGTH,
    VERTICAL,
    Anchor,
    Dimension,
)

ELL = [Point(0, 0), Point(40, 0), Point(40, 30), Point(25, 30), Point(25, 60), Point(0, 60)]


def driven(first: Anchor, second: Anchor, kind: str) -> Dimension:
    return Dimension(id=1, first=first, second=second, kind=kind, offset_mm=8.0)


def ring_segment(index: int, points=RECTANGLE) -> Dimension:
    return driven(
        Anchor(ANCHOR_VERTEX, index),
        Anchor(ANCHOR_VERTEX, (index + 1) % len(points)),
        SEGMENT_LENGTH,
    )


def test_a_segment_dimension_widens_the_section_without_shearing_it() -> None:
    points = set_measure(RECTANGLE, ring_segment(0), 150.0)
    assert points == [Point(0, 0), Point(150, 0), Point(150, 80), Point(0, 80)]
    assert segment_length(points, 0) == pytest.approx(150.0)
    assert segment_length(points, 3) == pytest.approx(80.0)


def test_a_segment_running_leftwards_moves_its_own_side() -> None:
    points = set_measure(RECTANGLE, ring_segment(2), 200.0)
    assert points == [Point(-80, 0), Point(120, 0), Point(120, 80), Point(-80, 80)]


def test_an_edge_anchored_dimension_drives_the_same_segment() -> None:
    dimension = driven(Anchor(ANCHOR_EDGE, 1, 0.0), Anchor(ANCHOR_EDGE, 1, 1.0), SEGMENT_LENGTH)
    assert set_measure(RECTANGLE, dimension, 50.0) == [
        Point(0, 0),
        Point(120, 0),
        Point(120, 50),
        Point(0, 50),
    ]


def test_a_horizontal_distance_between_two_free_vertices_moves_everything_past_it() -> None:
    dimension = driven(Anchor(ANCHOR_VERTEX, 0), Anchor(ANCHOR_VERTEX, 2), HORIZONTAL)
    points = set_measure(ELL, dimension, 50.0)
    assert points == [
        Point(0, 0),
        Point(50, 0),
        Point(50, 30),
        Point(25, 30),
        Point(25, 60),
        Point(0, 60),
    ]


def test_a_vertical_distance_between_two_free_vertices_moves_everything_past_it() -> None:
    dimension = driven(Anchor(ANCHOR_VERTEX, 0), Anchor(ANCHOR_VERTEX, 4), VERTICAL)
    points = set_measure(ELL, dimension, 70.0)
    assert points[4] == Point(25, 70)
    assert points[5] == Point(0, 70)
    assert points[1] == Point(40, 0)


def test_a_vertex_inside_the_boundary_plane_never_moves() -> None:
    dimension = driven(Anchor(ANCHOR_VERTEX, 0), Anchor(ANCHOR_VERTEX, 2), VERTICAL)
    points = set_measure(RECTANGLE, dimension, 60.0)
    assert points[0] == Point(0, 0)
    assert points[1] == Point(120, 0)


@pytest.mark.parametrize(
    ("dimension", "code"),
    [
        (ring_segment(3), "closing_segment"),
        (driven(Anchor(ANCHOR_VERTEX, 9), Anchor(ANCHOR_VERTEX, 1), SEGMENT_LENGTH), "out_of_range"),
        (driven(Anchor(ANCHOR_VERTEX, 0), Anchor(ANCHOR_VERTEX, 3), HORIZONTAL), "unchanged_anchors"),
    ],
)
def test_a_measure_that_single_rule_cannot_drive_is_refused(dimension, code: str) -> None:
    with pytest.raises(SketchError) as refused:
        set_measure(RECTANGLE, dimension, 10.0)
    assert refused.value.code == code


def test_a_slanted_segment_cannot_be_driven() -> None:
    triangle = [Point(0, 0), Point(30, 40), Point(0, 40)]
    with pytest.raises(SketchError) as refused:
        set_measure(triangle, ring_segment(0, triangle), 60.0)
    assert refused.value.code == "slanted_segment"


@pytest.mark.parametrize("target", [0.0, -5.0])
def test_a_driven_value_must_be_greater_than_zero(target: float) -> None:
    with pytest.raises(SketchError) as refused:
        set_measure(RECTANGLE, ring_segment(0), target)
    assert refused.value.code == "non_positive"


def test_an_unchanged_measure_is_refused() -> None:
    with pytest.raises(SketchError) as refused:
        set_measure(RECTANGLE, ring_segment(0), 120.0)
    assert refused.value.code == "unchanged"


def test_too_few_vertices_cannot_be_driven() -> None:
    pair = [Point(0, 0), Point(10, 0)]
    with pytest.raises(SketchError) as refused:
        set_measure(pair, ring_segment(0, pair), 40.0)
    assert refused.value.code == "too_few_vertices"


def test_a_refused_measure_leaves_the_geometry_untouched() -> None:
    points = list(RECTANGLE)
    with pytest.raises(SketchError):
        set_measure(points, ring_segment(3), 10.0)
    assert points == RECTANGLE
