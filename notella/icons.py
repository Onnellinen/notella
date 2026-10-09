"""Small palette-aware toolbar icons, without external icon dependencies."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF


def toolbar_icon(name: str, color: QColor) -> QIcon:
    image = QPixmap(24, 24)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(color, 1.8))
    if name in ("bold", "italic", "underline"):
        font = QFont("Sans Serif", 14)
        font.setBold(name == "bold")
        font.setItalic(name == "italic")
        painter.setFont(font)
        painter.drawText(QRectF(1, 0, 22, 22), Qt.AlignmentFlag.AlignCenter, name[0].upper())
        if name == "underline":
            painter.drawLine(6, 21, 18, 21)
    elif name in ("bullets", "numbers"):
        painter.setFont(QFont("Sans Serif", 7))
        for index, y in enumerate((5, 12, 19), 1):
            painter.drawLine(10, y, 22, y)
            if name == "bullets":
                painter.setBrush(color)
                painter.drawEllipse(QPointF(4, y), 1.2, 1.2)
            else:
                painter.drawText(QRectF(0, y - 5, 8, 10), Qt.AlignmentFlag.AlignCenter, str(index))
    elif name == "pin":
        painter.drawPolyline(QPolygonF([
            QPointF(7, 3), QPointF(17, 3), QPointF(15, 7),
            QPointF(15, 11), QPointF(19, 15), QPointF(5, 15),
            QPointF(9, 11), QPointF(9, 7), QPointF(7, 3),
        ]))
        painter.drawLine(12, 15, 12, 22)
    elif name == "close":
        painter.drawLine(6, 6, 18, 18)
        painter.drawLine(18, 6, 6, 18)
    elif name == "color":
        painter.setPen(QPen(QColor("#505050"), 1))
        painter.setBrush(color)
        painter.drawRect(QRectF(2, 2, 20, 20))
    else:
        painter.end()
        raise ValueError(f"Unknown toolbar icon: {name}")
    painter.end()
    return QIcon(image)
