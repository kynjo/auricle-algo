"""Read-only parameter provenance card; refreshes never regenerate music."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QLabel, QTableWidget, QTableWidgetItem, QHeaderView


def formatted(value):
    if isinstance(value, float): return f'{value:.4g}'
    return '—' if value is None else str(value)


class InfluenceDialog(QDialog):
    def __init__(self, host, block_id, key=None):
        super().__init__(host)
        self.host, self.block_id = host, block_id
        self.setWindowTitle('Parameter influences')
        self.resize(460, 370)
        layout = QVBoxLayout(self)
        self.heading = QLabel()
        layout.addWidget(self.heading)
        self.parameter = QComboBox()
        block = host.get_entity(block_id)
        for name in sorted(host.engine.parameter_catalog(block)):
            self.parameter.addItem(name.replace('_', ' ').title(), name)
        if key and self.parameter.findData(key) < 0: self.parameter.addItem(key, key)
        if key: self.parameter.setCurrentIndex(self.parameter.findData(key))
        layout.addWidget(self.parameter)
        self.values = QLabel()
        self.values.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.values)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Latest writes', 'Before', 'Written'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(95)
        layout.addWidget(self.table, 1)
        self.note = QLabel('Writes replace values in this order; they are not added together. Earlier writes may be overwritten.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.output = QLabel()
        self.output.setWordWrap(True)
        layout.addWidget(self.output)
        self.parameter.currentIndexChanged.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(160)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self):
        host = self.host
        with host.transport._state_lock:
            block = host.get_entity(self.block_id)
            if block is None:
                self.heading.setText('Block removed — close this card or undo deletion')
                self.values.clear(); self.table.setRowCount(0); self.output.clear()
                return
            key = self.parameter.currentData()
            default = host.engine.parameter_catalog(block).get(key, (None, 0, 1))[0]
            trace = host.engine.parameter_influence.describe(block, key, default)
            effective = host.engine._live_parameter(block, key, default) if block.mode == 'LIVE' else trace['current']
            rows = trace['writes']
            if effective != trace['current']:
                rows.append({'source': 'Active LIVE technique', 'before': trace['current'], 'value': effective})
            macros = dict(host.engine.director.global_macro_values)
            self.heading.setText(f'{block.name} · {block.mode}')
        self.values.setText(f'Manual base: {formatted(trace["base"])}    Effective: {formatted(effective)}')
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate((row['source'], formatted(row['before']), formatted(row['value']))):
                self.table.setItem(i, j, QTableWidgetItem(value))
        if not rows:
            self.note.setText('No automatic parameter writes recorded. The effective value is the manual value/default.')
        else:
            self.note.setText('Latest writes, in application order. Writes replace values; they are not added together.')
        energy = .70 + .60 * macros.get('energy', .5)
        keep = min(1., max(0., .25 + 1.5 * macros.get('density', .5)))
        self.output.setText(f'Also applied to generated notes: Energy ×{energy:.2f} velocity; '
                            f'Density keeps up to {keep:.0%} of events; Variation shapes accents. '
                            'Tension changes the Director trajectory. '
                            'Director, Process, Mutation and stream Relations act on notes, not on this scalar value.')
