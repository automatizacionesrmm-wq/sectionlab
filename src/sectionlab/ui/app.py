"""Main window: canvas, template panel, vertex list, results and the calculate flow.

The window owns the interaction state: which unit and how many decimals are shown, whether
the geometry comes from a template or from free drawing, and the last calculated results.
Validation blocks calculation with Spanish messages (spec S13, S15, D6).
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QProcess, QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QInputDialog,
    QApplication,
    QFileDialog,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
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
import sectionlab
from sectionlab import __version__
from sectionlab.core.engine import InvalidSectionError, SectionProperties, calculate
from sectionlab.core.edit import chamfer, mirror, offset
from sectionlab.core.model import Contour, Section
from sectionlab.core.sketch import SketchError
from sectionlab.core.snap import SNAP_KINDS, SnapKind
from sectionlab.core.templates import TemplateKind, TemplateParameterError, build_section
from sectionlab.core.units import Unit
from sectionlab.core.update import (
    REPOSITORY,
    Release,
    UpdateError,
    download,
    fetch_latest,
    install_code,
)
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
from sectionlab.ui.updater import UpdateBanner, UpdateChecker, UpdateDownloader
from sectionlab.ui.vertex_table import VertexTable

SNAP_ICON_NAMES: dict[SnapKind, str] = {
    SnapKind.ENDPOINT: "snap_endpoint",
    SnapKind.MIDPOINT: "snap_midpoint",
    SnapKind.CENTER: "snap_center",
    SnapKind.INTERSECTION: "snap_intersection",
    SnapKind.PERPENDICULAR: "snap_perpendicular",
}
"""Icon and label key of each snap family, in the order the toolbar shows it (spec S13)."""

APP_NAME = strings.UI["window_title"]
WINDOW_TITLE = f"{APP_NAME} {__version__}"
# The automatic check waits a moment, so the window paints before the network is touched.
AUTO_CHECK_DELAY_MS = 1500
FILE_FILTER = f"SectionLab (*{FILE_EXTENSION})"
CSV_FILTER = "CSV (*.csv)"
PANEL_WIDTH = 360
PANEL_MIN_WIDTH = 240


class _PanelHeader(QWidget):
    """Title bar of an inspector: drag it to a side, double click to float, right click for a menu."""

    DRAG_THRESHOLD = 6

    def __init__(self, dock: QDockWidget, window: "MainWindow", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dock = dock
        self._window = window
        self._origin: QPointF | None = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(strings.label_for("panel_move_tip"))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.globalPosition()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._origin is None:
            super().mouseMoveEvent(event)
            return
        if not self._dragging:
            delta = (event.globalPosition() - self._origin).manhattanLength()
            if delta >= self.DRAG_THRESHOLD:
                self._dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            super().mouseReleaseEvent(event)
            return
        moved = self._dragging
        self._origin = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if moved:
            self._window.move_panel(self._dock, event.globalPosition().toPoint())
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._window.toggle_panel_float(self._dock)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        menu = self._window.panel_menu(self._dock, event.globalPos())
        menu.exec(event.globalPos())
        event.accept()


class MainWindow(QMainWindow):
    """One section per window, with the drawing on the left and its data on the right."""

    def __init__(self, settings: AppSettings | None = None, *, interactive: bool = True) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1280, 820)

        self._interactive = interactive
        self._last_command: str | None = None
        self._settings = settings or load_settings()
        self._unit = self._settings.unit
        self._decimals = self._settings.decimals
        self._theme = self._settings.theme
        self._props: SectionProperties | None = None
        self._path: Path | None = None
        self._last_error: str | None = None
        self._template_kind: str | None = None
        self._template_mode = True
        self._fetch = fetch_latest
        self._download = download
        self._opener = None
        self._checker: UpdateChecker | None = None
        self._downloader: UpdateDownloader | None = None
        self._updates_dir: Path | None = None
        self._relaunch = _relaunch_application
        self._open_installer = _open_installer
        self._automatic_check = False
        self._last_check: tuple[str, str, str] | None = None
        self._release: Release | None = None
        self._icon_targets: list[tuple[QAction, str]] = []
        self._glyphs: list[tuple[QLabel, str]] = []
        self._docks: list[QDockWidget] = []
        self._dock_by_name: dict[str, QDockWidget] = {}
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
        self._snap_text = ""
        self._guides_text = ""
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
        self._build_snap_strip()
        self._apply_theme()

        self.canvas.sectionChanged.connect(self._on_section_changed)
        self.canvas.cursorMoved.connect(self._on_cursor_moved)
        self.canvas.snapChanged.connect(self._on_snap_changed)
        self.canvas.vertexSelected.connect(self._on_vertex_selected)
        self.canvas.segmentSelected.connect(self._on_segment_selected)
        self.canvas.drawingChanged.connect(self._on_drawing_changed)
        self.canvas.editRejected.connect(self._on_dimension_rejected)
        self.canvas.dimensionPlaced.connect(self._on_dimension_placed)
        self.canvas.dimensionToolChanged.connect(self._on_dimension_tool_changed)
        self.canvas.dimensionStepChanged.connect(self._on_dimension_step)
        self.canvas.guidesChanged.connect(self._on_guides_changed)
        self.canvas.drawingChanged.connect(self._on_drawing_changed)
        self.canvas.dimensionsDropped.connect(self._on_dimensions_dropped)
        self.canvas.dimensionEdited.connect(self._on_dimension_edited)
        self.template_panel.applied.connect(self.apply_template)
        self.template_panel.freeModeRequested.connect(self.start_free_geometry)
        self.template_panel.convertRequested.connect(self.convert_to_free_geometry)
        self.template_panel.parameterFocused.connect(self._on_parameter_focused)
        self.vertex_table.vertexEdited.connect(self.canvas.move_vertex)
        self.vertex_table.vertexActivated.connect(self.canvas.select_vertex)
        self.canvas.undo_stack().indexChanged.connect(self._on_undo_index_changed)

        self.update_banner.updateRequested.connect(self.apply_update)
        self._sync_undo_actions()
        self._sync_template_dock()
        self._refresh_displays()
        self._message_label.setText(strings.label_for("ready"))
        if self._interactive:
            # Parented to the window: closing it before the delay must cancel the check
            # instead of firing into a deleted C++ object.
            self._auto_check_timer = QTimer(self)
            self._auto_check_timer.setSingleShot(True)
            self._auto_check_timer.setInterval(AUTO_CHECK_DELAY_MS)
            self._auto_check_timer.timeout.connect(
                lambda: self.check_for_updates(automatic=True)
            )
            self._auto_check_timer.start()

    # ------------------------------------------------------------------ construction

    def _build_layout(self) -> None:
        """Give the drawing every pixel, and let each inspector dock float or move."""
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.update_banner = UpdateBanner(central)
        central_layout.addWidget(self.update_banner)
        central_layout.addWidget(self.canvas)
        self.setCentralWidget(central)
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
        for name, title, glyph, content, _height in specs:
            self._dock(name, title, glyph, content)

        # Template and vertices on the left, results on the right: the drawing keeps the
        # middle and stays the largest area (spec S8).
        template = self._dock_by_name["template"]
        vertices = self._dock_by_name["vertices"]
        results = self._dock_by_name["results"]
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, template)
        self.splitDockWidget(template, vertices, Qt.Orientation.Vertical)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, results)
        self.resizeDocks([template, vertices], [specs[0][4], specs[1][4]], Qt.Orientation.Vertical)
        self.resizeDocks([template, results], [PANEL_WIDTH, PANEL_WIDTH], Qt.Orientation.Horizontal)

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
        self._dock_by_name[name] = dock
        return dock

    def _panel_header(self, dock: QDockWidget, title: str, glyph: str) -> QWidget:
        header = _PanelHeader(dock, self, dock)
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

    def _panel_docks(self) -> list[QDockWidget]:
        """The inspectors that mean something right now: no template panel on free geometry."""
        if self._template_mode:
            return list(self._docks)
        template = self._dock_by_name.get("template")
        return [dock for dock in self._docks if dock is not template]

    def panel_docks(self) -> list[QDockWidget]:
        return self._panel_docks()

    def template_mode(self) -> bool:
        """True while a template drives the section, or while the document is still empty."""
        return self._template_mode

    def _sync_template_dock(self) -> None:
        """Hide the template inspector once the section is free geometry (spec S8)."""
        dock = self._dock_by_name.get("template")
        if dock is None:
            return
        dock.toggleViewAction().setEnabled(self._template_mode)
        if not self._template_mode:
            dock.hide()
        self._sync_panels_action()

    def panel_target_at(self, global_point: QPoint) -> Qt.DockWidgetArea | None:
        """The side a drop would dock to, or None when the point is outside the window."""
        local = self.mapFromGlobal(global_point)
        if not self.rect().contains(local):
            return None
        if local.x() < self.width() / 2:
            return Qt.DockWidgetArea.LeftDockWidgetArea
        return Qt.DockWidgetArea.RightDockWidgetArea

    def place_panel(self, dock: QDockWidget, area: Qt.DockWidgetArea) -> None:
        """Dock one inspector on a side of the window."""
        dock.setFloating(False)
        self.addDockWidget(area, dock)
        dock.show()
        self._sync_panels_action()

    def move_panel(self, dock: QDockWidget, global_point: QPoint) -> None:
        """Drop a dragged inspector: a side of the window, or a float where it was left."""
        area = self.panel_target_at(global_point)
        if area is None:
            dock.setFloating(True)
            dock.move(global_point - QPoint(dock.width() // 2, 12))
            dock.show()
            self._sync_panels_action()
            return
        self.place_panel(dock, area)

    def toggle_panel_float(self, dock: QDockWidget) -> None:
        """Double clicking a header pops the inspector out, and back in."""
        if dock.isFloating():
            self.place_panel(dock, Qt.DockWidgetArea.RightDockWidgetArea)
            return
        dock.setFloating(True)
        dock.move(self.mapToGlobal(QPoint(self.width() // 3, self.height() // 4)))
        dock.show()
        self._sync_panels_action()

    def panel_menu(self, dock: QDockWidget, global_point: QPoint) -> QMenu:
        """The header's own menu: a side to dock to, or float it."""
        menu = QMenu(self)
        menu.addAction(strings.label_for("panel_left"), lambda: self.place_panel(dock, Qt.DockWidgetArea.LeftDockWidgetArea))
        menu.addAction(strings.label_for("panel_right"), lambda: self.place_panel(dock, Qt.DockWidgetArea.RightDockWidgetArea))
        if dock.isFloating():
            menu.addAction(strings.label_for("panel_dock"), lambda: self.toggle_panel_float(dock))
        else:
            menu.addAction(strings.label_for("panel_float"), lambda: self.toggle_panel_float(dock))
        menu.addSeparator()
        menu.addAction(strings.label_for("panel_hide"), dock.hide)
        return menu

    def panels_visible(self) -> bool:
        """True when at least one inspector is on screen."""
        return any(not dock.isHidden() for dock in self._panel_docks())

    def all_panels_visible(self) -> bool:
        return all(not dock.isHidden() for dock in self._panel_docks())

    def set_panels_visible(self, visible: bool) -> None:
        """Show or hide every inspector at once, leaving the drawing alone on screen."""
        for dock in self._panel_docks():
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

        self.action_dimension_tool = QAction(strings.label_for("dimension_tool"), self)
        self.action_dimension_tool.setCheckable(True)
        self.action_dimension_tool.setShortcut(QKeySequence("D"))
        self.action_dimension_tool.setStatusTip(strings.label_for("dimension_tool_tip"))
        self.action_dimension_tool.toggled.connect(self.set_dimension_tool)

        self.action_draw = QAction(strings.label_for("draw"), self)
        self.action_draw.setCheckable(True)
        self.action_draw.setShortcut(QKeySequence("L"))
        self.action_draw.setStatusTip(strings.label_for("draw_tip"))
        self.action_draw.toggled.connect(self.set_draw_tool)

        self.action_rectangle = QAction(strings.label_for("rectangle"), self)
        self.action_rectangle.setShortcut(QKeySequence("R"))
        self.action_rectangle.setStatusTip(strings.label_for("rectangle_tip"))
        self.action_rectangle.triggered.connect(self.start_rectangle)

        self.action_chamfer = QAction(strings.label_for("chamfer"), self)
        self.action_chamfer.setStatusTip(strings.label_for("chamfer_tip"))
        self.action_chamfer.triggered.connect(self.apply_chamfer)

        self.action_offset = QAction(strings.label_for("offset"), self)
        self.action_offset.setStatusTip(strings.label_for("offset_tip"))
        self.action_offset.triggered.connect(lambda: self.apply_offset(outward=False))

        self.action_offset_outward = QAction(strings.label_for("offset_outward"), self)
        self.action_offset_outward.triggered.connect(lambda: self.apply_offset(outward=True))

        self.action_mirror_vertical = QAction(strings.label_for("mirror_vertical"), self)
        self.action_mirror_vertical.setStatusTip(strings.label_for("mirror_tip"))
        self.action_mirror_vertical.triggered.connect(lambda: self.apply_mirror("vertical"))

        self.action_mirror_horizontal = QAction(strings.label_for("mirror_horizontal"), self)
        self.action_mirror_horizontal.setStatusTip(strings.label_for("mirror_tip"))
        self.action_mirror_horizontal.triggered.connect(lambda: self.apply_mirror("horizontal"))

        self.action_select_all = QAction(strings.label_for("select_all"), self)
        self.action_select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.action_select_all.triggered.connect(self.select_all)

        self.action_guides = QAction(strings.label_for("guides"), self)
        self.action_guides.setCheckable(True)
        self.action_guides.setChecked(True)
        self.action_guides.setShortcut(QKeySequence("Ctrl+L"))
        self.action_guides.setStatusTip(strings.label_for("guides_tip"))
        self.action_guides.toggled.connect(self.set_guides_visible)

        # One button per snap family, on or off like an OSNAP toolbar (spec S13).
        self._snap_actions: dict[SnapKind, QAction] = {}
        self._snap_pairs: list[tuple[QAction, str]] = []
        for kind, name in SNAP_ICON_NAMES.items():
            label = strings.label_for(name)
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(kind in self._settings.snaps)
            action.setToolTip(label)
            action.setStatusTip(f"{label}: {strings.label_for('snap_toggle_tip')}")
            action.toggled.connect(self._on_snap_toggled)
            self._snap_actions[kind] = action
            self._snap_pairs.append((action, name))
        self.canvas.set_enabled_snaps(self._settings.snaps)

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

        self.action_check_updates = QAction(strings.label_for("check_updates"), self)
        self.action_check_updates.triggered.connect(lambda: self.check_for_updates())
        self.action_about = QAction(strings.label_for("about"), self)
        self.action_about.triggered.connect(self.show_about)

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
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_select_all)

        draw_menu = self.menuBar().addMenu(strings.label_for("menu_draw"))
        draw_menu.addAction(self.action_draw)
        draw_menu.addAction(self.action_rectangle)
        draw_menu.addSeparator()
        draw_menu.addAction(self.action_chamfer)
        draw_menu.addAction(self.action_offset)
        draw_menu.addAction(self.action_offset_outward)
        draw_menu.addAction(self.action_mirror_vertical)
        draw_menu.addAction(self.action_mirror_horizontal)

        view_menu = self.menuBar().addMenu(strings.label_for("menu_view"))
        for action in (self.action_zoom_in, self.action_zoom_out, self.action_fit):
            view_menu.addAction(action)
        view_menu.addSeparator()
        view_menu.addAction(self.action_ortho)
        view_menu.addAction(self.action_dimension_tool)
        view_menu.addAction(self.action_guides)
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

        help_menu = self.menuBar().addMenu(strings.label_for("menu_help"))
        help_menu.addAction(self.action_check_updates)
        help_menu.addAction(self.action_about)

    def _decorate_toolbar(self) -> None:
        """Group the commands so the ribbon stays a dozen icons wide (spec S14).

        File and vertex operations become one button with a menu each: the ribbon keeps the
        commands that are used while drawing and pushes the rest one click away.
        """
        toolbar = self.findChild(QToolBar, "main_toolbar")
        if toolbar is None:
            return
        file_menu = QMenu(self)
        for action in (self.action_open, self.action_save, self.action_export):
            file_menu.addAction(action)
        vertex_menu = QMenu(self)
        for action in (self.action_insert_vertex, self.action_delete_vertex):
            vertex_menu.addAction(action)

        file_button = self._menu_button(toolbar, "open", "toolbar_file", file_menu)
        vertex_button = self._menu_button(toolbar, "vertex", "toolbar_vertices", vertex_menu)
        self._button_targets = [(file_button, "open"), (vertex_button, "vertex")]
        self._icon_targets = [
            (self.action_calculate, "calculate"),
            (self.action_undo, "undo"),
            (self.action_redo, "redo"),
            (self.action_draw, "draw"),
            (self.action_ortho, "ortho"),
            (self.action_dimension_tool, "measure"),
            (self.action_guides, "snap"),
            (self.action_zoom_in, "zoom_in"),
            (self.action_zoom_out, "zoom_out"),
            (self.action_fit, "fit"),
            (self.action_theme, "theme"),
            (self.action_settings, "settings"),
        ]
        slots = (
            [self.action_calculate],
            [file_button],
            [self.action_undo, self.action_redo],
            [self.action_draw],
            [vertex_button],
            [self.action_ortho, self.action_dimension_tool, self.action_guides],
            [self.action_zoom_in, self.action_zoom_out, self.action_fit],
            [self.action_theme, self.action_settings],
        )
        for action in list(toolbar.actions()):
            toolbar.removeAction(action)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setMovable(False)
        for index, slot in enumerate(slots):
            if index:
                toolbar.addSeparator()
            for entry in slot:
                if isinstance(entry, QToolButton):
                    toolbar.addWidget(entry)
                else:
                    toolbar.addAction(entry)
        button = toolbar.widgetForAction(self.action_calculate)
        if isinstance(button, QToolButton):
            button.setObjectName("primary")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setMinimumWidth(128)
            button.style().unpolish(button)
            button.style().polish(button)

    def _menu_button(self, parent, glyph: str, label_key: str, menu: QMenu) -> QToolButton:
        """One button that opens a menu, so a whole group costs a single icon (spec S14)."""
        button = QToolButton(parent)
        button.setObjectName(f"toolbar_{glyph}")
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(20, 20))
        button.setText(strings.label_for(label_key))
        button.setToolTip(strings.label_for(label_key))
        return button

    def _build_snap_strip(self) -> None:
        """The snap switches, small and icon-only at the right of the status bar (spec S13)."""
        strip = QWidget(self)
        strip.setObjectName("snap_strip")
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(3)
        self._snap_buttons: dict[SnapKind, QToolButton] = {}
        for kind, action in self._snap_actions.items():
            name = SNAP_ICON_NAMES[kind]
            button = QToolButton(strip)
            button.setObjectName(f"status_{name}")
            button.setDefaultAction(action)
            button.setAutoRaise(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setIconSize(QSize(15, 15))
            button.setFixedSize(QSize(22, 20))
            layout.addWidget(button)
            self._snap_buttons[kind] = button
        self.statusBar().addPermanentWidget(strip)

    def snap_buttons(self) -> dict[SnapKind, QToolButton]:
        return dict(self._snap_buttons)

    def active_command(self) -> str | None:
        """The command running right now, if any (spec S15)."""
        if self.canvas.is_placing_rectangle():
            return "rectangle"
        if self.canvas.is_placing_dimension():
            return "dimension"
        if self.canvas.is_drawing():
            return "draw"
        return None

    def set_draw_tool(self, active: bool) -> None:
        """Arm or leave the draw command, and keep the button honest (S1, S2)."""
        if active:
            if not self.canvas.is_editable():
                self.action_draw.setChecked(False)
                return
            self.canvas.begin_drawing()
            self._last_command = "draw"
            self._set_message(strings.label_for("draw_armed"))
            return
        self.canvas.end_drawing()

    def select_all(self) -> None:
        """`Ctrl+A`: every vertex of the section (S3)."""
        count = self.canvas.select_all()
        message = (
            strings.label_for("selection_count").format(count=count)
            if count
            else strings.label_for("nothing_selected")
        )
        self._set_message(message)

    def start_rectangle(self) -> None:
        """Rectangle by two opposite corners (S4)."""
        if not self.canvas.is_editable():
            return
        self.canvas.begin_rectangle_tool()
        self._last_command = "rectangle"
        self._set_message(strings.label_for("rectangle_armed"))

    def apply_chamfer(self) -> None:
        """Cut the selected corner (S4)."""
        chosen = self.canvas.selected_vertex()
        if chosen is None:
            self._set_message(strings.label_for("edit_needs_vertices"))
            return
        distance, accepted = QInputDialog.getDouble(
            self,
            strings.label_for("chamfer"),
            strings.label_for("chamfer_distance"),
            10.0,
            0.0,
            1_000_000.0,
            2,
        )
        if not accepted:
            return
        contour = self.canvas.section().outer if chosen[0] == "outer" else self.canvas.section().inner
        if contour is None:
            return
        try:
            points = chamfer(contour.points, chosen[1], distance)
        except SketchError as error:
            self._set_message(strings.edit_error(error.code))
            return
        self._replace_contour_points(points, strings.label_for("undo_chamfer"))

    def apply_offset(self, *, outward: bool) -> None:
        """A parallel contour at a distance: the thickness of a hollow section (S4)."""
        distance, accepted = QInputDialog.getDouble(
            self,
            strings.label_for("offset_outward" if outward else "offset"),
            strings.label_for("offset_distance"),
            5.0,
            0.0,
            1_000_000.0,
            2,
        )
        if not accepted:
            return
        contour = self.canvas.section().outer
        try:
            points = offset(contour.points, distance, outward=outward)
        except SketchError as error:
            self._set_message(strings.edit_error(error.code))
            return
        self._replace_contour_points(points, strings.label_for("undo_offset"))

    def apply_mirror(self, axis: str) -> None:
        """Reflect the contour about its own centre (S4)."""
        contour = self.canvas.section().outer
        try:
            points = mirror(contour.points, axis)
        except SketchError as error:
            self._set_message(strings.edit_error(error.code))
            return
        self._replace_contour_points(points, strings.label_for("undo_mirror"))

    def _replace_contour_points(self, points, text: str) -> None:
        self.canvas.replace_outer(points, text)
        self._last_command = None
        self._set_message(strings.label_for("applied_edit"))

    def cancel_active_command(self) -> bool:
        """`Esc`: leave the running command, then clear what is selected (spec S15).

        Cad programs put command state above selection state, and Esc unwinds one level at a
        time; an editor that owns the keyboard keeps its own Esc, so cancelling a typed value
        never kills the command behind it.
        """
        command = self.active_command()
        if command == "rectangle":
            self.canvas.cancel_rectangle_tool()
        elif command == "dimension":
            self.set_dimension_tool(False)
        elif command == "draw":
            self.canvas.end_drawing()
            self._set_message(strings.label_for("draw_left"))
            return True
        elif (
            self.canvas.selected_dimension() is not None
            or self.canvas.selected_vertex() is not None
            or self.canvas.selected_segment() is not None
        ):
            self.canvas.clear_selection()
            return True
        else:
            return False
        self._set_message(strings.label_for("command_cancelled"))
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Escape and self.cancel_active_command():
            event.accept()
            return
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and self.active_command() is None
            and self._last_command is not None
        ):
            self.repeat_last_command()
            event.accept()
            return
        super().keyPressEvent(event)

    def repeat_last_command(self) -> None:
        """`Enter` re-arms whatever command was last used, like a CAD's repeat (S1)."""
        if self._last_command == "draw":
            self.action_draw.setChecked(True)
            self.set_draw_tool(True)
        elif self._last_command == "rectangle":
            self.start_rectangle()
        elif self._last_command == "dimension":
            self.action_dimension_tool.setChecked(True)
            self.set_dimension_tool(True)

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
        self._refresh_snap_icons()
        for button, glyph in self._button_targets:
            button.setIcon(icon(glyph, palette["text_dim"], 20))
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

    def convert_to_free_geometry(self) -> bool:
        """Keep the contour exactly as it is, drop the template and unlock its vertices.

        A template section belongs to its parameters, so it cannot be nudged vertex by
        vertex (spec S10). This is the door out: same drawing, now editable, one undo step.
        """
        section = self.canvas.section()
        if section.template is None:
            return False
        self._template_kind = None
        self._template_mode = False
        self.canvas.set_editable(True)
        self.canvas.set_section(
            replace(section, template=None),
            record=True,
            text=strings.label_for("undo_convert"),
        )
        self._sync_template_dock()
        self._set_message(strings.label_for("converted_free"))
        return True

    def _on_parameter_focused(self, key: str, millimetres: float) -> None:
        """Point at the dimension whose value the template form is editing (spec S7)."""
        if key:
            self.canvas.set_value_highlight(millimetres, strings.label_for(key))
        else:
            self.canvas.set_value_highlight(None)

    def apply_template(self, kind: str, params: Mapping[str, float] | None = None) -> bool:
        """Build the chosen template in millimetres and show it read-only."""
        try:
            section = build_section(TemplateKind(kind), dict(params or {}))
        except (TemplateParameterError, ValueError) as error:
            code = getattr(error, "code", "")
            self._report_error(
                strings.error_message(code) if code else str(error), quiet=True
            )
            return False
        # Refit only when the template itself changes: while a parameter is edited the view
        # must stay where the user put it.
        refit = self._template_kind != kind
        # The same template keeps its vertex order, so its dimensions still refer to it; a
        # different template replaces the shape and its dimensions no longer mean anything.
        before = len(self.canvas.dimensions())
        self.canvas.set_section(section, fit=refit, keep_dimensions=not refit)
        lost = before - len(self.canvas.dimensions())
        self.canvas.set_editable(False)
        self._template_kind = kind
        self._template_mode = True
        # Only rebuild the form when the template actually changed: rebuilding it here would
        # overwrite the value the user just typed with the template default.
        if self.template_panel.kind() != kind:
            self.template_panel.set_kind(kind)
        self._path = None
        applied = f"{strings.label_for("applied")}: {strings.label_for(kind)}"
        if lost:
            key = "dimension_dropped" if lost == 1 else "dimensions_dropped"
            applied = f"{applied} · {lost} {strings.label_for(key)}"
        self._set_message(applied)
        self._last_error = None
        self._sync_template_dock()
        return True

    def start_free_geometry(self) -> None:
        """Discard the current geometry and start an empty free drawing (spec S10)."""
        self.canvas.set_section(Section(outer=Contour(points=[])))
        self.canvas.set_editable(True)
        self.canvas.reset_view()
        self.set_draw_tool(True)
        self._template_kind = None
        self._template_mode = False
        self._path = None
        self._props = None
        self._sync_template_dock()
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
        """`Supr`: delete every selected vertex, or the selected dimension (S3)."""
        if not self.canvas.is_editable() and self.canvas.selected_dimension() is None:
            return
        if not self.canvas.delete_selection():
            self._set_message(strings.label_for("nothing_selected"))

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
        """Show or hide the dimensions the user placed (spec S1)."""
        self.canvas.set_dimensions_visible(visible)
        if self.action_dimensions.isChecked() != visible:
            self.action_dimensions.setChecked(visible)
        if visible:
            self._set_message(strings.label_for("dimensions_hint"))

    def dimensions_visible(self) -> bool:
        return self.canvas.dimensions_visible()

    def set_dimension_tool(self, active: bool) -> None:
        """Arm or leave the dimension tool, keeping the action and the canvas in step."""
        if active and not self.canvas.begin_dimension_tool():
            self._set_message(strings.label_for("dimension_needs_section"))
            active = False
        elif not active:
            self.canvas.cancel_dimension_tool()
        if self.action_dimension_tool.isChecked() != active:
            self.action_dimension_tool.setChecked(active)

    def dimension_tool_active(self) -> bool:
        return self.canvas.is_placing_dimension()

    def set_guides_visible(self, visible: bool) -> None:
        """Show or hide the alignment guides (spec S12)."""
        self.canvas.set_guides_visible(visible)
        if self.action_guides.isChecked() != visible:
            self.action_guides.setChecked(visible)

    def set_enabled_snaps(self, kinds) -> None:
        """Switch snap families on or off, buttons and canvas kept in step (spec S13)."""
        chosen = tuple(kind for kind in SNAP_KINDS if kind in set(kinds))
        self.canvas.set_enabled_snaps(chosen)
        for kind, action in self._snap_actions.items():
            if action.isChecked() != (kind in chosen):
                action.blockSignals(True)
                action.setChecked(kind in chosen)
                action.blockSignals(False)
        if self._interactive:
            self._settings = replace(self._settings, snaps=chosen)
            save_settings(self._settings)
        if not chosen:
            self._set_message(strings.label_for("snap_none"))
        self._refresh_snap_icons()

    def _refresh_snap_icons(self) -> None:
        """Repaint the status-bar switches: bright when on, faint when off (spec S13)."""
        palette = tokens(self._theme)
        for action, name in self._snap_pairs:
            colour = palette["text"] if action.isChecked() else palette["text_faint"]
            action.setIcon(icon(name, colour, 15))

    def enabled_snaps(self) -> tuple[SnapKind, ...]:
        return tuple(kind for kind in SNAP_KINDS if kind in self.canvas.enabled_snaps())

    def snap_actions(self) -> dict[SnapKind, QAction]:
        return dict(self._snap_actions)

    def _on_snap_toggled(self) -> None:
        """Read the toggled button and push the whole set, so one place owns the state."""
        self.set_enabled_snaps(tuple(kind for kind, action in self._snap_actions.items() if action.isChecked()))

    def guides_visible(self) -> bool:
        return self.canvas.guides_visible()

    def _on_dimension_tool_changed(self, active: bool) -> None:
        if self.action_dimension_tool.isChecked() != active:
            self.action_dimension_tool.setChecked(active)
        self._set_message(
            strings.label_for("dimension_tool_first" if active else "ready")
        )

    def _on_dimension_step(self, picked: int) -> None:
        if not self.canvas.is_placing_dimension():
            return
        if picked <= 0:
            key = "dimension_tool_first"
        elif picked == 1:
            key = "dimension_tool_second"
        else:
            key = "dimension_tool_place"
        self._set_message(strings.label_for(key))

    def _on_dimension_placed(self, identifier: int) -> None:
        self._set_message(strings.label_for("dimension_placed"))

    def _on_dimensions_dropped(self, count: int) -> None:
        key = "dimension_dropped" if count == 1 else "dimensions_dropped"
        self._set_message(f"{count} {strings.label_for(key)}")

    def _on_dimension_edited(self, identifier: int, value: float) -> None:
        """A dimension that drives a template moves its parameter in the form (spec S6)."""
        template = self.canvas.section().template
        if template is not None and self._template_mode:
            self.template_panel.set_params(template.params)

    # ------------------------------------------------------------------ files

    def save_document(self, path: str | Path) -> None:
        target = Path(path)
        save(target, self.canvas.section(), self._unit, self.canvas.dimensions())
        self._path = target
        self._set_message(f"{strings.label_for('saved')}: {target.name}")

    def open_document(self, path: str | Path) -> bool:
        source = Path(path)
        try:
            section, unit, dimensions = load(source)
        except DocumentError as error:
            self._report_error(strings.error_message(error.code))
            return False

        self._unit = unit
        self.canvas.set_section(section)
        self.canvas.set_dimensions(dimensions)
        self.canvas.set_editable(section.template is None)
        self._template_mode = section.template is not None or not section.outer.points
        self._sync_template_dock()
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
            self.set_enabled_snaps(self._settings.snaps)

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
        self.action_delete_vertex.setEnabled(self.canvas.can_delete_selection())
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
        self._snap_text = strings.label_for(f"snap_{kind.lower()}") if kind else ""
        self._refresh_snap_label()

    def _on_guides_changed(self, label: str) -> None:
        self._guides_text = label
        self._refresh_snap_label()

    def _refresh_snap_label(self) -> None:
        """A snap wins the space; a guide fills it when nothing is snapped (spec S12)."""
        self._snap_label.setText(self._snap_text or self._guides_text)

    def _on_segment_selected(self, contour: str, index: int) -> None:
        """A picked edge takes typed input, so the status bar says so."""
        if contour:
            self._set_message(strings.label_for("segment_selected_hint"))

    def _on_vertex_selected(self, contour: str, index: int) -> None:
        if contour:
            self.vertex_table.select_vertex(contour, index)
        self.action_delete_vertex.setEnabled(self.canvas.can_delete_selection())
        self._sync_undo_actions()

    def _on_undo_index_changed(self) -> None:
        """Undo and redo may cross the line between a template and free geometry."""
        section = self.canvas.section()
        template = section.template
        self.canvas.set_editable(template is None)
        was_template_mode = self._template_mode
        self._template_mode = template is not None or not section.outer.points
        self._template_kind = template.kind if template is not None else None
        if self._template_mode != was_template_mode:
            self._sync_template_dock()
        if template is not None:
            self.template_panel.set_kind(template.kind)
            self.template_panel.set_params(template.params)
        self.canvas.set_value_highlight(None)
        self._sync_undo_actions()

    # ------------------------------------------------------------------ updates

    def check_for_updates(self, *, automatic: bool = False) -> bool:
        """Ask GitHub for the newest release in the background (spec S2)."""
        if self._checker is not None and self._checker.isRunning():
            if not automatic:
                self._set_message(strings.label_for("checking_in_flight"))
            return False
        self._automatic_check = automatic
        if not automatic:
            self._set_message(strings.label_for("checking_updates"))
        checker = UpdateChecker(self._fetch, __version__, self)
        checker.offered.connect(self._on_release_offered)
        checker.upToDate.connect(self._on_up_to_date)
        checker.failed.connect(self._on_check_failed)
        checker.finished.connect(self._on_checker_finished)
        self._checker = checker
        checker.start()
        return True

    def offered_release(self) -> Release | None:
        """The release waiting to be installed, if the banner is showing one."""
        return self._release

    def _on_release_offered(self, release: Release) -> None:
        self._record_check("offered", release.version)
        self._release = release
        self.update_banner.offer(release.version)

    def _on_up_to_date(self, release: Release) -> None:
        self._record_check("up_to_date", release.version)
        if not self._automatic_check:
            text = f"{strings.label_for('up_to_date')} ({release.version})"
            self._set_message(text)
            if self._interactive:
                QMessageBox.information(self, strings.label_for("about"), text)
        self._release = None
        self.update_banner.dismiss()
        if not self._automatic_check:
            self._set_message(f"{strings.label_for('up_to_date')} ({release.version})")

    def _on_check_failed(self, code: str, detail: str = "") -> None:
        # An automatic check never nags: offline is not an error the user must see (spec S7).
        self._record_check("failed", detail or code)
        if not self._automatic_check:
            reason = f"{strings.update_message(code)}\n\n{strings.label_for('check_log_hint')} "
            reason += str(self.check_log_path())
            if detail:
                reason += f"\n\n{detail}"
            self._set_message(strings.update_message(code))
            if self._interactive:
                QMessageBox.warning(self, strings.label_for("update_failed"), reason)

    def _record_check(self, outcome: str, detail: str = "") -> None:
        """Keep and log what the last check answered, so a silent failure is still evidence."""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._last_check = (stamp, outcome, detail)
        line = f"{stamp}\t{outcome}\t{detail}".rstrip("\t")
        try:
            path = self.check_log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as log:
                log.write(line + "\n")
        except OSError:
            pass  # a log that cannot be written must never break an update check

    def check_log_path(self) -> Path:
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        return Path(base or tempfile.gettempdir()) / "updates.log"

    def _on_checker_finished(self) -> None:
        checker = self._checker
        self._checker = None
        if checker is not None:
            checker.deleteLater()

    def updates_dir(self) -> Path:
        """Where downloads land: the user's application data, never the installation."""
        if self._updates_dir is not None:
            return self._updates_dir
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        return Path(base or tempfile.gettempdir()) / "updates"

    def apply_update(self) -> bool:
        """Download the offered release and, when it is a code patch, install it (spec S4)."""
        release = self._release
        if release is None or self._downloader is not None:
            return False
        asset = release.code()
        if asset is None:
            return self._offer_installer(release)
        target = self.updates_dir() / asset.name
        self.update_banner.set_busy(True)
        self.update_banner.offer_version(
            f"{strings.label_for('update_downloading')} {release.version}…"
        )
        downloader = UpdateDownloader(asset, target, self._opener, parent=self)
        downloader.ready.connect(self._on_patch_downloaded)
        downloader.failed.connect(self._on_update_failed)
        downloader.finished.connect(self._on_downloader_finished)
        self._downloader = downloader
        downloader.start()
        return True

    def _on_downloader_finished(self) -> None:
        downloader = self._downloader
        self._downloader = None
        if downloader is not None:
            downloader.deleteLater()

    def _on_update_failed(self, code: str) -> None:
        self.update_banner.set_busy(False)
        self._set_message(f"{strings.label_for('update_failed')}: {strings.update_message(code)}")
        if self._interactive:
            QMessageBox.warning(self, strings.label_for("update_failed"), strings.update_message(code))

    def _on_patch_downloaded(self, path: str) -> None:
        """Replace the installed package and ask about restarting (specs S4, S5)."""
        app_dir = self._installation_app_dir()
        if app_dir is None:
            self._on_update_failed("not_installed")
            return
        self.update_banner.offer_version(strings.label_for("update_applying"))
        try:
            install_code(Path(path), app_dir)
        except UpdateError as error:
            self._on_update_failed(error.code)
            return
        self._release = None
        self.update_banner.set_busy(False)
        self.update_banner.offer_version(strings.label_for("update_done"))
        self._set_message(strings.label_for("update_done"))
        self._ask_restart()

    def _installation_app_dir(self) -> Path | None:
        """The folder that holds ``sectionlab``; only a frozen install may be replaced."""
        if not getattr(sys, "frozen", False):
            return None
        package_file = getattr(sectionlab, "__file__", None)
        if not package_file:
            return None
        package = Path(package_file).resolve().parent
        if package.name != "sectionlab":
            return None
        return package.parent

    def _ask_restart(self) -> None:
        if not self._interactive:
            return
        answer = QMessageBox.question(
            self,
            strings.label_for("update_restart_title"),
            f"{strings.label_for('update_done')}.\n\n{strings.label_for('update_restart_question')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restart_application()

    def restart_application(self) -> bool:
        """Re-launch the same executable and close this window (spec S5)."""
        if not getattr(sys, "frozen", False):
            return False
        if not self._relaunch():
            return False
        self.close()
        return True

    def _offer_installer(self, release: Release) -> bool:
        installer = release.installer()
        if installer is None:
            self._on_update_failed("no_asset")
            return False
        target = self.updates_dir() / installer.name
        self.update_banner.set_busy(True)
        self.update_banner.offer_version(strings.label_for("update_needs_installer"))
        downloader = UpdateDownloader(installer, target, self._opener, parent=self)
        downloader.ready.connect(self._on_installer_downloaded)
        downloader.failed.connect(self._on_update_failed)
        downloader.finished.connect(self._on_downloader_finished)
        self._downloader = downloader
        downloader.start()
        return True

    def _on_installer_downloaded(self, path: str) -> None:
        self.update_banner.set_busy(False)
        self._set_message(f"{strings.label_for('installer_ready')} {path}")
        if not self._interactive:
            return
        QMessageBox.information(
            self,
            strings.label_for("about"),
            f"{strings.label_for('installer_ready')}:\n{path}\n\n"
            f"{strings.label_for('installer_close_hint')}",
        )
        if self._open_installer(path):
            self.close()

    def about_text(self) -> str:
        """What the About box says, so the text is testable without a dialog (spec S1)."""
        return (
            f"{APP_NAME} {__version__}\n"
            f"{strings.label_for('about_license')}\n\n"
            f"{self.last_check_text()}\n\n"
            f"{REPOSITORY}"
        )

    def last_check_text(self) -> str:
        """What the last update check answered, so a silent failure can still be read."""
        state = self._last_check
        if state is None:
            return strings.label_for("update_state_never")
        stamp, outcome, detail = state
        text = f"{strings.label_for(f'update_state_{outcome}')} — {stamp}"
        if detail:
            text += f" · {detail}"
        return text

    def show_about(self) -> None:
        QMessageBox.about(self, strings.label_for("about"), self.about_text())

    def _on_dimension_rejected(self, code: str) -> None:
        self._set_message(strings.dimension_message(code))

    def _on_drawing_changed(self, drawing: bool) -> None:
        self.action_insert_vertex.setEnabled(self.canvas.is_editable())
        if self.action_draw.isChecked() != drawing:
            self.action_draw.blockSignals(True)
            self.action_draw.setChecked(drawing)
            self.action_draw.blockSignals(False)

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

    def _report_error(self, message: str, *, quiet: bool = False) -> None:
        """Explain a refusal in the status bar; only an explicit action may interrupt."""
        self._last_error = message
        self._set_message(message)
        if self._interactive and not quiet:
            QMessageBox.warning(self, strings.label_for("window_title"), message)

    def _set_message(self, text: str) -> None:
        self._message_label.setText(text)


def _relaunch_application() -> bool:
    """Start the same executable again, detached from this process."""
    return QProcess.startDetached(sys.executable, sys.argv[1:])


def _open_installer(path: str) -> bool:
    """Run the downloaded installer once this window has closed."""
    if sys.platform.startswith("win"):
        return QProcess.startDetached("cmd", ["/c", f'timeout /t 3 >nul & "{path}"'])
    return QProcess.startDetached(path, [])


def _issues_text(issues: list[ValidationIssue] | tuple[ValidationIssue, ...]) -> str:
    lines = [f"• {strings.message_for(issue.code.value)}" for issue in issues]
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
