"""Compact native Qt editor for section macro automation."""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QSizePolicy

from composition_automation import normalize_curve, curve_value, unit
from ui_themes import theme_palette


class MacroCurveEditor(QWidget):
    curveChanged = Signal(dict)

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.theme = theme_palette()
        self.curve = normalize_curve({"points": [[0, .5], [1, .5]]})
        self.selected = 0
        self.dragging = False
        self.position = None
        self.current_value = None
        self.axis_labels = ("START", "END")
        self.setMinimumWidth(140)
        self.setFixedHeight(104)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip("Double-click to add a point; drag to move. Right-click or Delete removes an interior point. "
                        "Arrow keys adjust the selected point. Horizontal axis: section start → end; vertical axis: 0–100%.")
        self.setAccessibleName("Macro automation curve")

    def set_curve(self, curve):
        if self.dragging:
            return
        self.curve = normalize_curve(curve)
        self.selected = min(self.selected, len(self.curve["points"]) - 1)
        self.update()

    def set_position(self, position, value=None):
        state = (position, value)
        if state != (self.position, self.current_value):
            self.position, self.current_value = state
            self.update()

    def plot_rect(self):
        return QRectF(self.rect()).adjusted(10, 8, -10, -19)

    def point_position(self, point):
        rect = self.plot_rect()
        return QPointF(rect.left() + point[0] * rect.width(), rect.bottom() - point[1] * rect.height())

    def _nearest(self, position):
        best = min(range(len(self.curve["points"])),
                   key=lambda i: (self.point_position(self.curve["points"][i]) - position).manhattanLength())
        return best if (self.point_position(self.curve["points"][best]) - position).manhattanLength() <= 13 else None

    def _changed(self):
        self.setAccessibleDescription(f"{len(self.curve['points'])} points; selected point "
                                      f"{self.curve['points'][self.selected][0]:.0%}, {self.curve['points'][self.selected][1]:.0%}")
        self.curveChanged.emit(deepcopy(self.curve))
        self.update()

    def _move(self, position):
        rect = self.plot_rect()
        points = self.curve["points"]
        x = unit((position.x() - rect.left()) / max(1, rect.width()))
        y = unit((rect.bottom() - position.y()) / max(1, rect.height()))
        if self.selected in (0, len(points) - 1):
            x = points[self.selected][0]
        else:
            x = max(points[self.selected - 1][0] + .001, min(points[self.selected + 1][0] - .001, x))
        point = [round(x, 6), round(y, 6)]
        if points[self.selected] != point:
            points[self.selected] = point
            self._changed()

    def mousePressEvent(self, event):
        index = self._nearest(event.position())
        if event.button() == Qt.RightButton:
            if index is not None and 0 < index < len(self.curve["points"]) - 1:
                self.curve["points"].pop(index)
                self.selected = min(index, len(self.curve["points"]) - 1)
                self._changed()
            event.accept()
        elif event.button() == Qt.LeftButton:
            self.setFocus()
            if index is not None:
                self.selected = index
                self.dragging = True
                self.update()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            self._move(event.position())
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self._move(event.position())
        self.dragging = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton or not self.plot_rect().contains(event.position()):
            return
        if self._nearest(event.position()) is not None or len(self.curve["points"]) >= 64:
            return
        rect = self.plot_rect()
        x = unit((event.position().x() - rect.left()) / rect.width())
        if any(abs(x - p[0]) < .002 for p in self.curve["points"]):
            return
        point = [x, unit((rect.bottom() - event.position().y()) / rect.height())]
        self.curve["points"].append(point)
        self.curve["points"].sort()
        self.selected = self.curve["points"].index(point)
        self._changed()

    def keyPressEvent(self, event):
        points = self.curve["points"]
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and 0 < self.selected < len(points) - 1:
            points.pop(self.selected)
            self.selected = min(self.selected, len(points) - 1)
            self._changed()
        elif event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            x, y = points[self.selected]
            step = .05 if event.modifiers() & Qt.ShiftModifier else .01
            x += step * ((event.key() == Qt.Key_Right) - (event.key() == Qt.Key_Left))
            y += step * ((event.key() == Qt.Key_Up) - (event.key() == Qt.Key_Down))
            self._move(self.point_position((x, y)))
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.plot_rect()
        theme = self.theme
        p.setPen(QPen(QColor(theme.border), 1))
        p.setBrush(QColor(theme.panel))
        p.drawRoundedRect(r, 4, 4)
        for x in (.25, .5, .75):
            p.drawLine(self.point_position((x, 0)), self.point_position((x, 1)))
        p.drawLine(self.point_position((0, .5)), self.point_position((1, .5)))
        color = QColor(self.color if self.isEnabled() else theme.muted)
        preview_curve = {**self.curve, "enabled": True}
        path = QPainterPath()
        for i in range(161):
            x = i / 160.
            point = self.point_position((x, curve_value(preview_curve, x)))
            path.moveTo(point) if i == 0 else path.lineTo(point)
        p.setPen(QPen(color, 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        for i, point in enumerate(self.curve["points"]):
            p.setBrush(color if i == self.selected else QColor(theme.panel))
            p.drawEllipse(self.point_position(point), 4, 4)
        if self.position is not None:
            x = unit(self.position)
            p.setPen(QPen(QColor(theme.text), 1, Qt.DashLine))
            p.drawLine(self.point_position((x, 0)), self.point_position((x, 1)))
            p.setBrush(QColor(theme.text))
            p.drawEllipse(self.point_position((x, self.current_value if self.current_value is not None else curve_value(self.curve, x))), 3, 3)
        p.setPen(QColor(theme.muted))
        p.drawText(QRectF(r.left(), r.bottom() + 3, r.width(), 14), Qt.AlignLeft, self.axis_labels[0])
        p.drawText(QRectF(r.left(), r.bottom() + 3, r.width(), 14), Qt.AlignRight, self.axis_labels[1])
        p.end()
