"""Colour tokens and the generated stylesheet for the two themes (spec S1)."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor

from sectionlab.ui.theme import DARK, LIGHT, Theme, stylesheet, tokens

pytestmark = pytest.mark.usefixtures("qapp")


def test_both_themes_expose_the_same_tokens() -> None:
    assert set(DARK) == set(LIGHT)


def test_every_token_is_a_colour() -> None:
    for theme in (Theme.DARK, Theme.LIGHT):
        for name, value in tokens(theme).items():
            assert QColor(value).isValid(), f"{theme.value}.{name}={value}"


def test_the_stylesheet_carries_the_theme_accent() -> None:
    assert DARK["accent"] in stylesheet(Theme.DARK)
    assert LIGHT["accent"] in stylesheet(Theme.LIGHT)
    assert stylesheet(Theme.DARK) != stylesheet(Theme.LIGHT)


def test_an_unknown_theme_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        Theme("solarized")


def test_themes_are_addressable_by_value() -> None:
    assert Theme("dark") is Theme.DARK
    assert Theme("light") is Theme.LIGHT
