"""Contour validation that blocks calculation (specs S5, S13; decision D6)."""

from __future__ import annotations

import pytest

from sectionlab.core.model import Contour, Point, Section
from sectionlab.core.validation import (
    CLOSURE_TOLERANCE_MM,
    IssueCode,
    ValidationIssue,
    validate_section,
)


def square() -> Contour:
    return Contour(points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)])


def codes(section: Section) -> list[IssueCode]:
    return [issue.code for issue in validate_section(section)]


def test_tolerance_is_the_documented_value() -> None:
    assert CLOSURE_TOLERANCE_MM == 1e-6


def test_closed_square_has_no_issues() -> None:
    assert validate_section(Section(outer=square())) == []


def test_open_contour_reports_the_missing_closing_edge() -> None:
    open_contour = Contour(
        points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)],
        closed=False,
    )
    issues = validate_section(Section(outer=open_contour))
    assert [issue.code for issue in issues] == [IssueCode.OPEN_CONTOUR]
    assert issues[0].points == (Point(0, 10), Point(0, 0))


def test_two_vertices_are_not_a_contour() -> None:
    contour = Contour(points=[Point(0, 0), Point(10, 0)])
    assert codes(Section(outer=contour)) == [IssueCode.TOO_FEW_VERTICES]


def test_no_vertices_are_not_a_contour() -> None:
    assert codes(Section(outer=Contour(points=[]))) == [IssueCode.TOO_FEW_VERTICES]


def test_duplicate_points_are_reported() -> None:
    contour = Contour(
        points=[Point(0, 0), Point(10, 0), Point(10, 0), Point(10, 10), Point(0, 10)],
    )
    issues = validate_section(Section(outer=contour))
    assert IssueCode.DUPLICATE_POINTS in [issue.code for issue in issues]
    duplicate_issue = next(i for i in issues if i.code is IssueCode.DUPLICATE_POINTS)
    assert duplicate_issue.points == (Point(10, 0), Point(10, 0))


def test_points_within_tolerance_count_as_duplicates() -> None:
    contour = Contour(
        points=[
            Point(0, 0),
            Point(10, 0),
            Point(10, 0 + CLOSURE_TOLERANCE_MM / 2),
            Point(10, 10),
            Point(0, 10),
        ],
    )
    assert IssueCode.DUPLICATE_POINTS in codes(Section(outer=contour))


def test_repeating_the_first_point_at_the_end_is_not_a_duplicate() -> None:
    contour = Contour(
        points=[Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10), Point(0, 0)],
    )
    assert validate_section(Section(outer=contour)) == []


def test_self_intersection_is_reported_with_crossing_points() -> None:
    bow_tie = Contour(
        points=[Point(0, 0), Point(10, 10), Point(10, 0), Point(0, 10)],
    )
    issues = validate_section(Section(outer=bow_tie))
    assert [issue.code for issue in issues] == [IssueCode.SELF_INTERSECTION]
    assert issues[0].points == (Point(5, 5),)


def test_zero_area_is_reported_for_collinear_points() -> None:
    collinear = Contour(
        points=[Point(0, 0), Point(5, 0), Point(10, 0), Point(10, 1e-9)],
    )
    assert IssueCode.ZERO_AREA in codes(Section(outer=collinear))


def test_inner_contour_is_validated_too() -> None:
    inner_broken = Contour(points=[Point(2, 2), Point(8, 2), Point(8, 8), Point(2, 8)], closed=False)
    issues = validate_section(Section(outer=square(), inner=inner_broken))
    assert [issue.code for issue in issues] == [IssueCode.OPEN_CONTOUR]


def test_valid_hollow_section_has_no_issues() -> None:
    inner = Contour(points=[Point(2, 2), Point(8, 2), Point(8, 8), Point(2, 8)])
    assert validate_section(Section(outer=square(), inner=inner)) == []


def test_issue_carries_a_code_that_can_be_localized_later() -> None:
    issue = ValidationIssue(IssueCode.ZERO_AREA, (Point(0, 0),))
    assert issue.code.value == "ZERO_AREA"


def test_multiple_problems_are_all_reported() -> None:
    contour = Contour(
        points=[Point(0, 0), Point(10, 0), Point(10, 0), Point(10, 10), Point(0, 10)],
        closed=False,
    )
    reported = codes(Section(outer=contour))
    assert reported[0] is IssueCode.OPEN_CONTOUR
    assert IssueCode.DUPLICATE_POINTS in reported
