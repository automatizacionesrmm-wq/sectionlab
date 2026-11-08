"""Parametric templates: geometry only, no calculation.

Every template returns millimetre contours with counter-clockwise winding. Angular
templates are exact polygons with sharp corners (S10, decision D2); curved templates are a
polygon approximation for display only, because their properties are calculated from closed
forms (decision D1).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from sectionlab.core.model import Contour, Point, Section, TemplateSpec

CIRCLE_SEGMENTS = 360


class TemplateKind(str, Enum):
    """The templates offered in v1 (spec S10)."""

    RECTANGLE = "RECTANGLE"
    RECT_HOLLOW = "RECT_HOLLOW"
    CIRCLE = "CIRCLE"
    PIPE = "PIPE"
    TRIANGLE = "TRIANGLE"
    POLYGON = "POLYGON"
    I_PROFILE = "I_PROFILE"
    H_PROFILE = "H_PROFILE"
    U_CHANNEL = "U_CHANNEL"
    L_ANGLE = "L_ANGLE"
    T_PROFILE = "T_PROFILE"


class TemplateParameterError(ValueError):
    """Raised when the parameter combination cannot describe a closed section."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class TemplateParam:
    """One editable parameter: key, default value in mm, and its smallest allowed value."""

    key: str
    default: float
    minimum: float


_PARAMETERS: dict[TemplateKind, tuple[TemplateParam, ...]] = {
    TemplateKind.RECTANGLE: (
        TemplateParam("b", 100.0, 0.1),
        TemplateParam("h", 200.0, 0.1),
    ),
    TemplateKind.RECT_HOLLOW: (
        TemplateParam("b", 100.0, 0.1),
        TemplateParam("h", 200.0, 0.1),
        TemplateParam("t", 6.0, 0.1),
    ),
    TemplateKind.CIRCLE: (TemplateParam("d", 100.0, 0.1),),
    TemplateKind.PIPE: (
        TemplateParam("d", 100.0, 0.1),
        TemplateParam("t", 10.0, 0.1),
    ),
    TemplateKind.TRIANGLE: (
        TemplateParam("b", 100.0, 0.1),
        TemplateParam("h", 100.0, 0.1),
        TemplateParam("offset", 0.0, -10000.0),
    ),
    TemplateKind.POLYGON: (
        TemplateParam("n", 6.0, 3.0),
        TemplateParam("r", 50.0, 0.1),
    ),
    TemplateKind.I_PROFILE: (
        TemplateParam("h", 200.0, 0.1),
        TemplateParam("b", 100.0, 0.1),
        TemplateParam("tw", 6.0, 0.1),
        TemplateParam("tf", 10.0, 0.1),
    ),
    TemplateKind.H_PROFILE: (
        TemplateParam("h", 200.0, 0.1),
        TemplateParam("b", 200.0, 0.1),
        TemplateParam("tw", 8.0, 0.1),
        TemplateParam("tf", 12.0, 0.1),
    ),
    TemplateKind.U_CHANNEL: (
        TemplateParam("h", 200.0, 0.1),
        TemplateParam("b", 80.0, 0.1),
        TemplateParam("tw", 6.0, 0.1),
        TemplateParam("tf", 10.0, 0.1),
    ),
    TemplateKind.L_ANGLE: (
        TemplateParam("b", 100.0, 0.1),
        TemplateParam("h", 100.0, 0.1),
        TemplateParam("t", 10.0, 0.1),
    ),
    TemplateKind.T_PROFILE: (
        TemplateParam("h", 150.0, 0.1),
        TemplateParam("b", 100.0, 0.1),
        TemplateParam("tw", 8.0, 0.1),
        TemplateParam("tf", 12.0, 0.1),
    ),
}


def parameters(kind: TemplateKind) -> tuple[TemplateParam, ...]:
    """The editable parameters of a template, in display order."""
    return _PARAMETERS[kind]


def default_params(kind: TemplateKind) -> dict[str, float]:
    """Default parameter values in millimetres."""
    return {param.key: param.default for param in parameters(kind)}


def build_section(kind: TemplateKind, params: Mapping[str, float] | None = None) -> Section:
    """Build the template geometry from its parameters, filling in the defaults.

    Raises `TemplateParameterError` when the values cannot describe a closed section.
    """
    values = default_params(kind)
    values.update({key: float(value) for key, value in (params or {}).items()})

    _check_positive(kind, values)
    outer, inner = _BUILDERS[kind](values)
    return Section(
        outer=outer,
        inner=inner,
        template=TemplateSpec(kind=kind.value, params=values),
    )


def _check_positive(kind: TemplateKind, values: Mapping[str, float]) -> None:
    for param in parameters(kind):
        if param.key == "offset":
            continue
        if param.key == "n":
            if values["n"] < 3:
                raise TemplateParameterError("SIDES_BELOW_THREE", "a regular polygon needs 3 sides")
            continue
        if values[param.key] <= 0:
            raise TemplateParameterError(
                "PARAMETER_NOT_POSITIVE",
                f"parameter {param.key} must be greater than zero",
            )


def _rect(width: float, height: float, x_offset: float = 0.0, y_offset: float = 0.0) -> Contour:
    return Contour(
        points=[
            Point(x_offset, y_offset),
            Point(x_offset + width, y_offset),
            Point(x_offset + width, y_offset + height),
            Point(x_offset, y_offset + height),
        ]
    )


def _ring(diameter: float, segments: int = CIRCLE_SEGMENTS) -> Contour:
    radius = diameter / 2
    return Contour(
        points=[
            Point(
                radius * math.cos(2 * math.pi * index / segments),
                radius * math.sin(2 * math.pi * index / segments),
            )
            for index in range(segments)
        ]
    )


