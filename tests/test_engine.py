"""Calculation engine results against closed-form values (specs S11, S13)."""

from __future__ import annotations

import math

import pytest

from sectionlab.core.engine import InvalidSectionError, SectionProperties, calculate
from sectionlab.core.model import Contour, Point, Section


def rectangle(width: float = 100.0, height: float = 200.0) -> Section:
    return Section(
        outer=Contour(
            points=[
                Point(0, 0),
                Point(width, 0),
                Point(width, height),
                Point(0, height),
            ],
        )
    )


def hollow_rectangle(width: float = 100.0, height: float = 200.0, wall: float = 6.0) -> Section:
    return Section(
        outer=rectangle(width, height).outer,
        inner=Contour(
            points=[
                Point(wall, wall),
                Point(width - wall, wall),
                Point(width - wall, height - wall),
                Point(wall, height - wall),
            ],
        ),
    )


def test_closed_form_of_a_solid_rectangle() -> None:
    props = calculate(rectangle())
    assert props.area == pytest.approx(100 * 200, rel=1e-12)
    assert props.perimeter == pytest.approx(2 * (100 + 200), rel=1e-12)
    assert props.cx == pytest.approx(50, rel=1e-12)
    assert props.cy == pytest.approx(100, rel=1e-12)


def test_solid_rectangle_second_moments() -> None:
    props = calculate(rectangle())
    assert props.ix == pytest.approx(100 * 200**3 / 12, rel=1e-10)
    assert props.iy == pytest.approx(200 * 100**3 / 12, rel=1e-10)
    assert props.ixy == pytest.approx(0.0, abs=1e-3)


def test_solid_rectangle_principal_values_match_the_axes() -> None:
    props = calculate(rectangle())
    assert props.i1 == pytest.approx(props.ix, rel=1e-10)
    assert props.i2 == pytest.approx(props.iy, rel=1e-10)
    assert props.principal_angle_deg == pytest.approx(0.0, abs=1e-9)


def test_elastic_moduli_use_the_farthest_fibre() -> None:
    props = calculate(rectangle())
    assert props.sx == pytest.approx(props.ix / 100.0, rel=1e-10)
    assert props.sy == pytest.approx(props.iy / 50.0, rel=1e-10)


def test_radii_of_gyration_follow_their_moments() -> None:
    props = calculate(rectangle())
    assert props.rx == pytest.approx(math.sqrt(props.ix / props.area), rel=1e-12)
    assert props.ry == pytest.approx(math.sqrt(props.iy / props.area), rel=1e-12)
    assert props.r1 == pytest.approx(math.sqrt(props.i1 / props.area), rel=1e-12)
    assert props.r2 == pytest.approx(math.sqrt(props.i2 / props.area), rel=1e-12)


def test_bounding_box_is_reported_verbatim() -> None:
    props = calculate(rectangle())
    assert (props.x_min, props.x_max, props.y_min, props.y_max) == (0.0, 100.0, 0.0, 200.0)


def test_hollow_rectangle_subtracts_the_inner_contour() -> None:
    props = calculate(hollow_rectangle())
    assert props.area == pytest.approx(100 * 200 - 88 * 188, rel=1e-12)
    assert props.ix == pytest.approx((100 * 200**3 - 88 * 188**3) / 12, rel=1e-10)
    assert props.iy == pytest.approx((200 * 100**3 - 188 * 88**3) / 12, rel=1e-10)


def test_product_of_inertia_keeps_its_sign_convention() -> None:
    triangle = Section(
        outer=Contour(points=[Point(0, 0), Point(100, 0), Point(0, 100)]),
    )
    props = calculate(triangle)
    assert props.area == pytest.approx(100 * 100 / 2, rel=1e-12)
    assert props.cx == pytest.approx(100 / 3, rel=1e-12)
    assert props.cy == pytest.approx(100 / 3, rel=1e-12)
    assert props.ix == pytest.approx(100 * 100**3 / 36, rel=1e-10)
    assert props.iy == pytest.approx(100 * 100**3 / 36, rel=1e-10)
    assert props.ixy == pytest.approx(-100 * 100**3 / 72, rel=1e-10)


def test_principal_values_of_an_asymmetric_section() -> None:
    triangle = Section(
        outer=Contour(points=[Point(0, 0), Point(100, 0), Point(0, 100)]),
    )
    props = calculate(triangle)
    mean = (props.ix + props.iy) / 2
    radius = math.hypot((props.ix - props.iy) / 2, props.ixy)
    assert props.i1 == pytest.approx(mean + radius, rel=1e-10)
    assert props.i2 == pytest.approx(mean - radius, rel=1e-10)
    assert props.principal_angle_deg == pytest.approx(45.0, abs=1e-9)


def test_principal_angle_lies_in_one_axis_range() -> None:
    triangle = Section(
        outer=Contour(points=[Point(0, 0), Point(100, 0), Point(0, 100)]),
    )
    angle = calculate(triangle).principal_angle_deg
    assert -90.0 < angle <= 90.0


def test_clockwise_input_gives_the_same_result_as_counter_clockwise() -> None:
    clockwise = Section(
        outer=Contour(
            points=[Point(0, 0), Point(0, 200), Point(100, 200), Point(100, 0)],
        ),
    )
    assert calculate(clockwise) == calculate(rectangle())


def test_calculation_does_not_mutate_the_section() -> None:
    section = rectangle()
    before = [(point.x, point.y) for point in section.outer.points]
    calculate(section)
    assert [(point.x, point.y) for point in section.outer.points] == before


def test_open_contour_blocks_the_calculation() -> None:
    broken = Section(
        outer=Contour(
            points=[Point(0, 0), Point(100, 0), Point(100, 200), Point(0, 200)],
            closed=False,
        ),
    )
    with pytest.raises(InvalidSectionError) as error:
        calculate(broken)
    assert [issue.code.value for issue in error.value.issues] == ["OPEN_CONTOUR"]


def test_self_intersection_blocks_the_calculation() -> None:
    bow_tie = Section(
        outer=Contour(points=[Point(0, 0), Point(100, 100), Point(100, 0), Point(0, 100)]),
    )
    with pytest.raises(InvalidSectionError) as error:
        calculate(bow_tie)
    assert [issue.code.value for issue in error.value.issues] == ["SELF_INTERSECTION"]


def test_properties_are_plain_floats() -> None:
    props = calculate(rectangle())
    assert isinstance(props, SectionProperties)
    for field in SectionProperties.__dataclass_fields__:
        assert isinstance(getattr(props, field), float), field
