"""Compact inspector preset browser with an authored-value diff before Apply."""
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, QStandardPaths
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QLineEdit,
    QLabel, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QSplitter, QWidget, QFileDialog, QInputDialog, QMessageBox)

from auricle_catalogs import GENERATORS
from sound_presets import PresetStore, capture, compatible, prepared_parameters, apply
from sound_preset_catalog import factory_presets
from help_catalog import entry
from section_automation import UNITS
from ui_themes import theme_palette


class SoundPresetDialog(QDialog):
    def __init__(self, host, entity, kind='algorithm', directory=None):
        super().__init__(host)
        self.host, self.entity, self.project = host, entity, host.project
        self.setWindowTitle(f'Presets · {entity.name}')
        self.setWindowModality(Qt.WindowModal)
        self.resize(800, 520)
        directory = directory or str(Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / 'sound-presets')
        self.store = PresetStore(directory)
        layout = QVBoxLayout(self); layout.setSpacing(5)
        filters = QHBoxLayout()
        self.kind = QComboBox(); self.kind.addItem('Algorithm', 'algorithm'); self.kind.addItem('Block / Drum Voice', 'block')
        self.kind.setCurrentIndex(self.kind.findData(kind)); self.kind.setAccessibleName('Preset scope')
        if getattr(entity, 'drum_voices', None): self.kind.model().item(0).setEnabled(False)
        filters.addWidget(self.kind)
        self.algorithm = QComboBox(); self.algorithm.addItem('All algorithms', None)
        for value in GENERATORS: self.algorithm.addItem(value, value)
        with host.transport._transport_lock:
            value = host.engine.parameter_influence.document_attributes(entity).get('algorithm', entity.algorithm)
        self.algorithm.setCurrentIndex(self.algorithm.findData(value))
        self.algorithm.setAccessibleName('Preset algorithm filter'); filters.addWidget(self.algorithm)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search presets…'); self.search.setAccessibleName('Search sound presets')
        filters.addWidget(self.search, 1); layout.addLayout(filters)
        self.hint = QLabel(); self.hint.setWordWrap(True); self.hint.setObjectName('muted'); layout.addWidget(self.hint)
        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget(); self.list.setAccessibleName('Sound presets')
        self.list.setObjectName('soundPresetList')
        theme=getattr(host, '_active_theme', None) or theme_palette()
        self.list.setStyleSheet(f'QListWidget#soundPresetList::item:selected {{ background:{theme.selection}; color:{theme.text}; }}')
        split.addWidget(self.list)
        detail = QWidget(); column = QVBoxLayout(detail); column.setContentsMargins(4,0,0,0)
        self.description = QLabel(); self.description.setTextFormat(Qt.PlainText); self.description.setWordWrap(True)
        column.addWidget(self.description)
        self.diff = QTableWidget(0,3); self.diff.setHorizontalHeaderLabels(['Setting','Current base','Preset'])
        self.diff.setEditTriggers(QTableWidget.NoEditTriggers); self.diff.setSelectionBehavior(QTableWidget.SelectRows)
        self.diff.verticalHeader().hide(); self.diff.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.diff.setAccessibleName('Preset authored parameter comparison'); column.addWidget(self.diff,1)
        split.addWidget(detail); split.setSizes([250,530]); layout.addWidget(split,1)
        self.status = QLabel(); self.status.setWordWrap(True); self.status.setObjectName('muted'); layout.addWidget(self.status)
        row = QHBoxLayout()
        save = QPushButton('Save current…'); save.clicked.connect(self.save_current); row.addWidget(save)
        load = QPushButton('Import…'); load.clicked.connect(self.import_preset); row.addWidget(load)
        self.export = QPushButton('Export…'); self.export.clicked.connect(self.export_preset); row.addWidget(self.export)
        self.delete = QPushButton('Delete'); self.delete.clicked.connect(self.delete_preset); row.addWidget(self.delete)
        row.addStretch(1)
        self.apply_button = QPushButton('Apply'); self.apply_button.clicked.connect(self.apply_selected); row.addWidget(self.apply_button)
        close = QPushButton('Close'); close.clicked.connect(self.reject); row.addWidget(close)
        layout.addLayout(row)
        for button in self.findChildren(QPushButton): button.setAutoDefault(False)
        self.kind.currentIndexChanged.connect(self.reload)
        self.algorithm.currentIndexChanged.connect(self.reload)
        self.search.textChanged.connect(self.reload)
        self.list.currentItemChanged.connect(self.preview)
        self.reload()

    def valid_target(self):
        return self.host.project is self.project and self.host.get_entity(self.entity.id) is self.entity

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def reload(self, *_):
        selected = self.selected()
        identity = selected['id'] if selected else None
        self.list.clear()
        kind = self.kind.currentData()
        self.algorithm.setVisible(kind == 'algorithm')
        self.hint.setText('Algorithm: source parameters and seed only. Other musical controls stay as authored.' if kind == 'algorithm' else
            'Block: musical parameters, mode, mutations, processes and MIDI expression. MIDI routing, names, note maps and project assignments stay with the destination.')
        users, errors = self.store.list()
        search = self.search.text().casefold().strip()
        for item in [*factory_presets(), *users]:
            if item['kind'] != kind: continue
            if kind == 'algorithm' and self.algorithm.currentData() and item['algorithm'] != self.algorithm.currentData(): continue
            if kind == 'block' and (item['block_type'] != self.entity.block_type or (item['target']=='voice') != bool(getattr(self.entity,'is_drum_voice',False))): continue
            if search and search not in (item['name']+' '+item['description']+' '+item['algorithm']).casefold(): continue
            prefix = 'Factory' if item['id'].startswith('factory:') else 'User'
            row = QListWidgetItem(f'{prefix} · {item["name"]}')
            row.setData(Qt.UserRole,item); row.setToolTip(item['algorithm']+' · '+item['description']); self.list.addItem(row)
            if item['id'] == identity: self.list.setCurrentItem(row)
        if self.list.currentRow() < 0 and self.list.count(): self.list.setCurrentRow(0)
        self.status.setText(f'{len(errors)} unreadable preset file(s); originals were kept.' if errors else 'Lengths and rotations fit the current pattern. Composition and other active influences still apply. Undo restores a loaded preset.')
        self.status.setToolTip('\n'.join(errors))
        self.preview()

    def preview(self, *_):
        item = self.selected()
        self.diff.setRowCount(0)
        ready = bool(item and self.valid_target() and compatible(item,self.entity))
        self.apply_button.setEnabled(ready)
        self.export.setEnabled(item is not None)
        self.delete.setEnabled(bool(item and not item['id'].startswith('factory:')))
        if not item:
            self.description.setText('No matching presets. Save the current settings or import a preset.'); return
        self.description.setText(item['name']+' · '+item['algorithm']+'\n'+item['description']+
            ('\nThis kit needs the same number of voices for each role.' if not ready else ''))
        if not self.valid_target(): return
        with self.host.transport._transport_lock:
            before = capture(self.host.engine,self.entity,item['kind'],'Current')
            after = prepared_parameters(self.host.engine,self.entity,item)
        old=before['parameters']
        changes=[]
        if before['algorithm'] != item['algorithm']: changes.append(('Algorithm',before['algorithm'],item['algorithm']))
        for key in sorted(set(old) | set(after)):
            a,b=old.get(key,'default'),after.get(key,'default')
            if a != b:
                help_entry=entry('block',key)
                label=help_entry.label if help_entry else key.replace('_',' ').title()
                unit=UNITS.get(key,'')
                changes.append((label+(f' ({unit})' if unit else ''),a,b))
        if item['kind'] == 'block':
            for key in ('mode','mutators','processes','midi_expression'):
                if before[key] != item[key]: changes.append((key,before[key],item[key]))
            def voices(data):
                ordered=sorted(data['voices'], key=lambda voice:voice['parameters'].get('kit_role','perc'))
                return [{key:voice[key] for key in ('algorithm','parameters','mode','mutators','processes','midi_expression')}
                        for voice in ordered]
            if voices(before) != voices(item): changes.append(('Drum Voices',voices(before),voices(item)))
        def brief(value):
            text=str(value)
            return text[:160]+'…' if len(text)>160 else text
        self.diff.setRowCount(len(changes))
        for row, values in enumerate(changes):
            for col,value in enumerate(values):
                cell=QTableWidgetItem(brief(value));cell.setToolTip(str(value)); self.diff.setItem(row,col,cell)

    def error(self, exc): QMessageBox.warning(self,'Sound presets',str(exc))

    def save_current(self):
        if not self.valid_target(): return
        name, ok=QInputDialog.getText(self,'Save sound preset','Preset name:',text=self.entity.name+' · '+self.entity.algorithm)
        if not ok: return
        try:
            self.host.transport.flush_gui_commands(notify=True)
            with self.host.transport._transport_lock:
                item=capture(self.host.engine,self.entity,self.kind.currentData(),name)
            item=self.store.save(item);self.search.clear();self.reload();self.select_identity(item['id'])
        except (OSError,ValueError) as exc: self.error(exc)

    def import_preset(self):
        path,_=QFileDialog.getOpenFileName(self,'Import sound preset','','Auricle preset (*.json)')
        if not path: return
        try:
            item=self.store.save(self.store.read(path))
            self.kind.setCurrentIndex(self.kind.findData(item['kind']))
            if item['kind']=='algorithm': self.algorithm.setCurrentIndex(self.algorithm.findData(item['algorithm']))
            self.search.clear(); self.reload();self.select_identity(item['id'])
            if not compatible(item,self.entity): self.status.setText('Imported. Select a matching block type and Drum Voice layout to apply this preset.')
        except (OSError,ValueError,RecursionError) as exc: self.error(exc)

    def export_preset(self):
        item=self.selected()
        if not item:return
        path,_=QFileDialog.getSaveFileName(self,'Export sound preset','Auricle-preset.json','Auricle preset (*.json)')
        if not path:return
        if not path.lower().endswith('.json'):path+='.json'
        try:self.store.write(path,item)
        except (OSError,ValueError) as exc:self.error(exc)

    def select_identity(self, identity):
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole)['id'] == identity:
                self.list.setCurrentRow(row)
                break

    def delete_preset(self):
        item=self.selected()
        if not item or item['id'].startswith('factory:'):return
        if QMessageBox.question(self,'Delete preset',f'Delete “{item["name"]}” from your presets?') != QMessageBox.Yes:return
        try:self.store.delete(item);self.reload()
        except (OSError,ValueError) as exc:self.error(exc)

    def apply_selected(self):
        item=self.selected()
        if not item or not self.valid_target() or not compatible(item,self.entity):return
        payload=deepcopy(item)
        host,entity,project=self.host,self.entity,self.project
        def commit():
            if host.project is not project or host.get_entity(entity.id) is not entity:return
            host.transport._release_block_notes(entity.id)
            for owner in (entity, *(getattr(entity,'drum_voices',None) or [])):
                host.transport._release_expression_owner(owner.id)
            apply(host.engine,entity,payload)
        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(commit, notification={'dirty':True,'blocks':True,'block_id':entity.id,
            'refresh':'SOURCE','message':'Preset loaded: '+payload['name']},label='Load sound preset')
        self.accept()
