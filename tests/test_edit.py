"""Contour editing (spec S4): the shape operations a CAD offers on a closed ring."""

from __future__ import annotations

import pytest

from sectionlab.core.edit import chamfer, crosses_itself, mirror, offset, rectangle
from sectionlab.core.model import Contour, Point, signed_area
from sectionlab.core.sketch import SketchError


def _square(width: float = 100.0, height: float = 100.0) -> list[Point]:
    return [
        Point(0.0, 0.0),
        Point(width, 0.0),
        Point(width, height),
        Point(0.0, height),
    ]


def _area(points: list[Point]) -> float:
    return abs(signed_area(Contour(points=points, closed=True)))


# ------------------------------------------------------------------ chamfer (S4)


def test_a_chamfer_cuts_the_corner_of_a_square() -> None:
    points = chamfer(_square(), 0, 10.0)
    assert len(points) == 5
    # The corner loses one right triangle of legs 10.
    assert _area(points) == pytest.approx(10_000.0 - 50.0)


def test_a_chamfer_keeps_every_other_vertex_where_it_was() -> None:
    square = _square()
    points = chamfer(square, 1, 10.0)
    assert points[:1] == [square[0]]
    assert [point for point in square[2:] if point in points] == square[2:]


def test_a_chamfer_refuses_a_distance_that_eats_a_whole_side() -> None:
    with pytest.raises(SketchError) as error:
        chamfer(_square(), 0, 60.0)
    assert error.value.code == "chamfer_too_long"


def test_a_chamfer_of_zero_is_the_same_contour() -> None:
    assert chamfer(_square(), 0, 0.0) == _square()


# ------------------------------------------------------------------- offset (S4)


def test_an_inward_offset_makes_the_thickness_of_a_section() -> None:
    points = offset(_square(200.0, 100.0), 10.0, outward=False)
    assert _area(points) == pytest.approx(180.0 * 80.0)
    assert len(points) == 4


def test_an_outward_offset_grows_the_contour() -> None:
    points = offset(_square(200.0, 100.0), 10.0, outward=True)
    assert _area(points) == pytest.approx(220.0 * 120.0)


def test_an_offset_keeps_the_winding_direction() -> None:
    points = offset(_square(200.0, 100.0), 10.0, outward=False)
    assert signed_area(Contour(points=points, closed=True)) > 0


def test_an_offset_that_would_collapse_the_contour_is_refused() -> None:
    with pytest.raises(SketchError) as error:
        offset(_square(100.0, 10.0), 8.0, outward=False)
    assert error.value.code == "offset_collapsed"


def test_an_offset_wider_than_a_feature_is_refused() -> None:
    # A slab with a 10 mm tab: a 12 mm inward offset would turn the tab inside out.
    points = [
        Point(0.0, 0.0),
        Point(100.0, 0.0),
        Point(100.0, 50.0),
        Point(55.0, 50.0),
        Point(55.0, 55.0),
        Point(45.0, 55.0),
        Point(45.0, 50.0),
        Point(0.0, 50.0),
    ]
    with pytest.raises(SketchError) as error:
        offset(points, 12.0, outward=False)
    assert error.value.code == "offset_too_far"


def test_a_folded_contour_is_recognised_as_crossing_itself() -> None:
    bowtie = [Point(0.0, 0.0), Point(100.0, 100.0), Point(100.0, 0.0), Point(0.0, 100.0)]
    assert crosses_itself(bowtie) is True
    assert crosses_itself(_square()) is False


def test_an_offset_of_zero_is_the_same_contour() -> None:
    assert offset(_square(200.0, 100.0), 0.0, outward=False) == _square(200.0, 100.0)


# ------------------------------------------------------------------- mirror (S4)


def _triangle() -> list[Point]:
    return [Point(0.0, 0.0), Point(100.0, 0.0), Point(0.0, 50.0)]


def test_a_vertical_mirror_flips_the_drawing_left_to_right() -> None:
    points = mirror(_triangle(), "vertical")
    assert sorted((round(point.x, 6), round(point.y, 6)) for point in points) == [
        (0.0, 0.0),
        (100.0, 0.0),
        (100.0, 50.0),
    ]


def test_a_horizontal_mirror_flips_the_drawing_top_to_bottom() -> None:
    points = mirror(_triangle(), "horizontal")
    assert sorted((round(point.x, 6), round(point.y, 6)) for point in points) == [
        (0.0, 0.0),
        (0.0, 50.0),
        (100.0, 50.0),
    ]


def test_a_mirror_keeps_the_area_and_undoes_itself() -> None:
    original = _triangle()
    once = mirror(original, "vertical")
    assert _area(once) == pytest.approx(_area(original))
    twice = mirror(once, "vertical")
    assert sorted((round(p.x, 6), round(p.y, 6)) for p in twice) == sorted(
        (round(p.x, 6), round(p.y, 6)) for p in original
    )


def test_a_mirror_leaves_a_symmetric_contour_alone() -> None:
    square = _square(100.0, 50.0)
    points = mirror(square, "vertical")
    assert sorted((round(p.x, 6), round(p.y, 6)) for p in points) == sorted(
        (round(p.x, 6), round(p.y, 6)) for p in square
    )


def test_a_mirror_refuses_an_unknown_axis() -> None:
    with pytest.raises(SketchError) as error:
        mirror(_square(), "diagonal")
    assert error.value.code == "unknown_axis"


# ---------------------------------------------------------------- rectangle (S4)


def test_a_rectangle_is_made_from_two_opposite_corners() -> None:
    points = rectangle(Point(0.0, 0.0), Point(200.0, 100.0))
    assert len(points) == 4
    assert _area(points) == pytest.approx(20_000.0)


def test_a_rectangle_from_corners_in_any_order_is_the_same_rectangle() -> None:
    first = rectangle(Point(0.0, 0.0), Point(200.0, 100.0))
    second = rectangle(Point(200.0, 100.0), Point(0.0, 0.0))
    assert sorted((point.x, point.y) for point in first) == sorted(
        (point.x, point.y) for point in second
    )


def test_a_rectangle_needs_two_different_corners() -> None:
    with pytest.raises(SketchError) as error:
        rectangle(Point(10.0, 10.0), Point(10.0, 10.0))
    assert error.value.code == "degenerate_rectangle"
