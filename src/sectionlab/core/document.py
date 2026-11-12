"""`.sectionlab` project files: one section per file, JSON, schema versioned.

Coordinates and template parameters are always written in millimetres (spec S2, S10); the
documented unit is saved so reopening shows the same numbers the user was working with.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from sectionlab.core.dimensions import (
    ANCHOR_EDGE,
    ANCHOR_VERTEX,
    HORIZONTAL,
    SEGMENT_LENGTH,
    VERTICAL,
    Anchor,
    Dimension,
)
from sectionlab.core.model import Contour, Point, Section, TemplateSpec
from sectionlab.core.units import Unit

SCHEMA_VERSION = 1
FILE_EXTENSION = ".sectionlab"

DIMENSION_KINDS = (SEGMENT_LENGTH, HORIZONTAL, VERTICAL)
ANCHOR_KINDS = (ANCHOR_VERTEX, ANCHOR_EDGE)


class DocumentError(ValueError):
    """Raised when a project file cannot be read; the code is stable English text."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def to_payload(
    section: Section, unit: Unit, dimensions: Sequence[Dimension] = ()
) -> dict[str, object]:
    """Serialize a section, the active unit and its dimensions into a JSON-ready payload.

    Dimensions are written under an optional key so a file without them stays readable both
    ways: older builds ignore it and newer builds treat its absence as "no dimensions". That
    is why the schema version does not change.
    """
    geometry: dict[str, object] = {
        "outer": _contour_payload(section.outer),
        "inner": _contour_payload(section.inner) if section.inner is not None else None,
        "template": (
            {"kind": section.template.kind, "params": dict(section.template.params)}
            if section.template is not None
            else None
        ),
    }
    if dimensions:
        geometry["dimensions"] = [_dimension_payload(item) for item in dimensions]
    return {
        "schema_version": SCHEMA_VERSION,
        "unit": unit.value,
        "geometry": geometry,
    }


def from_payload(payload: Mapping[str, object]) -> tuple[Section, Unit, list[Dimension]]:
    """Rebuild a section, its unit and its dimensions, rejecting unknown schemas."""
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise DocumentError(
            "UNSUPPORTED_SCHEMA_VERSION",
            f"expected {SCHEMA_VERSION}, found {version!r}",
        )

    unit_text = payload.get("unit")
    try:
        unit = Unit(unit_text)
    except ValueError as error:
        raise DocumentError("UNKNOWN_UNIT", f"unknown unit {unit_text!r}") from error

    geometry = payload.get("geometry")
    if not isinstance(geometry, Mapping):
        raise DocumentError("MISSING_GEOMETRY", "the geometry block is missing")

    outer = _contour_from(geometry.get("outer"), "outer")
    inner_payload = geometry.get("inner")
    inner = _contour_from(inner_payload, "inner") if inner_payload is not None else None

    template = _template_from(geometry.get("template"))
    dimensions = _dimensions_from(geometry.get("dimensions"))
    return Section(outer=outer, inner=inner, template=template), unit, dimensions


def save(
    path: str | Path, section: Section, unit: Unit, dimensions: Sequence[Dimension] = ()
) -> None:
    """Write the section to `path` as UTF-8 JSON with a trailing newline."""
    text = json.dumps(to_payload(section, unit, dimensions), indent=2, ensure_ascii=False)
    Path(path).write_text(text + "\n", encoding="utf-8")


