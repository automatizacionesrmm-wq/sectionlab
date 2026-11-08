"""Length, area, section-modulus and second-moment unit conversion.

The internal geometry model is always millimetres (spec S2); every conversion here is an
app responsibility, because the calculation engine is unit-agnostic.
"""

from __future__ import annotations

from enum import Enum


class Unit(str, Enum):
    """Active display unit, shared by input and output."""

    MM = "mm"
    CM = "cm"
    M = "m"
    IN = "in"


FACTOR_TO_MM: dict[Unit, float] = {
    Unit.MM: 1.0,
    Unit.CM: 10.0,
    Unit.M: 1000.0,
    Unit.IN: 25.4,
}


def to_mm(value: float, unit: Unit) -> float:
    """Convert a length in ``unit`` to millimetres."""
    return value * FACTOR_TO_MM[unit]


def from_mm(value: float, unit: Unit) -> float:
    """Convert a length in millimetres to ``unit``."""
    return value / FACTOR_TO_MM[unit]


def to_mm2(value: float, unit: Unit) -> float:
    """Convert an area in ``unit`` squared to square millimetres."""
    return value * FACTOR_TO_MM[unit] ** 2


def from_mm2(value: float, unit: Unit) -> float:
    """Convert an area in square millimetres to ``unit`` squared."""
    return value / FACTOR_TO_MM[unit] ** 2


def to_mm3(value: float, unit: Unit) -> float:
    """Convert a section modulus in ``unit`` cubed to cubic millimetres."""
    return value * FACTOR_TO_MM[unit] ** 3


def from_mm3(value: float, unit: Unit) -> float:
    """Convert a section modulus in cubic millimetres to ``unit`` cubed."""
    return value / FACTOR_TO_MM[unit] ** 3


def to_mm4(value: float, unit: Unit) -> float:
    """Convert a second moment of area in ``unit`` to the fourth to ``unit`` in mm."""
    return value * FACTOR_TO_MM[unit] ** 4


def from_mm4(value: float, unit: Unit) -> float:
    """Convert a second moment of area in mm to the fourth to ``unit`` to the fourth."""
    return value / FACTOR_TO_MM[unit] ** 4
