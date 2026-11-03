"""Compact optional Drum rhythm controls, kept outside the main GUI module."""
from copy import deepcopy

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QPen, QBrush, QPalette
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout,
                              QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from help_tooltips import bind_help, bind_attributes, refresh_tree

from drum_rhythm import (LINK_DESCRIPTIONS, LINK_OPERATIONS, MAP_DEFAULTS, MAP_PRESETS,
                         RHYTHM_ENGINES, enable_musical_kit, integer, rhythm_engine,
                         suggested_links, unit)
from metric_kit import (METRIC_PARAMETERS, event_probabilities, metric_profile,
                        metric_settings, metric_weights)


class MetricPreview(QWidget):
    """Small cached probability display; no timer or model writes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kitMetricPreview")
        self.setFixedSize(200, 90)
        self.setAccessibleName("Metric pulse probabilities before role orchestration")
        self.setToolTip("Barlow probabilities before role orchestration and syncopation. Lines mark metric groups; bar height shows event probability, not velocity.")
        self._token, self._values, self._groups = None, (), ()

    def setProfile(self, groups, density, strength):
        token = (tuple(groups), density, strength)
        if token == self._token:
            return
        self._token, self._groups = token, tuple(groups)
        self._values = event_probabilities(metric_weights(metric_profile(tuple(groups)), density), strength)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(QPalette.Base))
        area = QRectF(5, 5, self.width() - 10, self.height() - 24)
        count = len(self._values)
        if count:
            width = area.width() / count
            painter.setPen(Qt.NoPen)
            painter.setBrush(palette.color(QPalette.Highlight))
            for i, probability in enumerate(self._values):
                height = area.height() * probability
                painter.drawRect(QRectF(area.left() + i * width + 1,
                                        area.bottom() - height, max(1., width - 2), height))
            painter.setPen(QPen(palette.color(QPalette.PlaceholderText), 1, Qt.DotLine))
            for group in range(1, len(self._groups)):
                x = area.left() + sum(self._groups[:group]) * width
                painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
        painter.setPen(palette.color(QPalette.Text))
        painter.drawText(QRectF(0, self.height() - 18, self.width(), 16), Qt.AlignCenter,
                         "Metric probability · 1/16")
        painter.end()


class RhythmMapPad(QWidget):
    """Small two-axis control for continuous groove-map morphing."""
    coordinatesChanged = Signal(float, float)

    def __init__(self, x=.25, y=.25, parent=None):
        super().__init__(parent)
        self._x = max(0.0, min(1.0, float(x)))
        self._y = max(0.0, min(1.0, float(y)))
        self.setObjectName("kitRhythmMapPad")
        self.setFixedSize(174, 112)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip("Drag the point: left → straight, right → broken; bottom → pocket, top → driving.")
        self.setAccessibleName("Rhythm map morph pad")
        self.setAccessibleDescription("Horizontal axis changes straight to broken. Vertical axis changes pocket to driving.")

    def coordinates(self):
        return self._x, self._y

    def setCoordinates(self, x, y):
        x = max(0.0, min(1.0, float(x)))
        y = max(0.0, min(1.0, float(y)))
        if abs(x - self._x) < 1e-6 and abs(y - self._y) < 1e-6:
            return
        self._x, self._y = x, y
        self.update()

    def _plot_rect(self):
        return QRectF(9, 8, self.width() - 18, self.height() - 27)

    def _set_from_position(self, point):
        rect = self._plot_rect()
        x = max(0.0, min(1.0, (point.x() - rect.left()) / max(1.0, rect.width())))
        y = max(0.0, min(1.0, 1.0 - (point.y() - rect.top()) / max(1.0, rect.height())))
        if abs(x - self._x) < .003 and abs(y - self._y) < .003:
            return
        self._x, self._y = x, y
        self.update()
        self.coordinatesChanged.emit(round(x, 3), round(y, 3))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._set_from_position(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._set_from_position(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        step = .02 if event.modifiers() & Qt.ShiftModifier else .05
        x, y = self._x, self._y
        if event.key() == Qt.Key_Left: x -= step
        elif event.key() == Qt.Key_Right: x += step
        elif event.key() == Qt.Key_Down: y -= step
        elif event.key() == Qt.Key_Up: y += step
        elif event.key() == Qt.Key_Home: x, y = 0.0, 0.0
        elif event.key() == Qt.Key_End: x, y = 1.0, 1.0
        else:
            super().keyPressEvent(event)
            return
        self._set_from_position(QPointF(self._plot_rect().left() + x * self._plot_rect().width(),
                                        self._plot_rect().bottom() - y * self._plot_rect().height()))
        event.accept()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        palette = self.palette()
        text = palette.color(QPalette.ColorRole.Text)
        muted = palette.color(QPalette.ColorRole.PlaceholderText)
        accent = palette.color(QPalette.ColorRole.Highlight)
        rect = self._plot_rect()
        painter.setPen(QPen(muted, 1))
        painter.setBrush(QBrush(palette.color(QPalette.ColorRole.Base)))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QPen(muted, 1, Qt.DotLine))
        painter.drawLine(QPointF(rect.center().x(), rect.top()), QPointF(rect.center().x(), rect.bottom()))
        painter.drawLine(QPointF(rect.left(), rect.center().y()), QPointF(rect.right(), rect.center().y()))
        painter.setPen(text)
        font = painter.font(); font.setPointSize(max(6, font.pointSize() - 2)); painter.setFont(font)
        painter.drawText(rect.adjusted(4, 2, -4, -2), Qt.AlignTop | Qt.AlignLeft, "DRIVE / STRAIGHT")
        painter.drawText(rect.adjusted(4, 2, -4, -2), Qt.AlignTop | Qt.AlignRight, "DRIVE / BROKEN")
        painter.drawText(rect.adjusted(4, 2, -4, -2), Qt.AlignBottom | Qt.AlignLeft, "POCKET / STRAIGHT")
        painter.drawText(rect.adjusted(4, 2, -4, -2), Qt.AlignBottom | Qt.AlignRight, "POCKET / BROKEN")
        px = rect.left() + self._x * rect.width()
        py = rect.bottom() - self._y * rect.height()
        painter.setPen(QPen(accent, 2))
        painter.setBrush(QBrush(accent))
        painter.drawEllipse(QPointF(px, py), 5.5, 5.5)
        painter.setPen(QPen(palette.color(QPalette.ColorRole.Base), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(px, py), 8, 8)
        painter.setPen(muted)
        painter.drawText(QRectF(4, self.height() - 17, self.width() - 8, 14), Qt.AlignCenter,
                         f"STRAIGHT  ←  X {self._x:.2f}  →  BROKEN")
        painter.end()


class DrumRhythmPanel(QWidget):
    def __init__(self, editor, knob_class, spin_class, label_factory, parent=None,
                 *, range_knob_class=None):
        super().__init__(parent)
        self.editor, self.host, self.drum = editor, editor.host, editor.drum
        self.setObjectName("drumRhythmPanel")
        self._spin_class = spin_class
        self._link_controls = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 3, 0, 0); outer.setSpacing(4)
        header = QHBoxLayout(); header.setSpacing(6)
        header.addWidget(QLabel("Rhythm engine"))
        self.engine_selector = QComboBox(); self.engine_selector.setObjectName("kitEngine")
        for label, key in RHYTHM_ENGINES:
            self.engine_selector.addItem(label, key)
        self.engine_selector.setCurrentIndex(self.engine_selector.findData(rhythm_engine(self.drum)))
        self.engine_selector.setToolTip("Role grid: classic kit. Rhythm map: groove skeletons. Metric / Barlow: metre-derived probabilities and bounded anticipation.")
        self.engine_selector.currentIndexChanged.connect(self._engine_changed)
        header.addWidget(self.engine_selector)
        self.motifs = QCheckBox("Motifs"); self.motifs.setObjectName("kitMotifs")
        self.motifs.setChecked(bool(self.drum.parameters.get("kit_motif_enabled", False)))
        self.motifs.setToolTip("Theme → Variation / Answer / Fill → Return. Replay and seeking reproduce the same development.")
        self.motifs.toggled.connect(lambda checked: editor._set_config("kit_motif_enabled", checked))
        header.addWidget(self.motifs)
        header.addWidget(QLabel("Return · phrases"))
        self.return_every = spin_class(); self.return_every.setObjectName("kitMotifReturn")
        self.return_every.setRange(2, 16)
        self.return_every.setValue(integer(self.drum.parameters.get("kit_motif_return", 4), 4, 2, 16))
        self.return_every.setFixedWidth(65)
        self.return_every.setToolTip("Periodically return to the original theme after this many kit phrases.")
        self.return_every.valueChanged.connect(lambda value: editor._set_config("kit_motif_return", int(value)))
        header.addWidget(self.return_every)
        self.state_label = QLabel("Theme"); self.state_label.setObjectName("kitMotifState")
        self.state_label.setMinimumWidth(65); header.addWidget(self.state_label)
        header.addStretch(1)
        self.activate = QPushButton("Musical kit"); self.activate.setObjectName("kitMusicalPreset")
        self.activate.setToolTip("Enable Rhythm map, motifs and suggested voice links together. MIDI assignments, generators and processing stay as configured.")
        self.activate.clicked.connect(self._activate)
        header.addWidget(self.activate)
        self.more = QPushButton(); self.more.setObjectName("kitRhythmMore"); self.more.setCheckable(True)
        expanded = getattr(self.host, "_kit_rhythm_expanded", {}).get(self.drum.id, False)
        self.more.setChecked(expanded)
        self.more.toggled.connect(self._expand)
        header.addWidget(self.more)
        outer.addLayout(header)
        self.body = QWidget()
        body = QVBoxLayout(self.body); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(3)
        controls = QHBoxLayout(); controls.setSpacing(8)
        self.knobs = []
        self._map_widgets = []
        self._metric_widgets = []
        descriptions = {
            "kit_map_x": ("Map X", "Horizontal morph: straight / pocket → broken / offbeat. Core meter anchors remain protected."),
            "kit_map_y": ("Map Y", "Vertical morph: restrained → driving. Density removes decoration before core beats."),
            "kit_motif_change": ("Development", "Probability of motif transformations and transitions. Zero repeats the theme; Fill still sets the end-of-phrase fill amount."),
        }
        for key, default in MAP_DEFAULTS.items():
            label, tooltip = descriptions[key]
            knob = knob_class(unit(self.drum.parameters, key, default), default=default)
            knob.bind_parameter(self.drum.id, key); knob.setObjectName(key)
            knob.setAccessibleName("Kit " + label); knob.setToolTip(tooltip); knob.setFixedWidth(54)
            knob.changed.connect(lambda value, k=key: self._map_knob_changed(k, value)
                                 if k in ("kit_map_x", "kit_map_y")
                                 else self.host._set_drum_kit_parameter(self.drum, k, value))
            cell = QWidget(); cell.setFixedWidth(74)
            column = QVBoxLayout(cell); column.setContentsMargins(0, 0, 0, 0); column.setSpacing(0)
            title = label_factory(label, knob); title.setObjectName("knobLabel"); title.setAlignment(Qt.AlignCenter)
            column.addWidget(title); column.addWidget(knob, 0, Qt.AlignCenter)
            controls.addWidget(cell); self.knobs.append(knob)
            if key != "kit_motif_change":
                self._map_widgets.append(cell)
        map_cell = QWidget(); map_layout = QVBoxLayout(map_cell)
        map_layout.setContentsMargins(2, 0, 2, 0); map_layout.setSpacing(0)
        map_title = QLabel("Groove map"); map_title.setObjectName("knobLabel")
        map_title.setAlignment(Qt.AlignCenter)
        self.map_preset = QComboBox(); self.map_preset.setObjectName("kitMapPreset")
        self.map_preset.addItem("Custom", None)
        for name, preset_x, preset_y in MAP_PRESETS:
            self.map_preset.addItem(name, (preset_x, preset_y))
        self.map_preset.currentIndexChanged.connect(self._apply_map_preset)
        self.map_pad = RhythmMapPad(unit(self.drum.parameters, "kit_map_x", .25),
                                    unit(self.drum.parameters, "kit_map_y", .25))
        self.map_pad.coordinatesChanged.connect(self._map_coordinates_changed)
        map_layout.addWidget(map_title); map_layout.addWidget(self.map_preset); map_layout.addWidget(self.map_pad)
        self._sync_map_preset()
        controls.addWidget(map_cell)
        self._map_widgets.append(map_cell)
        self.metric_knobs = []
        metric_labels = {"kit_metric_density": ("Density R", "R · 0–1. Sets weight ranges at each metric stratum. Zero retains a sparse metric skeleton; Master Density zero silences the kit."),
                         "kit_metric_strength": ("Strength M", "M · 0–1. One follows metric accents; zero distributes the same expected event count uniformly. Accent placement becomes less metric as M falls."),
                         "kit_metric_fragment": ("Fragment", "1–8 pulses (16ths). Maximum consecutive one-pulse anticipations. Then the run resolves at the next metric group. Syncopation above is the independent probability PS.")}
        for key, (default, low, high) in METRIC_PARAMETERS.items():
            label, tooltip = metric_labels[key]
            value = metric_settings(self.drum)[list(METRIC_PARAMETERS).index(key)]
            if key == "kit_metric_fragment":
                if range_knob_class is None:
                    from auricle_gui import RangeKnob
                    range_knob_class = RangeKnob
                knob = range_knob_class(low, high, value, integer=True, default=default)
            else:
                knob = knob_class(value, default=default)
            knob.bind_parameter(self.drum.id, key)
            knob.setObjectName(key); knob.setAccessibleName("Kit " + label)
            knob.setFixedWidth(54); knob.setToolTip(tooltip)
            knob.changed.connect(lambda value, k=key: self.host._set_param(
                self.drum, k, int(round(value)) if k == "kit_metric_fragment" else float(value)))
            cell = QWidget(); cell.setFixedWidth(74)
            column = QVBoxLayout(cell); column.setContentsMargins(0, 0, 0, 0); column.setSpacing(0)
            title = label_factory(label, knob); title.setObjectName("knobLabel"); title.setAlignment(Qt.AlignCenter)
            column.addWidget(title); column.addWidget(knob, 0, Qt.AlignCenter)
            controls.addWidget(cell); self.metric_knobs.append(knob); self._metric_widgets.append(cell)
        self.metric_preview = MetricPreview()
        controls.addWidget(self.metric_preview); self._metric_widgets.append(self.metric_preview)
        self.explanation = QLabel()
        self.explanation.setObjectName("muted"); self.explanation.setWordWrap(True)
        self.explanation.setMinimumWidth(120)
        controls.addWidget(self.explanation, 1)
        body.addLayout(controls)
        toolbar = QHBoxLayout(); toolbar.setSpacing(8)
        self.links_enabled = QCheckBox("Voice links"); self.links_enabled.setObjectName("kitLinksEnabled")
        self.links_enabled.setChecked(bool(self.drum.parameters.get("kit_links_enabled", False)))
        self.links_enabled.setToolTip("All links read one frozen candidate plan. Influence and chance are independent; delay and phase are separate. Anchors and fills are protected; cycles are deterministic.")
        self.links_enabled.toggled.connect(lambda checked: editor._set_config("kit_links_enabled", checked))
        toolbar.addWidget(self.links_enabled)
        self.link_warning = QLabel(); self.link_warning.setObjectName("kitLinkWarning")
        toolbar.addWidget(self.link_warning, 1)
        self.suggest_links = QPushButton("Suggest")
        self.suggest_links.setObjectName("kitSuggestLinks")
        self.suggest_links.setToolTip("Add role-aware links: snare answers, percussion fills kick gaps, and hats interlock.")
        self.suggest_links.clicked.connect(self._suggest_links)
        toolbar.addWidget(self.suggest_links)
        self.add_link = QPushButton("+ Add link"); self.add_link.setObjectName("kitAddLink")
        self.add_link.clicked.connect(self._add_link); toolbar.addWidget(self.add_link)
        body.addLayout(toolbar)
        self.links_body = QWidget(); self.links_layout = QGridLayout(self.links_body)
        self.links_layout.setContentsMargins(0, 0, 0, 0)
        self.links_layout.setHorizontalSpacing(5); self.links_layout.setVerticalSpacing(3)
        body.addWidget(self.links_body)
        outer.addWidget(self.body)
        self._build_links()
        bind_attributes(self, "kit", {"engine_selector": "kit_engine", "motifs": "kit_motif_enabled", "return_every": "kit_motif_return", "links_enabled": "kit_links_enabled", "map_pad": "kit_map_x", "map_preset": "kit_map_y"})
        refresh_tree(self)
        self._sync_engine_view()
        self._expand(expanded)

    def _engine_changed(self, _index):
        self.editor._set_config("kit_engine", self.engine_selector.currentData())
        self._sync_engine_view()
        self._expand(self.more.isChecked())

    def _sync_engine_view(self):
        metric = self.engine_selector.currentData() == "metric"
        for widget in self._map_widgets:
            widget.setVisible(not metric)
        for widget in self._metric_widgets:
            widget.setVisible(metric)
        self.activate.setText("Metric kit" if metric else "Musical kit")
        self.activate.setToolTip("Enable the selected musical engine, motifs and suggested links. Existing MIDI assignments and voice generators are preserved.")
        self.explanation.setText("R → density · M → metric strength\nSyncopation = PS · Fragment limits anticipation runs."
                                 if metric else "One shared groove · ornaments thin before anchors\nMotifs follow kit phrases; Composition adds section cadences.")

    def _expand(self, expanded):
        expanded = bool(expanded)
        self.body.setVisible(expanded)
        self.more.setText("Less ▴" if expanded else "Settings ▾")
        states = getattr(self.host, "_kit_rhythm_expanded", {})
        states[self.drum.id] = expanded
        self.host._kit_rhythm_expanded = states

        # The Rhythm Settings body is nested inside DrumKitEditor, which in
        # turn lives in the persistent Inspector scroll host.  Hiding the body
        # changes the natural height of all three layouts; explicitly
        # invalidate them so the accordion really collapses instead of leaving
        # the old minimum-height reservation behind.
        for widget in (self, self.editor, getattr(self.editor, "body", None)):
            if widget is None:
                continue
            layout = widget.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()
            widget.updateGeometry()
        self.editor._sync_layout_geometry()
        self.editor.updateGeometry()
        host_layout = getattr(self.host, "drum_kit_layout", None)
        if host_layout is not None:
            host_layout.invalidate()
            host_layout.activate()
        # Let Qt finish propagating the visibility/layout change before
        # recomputing the QScrollArea content extent.
        queue_fit = getattr(self.host, "_queue_inspector_fit", None)
        if callable(queue_fit):
            queue_fit()

    def _activate(self):
        with self.host.transport._state_lock:
            if not any(block is self.drum for block in self.host.project.blocks):
                return
            enable_musical_kit(self.drum)
            if self.engine_selector.currentData() == "metric":
                self.drum.parameters["kit_engine"] = "metric"
                for key, (default, _low, _high) in METRIC_PARAMETERS.items():
                    self.drum.parameters.setdefault(key, default)
            self.host.engine.regenerate(self.drum)
        self.host._mark_dirty()
        self.host._kit_rhythm_expanded[self.drum.id] = True
        self.host._kit_source_view = False
        self.host._queue_inspector_refresh()

    def _raw_links(self):
        raw = self.drum.parameters.get("kit_voice_links", [])
        return [deepcopy(item) for item in raw[:64] if isinstance(item, dict)] if isinstance(raw, list) else []

    def _voice_combo(self, value):
        combo = QComboBox()
        for i, voice in enumerate(self.drum.drum_voices):
            dot = QPixmap(10, 10); dot.fill(QColor(voice.color or self.editor.VOICE_COLORS[i % len(self.editor.VOICE_COLORS)]))
            combo.addItem(QIcon(dot), voice.name, voice.id)
        if combo.findData(value) < 0:
            combo.addItem(f"Missing voice ({value})", value)
        combo.setCurrentIndex(combo.findData(value))
        combo.setMinimumWidth(90)
        return combo

    def _build_links(self):
        while self.links_layout.count():
            item = self.links_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide(); widget.deleteLater()
        self._link_controls.clear()
        links = self._raw_links()
        if links:
            heading = QLabel("Each link reads the same frozen candidate plan · anchors and fills are protected")
            heading.setObjectName("muted")
            self.links_layout.addWidget(heading, 0, 0, 1, 7)
        for row, item in enumerate(links, 1):
            index = row - 1
            card = QWidget(); card.setObjectName(f"kitLinkCard_{index}")
            card_layout = QVBoxLayout(card); card_layout.setContentsMargins(2, 3, 2, 4); card_layout.setSpacing(3)
            top = QHBoxLayout(); top.setSpacing(4)
            enabled = QCheckBox(); enabled.setChecked(bool(item.get("enabled", True)))
            enabled.setToolTip("Enable this voice relationship")
            source = self._voice_combo(item.get("source"))
            source.setMinimumWidth(82)
            operation = QComboBox()
            for label, key in LINK_OPERATIONS:
                operation.addItem(label, key)
                operation.setItemData(operation.count() - 1, LINK_DESCRIPTIONS.get(key, ""), Qt.ToolTipRole)
            if operation.findData(item.get("operation")) < 0:
                operation.addItem("Unsupported operation", item.get("operation"))
            operation.setCurrentIndex(operation.findData(item.get("operation")))
            operation.setMinimumWidth(112)
            destination = self._voice_combo(item.get("destination"))
            destination.setMinimumWidth(82)
            remove = QPushButton("×"); remove.setFixedWidth(25)
            for widget, name in ((enabled, "enabled"), (source, "source"), (operation, "operation"),
                                 (destination, "destination"), (remove, "remove")):
                widget.setObjectName(f"kitLink_{index}_{name}")
            top.addWidget(enabled); top.addWidget(source, 1); top.addWidget(operation, 1)
            top.addWidget(destination, 1); top.addWidget(remove)
            card_layout.addLayout(top)

            bottom = QHBoxLayout(); bottom.setSpacing(4)
            delay = self._spin_class(); delay.setRange(0, 32); delay.setFixedWidth(52)
            delay.setValue(integer(item.get("delay", 0), 0, 0, 32))
            delay.setToolTip("Causal delay in sixteenth-note slots. Positive values make the destination respond later.")
            phase = self._spin_class(); phase.setRange(-32, 32); phase.setFixedWidth(52)
            phase.setValue(integer(item.get("phase", 0), 0, -32, 32))
            phase.setToolTip("Signed cyclic phase offset in sixteenth-note slots; independent from causal delay.")
            amount = QDoubleSpinBox(); amount.setRange(0, 1); amount.setSingleStep(.05); amount.setDecimals(2)
            amount.setValue(unit(item, "amount", .75)); amount.setFixedWidth(58)
            amount.setToolTip("Influence strength: how strongly this relationship affects destination events.")
            probability = QDoubleSpinBox(); probability.setRange(0, 1); probability.setSingleStep(.05); probability.setDecimals(2)
            probability.setValue(unit(item, "probability", 1.0)); probability.setFixedWidth(58)
            probability.setToolTip("Probability that this relationship is evaluated at each eligible slot.")
            for widget, name in ((delay, "delay"), (phase, "phase"), (amount, "amount"),
                                 (probability, "probability")):
                widget.setObjectName(f"kitLink_{index}_{name}")
            for title, widget in (("Delay", delay), ("Phase", phase),
                                  ("Influence", amount), ("Chance", probability)):
                bottom.addWidget(QLabel(title)); bottom.addWidget(widget)
            bottom.addStretch(1)
            card_layout.addLayout(bottom)
            self.links_layout.addWidget(card, row, 0, 1, 7)
            for key, widget in (("enabled", enabled), ("source", source), ("operation", operation), ("destination", destination),
                                ("delay", delay), ("phase", phase), ("amount", amount), ("probability", probability)):
                bind_help(widget, key, "kit_link")
            controls = (enabled, source, operation, destination, delay, phase, amount, probability, remove)
            enabled.toggled.connect(lambda value, i=index: self._edit_link(i, "enabled", value))
            source.currentIndexChanged.connect(lambda _, i=index, w=source: self._edit_link(i, "source", w.currentData()))
            destination.currentIndexChanged.connect(lambda _, i=index, w=destination: self._edit_link(i, "destination", w.currentData()))
            operation.currentIndexChanged.connect(lambda _, i=index, w=operation: self._edit_link(i, "operation", w.currentData()))
            delay.valueChanged.connect(lambda value, i=index: self._edit_link(i, "delay", int(value)))
            phase.valueChanged.connect(lambda value, i=index: self._edit_link(i, "phase", int(value)))
            amount.valueChanged.connect(lambda value, i=index: self._edit_link(i, "amount", value))
            probability.valueChanged.connect(lambda value, i=index: self._edit_link(i, "probability", value))
            remove.clicked.connect(lambda _, i=index: self._remove_link(i))
            self._link_controls.extend(controls)
        self._warnings()

    def _map_coordinates(self):
        # Continuous edits are committed by the transport worker. Until that
        # batch is applied, keep the latest authored coordinates visible rather
        # than reading the old model back into the pad/preset on a UI refresh.
        with self.host._pending_param_edits_lock:
            pending = dict(self.host._pending_param_edits.get(int(self.drum.id), {}))
        return tuple(unit(pending, key, unit(self.drum.parameters, key, MAP_DEFAULTS[key]))
                     for key in ("kit_map_x", "kit_map_y"))

    def _map_knob_changed(self, key, value):
        self.host._set_drum_kit_parameter(self.drum, key, value)
        self.map_pad.setCoordinates(*self._map_coordinates())
        self._sync_map_preset()

    def _sync_map_preset(self):
        x, y = self._map_coordinates()
        selected = 0
        for index in range(1, self.map_preset.count()):
            preset = self.map_preset.itemData(index)
            if preset and abs(x - preset[0]) <= .025 and abs(y - preset[1]) <= .025:
                selected = index
                break
        self.map_preset.blockSignals(True)
        self.map_preset.setCurrentIndex(selected)
        self.map_preset.blockSignals(False)

    def _apply_map_preset(self, index):
        preset = self.map_preset.itemData(index)
        if preset is not None:
            self.map_pad.setCoordinates(*preset)
            self._map_coordinates_changed(*preset)

    def _map_coordinates_changed(self, x, y):
        for key, value in (("kit_map_x", x), ("kit_map_y", y)):
            knob = next((item for item in self.knobs if item.objectName() == key), None)
            if knob is not None:
                knob.blockSignals(True); knob.setValue(value); knob.blockSignals(False)
            # Always submit both final values. Missing keys use implicit
            # defaults, and returning to the stored value must replace any
            # earlier queued drag. The host coalesces this into one batch.
            self.host._set_drum_kit_parameter(self.drum, key, value)
        self._sync_map_preset()

    def _suggest_links(self):
        links = self._raw_links()
        existing = {(item.get("source"), item.get("destination"), item.get("operation")) for item in links}
        added = [item for item in suggested_links(self.drum)
                 if (item["source"], item["destination"], item["operation"]) not in existing]
        if not added:
            self.link_warning.setText("Suggested role links are already present or the required voices are missing.")
            return
        links.extend(added[:max(0, 64 - len(links))])
        with self.host.transport._state_lock:
            if not any(block is self.drum for block in self.host.project.blocks):
                return
            self.drum.parameters["kit_links_enabled"] = True
        self.links_enabled.blockSignals(True); self.links_enabled.setChecked(True); self.links_enabled.blockSignals(False)
        self.editor._set_config("kit_voice_links", links); self._build_links()

    def _edit_link(self, index, key, value):
        links = self._raw_links()
        if index >= len(links):
            return
        links[index][key] = value
        if key == "operation" and value == "answer" and not links[index].get("delay"):
            links[index]["delay"] = 2
            delay = self.findChild(QWidget, f"kitLink_{index}_delay")
            if delay is not None:
                delay.blockSignals(True); delay.setValue(2); delay.blockSignals(False)
        self.editor._set_config("kit_voice_links", links)
        self._warnings()

    def _add_link(self):
        links = self._raw_links(); voices = self.drum.drum_voices
        if len(voices) < 2 or len(links) >= 64:
            return
        roles = {voice.parameters.get("kit_role"): voice.id for voice in voices if not voice.muted}
        source_id = roles.get("kick", voices[0].id)
        destination_id = roles.get("closed_hat", next((v.id for v in voices if v.id != source_id), voices[1].id))
        links.append(dict(source=source_id, destination=destination_id,
                          operation="support", delay=0, phase=0, amount=.45,
                          probability=.85, enabled=True))
        with self.host.transport._state_lock:
            if not any(block is self.drum for block in self.host.project.blocks):
                return
            self.drum.parameters["kit_links_enabled"] = True
        self.links_enabled.blockSignals(True); self.links_enabled.setChecked(True); self.links_enabled.blockSignals(False)
        self.editor._set_config("kit_voice_links", links); self._build_links()

    def _remove_link(self, index):
        links = self._raw_links()
        if index < len(links):
            del links[index]
            self.editor._set_config("kit_voice_links", links); self._build_links()

    def _warnings(self):
        links = self._raw_links()
        ids = {v.id for v in self.drum.drum_voices}
        invalid = any(type(item.get("source")) is not int or type(item.get("destination")) is not int
                      or item.get("source") not in ids or item.get("destination") not in ids
                      or item.get("source") == item.get("destination") for item in links)
        self.link_warning.setText("Choose two different voices; invalid links are skipped." if invalid else
                                 "Candidate-plan links · anchors protected" if links else "No links · + Add inserts an editable row")

    def update_state(self, active, plan=None, bar=0):
        mapped = active and rhythm_engine(self.drum) == "map"
        metric = active and rhythm_engine(self.drum) == "metric"
        self.engine_selector.setEnabled(active)
        self.motifs.setEnabled(mapped or metric)
        self.return_every.setEnabled((mapped or metric) and self.motifs.isChecked())
        for knob in self.knobs:
            knob.setEnabled((mapped or metric) and self.motifs.isChecked()
                            if knob.objectName() == "kit_motif_change" else mapped)
        for knob in self.metric_knobs:
            knob.setEnabled(metric)
        self.metric_preview.setEnabled(metric)
        if metric:
            from coordinated_kit import meter_groups
            values = self._metric_display_settings()
            self.metric_preview.setProfile(meter_groups(self.drum), values[0], values[1])
        self.links_enabled.setEnabled(active)
        self.add_link.setEnabled(active and len(self.drum.drum_voices) >= 2 and len(self._raw_links()) < 64)
        self.links_body.setEnabled(active and self.links_enabled.isChecked())
        self.suggest_links.setEnabled(active and len(self.drum.drum_voices) >= 2 and len(self._raw_links()) < 64)
        self.map_pad.setEnabled(mapped)
        self.map_preset.setEnabled(mapped)
        self.map_pad.setCoordinates(*self._map_coordinates())
        self._sync_map_preset()
        self.state_label.setText(plan.bar_states[min(bar, len(plan.bar_states) - 1)]
                                 if (mapped or metric) and plan and plan.bar_states and self.motifs.isChecked() else "—")

    def _metric_display_settings(self):
        # Honour the same pending edits as the map pad, without writing readback
        # into the authored parameter base or acquiring the transport model lock.
        values = dict(self.drum.parameters)
        lock = getattr(self.host, "_pending_param_edits_lock", None)
        if lock is not None:
            with lock:
                values.update(getattr(self.host, "_pending_param_edits", {}).get(int(self.drum.id), {}))
        return (unit(values, "kit_metric_density", .45), unit(values, "kit_metric_strength", .85))
