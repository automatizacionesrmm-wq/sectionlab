"""Main window: canvas, template panel, vertex list, results and the calculate flow.

The window owns the interaction state: which unit and how many decimals are shown, whether
the geometry comes from a template or from free drawing, and the last calculated results.
Validation blocks calculation with Spanish messages (spec S13, S15, D6).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
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
from sectionlab.core.model import Section
from sectionlab.core.templates import TemplateKind, TemplateParameterError, build_section
from sectionlab.core.units import Unit
from sectionlab.core.validation import ValidationIssue, validate_section
from sectionlab.ui import strings
from sectionlab.ui.canvas import INNER, OUTER, CanvasView
from sectionlab.ui.results import ResultsTable, format_length
from sectionlab.ui.settings import (
    AppSettings,
    SettingsDialog,
    load_settings,
    save_settings,
    unit_label,
)
from sectionlab.ui.template_panel import TemplatePanel
from sectionlab.ui.vertex_table import VertexTable

APP_NAME = strings.UI["window_title"]
FILE_FILTER = f"SectionLab (*{FILE_EXTENSION})"
CSV_FILTER = "CSV (*.csv)"


class MainWindow(QMainWindow):
    """One section per window, with the drawing on the left and its data on the right."""

    def __init__(self, settings: AppSettings | None = None, *, interactive: bool = True) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)

        self._interactive = interactive
        self._settings = settings or load_settings()
        self._unit = self._settings.unit
        self._decimals = self._settings.decimals
        self._props: SectionProperties | None = None
        self._path: Path | None = None
        self._last_error: str | None = None

        self.canvas = CanvasView(self)
        self.template_panel = TemplatePanel(self)
        self.vertex_table = VertexTable(self)
        self.results_table = ResultsTable(self)

        self._cursor_label = QLabel(self)
        self._snap_label = QLabel(self)
        self._unit_label = QLabel(self)
        self._message_label = QLabel(self)
        self.statusBar().addWidget(self._cursor_label)
        self.statusBar().addWidget(self._unit_label)
        self.statusBar().addWidget(self._snap_label)
        self.statusBar().addPermanentWidget(self._message_label)

        self._build_layout()
        self._build_actions()

        self.canvas.sectionChanged.connect(self._on_section_changed)
        self.canvas.cursorMoved.connect(self._on_cursor_moved)
        self.canvas.snapChanged.connect(self._on_snap_changed)
        self.canvas.vertexSelected.connect(self._on_vertex_selected)
        self.canvas.drawingChanged.connect(self._on_drawing_changed)
        self.template_panel.applied.connect(self.apply_template)
        self.template_panel.convertRequested.connect(self.convert_to_free_geometry)
        self.vertex_table.vertexEdited.connect(self.canvas.move_vertex)
        self.vertex_table.vertexActivated.connect(self.canvas.select_vertex)

        self._sync_undo_actions()
        self._refresh_displays()
        self._message_label.setText(strings.label_for("ready"))

    # ------------------------------------------------------------------ construction

    def _build_layout(self) -> None:
        side = QWidget(self)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(QLabel(strings.label_for("vertex_table"), side))
        side_layout.addWidget(self.vertex_table, 2)
        side_layout.addWidget(QLabel(strings.label_for("results"), side))
        side_layout.addWidget(self.results_table, 3)

        panel = QWidget(self)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(self.template_panel)
        panel_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(side)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.canvas)
        splitter.addWidget(scroll)
        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([500, 340, 340])
        self.setCentralWidget(splitter)

    def _build_actions(self) -> None:
        toolbar = self.addToolBar(strings.label_for("main_toolbar"))
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)

        self.action_calculate = QAction(strings.label_for("calculate"), self)
        self.action_calculate.setShortcut(QKeySequence("Ctrl+Return"))
        self.action_calculate.triggered.connect(self.calculate_now)
        toolbar.addAction(self.action_calculate)

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

        self.action_zoom_in = QAction(strings.label_for("zoom_in"), self)
        self.action_zoom_in.setShortcut(QKeySequence("Ctrl++"))
        self.action_zoom_in.triggered.connect(self.canvas.zoom_in)
        self.action_zoom_out = QAction(strings.label_for("zoom_out"), self)
        self.action_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.action_zoom_out.triggered.connect(self.canvas.zoom_out)
        self.action_fit = QAction(strings.label_for("zoom_fit"), self)
        self.action_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.action_fit.triggered.connect(self.canvas.fit_to_content)

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

        settings_menu = self.menuBar().addMenu(strings.label_for("menu_settings"))
        settings_menu.addAction(self.action_settings)

        for action in (
            self.action_undo,
            self.action_redo,
            self.action_delete_vertex,
            self.action_insert_vertex,
            self.action_zoom_in,
            self.action_zoom_out,
            self.action_fit,
            self.action_ortho,
        ):
            toolbar.addAction(action)

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
        self.canvas.set_section(section)
        self.canvas.set_editable(False)
        self.template_panel.set_kind(kind)
        self._path = None
        self._set_message(f"{strings.label_for("applied")}: {strings.label_for(kind)}")
        self._last_error = None
        return True

    def convert_to_free_geometry(self) -> bool:
        """Keep the contours and drop the template so the drawing can be edited."""
        section = self.canvas.section()
        if section.template is None:
            self.canvas.set_editable(True)
            return False
        self.canvas.set_section(Section(outer=section.outer, inner=section.inner))
        self.canvas.set_editable(True)
        self._set_message(strings.label_for("free_mode"))
        return True

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

    # ------------------------------------------------------------------ internals

    def _refresh_displays(self) -> None:
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
