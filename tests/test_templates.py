"""Parametric templates and their closed-form properties (specs S10, S11, S13)."""

from __future__ import annotations

import math

import pytest

from sectionlab.core.engine import calculate
from sectionlab.core.model import Section, signed_area
from sectionlab.core.templates import (
    CIRCLE_SEGMENTS,
    TemplateKind,
    TemplateParameterError,
    build_section,
    default_params,
    parameters,
)
from sectionlab.core.validation import validate_section

EXPECTED_DEFAULTS = {
    TemplateKind.RECTANGLE: {"b": 100.0, "h": 200.0},
    TemplateKind.RECT_HOLLOW: {"b": 100.0, "h": 200.0, "t": 6.0},
    TemplateKind.CIRCLE: {"d": 100.0},
    TemplateKind.PIPE: {"d": 100.0, "t": 10.0},
    TemplateKind.TRIANGLE: {"b": 100.0, "h": 100.0, "offset": 0.0},
    TemplateKind.POLYGON: {"n": 6.0, "r": 50.0},
    TemplateKind.I_PROFILE: {"h": 200.0, "b": 100.0, "tw": 6.0, "tf": 10.0},
    TemplateKind.H_PROFILE: {"h": 200.0, "b": 200.0, "tw": 8.0, "tf": 12.0},
    TemplateKind.U_CHANNEL: {"h": 200.0, "b": 80.0, "tw": 6.0, "tf": 10.0},
    TemplateKind.L_ANGLE: {"b": 100.0, "h": 100.0, "t": 10.0},
    TemplateKind.T_PROFILE: {"h": 150.0, "b": 100.0, "tw": 8.0, "tf": 12.0},
}


def section_area(section: Section) -> float:
    """Exact polygon area of the contours, independent of the calculation engine."""
    inner = abs(signed_area(section.inner)) if section.inner else 0.0
    return abs(signed_area(section.outer)) - inner


@pytest.mark.parametrize("kind", list(TemplateKind))
def test_defaults_match_the_specification_table(kind: TemplateKind) -> None:
    assert default_params(kind) == EXPECTED_DEFAULTS[kind]


@pytest.mark.parametrize("kind", list(TemplateKind))
def test_every_template_builds_a_valid_section(kind: TemplateKind) -> None:
    section = build_section(kind)
    assert validate_section(section) == []
    assert section.template is not None
    assert section.template.kind == kind.value


@pytest.mark.parametrize(
    "kind",
    [
        kind
        for kind in TemplateKind
        if kind not in (TemplateKind.CIRCLE, TemplateKind.PIPE)
    ],
)
def test_calculation_area_matches_the_exact_polygon_area(kind: TemplateKind) -> None:
    section = build_section(kind)
    props = calculate(section)
    assert props.area == pytest.approx(section_area(section), rel=1e-9)


@pytest.mark.parametrize("kind", list(TemplateKind))
def test_outer_contours_are_counter_clockwise(kind: TemplateKind) -> None:
    assert signed_area(build_section(kind).outer) > 0.0


def test_parameters_are_listed_in_display_order() -> None:
    assert [param.key for param in parameters(TemplateKind.I_PROFILE)] == [
        "h",
        "b",
        "tw",
        "tf",
    ]
    assert parameters(TemplateKind.POLYGON)[0].minimum == 3.0


def test_rectangle_properties() -> None:
    props = calculate(build_section(TemplateKind.RECTANGLE))
    assert props.area == pytest.approx(20_000.0, rel=1e-12)
    assert props.ix == pytest.approx(100 * 200**3 / 12, rel=1e-10)
    assert props.iy == pytest.approx(200 * 100**3 / 12, rel=1e-10)
    assert props.ixy == pytest.approx(0.0, abs=1e-3)


def test_hollow_rectangle_properties() -> None:
    props = calculate(build_section(TemplateKind.RECT_HOLLOW))
    assert props.area == pytest.approx(100 * 200 - 88 * 188, rel=1e-12)
    assert props.ix == pytest.approx((100 * 200**3 - 88 * 188**3) / 12, rel=1e-10)


