"""Template panel commits immediately: a kind change or an edit redraws (spec S4)."""

from __future__ import annotations

import pytest

from sectionlab.core.templates import TemplateKind
from sectionlab.ui.template_panel import TemplatePanel


@pytest.fixture()
def panel(qtbot) -> TemplatePanel:
    widget = TemplatePanel()
    qtbot.addWidget(widget)
    return widget


def test_choosing_a_kind_emits_it_at_once(qtbot, panel: TemplatePanel) -> None:
    combo = panel._kind
    with qtbot.waitSignal(panel.applied, timeout=200) as blocker:
        combo.setCurrentIndex(combo.findData(TemplateKind.TRIANGLE.value))
    assert blocker.args[0] == TemplateKind.TRIANGLE.value


def test_editing_a_parameter_rebuilds_after_a_short_pause(qtbot, panel: TemplatePanel) -> None:
    with qtbot.waitSignal(panel.applied, timeout=600) as blocker:
        panel._spins["b"].setValue(150.0)
    assert blocker.args[1]["b"] == pytest.approx(150.0)


def test_rapid_edits_coalesce_into_one_rebuild(qtbot, panel: TemplatePanel) -> None:
    received: list[object] = []
    panel.applied.connect(lambda *args: received.append(args))
    for value in (110.0, 120.0, 130.0):
        panel._spins["b"].setValue(value)
    qtbot.wait(400)
    assert len(received) == 1
    assert received[0][1]["b"] == pytest.approx(130.0)


def test_programmatic_changes_do_not_rebuild_the_section(qtbot, panel: TemplatePanel) -> None:
    received: list[object] = []
    panel.applied.connect(lambda *args: received.append(args))
    panel.set_kind(TemplateKind.I_PROFILE.value)
    panel.set_params({"h": 220.0})
    qtbot.wait(200)
    assert received == []
