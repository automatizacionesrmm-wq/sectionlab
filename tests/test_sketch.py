"""A dimension drives the geometry deterministically (spec S3)."""

from __future__ import annotations

import pytest

from sectionlab.core.model import Point
from sectionlab.core.sketch import SketchError, segment_length, set_segment_length

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
