"""Colour tokens and the application stylesheet.

One token table per theme, so every widget reads its colours from the same place: the canvas
paints with tokens, and the widget tree is styled by the generated stylesheet (spec S1).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from tempfile import gettempdir

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget


class Theme(str, Enum):
    """The two surfaces the tool ships with."""

    DARK = "dark"
    LIGHT = "light"


DARK: dict[str, str] = {
    "window": "#12151b",
    "window_alt": "#171b22",
    "panel": "#171b22",
    "panel_alt": "#1d222b",
    "panel_high": "#232a35",
    "border": "#262c37",
    "border_soft": "#1f242d",
    "text": "#e6ebf2",
    "text_dim": "#9aa5b4",
    "text_faint": "#65707f",
    "accent": "#39d0ff",
    "accent_soft": "#0e3b4c",
    "accent_border": "#1d6b86",
    "accent_text": "#d9f6ff",
    "accent_hover": "#17607c",
    "danger": "#ff8a8a",
    "danger_soft": "#3a1a1f",
    "ok": "#4ade80",
    "canvas": "#0c0f14",
    "grid_minor": "#151a22",
    "grid_major": "#212936",
    "axis": "#3a4552",
    "axis_text": "#65707f",
    "contour": "#39d0ff",
    "contour_fill": "#1f39d0ff",
    "inner": "#7fa8bd",
    "handle": "#0c0f14",
    "handle_border": "#39d0ff",
    "handle_selected": "#ffb648",
    "centroid": "#ffb648",
    "crosshair": "#4a6b7d",
    "draft": "#39d0ff",
    "dim": "#4a6b7d",
    "dim_text": "#c9d4e4",
    "snap": "#4ade80",
    "warning": "#ffb648",
}

LIGHT: dict[str, str] = {
    "window": "#eef2f7",
    "window_alt": "#f7f9fc",
    "panel": "#ffffff",
    "panel_alt": "#eef2f7",
    "panel_high": "#e3eaf4",
    "border": "#d3dce8",
    "border_soft": "#e8eef6",
    "text": "#0f172a",
    "text_dim": "#475569",
    "text_faint": "#7c8899",
    "accent": "#1d6ff2",
    "accent_soft": "#e8f1ff",
    "accent_border": "#a9ccff",
    "accent_text": "#0b4bb3",
    "accent_hover": "#0b5ad6",
    "danger": "#b42318",
    "danger_soft": "#fee4e2",
    "ok": "#15803d",
    "canvas": "#fcfdfe",
    "grid_minor": "#e9eff7",
    "grid_major": "#d3dfee",
    "axis": "#94a3b8",
    "axis_text": "#7c8899",
    "contour": "#0b4bb3",
    "contour_fill": "#291d6ff2",
    "inner": "#64748b",
    "handle": "#ffffff",
    "handle_border": "#0b4bb3",
    "handle_selected": "#c2410c",
    "centroid": "#c2410c",
    "crosshair": "#9fb0c4",
    "draft": "#1d6ff2",
    "dim": "#7c8899",
    "dim_text": "#27313d",
    "snap": "#15803d",
    "warning": "#b45309",
}

_TABLES = {Theme.DARK: DARK, Theme.LIGHT: LIGHT}


def tokens(theme: Theme) -> dict[str, str]:
    """The colour table for one theme."""
    return _TABLES[theme]


_STYLESHEET = """
QWidget {{
    background: {window};
    color: {text};
    font-size: 12px;
}}
QMainWindow, QDialog {{ background: {window}; }}

QMenuBar {{
    background: {window_alt};
    border-bottom: 1px solid {border};
    padding: 2px 4px;
}}
QMenuBar::item {{ padding: 5px 9px; border-radius: 4px; background: transparent; color: {text_dim}; }}
QMenuBar::item:selected {{ background: {panel_high}; color: {text}; }}
QMenu {{ background: {panel}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {accent_soft}; color: {accent_text}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}

QToolBar {{
    background: {window_alt};
    border-bottom: 1px solid {border};
    spacing: 2px;
    padding: 5px 8px;
}}
QToolBar::separator {{ width: 1px; background: {border}; margin: 4px 6px; }}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 6px;
    font-size: 10px;
    color: {text_dim};
}}
QToolButton:hover {{ background: {panel_high}; color: {text}; border-color: {border}; }}
QToolButton:pressed {{ background: {accent_soft}; }}
QToolButton:checked {{ background: {accent_soft}; color: {accent}; border-color: {accent_border}; }}
QToolButton:disabled {{ color: {text_faint}; }}

QToolButton#primary {{
    background: {accent_soft};
    border: 1px solid {accent_border};
    color: {accent_text};
    font-weight: 600;
    padding: 6px 14px;
}}
QToolButton#primary:hover {{ background: {accent_hover}; }}
QToolButton#primary:disabled {{ background: {panel_alt}; color: {text_faint}; border-color: {border}; }}

QLabel {{ background: transparent; }}
QLabel#panel_title {{
    color: {text_faint};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    background: transparent;
}}
QWidget#panel_header {{
    background: {panel_alt};
    border-bottom: 1px solid {border};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QLabel#status {{
    color: {text_dim};
    font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 11px;
    padding: 2px 10px;
    border-right: 1px solid {border};
}}

QLabel#panels_hint {{
    color: {accent};
    font-size: 11px;
    padding: 2px 10px;
    border-right: 1px solid {border};
}}

QFrame#panel {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 8px;
}}
QFrame#panel > QWidget {{ border: 0; }}

