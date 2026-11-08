"""Section geometry model (specs S5, S9; decisions D3, D4)."""

from __future__ import annotations

import pytest

from sectionlab.core.model import Contour, Point, Section, TemplateSpec, normalize_ccw, signed_area


def rectangle(points: list[Point]) -> Contour:
    return Contour(points=list(points))


def test_point_is_a_plain_coordinate_pair() -> None:
    point = Point(1.5, -2.5)
    assert (point.x, point.y) == (1.5, -2.5)


def test_contour_is_closed_by_default() -> None:
    contour = Contour(points=[Point(0, 0), Point(1, 0), Point(1, 1)])
    assert contour.closed is True


def test_counter_clockwise_rectangle_has_positive_signed_area() -> None:
    contour = rectangle(
        [Point(0, 0), Point(120, 0), Point(120, 80), Point(0, 80)],
    )
    assert signed_area(contour) == pytest.approx(120 * 80)


def test_clockwise_rectangle_has_negative_signed_area() -> None:
    contour = rectangle(
        [Point(0, 0), Point(0, 80), Point(120, 80), Point(120, 0)],
    )
    assert signed_area(contour) == pytest.approx(-120 * 80)


def test_signed_area_treats_the_point_list_as_a_ring_even_when_open() -> None:
    contour = Contour(
        points=[Point(0, 0), Point(120, 0), Point(120, 80), Point(0, 80)],
        closed=False,
    )
    assert signed_area(contour) == pytest.approx(120 * 80)


def test_normalize_ccw_flips_a_clockwise_contour() -> None:
    clockwise = rectangle([Point(0, 0), Point(0, 80), Point(120, 80), Point(120, 0)])
    normalized = normalize_ccw(clockwise)
    assert signed_area(normalized) == pytest.approx(120 * 80)
    assert len(normalized.points) == 4
    assert set((p.x, p.y) for p in normalized.points) == set(
        (p.x, p.y) for p in clockwise.points
    )


def test_normalize_ccw_leaves_a_ccw_contour_untouched() -> None:
    counter_clockwise = rectangle(
        [Point(0, 0), Point(120, 0), Point(120, 80), Point(0, 80)],
    )
    normalized = normalize_ccw(counter_clockwise)
    assert normalized.points == counter_clockwise.points


def test_normalize_ccw_preserves_the_closed_flag() -> None:
    open_clockwise = Contour(
        points=[Point(0, 0), Point(0, 80), Point(120, 80), Point(120, 0)],
        closed=False,
    )
    assert normalize_ccw(open_clockwise).closed is False


def test_section_can_carry_an_inner_contour_for_hollow_templates() -> None:
    outer = rectangle([Point(0, 0), Point(100, 0), Point(100, 200), Point(0, 200)])
    inner = rectangle([Point(6, 6), Point(94, 6), Point(94, 194), Point(6, 194)])
    section = Section(outer=outer, inner=inner, template=TemplateSpec("RECT_HOLLOW", {"b": 100.0}))
    assert section.inner is not None
    assert section.template is not None
    assert section.template.kind == "RECT_HOLLOW"
    assert section.template.params == {"b": 100.0}


def test_free_geometry_section_has_no_template() -> None:
    outer = rectangle([Point(0, 0), Point(10, 0), Point(10, 10)])
    assert Section(outer=outer).template is None
    assert Section(outer=outer).inner is None
