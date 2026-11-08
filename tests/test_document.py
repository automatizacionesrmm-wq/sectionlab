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
    section, unit = from_payload(to_payload(free_section(), Unit.MM))
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
    section, _ = from_payload(to_payload(open_section, Unit.MM))
    assert section.outer.closed is False


def test_hollow_section_keeps_its_inner_contour() -> None:
    section = build_section(TemplateKind.RECT_HOLLOW)
    restored, _ = from_payload(to_payload(section, Unit.MM))
    assert restored.inner is not None
    assert [(p.x, p.y) for p in restored.inner.points] == [
        (p.x, p.y) for p in section.inner.points
    ]


def test_template_parameters_are_kept_for_further_editing() -> None:
    section = build_section(TemplateKind.I_PROFILE, {"h": 300.0})
    restored, _ = from_payload(to_payload(section, Unit.IN))
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
    section, unit = load(target)
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