QStatusBar {{
    background: {panel_alt};
    border-top: 1px solid {border};
}}
QStatusBar::item {{ border: 0; }}

QSplitter::handle {{ background: {border}; width: 1px; height: 1px; }}

QDockWidget {{ background: {panel}; border: 1px solid {border}; }}
QDockWidget::title {{ background: {panel_alt}; padding: 0; border: 0; }}
QDockWidget QFrame#panel {{
    border-top: 0;
    border-top-left-radius: 0;
    border-top-right-radius: 0;
}}
QWidget#panel_header {{
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent;
    border: 0;
    padding: 0;
}}
QMainWindow::separator {{ background: {border}; width: 1px; height: 1px; }}
QMainWindow::separator:hover {{ background: {accent}; }}
QToolButton#dock_close {{ border: 0; background: transparent; padding: 2px; }}
QToolButton#dock_close:hover {{ background: {danger_soft}; border-radius: 4px; }}

QScrollArea {{ border: 0; background: {panel}; }}
QScrollBar:vertical {{ background: {panel}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {text_faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: {panel}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px; min-width: 24px; }}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {canvas};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 4px 7px;
    color: {text};
    selection-background-color: {accent_soft};
    selection-color: {accent_text};
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{ border-color: {accent_border}; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: 0; width: 18px; }}
QComboBox::down-arrow {{
    image: url({chevron});
    width: 10px;
    height: 10px;
    margin-right: 6px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({arrow_up});
    width: 9px;
    height: 6px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({arrow_down});
    width: 9px;
    height: 6px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    background: {panel_high};
    border-left: 1px solid {border};
    border-top-right-radius: 5px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    background: {panel_high};
    border-left: 1px solid {border};
    border-top: 1px solid {border};
    border-bottom-right-radius: 5px;
}}
QComboBox QAbstractItemView {{
    background: {panel};
    border: 1px solid {border};
    selection-background-color: {accent_soft};
    selection-color: {accent_text};
    outline: 0;
}}

QPushButton {{
    background: {panel_high};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 12px;
    color: {text};
}}
QPushButton:hover {{ border-color: {accent_border}; color: {accent_text}; }}
QPushButton:pressed {{ background: {accent_soft}; }}
QPushButton:disabled {{ color: {text_faint}; border-color: {border_soft}; }}
QPushButton#primary {{
    background: {accent_soft};
    border: 1px solid {accent_border};
    color: {accent_text};
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {accent_hover}; }}
QPushButton#ghost {{ background: transparent; color: {text_dim}; }}
QPushButton#ghost:hover {{ background: {panel_high}; color: {text}; }}

QTableWidget, QTableView {{
    background: {panel};
    alternate-background-color: {panel_alt};
    border: 1px solid {border};
    border-radius: 6px;
    gridline-color: {border_soft};
    selection-background-color: {accent_soft};
    selection-color: {accent_text};
}}
QTableWidget::item, QTableView::item {{ padding: 3px 6px; border: 0; }}
QHeaderView {{ background: {panel_alt}; }}
QHeaderView::section {{
    background: {panel_alt};
    color: {text_faint};
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    border: 0;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border_soft};
    padding: 6px 6px;
}}
QTableCornerButton::section {{ background: {panel_alt}; border: 0; }}

QGroupBox {{
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 8px;
    background: {panel};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {text_faint};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

QTabWidget::pane {{ border: 1px solid {border}; background: {panel}; }}
QTabBar::tab {{
    background: {panel_alt};
    color: {text_faint};
    border: 1px solid {border};
    border-bottom: 0;
    padding: 6px 12px;
}}
QTabBar::tab:selected {{ background: {panel}; color: {accent}; }}

QToolTip {{
    background: {panel_high};
    color: {text};
    border: 1px solid {border};
    padding: 4px 7px;
}}
"""


_ARROWS: dict[str, tuple[tuple[float, float], ...]] = {
    "up": ((5.0, 2.0), (9.0, 7.0), (1.0, 7.0)),
    "down": ((1.0, 3.0), (9.0, 3.0), (5.0, 8.0)),
    "chevron": ((1.5, 3.0), (5.5, 7.5), (9.5, 3.0), (9.5, 5.0), (5.5, 9.5), (1.5, 5.0)),
}


def _glyph_png(direction: str, colour: str) -> str:
    """Small generated PNG for a styled sub-control, cached per colour."""
    folder = Path(gettempdir()) / "sectionlab-theme"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{direction}-{colour.lstrip('#')}.png"
    if not target.exists():
        size = 10
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colour))
            polygon = QPolygonF([QPointF(x, y) for x, y in _ARROWS[direction]])
            painter.drawPolygon(polygon)
        finally:
            painter.end()
        pixmap.save(str(target))
    return target.as_posix()


def stylesheet(theme: Theme) -> str:
    """The generated Qt stylesheet for one theme."""
    values = dict(tokens(theme))
    values["arrow_up"] = _glyph_png("up", values["text_dim"])
    values["arrow_down"] = _glyph_png("down", values["text_dim"])
    values["chevron"] = _glyph_png("chevron", values["text_dim"])
    return _STYLESHEET.format(**values)


def apply_theme(widget: QApplication | QWidget, theme: Theme) -> None:
    """Restyle the whole tree; a widget falls back to its own application."""
    target = widget if isinstance(widget, QApplication) else widget.window()
    app = QApplication.instance()
    if app is None:
        return
    app.setStyleSheet(stylesheet(theme))
    if target is not None:
        target.setProperty("theme", theme.value)
