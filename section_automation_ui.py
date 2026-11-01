"""Compact section automation editor. Edits use the existing transport queue."""
from __future__ import annotations

from copy import deepcopy
from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QFrame, QStackedWidget, QSizePolicy,
)

from section_automation import (parameter_specs, make_track, operation_range, timing_for,
                                entities, MAX_TRACKS, curve_range, effective_operation, parameter_curve)
from composition_automation import normalize_curve, curve_value, unit
from composition_curve_ui import MacroCurveEditor
from parameter_influence_ui import InfluenceDialog, formatted
from help_tooltips import bind_help
from ui_themes import theme_palette

TIMING_NAMES = {'auto': 'Auto', 'continuous': 'Continuous', 'step': '1/16', 'beat': 'Beat',
                'bar': 'Bar', 'cycle': 'Source cycle', 'section': 'Section start'}


class ParameterCurveEditor(MacroCurveEditor):
    selectionChanged = Signal()
    editFinished = Signal()

    def __init__(self, parent=None):
        super().__init__('#55c5ad', parent)
        self.low, self.high, self.duration = 0., 1., 4.
        self.integer = False
        self.boolean = False
        self.snap = True
        self.setAccessibleName('Selected parameter automation curve')
        bind_help(self, 'curve', 'automation')

    def plot_rect(self):
        return QRectF(self.rect()).adjusted(49, 8, -12, -20)

    def _move(self, position):
        if self.snap and self.duration > 0:
            rect = self.plot_rect()
            x = max(0., min(1., (position.x() - rect.left()) / max(1., rect.width())))
            y = max(0., min(1., (rect.bottom() - position.y()) / max(1., rect.height())))
            x = round(x * self.duration * 4) / (self.duration * 4)
            position = self.point_position((x, y))
        rect = self.plot_rect()
        points = self.curve['points']
        x = unit((position.x() - rect.left()) / max(1., rect.width()))
        y = unit((rect.bottom() - position.y()) / max(1., rect.height()))
        if self.integer:
            span = self.high - self.low
            value = self.low + y * span
            value = int(value >= .5) if self.boolean else round(value)
            y = unit((value - self.low) / span) if span else .5
        if self.selected in (0, len(points) - 1): x = points[self.selected][0]
        else: x = max(points[self.selected - 1][0] + .001, min(points[self.selected + 1][0] - .001, x))
        point = [round(x, 12), round(y, 12)]
        if points[self.selected] != point:
            points[self.selected] = point
            self._changed()
        self.selectionChanged.emit()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.selectionChanged.emit()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if self.snap and self.curve['points']:
            self._move(self.point_position(self.curve['points'][self.selected]))
        self.selectionChanged.emit()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.editFinished.emit()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QColor(self.theme.muted))
        rect = self.plot_rect()
        painter.drawText(QRectF(1, rect.top(), 44, 15), Qt.AlignRight, f'{self.high:.4g}')
        painter.drawText(QRectF(1, rect.bottom() - 14, 44, 15), Qt.AlignRight, f'{self.low:.4g}')
        painter.end()


