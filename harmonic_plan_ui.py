"""Compact Perform overview and an immediately editable chord list."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QComboBox, QDialog, QScrollArea, QSpinBox, QSizePolicy)
from harmonic_plan import NOTES, QUALITIES, METERS, PRESETS, normalized, preset, chord_name


class HarmonicPlanPanel(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.editor = None
        self._syncing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        row = QHBoxLayout()
        self.enabled = QCheckBox('Follow plan')
        self.enabled.setToolTip('CHORD/PAD play these chords; BASS/MELODY use their tones. DRUM is unchanged.')
        self.enabled.toggled.connect(lambda value: self.change('enabled', value))
        row.addWidget(self.enabled)
        self.meter = QComboBox()
        self.meter.addItems(METERS)
        self.meter.setAccessibleName('Harmonic plan meter')
        self.meter.setToolTip('Bar size for harmony, in quarter-note beats. Independent of a Drum Kit meter.')
        self.meter.currentTextChanged.connect(lambda value: self.change('meter', value))
        row.addWidget(self.meter)
        self.loop = QCheckBox('Loop')
        self.loop.setToolTip('When off, hold the last chord after the plan ends.')
        self.loop.toggled.connect(lambda value: self.change('loop', value))
        row.addWidget(self.loop)
        self.current = QLabel('Off')
        row.addWidget(self.current, 1)
        edit = QPushButton('Edit chords…')
        edit.clicked.connect(self.open_editor)
        row.addWidget(edit)
        layout.addLayout(row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setMinimumWidth(0)
        self.summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.summary)
        self.sync()

    def sync(self):
        self._syncing = True
        config = normalized(self.host.project.harmonic_plan)
        self.enabled.setChecked(config['enabled'])
        self.meter.setCurrentText(config['meter'])
        self.loop.setChecked(config['loop'])
        self.summary.setText(' → '.join(f'{chord_name(c)} · {c["bars"]} bar' + ('s' if c['bars'] != 1 else '')
                                       for c in config['chords']) or 'No chords yet · Edit chords to create a plan')
        self._syncing = False
        self.update_runtime()
        if self.editor is not None: self.editor.rebuild()

    def apply(self, config):
        with self.host.transport._state_lock:
            self.host.project.harmonic_plan = normalized(config)
            self.host.engine.harmonic_runtime.reset()
        self.host._mark_dirty()
        self._syncing = True
        self.enabled.setChecked(config['enabled'])
        self.meter.setCurrentText(config['meter'])
        self.loop.setChecked(config['loop'])
        self._syncing = False
        current = normalized(config)
        self.summary.setText(' → '.join(f'{chord_name(c)} · {c["bars"]} bar' + ('s' if c['bars'] != 1 else '')
                                       for c in current['chords']) or 'No chords yet · Edit chords to create a plan')
        self.update_runtime()

    def change(self, key, value):
        if self._syncing: return
        config = normalized(self.host.project.harmonic_plan)
        if key == 'enabled' and value and not config['chords']:
            config['chords'] = preset()['chords']
        config[key] = value
        self.apply(config)
        if self.editor is not None: self.editor.rebuild()

    def update_runtime(self):
        with self.host.transport._state_lock:
            chord = self.host.engine.harmonic_runtime.at(self.host.engine.clock.position_beats)
        if chord is None:
            self.current.setText('Off' if not self.enabled.isChecked() else 'Add chords')
        else:
            self.current.setText(f'Bar {chord["bar"]} · {chord["name"]}' + (' · hold' if chord['held'] else ''))

    def open_editor(self):
        if self.editor is None:
            self.editor = HarmonicPlanEditor(self)
            self.editor.setAttribute(Qt.WA_DeleteOnClose)
            self.editor.destroyed.connect(lambda: setattr(self, 'editor', None))
        self.editor.show()
        self.editor.raise_()


class HarmonicPlanEditor(QDialog):
    def __init__(self, panel):
        super().__init__(panel.host)
        self.panel = panel
        self.setWindowTitle('Harmonic plan')
        self.resize(550, 370)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.presets = QComboBox()
        self.presets.addItems(PRESETS)
        self.presets.setAccessibleName('Chord progression preset')
        top.addWidget(self.presets, 1)
        use = QPushButton('Use preset')
        use.clicked.connect(self.use_preset)
        top.addWidget(use)
        add = QPushButton('+ Add')
        add.clicked.connect(self.add)
        top.addWidget(add)
        layout.addLayout(top)
        hint = QLabel('Root / quality / duration in bars. Changes take effect on the next note.\n'
                      'Explicit chord names are independent of KEY/SCALE. A seventh chord keeps all four notes.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        self.rebuild()

    def rebuild(self):
        old = self.scroll.takeWidget()
        if old is not None: old.deleteLater()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(4)
        config = normalized(self.panel.host.project.harmonic_plan)
        bar = 1
        for index, chord in enumerate(config['chords']):
            row = QHBoxLayout()
            label = QLabel(str(bar))
            label.setMinimumWidth(30)
            row.addWidget(label)
            root = QComboBox(); root.addItems(NOTES); root.setCurrentIndex(chord['root'])
            root.setAccessibleName(f'Chord {index+1} root')
            root.currentIndexChanged.connect(lambda value, i=index: self.edit(i, 'root', value))
            row.addWidget(root)
            quality = QComboBox(); quality.addItems(QUALITIES); quality.setCurrentText(chord['quality'])
            quality.setAccessibleName(f'Chord {index+1} quality')
            quality.currentTextChanged.connect(lambda value, i=index: self.edit(i, 'quality', value))
            row.addWidget(quality, 1)
            bars = QSpinBox(); bars.setRange(1, 64); bars.setValue(chord['bars']); bars.setSuffix(' bars')
            bars.setKeyboardTracking(False)
            bars.setAccessibleName(f'Chord {index+1} bars')
            bars.valueChanged.connect(lambda value, i=index: self.edit(i, 'bars', value))
            row.addWidget(bars)
            for title, delta in (('↑', -1), ('↓', 1), ('×', 0)):
                button = QPushButton(title); button.setFixedWidth(30)
                button.setAccessibleName(('Remove' if delta == 0 else 'Move') + f' chord {index+1}')
                button.setEnabled(delta == 0 or 0 <= index+delta < len(config['chords']))
                button.clicked.connect(lambda _=False, i=index, d=delta: self.move(i, d))
                row.addWidget(button)
            layout.addLayout(row)
            bar += chord['bars']
        if not config['chords']: layout.addWidget(QLabel('Click + Add to create the first chord.'))
        layout.addStretch()
        self.scroll.setWidget(page)

    def edit(self, index, key, value):
        config = normalized(self.panel.host.project.harmonic_plan)
        if index >= len(config['chords']): return
        config['chords'][index][key] = value
        self.panel.apply(config)
        # Keep the editing widgets alive. Update only the bar labels.
        layout = self.scroll.widget().layout()
        bar = 1
        for i, chord in enumerate(config['chords']):
            layout.itemAt(i).layout().itemAt(0).widget().setText(str(bar))
            bar += chord['bars']

    def add(self):
        config = normalized(self.panel.host.project.harmonic_plan)
        if len(config['chords']) >= 128: return
        config['chords'].append(deepcopy(config['chords'][-1]) if config['chords'] else {'root': 0, 'quality': 'major', 'bars': 1})
        self.panel.apply(config); self.rebuild()

    def move(self, index, delta):
        config = normalized(self.panel.host.project.harmonic_plan)
        chords = config['chords']
        if not 0 <= index < len(chords): return
        if delta == 0: chords.pop(index)
        elif 0 <= index+delta < len(chords): chords[index], chords[index+delta] = chords[index+delta], chords[index]
        self.panel.apply(config); self.rebuild()

    def use_preset(self):
        config = normalized(self.panel.host.project.harmonic_plan)
        config['chords'] = preset(self.presets.currentText())['chords']
        config['enabled'] = True
        self.panel.apply(config); self.rebuild()
