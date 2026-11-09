"""The generated icon set: every icon renders, and only known names resolve (spec S2)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSize

from sectionlab.ui import icons

pytestmark = pytest.mark.usefixtures("qapp")


def test_every_icon_renders() -> None:
    for name in icons.names():
        rendered = icons.icon(name, "#39d0ff", 20)
        assert not rendered.isNull(), name
        assert not rendered.pixmap(20, 20).isNull(), name


def test_icons_are_supersampled_for_high_density_screens() -> None:
    rendered = icons.icon("calculate", "#ffffff", 24)
    assert QSize(48, 48) in rendered.availableSizes()
    assert rendered.pixmap(24, 24).width() == 24


def test_an_unknown_icon_is_reported() -> None:
    with pytest.raises(KeyError):
        icons.icon("not-an-icon")


def test_an_invalid_colour_falls_back_to_grey() -> None:
    assert not icons.icon("save", "not-a-colour").isNull()


def test_the_toolbar_icons_exist() -> None:
    expected = {
        "calculate",
        "open",
        "save",
        "csv",
        "undo",
        "redo",
        "insert",
        "delete",
        "ortho",
        "zoom_in",
        "zoom_out",
        "fit",
        "theme",
        "settings",
        "light",
        "moon",
    }
    assert expected <= set(icons.names())
