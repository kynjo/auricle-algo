"""Qt editor for the section-based Composition Planner."""
from __future__ import annotations

from copy import deepcopy
import uuid

from PySide6.QtCore import Qt, QSize, QRectF, QPointF, QTimer, QEvent, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QCheckBox, QComboBox, QDoubleSpinBox, QGroupBox, QHeaderView, QLineEdit,
    QListWidget, QListWidgetItem, QListView, QSlider, QSpinBox,
    QTableWidget, QTableWidgetItem, QSizePolicy, QAbstractItemView,
    QStyledItemDelegate, QStyle, QScrollArea, QFrame, QLayout, QToolButton, QColorDialog, QDialog,
    QTabWidget,
)

from composition_planner import (
    SECTION_TYPES, METERS, MACRO_KEYS, MACRO_LABELS, TYPE_MACRO_PRESETS,
    METER_BEATS, CompositionRuntime, default_composition, normalize_composition,
    make_section, default_block_settings,
    EXPRESSION_SPECS, expression_settings,
    END_ACTIONS, CONTROLLED_PARAMETERS, SECTION_COLORS, section_color, available_section_color,
)
from composition_automation import MACRO_COLORS, CURVE_SHAPES, normalize_curve, section_macro
from composition_curve_ui import MacroCurveEditor
from ui_themes import theme_palette, mix, is_light_theme
from transport_icons import transport_icon
from composition_performance import normalize_performance
from help_tooltips import bind_attributes, bind_controls, bind_table

from composition_performance_ui import SectionPhraseEditor, SectionInstrumentGrid
from section_automation_ui import SectionAutomationPanel
from ui_metrics import TRANSPORT_HEIGHT, TRANSPORT_WIDTH
from midi_expression_ui import MidiExpressionEditor
from midi_expression import normalize_expression, entity_expression_config, merge_expression_configs


NEUTRAL_BLOCK_SETTINGS = {"enabled": True, "density": 1.0, "velocity": 1.0,
                          "register_center": 0.0, "variation": 0.0, **expression_settings({})}


def time_label(seconds):
    seconds = max(0, int(round(seconds)))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


