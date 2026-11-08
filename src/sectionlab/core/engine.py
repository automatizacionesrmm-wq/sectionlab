"""Section property calculation, delegated to `sectionproperties`.

The engine receives millimetres and returns plain floats in millimetres, square millimetres,
cubic millimetres, millimetres to the fourth and degrees; it never converts units (spec S1).
Invalid geometry never reaches the mesher (spec S13).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sectionproperties.analysis import Section as MeshAnalysis
from sectionproperties.pre.geometry import Geometry
from shapely.geometry import Polygon

from sectionlab.core.model import Contour, Section, normalize_ccw
from sectionlab.core.templates import TemplateKind
from sectionlab.core.validation import ValidationIssue, validate_section

_CURVED_KINDS = frozenset({TemplateKind.CIRCLE.value, TemplateKind.PIPE.value})

# Mesh density: the mesher subdivisions along the longest bounding-box side. Polygon
# results reach machine precision well before this density, and denser meshes only cost
# calculation time.
MESH_DIVISOR = 10
MIN_MESH_SIZE_MM = 0.5


class InvalidSectionError(ValueError):
    """Raised when a section cannot be calculated because validation reported issues."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        codes = ", ".join(issue.code.value for issue in issues)
        super().__init__(f"invalid section: {codes}")
        self.issues = issues


@dataclass(frozen=True)
class SectionProperties:
    """Centroidal properties of one section."""

    area: float
    perimeter: float
    cx: float
    cy: float
    ix: float
    iy: float
    ixy: float
    i1: float
    i2: float
    principal_angle_deg: float
    rx: float
    ry: float
    r1: float
    r2: float
    sx: float
    sy: float
    x_min: float
    x_max: float
    y_min: float
    y_max: float


def calculate(section: Section) -> SectionProperties:
    """Mesh the section and return its centroidal properties in millimetres.

    Raises `InvalidSectionError` when validation blocks the calculation. Curved templates are
    calculated from closed forms (decision D1) instead of their display polygon.
    """
    issues = validate_section(section)
    if issues:
        raise InvalidSectionError(issues)

    if section.template is not None and section.template.kind in _CURVED_KINDS:
        return _calculate_curved(section)

    polygon = to_polygon(section)
    x_min, y_min, x_max, y_max = (float(value) for value in polygon.bounds)

    mesh_size = max(max(x_max - x_min, y_max - y_min) / MESH_DIVISOR, MIN_MESH_SIZE_MM)
    geometry = Geometry(geom=polygon)
    geometry.create_mesh(mesh_size)
    analysis = MeshAnalysis(geometry)
    analysis.calculate_geometric_properties()
    props = analysis.section_props

    area = float(props.area)
    ix = float(props.ixx_c)
    iy = float(props.iyy_c)
    ixy = float(props.ixy_c)
    cx = float(props.cx)
    cy = float(props.cy)

    return SectionProperties(
        area=area,
        perimeter=float(props.perimeter),
        cx=cx,
        cy=cy,
        ix=ix,
        iy=iy,
        ixy=ixy,
        i1=float(props.i11_c),
        i2=float(props.i22_c),
        # Principal axes are meaningful modulo 180 degrees; report the major axis within
        # (-90, 90] counter-clockwise from +x (spec S9, decision D4).
        principal_angle_deg=_normalize_angle(float(props.phi)),
        rx=math.sqrt(ix / area),
        ry=math.sqrt(iy / area),
        r1=math.sqrt(float(props.i11_c) / area),
        r2=math.sqrt(float(props.i22_c) / area),
        # Elastic moduli use the greatest centroidal fibre distance (decision D4).
        sx=ix / max(y_max - cy, cy - y_min),
        sy=iy / max(x_max - cx, cx - x_min),
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
    )


def _calculate_curved(section: Section) -> SectionProperties:
    """Closed-form properties of a circle or pipe, both centred on the origin (decision D1)."""
    template = section.template
    assert template is not None
    params = template.params
    diameter = params["d"]
    outer_area = math.pi * diameter**2 / 4
    outer_inertia = math.pi * diameter**4 / 64

    if template.kind == TemplateKind.PIPE.value:
        inner_diameter = diameter - 2 * params["t"]
        area = outer_area - math.pi * inner_diameter**2 / 4
        inertia = outer_inertia - math.pi * inner_diameter**4 / 64
    else:
        area = outer_area
        inertia = outer_inertia

    radius = diameter / 2
    gyration = math.sqrt(inertia / area)
    modulus = inertia / radius
    return SectionProperties(
        area=area,
        perimeter=math.pi * diameter,
        cx=0.0,
        cy=0.0,
        ix=inertia,
        iy=inertia,
        ixy=0.0,
        i1=inertia,
        i2=inertia,
        principal_angle_deg=0.0,
        rx=gyration,
        ry=gyration,
        r1=gyration,
        r2=gyration,
        sx=modulus,
        sy=modulus,
        x_min=-radius,
        x_max=radius,
        y_min=-radius,
        y_max=radius,
    )


def to_polygon(section: Section) -> Polygon:
    """Build the shapely polygon, counter-clockwise outer ring and inner ring as a hole."""
    outer = normalize_ccw(section.outer)
    shell = _ring_coordinates(outer)
    holes = [_ring_coordinates(normalize_ccw(section.inner))] if section.inner else None
    return Polygon(shell, holes)


def _ring_coordinates(contour: Contour) -> list[tuple[float, float]]:
    return [(point.x, point.y) for point in contour.points]


def _normalize_angle(angle_deg: float) -> float:
    """Fold an angle into (-90, 90], the range of one principal axis."""
    folded = (angle_deg + 90.0) % 180.0
    return folded - 90.0 if folded > 0.0 else 0.0
