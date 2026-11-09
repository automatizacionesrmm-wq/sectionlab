"""Line icons drawn with QPainter, so the tool ships without external image assets.

Every icon lives on a 24x24 grid and is described by a few primitives; `icon()` renders it
in any colour and at any pixel size, which keeps the toolbar crisp on HiDPI screens and lets
the whole set follow the active theme (spec S2).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_GRID = 24.0

# Each entry is a tuple of primitives: L line, R round rect, C circle, D filled dot, P polyline,
# H half-filled disc.
_ICONS: dict[str, tuple[str, ...]] = {
    "new": ("P 6,3 17,3 20,6 20,21 4,21 4,3 6,3", "P 17,3 17,7 20,7"),
    "open": ("P 3,6 10,6 12,9 21,9 21,19 3,19 3,6",),
    "save": ("R 4 3 16 18 2", "R 8 3 8 6 0.5", "R 7 13 10 7 0.5"),
    "calculate": ("R 3 3 18 18 2.5", "P 7,12.4 10.6,16 17,8.4"),
    "undo": ("P 20,16 20,12 4,12", "P 9,7 4,12 9,17"),
    "redo": ("P 4,16 4,12 20,12", "P 15,7 20,12 15,17"),
    "draw": ("P 4,20 6,13 15,4 20,9 11,18 4,20", "L 13 6 18 11"),
    "insert": ("L 4 20 20 4", "D 12 12 2.2", "L 12 3 12 7", "L 12 17 12 21", "L 3 12 7 12", "L 17 12 21 12"),
    "delete": ("L 4 20 20 4", "C 12 12 3.4", "L 9.6 9.6 14.4 14.4", "L 14.4 9.6 9.6 14.4"),
    "ortho": ("P 4,3 4,20 21,20", "R 4 16 4 4 0"),
    "snap": ("L 12 2 12 7", "L 12 17 12 22", "L 2 12 7 12", "L 17 12 22 12", "R 9 9 6 6 1"),
    "grid": ("R 3 3 18 18 1.5", "L 3 9 21 9", "L 3 15 21 15", "L 9 3 9 21", "L 15 3 15 21"),
    "zoom_in": ("C 10.5 10.5 6.5", "L 15.4 15.4 21 21", "L 7.5 10.5 13.5 10.5", "L 10.5 7.5 10.5 13.5"),
    "zoom_out": ("C 10.5 10.5 6.5", "L 15.4 15.4 21 21", "L 7.5 10.5 13.5 10.5"),
    "fit": ("P 3,8 3,3 8,3", "P 21,8 21,3 16,3", "P 3,16 3,21 8,21", "P 21,16 21,21 16,21", "R 9 9 6 6 1"),
    "csv": ("L 12 3 12 13", "P 8,9 12,13 16,9", "P 3,16 3,21 21,21 21,16"),
    "settings": ("L 3 7 21 7", "L 3 12 21 12", "L 3 17 21 17", "D 8 7 2.6", "D 15 12 2.6", "D 10 17 2.6"),
    "template": ("P 3,20 3,4 21,4 21,8", "L 3 8 21 8", "L 9 8 9 20", "L 3 20 21 20"),
    "free": ("P 4,4 11,4 11,9", "P 13,15 20,15 20,20", "L 11 13 20 3", "D 4 20 1.6"),
    "vertex": ("P 4,20 4,8 20,8 20,20", "D 4 8 2.2", "D 20 8 2.2", "D 4 20 2.2", "D 20 20 2.2"),
    "theme": ("C 12 12 8.5", "H"),
    "close": ("L 6 6 18 18", "L 18 6 6 18"),
    "measure": ("P 3,15 15,3 21,9 9,21 3,15", "L 7 11 9 13", "L 10 8 12 10", "L 13 5 15 7"),
    "light": ("C 12 12 4.5", "L 12 1.5 12 4", "L 12 20 12 22.5", "L 1.5 12 4 12", "L 20 12 22.5 12",
              "L 4.6 4.6 6.4 6.4", "L 17.6 17.6 19.4 19.4", "L 19.4 4.6 17.6 6.4", "L 6.4 17.6 4.6 19.4"),
    "moon": ("H"),
}


def _hex(value: str) -> QColor:
    colour = QColor(value)
    return colour if colour.isValid() else QColor("#8a97a8")


def _draw(painter: QPainter, name: str, color: str, scale: float) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(scale, scale)
    pen = QPen(_hex(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    for primitive in _ICONS[name]:
        kind, _, rest = primitive.partition(" ")
        if kind == "L":
            x1, y1, x2, y2 = (float(v) for v in rest.split())
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        elif kind == "R":
            values = [float(v) for v in rest.split()]
            radius = values[4] if len(values) > 4 else 0.0
            painter.drawRoundedRect(QRectF(values[0], values[1], values[2], values[3]), radius, radius)
        elif kind == "C":
            cx, cy, r = (float(v) for v in rest.split())
            painter.drawEllipse(QPointF(cx, cy), r, r)
        elif kind == "D":
            cx, cy, r = (float(v) for v in rest.split())
            painter.setBrush(_hex(color))
            painter.drawEllipse(QPointF(cx, cy), r, r)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif kind == "P":
            path = QPainterPath()
            for index, pair in enumerate(rest.split()):
                x_text, y_text = pair.split(",")
                point = QPointF(float(x_text), float(y_text))
                if index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            painter.drawPath(path)
        elif kind == "H":
            painter.setBrush(_hex(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(QRectF(3.5, 3.5, 17.0, 17.0), 90 * 16, 180 * 16)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        else:  # pragma: no cover - guards a typo in the table above
            raise ValueError(primitive)


def icon(name: str, color: str = "#c9d4e4", size: int = 20) -> QIcon:
    """Render one named icon at `size` logical pixels."""
    if name not in _ICONS:
        raise KeyError(f"unknown icon: {name}")
    ratio = 2
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    try:
        # The pixmap carries the device pixel ratio, so the painter already works in logical
        # pixels: scaling by `size / _GRID` is what makes the 24-unit drawing fit `size`.
        _draw(painter, name, color, size / _GRID)
    finally:
        painter.end()
    return QIcon(pixmap)


def names() -> tuple[str, ...]:
    """Every icon the table defines, for tests and for a quick visual audit."""
    return tuple(_ICONS)
