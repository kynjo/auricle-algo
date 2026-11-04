"""Project-wide harmonic plan controls and editable chord progression."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QComboBox, QDialog, QScrollArea, QSpinBox, QSizePolicy)
from help_tooltips import bind_help, bind_attributes

from harmonic_plan import (NOTES, QUALITIES, METERS, PRESETS, normalized, preset,
                           chord_name, chord_intervals, scale_chords, shared_tones)
from generators import SCALE_NAMES, scale_intervals


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
        edit = QPushButton('Harmony editor…')
        edit.clicked.connect(self.open_editor)
        row.addWidget(edit)
        layout.addLayout(row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setMinimumWidth(0)
        self.summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.summary)
        self.sync()
        bind_attributes(self, "harmony")

    def sync(self):
        self._draft_config = normalized(deepcopy(self.host.project.harmonic_plan))
        config = self._draft_config
        self._syncing = True
        self.enabled.setChecked(config['enabled'])
        self.meter.setCurrentText(config['meter'])
        self.loop.setChecked(config['loop'])
        self.summary.setText(' → '.join(f'{chord_name(c)} · {c["bars"]} bar' + ('s' if c['bars'] != 1 else '')
                                       for c in config['chords']) or 'No chords yet · Edit chords to create a plan')
        self._syncing = False
        self.update_runtime()
        if self.editor is not None: self.editor.rebuild()

    def apply(self, config):
        project = self.host.project
        snapshot = normalized(deepcopy(config))
        self._draft_config = snapshot
        def commit():
            if self.host.project is not project:
                return
            project.harmonic_plan = snapshot
            self.host.engine.harmonic_runtime.reset()
        self.host._mark_pending_dirty()
        self.host.transport.enqueue_gui_command(
            commit, key=("harmonic-plan", id(project)),
            notification={"dirty": True, "harmonic": True}, label="Harmonic Plan edit")
        self._syncing = True
        self.enabled.setChecked(snapshot['enabled'])
        self.meter.setCurrentText(snapshot['meter'])
        self.loop.setChecked(snapshot['loop'])
        self._syncing = False
        self.summary.setText(' → '.join(f'{chord_name(c)} · {c["bars"]} bar' + ('s' if c['bars'] != 1 else '')
                                       for c in snapshot['chords']) or 'No chords yet · Edit chords to create a plan')

    def change(self, key, value):
        if self._syncing: return
        config = normalized(deepcopy(getattr(self, '_draft_config', self.host.project.harmonic_plan)))
        if key == 'enabled' and value and not config['chords']:
            config['chords'] = preset()['chords']
        config[key] = value
        self.apply(config)
        if self.editor is not None: self.editor.rebuild()

    def update_runtime(self):
        lock = self.host.transport._transport_lock
        if not lock.acquire(blocking=False):
            return
        try:
            chord = self.host.engine.harmonic_runtime.at(self.host.engine.clock.position_beats)
        finally:
            lock.release()
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
        self.setWindowTitle('Harmony & chord transitions')
        self.resize(950, 570)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.plan_enabled = QCheckBox('Follow plan')
        self.plan_enabled.setToolTip('Enable the harmonic plan for blocks that have Follow harmonic plan enabled.')
        self.plan_enabled.toggled.connect(lambda value: self.panel.change('enabled', value))
        top.addWidget(self.plan_enabled)
        self.presets = QComboBox()
        self.presets.addItems(PRESETS)
        bind_help(self.presets, "presets", "harmony")
        self.presets.setAccessibleName('Chord progression preset')
        top.addWidget(self.presets, 1)
        use = QPushButton('Use preset')
        use.clicked.connect(self.use_preset)
        top.addWidget(use)
        layout.addLayout(top)
        config = normalized(deepcopy(getattr(panel, '_draft_config', panel.host.project.harmonic_plan)))
        palette = QHBoxLayout()
        palette.addWidget(QLabel('Scale palette'))
        self.palette_root = QComboBox(); self.palette_root.addItems(NOTES)
        self.palette_root.setCurrentIndex(config.get('palette_root', int(panel.host.project.root_note) % 12))
        self.palette_root.setAccessibleName('Scale palette root')
        self.palette_root.setToolTip('Root used to build the palette. Does not change the global key.')
        palette.addWidget(self.palette_root)
        self.palette_scale = QComboBox(); self.palette_scale.addItems(SCALE_NAMES)
        self.palette_scale.setCurrentText(config.get('palette_scale', panel.host.project.scale))
        self.palette_scale.setAccessibleName('Scale palette')
        self.palette_scale.setToolTip('Uses the same scale library as the generators; does not change their scale.')
        palette.addWidget(self.palette_scale, 1)
        self.palette_size = QComboBox(); self.palette_size.addItems(['Triads', 'Sevenths'])
        self.palette_size.setAccessibleName('Scale chord size')
        self.palette_size.setToolTip('Stack every other scale degree into three or four notes.')
        palette.addWidget(self.palette_size)
        layout.addLayout(palette)
        picker = QHBoxLayout()
        self.candidates = QComboBox()
        self.candidates.setAccessibleName('Scale chord suggestions')
        self.candidates.setToolTip('Degrees are built from the selected scale. Common tones compare each option with the last chord.')
        picker.addWidget(self.candidates, 1)
        add = QPushButton('+ Add selected')
        add.setToolTip('Append the selected scale chord to the progression.')
        add.clicked.connect(self.add)
        picker.addWidget(add)
        layout.addLayout(picker)
        self.palette_notes = QLabel()
        self.palette_notes.setWordWrap(True)
        layout.addWidget(self.palette_notes)
        for control in (self.palette_root, self.palette_scale, self.palette_size):
            control.currentIndexChanged.connect(self.refresh_palette)
        hint = QLabel('Each row: bar · root · quality · duration · inversion · transition. '
                      'Use Replace to put the selected scale chord in that row. Edits apply on the next note.\n'
                      'Smooth follows the previous voicing; Fixed uses the authored voicing and register. '
                      'The plan is global across Composition sections.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        self.refresh_palette()
        self.rebuild()

    def refresh_palette(self, *_):
        current = self.candidates.currentIndex()
        root, scale = self.palette_root.currentIndex(), self.palette_scale.currentText()
        chords = scale_chords(root, scale, 4 if self.palette_size.currentIndex() else 3)
        config = normalized(deepcopy(getattr(self.panel, '_draft_config', self.panel.host.project.harmonic_plan)))
        previous = config['chords'][-1] if config['chords'] else None
        scores = [shared_tones(previous, chord) for chord in chords]
        best = max(scores, default=0)
        self.candidates.blockSignals(True)
        self.candidates.clear()
        for i, chord in enumerate(chords):
            tones = ' '.join(NOTES[(chord['root'] + n) % 12] for n in chord_intervals(chord))
            hint = f' · {scores[i]} common' if previous else ''
            if previous and best and scores[i] == best: hint += ' ★'
            self.candidates.addItem(f'{i+1}. {chord_name(chord)}  ({tones}){hint}', chord)
        self.candidates.setCurrentIndex(max(0, min(current, len(chords)-1)))
        self.candidates.blockSignals(False)
        self.palette_notes.setText('Scale: ' + ' · '.join(NOTES[(root + n) % 12] for n in scale_intervals(scale)) +
                                   '     ★ most common tones with the last chord')

    def palette_settings(self, config):
        config['palette_root'] = self.palette_root.currentIndex()
        config['palette_scale'] = self.palette_scale.currentText()

    def rebuild(self):
        old = self.scroll.takeWidget()
        if old is not None: old.deleteLater()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(4)
        config = normalized(deepcopy(getattr(self.panel, "_draft_config", self.panel.host.project.harmonic_plan)))
        self.plan_enabled.blockSignals(True)
        self.plan_enabled.setChecked(config['enabled'])
        self.plan_enabled.blockSignals(False)
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
            quality = QComboBox(); quality.addItems(QUALITIES)
            if chord['quality'] == 'custom': quality.addItem('custom')
            quality.setCurrentText(chord['quality'])
            quality.setAccessibleName(f'Chord {index+1} quality')
            quality.currentTextChanged.connect(lambda value, i=index: self.edit(i, 'quality', value))
            row.addWidget(quality, 1)
            bars = QSpinBox(); bars.setRange(1, 64); bars.setValue(chord['bars']); bars.setSuffix(' bars')
            bars.setKeyboardTracking(False)
            bars.setAccessibleName(f'Chord {index+1} bars')
            bars.valueChanged.connect(lambda value, i=index: self.edit(i, 'bars', value))
            row.addWidget(bars)
            inversion = QComboBox()
            inversion.addItem('Block inversion', None)
            for value in range(-3, 4): inversion.addItem(f'Inversion {value:+d}', value)
            inversion.setCurrentIndex(inversion.findData(chord.get('inversion')))
            inversion.setAccessibleName(f'Chord {index+1} inversion')
            inversion.setToolTip('Block inversion follows each block’s Inversion knob. A number overrides it for this chord.')
            inversion.currentIndexChanged.connect(lambda _value, i=index, w=inversion: self.edit(i, 'inversion', w.currentData()))
            row.addWidget(inversion)
            transition = QComboBox(); transition.addItem('Smooth', 'smooth'); transition.addItem('Fixed', 'fixed')
            transition.setCurrentIndex(transition.findData(chord.get('transition', 'smooth')))
            transition.setAccessibleName(f'Chord {index+1} transition')
            transition.setToolTip('Smooth chooses a voicing near the previous chord. Fixed starts from the authored inversion and register.')
            transition.currentIndexChanged.connect(lambda _value, i=index, w=transition: self.edit(i, 'transition', w.currentData()))
            row.addWidget(transition)
            replace = QPushButton('Replace')
            replace.setAccessibleName(f'Replace chord {index+1} with selected scale chord')
            replace.setToolTip('Replace this chord with the selected scale suggestion, retaining duration and transition settings.')
            replace.clicked.connect(lambda _=False, i=index: self.replace(i))
            row.addWidget(replace)
            for control, key in ((root, "root"), (quality, "quality"), (bars, "bars")):
                bind_help(control, key, "harmony")
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
        config = normalized(deepcopy(getattr(self.panel, "_draft_config", self.panel.host.project.harmonic_plan)))
        if index >= len(config['chords']): return
        chord = config['chords'][index]
        was_custom = chord['quality'] == 'custom'
        if value is None: chord.pop(key, None)
        else: chord[key] = value
        if key == 'quality' and value != 'custom':
            chord.pop('intervals', None)
            chord.pop('exact', None)
        self.panel.apply(config)
        self.refresh_palette()
        if key == 'quality' and was_custom and value != 'custom':
            self.rebuild()
            return
        # Keep the editing widgets alive. Update only the bar labels.
        layout = self.scroll.widget().layout()
        bar = 1
        for i, chord in enumerate(config['chords']):
            layout.itemAt(i).layout().itemAt(0).widget().setText(str(bar))
            bar += chord['bars']

    def add(self):
        config = normalized(deepcopy(getattr(self.panel, "_draft_config", self.panel.host.project.harmonic_plan)))
        if len(config['chords']) >= 128: return
        chord = self.candidates.currentData()
        if not chord: return
        config['chords'].append(deepcopy(chord))
        self.palette_settings(config)
        self.panel.apply(config); self.refresh_palette(); self.rebuild()

    def replace(self, index):
        config = normalized(deepcopy(getattr(self.panel, '_draft_config', self.panel.host.project.harmonic_plan)))
        candidate = self.candidates.currentData()
        if not candidate or not 0 <= index < len(config['chords']): return
        previous = config['chords'][index]
        chord = deepcopy(candidate)
        for key in ('bars', 'inversion', 'transition'):
            if key in previous: chord[key] = previous[key]
        config['chords'][index] = chord
        self.palette_settings(config)
        self.panel.apply(config); self.refresh_palette(); self.rebuild()

    def move(self, index, delta):
        config = normalized(deepcopy(getattr(self.panel, "_draft_config", self.panel.host.project.harmonic_plan)))
        chords = config['chords']
        if not 0 <= index < len(chords): return
        if delta == 0: chords.pop(index)
        elif 0 <= index+delta < len(chords): chords[index], chords[index+delta] = chords[index+delta], chords[index]
        self.panel.apply(config); self.refresh_palette(); self.rebuild()

    def use_preset(self):
        config = normalized(deepcopy(getattr(self.panel, "_draft_config", self.panel.host.project.harmonic_plan)))
        config['chords'] = preset(self.presets.currentText())['chords']
        config['enabled'] = True
        self.panel.apply(config); self.refresh_palette(); self.rebuild()
