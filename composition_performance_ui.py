"""Compact section performance editors for the combined Composition page."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFrame, QGroupBox, QLabel, QCheckBox, QComboBox, QPushButton,
    QSlider, QDoubleSpinBox, QHBoxLayout, QVBoxLayout, QGridLayout, QSizePolicy,
    QDialog, QDialogButtonBox, QScrollArea,
)

from help_tooltips import bind_attributes, bind_controls

from composition_performance import normalize_performance
from performance_presets import (
    phrases, phrase_for, phrase_with_duration, presets_for_entity,
    preset_for_entity, resolve_phrase_stage,
)
from ui_themes import theme_palette, is_light_theme, contrast_ratio
from ui_icons import block_type_icon
from ui_metrics import DENSE_HEIGHT
from PySide6.QtGui import QColor


def spin(low, high, value, width=60):
    widget = QDoubleSpinBox()
    widget.setRange(low, high)
    widget.setDecimals(2 if high <= 2 else 1)
    widget.setSingleStep(.05 if high <= 2 else 1)
    widget.setValue(value)
    widget.setFixedWidth(width)
    widget.setFixedHeight(DENSE_HEIGHT)
    return widget


def dot(color, tip):
    widget = QLabel()
    widget.setFixedSize(7, 7)
    widget.setStyleSheet(f"background:{color};border-radius:3px;")
    widget.setToolTip(tip)
    return widget


class SectionPhraseEditor(QGroupBox):
    def __init__(self, controller, strip_factory):
        super().__init__("SECTION PERFORMANCE")
        self.controller = controller
        self.syncing = False
        self._preview = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 7)
        layout.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(dot("#b493ed", "Perform phrase assigned to this Composition section"))
        row.addWidget(QLabel("Phrase"))
        self.phrase = QComboBox()
        self.phrase.setMinimumWidth(155)
        self.phrase.addItem("None", None)
        for item in phrases():
            self.phrase.addItem(item.name, item.id)
        row.addWidget(self.phrase, 2)
        row.addWidget(QLabel("Amount"))
        self.amount = QSlider(Qt.Horizontal)
        self.amount.setRange(0, 100)
        self.amount.setMinimumWidth(45)
        row.addWidget(self.amount, 1)
        self.value = QLabel("100%")
        self.value.setFixedWidth(36)
        row.addWidget(self.value)
        self.fit = QCheckBox("Fit to section")
        row.addWidget(self.fit)
        self.duration = spin(1, 1024, 16, 78)
        self.duration.setSuffix(" b")
        self.duration.setToolTip("Phrase duration in quarter-note beats; Fit uses the selected section's meter and bars.")
        row.addWidget(self.duration)
        self.targets = QPushButton("Targets…")
        self.targets.setFixedWidth(92)
        row.addWidget(self.targets)
        layout.addLayout(row)
        self.stages = strip_factory()
        layout.addWidget(self.stages)
        self.hint = QLabel("No phrase. Section macros and instrument coefficients still apply.")
        self.hint.setObjectName("muted")
        layout.addWidget(self.hint)
        self.phrase.currentIndexChanged.connect(self.changed)
        self.amount.valueChanged.connect(self.changed)
        self.fit.toggled.connect(self.changed)
        self.duration.valueChanged.connect(self.changed)
        self.targets.clicked.connect(self.choose_targets)
        bind_attributes(self, "section_phrase")

    def sync(self, section):
        settings = normalize_performance(section.get("performance"))
        self.syncing = True
        self.phrase.setCurrentIndex(max(0, self.phrase.findData(settings["phrase_id"])))
        self.amount.setValue(round(settings["amount"] * 100))
        self.value.setText(f'{round(settings["amount"] * 100)}%')
        self.fit.setChecked(settings["fit_to_section"])
        length = section["bars"] * self.controller.runtime.bar_beats() if settings["fit_to_section"] else settings["duration_beats"]
        self.duration.setValue(length)
        enabled = settings["phrase_id"] is not None
        self.duration.setEnabled(enabled and not settings["fit_to_section"])
        self.amount.setEnabled(enabled)
        self.fit.setEnabled(enabled)
        count = len(self.controller.host.project.blocks) if settings["block_ids"] is None else len(settings["block_ids"])
        self.targets.setText(f"Targets ({count})…")
        self.targets.setToolTip("All instruments, including new blocks" if settings["block_ids"] is None else "Only the selected instruments; an empty selection targets none")
        preview = (settings["phrase_id"], length)
        if preview != self._preview:
            self._preview = preview
            self.stages.set_phrase(phrase_with_duration(phrase_for(settings["phrase_id"]), length, section_fit=True))
        self.stages.setVisible(enabled)
        self.hint.setVisible(not enabled)
        self.syncing = False
        bind_attributes(self, "section_phrase")
        self.update_runtime()

    def changed(self, *_):
        if self.syncing:
            return
        section = self.controller._selected_section()
        settings = normalize_performance(section.get("performance"))
        settings.update(phrase_id=self.phrase.currentData(), amount=self.amount.value()/100,
                        fit_to_section=self.fit.isChecked())
        if not self.fit.isChecked() and self.sender() is self.duration:
            settings["duration_beats"] = self.duration.value()
        self.controller.set_section_performance(settings)

    def choose_targets(self):
        settings = normalize_performance(self.controller._selected_section().get("performance"))
        dialog = QDialog(self)
        dialog.setWindowTitle("Phrase targets")
        dialog.resize(360, 340)
        layout = QVBoxLayout(dialog)
        all_blocks = QCheckBox("All instruments, including new blocks")
        all_blocks.setChecked(settings["block_ids"] is None)
        layout.addWidget(all_blocks)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        rows = QVBoxLayout(content)
        checks = []
        for block in self.controller.host.project.blocks:
            check = QCheckBox(f"{block.name} · {block.block_type}")
            check.setChecked(settings["block_ids"] is None or block.id in settings["block_ids"])
            check.setEnabled(not all_blocks.isChecked())
            all_blocks.toggled.connect(lambda yes, w=check: w.setEnabled(not yes))
            rows.addWidget(check)
            checks.append((block.id, check))
        rows.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            settings["block_ids"] = None if all_blocks.isChecked() else [bid for bid, check in checks if check.isChecked()]
            self.controller.set_section_performance(settings)

    def update_runtime(self):
        state = self.controller.host.engine.director.phrase
        section = self.controller._selected_section()
        active = state.running and state.memory.get("section_owner") == section["id"]
        self.stages.set_active(state.stage_index if active else -1)


class SectionInstrumentCard(QFrame):
    def __init__(self, block, controller):
        super().__init__()
        self.block = block
        self.controller = controller
        self.syncing = False
        self.setObjectName("sectionInstrument")
        self.setMinimumWidth(470)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 6, 7, 6)
        outer.setSpacing(8)
        self.body = QVBoxLayout()
        self.body.setSpacing(2)
        outer.addLayout(self.body, 1)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.type_icon = QLabel()
        self.type_icon.setFixedSize(22, 22)
        self.type_icon.setToolTip(block.block_type)
        title_row.addWidget(self.type_icon)
        self.role = QLabel(block.block_type)
        self.role.setFixedWidth(55)
        self.name = QLabel(block.name)
        self.name.setObjectName("blockName")
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        title_row.addWidget(self.role)
        title_row.addWidget(self.name, 1)
        self.active = QCheckBox("Active")
        self.active.setToolTip("Allow this instrument to emit notes in the selected section")
        title_row.addWidget(self.active)
        self.body.addLayout(title_row)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(dot("#b493ed", "Perform technique for this section"))
        row.addWidget(QLabel("Technique"))
        self.technique = QComboBox()
        self.technique.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.technique.addItem("Inherit phrase", None)
        self.technique.addItem("None", "none")
        for preset in presets_for_entity(block):
            self.technique.addItem(preset.name, preset.id)
        row.addWidget(self.technique, 1)
        self.body.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("Amount"))
        self.amount = QSlider(Qt.Horizontal)
        self.amount.setRange(0, 100)
        self.amount.setMinimumWidth(30)
        row.addWidget(self.amount, 1)
        self.amount_value = QLabel("100%")
        self.amount_value.setFixedWidth(32)
        row.addWidget(self.amount_value)
        self.shape = QComboBox()
        for name, key in (("In", "in"), ("Out", "out"), ("Out–in–out", "in_out"), ("In–pulse", "pulse")):
            self.shape.addItem(name, key)
        self.shape.setFixedWidth(91)
        self.shape.setToolTip("In: slow start, then faster; Out: fast start, then slower; Out–in–out: eased start and end; In–pulse: rise and return.")
        row.addWidget(self.shape)
        self.fit = QCheckBox("Fit")
        self.fit.setToolTip("Stretch the technique over the entire section; otherwise hold its endpoint after the chosen duration")
        row.addWidget(self.fit)
        self.beats = spin(.25, 1024, 4, 65)
        self.beats.setSuffix(" b")
        row.addWidget(self.beats)
        self.body.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(5)
        self.coefficients = {}
        for key, label, low, high, default in (("gate", "Gate", .25, 2, 1), ("density", "Density", 0, 1, 1),
                                              ("velocity", "Velocity", 0, 1.5, 1), ("register_center", "Center", -24, 24, 0)):
            caption = QHBoxLayout()
            caption.setSpacing(3)
            caption.addWidget(dot("#4fc99d", "Composition section coefficient"))
            caption.addWidget(QLabel(label))
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addLayout(caption)
            row.addLayout(cell)
            control = spin(low, high, default, 54)
            if key == "register_center" and block.block_type == "DRUM":
                control.setEnabled(False)
                control.setToolTip("Register Center affects pitched instruments; Drum Voice base notes remain fixed")
            control.valueChanged.connect(lambda value, k=key: self.coefficient_changed(k, value))
            cell.addWidget(control)
            self.coefficients[key] = control
        self.body.addLayout(row)
        footer = QHBoxLayout()
        footer.setSpacing(6)
        self.mode = QComboBox()
        self.mode.addItems(["SEQ", "LIVE"])
        self.mode.setFixedWidth(70)
        self.mode.setToolTip("Instrument playback mode, shared by all sections")
        footer.addWidget(self.mode)
        self.mute = QCheckBox("Mute")
        self.mute.setToolTip("Global instrument mute, shared by all sections")
        footer.addWidget(self.mute)
        self.status = QLabel("Inherit phrase")
        self.status.setObjectName("muted")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        footer.addWidget(self.status, 1)
        self.details = QPushButton("Voices…" if getattr(block, "drum_voices", None) else "Details…")
        self.details.setFixedWidth(66)
        footer.addWidget(self.details)
        self.body.addLayout(footer)
        self.curve = controller.curve_factory()
        self.curve.setFixedSize(112, 80)
        self.curve.primary_color = controller.block_color(controller.host.project, block)
        outer.addWidget(self.curve, 0, Qt.AlignVCenter)
        self.active.toggled.connect(lambda value: self.coefficient_changed("enabled", bool(value)))
        self.technique.currentIndexChanged.connect(self.technique_changed)
        self.amount.valueChanged.connect(self.technique_changed)
        self.shape.currentIndexChanged.connect(self.technique_changed)
        self.fit.toggled.connect(self.technique_changed)
        self.beats.valueChanged.connect(self.technique_changed)
        self.mode.currentTextChanged.connect(self.mode_changed)
        self.mute.toggled.connect(self.mute_changed)
        self.details.clicked.connect(lambda: controller.show_block_details(block))
        self.apply_theme()
        self.sync()

    def apply_theme(self):
        theme = theme_palette(self.controller.host.theme_combo.currentText())
        self.type_icon.setPixmap(block_type_icon(self.block.block_type, theme.text, 22).pixmap(22, 22))
        color = self.controller.block_color(self.controller.host.project, self.block)
        self.setStyleSheet(f"QFrame#sectionInstrument {{ background:{theme.card};border:1px solid {theme.border};border-left:4px solid {color};border-radius:7px; }}")
        ink = color
        for _ in range(12):
            if contrast_ratio(ink, theme.card) >= 4.5:
                break
            ink = QColor(ink).darker(112).name() if is_light_theme(theme) else QColor(ink).lighter(112).name()
        self.role.setStyleSheet(f"color:{ink};font-weight:600;")
        self.curve.update()

    def entities(self):
        return getattr(self.block, "drum_voices", None) or [self.block]

    def sync(self):
        self.syncing = True
        section = self.controller._selected_section()
        settings = normalize_performance(section.get("performance"))
        override = settings["techniques"].get(str(self.block.id), {})
        pid = override.get("preset_id")
        index = self.technique.findData(pid)
        if index < 0:
            self.technique.addItem(f"Unavailable: {pid}", pid)
            index = self.technique.count()-1
        self.technique.setCurrentIndex(index)
        self.amount.setValue(round(override.get("amount", 1)*100))
        self.amount_value.setText(f"{self.amount.value()}%")
        self.shape.setCurrentIndex(max(0, self.shape.findData(override.get("shape", "in"))))
        self.fit.setChecked(override.get("fit_to_section", True))
        self.beats.setValue(section["bars"] * self.controller.runtime.bar_beats() if self.fit.isChecked() else override.get("beats", 4))
        explicit = bool(pid and pid != "none")
        self.amount.setEnabled(explicit)
        self.shape.setEnabled(explicit)
        self.fit.setEnabled(explicit)
        self.beats.setVisible(explicit and not self.fit.isChecked())
        values = [section.get("blocks", {}).get(str(entity.id), {}) for entity in self.entities()]
        self.active.setChecked(all(v.get("enabled", True) for v in values))
        self.active.setToolTip("Some voices differ; changing Active applies to the whole kit" if len({v.get("enabled", True) for v in values}) > 1 else "Active in this section")
        for key, control in self.coefficients.items():
            default = 0. if key == "register_center" else 1.
            samples = [float(v.get(key, default)) for v in values]
            control.setValue(samples[0] if samples else default)
            control.setToolTip("Mixed Drum Voice values; editing applies to all voices" if len(set(samples)) > 1 else "Composition section coefficient")
        self.mode.setCurrentText(self.block.mode)
        self.mute.setChecked(self.block.muted)
        self.syncing = False
        bind_attributes(self, "section_instrument")
        bind_controls(self.coefficients, "section_instrument")
        self.update_runtime()

    def coefficient_changed(self, key, value):
        if not self.syncing:
            self.controller.set_card_value(self.block, key, value)

    def technique_changed(self, *_):
        if self.syncing:
            return
        settings = normalize_performance(self.controller._selected_section().get("performance"))
        pid = self.technique.currentData()
        if pid is None:
            settings["techniques"].pop(str(self.block.id), None)
        else:
            old = settings["techniques"].get(str(self.block.id), {})
            settings["techniques"][str(self.block.id)] = {
                "preset_id": pid, "amount": self.amount.value()/100, "shape": self.shape.currentData(),
                "fit_to_section": self.fit.isChecked(), "beats": self.beats.value() if self.sender() is self.beats and not self.fit.isChecked() else old.get("beats", 4)}
        self.controller.set_section_performance(settings)

    def mode_changed(self, mode):
        if not self.syncing:
            self.controller.host._card_mode_changed(self.block.id, mode)
            self.sync()

    def mute_changed(self, value):
        if not self.syncing:
            self.controller.host._card_mute_changed(self.block.id, value)
            self.sync()

    def update_runtime(self):
        host = self.controller.host
        section = self.controller._selected_section()
        settings = normalize_performance(section.get("performance"))
        override = settings["techniques"].get(str(self.block.id))
        active = host.engine.performance.active.get(self.block.id)
        playing = host.transport.running and host.transport.playback_mode == "composition"
        live = bool(playing and active and active.owner_section == section["id"])
        preset = None
        amount, shape, progress = 1., "in", None
        status = "Inherit phrase"
        if live:
            preset = preset_for_entity(self.block, active.preset_id)
            amount, shape = active.amount, active.shape
            progress = min(1., active.elapsed_beats/max(.001, active.beats))
            status = f"{preset.name if preset else active.preset_id} · {round(progress*100)}%"
        elif override:
            preset = preset_for_entity(self.block, override["preset_id"])
            amount, shape = override["amount"], override["shape"]
            status = "None" if override["preset_id"] == "none" else preset.name if preset else "Unavailable technique"
        elif settings["phrase_id"] and (settings["block_ids"] is None or self.block.id in settings["block_ids"]):
            phrase = phrase_for(settings["phrase_id"])
            stage = resolve_phrase_stage(phrase, self.block.block_type, 0)
            preset = preset_for_entity(self.block, stage.technique_id)
            amount, shape = stage.amount * settings["amount"], stage.shape
            status = "Phrase · " + (preset.name if preset else stage.technique_id.replace('_', ' ').title())
        else:
            status = "No technique"
        preview = (preset, amount, shape)
        if preview != getattr(self, "_preview", None):
            self._preview = preview
            self.curve.set_technique(preset, amount, shape)
        self.curve.set_progress(progress)
        self.status.setText(status)
        self.status.setToolTip(status)
        self.mode.blockSignals(True); self.mode.setCurrentText(self.block.mode); self.mode.blockSignals(False)
        self.mute.blockSignals(True); self.mute.setChecked(self.block.muted); self.mute.blockSignals(False)


class SectionInstrumentGrid(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(7)
        self.cards = {}
        self.signature = None
        self.columns = 0

    def refresh(self):
        blocks = self.controller.host.project.blocks
        signature = tuple((id(b), b.id, b.name, b.block_type, b.algorithm, getattr(b, "color", ""), bool(b.parameters.get("kit_coordinated"))) for b in blocks)
        if signature != self.signature:
            previous = dict(self.cards)
            cards = {}
            for block, token in zip(blocks, signature):
                card = previous.pop(block.id, None)
                if card is not None and getattr(card, "_render_signature", None) != token:
                    self.grid.removeWidget(card); card.hide(); card.deleteLater(); card = None
                if card is None:
                    card = SectionInstrumentCard(block, self.controller)
                    card._render_signature = token
                cards[block.id] = card
            for card in previous.values():
                self.grid.removeWidget(card)
                card.hide()
                card.deleteLater()
            self.cards = cards
            self.signature = signature
            self.columns = 0
            self.reflow()
        else:
            for card in self.cards.values():
                card.sync()

    def reflow(self):
        columns = 2 if self.controller.editor_scroll.viewport().width() >= 980 else 1
        if columns == self.columns:
            return
        self.columns = columns
        for index, card in enumerate(self.cards.values()):
            self.grid.removeWidget(card)
            self.grid.addWidget(card, index//columns, index%columns)
        for index in range(2):
            self.grid.setColumnStretch(index, 1 if index < columns else 0)
            self.grid.setColumnMinimumWidth(index, 0)
        self.grid.invalidate()
        self.updateGeometry()

    def update_runtime(self):
        for card in self.cards.values():
            card.update_runtime()