class DestinationPicker(QDialog):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle('Add parameter automation')
        self.resize(460, 460)
        layout = QVBoxLayout(self)
        self.owner = QComboBox()
        for block in entities(panel.host.project):
            self.owner.addItem(panel.entity_name(block.id), block.id)
        if panel.owner_filter.currentData() is not None:
            self.owner.setCurrentIndex(self.owner.findData(panel.owner_filter.currentData()))
        self.search = QLineEdit(); self.search.setPlaceholderText('Find a parameter…')
        self.list = QListWidget()
        self.note = QLabel(''); self.note.setWordWrap(True); self.note.setObjectName('muted')
        layout.addWidget(self.owner); layout.addWidget(self.search); layout.addWidget(self.list, 1); layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText('Add / open')
        layout.addWidget(buttons)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.owner.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.list.currentItemChanged.connect(self.describe)
        for widget in (self.owner, self.search, self.list):
            bind_help(widget, 'destination', 'automation')
        self.refresh(); self.search.setFocus()

    def refresh(self):
        self.list.clear()
        owner = self.panel.host.get_entity(self.owner.currentData())
        if owner is None:
            return
        query = self.search.text().casefold()
        for key, spec in sorted(parameter_specs(self.panel.host.engine, owner).items(), key=lambda pair: pair[1].label.casefold()):
            suffix = ' · ' + '/'.join(spec.generators) if spec.generators else ''
            label = spec.label + suffix
            if query not in (label + ' ' + key).casefold():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            item.setToolTip(key + ('\nAvailable when this generator is active.' if spec.generators else ''))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def describe(self, item, _previous=None):
        if item is None:
            self.note.setText('No matching parameters.'); return
        owner = self.panel.host.get_entity(self.owner.currentData())
        spec = parameter_specs(self.panel.host.engine, owner)[item.data(Qt.UserRole)]
        text = ('Choice/text snapshot; applied at a musical boundary.' if spec.discrete else
                f'Range {spec.low:g}…{spec.high:g}' + (f' {spec.unit}' if spec.unit else '') +
                (' · integer.' if spec.integer or spec.boolean else ' · decimal.'))
        self.note.setText(text + ' Auto timing: ' + TIMING_NAMES[timing_for({'timing': 'auto'}, spec, owner)] + '.')

    def destination(self):
        item = self.list.currentItem()
        return (self.owner.currentData(), item.data(Qt.UserRole)) if item is not None else None


