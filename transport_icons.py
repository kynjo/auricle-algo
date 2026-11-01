"""Shared, theme-aware transport glyphs for the header and Composition."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QBrush, QIcon


def transport_icon(kind: str, color: str, size: int = 22) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(color)))
    if kind == "play":
        path = QPainterPath()
        path.moveTo(size * .28, size * .18)
        path.lineTo(size * .78, size * .50)
        path.lineTo(size * .28, size * .82)
        path.closeSubpath()
        painter.drawPath(path)
    else:
        margin = size * .24
        painter.drawRoundedRect(margin, margin, size - 2 * margin, size - 2 * margin, 2, 2)
    painter.end()
    return QIcon(pix)
