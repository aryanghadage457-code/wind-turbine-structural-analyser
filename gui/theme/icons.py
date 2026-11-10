"""Thin-line icons drawn with QPainter, so no image files are needed.

Usage:
    from gui.theme.icons import pixmap, icon
    label.setPixmap(pixmap("turbine", "#9A8873", 32))
    button.setIcon(icon("folder", "#9A8873", 20))

Every icon is drawn on a 24 x 24 grid and scales cleanly to any size.
Available names: plus, folder, turbine, cube, sliders, bolt, chart, wind, stress
"""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
)


def _poly(*coords):
    return QPolygonF([QPointF(x, y) for x, y in coords])


def _line(p, x1, y1, x2, y2):
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


# ---------------------------------------------------------------- drawers

def _plus(p):
    _line(p, 12, 5, 12, 19)
    _line(p, 5, 12, 19, 12)


def _folder(p):
    path = QPainterPath()
    path.moveTo(3, 7)
    path.lineTo(3, 18)
    path.quadTo(3, 19.5, 4.5, 19.5)
    path.lineTo(19.5, 19.5)
    path.quadTo(21, 19.5, 21, 18)
    path.lineTo(21, 9.5)
    path.quadTo(21, 8, 19.5, 8)
    path.lineTo(11, 8)
    path.lineTo(9, 5.5)
    path.lineTo(4.5, 5.5)
    path.quadTo(3, 5.5, 3, 7)
    p.drawPath(path)


def _turbine(p):
    p.drawPolygon(_poly((11, 22), (13, 22), (12.45, 12), (11.55, 12)))
    p.drawEllipse(QPointF(12, 10.2), 1.3, 1.3)
    _line(p, 12, 8.9, 12, 2)
    _line(p, 13.1, 10.9, 18.9, 14)
    _line(p, 10.9, 10.9, 5.1, 14)


def _cube(p):
    p.drawPolygon(_poly((12, 3), (20, 7.5), (20, 16.5),
                        (12, 21), (4, 16.5), (4, 7.5)))
    _line(p, 12, 12, 12, 21)
    _line(p, 12, 12, 4, 7.5)
    _line(p, 12, 12, 20, 7.5)


def _sliders(p):
    rows = [(6, 8.0), (12, 15.5), (18, 10.5)]
    for y, x in rows:
        _line(p, 4, y, x - 2.4, y)
        _line(p, x + 2.4, y, 20, y)
        p.drawEllipse(QPointF(x, y), 2.2, 2.2)


def _bolt(p):
    p.drawPolygon(_poly((13, 3), (5, 13.5), (11, 13.5),
                        (10, 21), (19, 10), (13, 10)))


def _chart(p):
    p.drawPolyline(_poly((4, 4), (4, 20), (20, 20)))
    p.drawPolyline(_poly((7.5, 16), (11, 11), (14, 14), (19, 7)))


def _wind(p):
    top = QPainterPath()
    top.moveTo(3, 8)
    top.lineTo(14, 8)
    top.quadTo(18, 8, 18, 5.5)
    top.quadTo(18, 3.5, 16, 3.5)
    p.drawPath(top)
    mid = QPainterPath()
    mid.moveTo(3, 13)
    mid.lineTo(19, 13)
    mid.quadTo(22, 13, 22, 15.5)
    mid.quadTo(22, 18, 19.5, 18)
    p.drawPath(mid)
    _line(p, 3, 18, 12, 18)


def _stress(p):
    p.drawPolygon(_poly((12, 3.5), (22, 20), (2, 20)))
    _line(p, 12, 9.5, 12, 14.5)
    c = p.pen().color()
    p.setBrush(c)
    p.drawEllipse(QPointF(12, 17.2), 0.5, 0.5)
    p.setBrush(Qt.NoBrush)


_DRAWERS = {
    "plus": _plus,
    "folder": _folder,
    "turbine": _turbine,
    "cube": _cube,
    "sliders": _sliders,
    "bolt": _bolt,
    "chart": _chart,
    "wind": _wind,
    "stress": _stress,
}


# ------------------------------------------------------------------- API

def pixmap(name, color, size=24, dpr=2.0):
    """Return a crisp transparent QPixmap of the named icon."""
    drawer = _DRAWERS[name]

    px = QPixmap(int(size * dpr), int(size * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24.0, size / 24.0)

    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    drawer(p)
    p.end()
    return px


def icon(name, color, size=24):
    return QIcon(pixmap(name, color, size))