def test_solid_circle_is_calculated_from_the_closed_form() -> None:
    props = calculate(build_section(TemplateKind.CIRCLE))
    assert props.area == pytest.approx(math.pi * 100**2 / 4, rel=1e-15)
    assert props.ix == pytest.approx(math.pi * 100**4 / 64, rel=1e-15)
    assert props.iy == pytest.approx(props.ix, rel=1e-15)
    assert props.ixy == 0.0
    assert props.sx == pytest.approx(props.ix / 50.0, rel=1e-15)
    assert props.perimeter == pytest.approx(math.pi * 100, rel=1e-15)


def test_pipe_is_calculated_from_the_closed_form() -> None:
    props = calculate(build_section(TemplateKind.PIPE))
    inner = 100 - 2 * 10
    assert props.area == pytest.approx(math.pi / 4 * (100**2 - inner**2), rel=1e-15)
    assert props.ix == pytest.approx(math.pi / 64 * (100**4 - inner**4), rel=1e-15)


def test_curved_templates_do_not_depend_on_the_display_polygon() -> None:
    section = build_section(TemplateKind.CIRCLE)
    assert len(section.outer.points) == CIRCLE_SEGMENTS
    assert calculate(section).area > section_area(section)


def test_triangle_properties() -> None:
    props = calculate(build_section(TemplateKind.TRIANGLE))
    assert props.area == pytest.approx(100 * 100 / 2, rel=1e-12)
    assert props.cy == pytest.approx(100 / 3, rel=1e-10)
    assert props.ix == pytest.approx(100 * 100**3 / 36, rel=1e-10)
    assert props.iy == pytest.approx(100 * 100**3 / 48, rel=1e-10)


def test_triangle_apex_offset_shifts_the_centroid() -> None:
    centred = calculate(build_section(TemplateKind.TRIANGLE))
    shifted = calculate(build_section(TemplateKind.TRIANGLE, {"offset": 20.0}))
    assert shifted.cx == pytest.approx(centred.cx + 20 / 3, rel=1e-10)


def test_regular_polygon_area_and_symmetry() -> None:
    props = calculate(build_section(TemplateKind.POLYGON))
    sides, radius = 6, 50.0
    exact_area = sides * radius**2 / 2 * math.sin(2 * math.pi / sides)
    assert props.area == pytest.approx(exact_area, rel=1e-9)
    assert props.ix == pytest.approx(props.iy, rel=1e-9)
    assert props.ixy == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    ("kind", "expected_area"),
    [
        (TemplateKind.I_PROFILE, 100 * 10 * 2 + 6 * 180),
        (TemplateKind.H_PROFILE, 200 * 12 * 2 + 8 * 176),
        (TemplateKind.U_CHANNEL, 80 * 10 * 2 + 6 * 180),
        (TemplateKind.L_ANGLE, 10 * 100 + 10 * 90),
        (TemplateKind.T_PROFILE, 100 * 12 + 8 * 138),
    ],
)
def test_angular_profiles_have_the_decomposed_area(
    kind: TemplateKind, expected_area: float
) -> None:
    assert calculate(build_section(kind)).area == pytest.approx(expected_area, rel=1e-9)


@pytest.mark.parametrize(
    "kind",
    [
        TemplateKind.I_PROFILE,
        TemplateKind.H_PROFILE,
        TemplateKind.U_CHANNEL,
        TemplateKind.T_PROFILE,
        TemplateKind.RECTANGLE,
        TemplateKind.RECT_HOLLOW,
        TemplateKind.POLYGON,
    ],
)
def test_symmetric_templates_have_no_product_of_inertia(kind: TemplateKind) -> None:
    assert calculate(build_section(kind)).ixy == pytest.approx(0.0, abs=1e-4)


def test_angle_profile_has_a_product_of_inertia() -> None:
    """Ixy = integral of x*y over the area, so material in the two positive legs is negative."""
    props = calculate(build_section(TemplateKind.L_ANGLE))
    assert props.ixy < 0.0
    assert props.principal_angle_deg != 0.0