def load(path: str | Path) -> tuple[Section, Unit, list[Dimension]]:
    """Read a project file written by `save`, raising `DocumentError` when it is unusable."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise DocumentError("MALFORMED_JSON", str(error)) from error
    if not isinstance(payload, Mapping):
        raise DocumentError("MALFORMED_JSON", "the file does not contain an object")
    return from_payload(payload)


def _contour_payload(contour: Contour) -> dict[str, object]:
    return {
        "closed": contour.closed,
        "points": [[point.x, point.y] for point in contour.points],
    }


def _contour_from(payload: object, name: str) -> Contour:
    if not isinstance(payload, Mapping):
        raise DocumentError("MISSING_GEOMETRY", f"the {name} contour is missing")

    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        raise DocumentError("MISSING_GEOMETRY", f"the {name} contour has no points")

    points: list[Point] = []
    for raw in raw_points:
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise DocumentError("MALFORMED_POINT", f"the {name} contour has a bad vertex")
        try:
            points.append(Point(float(raw[0]), float(raw[1])))
        except (TypeError, ValueError) as error:
            raise DocumentError("MALFORMED_POINT", f"the {name} contour has a bad vertex") from error

    return Contour(points=points, closed=bool(payload.get("closed", True)))


def _template_from(payload: object) -> TemplateSpec | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise DocumentError("MALFORMED_TEMPLATE", "the template block is not an object")

    kind = payload.get("kind")
    if not isinstance(kind, str):
        raise DocumentError("MALFORMED_TEMPLATE", "the template has no kind")

    raw_params = payload.get("params", {})
    if not isinstance(raw_params, Mapping):
        raise DocumentError("MALFORMED_TEMPLATE", "the template parameters are not an object")

    params: dict[str, float] = {}
    for key, value in raw_params.items():
        try:
            params[str(key)] = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as error:
            raise DocumentError("MALFORMED_TEMPLATE", f"bad template parameter {key!r}") from error
    return TemplateSpec(kind=kind, params=params)


def _dimension_payload(dimension: Dimension) -> dict[str, object]:
    return {
        "id": dimension.id,
        "kind": dimension.kind,
        "offset_mm": dimension.offset_mm,
        "first": _anchor_payload(dimension.first),
        "second": _anchor_payload(dimension.second),
    }


def _anchor_payload(anchor: Anchor) -> dict[str, object]:
    return {"kind": anchor.kind, "index": anchor.index, "t": anchor.t}


def _dimensions_from(payload: object) -> list[Dimension]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise DocumentError("MALFORMED_DIMENSION", "the dimensions block is not a list")
    return [_dimension_from(entry) for entry in payload]


def _dimension_from(entry: object) -> Dimension:
    if not isinstance(entry, Mapping):
        raise DocumentError("MALFORMED_DIMENSION", "a dimension is not an object")

    identifier = entry.get("id")
    if not isinstance(identifier, int) or isinstance(identifier, bool):
        raise DocumentError("MALFORMED_DIMENSION", "a dimension has no numeric id")

    kind = entry.get("kind")
    if kind not in DIMENSION_KINDS:
        raise DocumentError("UNKNOWN_DIMENSION_KIND", f"unknown dimension kind {kind!r}")

    offset = entry.get("offset_mm")
    if not isinstance(offset, (int, float)) or isinstance(offset, bool):
        raise DocumentError("MALFORMED_DIMENSION", "a dimension has no numeric offset")

    return Dimension(
        id=identifier,
        first=_anchor_from(entry.get("first")),
        second=_anchor_from(entry.get("second")),
        kind=str(kind),
        offset_mm=float(offset),
    )


def _anchor_from(payload: object) -> Anchor:
    if not isinstance(payload, Mapping):
        raise DocumentError("MALFORMED_DIMENSION", "an anchor is not an object")

    kind = payload.get("kind")
    if kind not in ANCHOR_KINDS:
        raise DocumentError("UNKNOWN_ANCHOR_KIND", f"unknown anchor kind {kind!r}")

    index = payload.get("index")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise DocumentError("MALFORMED_DIMENSION", "an anchor has no usable index")

    t = payload.get("t", 0.0)
    if not isinstance(t, (int, float)) or isinstance(t, bool) or not 0.0 <= float(t) <= 1.0:
        raise DocumentError("MALFORMED_DIMENSION", "an anchor parameter is outside 0..1")

    return Anchor(kind=str(kind), index=index, t=float(t))
