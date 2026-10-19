"""Compact inline Dialogue controls, separate from the main window module."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QComboBox, QSizePolicy

from instrument_dialogue import METERS, REPLIES, settings


class DialogueTimeline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(25)
        self.state = None
        self.colors = ('#448cbc', '#ad72cf')
        self.setAccessibleName('Dialogue call and response timeline')

    def paintEvent(self, _event):
        if not self.state:
            return
        s = self.state
        painter = QPainter(self)
        width = self.width()
        painter.fillRect(self.rect(), self.palette().base())
        scale = width / s['total']
        for start, length, label, color in (
            (0, s['call'], 'CALL', self.colors[0]),
            (s['call']+s['gap'], s['response'], 'RESPONSE', self.colors[1]),
        ):
            rect = QRectF(start*scale, 0, length*scale, self.height())
            fill = QColor(color)
            painter.fillRect(rect, fill)
            painter.setPen(QColor('#10121a') if fill.lightnessF() > .52 else QColor('white'))
            painter.drawText(rect, Qt.AlignCenter, label)
        if s.get('running') and s.get('active'):
            x = min(width-1, round(s['position']*scale))
            painter.setPen(QPen(QColor('#10121a'), 4))
            painter.drawLine(x, 0, x, self.height())
            painter.setPen(QPen(QColor('white'), 2))
            painter.drawLine(x, 0, x, self.height())


class DialogueControls(QWidget):
    def __init__(self, row, stepper_factory):
        super().__init__(row)
        self.row = row
        self._updating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        self.controls = {}
        for column, (key, label) in enumerate((('call_bars', 'Call · bars'), ('response_bars', 'Response · bars'),
                                              ('meter', 'Meter'), ('gap_beats', 'Pause · beats'),
                                              ('reply', 'Reply'), ('follow', 'Follow · %'))):
            caption = QLabel(label); caption.setObjectName('muted')
            grid.addWidget(caption, 0, column)
            if key in ('meter', 'reply'):
                control = QComboBox()
                control.addItems(METERS if key == 'meter' else REPLIES)
                control.currentTextChanged.connect(self.changed)
            elif key == 'gap_beats':
                control = stepper_factory()
                control.setRange(0, 4); control.setSingleStep(.25); control.setDecimals(2)
                control.valueChanged.connect(self.changed)
            else:
                control = stepper_factory()
                control.setRange(0, 100) if key == 'follow' else control.setRange(1, 8)
                control.valueChanged.connect(self.changed)
            control.setAccessibleName(f'Dialogue {row.relation.id}: {label}')
            if not isinstance(control, QComboBox):
                control.set_accessible_label(f'Dialogue {row.relation.id}: {label}')
                control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grid.addWidget(control, 1, column)
            grid.setColumnStretch(column, 2 if key == 'reply' else 1)
            self.controls[key] = control
        self.controls['gap_beats'].setToolTip('Quarter-note beats of silence between each turn, including the loop boundary.')
        self.controls['reply'].setToolTip('Own phrase: original material. Echo: call contour and accents. Contrast: inverted contour and accents. Reply rhythm stays its own; CHORD/PAD/DRUM follow accents only.')
        self.controls['follow'].setToolTip('How much of the call contour and accents is used in the reply. 0 keeps the original phrase.')
        layout.addLayout(grid)
        self.timeline = DialogueTimeline(self)
        layout.addWidget(self.timeline)
        self.status = QLabel()
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.sync()

    def sync(self):
        self._updating = True
        config = settings(self.row.relation)
        try:
            for key, control in self.controls.items():
                if isinstance(control, QComboBox):
                    control.setCurrentText(config[key])
                else:
                    control.setValue(round(config[key]*100) if key == 'follow' else config[key])
        finally:
            self._updating = False
        self.controls['follow'].setEnabled(config['reply'] != 'Own phrase')

    def changed(self, *_):
        if self._updating:
            return
        host, relation = self.row.editor.host, self.row.relation
        if not any(r is relation for r in host.project.relations):
            return
        with host.transport._state_lock:
            config = settings(relation)
            for key, control in self.controls.items():
                config[key] = control.currentText() if isinstance(control, QComboBox) else control.value() / (100 if key == 'follow' else 1)
            relation.parameters = {**(relation.parameters if isinstance(relation.parameters, dict) else {}), **config}
        host._mark_dirty()
        self.controls['follow'].setEnabled(config['reply'] != 'Own phrase')
        self.row.update_summary()
        self.update_runtime()

    def update_runtime(self):
        host, relation = self.row.editor.host, self.row.relation
        if relation.algorithm != 'Dialogue':
            return
        with host.transport._state_lock:
            state = host.engine.dialogue_runtime.status(relation, host.engine.clock.position_beats)
            running = host.transport.running
        if 'total' not in state:
            return
        self.timeline.state = {**state, 'running': running}
        self.timeline.update()
        if not state['active']:
            text = state['reason']
        else:
            name = self.row.source.currentText() if state['phase'] == 'Call' else self.row.dest.currentText()
            who = 'Both wait' if state['phase'] == 'Pause' else name
            text = f"{'PLAY' if running else 'STOP'} · {state['phase']}: {who} · {state['remaining']:.1f} beats left"
        if self.status.text() != text:
            self.status.setText(text)