class SectionDelegate(QStyledItemDelegate):
    """Paint both selection and text together; native highlight cannot hide labels."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = theme_palette()

    def paint(self, painter, option, index):
        theme = self.theme
        selected = bool(option.state & QStyle.State_Selected)
        active = bool(index.data(Qt.UserRole + 1))
        rect = QRectF(option.rect).adjusted(1, 2, -1, -2)
        color = index.data(Qt.UserRole + 2) or theme.accent
        background = mix(theme.card, color, .28 if selected else .12)
        if active and not selected:
            background = mix(theme.card, theme.success, .14)
        border = color if selected else mix(theme.border, color, .70)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(background))
        painter.setPen(QPen(QColor(border), 2))
        painter.drawRoundedRect(rect, 6, 6)
        if active:
            painter.setPen(QPen(QColor(theme.success), 3))
            painter.drawLine(QPointF(rect.left() + 5, rect.top() + 8),
                             QPointF(rect.left() + 5, rect.bottom() - 8))
        # A small grip hints that a card can be dragged, even before hovering.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.muted))
        for y in (rect.center().y() - 5, rect.center().y(), rect.center().y() + 5):
            painter.drawEllipse(QPointF(rect.left() + 13, y), 1, 1)
        lines = str(index.data(Qt.DisplayRole) or "").splitlines()
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.text))
        title_rect = rect.adjusted(23, 7, -8, -24)
        title = painter.fontMetrics().elidedText(lines[0] if lines else "", Qt.ElideRight, int(title_rect.width()))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(theme.text if selected else theme.muted))
        detail_rect = rect.adjusted(23, 29, -8, -5)
        subtitle = painter.fontMetrics().elidedText(lines[1] if len(lines) > 1 else "", Qt.ElideRight, int(detail_rect.width()))
        painter.drawText(detail_rect, Qt.AlignLeft | Qt.AlignVCenter, subtitle)
        painter.restore()


class CompositionTimeline(QWidget):
    """Full-form bar ruler, section boundaries and transport playhead."""
    seekRequested = Signal(float)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = theme_palette()
        self.sections = ()
        self.total_bars = 1
        self.position_bars = 0.0
        self.progress = 0.0
        self.active_index = -1
        self.selected_id = None
        self.running = False
        self.dragging = False
        self.setFixedHeight(74)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName("Composition timeline")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click or drag to seek the shared transport. Release to apply the position, snapped to a sixteenth note. "
                        "Section widths follow their bar lengths; selecting a card only edits it.")

    def set_runtime(self, sections, position_bars, active_index, selected_id, running):
        if self.dragging:
            return
        state = (tuple((s["id"], s["name"], int(s["bars"]), section_color(s)) for s in sections),
                 float(position_bars), int(active_index), selected_id, bool(running))
        if state == getattr(self, "_state", None):
            return
        self._state = state
        self.sections, self.position_bars, self.active_index, self.selected_id, self.running = state
        self.total_bars = max(1, sum(s[2] for s in self.sections))
        self.progress = max(0.0, min(1.0, self.position_bars / self.total_bars))
        self.setAccessibleDescription(f"Bar {self.position_bars + 1:g} of {self.total_bars}")
        self.update()

    def track_rect(self):
        return QRectF(self.rect()).adjusted(12, 24, -12, -12)

    def _preview_seek(self, point):
        track = self.track_rect()
        self.progress = max(0., min(1., (point.x() - track.left()) / max(1., track.width())))
        self.position_bars = self.progress * self.total_bars
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.track_rect().adjusted(0, -12, 0, 6).contains(event.position()):
            self.dragging = True
            self._preview_seek(event.position())
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self._preview_seek(event.position())
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.dragging and event.button() == Qt.LeftButton:
            self._preview_seek(event.position())
            self.dragging = False
            self._state = None
            self.seekRequested.emit(self.position_bars)
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        theme = self.theme
        track = self.track_rect()
        if track.width() <= 0:
            return
        painter.fillRect(self.rect(), QColor(theme.panel))
        cursor = 0
        for index, (section_id, name, bars, section_ink) in enumerate(self.sections):
            left = track.left() + track.width() * cursor / self.total_bars
            width = track.width() * bars / self.total_bars
            segment = QRectF(left, track.top(), width, track.height())
            color = mix(theme.card, section_ink, .24)
            if self.running and index == self.active_index:
                color = mix(theme.card, section_ink, .45)
            painter.fillRect(segment, QColor(color))
            painter.setPen(QPen(QColor(section_ink if section_id == self.selected_id else mix(theme.muted, section_ink, .6)), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(segment)
            if width > 38:
                label = painter.fontMetrics().elidedText(name, Qt.ElideRight, max(1, int(width - 12)))
                painter.setPen(QColor(theme.text))
                painter.drawText(segment.adjusted(6, 0, -6, 0), Qt.AlignCenter, label)
            cursor += bars

        stride = 1
        while track.width() * stride / self.total_bars < 48:
            stride *= 2
        painter.setPen(QColor(theme.muted))
        for bar in range(0, self.total_bars, stride):
            x = track.left() + track.width() * bar / self.total_bars
            painter.drawLine(QPointF(x, track.top() - 5), QPointF(x, track.top()))
            if x < track.right() - 70:
                painter.drawText(QRectF(x - 10, 3, 42, 15), Qt.AlignLeft | Qt.AlignVCenter, str(bar + 1))
        painter.drawText(QRectF(track.right() - 65, 3, 65, 15), Qt.AlignRight | Qt.AlignVCenter, f"{self.total_bars} bars")
        x = track.left() + track.width() * self.progress
        painter.setPen(QPen(QColor(theme.accent2), 2))
        painter.drawLine(QPointF(x, track.top() - 6), QPointF(x, track.bottom() + 4))
        painter.setBrush(QColor(theme.accent2))
        painter.drawEllipse(QPointF(x, track.top() - 6), 3, 3)
        painter.end()


class CompositionPlannerPanel(QWidget):
    """Editable, reorderable section list with per-section/per-entity settings."""
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self._syncing = False
        self._entity_signature = None
        self._macro_widgets = {}
        self._expression_widgets = {}
        self._expression_entity = None
        self._table_entity_ids = []
        self.runtime = CompositionRuntime(host.project)
        self._draft_project = None
        self._draft_config = None
        self._reorder_timer = QTimer(self)
        self._reorder_timer.setSingleShot(True)
        self._reorder_timer.timeout.connect(self._finish_reorder)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(7)
        self.editor_scroll = QScrollArea(self)
        self.editor_scroll.setWidgetResizable(True)
        self.editor_scroll.setFrameShape(QFrame.NoFrame)
        self.editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.editor_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        editor = QWidget()
        self.editor_scroll.setWidget(editor)
        outer.addWidget(self.editor_scroll, 1)
        self.editor = editor
        root = QVBoxLayout(editor)
        self.editor_layout = root
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(7)
        root.setSizeConstraint(QLayout.SetMinimumSize)

        title_row = QHBoxLayout()
        self.title_row = title_row
        title = QLabel("COMPOSITION PLANNER")
        self.page_title = title
        title.setObjectName("pageTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.enabled = QCheckBox("Enable composition")
        self.enabled.setToolTip("Composition Play enables this plan and starts at the selected From position. "
                               "Header Play auditions Blocks without Composition or Perform; this checkbox only arms the plan. "
                               "Selecting a section only edits it; the timeline seeks the form during Composition playback.")
        self.enabled.toggled.connect(self._set_enabled)
        title_row.addWidget(self.enabled)
        title_row.addWidget(QLabel("Meter"))
        self.meter = QComboBox()
        self.meter.addItems(METERS)
        self.meter.setFixedWidth(82)
        self.meter.setToolTip("Global bar length for Composition Planner. 6/8 = 3 quarter-note beats; 7/8 = 3.5.")
        self.meter.currentTextChanged.connect(self._set_meter)
        title_row.addWidget(self.meter)
        root.addLayout(title_row)

        description = QLabel("Arrange any number of sections. Type presets provide a starting point; all block settings remain editable.")
        self.description = description
        description.setObjectName("muted")
        description.setWordWrap(True)
        root.addWidget(description)

        playback = QHBoxLayout()
        playback.setSpacing(6)
        self.play_button = QPushButton()
        self.play_button.setObjectName("transportPlay")
        self.play_button.setFixedSize(TRANSPORT_WIDTH, TRANSPORT_HEIGHT)
        self.play_button.setIconSize(QSize(20, 20))
        self.play_button.setAccessibleName("Play composition")
        self.play_button.setCheckable(True)
        self.play_button.setToolTip("Play/stop Composition independently of Blocks. Start from the From position.")
        self.play_button.clicked.connect(self._toggle_composition)
        playback.addWidget(self.play_button)
        self.stop_button = QPushButton()
        self.stop_button.setObjectName("transportStop")
        self.stop_button.setFixedSize(TRANSPORT_WIDTH, TRANSPORT_HEIGHT)
        self.stop_button.setIconSize(QSize(20, 20))
        self.stop_button.setAccessibleName("Stop composition")
        self.stop_button.setToolTip("Stop Composition and release its notes. Blocks playback is unaffected.")
        self.stop_button.clicked.connect(self._stop_composition)
        playback.addWidget(self.stop_button)
        playback.addWidget(QLabel("From"))
        self.play_from = QComboBox()
        for label, key in (("Selected section", "selected"), ("Form start", "start"), ("Timeline cursor", "cursor")):
            self.play_from.addItem(label, key)
        self.play_from.setFixedWidth(140)
        self.play_from.setAccessibleName("Composition playback start")
        playback.addWidget(self.play_from)
        playback.addWidget(QLabel("End"))
        self.ending = QComboBox()
        for key, label in END_ACTIONS:
            self.ending.addItem(label, key)
        self.ending.setFixedWidth(155)
        self.ending.setAccessibleName("Composition end action")
        self.ending.setToolTip("Loop form: repeat the arrangement. Stop at end: finish at its exact length and release notes. "
                               "Hold last section: keep generating using the final section's settings and curve endpoints.")
        self.ending.currentIndexChanged.connect(self._set_ending)
        playback.addWidget(self.ending)
        self.parameter_list_toggle = QToolButton()
        self.parameter_list_toggle.setText("Controlled parameters")
        self.parameter_list_toggle.setCheckable(True)
        self.parameter_list_toggle.setArrowType(Qt.RightArrow)
        self.parameter_list_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        playback.addWidget(self.parameter_list_toggle)
        playback.addStretch(1)
        root.addLayout(playback)
        self.parameter_list = QLabel("<br>".join(f"<b>{label}:</b> {values}" for label, values in CONTROLLED_PARAMETERS)
            + "<br>Register Center and Octave spread: pitched blocks only. Harmony: BASS/MELODY following Harmonic Plan. "
              "Curves and Blend in control macro movement; Meter and Duration control form time. "
              "AUTOMATION adds exact block/voice parameter values and curves, timed to musical boundaries.")
        self.parameter_list.setWordWrap(True)
        self.parameter_list.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.parameter_list.setVisible(False)
        self.parameter_list_toggle.toggled.connect(self._toggle_parameter_list)
        root.addWidget(self.parameter_list)

        section_toolbar = QHBoxLayout()
        section_toolbar.setSpacing(5)
        self.section_type_add = QComboBox()
        self.section_type_add.addItems(SECTION_TYPES)
        self.section_type_add.setFixedWidth(112)
        section_toolbar.addWidget(self.section_type_add)
        self.add_button = QPushButton("+ Section")
        self.add_button.clicked.connect(self.add_section)
        section_toolbar.addWidget(self.add_button)
        self.duplicate_button = QPushButton("Duplicate")
        self.duplicate_button.clicked.connect(self.duplicate_section)
        section_toolbar.addWidget(self.duplicate_button)
        self.up_button = QPushButton("↑")
        self.up_button.setFixedWidth(34)
        self.up_button.setToolTip("Move selected section earlier")
        self.up_button.clicked.connect(lambda: self.move_section(-1))
        section_toolbar.addWidget(self.up_button)
        self.down_button = QPushButton("↓")
        self.down_button.setFixedWidth(34)
        self.down_button.setToolTip("Move selected section later")
        self.down_button.clicked.connect(lambda: self.move_section(1))
        section_toolbar.addWidget(self.down_button)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("deleteButton")
        self.remove_button.clicked.connect(self.remove_section)
        section_toolbar.addWidget(self.remove_button)
        section_toolbar.addStretch(1)
        root.addLayout(section_toolbar)

        self.total_label = QLabel()
        self.total_label.setObjectName("sectionTitle")
        self.total_label.setWordWrap(True)
        self.total_label.setAccessibleName("Total composition length")
        self.total_label.setToolTip("Sum of every section, in bars, quarter-note beats and time at the current BPM. Loop repeats this length.")
        root.addWidget(self.total_label)

        self.section_list = QListWidget()
        self.section_list.setFlow(QListView.LeftToRight)
        self.section_list.setWrapping(False)
        self.section_list.setObjectName("compositionSections")
        self.section_list.setMovement(QListView.Snap)
        self.section_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.section_list.setDefaultDropAction(Qt.MoveAction)
        self.section_list.setDragDropOverwriteMode(False)
        self.section_list.setDragEnabled(True)
        self.section_list.setAcceptDrops(True)
        self.section_list.setDropIndicatorShown(True)
        self.section_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.section_list.setAutoScroll(True)
        self.section_list.setAccessibleName("Composition sections")
        self.section_list.setToolTip("Drag a section left or right to change the playing order. Arrow buttons also move the selected section.")
        self.section_delegate = SectionDelegate(self.section_list)
        self.section_list.setItemDelegate(self.section_delegate)
        self.section_list.setResizeMode(QListView.Adjust)
        self.section_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.section_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.section_list.setFixedHeight(88)
        self.section_list.setSpacing(6)
        self.section_list.currentRowChanged.connect(self._select_section)
        self.section_list.model().rowsMoved.connect(self._sections_reordered)
        root.addWidget(self.section_list)

        details = QHBoxLayout()
        details.setSpacing(12)

        def add_detail(caption, widget):
            group = QWidget()
            group.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
            cell = QVBoxLayout(group)
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setSpacing(3)
            label = QLabel(caption)
            label.setObjectName("muted")
            label.setBuddy(widget)
            widget.setAccessibleName(f"Section {caption.lower()}")
            cell.addWidget(label)
            cell.addWidget(widget)
            details.addWidget(group)
            return label

        self.section_name = QLineEdit()
        self.section_name.setPlaceholderText("Section name")
        self.section_name.setFixedWidth(230)
        self.section_name.editingFinished.connect(self._commit_name)
        self.name_label = add_detail("Name", self.section_name)
        self.section_type = QComboBox()
        self.section_type.addItems(SECTION_TYPES)
        self.section_type.setFixedWidth(120)
        self.section_type.currentTextChanged.connect(self._change_type)
        self.type_label = add_detail("Type", self.section_type)
        self.section_bars = QSpinBox()
        self.section_bars.setRange(1, 128)
        self.section_bars.setSuffix(" bars")
        self.section_bars.setFixedWidth(92)
        self.section_bars.valueChanged.connect(self._change_bars)
        self.duration_label = add_detail("Duration", self.section_bars)
        self.transition_bars = QDoubleSpinBox()
        self.transition_bars.setRange(0, 8)
        self.transition_bars.setSingleStep(.25)
        self.transition_bars.setDecimals(2)
        self.transition_bars.setSuffix(" bars")
        self.transition_bars.setFixedWidth(100)
        self.transition_bars.setToolTip("Smoothly blend from the previous section's final macro values during this many bars. "
                                       "Includes the loop seam. Zero means an immediate change; the first start uses its own first point.")
        self.transition_bars.valueChanged.connect(self._change_transition)
        add_detail("Blend in", self.transition_bars)
        self.apply_preset_button = QPushButton("Apply type preset")
        self.apply_preset_button.setToolTip("Replace the selected section's macro and block settings with starter values for its type.")
        self.apply_preset_button.clicked.connect(self.apply_type_preset)
        details.addWidget(self.apply_preset_button, 0, Qt.AlignBottom)
        details.addStretch(1)
        root.addLayout(details)

        self.macros_group = QGroupBox("SECTION MACROS · unchecked means follow Global")
        macros_layout = QGridLayout(self.macros_group)
        macros_layout.setContentsMargins(7, 6, 7, 6)
        macros_layout.setHorizontalSpacing(8)
        macros_layout.setVerticalSpacing(3)
        macro_tips = {
            "energy": "Section energy changes velocity while retaining the Global macro as the baseline.",
            "tension": "Higher tension loosens chord-tone anchoring for BASS/MELODY that follow Harmonic Plan.",
            "density": "Density is evaluated at event time, so later sections can restore notes from the source pattern.",
            "variation": "Section variation changes the accent/dynamic contour for this section.",
        }
        for column, key in enumerate(MACRO_KEYS):
            box = QGroupBox(MACRO_LABELS[key])
            box.setToolTip(macro_tips[key])
            layout = QVBoxLayout(box)
            layout.setContentsMargins(5, 4, 5, 4)
            layout.setSpacing(3)
            top = QHBoxLayout()
            enabled = QCheckBox("Override")
            top.addWidget(enabled)
            top.addStretch(1)
            value_label = QLabel("Global 50%")
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            top.addWidget(value_label)
            layout.addLayout(top)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setSingleStep(1)
            layout.addWidget(slider)
            enabled.toggled.connect(lambda checked, k=key: self._toggle_macro_override(k, checked))
            slider.valueChanged.connect(lambda value, k=key: self._set_macro_value(k, value))
            curve_row = QHBoxLayout()
            curve_toggle = QCheckBox("Curve")
            shape = QComboBox()
            for name in CURVE_SHAPES:
                shape.addItem(name.title(), name)
            shape.setToolTip("Smooth: eased segments without overshoot. Linear: constant slopes. Step: hold until the next point.")
            curve_row.addWidget(curve_toggle)
            curve_row.addStretch(1)
            curve_row.addWidget(shape)
            layout.addLayout(curve_row)
            curve_editor = MacroCurveEditor(MACRO_COLORS[key])
            curve_editor.setAccessibleName(f"{MACRO_LABELS[key]} automation curve")
            layout.addWidget(curve_editor)
            curve_toggle.toggled.connect(lambda checked, k=key: self._toggle_macro_curve(k, checked))
            shape.currentIndexChanged.connect(lambda _index, k=key: self._change_curve_shape(k))
            curve_editor.curveChanged.connect(lambda curve, k=key: self._set_macro_curve(k, curve))
            macros_layout.addWidget(box, 0, column)
            self._macro_widgets[key] = {"box": box, "enabled": enabled, "slider": slider, "value": value_label,
                                        "curve_toggle": curve_toggle, "shape": shape, "curve": curve_editor}
        root.addWidget(self.macros_group)

        block_header = QHBoxLayout()
        self.block_header = block_header
        block_title = QLabel("BLOCK SETTINGS")
        block_title.setObjectName("sectionTitle")
        block_header.addWidget(block_title)
        block_header.addStretch(1)
        block_hint = QLabel("Density = event keep · Velocity = multiplier · Register Center = offset · Variation = dynamic movement")
        block_hint.setObjectName("muted")
        block_hint.setWordWrap(True)
        block_header.addWidget(block_hint, 2)
        root.addLayout(block_header)

        self.block_table = QTableWidget(0, 6)
        self.block_table.setHorizontalHeaderLabels(["Block / Drum Voice", "Active", "Density", "Velocity", "Register Center", "Variation"])
        self.block_table.verticalHeader().setVisible(False)
        self.block_table.setAlternatingRowColors(True)
        self.block_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.block_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.block_table.setMinimumHeight(170)
        self.block_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.block_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 6):
            self.block_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        root.addWidget(self.block_table, 1)
        self.block_table.itemSelectionChanged.connect(self._load_expression)
        self.expression_group = QGroupBox("EXPRESSION · select a block / Drum Voice")
        expression_layout = QHBoxLayout(self.expression_group)
        expression_layout.setContentsMargins(7, 6, 7, 6)
        expression_layout.setSpacing(12)
        for key, (label, default, low, high, step, tip) in EXPRESSION_SPECS.items():
            column = QVBoxLayout()
            column.setSpacing(3)
            column.addWidget(QLabel(label))
            spin = self._double_spin(default, low, high, step,
                lambda value, k=key: self._set_expression(k, value), tip)
            spin.setAccessibleName(f"Section {label}")
            column.addWidget(spin)
            expression_layout.addLayout(column)
            self._expression_widgets[key] = spin
        expression_layout.addStretch(1)
        root.insertWidget(root.indexOf(self.block_table), self.expression_group)

        status_row = QHBoxLayout()
        self.status = QLabel("Planner disabled")
        self.status.setObjectName("muted")
        status_row.addWidget(self.status, 1)
        self.position_label = QLabel()
        self.position_label.setObjectName("muted")
        self.position_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_row.addWidget(self.position_label)
        self.status.setWordWrap(True)
        outer.addLayout(status_row)
        self.timeline = CompositionTimeline(self)
        self.timeline.seekRequested.connect(self._seek_composition)
        outer.addWidget(self.timeline)

        if hasattr(host, "theme_combo"):
            host.theme_combo.currentTextChanged.connect(self._theme_changed)
        self.sync_from_project()
        bind_attributes(self, "composition")
        bind_controls(self._expression_widgets, "section_instrument")
        for widgets in self._macro_widgets.values():
            bind_controls(widgets, "composition_curve")

    def _entities(self):
        result = []
        for block in self.host.project.blocks:
            voices = getattr(block, "drum_voices", None) or []
            if str(block.block_type).upper() == "DRUM" and voices:
                result.extend((voice, f"{block.name} / {voice.name}") for voice in voices)
            else:
                result.append((block, block.name))
        return result

    def _signature(self):
        return tuple((int(entity.id), label, str(entity.block_type)) for entity, label in self._entities())

    def _config(self):
        project = self.host.project
        if self._draft_project is not project or not isinstance(self._draft_config, dict):
            self._draft_project = project
            source = getattr(project, "composition", None)
            self._draft_config = normalize_composition(deepcopy(source) if isinstance(source, dict) else default_composition())
        if not self._draft_config.get("sections"):
            self._draft_config["sections"] = default_composition()["sections"]
        return self._draft_config

    def _selected_index(self):
        config = self._config()
        if not config["sections"]:
            config["sections"] = default_composition()["sections"]
        item = self.section_list.currentItem()
        section_id = item.data(Qt.UserRole) if item is not None else None
        row = next((i for i, section in enumerate(config["sections"]) if section["id"] == section_id),
                   self.section_list.currentRow())
        return max(0, min(len(config["sections"]) - 1, row))

    def _selected_section(self):
        config = self._config()
        index = self._selected_index()
        return config["sections"][index]

    def _mark_changed(self, regenerate=False, message=None):
        if self._syncing:
            return
        project = self.host.project
        snapshot = deepcopy(self._config())
        def apply_composition():
            if self.host.project is not project:
                return
            previous = deepcopy(getattr(project, "composition", {}) or {})
            project.composition = snapshot
            transport = self.host.transport
            if transport.running:
                context = self.host.engine.composition_runtime.context_at(self.host.engine.clock.position_beats)
                if context is not None:
                    section_id = context.get("section_id")
                    old_section = next((x for x in previous.get("sections", []) if x.get("id") == section_id), {})
                    new_section = next((x for x in snapshot.get("sections", []) if x.get("id") == section_id), {})
                    old_blocks, new_blocks = old_section.get("blocks", {}), new_section.get("blocks", {})
                    for block in project.blocks:
                        for entity in (getattr(block, "drum_voices", None) or [block]):
                            key = str(int(entity.id))
                            if old_blocks.get(key, {}).get("enabled", True) and not new_blocks.get(key, {}).get("enabled", True):
                                transport._release_block_notes(int(entity.id))
            if regenerate:
                self.host.engine.generate()
            self.host.engine.section_automation.advance(self.host.engine.clock.position_beats)
            transport._composition_section_key = None
            transport._composition_context = None
        self.host._mark_pending_dirty()
        self.host.transport.enqueue_gui_command(
            apply_composition, key=("composition-config", id(project)),
            notification={"dirty": True, "composition": True, "message": message},
            label="Composition Planner edit")

    def sync_from_project(self):
        self._syncing = True
        try:
            project = self.host.project
            self.runtime.project = project
            config = normalize_composition(deepcopy(getattr(project, "composition", None)))
            entities = self._entities()
            valid_ids = {str(int(entity.id)) for entity, _label in entities}
            for section in config["sections"]:
                section.setdefault("blocks", {})
                section["blocks"] = {key: value for key, value in section["blocks"].items() if key in valid_ids}
                section.setdefault("midi_automation", {})
                section["midi_automation"] = {key: value for key, value in section["midi_automation"].items()
                                               if key in valid_ids and isinstance(value, dict)}
                for entity, _label in entities:
                    section["blocks"].setdefault(str(int(entity.id)), deepcopy(NEUTRAL_BLOCK_SETTINGS))
            self._draft_project, self._draft_config = project, config
            selected_item = self.section_list.currentItem()
            previous_id = selected_item.data(Qt.UserRole) if selected_item is not None else None
            self._entity_signature = self._signature()
            self.enabled.blockSignals(True); self.enabled.setChecked(config["enabled"]); self.enabled.blockSignals(False)
            self.meter.blockSignals(True); self.meter.setCurrentText(config["meter"]); self.meter.blockSignals(False)
            ending = "loop" if config.get("loop") else config.get("end_action", "hold")
            self.ending.blockSignals(True); self.ending.setCurrentIndex(self.ending.findData(ending)); self.ending.blockSignals(False)
            self._render_section_list(previous_id)
            self._load_selected()
        finally:
            self._syncing = False
        if config != getattr(project, "composition", None):
            self._mark_changed()
        self.update_runtime()

    def refresh_if_needed(self):
        signature = self._signature()
        if signature != self._entity_signature:
            self.sync_from_project()
        else:
            self.update_runtime()

    def _render_section_list(self, selected_id=None):
        config = self._config()
        selected_id = selected_id or (config["sections"][0]["id"] if config["sections"] else None)
        self.section_list.blockSignals(True)
        self.section_list.clear()
        selected_row = 0
        for index, section in enumerate(config["sections"]):
            item = QListWidgetItem(f"{index + 1:02d}  {section['name']}\n{section['type']} · {section['bars']} bars")
            item.setData(Qt.UserRole, section["id"])
            item.setData(Qt.UserRole + 2, section_color(section))
            item.setSizeHint(QSize(180, 62))
            item.setToolTip(f"{section['name']} · {section['type']} · {section['bars']} bars\nDrag left or right to reorder")
            self.section_list.addItem(item)
            if section["id"] == selected_id:
                selected_row = index
        if self.section_list.count():
            self.section_list.setCurrentRow(selected_row)
        self.section_list.blockSignals(False)
        if hasattr(self, "instrument_grid"):
            self._resize_sections()

    def _sections_reordered(self, *_):
        """Commit Qt's internal move by stable section id, keeping settings intact."""
        if self._syncing:
            return
        order = [self.section_list.item(i).data(Qt.UserRole) for i in range(self.section_list.count())]
        with self.host.transport._state_lock:
            config = self._config()
            sections = {section["id"]: section for section in config["sections"]}
            if len(order) != len(sections) or set(order) != set(sections):
                return
            if order == [section["id"] for section in config["sections"]]:
                return
            config["sections"] = [sections[section_id] for section_id in order]
        self._mark_changed()
        # Rebuild only after Qt has finished the drop; never delete a view's
        # focused controls while it is still processing its native move event.
        self._reorder_timer.start(0)

    def _finish_reorder(self):
        self._load_selected()
        self.update_runtime()

    def _select_section(self, _row):
        if self._syncing:
            return
        self._load_selected()
        self.update_runtime()

    def _load_selected(self):
        config = self._config()
        if not config["sections"]:
            return
        section = config["sections"][self._selected_index()]
        self._syncing = True
        try:
            self.section_name.blockSignals(True); self.section_name.setText(section["name"]); self.section_name.blockSignals(False)
            self.section_type.blockSignals(True); self.section_type.setCurrentText(section["type"]); self.section_type.blockSignals(False)
            self.section_bars.blockSignals(True); self.section_bars.setValue(int(section["bars"])); self.section_bars.blockSignals(False)
            self.transition_bars.blockSignals(True); self.transition_bars.setValue(float(section.get("transition_bars", 0))); self.transition_bars.blockSignals(False)
            globals_now = getattr(self.host.engine.director, "global_macro_values", {})
            for key, widgets in self._macro_widgets.items():
                override = section.get("macros", {}).get(key)
                widgets["enabled"].blockSignals(True); widgets["enabled"].setChecked(override is not None); widgets["enabled"].blockSignals(False)
                value = float(override if override is not None else globals_now.get(key, .5))
                widgets["slider"].blockSignals(True); widgets["slider"].setValue(round(value * 100)); widgets["slider"].blockSignals(False)
                widgets["slider"].setEnabled(override is not None)
                widgets["value"].setText(f"{round(value * 100)}%" if override is not None else f"Global {round(value * 100)}%")
                curve = normalize_curve(section.get("macro_curves", {}).get(key) or
                                        {"enabled": False, "points": [[0, value], [1, value]]})
                widgets["curve_toggle"].blockSignals(True); widgets["curve_toggle"].setChecked(curve["enabled"]); widgets["curve_toggle"].blockSignals(False)
                widgets["curve_toggle"].setEnabled(override is not None)
                widgets["shape"].blockSignals(True); widgets["shape"].setCurrentIndex(widgets["shape"].findData(curve["shape"])); widgets["shape"].blockSignals(False)
                active = override is not None and curve["enabled"]
                widgets["slider"].setEnabled(override is not None and not active)
                widgets["shape"].setEnabled(active)
                widgets["curve"].set_curve(curve)
                widgets["curve"].setEnabled(active)
            if hasattr(self, "color_button"):
                self.color_button.setStyleSheet(f"border:2px solid {section_color(section)};border-radius:5px;")
                self.phrase_editor.sync(section)
                self.instrument_grid.refresh()
                for widgets in self._macro_widgets.values():
                    widgets["slider"].setVisible(not (widgets["enabled"].isChecked() and widgets["curve_toggle"].isChecked()))
            self._render_block_table(section)
            if hasattr(self, "automation_panel"):
                self.automation_panel.sync()
        finally:
            self._syncing = False
        self._update_section_buttons()

    def _render_block_table(self, section):
        entities = self._entities()
        previous = self.block_table.currentRow()
        self._table_entity_ids = [int(entity.id) for entity, _label in entities]
        self.block_table.blockSignals(True)
        self.block_table.setRowCount(len(entities))
        for row, (entity, label) in enumerate(entities):
            item = QTableWidgetItem(label)
            item.setData(Qt.UserRole, int(entity.id))
            item.setToolTip(f"{entity.block_type} · {getattr(entity, 'algorithm', '')} · {getattr(entity, 'mode', '')}")
            self.block_table.setItem(row, 0, item)
            values = section.setdefault("blocks", {}).setdefault(str(int(entity.id)), deepcopy(NEUTRAL_BLOCK_SETTINGS))
            active = QCheckBox()
            active.setChecked(bool(values.get("enabled", True)))
            active.setToolTip("Allow this block/voice to emit notes in this section.")
            active.toggled.connect(lambda checked, bid=int(entity.id), sid=section["id"]: self._set_block_setting(sid, bid, "enabled", bool(checked)))
            self.block_table.setCellWidget(row, 1, self._centered(active))
            self.block_table.setCellWidget(row, 2, self._double_spin(values.get("density", 1.0), 0.0, 1.0, .05,
                lambda value, bid=int(entity.id), sid=section["id"]: self._set_block_setting(sid, bid, "density", value), "Probability of keeping each source event"))
            self.block_table.setCellWidget(row, 3, self._double_spin(values.get("velocity", 1.0), 0.0, 1.5, .05,
                lambda value, bid=int(entity.id), sid=section["id"]: self._set_block_setting(sid, bid, "velocity", value), "Velocity multiplier; values above 1 increase dynamics"))
            center = QSpinBox()
            center.setRange(-24, 24); center.setSuffix(" st"); center.setValue(round(values.get("register_center", 0))); center.setFixedWidth(94)
            center.setAccessibleName("Section Register Center offset")
            center.setToolTip("Offset to the block's Register Center, before final scale and harmonic placement. "
                              "0 follows the block; +12 raises the target register by one octave. Pitch classes are preserved. "
                              "The combined Center is limited to -48…+36. Unavailable for Drum Voices.")
            center.setEnabled(entity.block_type not in ("DRUM", "PERCUSSION"))
            center.valueChanged.connect(lambda value, bid=int(entity.id), sid=section["id"]: self._set_block_setting(sid, bid, "register_center", value))
            self.block_table.setCellWidget(row, 4, center)
            self.block_table.setCellWidget(row, 5, self._double_spin(values.get("variation", 0.0), 0.0, 1.0, .05,
                lambda value, bid=int(entity.id), sid=section["id"]: self._set_block_setting(sid, bid, "variation", value), "Deterministic per-event velocity variation"))
            self.block_table.setRowHeight(row, 32)
        bind_table(self.block_table, ("", "enabled", "density", "velocity", "register_center", "variation"), "section_instrument")
        self.block_table.blockSignals(False)
        if entities:
            self.block_table.selectRow(max(0, min(previous, len(entities) - 1)))
        self._load_expression()

    def _load_expression(self):
        if not hasattr(self, "expression_group"):
            return
        row = self.block_table.currentRow()
        item = self.block_table.item(row, 0) if row >= 0 else None
        self._expression_entity = None
        self.expression_group.setEnabled(item is not None)
        if item is None:
            if hasattr(self, "section_midi_group"):
                self.section_midi_group.setEnabled(False)
                self.section_midi_override.blockSignals(True)
                self.section_midi_override.setChecked(False)
                self.section_midi_override.blockSignals(False)
                self.section_midi_editor.setEnabled(False)
            return
        block_id = int(item.data(Qt.UserRole))
        with self.host.transport._state_lock:
            section = self._selected_section()
            values = expression_settings(section.get("blocks", {}).get(str(block_id), {}))
            self._expression_entity = (section["id"], block_id)
            entity = next((entity for entity, _label in self._entities() if entity.id == block_id), None)
        self.expression_group.setTitle(f"EXPRESSION · {item.text()}")
        percussive = entity is None or entity.block_type in ("DRUM", "PERCUSSION")
        for key, spin in self._expression_widgets.items():
            spin.blockSignals(True); spin.setValue(values[key]); spin.blockSignals(False)
            spin.setEnabled(not percussive if key == "octave_spread" else
                            entity is not None and entity.block_type in ("BASS", "MELODY") if key == "harmony" else True)
        if hasattr(self, "section_midi_group"):
            with self.host.transport._state_lock:
                section = self._selected_section()
                overrides = section.setdefault("midi_automation", {})
                override = overrides.get(str(block_id))
                parent = next((block for block in self.host.project.blocks
                               if any(int(voice.id) == block_id for voice in (getattr(block, "drum_voices", None) or []))), None)
                inherited = entity_expression_config(entity, parent=parent) if entity is not None else normalize_expression({})
            self.section_midi_override.blockSignals(True)
            self.section_midi_override.setChecked(isinstance(override, dict))
            self.section_midi_override.blockSignals(False)
            effective = merge_expression_configs(inherited, override) if isinstance(override, dict) else inherited
            self.section_midi_editor.set_config(effective)
            self.section_midi_editor.setEnabled(isinstance(override, dict))
            self.section_midi_group.setEnabled(item is not None)
            self.section_midi_group.setTitle(f"MIDI AUTOMATION · {item.text()}")

    def _toggle_section_midi_override(self, enabled):
        if self._syncing:
            return
        row = self.block_table.currentRow()
        item = self.block_table.item(row, 0) if row >= 0 else None
        if item is None:
            return
        block_id = int(item.data(Qt.UserRole))
        with self.host.transport._state_lock:
            section = self._selected_section()
            overrides = section.setdefault("midi_automation", {})
            if enabled:
                config = self.section_midi_editor.config()
                for lane in config.get("cc_lanes", []):
                    lane["timebase"] = "section"
                config.get("pitch_bend", {})["timebase"] = "section"
                config.get("aftertouch", {})["timebase"] = "section"
                overrides[str(block_id)] = normalize_expression(config)
                self.section_midi_editor.set_config(overrides[str(block_id)])
            else:
                overrides.pop(str(block_id), None)
        self.section_midi_editor.setEnabled(bool(enabled))
        self._mark_changed(message="Section MIDI automation override enabled" if enabled else "Following block MIDI expression")

    def _set_section_midi_automation(self, config):
        if self._syncing or not hasattr(self, "section_midi_override") or not self.section_midi_override.isChecked():
            return
        row = self.block_table.currentRow()
        item = self.block_table.item(row, 0) if row >= 0 else None
        if item is None:
            return
        block_id = int(item.data(Qt.UserRole))
        normalized = normalize_expression(config)
        with self.host.transport._state_lock:
            section = self._selected_section()
            section.setdefault("midi_automation", {})[str(block_id)] = normalized
        self._mark_changed()

    def _set_expression(self, key, value):
        if self._syncing or self._expression_entity is None:
            return
        self._set_block_setting(*self._expression_entity, key, value)

    @staticmethod
    def _centered(widget):
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(widget)
        return wrapper

    @staticmethod
    def _double_spin(value, low, high, step, callback, tooltip):
        spin = QDoubleSpinBox()
        spin.setRange(low, high); spin.setSingleStep(step); spin.setDecimals(2)
        spin.setValue(float(value)); spin.setFixedWidth(82); spin.setToolTip(tooltip)
        spin.valueChanged.connect(callback)
        return spin

    def _commit_name(self):
        if self._syncing:
            return
        name = self.section_name.text().strip()
        with self.host.transport._state_lock:
            section = self._selected_section()
            name = name or section["type"]
            if section["name"] == name:
                return
            section["name"] = name[:80]
            section_id = section["id"]
        self._mark_changed()
        self._render_section_list(section_id)
    def _change_type(self, value):
        if self._syncing or value not in SECTION_TYPES:
            return
        with self.host.transport._state_lock:
            section = self._selected_section()
            old_type = section["type"]
            if old_type == value:
                return
            if section["name"] == old_type:
                section["name"] = value
            if section_color(section) == SECTION_COLORS[old_type]:
                section["color"] = SECTION_COLORS[value]
            section["type"] = value
            section_id = section["id"]
        self._mark_changed()
        self._load_selected()
        self._render_section_list(section_id)
    def _change_bars(self, value):
        if self._syncing:
            return
        with self.host.transport._state_lock:
            section = self._selected_section()
            if int(section["bars"]) == int(value):
                return
            section["bars"] = int(value)
            section_id = section["id"]
        self._mark_changed()
        self._render_section_list(section_id)
        if hasattr(self, "phrase_editor"):
            self.phrase_editor.sync(self._selected_section())
            self.instrument_grid.refresh()
    def _toggle_macro_override(self, key, enabled):
        if self._syncing:
            return
        with self.host.transport._state_lock:
            section = self._selected_section()
            macros = section.setdefault("macros", {})
            if enabled:
                current = self.host.engine.director.global_macro_values.get(key, .5)
                macros[key] = float(self._macro_widgets[key]["slider"].value() / 100.0) if macros.get(key) is not None else float(current)
            else:
                macros[key] = None
        self._mark_changed()
        self._load_selected()

    def _change_transition(self, value):
        if self._syncing:
            return
        with self.host.transport._state_lock:
            self._selected_section()["transition_bars"] = float(value)
        self._mark_changed()

    def _toggle_macro_curve(self, key, enabled):
        if self._syncing:
            return
        with self.host.transport._state_lock:
            section = self._selected_section()
            value = section.get("macros", {}).get(key)
            if value is None:
                return
            curves = section.setdefault("macro_curves", {})
            curve = normalize_curve(curves.get(key) or {"points": [[0, value], [1, value]]})
            curve["enabled"] = bool(enabled)
            curves[key] = curve
            if enabled and section.get("transition_bars", 0) == 0:
                section["transition_bars"] = .25
        self._mark_changed()
        self._load_selected()

    def _change_curve_shape(self, key):
        if self._syncing:
            return
        curve = deepcopy(self._macro_widgets[key]["curve"].curve)
        curve["shape"] = self._macro_widgets[key]["shape"].currentData()
        self._set_macro_curve(key, curve)
        self._macro_widgets[key]["curve"].set_curve(curve)

    def _set_macro_curve(self, key, curve):
        if self._syncing:
            return
        with self.host.transport._state_lock:
            section = self._selected_section()
            if section.get("macros", {}).get(key) is None:
                return
            section.setdefault("macro_curves", {})[key] = normalize_curve(curve)
        self._mark_changed()
    def _set_macro_value(self, key, raw):
        if self._syncing:
            return
        value = max(0.0, min(1.0, int(raw) / 100.0))
        with self.host.transport._state_lock:
            section = self._selected_section()
            if section.setdefault("macros", {}).get(key) is None:
                return
            section["macros"][key] = value
        self._macro_widgets[key]["value"].setText(f"{round(value * 100)}%")
        self._mark_changed()
    def _set_block_setting(self, section_id, block_id, key, value):
        if self._syncing:
            return
        with self.host.transport._state_lock:
            config = self._config()
            section = next((item for item in config["sections"] if item["id"] == section_id), None)
            if section is None:
                return
            settings = section.setdefault("blocks", {}).setdefault(str(int(block_id)), deepcopy(NEUTRAL_BLOCK_SETTINGS))
            if settings.get(key) == value:
                return
            settings[key] = value
        self._mark_changed()
        if hasattr(self, "instrument_grid"):
            self.instrument_grid.refresh()
    def _set_enabled(self, value):
        if self._syncing:
            return
        config = self._config()
        if bool(config["enabled"]) == bool(value):
            return
        config["enabled"] = bool(value)
        self._mark_changed(regenerate=True, message="Composition Planner enabled" if value else "Composition Planner disabled")

    def _set_meter(self, value):
        if self._syncing or value not in METERS:
            return
        with self.host.transport._state_lock:
            config = self._config()
            if config["meter"] == value:
                return
            config["meter"] = value
            selected_id = self._selected_section()["id"]
        self._mark_changed()
        self._render_section_list(selected_id)
        if hasattr(self, "phrase_editor"):
            self.phrase_editor.sync(self._selected_section())
            self.instrument_grid.refresh()
    def _set_ending(self, _index):
        if self._syncing:
            return
        value = self.ending.currentData()
        with self.host.transport._state_lock:
            config = self._config()
            current = "loop" if config.get("loop") else config.get("end_action", "hold")
            if current == value:
                return
            config["loop"] = value == "loop"
            config["end_action"] = "stop" if value == "stop" else "hold"
        self._mark_changed()

    def _toggle_parameter_list(self, visible):
        self.parameter_list.setVisible(visible)
        self.parameter_list_toggle.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)

    def _sync_playback(self):
        callback = getattr(self.host, "_sync_transport_buttons", None)
        if callback is not None:
            callback()
        callback = getattr(self.host, "_update_parameter_sources", None)
        if callback is not None:
            callback(force=True)
        self.update_runtime()

    def sync_playback_buttons(self):
        running = (self.host.transport.running
                   and self.host.transport.playback_mode == "composition")
        self.play_button.blockSignals(True)
        self.play_button.setChecked(running)
        self.play_button.blockSignals(False)
        self.stop_button.setEnabled(running)

    def _toggle_composition(self, checked):
        if checked:
            self._play_composition()
        else:
            self._stop_composition()

    def _play_composition(self):
        config = self._config()
        preview_project = deepcopy(self.host.project)
        preview_project.composition = deepcopy(config)
        preview_runtime = CompositionRuntime(preview_project)
        origin = self.play_from.currentData()
        if origin == "selected":
            position = preview_runtime.section_start(self._selected_section()["id"])
        elif origin == "cursor":
            position = float(self.host.transport.composition_position)
            total = preview_runtime.total_beats()
            if config.get("loop") and total > 0:
                position %= total
            position = max(0., min(max(0., total - .25), position))
        else:
            position = 0.
        if not config["enabled"]:
            config["enabled"] = True
            self.enabled.blockSignals(True); self.enabled.setChecked(True); self.enabled.blockSignals(False)
            self._mark_changed(regenerate=True)
        # Transport.start drains pending GUI commands before starting playback.
        self.host.transport.start(position_beats=position, mode="composition")
        self._sync_playback()

    def _stop_composition(self):
        if self.host.transport.playback_mode == "composition":
            self.host.transport.stop()
        self._sync_playback()

    def _seek_composition(self, position_bars):
        self.host.transport.flush_gui_commands(notify=True)
        runtime = CompositionRuntime(self.host.project)
        position = round(float(position_bars) * runtime.bar_beats() * 4) / 4
        position = max(0., min(runtime.total_beats() - .25, position))
        self.host.transport.composition_position = position
        if not self.host.transport.running or self.host.transport.playback_mode == "composition":
            self.host.transport.seek(position)
        self.play_from.setCurrentIndex(self.play_from.findData("cursor"))
        self._sync_playback()

    def add_section(self):
        with self.host.transport._state_lock:
            config = self._config()
            if len(config["sections"]) >= 128:
                self.host.set_message("Composition is limited to 128 sections")
                return
            section_type = self.section_type_add.currentText()
            entities = [entity for entity, _label in self._entities()]
            section = make_section(section_type, entities, bars=4)
            names = {item["name"] for item in config["sections"]}
            base = section_type
            number = 2
            while section["name"] in names:
                section["name"] = f"{base} {number}"
                number += 1
            insert_at = self.section_list.currentRow() + 1
            section["color"] = available_section_color(config["sections"], section_color(section))
            config["sections"].insert(max(0, insert_at), section)
            section_id = section["id"]
            section_name = section["name"]
        self._mark_changed(message=f"Added {section_name}")
        self._render_section_list(section_id)
        self._load_selected()
    def duplicate_section(self):
        with self.host.transport._state_lock:
            config = self._config()
            if len(config["sections"]) >= 128:
                self.host.set_message("Composition is limited to 128 sections")
                return
            source = deepcopy(self._selected_section())
            source["id"] = "sec-" + uuid.uuid4().hex[:10]
            source["color"] = available_section_color(config["sections"], section_color(source))
            base = source["name"]
            names = {item["name"] for item in config["sections"]}
            suffix = 2
            source["name"] = f"{base} {suffix}"
            while source["name"] in names:
                suffix += 1; source["name"] = f"{base} {suffix}"
            config["sections"].insert(self._selected_index() + 1, source)
            section_id = source["id"]
        self._mark_changed(message=f"Duplicated {base}")
        self._render_section_list(section_id)
        self._load_selected()
    def remove_section(self):
        with self.host.transport._state_lock:
            config = self._config()
            if len(config["sections"]) <= 1:
                self.host.set_message("Composition must contain at least one section")
                return
            index = self._selected_index()
            removed = config["sections"].pop(index)
            selected_id = config["sections"][min(index, len(config["sections"]) - 1)]["id"]
            removed_name = removed["name"]
        self._mark_changed(message=f"Removed {removed_name}")
        self._render_section_list(selected_id)
        self._load_selected()
    def move_section(self, direction):
        with self.host.transport._state_lock:
            config = self._config()
            index = self._selected_index()
            target = index + int(direction)
            if not 0 <= target < len(config["sections"]):
                return
            config["sections"][index], config["sections"][target] = config["sections"][target], config["sections"][index]
            selected_id = config["sections"][target]["id"]
        self._mark_changed()
        self._render_section_list(selected_id)
        self._load_selected()
    def apply_type_preset(self):
        with self.host.transport._state_lock:
            section = self._selected_section()
            section_type = section["type"]
            section["macros"] = dict(TYPE_MACRO_PRESETS[section_type])
            section["macro_curves"] = {}
            section["blocks"] = {str(int(entity.id)): default_block_settings(section_type, entity)
                                 for entity, _label in self._entities()}
        self._mark_changed(message=f"Applied {section_type} preset")
        self._load_selected()
    def update_runtime(self):
        with self.host.transport._state_lock:
            config = self._config()
            transport = self.host.transport
            playing_form = transport.running and transport.playback_mode == "composition"
            if playing_form:
                transport.composition_position = float(self.host.engine.clock.position_beats)
            beat = float(transport.composition_position)
            context = self.runtime.context(beat)
            total_bars = int(context["total_bars"])
            active_index = int(context["index"])
            active_section = context["section"]
            effective_macros = self.runtime.effective_macros(active_section, self.host.engine.director.global_macro_values, context)
            running = bool(playing_form)
            meter = config["meter"]
            enabled = bool(config["enabled"]) and not (transport.running and not playing_form)
            total_beats = total_bars * METER_BEATS[meter]
            sections = tuple({"id": s["id"], "name": s["name"], "type": s["type"], "bars": int(s["bars"]), "color": section_color(s)}
                             for s in config["sections"])
            tempo = max(1.0, float(self.host.project.tempo))
            local_beat = (float(context["start_beat"]) - int(context["cycle"]) * total_beats
                          + float(context["local_beat"]))
            local_beat = max(0.0, min(total_beats, local_beat))
            local_bar = min(total_bars, int(local_beat // METER_BEATS[meter]) + 1)
        self._theme_changed()
        sections_by_id = {s["id"]: (index, s) for index, s in enumerate(sections)}
        for index in range(self.section_list.count()):
            item = self.section_list.item(index)
            position = sections_by_id.get(item.data(Qt.UserRole))
            if position is None:
                continue
            section_index, section = position
            marker = "▶ " if section_index == active_index and running and enabled else ""
            text = f"{marker}{section_index + 1:02d}  {section['name']}\n{section['type']} · {section['bars']} bars"
            if item.text() != text:
                item.setText(text)
            is_active = bool(section_index == active_index and enabled)
            previous_active = item.data(Qt.UserRole + 1)
            if previous_active != is_active:
                item.setData(Qt.UserRole + 1, is_active)
        active_macro_text = " · ".join(f"{MACRO_LABELS[key]} {round(value * 100)}%" for key, value in effective_macros.items())
        state = "PLAYING" if running and enabled else "READY · preview only" if enabled else "OFF · preview only"
        if transport.running and not playing_form:
            state = f"BYPASS · {transport.playback_mode.title()} playback"
        if enabled and beat >= total_beats:
            if self.runtime.ending() == "stop" and not running:
                state = "FINISHED"
            elif self.runtime.ending() == "hold":
                state = "HOLD LAST"
        self.status.setText(f"{state} · {active_section['name']} · section bar {context['section_bar']}/{active_section['bars']} · {active_macro_text}")
        total_time = time_label(total_beats * 60 / tempo)
        elapsed_time = time_label(local_beat * 60 / tempo)
        self._total_text = f"TOTAL · {total_bars} bars · {total_beats:g} beats · {total_time} at {tempo:g} BPM · one pass"
        self._short_total_text = f"TOTAL · {total_bars} bars · {total_time}"
        self.total_label.setToolTip(self._total_text)
        self._update_total_caption()
        cycle_text = f" · loop {int(context['cycle']) + 1}" if context["loop"] else ""
        self.position_label.setText(f"{elapsed_time} / {total_time} · bar {local_bar}/{total_bars}{cycle_text}")
        item = self.section_list.currentItem()
        selected_id = item.data(Qt.UserRole) if item is not None else None
        for key, widgets in self._macro_widgets.items():
            selected_active = selected_id == context["section_id"] and enabled
            widgets["curve"].set_position(context["section_progress"] if selected_active else None,
                                           effective_macros[key] if selected_active else None)
            if widgets["curve_toggle"].isChecked() and widgets["enabled"].isChecked():
                preview = section_macro(self._selected_section(), key,
                    self.host.engine.director.global_macro_values, 0.)
                widgets["value"].setText(f'{round((effective_macros[key] if selected_active else preview) * 100)}%'
                                          + (" · live" if selected_active and running else " · curve"))
        self.timeline.set_runtime(sections, local_beat / METER_BEATS[meter], active_index,
                                  selected_id, running and enabled)
        self.sync_playback_buttons()
        self._update_section_buttons()
        if hasattr(self, "instrument_grid"):
            self.phrase_editor.update_runtime()
            self.instrument_grid.update_runtime()
        if hasattr(self, "automation_panel"):
            self.automation_panel.update_runtime()

    def _theme_changed(self, *_):
        theme = theme_palette(self.host.theme_combo.currentText() if hasattr(self.host, "theme_combo") else "Midnight")
        if theme == getattr(self, "_theme", None):
            return
        self._theme = theme
        self.section_delegate.theme = theme
        self.timeline.theme = theme
        ink = "#111111" if is_light_theme(theme) else "#ffffff"
        self.play_button.setIcon(transport_icon("play", ink, 20))
        self.stop_button.setIcon(transport_icon("stop", ink, 20))
        for widgets in self._macro_widgets.values():
            widgets["curve"].theme = theme
            widgets["curve"].update()
        self.section_list.setStyleSheet(
            f"QListWidget#compositionSections {{ background:{theme.panel}; border:1px solid {theme.border}; border-radius:6px; }}"
            f"QListWidget#compositionSections::drop-indicator {{ background:{theme.accent}; width:3px; }}")
        self.section_list.viewport().update()
        self.timeline.update()
        if hasattr(self, "section_midi_editor"):
            self.section_midi_editor.apply_theme(theme)
        if hasattr(self, "instrument_grid"):
            for card in self.instrument_grid.cards.values():
                card.apply_theme()
    def _update_section_buttons(self):
        count = len(self._config()["sections"])
        row = self.section_list.currentRow()
        self.duplicate_button.setEnabled(0 < count < 128)
        self.add_button.setEnabled(count < 128)
        self.remove_button.setEnabled(count > 1)
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < count - 1)
        has_section = count > 0
        for widget in (self.section_name, self.section_type, self.section_bars, self.apply_preset_button):
            widget.setEnabled(has_section)
        for key, widgets in self._macro_widgets.items():
            widgets["enabled"].setEnabled(has_section)
            override = has_section and widgets["enabled"].isChecked()
            curve_active = override and widgets["curve_toggle"].isChecked()
            widgets["slider"].setEnabled(override and not curve_active)
            widgets["curve_toggle"].setEnabled(override)
            widgets["shape"].setEnabled(curve_active)
            widgets["curve"].setEnabled(curve_active)

    def attach_performance(self, performance, curve_factory, strip_factory, block_color):
        """Compose the form, section editor, instruments and global controls."""
        self.performance = performance
        self.curve_factory = curve_factory
        self.block_color = block_color
        root = self.editor_layout
        root.setSizeConstraint(QLayout.SetDefaultConstraint)
        root.setSpacing(4)
        self.editor.setMinimumSize(0, 0)
        self.description.hide()
        self.section_list.setFixedHeight(76)
        self.section_list.setSpacing(3)
        self.timeline.setFixedHeight(46)
        self.layout().removeWidget(self.timeline)
        root.insertWidget(root.indexOf(self.section_list)+1, self.timeline)
        self.section_name.setFixedWidth(180)
        self.transition_bars.setFixedWidth(88)
        self.color_button = QPushButton("Color…")
        self.color_button.setFixedWidth(58)
        self.color_button.clicked.connect(self._choose_color)
        # The fields are each a small QWidget in a horizontal row.
        self.details_row = next(root.itemAt(i).layout() for i in range(root.count())
                                if root.itemAt(i).layout() and root.itemAt(i).layout().indexOf(self.apply_preset_button) >= 0)
        self.details_row.insertWidget(self.details_row.indexOf(self.apply_preset_button), self.color_button, 0, Qt.AlignBottom)
        self.total_label.setWordWrap(False)
        self.total_label.setMinimumWidth(0)
        self.total_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        root.removeWidget(self.total_label)
        for index in range(self.title_row.count()):
            self.title_row.setStretch(index, 0)
        self.title_row.insertWidget(1, self.total_label, 1)
        self.total_label.setStyleSheet("font-size:11px;")
        self.total_label.setContentsMargins(10, 0, 0, 0)
        for widgets in self._macro_widgets.values():
            widgets["box"].layout().setContentsMargins(5, 3, 5, 3)
            widgets["box"].layout().setSpacing(2)
            widgets["curve"].setFixedHeight(70)
            widgets["slider"].setFixedHeight(14)
            widgets["shape"].setMaximumWidth(78)
            widgets["curve_toggle"].setText("Curve")
        root.removeItem(self.block_header)
        self.advanced = QWidget()
        advanced_layout = QVBoxLayout(self.advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.addLayout(self.block_header)
        for widget in (self.expression_group, self.block_table):
            root.removeWidget(widget)
            advanced_layout.addWidget(widget)
        self.section_midi_group = QGroupBox("MIDI AUTOMATION · selected section / block")
        section_midi_layout = QVBoxLayout(self.section_midi_group)
        section_midi_layout.setContentsMargins(7, 6, 7, 6)
        self.section_midi_override = QCheckBox("Override Block Inspector MIDI expression for this section")
        self.section_midi_override.setToolTip("Unchecked: inherit the block/voice MIDI expression. Checked: use this section-specific CC, Pitch Bend and Aftertouch automation.")
        self.section_midi_override.toggled.connect(self._toggle_section_midi_override)
        section_midi_layout.addWidget(self.section_midi_override)
        self.section_midi_editor = MidiExpressionEditor({}, self.section_midi_group)
        self.section_midi_editor.changed.connect(self._set_section_midi_automation)
        section_midi_layout.addWidget(self.section_midi_editor)
        advanced_layout.addWidget(self.section_midi_group)
        self.block_table.setMaximumHeight(260)
        self.block_table.setMinimumHeight(150)
        self.details_toggle = QToolButton()
        self.details_toggle.setText("Block / Drum Voice settings")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setArrowType(Qt.RightArrow)
        self.details_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.details_toggle.toggled.connect(self._toggle_details)

        # Keep the form overview visible and move the dense editing surfaces
        # into focused pages.  The controls themselves are reparented, not
        # recreated, so all existing signal wiring and project semantics stay
        # intact.
        self.composition_tabs = QTabWidget(self.editor)
        self.composition_tabs.setObjectName("compositionWorkspaceTabs")
        self.composition_tabs.setDocumentMode(True)
        self.composition_tabs.setMovable(False)
        self.composition_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.composition_tabs.setMinimumHeight(300)

        self.section_page = QWidget()
        section_layout = QVBoxLayout(self.section_page)
        section_layout.setContentsMargins(8, 8, 8, 8)
        section_layout.setSpacing(8)
        section_hint = QLabel("Edit the selected section: identity, automation curves and phrase assignment.")
        section_hint.setObjectName("muted")
        section_hint.setWordWrap(True)
        section_layout.addWidget(section_hint)
        root.removeItem(self.details_row)
        section_layout.addLayout(self.details_row)
        root.removeWidget(self.macros_group)
        section_layout.addWidget(self.macros_group)

        self.phrase_editor = SectionPhraseEditor(self, strip_factory)
        section_layout.addWidget(self.phrase_editor)
        section_layout.addStretch(1)

        self.instrument_page = QWidget()
        instrument_layout = QVBoxLayout(self.instrument_page)
        instrument_layout.setContentsMargins(8, 8, 8, 8)
        instrument_layout.setSpacing(7)
        instrument_hint = QLabel("Per-section instrument techniques, coefficients and optional block-level overrides.")
        instrument_hint.setObjectName("muted")
        instrument_hint.setWordWrap(True)
        instrument_layout.addWidget(instrument_hint)
        heading = QHBoxLayout()
        label = QLabel("INSTRUMENT PERFORMANCE")
        label.setObjectName("sectionTitle")
        heading.addWidget(label)
        heading.addStretch()
        instrument_layout.addLayout(heading)
        self.instrument_grid = SectionInstrumentGrid(self)
        instrument_layout.addWidget(self.instrument_grid)
        instrument_layout.addWidget(self.details_toggle)
        instrument_layout.addWidget(self.advanced)
        instrument_layout.addStretch(1)

        self.global_page = QWidget()
        global_layout = QVBoxLayout(self.global_page)
        global_layout.setContentsMargins(8, 8, 8, 8)
        global_layout.setSpacing(8)
        global_heading = QHBoxLayout()
        global_title = QLabel("GLOBAL MUSICAL CONTROLS")
        global_title.setObjectName("sectionTitle")
        global_heading.addWidget(global_title)
        global_heading.addStretch(1)
        audition = QPushButton("Manual performance audition…")
        audition.setToolTip("Open standalone phrase/technique controls; playback starts only when explicitly requested")
        audition.clicked.connect(self._open_manual_audition)
        global_heading.addWidget(audition)
        global_layout.addLayout(global_heading)
        global_hint = QLabel("These settings apply across the composition. Section macros and instrument assignments are edited in their own pages.")
        global_hint.setObjectName("muted")
        global_hint.setWordWrap(True)
        global_layout.addWidget(global_hint)

        self.global_grid = QGridLayout()
        self.global_grid.setContentsMargins(0, 0, 0, 0)
        self.global_grid.setHorizontalSpacing(8)
        self.global_grid.setVerticalSpacing(8)
        self.global_sections = [performance.director_section, performance.harmonic_section]
        for section in self.global_sections:
            performance.layout().removeWidget(section)
            section.header.setChecked(False)
            section._toggle(False)
            section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.global_grid.addWidget(self.global_sections[0], 0, 0)
        self.global_grid.addWidget(self.global_sections[1], 0, 1)
        global_layout.addLayout(self.global_grid)
        global_layout.addStretch(1)

        self.composition_tabs.addTab(self.section_page, "SECTION")
        self.composition_tabs.setTabToolTip(0, "Selected section properties, macro curves and phrase assignment")
        self.composition_tabs.addTab(self.instrument_page, "INSTRUMENTS")
        self.composition_tabs.setTabToolTip(1, "Per-instrument performance and detailed block settings")
        self.composition_tabs.addTab(self.global_page, "GLOBAL")
        self.composition_tabs.setTabToolTip(2, "Project-wide Musical Director and Harmonic Plan")
        self.automation_panel = SectionAutomationPanel(self)
        self.composition_tabs.addTab(self.automation_panel, "AUTOMATION")
        self.composition_tabs.setTabToolTip(3, "Exact parameter values and curves for this section, with timing and source policy")
        root.addWidget(self.composition_tabs, 1)
        self.advanced.hide()
        self.editor_scroll.viewport().installEventFilter(self)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._resize_sections)
        self.editor_scroll.verticalScrollBar().rangeChanged.connect(lambda *_: self._resize_timer.start(0))
        self._load_selected()
        self._resize_sections()
        bind_attributes(self, "composition")

    def _toggle_details(self, visible):
        self.advanced.setVisible(visible)
        self.details_toggle.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)

    def _choose_color(self):
        section = self._selected_section()
        color = QColorDialog.getColor(QColor(section_color(section)), self, "Section color")
        if color.isValid():
            with self.host.transport._state_lock:
                section["color"] = color.name().lower()
            self._mark_changed()
            self._render_section_list(section["id"])
            self._load_selected()

    def eventFilter(self, obj, event):
        if obj is self.editor_scroll.viewport() and event.type() == QEvent.Resize and hasattr(self, "_resize_timer"):
            self._resize_timer.start(0)
        return super().eventFilter(obj, event)

    def _resize_sections(self):
        if not hasattr(self, "instrument_grid"):
            return
        width = max(1, self.editor_scroll.viewport().width())
        sections = self._config()["sections"]
        available = max(1, width - 12 - 6 * len(sections))
        total = sum(s["bars"] for s in sections)
        for index in range(self.section_list.count()):
            item = self.section_list.item(index)
            section = next((s for s in sections if s["id"] == item.data(Qt.UserRole)), None)
            if section:
                item.setSizeHint(QSize(max(98, round(available*section["bars"]/max(1, total))), 56))
        for index in range(self.details_row.count()):
            widget = self.details_row.itemAt(index).widget()
            if widget and isinstance(widget.layout(), QVBoxLayout):
                widget.layout().setDirection(QHBoxLayout.LeftToRight if width >= 1050 else QVBoxLayout.TopToBottom)
                widget.layout().setSpacing(5 if width >= 1050 else 2)
        grid = self.macros_group.layout()
        columns = 4 if width >= 1000 else 2
        for index, widgets in enumerate(self._macro_widgets.values()):
            grid.removeWidget(widgets["box"])
            grid.addWidget(widgets["box"], index//columns, index%columns)
        for index in range(4):
            grid.setColumnStretch(index, 1 if index < columns else 0)
            grid.setColumnMinimumWidth(index, 0)
        self.instrument_grid.reflow()
        global_columns = 2 if width >= 1050 else 1
        for index, section in enumerate(self.global_sections):
            self.global_grid.removeWidget(section)
            self.global_grid.addWidget(section, index // global_columns, index % global_columns, Qt.AlignTop)
        for index in range(2):
            self.global_grid.setColumnStretch(index, 1 if index < global_columns else 0)
            self.global_grid.setColumnMinimumWidth(index, 0)
        self._update_total_caption()
        self.editor_layout.invalidate()
        self.editor_layout.activate()
        self.editor.updateGeometry()
        if self.editor.width() > width and self.editor.minimumSizeHint().width() <= width:
            self.editor.resize(width, self.editor.height())

    def set_section_performance(self, settings):
        with self.host.transport._state_lock:
            section = self._selected_section()
            section["performance"] = normalize_performance(settings)
        self._mark_changed()
        self.phrase_editor.sync(section)
        self.instrument_grid.refresh()

    def set_card_value(self, block, key, value):
        with self.host.transport._state_lock:
            section = self._selected_section()
            entities = getattr(block, "drum_voices", None) or [block]
            changed = False
            for entity in entities:
                settings = section.setdefault("blocks", {}).setdefault(str(entity.id), deepcopy(NEUTRAL_BLOCK_SETTINGS))
                if settings.get(key) == value:
                    continue
                settings[key] = value
                changed = True
        if changed:
            self._mark_changed()
            self.instrument_grid.refresh()
            if self.advanced.isVisible():
                self._render_block_table(section)

    def show_block_details(self, block):
        if hasattr(self, "composition_tabs"):
            self.composition_tabs.setCurrentWidget(self.instrument_page)
        self.details_toggle.setChecked(True)
        entities = getattr(block, "drum_voices", None) or [block]
        ids = {entity.id for entity in entities}
        for row, bid in enumerate(self._table_entity_ids):
            if bid in ids:
                self.block_table.selectRow(row)
                self.block_table.scrollToItem(self.block_table.item(row, 0))
                break
        self.editor_scroll.ensureWidgetVisible(self.expression_group)

    def _open_manual_audition(self):
        dialog = getattr(self, "_manual_dialog", None)
        if dialog is None:
            dialog = QDialog(self.host)
            dialog.setWindowTitle("Manual performance audition")
            dialog.resize(1080, 760)
            layout = QVBoxLayout(dialog)
            info = QLabel("Standalone audition. Play Phrase / Restart switches from Composition to manual performance.")
            info.setObjectName("muted")
            info.setWordWrap(True)
            layout.addWidget(info)
            layout.addWidget(self.performance)
            self.performance.show()
            self._manual_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _update_total_caption(self):
        compact = hasattr(self, "instrument_grid") and self.editor_scroll.viewport().width() < 1200
        self.page_title.setText("COMPOSITION" if compact else "COMPOSITION PLANNER")
        self.total_label.setText(getattr(self, "_short_total_text" if compact else "_total_text", ""))
