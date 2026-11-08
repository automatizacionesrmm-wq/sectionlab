"""The UI text module covers every code and label the interface can show (S16, D6)."""

from __future__ import annotations

import pytest

from sectionlab.core.engine import SectionProperties
from sectionlab.core.templates import TemplateKind, TemplateParameterError, parameters
from sectionlab.core.validation import IssueCode
from sectionlab.ui import strings


def test_every_validation_code_has_a_spanish_message() -> None:
    for code in IssueCode:
        assert strings.message_for(code.value).strip()


def test_unknown_validation_code_raises() -> None:
    with pytest.raises(KeyError):
        strings.message_for("NOT_A_CODE")


def test_every_template_kind_has_a_label() -> None:
    for kind in TemplateKind:
        assert strings.label_for(kind.value).strip()


def test_every_template_parameter_has_a_label() -> None:
    keys = {param.key for kind in TemplateKind for param in parameters(kind)}
    for key in keys:
        assert strings.label_for(key).strip()


def test_every_result_field_has_a_label_and_unit() -> None:
    for field in SectionProperties.__dataclass_fields__:
        label, unit = strings.result_label(field)
        assert label.strip()
        assert unit in {"mm", "mm²", "mm³", "mm⁴", "°"}


def test_unknown_result_field_raises() -> None:
    with pytest.raises(KeyError):
        strings.result_label("j")


def test_main_window_keys_are_spanish_and_not_empty() -> None:
    for key, text in strings.UI.items():
        assert text.strip(), key
        assert text != key, f"{key} was not translated"


def test_every_parameter_error_code_has_a_message() -> None:
    codes = {
        "PARAMETER_NOT_POSITIVE",
        "SIDES_BELOW_THREE",
        "WALL_NOT_THINNER_THAN_OUTER",
        "WALL_NOT_THINNER_THAN_RADIUS",
        "FLANGE_TOO_THICK",
        "WEB_TOO_WIDE",
        "LEG_NOT_THINNER_THAN_OUTER",
    }
    assert codes <= set(strings.PARAMETER_ERROR_MESSAGES)
    for code in codes:
        assert strings.error_message(code).strip()


def test_every_document_error_code_has_a_message() -> None:
    codes = {
        "UNSUPPORTED_SCHEMA_VERSION",
        "UNKNOWN_UNIT",
        "MISSING_GEOMETRY",
        "MALFORMED_POINT",
        "MALFORMED_TEMPLATE",
        "MALFORMED_JSON",
    }
    assert codes <= set(strings.DOCUMENT_ERROR_MESSAGES)


def test_unknown_error_code_falls_back_instead_of_crashing() -> None:
    assert strings.error_message("SOMETHING_NEW").strip()


def test_parameter_error_codes_match_the_core_module() -> None:
    with pytest.raises(TemplateParameterError) as error:
        from sectionlab.core.templates import build_section

        build_section(TemplateKind.POLYGON, {"n": 1})
    assert error.value.code in strings.PARAMETER_ERROR_MESSAGES
