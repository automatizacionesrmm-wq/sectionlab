"""One dimension per segment, placed outside the contour (specs S2-S3)."""

from __future__ import annotations

import pytest

from sectionlab.core.model import Point
from sectionlab.ui.dimensions import HEIGHT, LENGTH, WIDTH, dimensions_for

RECTANGLE = [Point(0, 0), Point(120, 0), Point(120, 80), Point(0, 80)]


def test_every_segment_of_a_rectangle_gets_its_own_dimension() -> None:
    dimensions = dimensions_for(RECTANGLE)
    assert [dimension.index for dimension in dimensions] == [0, 1, 2, 3]
    assert [dimension.kind for dimension in dimensions] == [WIDTH, HEIGHT, WIDTH, HEIGHT]
    assert [dimension.value for dimension in dimensions] == [120.0, 80.0, 120.0, 80.0]


def test_the_closing_segment_is_measured_but_cannot_be_edited() -> None:
    dimensions = dimensions_for(RECTANGLE)
    assert dimensions[3].closing
    assert not dimensions[3].editable
    assert all(dimension.editable for dimension in dimensions[:3])


def test_a_slanted_segment_is_measured_along_its_length() -> None:
    triangle = [Point(0, 0), Point(30, 40), Point(0, 40)]
    diagonal = dimensions_for(triangle)[0]
    assert diagonal.kind == LENGTH
    assert diagonal.value == pytest.approx(50.0)
    assert not diagonal.editable


def test_the_normal_points_away_from_the_section() -> None:
    dimensions = dimensions_for(RECTANGLE)
    outward = {(0, -1.0), (1.0, 0.0), (0, 1.0), (-1.0, 0.0)}
    asserted = set()
    for dimension in dimensions:
        assert (round(dimension.normal.x, 6), round(dimension.normal.y, 6)) in {
            (float(x), float(y)) for x, y in outward
        }
        asserted.add(dimension.index)
    assert asserted == {0, 1, 2, 3}
    # The bottom edge points down, the right edge points right.
    assert dimensions[0].normal.y == pytest.approx(-1.0)
    assert dimensions[1].normal.x == pytest.approx(1.0)


def test_an_open_path_does_not_measure_a_closing_edge() -> None:
    points = [Point(0, 0), Point(10, 0), Point(10, 5)]
    dimensions = dimensions_for(points, closed=False)
    assert len(dimensions) == 2
    assert all(not dimension.closing for dimension in dimensions)


def test_a_degenerate_segment_is_skipped() -> None:
    points = [Point(0, 0), Point(0, 0), Point(10, 0), Point(10, 10)]
    dimensions = dimensions_for(points)
    assert [dimension.index for dimension in dimensions] == [1, 2, 3]


def test_a_single_point_has_no_dimensions() -> None:
    assert dimensions_for([Point(0, 0)]) == []