def _rectangle(values: Mapping[str, float]) -> tuple[Contour, None]:
    return _rect(values["b"], values["h"]), None


def _rect_hollow(values: Mapping[str, float]) -> tuple[Contour, Contour | None]:
    width, height, wall = values["b"], values["h"], values["t"]
    if 2 * wall >= min(width, height):
        raise TemplateParameterError(
            "WALL_NOT_THINNER_THAN_OUTER",
            "the wall leaves no opening",
        )
    inner = _rect(width - 2 * wall, height - 2 * wall, wall, wall)
    return _rect(width, height), inner


def _circle(values: Mapping[str, float]) -> tuple[Contour, None]:
    return _ring(values["d"]), None


def _pipe(values: Mapping[str, float]) -> tuple[Contour, Contour | None]:
    diameter, wall = values["d"], values["t"]
    inner_diameter = diameter - 2 * wall
    if inner_diameter <= 0:
        raise TemplateParameterError(
            "WALL_NOT_THINNER_THAN_RADIUS",
            "the wall closes the inner hole",
        )
    return _ring(diameter), Contour(points=list(reversed(_ring(inner_diameter).points)))


def _triangle(values: Mapping[str, float]) -> tuple[Contour, None]:
    width, height, offset = values["b"], values["h"], values["offset"]
    return (
        Contour(
            points=[
                Point(0, 0),
                Point(width, 0),
                Point(width / 2 + offset, height),
            ]
        ),
        None,
    )


def _regular_polygon(values: Mapping[str, float]) -> tuple[Contour, None]:
    sides = int(round(values["n"]))
    radius = values["r"]
    return (
        Contour(
            points=[
                Point(
                    radius * math.cos(math.pi / 2 + 2 * math.pi * index / sides),
                    radius * math.sin(math.pi / 2 + 2 * math.pi * index / sides),
                )
                for index in range(sides)
            ]
        ),
        None,
    )


def _i_profile(values: Mapping[str, float]) -> tuple[Contour, None]:
    height, width = values["h"], values["b"]
    web, flange = values["tw"], values["tf"]
    if 2 * flange >= height:
        raise TemplateParameterError("FLANGE_TOO_THICK", "the flanges leave no web")
    if web >= width:
        raise TemplateParameterError("WEB_TOO_WIDE", "the web is wider than the flange")
    half_width, half_web = width / 2, web / 2
    return (
        Contour(
            points=[
                Point(-half_width, 0),
                Point(half_width, 0),
                Point(half_width, flange),
                Point(half_web, flange),
                Point(half_web, height - flange),
                Point(half_width, height - flange),
                Point(half_width, height),
                Point(-half_width, height),
                Point(-half_width, height - flange),
                Point(-half_web, height - flange),
                Point(-half_web, flange),
                Point(-half_width, flange),
            ]
        ),
        None,
    )


def _h_profile(values: Mapping[str, float]) -> tuple[Contour, None]:
    return _i_profile(values)


def _u_channel(values: Mapping[str, float]) -> tuple[Contour, None]:
    height, width = values["h"], values["b"]
    web, flange = values["tw"], values["tf"]
    if 2 * flange >= height:
        raise TemplateParameterError("FLANGE_TOO_THICK", "the flanges leave no web")
    if web >= width:
        raise TemplateParameterError("WEB_TOO_WIDE", "the web is wider than the flange")
    return (
        Contour(
            points=[
                Point(-width, 0),
                Point(0, 0),
                Point(0, flange),
                Point(-width + web, flange),
                Point(-width + web, height - flange),
                Point(0, height - flange),
                Point(0, height),
                Point(-width, height),
            ]
        ),
        None,
    )


def _l_angle(values: Mapping[str, float]) -> tuple[Contour, None]:
    width, height, thickness = values["b"], values["h"], values["t"]
    if thickness >= min(width, height):
        raise TemplateParameterError("LEG_NOT_THINNER_THAN_OUTER", "the leg thickness is too large")
    return (
        Contour(
            points=[
                Point(0, 0),
                Point(width, 0),
                Point(width, thickness),
                Point(thickness, thickness),
                Point(thickness, height),
                Point(0, height),
            ]
        ),
        None,
    )


def _t_profile(values: Mapping[str, float]) -> tuple[Contour, None]:
    height, width = values["h"], values["b"]
    web, flange = values["tw"], values["tf"]
    if flange >= height:
        raise TemplateParameterError("FLANGE_TOO_THICK", "the flange leaves no web")
    if web >= width:
        raise TemplateParameterError("WEB_TOO_WIDE", "the web is wider than the flange")
    half_width, half_web = width / 2, web / 2
    return (
        Contour(
            points=[
                Point(-half_web, 0),
                Point(half_web, 0),
                Point(half_web, height - flange),
                Point(half_width, height - flange),
                Point(half_width, height),
                Point(-half_width, height),
                Point(-half_width, height - flange),
                Point(-half_web, height - flange),
            ]
        ),
        None,
    )


_BUILDERS = {
    TemplateKind.RECTANGLE: _rectangle,
    TemplateKind.RECT_HOLLOW: _rect_hollow,
    TemplateKind.CIRCLE: _circle,
    TemplateKind.PIPE: _pipe,
    TemplateKind.TRIANGLE: _triangle,
    TemplateKind.POLYGON: _regular_polygon,
    TemplateKind.I_PROFILE: _i_profile,
    TemplateKind.H_PROFILE: _h_profile,
    TemplateKind.U_CHANNEL: _u_channel,
    TemplateKind.L_ANGLE: _l_angle,
    TemplateKind.T_PROFILE: _t_profile,
}
