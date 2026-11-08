"""Unit conversion rules (specs S2, S4; decision D5)."""

from __future__ import annotations

import pytest

from sectionlab.core.units import (
    FACTOR_TO_MM,
    Unit,
    from_mm,
    from_mm2,
    from_mm3,
    from_mm4,
    to_mm,
    to_mm2,
    to_mm3,
    to_mm4,
)


def test_unit_values_are_the_ui_tokens() -> None:
    assert [unit.value for unit in Unit] == ["mm", "cm", "m", "in"]


def test_millimetre_is_the_identity() -> None:
    assert FACTOR_TO_MM[Unit.MM] == 1.0
    assert to_mm(12.5, Unit.MM) == 12.5
    assert from_mm(12.5, Unit.MM) == 12.5


@pytest.mark.parametrize(
    ("unit", "millimetres"),
    [
        (Unit.CM, 10.0),
        (Unit.M, 1000.0),
        (Unit.IN, 25.4),
    ],
)
def test_lengths_convert_to_and_from_millimetres(unit: Unit, millimetres: float) -> None:
    assert to_mm(1.0, unit) == pytest.approx(millimetres)
    assert from_mm(millimetres, unit) == pytest.approx(1.0)
    assert from_mm(to_mm(3.75, unit), unit) == pytest.approx(3.75)


def test_one_square_inch_is_645_16_square_millimetres() -> None:
    assert to_mm2(1.0, Unit.IN) == pytest.approx(645.16)
    assert from_mm2(645.16, Unit.IN) == pytest.approx(1.0)


def test_one_cubic_inch_is_25_4_cubed_cubic_millimetres() -> None:
    assert to_mm3(1.0, Unit.IN) == pytest.approx(25.4**3)
    assert from_mm3(25.4**3, Unit.IN) == pytest.approx(1.0)


def test_one_fourth_power_inch_is_25_4_to_the_fourth() -> None:
    assert to_mm4(1.0, Unit.IN) == pytest.approx(25.4**4)
    assert from_mm4(25.4**4, Unit.IN) == pytest.approx(1.0)


def test_area_modulus_and_inertia_use_powers_of_the_length_factor() -> None:
    factor = FACTOR_TO_MM[Unit.CM]
    assert to_mm2(2.0, Unit.CM) == pytest.approx(2.0 * factor**2)
    assert to_mm3(2.0, Unit.CM) == pytest.approx(2.0 * factor**3)
    assert to_mm4(2.0, Unit.CM) == pytest.approx(2.0 * factor**4)
    assert from_mm2(2.0 * factor**2, Unit.CM) == pytest.approx(2.0)
    assert from_mm3(2.0 * factor**3, Unit.CM) == pytest.approx(2.0)
    assert from_mm4(2.0 * factor**4, Unit.CM) == pytest.approx(2.0)


def test_conversions_do_not_touch_the_input_value() -> None:
    value = 7.5
    to_mm(value, Unit.IN)
    from_mm(value, Unit.IN)
    assert value == 7.5
