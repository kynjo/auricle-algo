"""Small source dots painted inside existing parameter captions, without reflow."""
from html import escape
import time
import weakref

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPalette
from PySide6.QtWidgets import QLabel, QMenu
from shiboken6 import isValid

from help_tooltips import copy_help

from parameter_sources import SOURCE_COLORS, SourceSnapshot, parameter_values, feedback_value


DOT_SIZE = 8
DOT_GAP = 3
_labels = weakref.WeakSet()


class ParameterSourceLabel(QLabel):
    def __init__(self, text, parent=None, *, binding=None):
        super().__init__(text, parent)
        self.binding = binding
        self.source_marks = ()
        self._source_state = None
        self._original_tooltip = ""
        self.setMinimumWidth(0)
        _labels.add(self)

    def contextMenuEvent(self, event):
        if self.binding is None:
            return super().contextMenuEvent(event)
        host = self.parentWidget()
        while host is not None and not hasattr(host, '_assign_composition_automation'):
            host = host.parentWidget()
        if host is None:
            return super().contextMenuEvent(event)
        menu = QMenu(self)
        assign = menu.addAction('Automate in Composition…')
        influences = menu.addAction('Parameter influences…')
        from section_automation import ARTICULATION_NUMERIC_KEYS
        macro_actions = {}
        if self.binding[1] in ARTICULATION_NUMERIC_KEYS:
            for source in ('energy', 'tension'):
                macro_actions[menu.addAction(f'Composition: link {source.title()}…')] = source
        chosen = menu.exec(event.globalPos())
        if chosen == assign: host._assign_composition_automation(*self.binding)
        elif chosen == influences: host._open_automation_influences(*self.binding)
        elif chosen in macro_actions: host._link_articulation_macro(*self.binding, macro_actions[chosen])
        menu.deleteLater()

    def set_base_tooltip(self, text):
        if text != self._original_tooltip:
            self._original_tooltip = text
            self._source_state = None
        if not self.source_marks:
            self.setToolTip(text)

    def set_sources(self, marks, values=None, feedback=None):
        state = (marks, values, feedback, self.text())
        if state == self._source_state:
            return
        self._source_state = state
        if not self.source_marks:
            self._original_tooltip = self.toolTip()
        self.source_marks = marks
        if not marks:
            self.setToolTip(self._original_tooltip)
            self.setAccessibleDescription("")
        else:
            rows = [self._original_tooltip, f"<b>{escape(self.text())}</b>"]
            if values is not None:
                base, current = values
                def formatted(value):
                    return f"{value:.4g}" if isinstance(value, float) else "—" if value is None else str(value)
                rows.append(f"Manual: {escape(formatted(base))} · Parameter: {escape(formatted(current))}")
            if feedback is not None:
                if values is None:
                    rows.append(f'Manual: {feedback.manual:.4g}')
                rows.append(f'{escape(feedback.mode)}: {feedback.effective:.4g}')
                if feedback.mode == "Output equivalent":
                    rows.append("The needle shows output influence; the short outer tick is the manual setting.")
            for mark in marks:
                state_text = "active" if mark.active else "assigned / bypassed"
                rows.append(f'<br><span style="color:{SOURCE_COLORS[mark.source]}">●</span> '
                            f'<b>{mark.source}</b> · {state_text}')
                rows.extend(escape(detail) for detail in mark.details)
            self.setToolTip("<br>".join(rows))
            self.setAccessibleDescription("; ".join(
                f'{mark.source}: ' + "; ".join(mark.details) for mark in marks))
        self.update()

    def paintEvent(self, event):
        if not self.source_marks:
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(self.font())
        rect = self.contentsRect()
        dots_width = len(self.source_marks) * (DOT_SIZE + DOT_GAP)
        available = max(0, rect.width() - dots_width - DOT_GAP)
        metrics = painter.fontMetrics()
        text = metrics.elidedText(self.text(), Qt.ElideRight, available)
        text_width = metrics.horizontalAdvance(text)
        total = text_width + DOT_GAP + dots_width - DOT_GAP
        x = rect.left()
        if self.alignment() & Qt.AlignHCenter:
            x += max(0, (rect.width() - total) // 2)
        elif self.alignment() & Qt.AlignRight:
            x += max(0, rect.width() - total)
        group = QPalette.Active if self.isEnabled() else QPalette.Disabled
        painter.setPen(self.palette().color(group, QPalette.WindowText))
        painter.drawText(QRectF(x, rect.top(), text_width, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
        x += text_width + DOT_GAP
        y = rect.center().y() - DOT_SIZE / 2 + .5
        for mark in self.source_marks:
            color = QColor(SOURCE_COLORS[mark.source])
            painter.setPen(QPen(color, 1))
            painter.setBrush(color if mark.active else Qt.NoBrush)
            # Include the stroke in the requested eight-pixel footprint.
            painter.drawEllipse(QRectF(x + .5, y + .5, DOT_SIZE - 1, DOT_SIZE - 1))
            x += DOT_SIZE + DOT_GAP
        painter.end()


def source_label(text, control):
    label = ParameterSourceLabel(text, binding=getattr(control, "_auricle_parameter", None))
    label._control_ref = weakref.ref(control)
    copy_help(control, label)
    return label


def update_parameter_sources(host, *, force=False):
    """Use the existing UI heartbeat; never wait for a busy MIDI worker."""
    now = time.monotonic()
    if not force and now - getattr(host, "_source_refresh_at", 0.) < .05:
        return
    # The registry contains only source captions, not thousands of unrelated
    # Qt children. Weak entries disappear when an Inspector is replaced.
    labels = [label for label in list(_labels) if isValid(label)
              and label.binding is not None and host.isAncestorOf(label)
              and (force or label.isVisible())]
    if not labels:
        return
    lock = host.transport._transport_lock
    if not lock.acquire(blocking=False):
        return
    state_lock = host.transport._state_lock
    if not state_lock.acquire(blocking=False):
        lock.release()
        return
    try:
        snapshot = SourceSnapshot(host.engine)
        states = {}
        for label in labels:
            binding = label.binding
            if binding not in states:
                marks = snapshot.marks(*binding)
                states[binding] = (marks, parameter_values(host.engine, *binding) if marks else None,
                                   feedback_value(snapshot, *binding, marks))
    finally:
        state_lock.release()
        lock.release()
    host._source_refresh_at = now
    for label in labels:
        label.set_sources(*states[label.binding])
        feedback = states[label.binding][2]
        ref = getattr(label, "_control_ref", None)
        control = ref() if ref is not None else None
        if feedback is not None and control is not None and isValid(control) and hasattr(control, "set_runtime_value"):
            control.set_runtime_value(feedback.manual, feedback.effective)
        values = states[label.binding][1]
        if values is not None and control is not None and isValid(control) and hasattr(control, "set_runtime_choice"):
            control.set_runtime_choice(*values)
    bar = getattr(host, "global_macro_bar", None)
    if bar is not None:
        for index, key in enumerate(("energy", "tension", "density", "variation")):
            state = states.get((None, key))
            if state is None or state[2] is None or bar.sliders[index].isSliderDown():
                continue
            feedback = state[2]
            slider = bar.sliders[index]
            previous = slider.blockSignals(True)
            try:
                slider.setValue(round(feedback.effective * 100))
            finally:
                slider.blockSignals(previous)
            bar.values[index].setText(f"{round(feedback.effective * 100)}%")
