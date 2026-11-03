"""Line icons for the ribbon, drawn with QPainter (no image files needed).

    ribbon_icon("wind")  ->  QIcon  (normal + disabled state)

Drawn on a 24x24 grid, stroke only, to match the thin-line style of the
Start page. Independent of gui/theme/icons.py so nothing there can break.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from gui.theme.styles import COLORS


def _pts(*xy):
    return [QPointF(xy[i], xy[i + 1]) for i in range(0, len(xy), 2)]


def _save(p):
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2)
    p.drawPolyline(_pts(8, 4, 8, 9, 16, 9, 16, 4))
    p.drawRect(QRectF(8, 14, 8, 6))


def _close_project(p):
    p.drawPolyline(_pts(3, 19, 3, 6, 9, 6, 11, 8, 21, 8, 21, 19, 3, 19))
    p.drawLine(QPointF(10, 11.5), QPointF(14, 15.5))
    p.drawLine(QPointF(14, 11.5), QPointF(10, 15.5))


def _fit(p):
    for a in ((3, 8, 3, 3, 8, 3), (16, 3, 21, 3, 21, 8),
              (21, 16, 21, 21, 16, 21), (8, 21, 3, 21, 3, 16)):
        p.drawPolyline(_pts(*a))
    p.drawRect(QRectF(9, 9, 6, 6))


def _cube(p):
    p.drawPolygon(_pts(12, 3, 20, 7.5, 20, 16.5, 12, 21, 4, 16.5, 4, 7.5))
    p.drawPolyline(_pts(4, 7.5, 12, 12, 20, 7.5))
    p.drawLine(QPointF(12, 12), QPointF(12, 21))


def _turbine(p):
    p.drawLine(QPointF(12, 9), QPointF(12, 22))
    p.drawLine(QPointF(9, 22), QPointF(15, 22))
    p.drawLine(QPointF(12, 9), QPointF(12, 2))
    p.drawLine(QPointF(12, 9), QPointF(5.9, 12.5))
    p.drawLine(QPointF(12, 9), QPointF(18.1, 12.5))
    p.drawEllipse(QPointF(12, 9), 1.5, 1.5)


def _step(p):
    p.drawPolyline(_pts(6, 3, 14, 3, 18, 7, 18, 21, 6, 21, 6, 3))
    p.drawPolyline(_pts(14, 3, 14, 7, 18, 7))
    p.drawLine(QPointF(12, 10), QPointF(12, 17))
    p.drawPolyline(_pts(9, 14, 12, 17, 15, 14))


def _dimensions(p):
    p.drawLine(QPointF(4, 12), QPointF(20, 12))
    p.drawLine(QPointF(4, 7), QPointF(4, 17))
    p.drawLine(QPointF(20, 7), QPointF(20, 17))
    p.drawPolyline(_pts(7, 9.5, 4, 12, 7, 14.5))
    p.drawPolyline(_pts(17, 9.5, 20, 12, 17, 14.5))


def _material(p):
    p.drawPolygon(_pts(12, 4, 21, 9, 12, 14, 3, 9))
    p.drawPolyline(_pts(3, 13, 12, 18, 21, 13))
    p.drawPolyline(_pts(3, 17, 12, 22, 21, 17))


def _wind(p):
    for y, x_end, r in ((8, 15, 3), (13, 19, 3.5), (18, 10, 2.5)):
        path = QPainterPath(QPointF(3, y))
        path.lineTo(x_end, y)
        path.cubicTo(x_end + r * 1.4, y, x_end + r * 1.4, y - r * 2,
                     x_end, y - r * 2)
        p.drawPath(path)


def _air(p):
    p.drawRoundedRect(QRectF(10, 3, 4, 12), 2, 2)
    p.drawEllipse(QPointF(12, 18), 3.2, 3.2)
    p.drawLine(QPointF(12, 8), QPointF(12, 15))


def _mesh(p):
    p.drawRect(QRectF(4, 4, 16, 16))
    for v in (9.3, 14.7):
        p.drawLine(QPointF(v, 4), QPointF(v, 20))
        p.drawLine(QPointF(4, v), QPointF(20, v))


def _play(p):
    p.drawPolygon(_pts(8, 5, 19, 12, 8, 19))


def _stop(p):
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    p.drawLine(QPointF(9, 9), QPointF(15, 15))
    p.drawLine(QPointF(15, 9), QPointF(9, 15))


def _contour(p):
    for rx, ry in ((9, 7), (6, 4.5), (3, 2)):
        p.drawEllipse(QPointF(12, 12), rx, ry)


def _displacement(p):
    pen = p.pen()
    pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(4, 20), QPointF(10, 14))
    pen.setStyle(Qt.SolidLine)
    p.setPen(pen)
    p.drawLine(QPointF(10, 14), QPointF(20, 4))
    p.drawPolyline(_pts(13, 4, 20, 4, 20, 11))


def _surface(outer_solid):
    def draw(p):
        pen = p.pen()
        solid, dashed = Qt.SolidLine, Qt.DashLine
        pen.setStyle(solid if outer_solid else dashed)
        p.setPen(pen)
        p.drawEllipse(QPointF(12, 12), 9, 9)
        pen.setStyle(dashed if outer_solid else solid)
        p.setPen(pen)
        p.drawEllipse(QPointF(12, 12), 5, 5)
    return draw


def _warning(p):
    p.drawPolygon(_pts(12, 3, 22, 20, 2, 20))
    p.drawLine(QPointF(12, 9), QPointF(12, 14))
    p.drawPoint(QPointF(12, 17))


_DRAWERS = {
    "save": _save, "close_project": _close_project, "fit": _fit,
    "cube": _cube, "turbine": _turbine, "step": _step,
    "dimensions": _dimensions, "material": _material, "wind": _wind,
    "air": _air, "mesh": _mesh, "play": _play, "stop": _stop,
    "contour": _contour, "displacement": _displacement,
    "outer": _surface(True), "inner": _surface(False), "warning": _warning,
}


def _render(name, color, size):
    ratio = 2  # crisp on high-DPI screens
    pix = QPixmap(size * ratio, size * ratio)
    pix.fill(Qt.transparent)
    pix.setDevicePixelRatio(ratio)

    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    drawer = _DRAWERS.get(name)
    if drawer:
        drawer(p)
    p.end()
    return pix


def ribbon_icon(name, size=26):
    """QIcon with a normal (light) and a disabled (muted) state."""
    icon = QIcon()
    icon.addPixmap(_render(name, COLORS["text"], size), QIcon.Normal)
    icon.addPixmap(_render(name, COLORS["text3"], size), QIcon.Disabled)
    return icon


ICON_NAMES = sorted(_DRAWERS)