def test_profile_bounding_boxes_follow_the_parameters() -> None:
    i_props = calculate(build_section(TemplateKind.I_PROFILE))
    assert (i_props.x_min, i_props.x_max) == (-50.0, 50.0)
    assert (i_props.y_min, i_props.y_max) == (0.0, 200.0)

    u_props = calculate(build_section(TemplateKind.U_CHANNEL))
    assert (u_props.x_min, u_props.x_max) == (-80.0, 0.0)


def test_parameter_changes_rebuild_the_geometry() -> None:
    section = build_section(TemplateKind.RECTANGLE, {"b": 150.0})
    assert section.template is not None
    assert section.template.params == {"b": 150.0, "h": 200.0}
    assert calculate(section).area == pytest.approx(150 * 200, rel=1e-9)


@pytest.mark.parametrize(
    ("kind", "params", "code"),
    [
        (TemplateKind.RECTANGLE, {"b": 0.0}, "PARAMETER_NOT_POSITIVE"),
        (TemplateKind.RECT_HOLLOW, {"t": 100.0}, "WALL_NOT_THINNER_THAN_OUTER"),
        (TemplateKind.PIPE, {"t": 50.0}, "WALL_NOT_THINNER_THAN_RADIUS"),
        (TemplateKind.POLYGON, {"n": 2.0}, "SIDES_BELOW_THREE"),
        (TemplateKind.L_ANGLE, {"t": 200.0}, "LEG_NOT_THINNER_THAN_OUTER"),
        (TemplateKind.I_PROFILE, {"tf": 120.0}, "FLANGE_TOO_THICK"),
        (TemplateKind.U_CHANNEL, {"tw": 200.0}, "WEB_TOO_WIDE"),
        (TemplateKind.T_PROFILE, {"tf": 150.0}, "FLANGE_TOO_THICK"),
    ],
)
def test_impossible_parameters_are_rejected(
    kind: TemplateKind, params: dict[str, float], code: str
) -> None:
    with pytest.raises(TemplateParameterError) as error:
        build_section(kind, params)
    assert error.value.code == code


# --- each template declares which parameter a measure drives (spec S6) -------------------

from sectionlab.core.dimensions import (  # noqa: E402
    ANCHOR_EDGE,
    ANCHOR_VERTEX,
    HORIZONTAL,
    SEGMENT_LENGTH,
    VERTICAL,
    Anchor,
    Dimension,
    measure,
)
from sectionlab.core.templates import (  # noqa: E402
    default_params,
    parameter_for,
    parameter_override,
)


def span(first: int, second: int, kind: str) -> Dimension:
    return Dimension(
        id=1,
        first=Anchor(ANCHOR_VERTEX, first),
        second=Anchor(ANCHOR_VERTEX, second),
        kind=kind,
        offset_mm=6.0,
    )


def points_of(kind: TemplateKind, **overrides: float) -> list[Point]:
    return build_section(kind, overrides).outer.points


