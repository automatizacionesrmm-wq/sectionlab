"""Project files: `.sectionlab` JSON round trip (specs S2, S5, S10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sectionlab.core.document import (
    SCHEMA_VERSION,
    DocumentError,
    from_payload,
    load,
    save,
    to_payload,
)
from sectionlab.core.model import Contour, Point, Section, TemplateSpec
from sectionlab.core.templates import TemplateKind, build_section
from sectionlab.core.units import Unit


def free_section() -> Section:
    return Section(
        outer=Contour(
            points=[Point(0, 0), Point(120, 0), Point(120, 80), Point(0, 80)],
        )
    )


def test_payload_carries_the_schema_version_and_unit() -> None:
    payload = to_payload(free_section(), Unit.CM)
    assert payload["schema_version"] == SCHEMA_VERSION == 1
    assert payload["unit"] == "cm"


def test_free_geometry_round_trips_through_the_payload() -> None:
    section, unit, _ = from_payload(to_payload(free_section(), Unit.MM))
    assert unit is Unit.MM
    assert [(p.x, p.y) for p in section.outer.points] == [
        (0.0, 0.0),
        (120.0, 0.0),
        (120.0, 80.0),
        (0.0, 80.0),
    ]
    assert section.inner is None
    assert section.template is None


def test_open_contour_survives_the_round_trip() -> None:
    open_section = Section(
        outer=Contour(
            points=[Point(0, 0), Point(10, 0), Point(10, 10)],
            closed=False,
        )
    )
    section, _, _ = from_payload(to_payload(open_section, Unit.MM))
    assert section.outer.closed is False


def test_hollow_section_keeps_its_inner_contour() -> None:
    section = build_section(TemplateKind.RECT_HOLLOW)
    restored, _, _ = from_payload(to_payload(section, Unit.MM))
    assert restored.inner is not None
    assert [(p.x, p.y) for p in restored.inner.points] == [
        (p.x, p.y) for p in section.inner.points
    ]


def test_template_parameters_are_kept_for_further_editing() -> None:
    section = build_section(TemplateKind.I_PROFILE, {"h": 300.0})
    restored, _, _ = from_payload(to_payload(section, Unit.IN))
    assert restored.template == TemplateSpec(
        kind=TemplateKind.I_PROFILE.value,
        params=section.template.params,
    )


def test_coordinates_are_stored_in_millimetres_whatever_the_unit() -> None:
    payload = to_payload(free_section(), Unit.IN)
    outer = payload["geometry"]["outer"]
    assert outer["points"][2] == [120.0, 80.0]


def test_save_writes_utf8_json_with_a_trailing_newline(tmp_path: Path) -> None:
    target = tmp_path / "beam.sectionlab"
    save(target, free_section(), Unit.MM)
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text)["unit"] == "mm"


def test_save_and_load_round_trip_in_another_unit(tmp_path: Path) -> None:
    target = tmp_path / "beam.sectionlab"
    save(target, build_section(TemplateKind.PIPE), Unit.IN)
    section, unit, _ = load(target)
    assert unit is Unit.IN
    assert section.template is not None
    assert section.template.kind == TemplateKind.PIPE.value


def test_unsupported_schema_version_is_rejected() -> None:
    payload = to_payload(free_section(), Unit.MM)
    payload["schema_version"] = 99
    with pytest.raises(DocumentError) as error:
        from_payload(payload)
    assert error.value.code == "UNSUPPORTED_SCHEMA_VERSION"


def test_unknown_unit_is_rejected() -> None:
    payload = to_payload(free_section(), Unit.MM)
    payload["unit"] = "furlong"
    with pytest.raises(DocumentError) as error:
        from_payload(payload)
    assert error.value.code == "UNKNOWN_UNIT"


def test_missing_geometry_is_rejected() -> None:
    payload = {"schema_version": 1, "unit": "mm"}
    with pytest.raises(DocumentError) as error:
        from_payload(payload)
    assert error.value.code == "MISSING_GEOMETRY"


def test_malformed_vertex_is_rejected() -> None:
    payload = to_payload(free_section(), Unit.MM)
    payload["geometry"]["outer"]["points"] = [[0, 0], ["not a number", 1], [1, 1]]
    with pytest.raises(DocumentError) as error:
        from_payload(payload)
    assert error.value.code == "MALFORMED_POINT"


def test_malformed_json_file_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "broken.sectionlab"
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(DocumentError) as error:
        load(target)
    assert error.value.code == "MALFORMED_JSON"


# --- dimensions travel with the file (spec S10) -----------------------------------------

from sectionlab.core.dimensions import (  # noqa: E402
    ANCHOR_EDGE,
    ANCHOR_VERTEX,
    HORIZONTAL,
    SEGMENT_LENGTH,
    Anchor,
    Dimension,
)

PLACED = [
    Dimension(1, Anchor(ANCHOR_VERTEX, 0), Anchor(ANCHOR_VERTEX, 1), SEGMENT_LENGTH, 12.5),
    Dimension(2, Anchor(ANCHOR_EDGE, 1, 0.25), Anchor(ANCHOR_VERTEX, 3), HORIZONTAL, -4.0),
]


def test_dimensions_survive_the_round_trip() -> None:
    _, _, dimensions = from_payload(to_payload(free_section(), Unit.MM, PLACED))
    assert dimensions == PLACED


def test_a_file_without_the_key_loads_with_no_dimensions() -> None:
    payload = to_payload(free_section(), Unit.MM)
    assert "dimensions" not in payload["geometry"]
    _, _, dimensions = from_payload(payload)
    assert dimensions == []


def test_the_schema_version_does_not_change_so_older_builds_can_read_the_geometry() -> None:
    payload = to_payload(free_section(), Unit.MM, PLACED)
    assert payload["schema_version"] == 1


def test_saving_and_loading_a_file_keeps_its_dimensions(tmp_path) -> None:
    target = tmp_path / "placed.sectionlab"
    save(target, free_section(), Unit.MM, PLACED)
    _, _, dimensions = load(target)
    assert dimensions == PLACED


def _with_dimensions(entries: object) -> dict[str, object]:
    payload = to_payload(free_section(), Unit.MM)
    geometry = dict(payload["geometry"])
    geometry["dimensions"] = entries
    return {**payload, "geometry": geometry}


def test_a_dimension_block_that_is_not_a_list_is_refused() -> None:
    with pytest.raises(DocumentError) as refused:
        from_payload(_with_dimensions({"id": 1}))
    assert refused.value.code == "MALFORMED_DIMENSION"


@pytest.mark.parametrize(
    ("entry", "code"),
    [
        ({"id": 1, "kind": "arc", "first": {"kind": "vertex", "index": 0}, "second": {"kind": "vertex", "index": 1}, "offset_mm": 0.0}, "UNKNOWN_DIMENSION_KIND"),
        ({"id": 1, "kind": SEGMENT_LENGTH, "first": {"kind": "point", "index": 0}, "second": {"kind": "vertex", "index": 1}, "offset_mm": 0.0}, "UNKNOWN_ANCHOR_KIND"),
        ({"id": 1, "kind": SEGMENT_LENGTH, "first": {"kind": "vertex", "index": -2}, "second": {"kind": "vertex", "index": 1}, "offset_mm": 0.0}, "MALFORMED_DIMENSION"),
        ({"id": 1, "kind": SEGMENT_LENGTH, "first": {"kind": "edge", "index": 0, "t": 1.5}, "second": {"kind": "vertex", "index": 1}, "offset_mm": 0.0}, "MALFORMED_DIMENSION"),
        ({"id": 1, "kind": SEGMENT_LENGTH, "first": {"kind": "vertex", "index": 0}, "second": {"kind": "vertex", "index": 1}}, "MALFORMED_DIMENSION"),
        ({"kind": SEGMENT_LENGTH, "first": {"kind": "vertex", "index": 0}, "second": {"kind": "vertex", "index": 1}, "offset_mm": 0.0}, "MALFORMED_DIMENSION"),
        ("nope", "MALFORMED_DIMENSION"),
    ],
)
def test_a_malformed_dimension_entry_is_refused(entry, code: str) -> None:
    with pytest.raises(DocumentError) as refused:
        from_payload(_with_dimensions([entry]))
    assert refused.value.code == code
