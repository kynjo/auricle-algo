"""Parameter layers, their effective result and persistent user policies."""
from itertools import permutations
from copy import deepcopy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QComboBox, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QGridLayout, QDoubleSpinBox, QGroupBox)
from help_tooltips import bind_help

from parameter_influence import KINDS
from section_automation import parameter_specs


def formatted(value):
    if isinstance(value, float): return f'{value:.4g}'
    return '—' if value is None else str(value)


class InfluenceDialog(QDialog):
    def __init__(self, host, block_id, key=None):
        super().__init__(host)
        self.host, self.block_id = host, block_id
        self._policy_loaded = None
        self._syncing = False
        self.setWindowTitle('Parameter influences')
        self.resize(610, 540)
        layout = QVBoxLayout(self)
        self.heading = QLabel(); layout.addWidget(self.heading)
        self.parameter = QComboBox()
        block = host.get_entity(block_id)
        for name, spec in sorted(parameter_specs(host.engine, block).items()):
            self.parameter.addItem(spec.label, name)
        if key and self.parameter.findData(key) < 0: self.parameter.addItem(key, key)
        if key: self.parameter.setCurrentIndex(self.parameter.findData(key))
        layout.addWidget(self.parameter)
        self.values = QLabel(); self.values.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.values)
        policy = QGroupBox('Control policy · saved with project')
        grid = QGridLayout(policy)
        self.mode = QComboBox(); self.mode.setAccessibleName('Parameter influence mode')
        for text, data in [('Priority', 'priority'), ('Weighted blend', 'blend'), ('Manual only', 'manual')]: self.mode.addItem(text, data)
        self.priority = QComboBox(); self.priority.setAccessibleName('Parameter source priority')
        for order in permutations(KINDS): self.priority.addItem(' > '.join(order), list(order))
        self.priority.setMaxVisibleItems(12)
        self.priority.setToolTip('Highest priority on the left. Partial weights let lower layers through.')
        grid.addWidget(QLabel('Mode'), 0, 0); grid.addWidget(self.mode, 0, 1, 1, 3)
        grid.addWidget(QLabel('Priority'), 1, 0); grid.addWidget(self.priority, 1, 1, 1, 3)
        self.weights = {}
        for column, kind in enumerate(('Manual', *KINDS)):
            grid.addWidget(QLabel(kind), 2, column)
            spin = QDoubleSpinBox(); spin.setRange(0., 1.); spin.setDecimals(2); spin.setSingleStep(.1)
            spin.setAccessibleName(kind + ' influence weight')
            spin.setToolTip('0 disables this source category; 1 gives full weight. Multiple routes in a category are averaged.')
            grid.addWidget(spin, 3, column); self.weights[kind] = spin
            spin.valueChanged.connect(self._changed)
        layout.addWidget(policy)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Source', 'Target', 'Weight', 'State'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3): self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.verticalHeader().hide(); self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(100); layout.addWidget(self.table, 1)
        self.note = QLabel(); self.note.setWordWrap(True); layout.addWidget(self.note)
        self.output = QLabel(); self.output.setWordWrap(True); layout.addWidget(self.output)
        self.regenerate_timer = QTimer(self); self.regenerate_timer.setSingleShot(True)
        self.regenerate_timer.setInterval(35); self.regenerate_timer.timeout.connect(self._regenerate)
        self.parameter.currentIndexChanged.connect(self.refresh)
        self.mode.currentIndexChanged.connect(self._changed); self.priority.currentIndexChanged.connect(self._changed)
        self.timer = QTimer(self); self.timer.setInterval(160); self.timer.timeout.connect(self.refresh); self.timer.start()
        self.refresh()
        bind_help(self.mode, "policy", "influence")
        bind_help(self.priority, "priority", "influence")
        for kind, control in self.weights.items():
            bind_help(control, kind.lower(), "influence")

    def _changed(self, *_):
        if self._syncing: return
        host = self.host
        block_id = int(self.block_id)
        key = self.parameter.currentData()
        policy = {'mode': self.mode.currentData(), 'priority': self.priority.currentData(),
                  'weights': {kind: spin.value() for kind, spin in self.weights.items()}}
        project = host.project
        def commit():
            if host.project is not project: return
            block = host.get_entity(block_id)
            if block is not None:
                host.engine.parameter_influence.set_policy(block, key, policy)
        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            commit, key=("parameter-influence", id(project), block_id, key),
            notification={"dirty": True}, label="Parameter Influence policy")
        self.regenerate_timer.start()
        self._policy_loaded = None

    def _regenerate(self):
        host = self.host
        block_id = int(self.block_id)
        project = host.project
        def commit():
            if host.project is project:
                block = host.get_entity(block_id)
                if block is not None: host.engine.regenerate(block)
        host.transport.enqueue_gui_command(
            commit, key=("parameter-influence-regenerate", id(project), block_id),
            label="Regenerate influenced block")

    def refresh(self):
        host = self.host
        lock = host.transport._transport_lock
        if not lock.acquire(blocking=False):
            return
        try:
            block = host.get_entity(self.block_id)
            if block is None:
                removed = True
            else:
                removed = False
                key = self.parameter.currentData()
                spec = parameter_specs(host.engine, block).get(key)
                default = spec.default if spec else None
                if spec is not None and spec.discrete:
                    host.engine.parameter_influence.configure_discrete(block, key, default, spec.choices)
                trace = host.engine.parameter_influence.describe(block, key, default)
                effective = (host.engine._live_parameter(block, key, default)
                             if block.mode == 'LIVE' and not trace['discrete'] else trace['current'])
                rows = deepcopy(trace['writes'])
                settings = deepcopy(trace['policy'])
                macros = dict(host.engine.director.global_macro_values)
                heading = f'{block.name} · {block.mode}'
                base = trace['base']
        finally:
            lock.release()
        if removed:
            self.heading.setText('Block removed — close this card or undo deletion')
            self.values.clear(); self.table.setRowCount(0); self.output.clear()
            return
        self.heading.setText(heading)
        if self._policy_loaded != (key, settings):
            self._syncing = True
            try:
                self.mode.setCurrentIndex(self.mode.findData(settings['mode']))
                self.priority.setCurrentIndex(next(i for i in range(self.priority.count()) if self.priority.itemData(i) == settings['priority']))
                for kind, spin in self.weights.items(): spin.setValue(settings['weights'][kind])
                self.priority.setEnabled(settings['mode'] == 'priority')
                for kind, spin in self.weights.items(): spin.setEnabled(settings['mode'] != 'manual' and (kind != 'Manual' or settings['mode'] == 'blend'))
            finally: self._syncing = False
            self._policy_loaded = (key, settings)
        self.values.setText(f'Manual base: {formatted(base)}    Effective: {formatted(effective)}')
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate((row['source'], formatted(row['value']), formatted(row['effective_weight']), row['status'])):
                self.table.setItem(i, j, QTableWidgetItem(value))
        self.note.setText({'priority': 'Priority resolves layers independently of update order. The first category has precedence; partial weights retain the lower result.',
                           'blend': 'Weighted mean of Manual, Composition, Macro, Technique and Modulation targets. Routes inside one category are averaged first. Choices/text always use priority.',
                           'manual': 'Automatic layers remain visible and are bypassed. Only the manual base controls this parameter.'}[settings['mode']])
        energy = .70 + .60 * macros.get('energy', .5)
        keep = min(1., max(0., .25 + 1.5 * macros.get('density', .5)))
        self.output.setText(f'Also applied to generated notes: Energy ×{energy:.2f} velocity; Density keeps up to {keep:.0%} of events; '
                            'Variation shapes accents; Tension controls the Director. Process, Mutation and stream Relations act on note data separately.')

