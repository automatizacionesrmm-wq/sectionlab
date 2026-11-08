"""Display precision and export precision (specs S3, S4, S15; decision D5)."""

from __future__ import annotations

import pytest

from sectionlab.core.precision import (
    DEFAULT_DECIMALS,
    MAX_DECIMALS,
    MIN_DECIMALS,
    format_full,
    format_value,
    results_to_csv,
)


def test_decimal_bounds_are_the_documented_ones() -> None:
    assert (MIN_DECIMALS, DEFAULT_DECIMALS, MAX_DECIMALS) == (0, 2, 6)


@pytest.mark.parametrize(
    ("decimals", "expected"),
    [
        (0, "1"),
        (1, "1.2"),
        (2, "1.23"),
        (6, "1.234568"),
    ],
)
def test_display_rounds_to_the_requested_decimals(decimals: int, expected: str) -> None:
    assert format_value(1.2345678, decimals) == expected


def test_display_clamps_decimals_into_range() -> None:
    assert format_value(1.25, -3) == format_value(1.25, MIN_DECIMALS)
    assert format_value(1.25, 11) == format_value(1.25, MAX_DECIMALS)


def test_display_defaults_to_two_decimals() -> None:
    assert format_value(3.14159, DEFAULT_DECIMALS) == "3.14"


def test_full_precision_round_trips_through_float() -> None:
    for value in (0.1 + 0.2, 1 / 3, 1e-7, 123456789.123456, -66_666_666.66666667):
        assert float(format_full(value)) == value


def test_full_precision_keeps_digits_display_would_hide() -> None:
    assert format_value(1.23456789, DEFAULT_DECIMALS) == "1.23"
    assert format_full(1.23456789) == repr(1.23456789)


def test_csv_without_rows_is_empty() -> None:
    assert results_to_csv([]) == ""


def test_csv_header_follows_first_row_key_order() -> None:
    csv_text = results_to_csv([{"area": 20000.0, "ix": 66_666_666.66666667}])
    header, row = csv_text.splitlines()
    assert header == "area,ix"
    assert row.split(",") == ["20000.0", format_full(66_666_666.66666667)]


def test_csv_keeps_full_precision_regardless_of_display_decimals() -> None:
    value = 1 / 3
    assert format_value(value, MIN_DECIMALS) == "0"
    assert format_full(value) in results_to_csv([{"r1": value}])


def test_csv_writes_one_line_per_row_with_deterministic_endings() -> None:
    csv_text = results_to_csv([{"a": 1.0}, {"a": 2.5}])
    assert "\r" not in csv_text
    assert csv_text.count("\n") == 3
    assert csv_text.endswith("\n")


def test_csv_quotes_keys_that_contain_a_comma() -> None:
    assert results_to_csv([{"area, mm2": 1.0}]).startswith('"area, mm2"')


def test_csv_rejects_rows_with_missing_keys() -> None:
    with pytest.raises(KeyError):
        results_to_csv([{"a": 1.0, "b": 2.0}, {"a": 3.0}])
