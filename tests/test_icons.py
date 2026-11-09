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


def ink_box(image) -> tuple[int, int, int, int]:
    xs = [
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 40
    ]
    return (
        min(x for x, _ in xs),
        min(y for _, y in xs),
        max(x for x, _ in xs),
        max(y for _, y in xs),
    )


def test_every_icon_fills_its_box_without_being_clipped() -> None:
    """A doubled scale used to clip every icon down to its top-left corner."""
    size = 32
    for name in icons.names():
        image = icons.icon(name, "#ffffff", size).pixmap(size, size).toImage()
        left, top, right, bottom = ink_box(image)
        assert (left, top, right, bottom) != (size - 1, size - 1, size - 1, size - 1), name
        assert left >= 1 and top >= 1, name
        assert right <= size - 2 and bottom <= size - 2, name
        assert max(right - left, bottom - top) >= 0.4 * size, name
