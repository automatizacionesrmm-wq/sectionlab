"""Main window: canvas, template panel, vertex list, results and the calculate flow.

The window owns the interaction state: which unit and how many decimals are shown, whether
the geometry comes from a template or from free drawing, and the last calculated results.
Validation blocks calculation with Spanish messages (spec S13, S15, D6).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QDockWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sectionlab.core.document import (
    FILE_EXTENSION,
    DocumentError,
    load,
    save,
)
from sectionlab.core.engine import InvalidSectionError, SectionProperties, calculate
from sectionlab.core.model import Contour, Section
from sectionlab.core.templates import TemplateKind, TemplateParameterError, build_section
from sectionlab.core.units import Unit
from sectionlab.core.validation import ValidationIssue, validate_section
from sectionlab.ui import strings
from sectionlab.ui.canvas import INNER, OUTER, CanvasView
from sectionlab.ui.icons import icon
from sectionlab.ui.results import ResultsTable, format_length
from sectionlab.ui.settings import (
    AppSettings,
    SettingsDialog,
    load_settings,
    save_settings,
    unit_label,
)
from sectionlab.ui.template_panel import TemplatePanel
from sectionlab.ui.theme import Theme, apply_theme, tokens
from sectionlab.ui.vertex_table import VertexTable

APP_NAME = strings.UI["window_title"]
FILE_FILTER = f"SectionLab (*{FILE_EXTENSION})"
CSV_FILTER = "CSV (*.csv)"
PANEL_WIDTH = 360
PANEL_MIN_WIDTH = 240


class MainWindow(QMainWindow):
    """One section per window, with the drawing on the left and its data on the right."""

    def __init__(self, settings: AppSettings | None = None, *, interactive: bool = True) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)

        self._interactive = interactive
        self._settings = settings or load_settings()
        self._unit = self._settings.unit
        self._decimals = self._settings.decimals
        self._theme = self._settings.theme
        self._props: SectionProperties | None = None
        self._path: Path | None = None
        self._last_error: str | None = None
        self._template_kind: str | None = None
        self._icon_targets: list[tuple[QAction, str]] = []
        self._glyphs: list[tuple[QLabel, str]] = []
        self._docks: list[QDockWidget] = []
        self._panel_actions: list[QAction] = []
        self._dock_closers: list[QToolButton] = []

        self.canvas = CanvasView(self)
        self.template_panel = TemplatePanel(self)
        self.vertex_table = VertexTable(self)
        self.results_table = ResultsTable(self)

        self._cursor_label = QLabel(self)
        self._snap_label = QLabel(self)
        self._unit_label = QLabel(self)
        self._nav_label = QLabel(strings.label_for("hint_navigate"), self)
        self._message_label = QLabel(self)
        for label in (self._cursor_label, self._snap_label, self._unit_label, self._message_label):
            label.setObjectName("status")
            self.statusBar().addWidget(label)
        self._nav_label.setObjectName("status")
        self._panels_hint = QLabel(strings.label_for("panels_hidden_hint"), self)
        self._panels_hint.setObjectName("panels_hint")
        self._panels_hint.hide()
        self.statusBar().addPermanentWidget(self._panels_hint)
        self.statusBar().addPermanentWidget(self._nav_label)
        self.statusBar().addPermanentWidget(self._message_label)

        self._build_layout()
        self._build_actions()
        self._decorate_toolbar()
        self._apply_theme()

        self.canvas.sectionChanged.connect(self._on_section_changed)
        self.canvas.cursorMoved.connect(self._on_cursor_moved)
        self.canvas.snapChanged.connect(self._on_snap_changed)
        self.canvas.vertexSelected.connect(self._on_vertex_selected)
        self.canvas.drawingChanged.connect(self._on_drawing_changed)
        self.template_panel.applied.connect(self.apply_template)
        self.template_panel.freeModeRequested.connect(self.start_free_geometry)
        self.vertex_table.vertexEdited.connect(self.canvas.move_vertex)
        self.vertex_table.vertexActivated.connect(self.canvas.select_vertex)

        self._sync_undo_actions()
        self._refresh_displays()
        self._message_label.setText(strings.label_for("ready"))

    # ------------------------------------------------------------------ construction

    def _build_layout(self) -> None:
        """Give the drawing every pixel, and let each inspector dock float or move."""
        self.setCentralWidget(self.canvas)
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )
        specs = (
            ("template", strings.label_for("template_mode"), "template", self.template_panel, 230),
            ("vertices", strings.label_for("vertex_table"), "vertex", self.vertex_table, 340),
            ("results", strings.label_for("results"), "calculate", self.results_table, 300),
        )
        previous: QDockWidget | None = None
        for name, title, glyph, content, _height in specs:
            dock = self._dock(name, title, glyph, content)
            if previous is None:
                self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            else:
                self.splitDockWidget(previous, dock, Qt.Orientation.Vertical)
            previous = dock
        self.resizeDocks(self._docks, [PANEL_WIDTH] * len(self._docks), Qt.Orientation.Horizontal)
        self.resizeDocks(self._docks, [spec[4] for spec in specs], Qt.Orientation.Vertical)

    def _dock(self, name: str, title: str, glyph: str, content: QWidget) -> QDockWidget:
        """A movable, floatable, resizable inspector holding one panel."""
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock_{name}")
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        dock.setMinimumWidth(PANEL_MIN_WIDTH)
        dock.setTitleBarWidget(self._panel_header(dock, title, glyph))
        dock.setWidget(self._panel_body(dock, content))
        dock.visibilityChanged.connect(self._sync_panels_action)
        self._docks.append(dock)
        # Qt keeps this checkable action in step with the dock, which is what lets the
        # Paneles submenu reopen one panel the user closed with its own close button.
        self._panel_actions.append(dock.toggleViewAction())
        return dock

    def _panel_header(self, dock: QDockWidget, title: str, glyph: str) -> QWidget:
        header = QWidget(dock)
        header.setObjectName("panel_header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 6, 6, 6)
        layout.setSpacing(7)
        mark = QLabel(header)
        layout.addWidget(mark)
        caption = QLabel(title.upper(), header)
        caption.setObjectName("panel_title")
        layout.addWidget(caption)
        layout.addStretch(1)
        closer = QToolButton(header)
        closer.setObjectName("dock_close")
        closer.setAutoRaise(True)
        closer.setIconSize(QSize(14, 14))
        closer.setFixedSize(20, 20)
        closer.setCursor(Qt.CursorShape.PointingHandCursor)
        closer.setToolTip(strings.label_for("hide_panel"))
        closer.clicked.connect(dock.hide)
        layout.addWidget(closer)
        self._glyphs.append((mark, glyph))
        self._dock_closers.append(closer)
        return header

    def _panel_body(self, dock: QDockWidget, content: QWidget) -> QFrame:
        """The framed card below a dock's title bar."""
        frame = QFrame(dock)
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        content.setParent(frame)
        layout.addWidget(content)
        return frame

    def panels_visible(self) -> bool:
        """True when at least one inspector is on screen."""
        return any(not dock.isHidden() for dock in self._docks)

    def all_panels_visible(self) -> bool:
        return all(not dock.isHidden() for dock in self._docks)

    def set_panels_visible(self, visible: bool) -> None:
        """Show or hide every inspector at once, leaving the drawing alone on screen."""
        for dock in self._docks:
            dock.setVisible(visible)
        if hasattr(self, "action_panels"):
            self.action_panels.blockSignals(True)
            self.action_panels.setChecked(visible)
            self.action_panels.blockSignals(False)
        self._sync_panels_action()

    def _sync_panels_action(self, *_args: object) -> None:
        """Keep F9 and the status hint honest about what is on screen."""
        if hasattr(self, "action_panels"):
            # Checked only when every inspector is up, so one F9 press restores the rest
            # instead of hiding what is left.
            self.action_panels.blockSignals(True)
            self.action_panels.setChecked(self.all_panels_visible())
            self.action_panels.blockSignals(False)
        if hasattr(self, "_panels_hint"):
            nothing_shown = not self.panels_visible()
            self._panels_hint.setVisible(nothing_shown)

    def _build_actions(self) -> None:
        toolbar = self.addToolBar(strings.label_for("main_toolbar"))
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)

        self.action_calculate = QAction(strings.label_for("calculate"), self)
        self.action_calculate.setShortcut(QKeySequence("Ctrl+Return"))
        self.action_calculate.triggered.connect(self.calculate_now)

        self.action_open = QAction(strings.label_for("open"), self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self.open_document_dialog)

        self.action_save = QAction(strings.label_for("save"), self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self.save_document_dialog)

        self.action_export = QAction(strings.label_for("export_csv"), self)
        self.action_export.triggered.connect(self.export_csv_dialog)

        self.action_undo = self.canvas.undo_stack().createUndoAction(self, strings.label_for("undo"))
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.action_redo = self.canvas.undo_stack().createRedoAction(self, strings.label_for("redo"))
        self.action_redo.setShortcut(QKeySequence.StandardKey.Redo)

        self.action_delete_vertex = QAction(strings.label_for("delete_vertex"), self)
        self.action_delete_vertex.setShortcut(QKeySequence("Delete"))
        self.action_delete_vertex.triggered.connect(self.delete_selected_vertex)

        self.action_insert_vertex = QAction(strings.label_for("add_vertex"), self)
        self.action_insert_vertex.triggered.connect(self.insert_vertex)

        self.action_ortho = QAction(strings.label_for("ortho"), self)
        self.action_ortho.setCheckable(True)
        self.action_ortho.setShortcut(QKeySequence("F8"))
        self.action_ortho.toggled.connect(self.canvas.set_ortho)
        self.canvas.set_ortho(False)

        self.action_dimensions = QAction(strings.label_for("dimensions"), self)
        self.action_dimensions.setCheckable(True)
        self.action_dimensions.setChecked(True)
        self.action_dimensions.setShortcut(QKeySequence("Ctrl+D"))
        self.action_dimensions.setStatusTip(strings.label_for("dimensions_tip"))
        self.action_dimensions.toggled.connect(self.set_dimensions_visible)

        self.action_zoom_in = QAction(strings.label_for("zoom_in"), self)
        self.action_zoom_in.setShortcut(QKeySequence("Ctrl++"))
        self.action_zoom_in.triggered.connect(self.canvas.zoom_in)
        self.action_zoom_out = QAction(strings.label_for("zoom_out"), self)
        self.action_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.action_zoom_out.triggered.connect(self.canvas.zoom_out)
        self.action_fit = QAction(strings.label_for("zoom_fit"), self)
        self.action_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.action_fit.triggered.connect(self.canvas.fit_to_content)

        self.action_theme = QAction(strings.label_for("theme"), self)
        self.action_theme.setShortcut(QKeySequence("Ctrl+Shift+T"))
        self.action_theme.triggered.connect(self.toggle_theme)

        self.action_panels = QAction(strings.label_for("panels_all"), self)
        self.action_panels.setCheckable(True)
        self.action_panels.setChecked(True)
        self.action_panels.setShortcut(QKeySequence("F9"))
        self.action_panels.setStatusTip(strings.label_for("panels_tip"))
        self.action_panels.toggled.connect(self.set_panels_visible)

        self.action_settings = QAction(strings.label_for("settings"), self)
        self.action_settings.triggered.connect(self.open_settings_dialog)

        file_menu = self.menuBar().addMenu(strings.label_for("menu_file"))
        for action in (self.action_open, self.action_save, self.action_export):
            file_menu.addAction(action)
        file_menu.addSeparator()
        quit_action = QAction(strings.label_for("quit"), self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = self.menuBar().addMenu(strings.label_for("menu_edit"))
        for action in (self.action_undo, self.action_redo):
            edit_menu.addAction(action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_insert_vertex)
        edit_menu.addAction(self.action_delete_vertex)

        view_menu = self.menuBar().addMenu(strings.label_for("menu_view"))
        for action in (self.action_zoom_in, self.action_zoom_out, self.action_fit):
            view_menu.addAction(action)
        view_menu.addSeparator()
        view_menu.addAction(self.action_ortho)
        view_menu.addAction(self.action_dimensions)
        view_menu.addAction(self.action_theme)

        # A closed panel must always be findable again: one entry per inspector, kept in
        # sync by Qt, plus the F9 shortcut that brings all of them back.
        panels_menu = view_menu.addMenu(strings.label_for("panels"))
        panels_menu.addAction(self.action_panels)
        panels_menu.addSeparator()
        for action in self._panel_actions:
            panels_menu.addAction(action)

        settings_menu = self.menuBar().addMenu(strings.label_for("menu_settings"))
        settings_menu.addAction(self.action_settings)

    def _decorate_toolbar(self) -> None:
        """Replace the flat toolbar with icon groups and a primary calculate button."""
        toolbar = self.findChild(QToolBar, "main_toolbar")
        if toolbar is None:
            return
        pairs = [
            (self.action_calculate, "calculate"),
            (self.action_open, "open"),
            (self.action_save, "save"),
            (self.action_export, "csv"),
            (self.action_undo, "undo"),
            (self.action_redo, "redo"),
            (self.action_insert_vertex, "insert"),
            (self.action_delete_vertex, "delete"),
            (self.action_ortho, "ortho"),
            (self.action_zoom_in, "zoom_in"),
            (self.action_zoom_out, "zoom_out"),
            (self.action_fit, "fit"),
            (self.action_theme, "theme"),
            (self.action_settings, "settings"),
        ]
        self._icon_targets = list(pairs)
        for action in list(toolbar.actions()):
            toolbar.removeAction(action)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setMovable(False)
        groups = (pairs[0:1], pairs[1:4], pairs[4:6], pairs[6:9], pairs[9:12], pairs[12:14])
        for index, group in enumerate(groups):
            if index:
                toolbar.addSeparator()
            for action, _ in group:
                toolbar.addAction(action)
        button = toolbar.widgetForAction(self.action_calculate)
        if isinstance(button, QToolButton):
            button.setObjectName("primary")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setMinimumWidth(128)
            button.style().unpolish(button)
            button.style().polish(button)

    # ------------------------------------------------------------------ theme

    def current_theme(self) -> Theme:
        return self._theme

    def toggle_theme(self) -> None:
        """Swap the dark and light surfaces."""
        self.set_theme(Theme.LIGHT if self._theme is Theme.DARK else Theme.DARK)

    def set_theme(self, theme: Theme | str) -> None:
        self._theme = Theme(theme)
        self._apply_theme()
        if self._interactive:
            self._settings = replace(self._settings, theme=self._theme)
            save_settings(self._settings)

    def _apply_theme(self) -> None:
        apply_theme(self, self._theme)
        self.canvas.apply_palette(tokens(self._theme))
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        palette = tokens(self._theme)
        for action, name in self._icon_targets:
            colour = palette["accent_text"] if name == "calculate" else palette["text_dim"]
            glyph = name
            if name == "theme":
                glyph = "light" if self._theme is Theme.DARK else "moon"
            action.setIcon(icon(glyph, colour, 20))
            action.setIconText(strings.label_for(f"short_{name}"))
        for label, name in self._glyphs:
            label.setPixmap(icon(name, palette["text_faint"], 13).pixmap(13, 13))
        for closer in self._dock_closers:
            closer.setIcon(icon("close", palette["text_faint"], 14))

    # ------------------------------------------------------------------ public state

    def section(self) -> Section:
        return self.canvas.section()

    def properties(self) -> SectionProperties | None:
        return self._props

    def current_unit(self) -> Unit:
        return self._unit

    def current_decimals(self) -> int:
        return self._decimals

    def last_error(self) -> str | None:
        return self._last_error

    def document_path(self) -> Path | None:
        return self._path

    # ------------------------------------------------------------------ interactions

    def apply_template(self, kind: str, params: Mapping[str, float] | None = None) -> bool:
        """Build the chosen template in millimetres and show it read-only."""
        try:
            section = build_section(TemplateKind(kind), dict(params or {}))
        except (TemplateParameterError, ValueError) as error:
            code = getattr(error, "code", "")
            self._report_error(strings.error_message(code) if code else str(error))
            return False
        refit = self._template_kind != kind
        self.canvas.set_section(section)
        self.canvas.set_editable(False)
        if refit:
            self.canvas.fit_to_content()
        self._template_kind = kind
        self.template_panel.set_kind(kind)
        self._path = None
        self._set_message(f"{strings.label_for("applied")}: {strings.label_for(kind)}")
        self._last_error = None
        return True

    def start_free_geometry(self) -> None:
        """Discard the current geometry and start an empty free drawing (spec S10)."""
        self.canvas.set_section(Section(outer=Contour(points=[])))
        self.canvas.set_editable(True)
        self.canvas.reset_view()
        self.canvas.begin_drawing()
        self._template_kind = None
        self._path = None
        self._props = None
        self._set_message(strings.label_for("free_started"))

    def insert_vertex(self) -> None:
        if not self.canvas.is_editable():
            return
        points = self.canvas.section().outer.points
        if points:
            last = points[-1]
            self.canvas.add_vertex(last.x + 10.0, last.y)
        else:
            self.canvas.begin_drawing()

    def delete_selected_vertex(self) -> None:
        selected = self.canvas.selected_vertex()
        if selected is None or not self.canvas.is_editable():
            return
        self.canvas.delete_vertex(*selected)
        self.canvas.clear_selection()

    def validation_message(self) -> str | None:
        """Spanish explanation of why the section cannot be calculated, or None."""
        issues = validate_section(self.canvas.section())
        if not issues:
            return None
        return _issues_text(issues)

    def calculate_now(self) -> bool:
        """Validate, calculate and show the results; returns False when blocked."""
        missing = self.validation_message()
        if missing is not None:
            self._block_calculation(missing)
            return False
        try:
            props = calculate(self.canvas.section())
        except InvalidSectionError as error:  # defence in depth: same rules as validate
            self._block_calculation(_issues_text(error.issues))
            return False

        self._props = props
        self._last_error = None
        self.canvas.set_centroid(props.cx, props.cy, angle_deg=props.principal_angle_deg)
        self._refresh_displays()
        self._set_message(strings.label_for("calculated"))
        return True

    def set_unit(self, unit: Unit) -> None:
        """Change the active unit; geometry is untouched, only the display converts."""
        self._unit = Unit(unit)
        self.template_panel.set_unit(self._unit)
        self._refresh_displays()

    def set_decimals(self, decimals: int) -> None:
        self._decimals = int(decimals)
        self._refresh_displays()

    def set_dimensions_visible(self, visible: bool) -> None:
        """Show or hide the per-segment dimensions (spec S2)."""
        self.canvas.set_dimensions_visible(visible)
        if self.action_dimensions.isChecked() != visible:
            self.action_dimensions.setChecked(visible)

    def dimensions_visible(self) -> bool:
        return self.canvas.dimensions_visible()

    # ------------------------------------------------------------------ files

    def save_document(self, path: str | Path) -> None:
        target = Path(path)
        save(target, self.canvas.section(), self._unit)
        self._path = target
        self._set_message(f"{strings.label_for('saved')}: {target.name}")

    def open_document(self, path: str | Path) -> bool:
        source = Path(path)
        try:
            section, unit = load(source)
        except DocumentError as error:
            self._report_error(strings.error_message(error.code))
            return False

        self._unit = unit
        self.canvas.set_section(section)
        self.canvas.set_editable(section.template is None)
        self.canvas.fit_to_content()
        if section.template is not None:
            self.template_panel.set_kind(section.template.kind)
            self.template_panel.set_params(section.template.params)
        self.template_panel.set_unit(self._unit)
        self._props = None
        self._path = source
        self._last_error = None
        self.setWindowTitle(f"{APP_NAME} — {source.name}")
        self._refresh_displays()
        return True

    def export_csv(self, path: str | Path) -> str:
        """Write full-precision results; returns the CSV text that was saved."""
        text = self.results_table.csv_text()
        Path(path).write_text(text, encoding="utf-8")
        self._set_message(f"CSV: {Path(path).name}")
        return text

    # ------------------------------------------------------------------ dialogs

    def open_document_dialog(self) -> None:
        if not self._interactive:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, strings.label_for("open"), str(self._path or ""), FILE_FILTER
        )
        if path:
            self.open_document(path)

    def save_document_dialog(self) -> None:
        if not self._interactive:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            strings.label_for("save"),
            str(self._path or f"seccion{FILE_EXTENSION}"),
            FILE_FILTER,
        )
        if path:
            self.save_document(path)

    def export_csv_dialog(self) -> None:
        if not self._interactive:
            return
        default = "resultados.csv"
        if self._path is not None:
            default = str(self._path.with_suffix(".csv"))
        path, _ = QFileDialog.getSaveFileName(self, strings.label_for("export_csv"), default, CSV_FILTER)
        if path:
            self.export_csv(path)

    def open_settings_dialog(self) -> None:
        if not self._interactive:
            return
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._settings = dialog.values()
            self.set_unit(self._settings.unit)
            self.set_decimals(self._settings.decimals)
            self.set_theme(self._settings.theme)

    # ------------------------------------------------------------------ internals

    def _refresh_displays(self) -> None:
        # The canvas writes its measurements in the same unit the panels accept, so a value
        # typed here and a value read there can never disagree (spec S2).
        self.canvas.set_display(self._unit, self._decimals)
        self.vertex_table.show_section(self.canvas.section(), self._unit, self._decimals)
        self.results_table.show_properties(self._props, self._unit, self._decimals)
        self._unit_label.setText(unit_label(self._unit))

    def _sync_undo_actions(self) -> None:
        self.action_undo.setEnabled(self.canvas.undo_stack().canUndo())
        self.action_redo.setEnabled(self.canvas.undo_stack().canRedo())
        self.action_delete_vertex.setEnabled(self.canvas.selected_vertex() is not None)
        self.action_insert_vertex.setEnabled(self.canvas.is_editable())

    def _on_section_changed(self) -> None:
        self._props = None
        self.canvas.set_centroid(None)
        self._refresh_displays()
        self._sync_undo_actions()

    def _on_cursor_moved(self, x: float, y: float) -> None:
        symbol = unit_label(self._unit)
        self._cursor_label.setText(
            f"X {format_length(x, self._unit, self._decimals)}  "
            f"Y {format_length(y, self._unit, self._decimals)} {symbol}"
        )

    def _on_snap_changed(self, kind: str) -> None:
        label = ""
        if kind:
            label = strings.label_for(f"snap_{kind.lower()}")
        self._snap_label.setText(label)

    def _on_vertex_selected(self, contour: str, index: int) -> None:
        if contour:
            self.vertex_table.select_vertex(contour, index)
        self._sync_undo_actions()

    def _on_drawing_changed(self, drawing: bool) -> None:
        self.action_insert_vertex.setEnabled(self.canvas.is_editable())

    def _block_calculation(self, message: str) -> None:
        self._props = None
        self._last_error = message
        self.results_table.show_properties(None, self._unit, self._decimals)
        self._highlight_first_issue()
        self._set_message(strings.label_for("invalid_title"))
        if self._interactive:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle(strings.label_for("invalid_title"))
            box.setText(message)
            box.setInformativeText(strings.label_for("invalid_hint"))
            box.exec()

    def _highlight_first_issue(self) -> None:
        issues = validate_section(self.canvas.section())
        if not issues:
            return
        point = issues[0].points[0] if issues[0].points else None
        if point is None:
            return
        for name, contour in ((OUTER, self.canvas.section().outer), (INNER, self.canvas.section().inner)):
            if contour is None:
                continue
            for index, candidate in enumerate(contour.points):
                if candidate == point:
                    self.canvas.select_vertex(name, index)
                    return

    def _report_error(self, message: str) -> None:
        self._last_error = message
        self._set_message(message)
        if self._interactive:
            QMessageBox.warning(self, strings.label_for("window_title"), message)

    def _set_message(self, text: str) -> None:
        self._message_label.setText(text)


def _issues_text(issues: list[ValidationIssue] | tuple[ValidationIssue, ...]) -> str:
    lines = [f"• {strings.message_for(issue.code.value)}" for issue in issues]
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
