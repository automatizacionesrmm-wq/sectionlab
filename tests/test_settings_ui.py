"""Settings dialog, persisted preferences and template parameter form (S3, S4, S10)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from sectionlab.core.precision import DEFAULT_DECIMALS, MAX_DECIMALS, MIN_DECIMALS
from sectionlab.core.snap import SNAP_KINDS, SnapKind
from sectionlab.core.templates import TemplateKind, default_params
from sectionlab.core.units import Unit
from sectionlab.ui import strings, settings as settings_module
from sectionlab.ui.settings import AppSettings, SettingsDialog, load_settings, save_settings, unit_label
from sectionlab.ui.template_panel import TemplatePanel
from sectionlab.ui.theme import Theme


def test_default_settings() -> None:
    settings = AppSettings()
    assert settings.unit is Unit.MM
    assert settings.decimals == DEFAULT_DECIMALS == 2


def test_unit_symbols() -> None:
    assert unit_label(Unit.MM) == "mm"
    assert unit_label(Unit.IN) == "in"


@pytest.fixture()
def isolated_store(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings_module, "ORGANIZATION", "SectionLabTests")
    monkeypatch.setattr(settings_module, "APPLICATION", "isolated")
    store = QSettings("SectionLabTests", "isolated")
    store.clear()


def test_settings_round_trip_through_qsettings(isolated_store) -> None:
    saved = AppSettings(unit=Unit.IN, decimals=4)
    save_settings(saved)
    assert load_settings() == saved


def test_out_of_range_decimals_are_clamped_on_load(isolated_store) -> None:
    store = QSettings(settings_module.ORGANIZATION, settings_module.APPLICATION)
    store.setValue("decimals", 99)
    loaded = load_settings()
    assert loaded.decimals == MAX_DECIMALS


def test_dialog_starts_from_the_given_settings(qtbot) -> None:
    dialog = SettingsDialog(AppSettings(unit=Unit.CM, decimals=1))
    qtbot.addWidget(dialog)
    values = dialog.values()
    assert values.unit is Unit.CM
    assert values.decimals == 1


def test_dialog_returns_the_chosen_values(qtbot) -> None:
    dialog = SettingsDialog(AppSettings())
    qtbot.addWidget(dialog)
    dialog._unit.setCurrentIndex(dialog._unit.findData(Unit.M.value))
    dialog._decimals.setValue(MIN_DECIMALS + 5)
    values = dialog.values()
    assert values.unit is Unit.M
    assert values.decimals == MIN_DECIMALS + 5


@pytest.fixture()
def panel(qtbot) -> TemplatePanel:
    widget = TemplatePanel()
    qtbot.addWidget(widget)
    return widget


def test_panel_lists_every_template(panel: TemplatePanel) -> None:
    assert panel._kind.count() == len(TemplateKind)
    assert panel._kind.itemText(0) == strings.label_for(TemplateKind.RECTANGLE.value)


def test_panel_shows_default_parameters_in_millimetres(panel: TemplatePanel) -> None:
    assert panel.params() == default_params(TemplateKind.RECTANGLE)


def test_changing_template_rebuilds_the_form(panel: TemplatePanel) -> None:
    panel.set_kind(TemplateKind.I_PROFILE.value)
    assert set(panel.params()) == {"h", "b", "tw", "tf"}


def test_parameters_are_shown_in_the_active_unit(panel: TemplatePanel) -> None:
    panel.set_unit(Unit.CM)
    assert panel._spins["b"].value() == pytest.approx(10.0)
    assert panel.params() == pytest.approx({"b": 100.0, "h": 200.0})


def test_unit_change_preserves_the_millimetre_value(panel: TemplatePanel) -> None:
    panel.set_unit(Unit.CM)
    assert panel.params() == pytest.approx(default_params(TemplateKind.RECTANGLE))
    panel.set_unit(Unit.IN)
    assert panel.params() == pytest.approx(default_params(TemplateKind.RECTANGLE))


def test_applying_emits_the_kind_and_millimetre_parameters(qtbot, panel: TemplatePanel) -> None:
    with qtbot.waitSignal(panel.applied, timeout=200) as blocker:
        panel._apply.click()
    assert blocker.args[0] == TemplateKind.RECTANGLE.value
    assert blocker.args[1] == default_params(TemplateKind.RECTANGLE)


def test_setting_parameters_shows_them_in_the_active_unit(panel: TemplatePanel) -> None:
    panel.set_kind(TemplateKind.RECT_HOLLOW.value)
    panel.set_unit(Unit.CM)
    panel.set_params({"b": 150.0, "h": 200.0, "t": 6.0})
    assert panel.params()["b"] == pytest.approx(150.0)


def test_free_geometry_mode_is_requested(qtbot, panel: TemplatePanel) -> None:
    with qtbot.waitSignal(panel.freeModeRequested, timeout=200):
        panel._free.click()


def test_the_theme_round_trips_through_qsettings(isolated_store) -> None:
    saved = AppSettings(unit=Unit.MM, decimals=2, theme=Theme.LIGHT)
    save_settings(saved)
    assert load_settings() == saved


def test_an_unknown_stored_theme_falls_back_to_dark(isolated_store) -> None:
    store = QSettings("SectionLabTests", "isolated")
    store.setValue("theme", "solarized")
    store.sync()
    assert load_settings().theme is Theme.DARK


def test_the_dialog_reports_the_chosen_theme() -> None:
    dialog = SettingsDialog(AppSettings(theme=Theme.LIGHT))
    assert dialog.values().theme is Theme.LIGHT
    index = dialog._theme.findData(Theme.DARK.value)
    dialog._theme.setCurrentIndex(index)
    assert dialog.values().theme is Theme.DARK


def test_the_settings_dialog_shows_the_running_version(qtbot) -> None:
    from sectionlab import __version__
    from PySide6.QtWidgets import QLabel

    dialog = SettingsDialog(AppSettings())
    qtbot.addWidget(dialog)
    label = dialog.findChild(QLabel, "settings_version")
    assert label is not None
    assert label.text() == f"{strings.label_for('version_label')} {__version__}"


def test_snaps_are_all_on_until_the_user_turns_one_off(isolated_store) -> None:
    assert load_settings().snaps == SNAP_KINDS


def test_snap_state_survives_a_round_trip(isolated_store) -> None:
    saved = AppSettings(snaps=(SnapKind.ENDPOINT, SnapKind.CENTER))
    save_settings(saved)
    assert load_settings().snaps == (SnapKind.ENDPOINT, SnapKind.CENTER)


def test_turning_every_snap_off_is_remembered_and_not_reset(isolated_store) -> None:
    save_settings(AppSettings(snaps=()))
    assert load_settings().snaps == ()


def test_unknown_snap_names_are_ignored_and_order_is_canonical(isolated_store) -> None:
    store = QSettings(settings_module.ORGANIZATION, settings_module.APPLICATION)
    store.setValue("snaps", "PERPENDICULAR,NONSENSE,ENDPOINT")
    assert load_settings().snaps == (SnapKind.ENDPOINT, SnapKind.PERPENDICULAR)


def test_the_settings_dialog_keeps_the_snap_choice(qtbot) -> None:
    dialog = SettingsDialog(AppSettings(snaps=(SnapKind.MIDPOINT,)))
    qtbot.addWidget(dialog)
    assert dialog.values().snaps == (SnapKind.MIDPOINT,)