@pytest.mark.parametrize(
    ("kind", "dimension", "parameter"),
    [
        (TemplateKind.RECTANGLE, span(0, 1, HORIZONTAL), "b"),
        (TemplateKind.RECTANGLE, span(0, 3, VERTICAL), "h"),
        (TemplateKind.CIRCLE, span(0, 180, HORIZONTAL), "d"),
        (TemplateKind.PIPE, span(0, 180, HORIZONTAL), "d"),
        (TemplateKind.TRIANGLE, span(0, 1, HORIZONTAL), "b"),
        (TemplateKind.TRIANGLE, span(0, 2, VERTICAL), "h"),
        (TemplateKind.POLYGON, span(0, 3, VERTICAL), "r"),
        (TemplateKind.I_PROFILE, span(0, 1, HORIZONTAL), "b"),
        (TemplateKind.I_PROFILE, span(0, 6, VERTICAL), "h"),
        (TemplateKind.I_PROFILE, span(9, 4, HORIZONTAL), "tw"),
        (TemplateKind.I_PROFILE, span(1, 2, VERTICAL), "tf"),
        (TemplateKind.H_PROFILE, span(0, 6, VERTICAL), "h"),
        (TemplateKind.U_CHANNEL, span(0, 1, HORIZONTAL), "b"),
        (TemplateKind.U_CHANNEL, span(0, 7, VERTICAL), "h"),
        (TemplateKind.U_CHANNEL, span(0, 3, HORIZONTAL), "tw"),
        (TemplateKind.U_CHANNEL, span(1, 2, VERTICAL), "tf"),
        (TemplateKind.L_ANGLE, span(0, 1, HORIZONTAL), "b"),
        (TemplateKind.L_ANGLE, span(0, 5, VERTICAL), "h"),
        (TemplateKind.L_ANGLE, span(1, 2, VERTICAL), "t"),
        (TemplateKind.T_PROFILE, span(4, 5, HORIZONTAL), "b"),
        (TemplateKind.T_PROFILE, span(0, 4, VERTICAL), "h"),
        (TemplateKind.T_PROFILE, span(0, 1, HORIZONTAL), "tw"),
        (TemplateKind.T_PROFILE, span(2, 4, VERTICAL), "tf"),
    ],
)
def test_the_measure_each_template_declares(kind: TemplateKind, dimension, parameter: str) -> None:
    assert parameter_for(kind, default_params(kind), dimension) == parameter


@pytest.mark.parametrize(
    ("kind", "dimension"),
    [
        # A web height depends on the height and on the flange thickness at once.
        (TemplateKind.I_PROFILE, span(3, 4, VERTICAL)),
        (TemplateKind.U_CHANNEL, span(2, 5, VERTICAL)),
        # A triangle's base is broken by the apex offset, so its height is the only free one.
        (TemplateKind.TRIANGLE, span(1, 2, HORIZONTAL)),
    ],
)
def test_a_measure_two_parameters_share_has_no_driver(kind: TemplateKind, dimension) -> None:
    assert parameter_for(kind, default_params(kind), dimension) is None


def test_the_number_of_sides_is_never_driven_by_a_dimension() -> None:
    for index in range(1, 6):
        assert parameter_for(TemplateKind.POLYGON, default_params(TemplateKind.POLYGON), span(0, index, HORIZONTAL)) != "n"


def test_an_edge_anchor_can_isolate_a_parameter_a_vertex_cannot() -> None:
    """On a triangle the apex offset is measurable only against the middle of the base."""
    dimension = Dimension(
        id=1,
        first=Anchor(ANCHOR_VERTEX, 2),
        second=Anchor(ANCHOR_EDGE, 0, 0.5),
        kind=HORIZONTAL,
        offset_mm=6.0,
    )
    assert parameter_for(TemplateKind.TRIANGLE, default_params(TemplateKind.TRIANGLE), dimension) == "offset"


def test_an_override_makes_the_measure_equal_the_target() -> None:
    kind = TemplateKind.I_PROFILE
    params = default_params(kind)
    dimension = span(0, 1, HORIZONTAL)
    override = parameter_override(kind, params, dimension, 240.0)
    assert override is not None
    rebuilt = build_section(kind, {**params, **override})
    assert measure(rebuilt.outer.points, dimension) == pytest.approx(240.0)


def test_an_override_on_a_shared_measure_is_refused() -> None:
    kind = TemplateKind.I_PROFILE
    assert parameter_override(kind, default_params(kind), span(3, 4, VERTICAL), 120.0) is None


def test_an_override_that_would_break_the_section_is_refused() -> None:
    kind = TemplateKind.RECT_HOLLOW
    dimension = span(0, 1, HORIZONTAL)
    assert parameter_override(kind, default_params(kind), dimension, 0.05) is None


def test_an_override_keeps_twelve_vertices_in_the_same_order() -> None:
    kind = TemplateKind.I_PROFILE
    params = default_params(kind)
    before = points_of(kind)
    rebuilt = build_section(kind, {**params, **(parameter_override(kind, params, span(0, 1, HORIZONTAL), 240.0) or {})})
    assert len(rebuilt.outer.points) == len(before)
    assert [point.y for point in rebuilt.outer.points] == [point.y for point in before]