class SectionAutomationPanel(QWidget):
    def __init__(self, planner):
        super().__init__()
        self.planner, self.host = planner, planner.host
        self._syncing = False
        self._section_id = None
        self._selected_id = None
        self._table_signature = None
        self._details_signature = None
        self._loaded_spec = None
        self._pending_project = None
        self.setObjectName('sectionParameterAutomation')
        root = QVBoxLayout(self); root.setContentsMargins(6, 6, 6, 6); root.setSpacing(5)
        top = QHBoxLayout(); top.setSpacing(5)
        self.owner_filter = QComboBox(); self.owner_filter.setMinimumWidth(120); self.owner_filter.setMaximumWidth(260)
        self.search = QLineEdit(); self.search.setPlaceholderText('Filter assigned parameters…')
        self.add_button = QPushButton('+ Parameter'); self.remove_button = QPushButton('Remove')
        top.addWidget(self.owner_filter); top.addWidget(self.search, 1); top.addWidget(self.add_button); top.addWidget(self.remove_button)
        root.addLayout(top)
        self.heading = QLabel(); self.heading.setObjectName('muted'); self.heading.setWordWrap(True)
        root.addWidget(self.heading)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['On', 'Instrument', 'Parameter', 'Rule', 'Status'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide(); self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setColumnWidth(0, 32)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        for column in (1, 2, 4):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(100)
        self.table.setMaximumHeight(120)
        self.body = QBoxLayout(QBoxLayout.TopToBottom)
        self.body.setSpacing(8)
        self.body.addWidget(self.table, 3, Qt.AlignTop)
        root.addLayout(self.body, 1)
        self.editor = QFrame(); self.editor.setObjectName('automationDetails')
        detail = QVBoxLayout(self.editor); detail.setContentsMargins(0, 0, 0, 0); detail.setSpacing(4)
        self.destination = QLabel(); self.destination.setWordWrap(True); self.destination.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail.addWidget(self.destination)
        grid = QGridLayout(); grid.setContentsMargins(0, 0, 0, 0); grid.setSpacing(5)
        self.mode = QComboBox(); self.mode.addItem('Value', 'value'); self.mode.addItem('Curve', 'curve')
        self.operation = QComboBox()
        for text, value in [('Set value', 'set'), ('Add to manual', 'add'), ('Multiply manual', 'multiply')]:
            self.operation.addItem(text, value)
        self.timing = QComboBox()
        for value, label in TIMING_NAMES.items(): self.timing.addItem(label, value)
        self.weight = QDoubleSpinBox(); self.weight.setRange(0, 1); self.weight.setDecimals(2); self.weight.setSingleStep(.1)
        for col, (label, control, key) in enumerate([('Mode', self.mode, 'mode'), ('Operation', self.operation, 'operation'),
                                                    ('Apply', self.timing, 'timing'), ('Weight', self.weight, 'weight')]):
            grid.addWidget(QLabel(label), 0, col); grid.addWidget(control, 1, col)
            control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            control.setMinimumWidth(0)
            bind_help(control, key, 'automation')
        detail.addLayout(grid)
        second = QHBoxLayout(); second.setSpacing(5)
        self.value_stack = QStackedWidget()
        self.value = QDoubleSpinBox(); self.value.setDecimals(5); self.value.setSingleStep(.05)
        self.choice = QComboBox(); self.text = QLineEdit(); self.text.setMaxLength(4096)
        for widget in (self.value, self.choice, self.text): self.value_stack.addWidget(widget)
        self.value_label = QLabel('Value')
        second.addWidget(self.value_label); second.addWidget(self.value_stack, 1)
        self.shape = QComboBox()
        for shape in ('linear', 'smooth', 'step'): self.shape.addItem(shape.title(), shape)
        self.influence_button = QPushButton('Influences…')
        self.shape.setMaximumWidth(140)
        second.addStretch(1)
        second.addWidget(self.shape); second.addWidget(self.influence_button)
        detail.addLayout(second)
        self.curve_box = QWidget(); curve_layout = QVBoxLayout(self.curve_box)
        curve_layout.setContentsMargins(0, 0, 0, 0); curve_layout.setSpacing(3)
        ranges = QHBoxLayout(); ranges.setSpacing(5)
        self.low = QDoubleSpinBox(); self.high = QDoubleSpinBox()
        for widget in (self.low, self.high): widget.setDecimals(5); widget.setMinimumWidth(0)
        self.range_label = QLabel('Range')
        ranges.addWidget(self.range_label); ranges.addWidget(self.low, 1); ranges.addWidget(QLabel('to')); ranges.addWidget(self.high, 1)
        self.full_range = QPushButton('Full')
        self.full_range.setToolTip('Use the current parameter limits without changing point positions')
        self.ramp = QPushButton('Ramp'); self.flat = QPushButton('Flat')
        ranges.addWidget(self.full_range); ranges.addWidget(self.ramp); ranges.addWidget(self.flat)
        curve_layout.addLayout(ranges)
        self.curve = ParameterCurveEditor(); curve_layout.addWidget(self.curve)
        points = QHBoxLayout(); points.setSpacing(5)
        self.point_beat = QDoubleSpinBox(); self.point_beat.setDecimals(4); self.point_beat.setSingleStep(.25)
        self.point_value = QDoubleSpinBox(); self.point_value.setDecimals(5)
        self.snap = QCheckBox('Snap 1/16'); self.snap.setChecked(True)
        points.addWidget(QLabel('Point beat')); points.addWidget(self.point_beat, 1)
        points.addWidget(QLabel('Value')); points.addWidget(self.point_value, 1); points.addWidget(self.snap)
        curve_layout.addLayout(points); detail.addWidget(self.curve_box)
        self.timing_note = QLabel(); self.timing_note.setObjectName('muted'); self.timing_note.setWordWrap(True)
        self.live = QLabel(); self.live.setWordWrap(True); self.live.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail.addWidget(self.timing_note); detail.addWidget(self.live)
        detail.addStretch(1)
        self.body.addWidget(self.editor, 4)
        self.commit_timer = QTimer(self); self.commit_timer.setSingleShot(True); self.commit_timer.setInterval(35)
        self.commit_timer.timeout.connect(self.flush)
        self.owner_filter.currentIndexChanged.connect(lambda _index: self.sync())
        self.search.textChanged.connect(lambda _text: self.sync())
        self.add_button.clicked.connect(self.pick_destination)
        self.remove_button.clicked.connect(self.remove_selected)
        self.table.itemSelectionChanged.connect(self._select)
        self.table.itemChanged.connect(self._toggle)
        self.mode.currentIndexChanged.connect(lambda _i: self._field('mode', self.mode.currentData()))
        self.operation.currentIndexChanged.connect(self._operation_changed)
        self.timing.currentIndexChanged.connect(lambda _i: self._field('timing', self.timing.currentData()))
        self.weight.valueChanged.connect(lambda value: self._field('weight', value))
        self.value.valueChanged.connect(lambda value: self._field('value', value))
        self.choice.currentIndexChanged.connect(lambda _i: self._field('value', self.choice.currentData()))
        self.text.editingFinished.connect(lambda: self._field('value', self.text.text()))
        self.shape.currentIndexChanged.connect(self._shape_changed)
        self.low.editingFinished.connect(self._range_changed); self.high.editingFinished.connect(self._range_changed)
        self.curve.curveChanged.connect(self._curve_changed)
        self.curve.selectionChanged.connect(self._point_fields)
        self.curve.editFinished.connect(self.sync)
        self.point_beat.valueChanged.connect(self._point_edited); self.point_value.valueChanged.connect(self._point_edited)
        self.snap.toggled.connect(lambda value: setattr(self.curve, 'snap', value))
        self.ramp.clicked.connect(lambda: self._preset_curve(False)); self.flat.clicked.connect(lambda: self._preset_curve(True))
        self.full_range.clicked.connect(self._use_full_range)
        self.influence_button.clicked.connect(self.open_influences)
        bindings = [(self.add_button, 'add'), (self.remove_button, 'remove'), (self.owner_filter, 'destination'),
                    (self.search, 'filter'), (self.table, 'tracks'), (self.value_stack, 'value'),
                    (self.value, 'value'), (self.choice, 'value'), (self.text, 'value'),
                    (self.shape, 'curve'), (self.low, 'range'), (self.high, 'range'),
                    (self.point_beat, 'point'), (self.point_value, 'point'), (self.snap, 'point'),
                    (self.full_range, 'full_range'),
                    (self.influence_button, 'influences'), (self.ramp, 'ramp'), (self.flat, 'ramp')]
        for widget, key in bindings: bind_help(widget, key, 'automation')
        self.sync()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # A scrollbar may remove ~15 px. Hysteresis keeps that width change
        # from repeatedly switching the layout and changing its height.
        threshold = 984 if self.body.direction() == QBoxLayout.LeftToRight else 1024
        wide = event.size().width() >= threshold
        direction = QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom
        if self.body.direction() != direction:
            self.body.setDirection(direction)
        self._fit_table()

    def _fit_table(self):
        wide = self.body.direction() == QBoxLayout.LeftToRight
        height = max(105, min(360, 32 + 26 * self.table.rowCount())) if wide else 120
        self.table.setMaximumHeight(height)

    def entity_name(self, entity_id):
        entity = self.host.get_entity(entity_id)
        if entity is None: return f'Missing instrument #{entity_id}'
        parent = self.host.engine.drum_parent_for(entity)
        return f'{parent.name} / {entity.name}' if parent else entity.name

    def track(self):
        return next((track for track in self.planner._selected_section().get('parameter_automation', [])
                     if track['id'] == self._selected_id), None)

    def _spec(self, track):
        owner = self.host.get_entity(track['entity_id']) if track else None
        spec = parameter_specs(self.host.engine, owner).get(track['parameter']) if owner is not None else None
        return owner, spec

    def sync(self, selected_id=None):
        if self.curve.dragging:
            return
        section = self.planner._selected_section()
        if section['id'] != self._section_id:
            self._section_id = section['id']; self._selected_id = None
        if selected_id is not None: self._selected_id = selected_id
        # Re-select an existing destination even when no table data changed.
        # Assignment shortcuts must not leave another row highlighted.
        if selected_id is not None: self._table_signature = None
        current_filter = self.owner_filter.currentData()
        owner_items = [(None, 'All instruments / voices')] + [(entity.id, self.entity_name(entity.id)) for entity in entities(self.host.project)]
        if [(self.owner_filter.itemData(i), self.owner_filter.itemText(i)) for i in range(self.owner_filter.count())] != owner_items:
            self.owner_filter.blockSignals(True); self.owner_filter.clear()
            for entity_id, name in owner_items: self.owner_filter.addItem(name, entity_id)
            self.owner_filter.setCurrentIndex(max(0, self.owner_filter.findData(current_filter)))
            self.owner_filter.blockSignals(False)
        tracks = section.get('parameter_automation', [])
        self.heading.setText(f'{section["name"]} · {section["bars"]} bars · {len(tracks)}/{MAX_TRACKS} lanes · ' +
                             ('Composition Play activates automation' if tracks else 'Add a parameter or right-click an Inspector control'))
        visible = []
        for track in tracks:
            owner, spec = self._spec(track)
            title = spec.label if spec else track['parameter']
            if self.owner_filter.currentData() is not None and track['entity_id'] != self.owner_filter.currentData(): continue
            if self.search.text().casefold() not in (title + ' ' + self.entity_name(track['entity_id']) + ' ' + track['parameter']).casefold(): continue
            visible.append((track, title))
        signature = repr((section['id'], visible, owner_items))
        if signature != self._table_signature:
            self._syncing = True
            self.table.blockSignals(True)
            try:
                self.table.setRowCount(len(visible)); selected_row = -1
                for row, (track, title) in enumerate(visible):
                    check = QTableWidgetItem(); check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                    check.setCheckState(Qt.Checked if track['enabled'] else Qt.Unchecked)
                    check.setData(Qt.UserRole, track['id']); self.table.setItem(row, 0, check)
                    for column, text in enumerate((self.entity_name(track['entity_id']), title,
                                                   f'{track["operation"]} · {track["mode"]}', 'Ready'), 1):
                        item = QTableWidgetItem(text); item.setData(Qt.UserRole, track['id']); self.table.setItem(row, column, item)
                    if track['id'] == self._selected_id: selected_row = row
                if selected_row < 0 and visible: selected_row = 0
                if selected_row >= 0:
                    self.table.selectRow(selected_row); self._selected_id = visible[selected_row][0]['id']
                else:
                    self._selected_id = None
            finally:
                self.table.blockSignals(False); self._syncing = False
            self._table_signature = signature
        self._fit_table()
        self.add_button.setEnabled(len(tracks) < MAX_TRACKS)
        self.remove_button.setEnabled(self.track() is not None)
        self.load_details()
        self.update_runtime()

    def _select(self):
        if self._syncing: return
        row = self.table.currentRow()
        self._selected_id = self.table.item(row, 0).data(Qt.UserRole) if row >= 0 else None
        self.load_details(); self.update_runtime()

    def _toggle(self, item):
        if self._syncing or item.column() != 0: return
        self._selected_id = item.data(Qt.UserRole)
        self._field('enabled', item.checkState() == Qt.Checked)

    def load_details(self):
        track = self.track(); owner, spec = self._spec(track)
        self.editor.setVisible(track is not None)
        self.editor.setEnabled(owner is not None and spec is not None)
        if track is None or spec is None or owner is None: return
        signature = repr((track, spec, self.planner._selected_section()['bars'], self.planner.runtime.bar_beats()))
        if signature == self._details_signature: return
        self._syncing = True
        try:
            operation = effective_operation(track, spec)
            description = ('choice' if spec.choices else 'text' if spec.text else
                           f'{spec.low:g}…{spec.high:g}' + (f' {spec.unit}' if spec.unit else '') +
                           (' · on/off' if spec.boolean else ' · integer' if spec.integer else ' · decimal'))
            self.destination.setText(f'{self.entity_name(owner.id)} · {spec.label} · {description}')
            self.destination.setToolTip(track['parameter'])
            for combo, value in ((self.mode, track['mode']), (self.operation, operation), (self.timing, track['timing'])):
                combo.setCurrentIndex(max(0, combo.findData(value)))
            self.weight.setValue(track['weight'])
            self.mode.setEnabled(not spec.discrete); self.operation.setEnabled(not spec.discrete and not spec.boolean)
            for index in range(self.timing.count()):
                timing = self.timing.itemData(index)
                allowed = timing_for({'timing': timing}, spec, owner) == timing or timing == 'auto'
                self.timing.model().item(index).setEnabled(allowed)
            low, high = operation_range(spec, operation)
            decimals = spec.decimals(operation)
            unit = spec.operand_unit(operation)
            for spin in (self.value, self.low, self.high, self.point_value):
                spin.setDecimals(decimals); spin.setSingleStep(spec.step(operation))
                spin.setSuffix(' ' + unit if unit else '')
            self.value.setRange(low, high)
            self.value.setValue(float(track['value']) if isinstance(track['value'], (int, float)) else spec.low)
            self.choice.clear()
            for value in spec.choices:
                label = ('Auto' if value == -1 else self.entity_name(value)) if spec.key in ('relation_drum_source', 'relation_chord_source') else str(value)
                self.choice.addItem(label, value)
            self.choice.setCurrentIndex(max(0, self.choice.findData(track['value'])))
            self.text.setText(str(track['value']))
            self.value_stack.setCurrentWidget(self.choice if spec.choices else self.text if spec.text else self.value)
            self.value_stack.setVisible(track['mode'] == 'value' or spec.discrete)
            self.value_label.setVisible(track['mode'] == 'value' or spec.discrete)
            self.curve_box.setVisible(track['mode'] == 'curve' and not spec.discrete)
            self.shape.setVisible(track['mode'] == 'curve' and not spec.discrete)
            for spin in (self.low, self.high): spin.setRange(low, high)
            fitted_low, fitted_high = curve_range(track, spec)
            self.low.setValue(fitted_low); self.high.setValue(fitted_high)
            self.low.setEnabled(low != high); self.high.setEnabled(low != high)
            self.range_label.setText('Factor' if operation == 'multiply' else 'Delta' if operation == 'add' else 'Range')
            self.curve.low, self.curve.high = fitted_low, fitted_high
            self.curve.integer = decimals == 0
            self.curve.boolean = spec.boolean
            self.curve.duration = self.planner._selected_section()['bars'] * self.planner.runtime.bar_beats()
            self.curve.set_curve(parameter_curve(track, spec))
            self.shape.setCurrentIndex(self.shape.findData(track['curve']['shape']))
            actual_timing = timing_for(track, spec, owner)
            note = 'Continuous follows musical time. SEQ material refreshes once per 1/16; LIVE reads the resolved value.' if actual_timing == 'continuous' else \
                   'Held between musical boundaries. Live edits wait for the next boundary; section entry and seek reconstruct the destination value.'
            self.timing_note.setText('Apply: ' + TIMING_NAMES[actual_timing] + '. ' + note +
                                     (' Choices/text use source priority; Set only.' if spec.discrete else ''))
            self._details_signature = signature
            self._loaded_spec = spec
        finally:
            self._syncing = False
        self._point_fields()

    def _changed(self):
        if self._syncing: return
        self._pending_project = self.host.project
        self.host._mark_pending_dirty()
        self.commit_timer.start()
        self._table_signature = None; self._details_signature = None

    def flush(self):
        self.commit_timer.stop()
        if self._pending_project is self.host.project:
            self._pending_project = None
            self.planner._mark_changed(message='Section parameter automation updated')

    def _field(self, key, value):
        if self._syncing: return
        track = self.track()
        if track is None or track.get(key) == value: return
        self._adopt_range()
        track[key] = value
        self._changed()
        if key not in ('value', 'weight'): self.sync()

    def _operation_changed(self, _index):
        if self._syncing: return
        track = self.track(); owner, spec = self._spec(track)
        if spec is None: return
        operation = self.operation.currentData()
        track['operation'] = operation
        track['low'], track['high'] = operation_range(spec, operation)
        track['value'] = 0. if operation == 'add' else 1. if operation == 'multiply' else spec.coerce(self.host.engine.parameter_influence.base_value(owner, spec.key, spec.default))
        track['curve'] = normalize_curve({'shape': track['curve']['shape'], 'points': [[0, 0], [1, 1]]})
        self._changed(); self.sync()

    def _shape_changed(self, _index):
        if self._syncing or self.track() is None: return
        curve = deepcopy(self.track()['curve']); curve['shape'] = self.shape.currentData()
        self._curve_changed(curve)

    def _range_changed(self):
        if self._syncing or self.track() is None: return
        if self.high.value() <= self.low.value():
            self._details_signature = None; self.load_details()
            self.host.set_message('Curve range: maximum must be greater than minimum'); return
        self.track()['low'], self.track()['high'] = self.low.value(), self.high.value()
        self._changed(); self.load_details()

    def _adopt_range(self):
        track = self.track(); _owner, spec = self._spec(track)
        if spec is not None:
            track['low'], track['high'] = curve_range(track, spec)
            track['operation'] = effective_operation(track, spec)

    def _use_full_range(self):
        track = self.track(); _owner, spec = self._spec(track)
        if spec is None: return
        track['low'], track['high'] = operation_range(spec, effective_operation(track, spec))
        self._changed(); self.load_details()

    def _curve_changed(self, curve):
        if self._syncing or self.track() is None: return
        self._adopt_range()
        self.track()['curve'] = normalize_curve(curve)
        _owner, spec = self._spec(self.track())
        if spec is not None: self.track()['curve'] = parameter_curve(self.track(), spec)
        self._changed(); self.curve.curve = deepcopy(self.track()['curve']); self.curve.update(); self._point_fields()

    def _point_fields(self):
        track = self.track()
        if track is None: return
        index = min(self.curve.selected, len(track['curve']['points']) - 1)
        _owner, spec = self._spec(track)
        low, high = curve_range(track, spec) if spec else (track['low'], track['high'])
        x, y = parameter_curve(track, spec)['points'][index] if spec else track['curve']['points'][index]
        self._syncing = True
        try:
            self.point_beat.setRange(0., self.curve.duration)
            self.point_beat.setValue(x * self.curve.duration)
            self.point_beat.setEnabled(index not in (0, len(track['curve']['points']) - 1))
            self.point_value.setRange(low, high)
            self.point_value.setValue(low + y * (high - low))
        finally: self._syncing = False

    def _point_edited(self, _value):
        if self._syncing or self.track() is None: return
        self._adopt_range()
        track = self.track(); points = deepcopy(track['curve']['points']); index = self.curve.selected
        x = self.point_beat.value() / max(1e-9, self.curve.duration)
        if index in (0, len(points) - 1): x = points[index][0]
        else: x = max(points[index - 1][0] + .001, min(points[index + 1][0] - .001, x))
        y = (self.point_value.value() - track['low']) / max(1e-9, track['high'] - track['low'])
        points[index] = [x, y]
        self._curve_changed({**track['curve'], 'points': points})

    def _preset_curve(self, flat):
        track = self.track()
        if track is None: return
        self._adopt_range()
        if flat:
            y = (self.point_value.value() - track['low']) / max(1e-9, track['high'] - track['low'])
            points = [[0, y], [1, y]]
        else: points = [[0, 0], [1, 1]]
        self._curve_changed({**track['curve'], 'points': points}); self.curve.set_curve(self.track()['curve'])

    def pick_destination(self):
        picker = DestinationPicker(self)
        if picker.exec() == QDialog.Accepted and picker.destination(): self.assign(*picker.destination())
        picker.deleteLater()

    def assign(self, entity_id, key):
        owner = self.host.get_entity(entity_id)
        if owner is None or key not in parameter_specs(self.host.engine, owner): return False
        section = self.planner._selected_section(); tracks = section.setdefault('parameter_automation', [])
        track = next((track for track in tracks if track['entity_id'] == entity_id and track['parameter'] == key), None)
        if track is None:
            if len(tracks) >= MAX_TRACKS:
                self.host.set_message('This section already has 128 automation lanes'); return False
            track = make_track(self.host.engine, owner, key); tracks.append(track)
            self._changed(); self.flush()
        self.owner_filter.blockSignals(True); self.owner_filter.setCurrentIndex(0); self.owner_filter.blockSignals(False)
        self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
        self.sync(track['id'])
        return True

    def remove_selected(self):
        track = self.track()
        if track is None: return
        self.planner._selected_section()['parameter_automation'].remove(track)
        self._selected_id = None; self._changed(); self.flush(); self.sync()

    def open_influences(self):
        track = self.track()
        if track is None: return
        dialog = InfluenceDialog(self.host, track['entity_id'], track['parameter'])
        dialog.setAttribute(Qt.WA_DeleteOnClose); dialog.show()

    def update_runtime(self):
        if not self.isVisible(): return
        lock = self.host.transport._transport_lock
        if not lock.acquire(blocking=False): return
        try:
            runtime = self.host.engine.section_automation
            statuses = deepcopy(runtime.statuses)
            selected_section = self.planner._selected_section()
            context = self.host.engine.composition_runtime.context_at(self.host.engine.clock.position_beats)
            active = self.host.transport.running and self.host.transport.playback_mode == 'composition' and context is not None
            same_section = active and context['section_id'] == selected_section['id']
            track = self.track(); owner, spec = self._spec(track)
            trace = (self.host.engine.parameter_influence.describe(owner, track['parameter'], spec.default)
                     if owner is not None and spec is not None else None)
        finally: lock.release()
        if spec is not None and spec != self._loaded_spec and not self.curve.dragging:
            self._details_signature = None
            self.load_details()
        self._syncing = True; self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                tid = self.table.item(row, 0).data(Qt.UserRole)
                status = statuses.get(tid, {}) if same_section else {}
                text = status.get('state', 'other section' if active else 'ready / stopped')
                enabled = self.table.item(row, 0).checkState() == Qt.Checked
                if not enabled: text = 'disabled'
                active_row = text == 'active'
                item = self.table.item(row, 4)
                caption = ('● ' if active_row else '○ ') + text
                if item.text() != caption: item.setText(caption)
                item.setForeground(QColor('#55c5ad' if active_row else self.palette().text().color()))
                item.setToolTip('Apply: ' + TIMING_NAMES.get(status.get('timing'), 'Auto') +
                    (f' · next section beat {status["next_beat"]:g}' if 'next_beat' in status else '') +
                    (f' · target {formatted(status["target"])}' if 'target' in status else '') +
                    (f' · effective {formatted(status["current"])}' if 'current' in status else ''))
            if track is not None and trace is not None:
                status = statuses.get(track['id'], {}) if same_section else {}
                text = f'Manual {formatted(trace["base"])}   →   Effective {formatted(trace["current"])}'
                if 'target' in status: text += f'   ·   Automation target {formatted(status["target"])}'
                text += '   ·   ' + status.get('state', 'ready / stopped' if not active else 'another section')
                if self.live.text() != text: self.live.setText(text)
                self.curve.theme = theme_palette(self.host.theme_combo.currentText())
                held = curve_value(parameter_curve(track, spec), status.get('sample_beat', 0.) / max(1e-9, self.curve.duration))
                if spec.decimals(effective_operation(track, spec)) == 0:
                    low, high = curve_range(track, spec)
                    operand = low + held * (high - low)
                    operand = int(operand >= .5) if spec.boolean else round(operand)
                    held = (operand - low) / (high - low) if high != low else .5
                self.curve.set_position(context['section_progress'] if same_section else None, held if same_section else None)
        finally:
            self.table.blockSignals(False); self._syncing = False
