"""Auricle Qt user interface."""
from __future__ import annotations

import math
import random
import sys
import time
import threading
from functools import lru_cache
from pathlib import Path
import mido
from shiboken6 import isValid

from PySide6.QtCore import Qt, Signal, QTimer, QSize, QRectF, QPoint, QPointF, QEvent, QSettings
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPixmap, QIcon, QPalette, QKeySequence, QShortcut, QPainterPath, QTextDocument
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QSlider, QComboBox,
    QListWidget, QListWidgetItem, QGroupBox, QLineEdit, QDialog,
    QDialogButtonBox, QMessageBox, QFileDialog, QSplitter, QScrollArea, QMenu,
    QFrame, QButtonGroup, QSizePolicy, QAbstractItemView, QCheckBox, QInputDialog, QLayout,
    QTabWidget, QTabBar, QStyle, QStyleOptionTab, QTextBrowser, QProgressBar, QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem, QColorDialog,
)

from auricle_core import (
    APP_VERSION, BLOCK_TYPES, GENERATORS, NON_NUMERIC_PARAMETERS, NOTE_NAMES, PARTS, ROLE_PROFILES, apply_role_defaults,
    PROCESS_TARGETS, PROCESS_TYPES, RELATIONS, SCALES, Block, MusicEngine, Mutator, Process,
    Project, Relation, Transport, DrumVoice, ensure_drum_voices, get_midi_input_names, get_midi_output_names, load_project, midi_note_for, save_project,
    next_relation_id, duplicate_relation, validate_relations,
)

from performance_presets import phrases as performance_phrases, phrase_for, phrase_with_duration, interpolate_preset, presets_for_entity, preset_for_entity
from ui_themes import theme_names, theme_palette, theme_stylesheet, mix as theme_mix, on_color, is_light_theme
from help_content import help_markdown
from help_tooltips import (bind_help, bind_attributes, bind_controls, refresh_tree, set_help_language, render_help)
from transport_icons import transport_icon
from auricle_drum import KIT_DEFAULTS, KIT_TOOLTIPS, kit_value
from coordinated_kit import (ROLES as KIT_ROLES, STYLES as KIT_STYLES, METERS as KIT_METERS,
                             CREATIVE_DEFAULTS, creative_value, KitStep, KitCoordinator, coordinated,
                             voice_role, infer_role, phrase_bars, STEP_BEATS)
from motif_development import MODES as MOTIF_MODES, settings as motif_settings, digest as motif_digest
from pattern_chance import step_chances
from auricle_catalogs import DEFAULT_PATTERN
from generators import parse_number_list, fixed_pattern
from mutators import mutators_for_target, mutator_help
from drum_editing import sound_snapshot, apply_sound
from drum_rhythm import enable_musical_kit
from drum_rhythm_ui import DrumRhythmPanel
from project_history_ui import HistoryController
from project_history import document_state, parameter_only_changes
from auricle_persistence import project_from_dict
from harmonic_plan_ui import HarmonicPlanPanel
from composition_planner_ui import CompositionPlannerPanel
from instrument_dialogue_ui import DialogueControls
from auricle_resources import asset_path, REQUIRED_ASSETS
from parameter_sources_ui import ParameterSourceLabel, source_label, update_parameter_sources
from parameter_sources import SOURCE_COLORS, SourceSnapshot, feedback_value
from midi_expression_ui import MidiExpressionEditor, MidiSyncDialog
from midi_expression import normalize_expression, normalize_midi_sync
from midi_learn import normalize_mappings, decode_input_message, normalize_mapping, mapping_matches, MidiLearnRuntime, MAX_MAPPINGS
from midi_learn_ui import MidiLearnDialog
from midi_input_reader import read_input_loop
from midi_input_diagnostics import MidiInputDiagnostics, format_diagnostics
from ui_metrics import (DENSE_HEIGHT, TRANSPORT_HEIGHT, TRANSPORT_WIDTH,
                        MODE_WIDTH, TAB_ICON_SIZE, CARD_HEIGHT, initial_window_geometry, quiet_rebuild)
from ui_icons import block_type_icon, navigation_icon, application_icon, logo_pixmap, LogoLabel
from ui_layout import InspectorPair, InspectorIdentity, InspectorControlGrid, parameter_cell

PARAMETER_LABELS = {
    "fill_density": "Density", "event_probability": "Probability", "gate": "Gate",
    "live_min_beats": "Min Beats", "live_max_beats": "Max Beats", "live_gate": "Live Gate",
    "euclidean_steps": "Steps", "bres_steps": "Steps", "pulses": "Pulses",
    "euclidean_rotation": "Rotation", "bres_rotation": "Rotation", "tm_rotation": "Rotation",
    "debruijn_rotation": "Rotation", "fib_offset": "Offset",
    "poly_a": "Cycle A", "poly_b": "Cycle B", "poly_phase_a": "Phase A", "poly_phase_b": "Phase B",
    "tm_density": "Density", "fib_density": "Density", "sequence_mod": "Degree Range",
    "sequence_stride": "Stride", "sequence_offset": "Offset", "debruijn_order": "Order",
    "interval_step": "Step", "interval_return": "Return Bias", "interval_range": "Range", "interval_leap": "Leap Chance",
    "scale_step": "Step", "scale_direction": "Direction", "scale_octaves": "Octave Range", "scale_leap": "Leap Chance",
    "scale_octave_spread": "Octave Spread", "arp_octaves": "Octave Range", "ca_rule": "Rule",
    "ca_generations": "Generations", "ca_density": "Density", "ca_boundary": "Boundary", "ca_evolution": "Evolution", "ls_iterations": "Iterations",
    "turing_density": "Density", "orbit_cycle_a": "Orbit A Cycle", "orbit_cycle_b": "Orbit B Cycle",
    "orbit_phase_a": "Orbit A Phase", "orbit_phase_b": "Orbit B Phase", "orbit_rotation": "Rotation",
    "geometry_particles": "Particles", "geometry_speed": "Speed", "geometry_substeps": "Substeps",
    "chaos_r": "Chaos R", "chaos_x": "Initial X", "chaos_octaves": "Octave Range", "chaos_burn_in": "Burn-in", "chaos_smooth": "Smooth",
    "markov_jump": "Max Jump", "markov_transpose": "Transpose", "markov_octaves": "Octave Range",
    "markov_rest": "Rest Chance", "markov_leap": "Leap Chance", "markov_stay": "Stay Chance",
    "walk_step": "Step", "walk_range": "Range", "walk_start": "Start", "walk_return_bias": "Return Bias", "walk_drift": "Drift",
    "probability": "Probability", "probability_pitch_range": "Pitch Range", "probability_center": "Center",
    "probability_octaves": "Octave Range", "probability_velocity_floor": "Velocity Floor",
    "pattern_rotation": "Rotation", "pattern_scale": "Scale", "pattern_probability": "Probability",
    "velocity_base": "Velocity Base", "velocity_range": "Velocity Range", "velocity_random": "Velocity Random", "velocity_accent": "Accent",
    "transpose": "Transpose", "octave": "Octave", "amount": "Amount", "feedback": "Feedback", "mix": "Mix", "time": "Time", "repeats": "Repeats",
    "groove_follow": "Groove Mask", "groove_accent": "Groove Accent", "groove_offset": "Groove Offset", "harmony_anchor": "Chord Anchor",
}
def parameter_label(key, fallback=None):
    return PARAMETER_LABELS.get(key, fallback if fallback is not None else key.replace("_", " ").title())

DEFAULT_BLOCK_COLORS = {
    "DRUM": "#d86b6b",
    "BASS": "#5f9ed6",
    "MELODY": "#d8a84e",
    "PAD": "#8b78d8",
    "CHORD": "#59b89a",
}

GLOBAL_MACRO_DEFS = (
    ("Energy", "energy"),
    ("Tension", "tension"),
    ("Density", "density"),
    ("Variation", "variation"),
)
GLOBAL_MACRO_COLORS = ("#e58a3d", "#bd6ee8", "#4c9ae8", "#5fbd78")
NAVIGATION_SYMBOLS = {"BLOCKS": "▦", "PERFORM": "▶", "COMPOSITION": "▤",
                      "RELATIONS": "↔", "MIDI MONITOR": "≋", "HELP": "?"}


def ensure_global_macros(project):
    """Materialize the four Perform macros and preserve user names/routes."""
    macros = list(getattr(project, "macros", []) or [])
    defaults = (0.50, 0.50, 0.50, 0.50)
    while len(macros) < len(GLOBAL_MACRO_DEFS):
        index = len(macros)
        name, control = GLOBAL_MACRO_DEFS[index]
        macros.append({"name": name, "control": control, "value": defaults[index], "routes": []})
    for index, (default_name, control) in enumerate(GLOBAL_MACRO_DEFS):
        macro = macros[index]
        macro.setdefault("name", default_name)
        macro.setdefault("control", control)
        macro.setdefault("value", defaults[index])
        macro.setdefault("routes", [])
    project.macros = macros
    return macros


_BLOCK_COLOR_PALETTE = (
    "#e57373", "#f06292", "#ba68c8", "#9575cd", "#7986cb", "#64b5f6",
    "#4fc3f7", "#4dd0e1", "#4db6ac", "#81c784", "#aed581", "#dce775",
    "#ffd54f", "#ffb74d", "#ff8a65", "#a1887f", "#90a4ae",
)

def random_block_color(existing=()):
    """Choose a persistent, visually distinct accent for a newly created block."""
    used = {str(c).lower() for c in existing if c}
    choices = [c for c in _BLOCK_COLOR_PALETTE if c.lower() not in used]
    return random.choice(choices or _BLOCK_COLOR_PALETTE)

def block_type_color(project, block_type):
    colors = getattr(project, "block_colors", None) or {}
    return colors.get(block_type, DEFAULT_BLOCK_COLORS.get(block_type, "#7f8c99"))

def block_color(project, block):
    """Return the effective accent color for one block.

    New projects can assign colors per block. Older projects remain compatible
    through the legacy per-type color fallback.
    """
    color = getattr(block, "color", "") or ""
    return color if color else block_type_color(project, block.block_type)


# Active theme tokens for widgets that paint themselves or need per-widget
# rules.  MainWindow._apply_style() keeps this in sync with the theme combo.
_ACTIVE_THEME = theme_palette("Midnight")


def active_theme():
    return _ACTIVE_THEME


def set_active_theme(theme):
    global _ACTIVE_THEME
    _ACTIVE_THEME = theme


def build_qpalette(t) -> QPalette:
    """QPalette matching a theme.

    Stylesheets alone do not change palette roles such as Highlight/Mid/Base,
    which custom-painted widgets (knobs, piano roll, preview) and dialogs use.
    """
    pal = QPalette()
    roles = {
        QPalette.Window: t.bg, QPalette.WindowText: t.text, QPalette.Base: t.panel,
        QPalette.AlternateBase: t.card, QPalette.Text: t.text, QPalette.Button: t.card,
        QPalette.ButtonText: t.text, QPalette.BrightText: on_color(t.danger),
        QPalette.Highlight: t.accent, QPalette.HighlightedText: on_color(t.accent),
        QPalette.ToolTipBase: t.card, QPalette.ToolTipText: t.text,
        QPalette.PlaceholderText: t.muted, QPalette.Link: t.accent2,
        QPalette.Light: theme_mix(t.card, t.text, .18), QPalette.Midlight: theme_mix(t.border, t.card, .5),
        QPalette.Mid: t.border, QPalette.Dark: theme_mix(t.border, t.bg, .5),
        QPalette.Shadow: theme_mix(t.bg, "#000000", .5),
    }
    for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        for role, color in roles.items():
            pal.setColor(group, role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t.muted))
    return pal


def tinted_pixmap(path, color, width, height) -> QPixmap:
    """Logo recoloured with a theme colour; alpha is preserved.

    The bundled logo is white and disappeared on light themes.
    """
    source = QPixmap(str(path))
    if source.isNull():
        return source
    source = source.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QPixmap(source.size())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(out.rect(), QColor(color))
    painter.end()
    return out


def block_mute_stylesheet() -> str:
    """Theme-aware rules for the latched block MUTE button."""
    t = active_theme()
    return (
        f"QPushButton#blockMute {{ background:{t.input}; color:{t.muted}; border:1px solid {t.border}; border-radius:5px; font-weight:700; padding:0; min-width:{DENSE_HEIGHT - 2}px; max-width:{DENSE_HEIGHT - 2}px; min-height:{DENSE_HEIGHT - 2}px; max-height:{DENSE_HEIGHT - 2}px; }}"
        f"QPushButton#blockMute:hover {{ border-color:{t.accent}; color:{t.text}; }}"
        f"QPushButton#blockMute:checked {{ background:{t.danger}; color:{on_color(t.danger)}; border:1px solid {t.danger}; }}"
    )


def repolish(widget):
    """Re-apply stylesheet rules after a dynamic property changed."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


# Algorithm affinity used only by the GUI as a visual hint.
# rhythm  = strongest use is event/rhythm generation
# pitch   = strongest use is notes/melodic material
# both    = useful for both representations
ALGORITHM_AFFINITY = {
    "Euclidean": "rhythm",
    "Bresenham": "rhythm",
    "Polyrhythm": "rhythm",
    "Thue-Morse": "rhythm",
    "Fibonacci Rhythm": "rhythm",
    "Fibonacci": "both",
    "Recaman": "both",
    "De Bruijn": "both",
    "Markov": "pitch",
    "Random Walk": "pitch",
    "Interval Walker": "pitch",
    "Scale Walker": "pitch",
    "Weighted Scale": "pitch",
    "Arpeggiator": "pitch",
    "Probability": "both",
    "Pattern": "both",
    "Cellular Automaton": "both",
    "L-System": "both",
    "Logistic Chaos": "both",
    "Turing Machine": "both",
    "Orbital Sequence": "rhythm",
    "Geometry Collision": "both",
}

ALGORITHM_AFFINITY_COLORS = {
    "rhythm": "#2f7de1",  # blue
    "pitch": "#e58a24",   # orange
}

def algorithm_affinity(name: str) -> str:
    """Return the GUI classification for an algorithm."""
    return ALGORITHM_AFFINITY.get(str(name), "both")


@lru_cache(maxsize=128)
def algorithm_affinity_icon(name: str, size: int = 12) -> QIcon:
    """Create the small square affinity marker shown in algorithm combos."""
    affinity = algorithm_affinity(name)
    blue = QColor(ALGORITHM_AFFINITY_COLORS["rhythm"])
    orange = QColor(ALGORITHM_AFFINITY_COLORS["pitch"])
    border = QColor("#30353b")
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, False)
    rect = pixmap.rect().adjusted(1, 1, -1, -1)
    if affinity == "rhythm":
        painter.fillRect(rect, blue)
    elif affinity == "pitch":
        painter.fillRect(rect, orange)
    else:
        # Upper-left half blue, lower-right half orange, separated by a
        # diagonal. This remains readable even at the small 12 px size.
        painter.setBrush(QBrush(blue)); painter.setPen(Qt.NoPen)
        painter.drawPolygon([rect.topLeft(), rect.topRight(), rect.bottomLeft()])
        painter.setBrush(QBrush(orange))
        painter.drawPolygon([rect.topRight(), rect.bottomRight(), rect.bottomLeft()])
        painter.setPen(QPen(border, 1))
        painter.drawLine(rect.topLeft(), rect.bottomRight())
    painter.setPen(QPen(border, 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(rect)
    painter.end()
    return QIcon(pixmap)


def setup_algorithm_combo(combo: QComboBox, current: str | None = None) -> QComboBox:
    """Populate an algorithm QComboBox with affinity icons."""
    combo.clear()
    combo.setIconSize(QSize(12, 12))
    for algorithm in GENERATORS:
        combo.addItem(algorithm_affinity_icon(algorithm), algorithm)
        index = combo.count() - 1
        combo.setItemData(index, algorithm_affinity(algorithm), Qt.UserRole)
    if current in GENERATORS:
        combo.setCurrentText(current)
    return combo


def monochrome_tab_icon(symbol: str, size: int = TAB_ICON_SIZE, color: str | None = None) -> QIcon:
    return navigation_icon(symbol, color or active_theme().muted, size)


class SourceTabBar(QTabBar):
    """Native navigation coloured like the parameter source indicators."""
    @staticmethod
    def source_colors(theme, source, selected=False, hovered=False):
        color = SOURCE_COLORS[source]
        background = theme_mix(theme.tab, color, .55 if selected else .33 if hovered else .17)
        return background, on_color(background, dark="#000000"), color if selected else theme_mix(theme.border, color, .70)

    def paintEvent(self, event):
        super().paintEvent(event)
        theme = getattr(self.window(), "_active_theme", None) or active_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(self.font())
        for index in range(self.count()):
            source = self.tabData(index)
            if source not in SOURCE_COLORS:
                continue
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            selected = bool(option.state & QStyle.State_Selected)
            background, ink, border = self.source_colors(theme, source, selected, bool(option.state & QStyle.State_MouseOver))
            if not self.isTabEnabled(index):
                ink = theme_mix(ink, background, .55)
            rect = QRectF(self.tabRect(index)).adjusted(.5, .5, -4.5, -.5)
            painter.setPen(QPen(QColor(border), 2 if selected else 1))
            painter.setBrush(QColor(background))
            painter.drawRoundedRect(rect, 6, 6)
            text_rect = rect.adjusted(14, 0, -14, 0)
            symbol = NAVIGATION_SYMBOLS.get(self.tabText(index))
            if symbol:
                size = self.iconSize().width()
                monochrome_tab_icon(symbol, size=size, color=ink).paint(
                    painter, int(text_rect.left()), int(rect.center().y() - size / 2), size, size)
                text_rect.adjust(size + 6, 0, 0, 0)
            if source == "Composition":
                painter.setBrush(QColor(SOURCE_COLORS["Perform"]))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(rect.right()-10, rect.center().y()), 3, 3)
                text_rect.adjust(0, 0, -6, 0)
            painter.setPen(QColor(ink))
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                             self.fontMetrics().elidedText(self.tabText(index), Qt.ElideRight, int(text_rect.width())))
            if selected and self.hasFocus():
                painter.setPen(QPen(QColor(ink), 1, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 3, 3)
        painter.end()


class Knob(QWidget):
    """Compact circular control with a layout-owned numeric readout.

    The dial is painted only in the upper region.  The value is a real QLabel
    child, so accordion/scroll-area geometry cannot clip it independently of
    the control's size hint.
    """
    changed = Signal(float)
    midi_learn_requested = Signal(object)
    midi_clear_requested = Signal(object)

    def __init__(self, value=0.5, parent=None, default=None, lo=0.0, hi=1.0, integer=False, decimals=2):
        super().__init__(parent)
        self.lo=float(lo); self.hi=float(hi); self.integer=bool(integer); self.decimals=int(decimals)
        self.default=float(value if default is None else default)
        self._value=float(value)
        self._runtime_value = None
        self._drag_start_y=None; self._drag_start_value=None
        self.setFixedSize(54, 74)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip("Drag to change · wheel to adjust · double-click to reset · Shift for fine adjustment")
        self.setMouseTracking(True)
        self._wheel_accum = 0.0

        self.value_label = QLabel(self._formatted(), self)
        self.value_label.setObjectName("knobValue")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.value_label.setGeometry(0, 55, 54, 17)

    def bind_parameter(self, block_id, key):
        self._auricle_parameter = (block_id, key)
        self._auricle_has_midi_learn_menu = True
        if not bind_help(self, key):
            # User-defined keys still support learning before they have a catalog entry.
            self.setToolTip(self.toolTip() + " · Right-click: MIDI Learn / clear mapping")

    def contextMenuEvent(self, event):
        binding = getattr(self, "_auricle_parameter", None)
        if not binding:
            event.ignore()
            return
        menu = QMenu(self)
        learn = menu.addAction("MIDI Learn this parameter…")
        clear = menu.addAction("Clear MIDI mapping")
        menu.addSeparator()
        automate = menu.addAction("Automate in Composition…")
        influences = menu.addAction("Parameter influences…")
        host = self.parentWidget()
        while host is not None and not hasattr(host, "_assign_composition_automation"):
            host = host.parentWidget()
        automate.setEnabled(host is not None)
        influences.setEnabled(host is not None)
        chosen = menu.exec(event.globalPos())
        target = {"kind": "block_parameter", "block_id": int(binding[0]),
                  "parameter": str(binding[1]), "integer": bool(self.integer),
                  "min": float(self.lo), "max": float(self.hi), "initial": float(self.value())}
        if chosen == learn:
            self.midi_learn_requested.emit(target)
        elif chosen == clear:
            self.midi_clear_requested.emit(target)
        elif chosen == automate and host is not None:
            host._assign_composition_automation(*binding)
        elif chosen == influences and host is not None:
            host._open_automation_influences(*binding)
        menu.deleteLater()

    def _norm(self):
        if self.hi == self.lo: return 0.0
        return max(0.0, min(1.0, (self.displayValue()-self.lo)/(self.hi-self.lo)))

    def _formatted(self):
        value = self.displayValue()
        if self.integer: return str(int(round(value)))
        if self.decimals <= 0: return str(int(round(value)))
        return f"{value:.{self.decimals}f}"

    def value(self):
        return int(round(self._value)) if self.integer else self._value

    def displayValue(self):
        return self._value if self._runtime_value is None else self._runtime_value

    def set_runtime_value(self, manual, effective):
        """UI feedback only: preserve the authored value and emit no edit."""
        if self._drag_start_y is not None:
            return
        if not all(math.isfinite(float(v)) for v in (manual, effective)):
            return
        manual = max(self.lo, min(self.hi, float(manual)))
        effective = max(self.lo, min(self.hi, float(effective)))
        if self.integer:
            manual, effective = round(manual), round(effective)
        if self._value == manual and self._runtime_value == effective:
            return
        self._value = manual
        self._runtime_value = effective
        self._sync_value_label()
        self.update()

    def _sync_value_label(self):
        if hasattr(self, "value_label"):
            self.value_label.setText(self._formatted())

    def setValue(self, value):
        v=max(self.lo,min(self.hi,float(value)))
        if self.integer: v=round(v)
        changed=abs(v-self._value)>1e-12
        self._value=v
        self._runtime_value = None
        self._sync_value_label()
        self.update()
        if changed: self.changed.emit(self.value())

    def setDefault(self, value):
        self.default=float(value)
        self.update()

    def _reset(self):
        self.setValue(self.default)

    def mouseDoubleClickEvent(self, event):
        if event.button()==Qt.LeftButton:
            self._reset(); event.accept(); return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:
            self._drag_start_y=event.position().y(); self._drag_start_value=self._value
            self.setFocus(); self.grabMouse(); event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_y is None: return
        dy=self._drag_start_y-event.position().y()
        span=self.hi-self.lo
        sensitivity=span/180.0
        if event.modifiers() & Qt.ShiftModifier: sensitivity/=5.0
        self.setValue(self._drag_start_value + dy*sensitivity)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_start_y=None; self._drag_start_value=None
        if self.mouseGrabber() is self:
            self.releaseMouse()
        event.accept()

    def keyPressEvent(self, event):
        step=(self.hi-self.lo)/100.0
        if self.integer: step=max(1, round(step))
        if event.key()==Qt.Key_Right or event.key()==Qt.Key_Up:
            self.setValue(self._value + step); event.accept(); return
        if event.key()==Qt.Key_Left or event.key()==Qt.Key_Down:
            self.setValue(self._value - step); event.accept(); return
        if event.key()==Qt.Key_Home:
            self.setValue(self.lo); event.accept(); return
        if event.key()==Qt.Key_End:
            self.setValue(self.hi); event.accept(); return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        delta=event.angleDelta().y() or event.angleDelta().x()
        if not delta:
            event.ignore(); return
        span=self.hi-self.lo
        step=(span/100.0 if not self.integer else max(1.0, round(span/100.0)))
        if event.modifiers() & Qt.ShiftModifier:
            step = step/5.0 if not self.integer else max(1.0, step/5.0)
        # Accumulate high-resolution trackpad deltas: small deltas used to be
        # rounded away, so integer knobs could not be scrolled on trackpads.
        self._wheel_accum += delta/120.0
        whole = int(self._wheel_accum) if self.integer else self._wheel_accum
        if whole:
            self._wheel_accum -= whole
            self.setValue(self._value + whole*step)
        event.accept()

    def focusInEvent(self, event):
        super().focusInEvent(event); self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event); self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "value_label"):
            self.value_label.setGeometry(0, max(54, self.height()-19), self.width(), 17)

    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing, True)
        r=min(self.width(), 48); cx=self.width()/2; cy=27; radius=r/2-4
        center_x=cx; center_y=cy
        pal=self.palette()
        base=pal.color(QPalette.Mid); accent=pal.color(QPalette.Highlight)
        if not self.isEnabled(): accent=pal.color(QPalette.Disabled, QPalette.WindowText)
        pen=QPen(base, 5, Qt.SolidLine, Qt.RoundCap); p.setPen(pen)
        rect=QRectF(center_x-radius, center_y-radius, radius*2, radius*2)
        p.drawArc(rect, 225*16, -270*16)
        pen=QPen(accent, 5, Qt.SolidLine, Qt.RoundCap); p.setPen(pen)
        p.drawArc(rect, 225*16, int((-270*self._norm())*16))
        import math
        angle=math.radians(225-270*self._norm())
        x2=center_x+math.cos(angle)*(radius-2); y2=center_y-math.sin(angle)*(radius-2)
        p.setPen(QPen(accent, 2)); p.drawLine(center_x, center_y, x2, y2)
        p.setPen(Qt.NoPen); p.setBrush(accent); p.drawEllipse(int(center_x-3), int(center_y-3), 6, 6)
        if self._runtime_value is not None and abs(self._runtime_value - self._value) > 1e-9:
            manual_norm = max(0., min(1., (self._value-self.lo) / max(1e-9, self.hi-self.lo)))
            manual_angle = math.radians(225-270*manual_norm)
            ghost = pal.color(QPalette.WindowText); ghost.setAlpha(160)
            p.setPen(QPen(ghost, 2))
            p.drawLine(QPointF(cx+math.cos(manual_angle)*(radius+2), cy-math.sin(manual_angle)*(radius+2)),
                       QPointF(cx+math.cos(manual_angle)*(radius+5), cy-math.sin(manual_angle)*(radius+5)))
        if self.hasFocus():
            # Keyboard focus must be visible now that knobs accept arrow keys.
            ring=QColor(accent); ring.setAlpha(170)
            p.setPen(QPen(ring, 1, Qt.DashLine)); p.setBrush(Qt.NoBrush)
            p.drawEllipse(rect.adjusted(-4, -4, 4, 4))
        p.end()


class ParamKnob(Knob):
    def __init__(self, value=0.5, parent=None, default=None):
        super().__init__(value, parent, default, 0.0, 1.0, False, 2)


class RangeKnob(Knob):
    def __init__(self, lo, hi, value, integer=False, parent=None, default=None):
        decimals=0 if integer else (2 if abs(float(hi)-float(lo)) <= 10 else 1)
        super().__init__(value, parent, default, lo, hi, integer, decimals)

# Compatibility aliases: the engine/UI code uses these names in several dialogs.
ParamSlider = ParamKnob
RangeSlider = RangeKnob


class ValueStepper(QWidget):
    """Compact DAW-style numeric editor:  -  value  +

    Platform independent replacement for QSpinBox.  The central editor is a
    QLineEdit, so values can be typed directly.  It also supports mouse wheel,
    arrow keys and the same small-button workflow used by transport controls.
    """
    valueChanged = Signal(object)

    def __init__(self, value=0, parent=None):
        super().__init__(parent)
        self._value = value
        self._minimum = -2147483648
        self._maximum = 2147483647
        self._step = 1
        self._decimals = 0

        self.minus = QPushButton("−")
        self.plus = QPushButton("+")
        self.editor = QLineEdit()
        self.editor.setAlignment(Qt.AlignCenter)
        self.setAccessibleName("Numeric value stepper")
        self.setAccessibleDescription("Change value with buttons, wheel, arrow keys, or text entry")
        self.editor.setAccessibleName("Numeric value input")
        self.minus.setAccessibleName("Decrease value")
        self.plus.setAccessibleName("Increase value")
        self.editor.setObjectName("valueStepperEditor")
        self.minus.setObjectName("valueStepperButton")
        self.plus.setObjectName("valueStepperButton")
        self.minus.setFixedWidth(20)
        self.plus.setFixedWidth(20)
        self.editor.setMinimumWidth(26)

        self.minus.clicked.connect(lambda: self._change(-self._step))
        self.plus.clicked.connect(lambda: self._change(self._step))
        self.editor.editingFinished.connect(self._commit_text)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.minus)
        lay.addWidget(self.editor, 1)
        lay.addWidget(self.plus)
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._refresh()

    def setRange(self, lo, hi):
        self._minimum, self._maximum = lo, hi
        self.setValue(self._value)

    def setMinimum(self, value): self.setRange(value, self._maximum)
    def setMaximum(self, value): self.setRange(self._minimum, value)

    def setSingleStep(self, value): self._step = value

    def setDecimals(self, value):
        self._decimals = value
        self._refresh()

    def value(self):
        return self._value

    def setValue(self, value):
        try:
            number = float(str(value).strip().replace(",", "."))
            if math.isnan(number) or math.isinf(number):
                raise ValueError(value)
            # "12.5" in an integer field rounds instead of being ignored.
            value = number if self._decimals else int(round(number))
        except (TypeError, ValueError):
            # Invalid text restores the current value instead of jumping.
            value = self._value
        value = min(max(value, self._minimum), self._maximum)
        if self._decimals:
            value = round(value, self._decimals)
        if value != self._value:
            self._value = value
            self.valueChanged.emit(value)
        self._refresh()

    def _change(self, delta):
        self.setValue(self._value + delta)

    def _commit_text(self):
        self.setValue(self.editor.text())

    def _refresh(self):
        if self._decimals:
            text = f"{self._value:.{self._decimals}f}"
        else:
            text = str(int(self._value))
        self.editor.setText(text)

    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        if not dy:
            # Horizontal scrolling used to count as "down" and decrement.
            event.ignore()
            return
        self._wheel_accum = getattr(self, "_wheel_accum", 0.0) + dy / 120.0
        steps = int(self._wheel_accum)
        if steps:
            self._wheel_accum -= steps
            self._change(steps * self._step)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            self._change(self._step)
            return
        if event.key() == Qt.Key_Down:
            self._change(-self._step)
            return
        super().keyPressEvent(event)

    def sizeHint(self):
        return QSize(72, 24)

    def set_accessible_label(self, text):
        """Give screen readers the meaning of this stepper (BPM, channel...)."""
        self.setAccessibleName(str(text))
        self.editor.setAccessibleName(f"{text} value")
        self.minus.setAccessibleName(f"Decrease {text}")
        self.plus.setAccessibleName(f"Increase {text}")


# Backward compatibility: old UI code still refers to ContrastSpinBox.
# ValueStepper replaced QSpinBox but keeps the same public API.
ContrastSpinBox = ValueStepper
ContrastDoubleSpinBox = ValueStepper


class RandomizeDialog(QDialog):
    def __init__(self, host, block, parent=None):
        super().__init__(parent); self.host=host; self.block=block; self.setWindowTitle("Randomize block"); self.resize(340,300)
        lay=QVBoxLayout(self); lay.addWidget(QLabel(f"Randomize: {block.name}"))
        self.checks={}
        for name in ("Generator","Density","Pitch","Mutators","Processes","Relations"):
            cb=QCheckBox(name); cb.setChecked(name not in ("Relations",)); self.checks[name]=cb; lay.addWidget(cb)
        lay.addWidget(QLabel("Amount")); self.amount=ParamSlider(.35); lay.addWidget(self.amount)
        buttons=QDialogButtonBox(QDialogButtonBox.Cancel); buttons.rejected.connect(self.reject)
        self.randomize_button=QPushButton("RANDOMIZE")
        self.randomize_button.clicked.connect(self.apply_randomize)
        buttons.addButton(self.randomize_button, QDialogButtonBox.AcceptRole)
        lay.addWidget(buttons)
    def apply_randomize(self):
        cats={k for k,v in self.checks.items() if v.isChecked()}
        self.host.engine.randomize_block(self.block,cats,self.amount.value())
        if "Relations" in cats:
            for r in self.host.project.relations:
                if r.source_block==self.block.id or r.destination_block==self.block.id:
                    r.amount=max(0,min(1,r.amount+random.uniform(-.35,.35)*self.amount.value()))
            self.host.engine.apply_relations()
            self.host._refresh_relations()
        self.host._refresh_blocks(); self.host._queue_inspector_refresh(); self.host.performance.refresh_blocks(self.host.project); self.host.patch_overview.rebuild(self.host.project)
        self.host._mark_dirty()
        self.randomize_button.setText("RANDOMIZE AGAIN")

class ModeSwitch(QWidget):
    changed = Signal(str)

    def __init__(self, mode="SEQ", parent=None):
        super().__init__(parent)
        self.seq = QPushButton("SEQ")
        self.live = QPushButton("LIVE")
        for button in (self.seq, self.live):
            button.setCheckable(True)
            button.setObjectName("modeButton")
            button.setFixedSize(MODE_WIDTH, DENSE_HEIGHT)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.addButton(self.seq)
        self.group.addButton(self.live)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addWidget(self.seq)
        layout.addWidget(self.live)
        self.setFixedSize(MODE_WIDTH * 2 + 1, DENSE_HEIGHT)
        self.seq.clicked.connect(lambda: self.changed.emit("SEQ"))
        self.live.clicked.connect(lambda: self.changed.emit("LIVE"))
        self.set_mode(mode)

    def set_mode(self, mode):
        self.seq.setChecked(mode != "LIVE")
        self.live.setChecked(mode == "LIVE")

    def mode(self):
        return "LIVE" if self.live.isChecked() else "SEQ"

class InspectorGroup(QGroupBox):
    accordion_toggled = Signal(bool)
    """Non-collapsible nested inspector group.

    Top-level LayerGroup sections own the accordion hierarchy. Nested groups
    stay permanently visible so the Inspector does not develop nested
    disclosure controls that make navigation and layout harder to follow.
    """

    def __init__(self, title, parent=None, expanded=True):
        super().__init__(title, parent)
        self.base_title = title
        self.summary_text = ""
        self._expanded = bool(expanded)
        # Do NOT use QGroupBox.checkable/checked for accordion state.
        self.setCheckable(False)

    def isChecked(self):
        return True

    def setChecked(self, checked):
        # Compatibility shim: nested InspectorGroup sections are always open.
        self._expanded = True
        self._apply_children_visibility()
        self._update_title()

    def mousePressEvent(self, event):
        # Nested groups are intentionally not interactive accordions.
        super().mousePressEvent(event)

    def set_summary(self, text):
        self.summary_text = text or ""
        self._update_title()

    def _update_title(self):
        suffix = f"   —  {self.summary_text}" if self.summary_text else ""
        self.setTitle(f"{self.base_title}{suffix}")

    def _apply_children_visibility(self):
        for child in self.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            child.setVisible(True)

    def _sync_layout_geometry(self):
        layout = self.layout()
        if layout is None:
            return
        layout.invalidate()
        layout.activate()
        # A QGroupBox adds a styled frame/title outside its layout margins.
        # Publishing only sizeHint() lets a parent compress the group over
        # the knob readouts. totalSizeHint() includes those extra insets.
        hint = layout.totalSizeHint()
        if hint.isValid():
            height = max(0, hint.height(), layout.totalMinimumSize().height())
            if self.minimumHeight() != height:
                self.setMinimumHeight(height)
                self.updateGeometry()

    def _set_expanded(self, expanded):
        # Kept for compatibility with old callers; nested groups remain open.
        self._expanded = True
        self._apply_children_visibility()
        self._update_title()

    def _sync(self, checked):
        self._set_expanded(True)


class LayerGroup(QGroupBox):
    accordion_toggled = Signal(bool)
    """Top-level inspector layer using visibility-only accordion state."""
    def __init__(self, title, parent=None, expanded=True, summary=""):
        super().__init__(title, parent)
        self.base_title = title
        self.summary_text = summary or ""
        self._expanded = bool(expanded)
        # Like InspectorGroup, this is an accordion, not a checkable option.
        # QGroupBox.checkable would disable descendants and can leave nested
        # controls with the wrong enabled/hit-test state during construction.
        self.setCheckable(False)
        self._update_title()

    def isChecked(self):
        return self._expanded

    def setChecked(self, checked):
        self._set_expanded(bool(checked))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 27:
            self._set_expanded(not self._expanded)
            event.accept()
            return
        super().mousePressEvent(event)

    def set_summary(self, text):
        self.summary_text = text or ""
        self._update_title()

    def _update_title(self):
        prefix = "▾" if self._expanded else "▸"
        suffix = f"   —  {self.summary_text}" if self.summary_text and not self._expanded else ""
        self.setTitle(f"{prefix}  {self.base_title}{suffix}")

    def _apply_children_visibility(self):
        for child in self.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            child.setVisible(self._expanded)

    def _sync_layout_geometry(self):
        layout = self.layout()
        if layout is None:
            return
        layout.invalidate()
        layout.activate()
        if self._expanded:
            # Include the outer accordion's frame/title as well as the
            # nested groups, so their numeric readouts remain inside it.
            hint = layout.totalSizeHint()
            height = max(0, hint.height(), layout.totalMinimumSize().height())
        else:
            height = 0
        if self.minimumHeight() != height:
            self.setMinimumHeight(height)
            self.updateGeometry()

    def _set_expanded(self, expanded):
        expanded = bool(expanded)
        if expanded == self._expanded:
            self._apply_children_visibility()
            return
        self._expanded = expanded
        self._apply_children_visibility()
        self._update_title()
        self.accordion_toggled.emit(self._expanded)
        if self._expanded:
            # Nested groups measured themselves while hidden; resync so knob
            # values are not clipped by the group frame after expanding.
            for group in self.findChildren(InspectorGroup):
                group._sync_layout_geometry()
        self._sync_layout_geometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()
        # Top-level Inspector accordions change the scroll page's natural
        # height.  Recompute the page extent after Qt has propagated visibility
        # and layout changes so the scrollbar neither stops early nor retains
        # a large blank tail after sections collapse.
        ancestor = parent
        while ancestor is not None:
            queue_fit = getattr(ancestor, "_queue_inspector_fit", None)
            if callable(queue_fit):
                queue_fit()
                break
            ancestor = ancestor.parentWidget()

    def _sync(self, checked):
        self._set_expanded(checked)


class PatchNode(QGraphicsRectItem):
    def __init__(self, block_id, title, subtitle, x, y, w=210, h=78, selected_callback=None, accent_color="#7f8c99"):
        super().__init__(0, 0, w, h)
        self.block_id = block_id
        self.selected_callback = selected_callback
        self.accent_color = accent_color
        self.setPos(x, y)
        self.setBrush(QBrush(QColor(accent_color).lighter(170)))
        self.setPen(QPen(QColor(accent_color), 2))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.title_item = QGraphicsTextItem(title, self)
        self.title_item.setPos(10, 7)
        self.title_item.setTextWidth(w - 20)
        self.subtitle_item = QGraphicsTextItem(subtitle, self)
        self.subtitle_item.setPos(10, 31)
        self.subtitle_item.setTextWidth(w - 20)
        self.setToolTip(f"Block {title}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.selected_callback is not None:
                self.selected_callback(self.block_id)
            event.accept()
            return
        super().mousePressEvent(event)


class PatchOverview(QWidget):
    block_selected = Signal(int)
    def __init__(self, parent=None):
        super().__init__(parent)
        lay=QVBoxLayout(self); lay.setContentsMargins(6,6,6,6); lay.setSpacing(4)
        head=QHBoxLayout(); head.addWidget(QLabel("PATCH OVERVIEW")); head.addStretch()
        self.info=QLabel("Blocks, musical relations and parameter-modulation routes")
        self.info.setObjectName("muted"); head.addWidget(self.info)
        lay.addLayout(head)
        self.view=QGraphicsView(); self.view.setRenderHints(self.view.renderHints())
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded); self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scene=QGraphicsScene(self); self.view.setScene(self.scene); lay.addWidget(self.view,1)
    def rebuild(self, project):
        self.scene.clear()
        nodes={}
        cols=max(1, min(4, len(project.blocks)))
        for i,b in enumerate(project.blocks):
            col=i%cols; row=i//cols
            node=PatchNode(b.id, b.name, f"{b.block_type}  ·  {b.algorithm}  ·  {b.mode}", 30+col*250, 30+row*125, selected_callback=self.block_selected.emit, accent_color=block_color(project, b))
            base = QColor(block_color(project, b))
            base.setAlpha(45)
            node.setBrush(QBrush(base))
            node.setPen(QPen(QColor(block_color(project, b)), 2))
            node.title_item.setDefaultTextColor(self.view.palette().text().color())
            node.subtitle_item.setDefaultTextColor(self.view.palette().mid().color())
            node.title_item.setAcceptedMouseButtons(Qt.NoButton)
            node.subtitle_item.setAcceptedMouseButtons(Qt.NoButton)
            self.scene.addItem(node); nodes[b.id]=node
        # Relation routes
        for r in project.relations:
            if r.source_block not in nodes or r.destination_block not in nodes: continue
            a=nodes[r.source_block].sceneBoundingRect(); d=nodes[r.destination_block].sceneBoundingRect()
            line=QGraphicsLineItem(a.center().x(),a.center().y(),d.center().x(),d.center().y())
            line.setPen(QPen(self.view.palette().highlight().color(), 1.5)); line.setZValue(-1)
            line.setData(0, "relation")
            self.scene.addItem(line)
            source_voice = next((v for b in project.blocks if b.id == r.source_block
                                 for v in getattr(b, "drum_voices", None) or []
                                 if int(v.id) == int(getattr(r, "source_voice_id", 0) or 0)), None)
            destination_voice = next((v for b in project.blocks if b.id == r.destination_block
                                      for v in getattr(b, "drum_voices", None) or []
                                      if int(v.id) == int(getattr(r, "destination_voice_id", 0) or 0)), None)
            source_label = source_voice.name if source_voice is not None else r.source_part
            destination_label = destination_voice.name if destination_voice is not None else r.destination_part
            txt=QGraphicsTextItem(f"{source_label} → {r.algorithm} → {destination_label}")
            txt.setDefaultTextColor(QColor(active_theme().text))
            txt.setData(0, "relation")
            txt.setPos((a.center().x()+d.center().x())/2-50,(a.center().y()+d.center().y())/2-12)
            self.scene.addItem(txt)
        # Process parameter routes are shown as dashed-looking text routes.
        for b in project.blocks:
            for proc in b.processes:
                if proc.type != "Parameter Modulation": continue
                dest=proc.parameters.get("destination_block")
                if dest not in nodes or b.id not in nodes: continue
                a=nodes[b.id].sceneBoundingRect(); d=nodes[dest].sceneBoundingRect()
                line=QGraphicsLineItem(a.center().x(),a.center().y()+18,d.center().x(),d.center().y()+18)
                pen=self.view.palette().mid().color(); pen.setAlpha(180); line.setPen(QPen(pen, 1, Qt.DashLine)); line.setZValue(-1); self.scene.addItem(line)
                line.setData(0, "modulation")
                txt=QGraphicsTextItem(f"+1 tick  →  {proc.parameters.get('destination_parameter','parameter')}")
                txt.setDefaultTextColor(QColor(active_theme().muted))
                txt.setData(0, "modulation")
                txt.setPos((a.center().x()+d.center().x())/2-50,(a.center().y()+d.center().y())/2+6)
                self.scene.addItem(txt)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-30,-30,30,30))

    def apply_theme(self, theme):
        for item in self.scene.items():
            if isinstance(item, PatchNode):
                item.title_item.setDefaultTextColor(QColor(theme.text))
                item.subtitle_item.setDefaultTextColor(QColor(theme.muted))
            elif isinstance(item, QGraphicsTextItem) and item.parentItem() is None:
                item.setDefaultTextColor(QColor(theme.muted if item.data(0) == "modulation" else theme.text))
            elif isinstance(item, QGraphicsLineItem):
                color = QColor(theme.border if item.data(0) == "modulation" else theme.accent)
                if item.data(0) == "modulation":
                    color.setAlpha(180)
                pen = item.pen(); pen.setColor(color); item.setPen(pen)
        self.view.viewport().update()


class PhraseTimelineWidget(QWidget):
    """Compact phrase timeline with beat ticks and a moving playhead."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.phrase = None
        self.progress = 0.0
        self.stage_index = -1
        self.running = False
        self.setMinimumHeight(42)
        self.setMaximumHeight(48)

    def set_phrase(self, phrase):
        self.phrase = phrase
        self.progress = 0.0
        self.stage_index = -1
        self.running = False
        self.update()

    def set_runtime(self, progress, stage_index, running):
        self.progress = max(0.0, min(1.0, float(progress)))
        self.stage_index = int(stage_index)
        self.running = bool(running)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        theme = active_theme()
        rect = self.rect().adjusted(2, 3, -2, -3)
        painter.fillRect(rect, QColor(theme.panel))
        if self.phrase is None or not getattr(self.phrase, "stages", None):
            painter.setPen(QColor(theme.muted))
            painter.drawText(rect, Qt.AlignCenter, "No phrase selected")
            return

        total = max(.25, sum(float(stage.beats) for stage in self.phrase.stages))
        beat_count = max(1, int(round(total)))
        track = rect.adjusted(6, 16, -6, -7)
        x = float(track.left())
        colors = (QColor(theme.card), QColor(theme.tab), QColor(theme.input), QColor(theme.panel))
        for index, stage in enumerate(self.phrase.stages):
            width = track.width() * float(stage.beats) / total
            segment = QRectF(x, track.top(), width, track.height())
            painter.fillRect(segment, colors[index % len(colors)])
            if self.running and index == self.stage_index:
                painter.fillRect(segment, QColor(theme.selection))
            painter.setPen(QColor(theme.text))
            label = stage.label or stage.technique_id.replace("_", " ").title()
            painter.drawText(segment, Qt.AlignCenter, label)
            x += width

        progress_x = track.left() + track.width() * self.progress
        if self.progress > 0:
            painter.fillRect(QRectF(track.left(), track.top(), max(1.0, progress_x - track.left()), track.height()), QColor(theme.accent2))
        painter.setPen(QPen(QColor(theme.accent), 2))
        painter.drawLine(QPointF(progress_x, track.top() - 3), QPointF(progress_x, track.bottom() + 2))
        painter.setBrush(QColor(theme.accent))
        painter.drawEllipse(QPointF(progress_x, track.top() - 3), 3.0, 3.0)

        painter.setPen(QColor(theme.muted))
        # Long phrases need fewer labels so the beat ruler stays readable.
        label_stride = 1
        while label_stride < beat_count and track.width() * label_stride / beat_count < 32:
            label_stride *= 2
        tick_stride = max(1, label_stride // 4)
        for beat in range(0, beat_count + 1, tick_stride):
            tick_x = track.left() + track.width() * beat / float(beat_count)
            tick_height = 4 if beat % 4 == 0 else 2
            painter.drawLine(QPointF(tick_x, track.top() - tick_height), QPointF(tick_x, track.top()))
            if beat < beat_count and beat % label_stride == 0:
                painter.drawText(QRectF(tick_x - 14, rect.top(), 28, 12), Qt.AlignCenter, str(beat + 1))


class TechniqueCurveWidget(QWidget):
    """Show the normalized time-shape of the selected performance technique."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preset = None
        self.amount = 1.0
        self.shape = "in"
        self.progress = None
        self.primary_color = None
        self.setMinimumHeight(56)
        self.setMaximumHeight(62)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_technique(self, preset, amount=1.0, shape="in"):
        self.preset = preset
        self.amount = float(amount)
        self.shape = str(shape or "in")
        self.update()

    def set_progress(self, progress):
        progress = None if progress is None else max(0., min(1., float(progress)))
        if progress != self.progress:
            self.progress = progress
            self.update()

    def _parameter_curves(self):
        if self.preset is None:
            return []
        curves = []
        for move in getattr(self.preset, "moves", ()):
            if abs(float(move.end) - float(move.start)) < 1e-9:
                continue
            values = []
            for step in range(17):
                sample = interpolate_preset(self.preset, step / 16.0, self.amount, self.shape)
                value = float(sample.get(move.parameter, move.start))
                lo, hi = sorted((float(move.start), float(move.end)))
                normalized = (value - lo) / max(1e-9, hi - lo)
                values.append(max(0.0, min(1.0, normalized)))
            curves.append((move.parameter.replace("_", " "), values))
        return curves

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        theme = active_theme()
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.fillRect(rect, QColor(theme.panel))
        curves = self._parameter_curves()
        painter.setPen(QColor(theme.border))
        for i in range(5):
            y = rect.top() + rect.height() * i / 4.0
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        for i in range(9):
            x = rect.left() + rect.width() * i / 8.0
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        if not curves:
            painter.setPen(QColor(theme.muted))
            painter.drawText(rect, Qt.AlignCenter, "No parameter curve")
            return
        curve_colors = (QColor(self.primary_color or theme.accent), QColor(theme.accent2), QColor(theme.success), QColor(theme.warning), QColor(theme.danger))
        if self.primary_color and is_light_theme(theme):
            curve_colors = (curve_colors[0].darker(150), *curve_colors[1:])
        self.setToolTip("\n".join(label for label, _values in curves))
        legend_y = rect.top() + 11
        legend_x = rect.left() + 6
        for curve_index, (label, values) in enumerate(curves):
            color = curve_colors[curve_index % len(curve_colors)]
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(legend_x, legend_y), QPointF(legend_x + 10, legend_y))
            painter.setPen(QColor(theme.muted))
            painter.drawText(QRectF(legend_x + 13, legend_y - 6, 92, 12), Qt.AlignLeft, label[:14])
            legend_x += 112
            if legend_x > rect.right() - 50:
                break
        chart = rect.adjusted(22, 18, -4, -12)
        painter.setPen(QColor(theme.muted))
        painter.drawText(QRectF(rect.left(), chart.top() - 2, 18, 10), Qt.AlignLeft, "1")
        painter.drawText(QRectF(rect.left(), chart.bottom() - 8, 18, 10), Qt.AlignLeft, "0")
        painter.drawText(QRectF(chart.left(), chart.bottom() + 1, chart.width(), 10), Qt.AlignCenter, "time")
        for curve_index, (_label, values) in enumerate(curves):
            path = QPainterPath()
            for index, value in enumerate(values):
                x = chart.left() + chart.width() * index / max(1, len(values) - 1)
                y = chart.bottom() - chart.height() * value
                if index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(curve_colors[curve_index % len(curve_colors)], 2))
            painter.drawPath(path)

        if self.progress is not None:
            x = chart.left() + chart.width()*self.progress
            painter.setPen(QPen(QColor(theme.success), 1.5))
            painter.drawLine(QPointF(x, chart.top()), QPointF(x, chart.bottom()))


class PhraseStageStrip(QWidget):
    """Segmented display of a multi-stage phrase.

    The running stage is highlighted and finished stages are tinted; when no
    phrase runs nothing is highlighted (previously stage 1 was always lit).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._pills = []
        self._active = None

    def set_phrase(self, phrase):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._pills = []
        self._active = None
        if not phrase:
            return
        for i, stage in enumerate(phrase.stages):
            label = stage.label or stage.technique_id.replace('_', ' ').title()
            beats = f"{stage.beats:.2f}".rstrip("0").rstrip(".")
            pill = QLabel(f"{label} ({beats}b)")
            pill.setObjectName("phraseStage")
            pill.setAlignment(Qt.AlignCenter)
            self._layout.addWidget(pill, 1)
            self._pills.append(pill)
            if i < len(phrase.stages) - 1:
                arrow = QLabel("›")
                arrow.setObjectName("phraseArrow")
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setFixedWidth(18)
                self._layout.addWidget(arrow)
        self.set_active(-1)

    def set_active(self, index):
        index = int(index)
        if index == self._active:
            return
        self._active = index
        for i, pill in enumerate(self._pills):
            pill.setProperty("active", i == index)
            pill.setProperty("done", 0 <= index and i < index)
            repolish(pill)


class PerformSection(QWidget):
    """Collapsible section used to keep the Perform workspace compact."""
    def __init__(self, title, widget, expanded=True, parent=None):
        super().__init__(parent)
        self.title = str(title)
        self.header = QPushButton()
        self.header.setObjectName("collapseHeader")
        self.header.setCheckable(True)
        self.header.setChecked(bool(expanded))
        self.header.setAccessibleName(f"Toggle {self.title} section")
        self.body = widget
        self.header.toggled.connect(self._toggle)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.header)
        layout.addWidget(self.body)
        self._toggle(bool(expanded))

    def _toggle(self, expanded):
        self.body.setVisible(bool(expanded))
        self.header.setText(("▾ " if expanded else "▸ ") + self.title)


class TargetSelectionDialog(QDialog):
    def __init__(self, project, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Phrase targets")
        self.setMinimumWidth(340)
        self.checks = []
        layout = QVBoxLayout(self)
        hint = QLabel("Choose which blocks receive the phrase.")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        for block in project.blocks:
            check = QCheckBox(f"{block.name} · {block.block_type}")
            check.setChecked(block.id in selected)
            check.setEnabled(not bool(block.muted))
            if block.muted:
                check.setToolTip("Muted blocks are unavailable as phrase targets")
            check.setProperty("blockId", int(block.id))
            layout.addWidget(check)
            self.checks.append(check)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_ids(self):
        return [int(c.property("blockId")) for c in self.checks if c.isChecked()]


class PhrasePanel(QGroupBox):
    """Compact phrase launcher shown at the top of the Perform tab."""
    def __init__(self, host, parent=None):
        super().__init__("GLOBAL PHRASE", parent)
        self.host = host
        self._block_names = []
        self._target_ids = set()
        self._syncing = True
        self._build()
        self._syncing = False
        self.sync_from_project()
        bind_attributes(self, "perform", {"phrase_combo": "phrase", "duration": "duration", "amount": "amount", "targets_button": "targets"})

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Phrase"))
        self.phrase_combo = QComboBox()
        for phrase in performance_phrases():
            self.phrase_combo.addItem(phrase.name, phrase.id)
        self.phrase_combo.currentIndexChanged.connect(self._phrase_changed)
        top.addWidget(self.phrase_combo, 1)
        top.addWidget(QLabel("Duration · beats"))
        self.duration = ValueStepper()
        self.duration.setRange(4, 256)
        self.duration.setFixedWidth(96)
        self.duration.set_accessible_label("Phrase duration in beats")
        self.duration.setToolTip("4–256 quarter-note beats. All stages stretch proportionally; live changes preserve progress.")
        self.duration.valueChanged.connect(self._duration_changed)
        top.addWidget(self.duration)
        top.addWidget(QLabel("Amount"))
        self.amount = QSlider(Qt.Horizontal)
        self.amount.setRange(0, 100)
        self.amount.setValue(100)
        self.amount.setMinimumWidth(80)
        self.amount.setMaximumWidth(220)
        self.amount_label = QLabel("100%")
        self.amount.valueChanged.connect(self._amount_changed)
        top.addWidget(self.amount, 1)
        top.addWidget(self.amount_label)
        lay.addLayout(top)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.description = QLabel()
        self.description.setObjectName("muted")
        self.description.setWordWrap(True)
        actions.addWidget(self.description, 1)
        self.start = QPushButton("PLAY PHRASE")
        self.start.clicked.connect(self._start)
        actions.addWidget(self.start)
        self.stop = QPushButton("STOP PHRASE")
        self.stop.clicked.connect(self._stop)
        actions.addWidget(self.stop)
        self.stop.setEnabled(False)
        lay.addLayout(actions)

        self.stages = PhraseStageStrip()
        lay.addWidget(self.stages)

        self.timeline = PhraseTimelineWidget()
        self.timeline.setToolTip("Phrase progress across the selected phrase's actual beats")
        lay.addWidget(self.timeline)

        self.block_summary = QLabel()
        self.block_summary.setObjectName("muted")
        self.block_summary.setWordWrap(True)
        lay.addWidget(self.block_summary)
        self.targets_button = QPushButton("TARGETS")
        self.targets_button.setAccessibleName("Choose phrase targets")
        self.targets_button.clicked.connect(self._choose_targets)
        actions.addWidget(self.targets_button)
        self._phrase_changed()

    def refresh_blocks(self, project):
        if not self._target_ids:
            self._target_ids = {int(block.id) for block in project.blocks if not block.muted}
        valid = {int(block.id) for block in project.blocks}
        self._target_ids.intersection_update(valid)
        self._block_names = [f"{block.name} · {block.block_type}" for block in project.blocks if int(block.id) in self._target_ids]
        if self._block_names:
            extra = max(0, len(self._block_names) - 6)
            shown = self._block_names[:6]
            suffix = f"   +{extra}" if extra else ""
            self.block_summary.setText("Targets: " + "   |   ".join(shown) + suffix)
            self.targets_button.setText(f"TARGETS ({len(self._target_ids)})")
        else:
            self.block_summary.setText("Targets: none selected")
            self.targets_button.setText("TARGETS (0)")

    def sync_from_project(self):
        """Restore the visible phrase selector from the loaded engine state."""
        self._syncing = True
        saved = self.host.project.performance.get("_phrase", {})
        state = getattr(getattr(self.host, "engine", None), "director", None)
        state = getattr(state, "phrase", None)
        phrase_id = str(saved.get("phrase_id") or getattr(state, "phrase_id", "") or "")
        if not phrase_id:
            phrase_id = str(getattr(self.host.project, "phrase_state", {}).get("phrase_id", "") or "")
        self.phrase_combo.blockSignals(True)
        self.phrase_combo.setCurrentIndex(max(0, self.phrase_combo.findData(phrase_id)))
        self.phrase_combo.blockSignals(False)
        phrase = phrase_for(self.phrase_combo.currentData())
        beats = saved.get("duration_beats")
        if beats is None and getattr(state, "phrase_id", "") == self.phrase_combo.currentData():
            beats = state.memory.get("total_beats")
        self.duration.blockSignals(True)
        self.duration.setValue(beats if beats is not None else phrase.total_beats)
        self.duration.blockSignals(False)
        intensity = saved.get("amount", getattr(state, "intensity", None))
        if intensity is None:
            intensity = getattr(self.host.project, "phrase_state", {}).get("intensity", 1.0)
        try:
            amount = max(0, min(100, int(round(float(intensity) * 100))))
        except (TypeError, ValueError):
            amount = 100
        self.amount.blockSignals(True)
        self.amount.setValue(amount)
        self.amount.blockSignals(False)
        self.amount_label.setText(f"{amount}%")
        ids = saved.get("block_ids", getattr(state, "block_ids", None))
        if ids is None:
            ids = getattr(self.host.project, "phrase_state", {}).get("block_ids", [])
        if ids:
            self._target_ids = {int(item) for item in ids}
        else:
            self._target_ids = {int(block.id) for block in self.host.project.blocks if not block.muted}
        self._refresh_phrase_preview()
        self._syncing = False

    def _choose_targets(self):
        dialog = TargetSelectionDialog(self.host.project, self._target_ids, self)
        if dialog.exec() == QDialog.Accepted:
            self._target_ids = set(dialog.selected_ids())
            self.refresh_blocks(self.host.project)
            self._save_settings()

    def _phrase_changed(self, *_):
        phrase = phrase_for(self.phrase_combo.currentData())
        self.duration.blockSignals(True)
        self.duration.setValue(phrase.total_beats if phrase else 16)
        self.duration.blockSignals(False)
        self._refresh_phrase_preview()
        self._save_settings()

    def _refresh_phrase_preview(self):
        phrase = phrase_with_duration(phrase_for(self.phrase_combo.currentData()), self.duration.value())
        if not phrase:
            self.description.setText("")
            self.stages.set_phrase(None)
            self.timeline.set_phrase(None)
            return
        self.description.setText(phrase.description)
        self.stages.set_phrase(phrase)
        self.timeline.set_phrase(phrase)
        self.timeline.setToolTip(f"Phrase progress across {phrase.total_beats:g} beats")

    def _save_settings(self):
        if self._syncing:
            return
        host = self.host
        settings = {
            "phrase_id": self.phrase_combo.currentData(),
            "duration_beats": float(self.duration.value()),
            "amount": self.amount.value() / 100.0,
            "block_ids": self._selected_ids(),
        }

        def save_phrase_settings():
            host.project.performance["_phrase"] = settings

        # Initial UI construction runs before the transport worker and history
        # controller exist; seed the default project synchronously in that phase.
        if not hasattr(host, "transport_worker"):
            save_phrase_settings()
            return
        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            save_phrase_settings, key=("phrase-settings",),
            notification={"dirty": True}, label="save phrase settings"
        )

    def _duration_changed(self, value):
        host = self.host
        phrase_id = self.phrase_combo.currentData()
        duration = float(value)

        def update_duration():
            state = host.engine.director.phrase
            if state.running and not state.memory.get("section_owner") and state.phrase_id == phrase_id:
                host.engine.performance.update_phrase_duration(duration)

        host.transport.enqueue_gui_command(
            update_duration, key=("phrase-duration",),
            notification={"dirty": False, "performance": True}, label="phrase duration"
        )
        self._refresh_phrase_preview()
        self.update_runtime()
        self._save_settings()

    def _selected_ids(self):
        return sorted(self._target_ids) or [b.id for b in self.host.project.blocks if not b.muted]

    def _amount_changed(self, value):
        self.amount_label.setText(f"{value}%")
        host = self.host
        amount = float(value) / 100.0

        def update_amount():
            updater = getattr(host.engine.performance, "update_phrase_amount", None)
            if updater is not None and not host.engine.director.phrase.memory.get("section_owner"):
                updater(amount)

        host.transport.enqueue_gui_command(
            update_amount, key=("phrase-amount",),
            notification={"dirty": False, "performance": True}, label="phrase amount"
        )
        self._save_settings()

    def _start(self):
        host = self.host
        ids = self._selected_ids()
        phrase_id = self.phrase_combo.currentData()
        phrase_name = self.phrase_combo.currentText()
        amount = self.amount.value() / 100.0
        duration = float(self.duration.value())
        notification = {"dirty": False, "performance": True}

        def start_phrase():
            if not host.transport.running or host.transport.playback_mode == "composition":
                host.transport.start(mode="perform")
            started = host.engine.performance.start_phrase(
                host.project, phrase_id, ids, amount, duration_beats=duration
            )
            if started:
                notification["message"] = f"Phrase: {phrase_name}"
            else:
                notification["dirty"] = False

        host.transport.enqueue_gui_command(
            start_phrase, key=("phrase-start",), notification=notification,
            label="start performance phrase"
        )
        self._save_settings()

    def _stop(self):
        host = self.host
        fallback_id = self.phrase_combo.currentData()

        def stop_phrase():
            state = host.engine.director.phrase
            if state.memory.get("section_owner"):
                return
            phrase_id = state.phrase_id if state.running and state.phrase_id else fallback_id
            host.engine.performance.stop_phrase(phrase_id)

        host.transport.enqueue_gui_command(
            stop_phrase, key=("phrase-stop",),
            notification={"dirty": False, "performance": True, "message": "Phrase stopped"},
            label="stop performance phrase"
        )

    def update_runtime(self):
        """Reflect the live PhraseState; called from the UI heartbeat."""
        state = self.host.engine.director.phrase
        running = bool(state.running and not state.memory.get("section_owner"))
        current = self.phrase_combo.currentData()
        self.stages.set_active(int(state.stage_index) if running and state.phrase_id == current else -1)
        self.timeline.set_runtime(
            self.host.engine.director.snapshot().progress if running and state.phrase_id == current else 0.0,
            int(state.stage_index) if running and state.phrase_id == current else -1,
            running and state.phrase_id == current,
        )
        text = "RESTART PHRASE" if running else "PLAY PHRASE"
        if self.start.text() != text:
            self.start.setText(text)
        if self.stop.isEnabled() != running:
            self.stop.setEnabled(running)

class PerformanceBlockCard(QFrame):
    """Compact musical-technique card used by the Perform tab."""
    selected = Signal(int)
    mute_changed = Signal(int, bool)
    mode_changed = Signal(int, str)
    def __init__(self, block, host, parent=None):
        super().__init__(parent)
        self.block_id = block.id
        self.host = host
        self.block = block
        accent = block_color(host.project, block)
        self.setObjectName("performCard")
        self.setProperty("blockType", block.block_type)
        self.apply_theme(active_theme())

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)

        left = QVBoxLayout()
        left.setSpacing(2)
        left.setAlignment(Qt.AlignTop)
        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignTop)
        lay.addLayout(left, 3)
        lay.addLayout(right, 1)

        # Header (shared identity)
        head = QHBoxLayout()
        head.setSpacing(4)
        dot = QLabel()
        dot.setFixedSize(24, 24)
        dot.setPixmap(block_type_icon(block.block_type, accent, 24).pixmap(24, 24))
        dot.setToolTip(block.block_type)
        head.addWidget(dot)
        name = QLabel(block.name)
        name.setObjectName("blockName")
        head.addWidget(name, 1)
        badge = QLabel(block.block_type)
        badge.setObjectName("performBadge")
        badge.setStyleSheet(f"background:{accent}; color:{on_color(accent)}; padding:3px 7px; border-radius:4px; font-weight:700;")
        head.addWidget(badge)
        self.midi_indicator = QLabel()
        self.midi_indicator.setFixedSize(9, 9)
        self.midi_indicator.setToolTip("MIDI activity")
        self.midi_indicator.setAccessibleName(f"{block.name} MIDI activity")
        self.midi_indicator.setObjectName("performMidi")
        self._midi_on = False
        head.addWidget(self.midi_indicator)
        left.addLayout(head)

        # Generator side
        gen_title = QLabel("GENERATOR")
        gen_title.setObjectName("muted")
        left.addWidget(gen_title)

        gen = QHBoxLayout()
        gen.addWidget(QLabel("Technique"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(140)
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        gen.addWidget(self.preset_combo, 1)
        left.addLayout(gen)

        self.description = QLabel("Choose a musical technique for this block")
        self.description.setObjectName("muted")
        self.description.setWordWrap(True)
        self.description.setToolTip("Technique description")
        self.description.setMinimumHeight(18)
        self.description.setMaximumHeight(38)
        left.addWidget(self.description)

        self.technique_curve = TechniqueCurveWidget()
        self.technique_curve.setFixedSize(140, 100)
        self.technique_curve.setToolTip("Normalized parameter movement of the selected technique")

        settings = QHBoxLayout()
        settings.setSpacing(4)
        amount_label = QLabel("Amount")
        settings.addWidget(amount_label)
        self.amount = QSlider(Qt.Horizontal)
        self.amount.setRange(0, 100)
        self.amount.setValue(100)
        self.amount.setMinimumWidth(80)
        self.amount.valueChanged.connect(self._settings_changed)
        settings.addWidget(self.amount, 1)
        self.amount_label = QLabel("100%")
        self.amount_label.setMinimumWidth(34)
        settings.addWidget(self.amount_label)
        shape_label = QLabel("Shape")
        settings.addWidget(shape_label)
        self.shape = QComboBox()
        self.shape.addItems(["in", "out", "in/out", "pulse"])
        self.shape.setMinimumWidth(72)
        self.shape.currentTextChanged.connect(self._settings_changed)
        settings.addWidget(self.shape)
        length_label = QLabel("Length")
        settings.addWidget(length_label)
        self.length = QComboBox()
        self.length.addItems(["1 beat", "2 beats", "4 beats", "8 beats", "16 beats"])
        self.length.setCurrentText("4 beats")
        self.length.setMinimumWidth(78)
        self.length.currentTextChanged.connect(self._settings_changed)
        settings.addWidget(self.length)
        left.addLayout(settings)

        self.activity = QProgressBar()
        self.activity.setRange(0, 100)
        self.activity.setTextVisible(False)
        self.activity.setFixedHeight(6)
        self.activity.setAccessibleName(f"{block.name} performance activity")
        left.addWidget(self.activity)
        self.status = QLabel("idle")
        self.status.setObjectName("muted")
        left.addWidget(self.status)

        # Musical Diagnostics (v100.1.1)
        self.diagnostics = QLabel("INPUT: Groove --  Harmony --\nOUTPUT: Motif --  Density --")
        self.diagnostics.setObjectName("muted")
        self.diagnostics.setToolTip("Live musical context diagnostics for Relations debugging")
        left.addWidget(self.diagnostics)

        # Performance side
        perf_title = QLabel("PERFORMANCE")
        perf_title.setObjectName("muted")
        right.addWidget(perf_title)
        right.addWidget(self.technique_curve, 0, Qt.AlignHCenter)

        self.enable = QPushButton("ENABLE")
        self.enable.setCheckable(True)
        self.enable.setAccessibleName(f"Enable {block.name} technique")
        self.enable.clicked.connect(self._toggle)
        actions = QHBoxLayout()
        actions.setSpacing(2)
        actions.addWidget(self.enable, 1)

        self.restart = QPushButton("RESTART")
        self.restart.setAccessibleName(f"Restart {block.name} technique")
        self.restart.clicked.connect(self._restart)
        actions.addWidget(self.restart, 1)
        right.addLayout(actions)

        self.mode_switch = ModeSwitch(block.mode)
        self.mode_switch.changed.connect(self._mode_changed)
        right.addWidget(self.mode_switch)

        self.mute_button = QPushButton("UNMUTE" if block.muted else "MUTE")
        self.mute_button.setObjectName("performMute")
        self.mute_button.setCheckable(True)
        self.mute_button.setAccessibleName(f"Mute {block.name}")
        self.mute_button.setChecked(bool(block.muted))
        self.mute_button.clicked.connect(self._mute_clicked)
        right.addWidget(self.mute_button)

        self.setMinimumWidth(520)
        self.setMaximumWidth(900)
        # Natural content height keeps rows compact without clipping wrapped
        # descriptions or stretching the gaps beside the fixed-size graph.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._restoring_settings = True
        self._load_catalog()
        self._restore_performance_state()
        self._restoring_settings = False
        bind_attributes(self, "perform", {"preset_combo": "preset", "amount": "amount", "shape": "shape", "length": "length"})

    def _mode_changed(self, mode):
        mode = "LIVE" if mode == "LIVE" else "SEQ"
        if self.block.mode == mode:
            return
        self.block.mode = mode
        self.mode_changed.emit(self.block_id, mode)

    def _mute_clicked(self, checked):
        self.block.muted = bool(checked)
        # setText("MUTED" if checked else "MUTE") was ambiguous; use action labels.
        self.mute_button.setText("UNMUTE" if checked else "MUTE")
        self.mute_changed.emit(self.block_id, bool(checked))

    def _restore_performance_state(self):
        state = self.host.project.performance.get(str(self.block_id), {}) if hasattr(self.host.project, "performance") else {}
        pid = state.get("preset_id")
        if pid:
            idx = self.preset_combo.findData(pid)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)
        amount = state.get("amount")
        if amount is not None:
            self.amount.setValue(max(0, min(100, int(round(float(amount) * 100)))))
        shape = state.get("shape")
        if shape in ("in", "out", "in_out", "in/out", "pulse"):
            self.shape.setCurrentText("in/out" if shape == "in_out" else shape)
        beats = state.get("beats")
        if beats in (1, 2, 4, 8, 16):
            self.length.setCurrentText(f"{int(beats)} beat" if int(beats) == 1 else f"{int(beats)} beats")
        # Loading/rebuilding a card restores choices, never starts a gesture.
        # The runtime is the authority for the button's active state.
        running = self.host.engine.performance.active.get(self.block_id)
        enabled = running is not None and getattr(running, "phrase_id", None) is None and not running.owner_section
        self.enable.blockSignals(True)
        self.enable.setChecked(enabled)
        self.enable.setText("DISABLE" if enabled else "ENABLE")
        self.enable.blockSignals(False)

    def _load_catalog(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for preset in presets_for_entity(self.block):
            self.preset_combo.addItem(preset.name, preset.id)
        self.preset_combo.blockSignals(False)
        self._preset_changed(self.preset_combo.currentIndex())

    def _preset_changed(self, _index):
        preset = preset_for_entity(self.block, self.preset_combo.currentData())
        if not preset:
            return
        description = preset.description
        self.description.setText(description)
        self.description.setToolTip(description)
        self.technique_curve.set_technique(preset, self.amount.value() / 100.0, self._shape_value())
        self.technique_curve.setToolTip(f"{preset.name}: normalized parameter curves")
        default_shape = "in/out" if preset.default_shape == "in_out" else preset.default_shape
        self.shape.blockSignals(True)
        self.shape.setCurrentText(default_shape)
        self.shape.blockSignals(False)
        options = {1: "1 beat", 2: "2 beats", 4: "4 beats", 8: "8 beats", 16: "16 beats"}
        self.length.blockSignals(True)
        self.length.setCurrentText(options.get(int(preset.default_beats), "4 beats"))
        self.length.blockSignals(False)

    def _beats(self):
        return float(self.length.currentText().split()[0])

    def _shape_value(self):
        return "in_out" if self.shape.currentText() == "in/out" else self.shape.currentText()

    def _save_performance_state(self, enabled=None):
        if getattr(self, "_restoring_settings", False): return
        host = self.host
        block_id = int(self.block_id)
        state_data = {
            "preset_id": self.preset_combo.currentData(),
            "amount": self.amount.value() / 100.0,
            "shape": self._shape_value(),
            "beats": self._beats(),
            "enabled": bool(self.enable.isChecked() if enabled is None else enabled),
        }

        def save_state():
            host.project.performance[str(block_id)] = state_data

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            save_state, key=("performance-settings", block_id),
            notification={"dirty": True, "performance": True},
            label=f"save performance settings {block_id}"
        )

    def _settings_changed(self, *_):
        self.amount_label.setText(f"{self.amount.value()}%")
        preset = preset_for_entity(self.block, self.preset_combo.currentData())
        if preset:
            self.technique_curve.set_technique(preset, self.amount.value() / 100.0, self._shape_value())
        if getattr(self, "_restoring_settings", False): return
        host = self.host
        block_id = int(self.block_id)
        amount = self.amount.value() / 100.0
        shape = self._shape_value()
        beats = self._beats()

        def update_active():
            state = host.engine.performance.active.get(block_id)
            if state and not state.owner_section:
                state.amount = amount
                state.shape = shape
                state.beats = beats

        host.transport.enqueue_gui_command(
            update_active, key=("performance-active-settings", block_id),
            notification={"dirty": False, "performance": True},
            label=f"update performance gesture {block_id}"
        )
        self._save_performance_state()

    def _toggle(self, checked):
        if checked:
            self._restart()
        else:
            host = self.host
            block_id = int(self.block_id)
            host.transport.enqueue_gui_command(
                lambda: host.engine.performance.stop(block_id),
                key=("performance-stop", block_id),
                notification={"dirty": False, "performance": True},
                label=f"stop performance {block_id}"
            )
            self.status.setText("idle")
            self.enable.setText("ENABLE")
            self._save_performance_state(False)

    def _restart(self):
        host = self.host
        block = self.block
        block_id = int(self.block_id)
        preset_id = self.preset_combo.currentData()
        amount = self.amount.value() / 100.0
        shape = self._shape_value()
        beats = self._beats()
        if not preset_id:
            self.enable.blockSignals(True)
            self.enable.setChecked(False)
            self.enable.setText("ENABLE")
            self.enable.blockSignals(False)
            self._save_performance_state(False)
            return
        notification = {"dirty": False, "performance": True}

        def start_performance():
            if preset_id and (not host.transport.running or host.transport.playback_mode == "composition"):
                host.transport.start(mode="perform")
            ok = bool(preset_id and host.engine.performance.start(block, preset_id, amount, shape, beats))
            if not ok:
                notification["message"] = "Performance preset could not be started"

        host.transport.enqueue_gui_command(
            start_performance, key=("performance-start", block_id),
            notification=notification, label=f"start performance {block_id}"
        )
        self._save_performance_state(True)

    def set_activity(self, value, active):
        self.activity.setValue(max(0, min(100, int(value * 100))))
        midi_on = bool(active) and not bool(self.block.muted)
        if midi_on != self._midi_on:
            # Restyle only on transitions; this runs on every UI heartbeat.
            self._midi_on = midi_on
            self.midi_indicator.setProperty("active", midi_on)
            repolish(self.midi_indicator)
        state = self.host.engine.performance.active.get(self.block_id)
        if state:
            progress = min(1.0, state.elapsed_beats / max(.25, state.beats))
            self._set_status(f"{state.preset_id} · {int(progress * 100)}%")
        else:
            if self.enable.isChecked():
                # The gesture ended in the runtime.  The button used to stay ON
                # (and stay "enabled" in the project), so every card rebuild
                # restarted the gesture and parameters jumped.
                self.enable.blockSignals(True)
                self.enable.setChecked(False)
                self.enable.setText("ENABLE")
                self.enable.blockSignals(False)
                self._save_performance_state(False)
            if not active:
                self._set_status("idle")

    def _set_status(self, text):
        if self.status.text() != text:
            self.status.setText(text)

    def update_diagnostics(self, project, engine):
        """Live relation context (this label used to be a static placeholder)."""
        role = str(self.block.block_type).upper()
        blocks = list(project.blocks)

        def first(kind):
            return next((b for b in blocks if str(b.block_type).upper() == kind), None)

        p = self.block.parameters
        if role == "BASS":
            src = engine.role_relation_source(self.block)
            line = (f"Groove ← {src.name} · mask {float(p.get('groove_follow', .7)):.2f} · accent {float(p.get('groove_accent', .65)):.2f}"
                    if src else "Groove: no DRUM block")
        elif role == "MELODY":
            src = engine.role_relation_source(self.block)
            line = (f"Harmony ← {src.name} · anchor {float(p.get('harmony_anchor', .55)):.2f}"
                    if src else "Harmony: no CHORD block")
        elif role in ("DRUM", "CHORD"):
            target = "BASS" if role == "DRUM" else "MELODY"
            label = "Groove" if role == "DRUM" else "Harmony"
            n = sum(1 for b in blocks if str(b.block_type).upper() == target and engine.role_relation_source(b) is self.block)
            line = f"{label} → {n} {target} block{'s' if n != 1 else ''}" if n else f"{label}: not used by any {target} block"
        else:
            line = "No built-in role relation"
        rels_in = sum(1 for r in project.relations if getattr(r, "enabled", True) and r.destination_block == self.block_id)
        rels_out = sum(1 for r in project.relations if getattr(r, "enabled", True) and r.source_block == self.block_id)
        rhythm = self.block.outputs.get("rhythm") or []
        density = (sum(1 for v in rhythm if v > 0) / len(rhythm)) if rhythm else 0.0
        active_motif = engine.active_motif(self.block)
        motif = active_motif.name if active_motif is not None else "—"
        with self.host.transport._transport_lock:
            route = engine.dialogue_runtime.route_for(self.block)
            if route is not None:
                relation = route['relation']
                state = engine.dialogue_runtime.status(relation, engine.clock.position_beats)
                source = self.block.id == relation.source_block
                partner_id = relation.destination_block if source else relation.source_block
                partner = next((b.name for b in blocks if b.id == partner_id), '?')
                turn = ('Calling' if source else 'Waiting') if state['phase'] == 'Call' else (
                    ('Waiting' if source else 'Responding') if state['phase'] == 'Response' else 'Pause')
                line = f"Dialogue ↔ {partner} · {turn} · {state['remaining']:.1f} beats" if state['active'] else f"Dialogue · {state['reason']}"
        text = f"{line}\nRelations in {rels_in} · out {rels_out} · Motif {motif} · Density {density:.2f}"
        if self.diagnostics.text() != text:
            self.diagnostics.setText(text)

    def apply_theme(self, theme):
        accent = block_color(self.host.project, self.block)
        # Preserve the card and its controls while updating its local style.
        self.setStyleSheet(
            f"QFrame#performCard {{ border:1px solid {theme_mix(accent, theme.border, .45)}; border-left:4px solid {accent}; border-radius:7px; background:{theme.card}; }}"
            f"QFrame#performCard[selected=\"true\"] {{ border:2px solid {theme.accent}; border-left:4px solid {accent}; }}"
        )

    def set_selected(self, selected):
        if bool(self.property("selected")) == bool(selected):
            return
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.block_id)
        super().mousePressEvent(event)


class MacroRouteDialog(QDialog):
    """Explicit editor for one macro -> block parameter route."""
    def __init__(self, host, macro_index, parent=None):
        super().__init__(parent)
        self.host = host
        self.macro_index = macro_index
        self.setWindowTitle(f"Macro {macro_index + 1} route")
        self.resize(430, 330)

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.block_combo = QComboBox()
        for b in host.project.blocks:
            self.block_combo.addItem(f"{b.name}  [{b.block_type}]", b.id)
        form.addRow("Target block", self.block_combo)

        self.parameter_combo = QComboBox()
        form.addRow("Parameter", self.parameter_combo)
        lay.addLayout(form)

        self.min_value = ContrastDoubleSpinBox(); self.min_value.setDecimals(3); self.min_value.setSingleStep(0.01)
        self.max_value = ContrastDoubleSpinBox(); self.max_value.setDecimals(3); self.max_value.setSingleStep(0.01)
        self.amount = ContrastDoubleSpinBox(); self.amount.setDecimals(2); self.amount.setRange(0.0, 1.0); self.amount.setSingleStep(0.05); self.amount.setValue(1.0)
        self.curve = ContrastDoubleSpinBox(); self.curve.setDecimals(2); self.curve.setRange(0.1, 8.0); self.curve.setSingleStep(0.1); self.curve.setValue(1.0)
        form.addRow("Minimum", self.min_value)
        form.addRow("Maximum", self.max_value)
        form.addRow("Amount", self.amount)
        form.addRow("Curve", self.curve)
        bind_attributes(self, "macro_route")

        self.info = QLabel("The macro value 0..1 is mapped into Minimum..Maximum.")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self.block_combo.currentIndexChanged.connect(self._block_changed)
        self.parameter_combo.currentIndexChanged.connect(self._parameter_changed)
        self._block_changed()

    def _current_block(self):
        bid = self.block_combo.currentData()
        return self.host.get_block(bid) if bid is not None else None

    def _block_changed(self, *_):
        block = self._current_block()
        self.parameter_combo.blockSignals(True)
        self.parameter_combo.clear()
        if block is not None:
            catalog = self.host.engine.parameter_catalog(block)
            for key in sorted(catalog):
                if key in NON_NUMERIC_PARAMETERS:
                    continue
                self.parameter_combo.addItem(key.replace('_', ' '), key)
        self.parameter_combo.blockSignals(False)
        self._parameter_changed()

    def _parameter_changed(self, *_):
        block = self._current_block()
        key = self.parameter_combo.currentData()
        if block is None or not key:
            return
        catalog = self.host.engine.parameter_catalog(block)
        if key not in catalog:
            return
        default, lo, hi = catalog[key]
        self.min_value.setRange(lo, hi); self.max_value.setRange(lo, hi)
        self.min_value.setValue(lo); self.max_value.setValue(hi)

    def route(self):
        return {
            "block_id": int(self.block_combo.currentData()),
            "parameter": str(self.parameter_combo.currentData()),
            "min": float(self.min_value.value()),
            "max": float(self.max_value.value()),
            "amount": float(self.amount.value()),
            "curve": float(self.curve.value()),
        }


class MacroPanel(QGroupBox):
    def __init__(self, host, parent=None):
        super().__init__("MACROS", parent)
        self.host = host
        self.sliders = []
        if not host.project.macros:
            host.project.macros = [{"name": f"MACRO {i+1}", "value": .5, "routes": []} for i in range(4)]
        self._build()

    def _build(self):
        lay = QGridLayout(self)
        lay.setContentsMargins(7, 5, 7, 5)
        lay.setHorizontalSpacing(8)
        lay.setVerticalSpacing(4)
        for i, macro in enumerate(self.host.project.macros[:4]):
            label = QLabel(str(macro.get("name", f"MACRO {i+1}")))
            slider = ParamSlider(float(macro.get("value", .5)), default=.5)
            bind_help(slider, "value", "macro_route")
            slider.changed.connect(lambda v, i=i: self._changed(i, v))
            self.sliders.append(slider)
            lay.addWidget(label, i, 0)
            lay.addWidget(slider, i, 1)

            add = QPushButton("+ route")
            add.setToolTip("Add a macro route to a block parameter")
            add.clicked.connect(lambda _=False, i=i: self._add_route(i))
            lay.addWidget(add, i, 2)

            routes = macro.get("routes", []) or []
            if routes:
                route_box = QVBoxLayout()
                for ri, route in enumerate(routes):
                    b = self.host.get_block(route.get("block_id"))
                    target = f"{b.name}.{route.get('parameter')}" if b else f"block {route.get('block_id')}.{route.get('parameter')}"
                    lo = float(route.get("min", 0.0)); hi = float(route.get("max", 1.0))
                    text = QLabel(f"→ {target} [{lo:.2f}..{hi:.2f}]")
                    remove = QPushButton("×")
                    remove.setFixedWidth(24)
                    remove.setToolTip("Remove route")
                    remove.clicked.connect(lambda _=False, i=i, ri=ri: self._remove_route(i, ri))
                    row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.addWidget(text, 1); row.addWidget(remove)
                    route_box.addLayout(row)
                lay.addLayout(route_box, i, 3)

    def _changed(self, i, value):
        self.host.project.macros[i]["value"] = float(value)
        self.host.engine.apply_macros()
        self.host._mark_dirty()
        self.host._queue_inspector_refresh()

    def _add_route(self, i):
        if not self.host.project.blocks:
            self.host.set_message("Add a block before creating a macro route")
            return
        dialog = MacroRouteDialog(self.host, i, self)
        if dialog.exec() != QDialog.Accepted:
            return
        route = dialog.route()
        self.host.project.macros[i].setdefault("routes", []).append(route)
        self.host.engine.apply_macros()
        self.host._mark_dirty()
        b = self.host.get_block(route["block_id"])
        target = f"{b.name}.{route['parameter']}" if b else route["parameter"]
        self.host.set_message(f"{self.host.project.macros[i].get('name', f'MACRO {i+1}')} → {target}")
        self.host._queue_inspector_refresh()
        self.host.performance.rebuild_macro_panel()

    def _remove_route(self, i, route_index):
        routes = self.host.project.macros[i].setdefault("routes", [])
        if 0 <= route_index < len(routes):
            routes.pop(route_index)
            self.host.engine.apply_macros()
            self.host._mark_dirty()
            self.host.set_message("Macro route removed")
            self.host._queue_inspector_refresh()
            self.host.performance.rebuild_macro_panel()


class GlobalMacroBar(QFrame):
    """Always-visible global Director controls shared with Perform."""
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.sliders = []
        self.values = []
        self.labels = []
        self.cards = []
        self.setObjectName("globalMacroBar")
        self.setAccessibleName("Global macros")
        self.setToolTip("Global Director controls: Energy, Tension, Density and Variation")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)
        title = QLabel("GLOBAL")
        title.setObjectName("muted")
        title.setToolTip("Global musical character")
        layout.addWidget(title)
        for index, (default_name, control) in enumerate(GLOBAL_MACRO_DEFS):
            card = QFrame()
            card.setObjectName("globalMacroCard")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            row = QHBoxLayout(card)
            row.setContentsMargins(9, 7, 9, 7)
            row.setSpacing(5)
            name = ParameterSourceLabel(default_name, binding=(None, control))
            name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            name.setFixedWidth(68)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            # Let the four header controls share the available width.  A
            # fixed 150 px slider left unused space on wide windows and made
            # the header crowd itself at the minimum window width.
            slider.setMinimumWidth(48)
            slider.setMinimumHeight(26)
            slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            slider.setAccessibleName(f"Global {default_name}")
            bind_help(slider, control, "macro")
            bind_help(name, control, "macro")
            slider.setContextMenuPolicy(Qt.CustomContextMenu)
            slider.customContextMenuRequested.connect(
                lambda pos, i=index, w=slider: self._macro_context_menu(i, w.mapToGlobal(pos)))
            value = QLabel("0%")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            # Reserve the full 100% width so dragging never shifts the track.
            value.setFixedWidth(34)
            row.addWidget(name)
            row.addWidget(slider, 1)
            row.addWidget(value)
            layout.addWidget(card, 1)
            self.cards.append(card)
            self.labels.append(name)
            self.sliders.append(slider)
            self.values.append(value)
            slider.valueChanged.connect(lambda raw, i=index: self._changed(i, raw))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.apply_theme(active_theme())
        self.refresh_from_project()

    def _macro_context_menu(self, index, global_pos):
        menu = QMenu(self)
        menu.addAction("MIDI Learn this macro…")
        chosen = menu.exec(global_pos)
        if chosen is not None:
            macro = self.host.project.macros[index]
            self.host._arm_midi_learn({"kind": "global_macro", "macro_index": index,
                                       "min": 0.0, "max": 1.0,
                                       "initial": float(macro.get("value", .5))})
        menu.deleteLater()

    def apply_theme(self, theme):
        for index, color in enumerate(GLOBAL_MACRO_COLORS):
            ink = theme_mix(color, theme.text, .35) if is_light_theme(theme) else color
            self.cards[index].setStyleSheet(
                f"QFrame#globalMacroCard {{ background:{theme_mix(theme.card, color, .06)}; "
                f"border:1px solid {theme_mix(theme.border, color, .45)}; border-radius:7px; }}"
            )
            for label in (self.labels[index], self.values[index]):
                label.setStyleSheet(f"color:{ink}; font-size:11px; font-weight:600;")
            self.sliders[index].setStyleSheet(
                "QSlider { background:transparent; }"
                f"QSlider::groove:horizontal {{ height:6px; background:{theme_mix(theme.border, color, .35)}; border-radius:3px; }}"
                f"QSlider::sub-page:horizontal {{ background:{color}; border-radius:3px; }}"
                f"QSlider::add-page:horizontal {{ background:{theme.input}; border-radius:3px; }}"
                f"QSlider::handle:horizontal {{ background:{color}; border:1px solid {ink}; width:14px; margin:-5px 0; border-radius:7px; }}"
                f"QSlider::handle:horizontal:hover {{ background:{theme.text}; }}"
            )

    def _changed(self, index, raw):
        self.values[index].setText(f"{int(raw)}%")
        self.host._set_global_macro(index, float(raw) / 100.0, self)

    def refresh_from_project(self):
        macros = ensure_global_macros(self.host.project)
        for index, (default_name, _control) in enumerate(GLOBAL_MACRO_DEFS):
            macro = macros[index]
            name = str(macro.get("name") or default_name)
            value = max(0, min(100, int(round(float(macro.get("value", .5)) * 100))))
            label = self.labels[index]
            label.setText(label.fontMetrics().elidedText(name, Qt.ElideRight, label.width()))
            label.setAccessibleName(name)
            bind_help(label, _control, "macro", extra=f"Global {name}")
            self.sliders[index].setAccessibleName(f"Global {name}")
            self.sliders[index].blockSignals(True)
            self.sliders[index].setValue(value)
            self.sliders[index].blockSignals(False)
            self.values[index].setText(f"{value}%")

class DirectorControlPanel(QGroupBox):
    """Musical Director controls plus live multidimensional runtime monitor."""
    CURVES = {
        "Gentle rise": "gentle_rise",
        "Crescendo": "crescendo",
        "Peak and release": "peak_release",
    }
    def __init__(self, host, parent=None):
        super().__init__("MUSICAL DIRECTOR", parent)
        self.host=host
        self._control_update_queued = False
        lay=QVBoxLayout(self)
        control=QGridLayout()
        self.curve=QComboBox()
        self.curve.addItems(["Gentle rise","Crescendo","Peak and release","Custom"])
        self.curve.setAccessibleName("Director phrase curve")
        self.curve.setToolTip("Choose a phrase tension trajectory; Custom keeps the loaded trajectory")
        control.addWidget(QLabel("Phrase Curve"),0,0)
        control.addWidget(self.curve,0,1,1,5)
        self.controls={}
        self.control_values={}
        names=("Smoothing","Energy Influence","Density Influence","Register Influence","Probability Influence","Voice Smooth")
        defaults=(60,60,60,60,60,60)
        for col,(name,default) in enumerate(zip(names,defaults)):
            w=QSlider(Qt.Horizontal); w.setRange(0,100); w.setValue(default)
            w.setAccessibleName(name)
            w.setToolTip(f"{name}: {default}%")
            self.controls[name]=w
            control.addWidget(QLabel(name),1,col)
            control.addWidget(w,2,col)
            value_label = QLabel(f"{default}%")
            value_label.setObjectName("knobValue")
            value_label.setAlignment(Qt.AlignCenter)
            self.control_values[name] = value_label
            control.addWidget(value_label,3,col)
            w.valueChanged.connect(lambda value, n=name: self._control_changed(n,value))
        lay.addLayout(control)

        monitor=QGridLayout()
        self.meters={}
        for col,name in enumerate(("Tension","Energy","Density","Register","Probability","Duration","Variation")):
            lab=QLabel(name+": --")
            lab.setObjectName("directorMeter")
            lab.setAlignment(Qt.AlignCenter)
            self.meters[name]=lab
            monitor.addWidget(lab,0,col)
        self.state=QLabel("Director idle")
        self.state.setObjectName("muted")
        monitor.addWidget(self.state,1,0,1,7)
        lay.addLayout(monitor)
        self.curve.currentTextChanged.connect(self._curve_changed)
        bind_help(self.curve, "curve", "director")
        bind_controls(self.controls, "director")

    def _control_changed(self, name, value):
        d=getattr(self.host.engine,"director",None)
        if d is None: return
        d.set_control(name,float(value)/100.0)
        if name in self.control_values:
            self.control_values[name].setText(f"{int(value)}%")
            bind_help(self.controls[name], name, "director")
        if name=="Voice Smooth":
            # MusicDirector owns the persisted value; synchronize the runtime
            # solver instead of maintaining a second independently-set value.
            self.host.engine.sync_voice_leading_settings()
        if not self._control_update_queued:
            self._control_update_queued = True
            QTimer.singleShot(35, self, self._flush_control_update)

    def _flush_control_update(self):
        self._control_update_queued = False
        self._save_state()
        if hasattr(self.host, "_mark_dirty"):
            self.host._mark_dirty()
        self.host.engine.generate()
        self.refresh()

    def _curve_changed(self, text):
        d=getattr(self.host.engine,"director",None)
        key=self.CURVES.get(str(text))
        if d is not None and key:
            total=float(getattr(d.phrase,"memory",{}).get("total_beats",16.0) or 16.0)
            d.set_curve_preset(key,total)
            if hasattr(self.host, "_mark_dirty"):
                self.host._mark_dirty()
        elif d is not None and str(text) == "Custom":
            # Custom is intentionally a stable loaded curve, rather than a
            # silent no-op that resets the phrase on project load.
            self._save_state()
        self.refresh()

    def _save_state(self):
        performance = getattr(self.host.project, "performance", None)
        if performance is None:
            return
        performance["_director"] = {
            "curve": self.curve.currentText(),
            "controls": {name: int(slider.value()) for name, slider in self.controls.items()},
        }

    def apply_to_engine(self):
        """Push the panel's slider values into a (new) engine/director.

        After Open project the engine was recreated with defaults while the
        sliders kept their positions, so the UI no longer matched the sound.
        """
        if getattr(self.host, "_installing_project", False):
            # Project restore is a synchronization step, not a user edit.
            # Calling _control_changed here would schedule a delayed save
            # callback that ran after _install_project() cleared its guard and
            # marked a freshly opened project dirty.
            director = getattr(self.host.engine, "director", None)
            if director is not None:
                for name, slider in self.controls.items():
                    director.set_control(name, float(slider.value()) / 100.0)
                smooth = self.controls.get("Voice Smooth")
                if smooth is not None:
                    director.set_control("Voice Smooth", float(smooth.value()) / 100.0)
                    self.host.engine.sync_voice_leading_settings()
            self._curve_changed(self.curve.currentText())
            self.refresh()
            return
        for name, slider in self.controls.items():
            self._control_changed(name, slider.value())
        self._curve_changed(self.curve.currentText())

    def sync_from_project(self):
        state = getattr(self.host.project, "performance", {}).get("_director", {})
        controls = state.get("controls", {}) if isinstance(state, dict) else {}
        for name, slider in self.controls.items():
            value = controls.get(name, slider.value())
            slider.blockSignals(True)
            slider.setValue(max(0, min(100, int(value))))
            slider.blockSignals(False)
            self.control_values[name].setText(f"{slider.value()}%")
        curve = state.get("curve") if isinstance(state, dict) else None
        if curve and self.curve.findText(curve) >= 0:
            self.curve.blockSignals(True)
            self.curve.setCurrentText(curve)
            self.curve.blockSignals(False)

    def refresh(self):
        d=getattr(self.host.engine,"director",None)
        if d is None: return
        snap=d.snapshot()
        self.meters["Tension"].setText(f"Tension: {snap.tension:.2f}")
        self.meters["Energy"].setText(f"Energy: {snap.energy:.2f}")
        self.meters["Density"].setText(f"Density: {snap.density:.2f}")
        self.meters["Register"].setText(f"Register: {snap.register_shift:+.1f}")
        self.meters["Probability"].setText(f"Probability: {snap.probability:.2f}")
        self.meters["Duration"].setText(f"Duration: ×{snap.duration_factor:.2f}")
        self.meters["Variation"].setText(f"Variation: {snap.variation:.2f}")
        if d.phrase.running:
            pct=int(round(snap.progress*100))
            stage=max(0,int(getattr(d.phrase,"stage_index",-1)))+1
            self.state.setText(f"{d.phrase.name or d.phrase.phrase_id} · Stage {stage} · {pct}% · Motifs {len(d.phrase.active_motifs)}")
        else:
            self.state.setText(f"Director idle · Motifs {len(d.motifs.motifs)}")


class PerformancePanel(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.cards = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("PERFORMANCE DIRECTOR")
        title.setObjectName("pageTitle")
        head.addWidget(title)
        head.addStretch()
        subtitle = QLabel("Phrase-based macro control")
        subtitle.setObjectName("muted")
        head.addWidget(subtitle)
        lay.addLayout(head)

        self.phrase_panel = PhrasePanel(self.host)
        self.phrase_panel.setTitle("")
        self.phrase_section = PerformSection("GLOBAL PHRASE", self.phrase_panel, expanded=True)
        lay.addWidget(self.phrase_section)

        self.harmonic_panel = HarmonicPlanPanel(self.host)
        self.harmonic_section = PerformSection("HARMONIC PLAN", self.harmonic_panel, expanded=True)
        lay.addWidget(self.harmonic_section)

        # Global macros are intentionally shown once in the window header.
        # Keep the attribute for callers that refresh legacy route panels.
        self.macro_panel = None
        self.macro_section = None

        self.director_panel = DirectorControlPanel(self.host)
        self.director_panel.setTitle("")
        self.director_section = PerformSection("MUSICAL DIRECTOR", self.director_panel, expanded=False)
        lay.addWidget(self.director_section)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self._grid_columns = 1
        self.scroll.setWidget(self.container)
        lay.addWidget(self.scroll, 1)
        self.scroll.viewport().installEventFilter(self)
        # A vertical scrollbar changes the usable viewport width after layout.
        # Reflow once more on that geometry change instead of waiting until a
        # card has already been clipped.
        self.scroll.verticalScrollBar().rangeChanged.connect(
            lambda *_: QTimer.singleShot(0, self, self._relayout_cards))

    def rebuild_macro_panel(self):
        if hasattr(self.host, "global_macro_bar"):
            self.host.global_macro_bar.refresh_from_project()

    def sync_block(self, block):
        """Update one card's mute/mode controls in place (no rebuild)."""
        card = self.cards.get(block.id)
        if card is None:
            return
        card.block = block
        card.mute_button.blockSignals(True)
        card.mute_button.setChecked(bool(block.muted))
        card.mute_button.setText("UNMUTE" if block.muted else "MUTE")
        card.mute_button.blockSignals(False)
        card.mode_switch.set_mode(block.mode)

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() == QEvent.Resize:
            self._relayout_cards()
        return super().eventFilter(obj, event)

    def _column_count(self):
        # Base reflow on the *real card requirement*, not an optimistic 320px.
        # The approved two-column card (Generator | Performance) needs roughly
        # 455px including grid spacing. Reflow before the next card can cross
        # the viewport edge.
        width=max(1,self.scroll.viewport().width())
        margins=self.grid.contentsMargins()
        available=max(1,width-margins.left()-margins.right())
        spacing=max(0,self.grid.horizontalSpacing())
        cards=list(self.cards.values())
        card_min=max([455] + [max(455,c.minimumSizeHint().width()) for c in cards])
        return max(1,min(4,(available+spacing)//(card_min+spacing)))

    def _relayout_cards(self):
        columns = self._column_count()
        # Reflow immediately on viewport resize, before Qt can clip cards.
        if columns == self._grid_columns and self.grid.count() == len(self.cards):
            return
        self._grid_columns = columns
        for index, card in enumerate(self.cards.values()):
            self.grid.removeWidget(card)
            self.grid.addWidget(card, index // columns, index % columns)
        for col in range(4):
            self.grid.setColumnStretch(col, 1 if col < columns else 0)
        rows = max(1, (len(self.cards) + columns - 1) // columns)
        for row in range(rows + 8):
            self.grid.setRowStretch(row, 1 if row == rows else 0)

    def _clear(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                # Hide now: deleteLater() runs later, and until then the old
                # card was painted underneath the rebuilt grid.
                w.hide()
                w.deleteLater()
        self.cards = {}

    def refresh_blocks(self, project, preserve=False):
        self.phrase_panel.refresh_blocks(project)
        if hasattr(self.host, "global_macro_bar"):
            self.host.global_macro_bar.refresh_from_project()
        previous = dict(self.cards)
        cards = {}
        for b in project.blocks:
            signature = (id(b), b.name, b.block_type, b.algorithm, getattr(b, "color", ""), bool(b.parameters.get("kit_coordinated")))
            card = previous.pop(b.id, None)
            if card is not None and getattr(card, "_render_signature", None) != signature:
                self.grid.removeWidget(card); card.hide(); card.deleteLater(); card = None
            if card is None:
                card = PerformanceBlockCard(b, self.host)
                card._render_signature = signature
                card.selected.connect(self.host.select_block)
                card.mute_changed.connect(self.host._card_mute_changed)
                card.mode_changed.connect(self.host._card_mode_changed)
            card.set_selected(b.id == self.host.selected_block_id)
            cards[b.id] = card
        for card in previous.values():
            self.grid.removeWidget(card); card.hide(); card.deleteLater()
        changed = list(self.cards.items()) != list(cards.items())
        self.cards = cards
        if changed:
            self._grid_columns = 0
        for b in project.blocks:
            self.sync_block(b)
        self._relayout_cards()
        panel = getattr(self.host, "composition_panel", None)
        if panel is not None and hasattr(panel, "instrument_grid"):
            panel.instrument_grid.refresh()

    def update_activity(self, project, running):
        # The monitor follows the same UI heartbeat as MIDI activity, so it
        # reflects the actual PhraseState rather than only user interaction.
        self.director_panel.refresh()
        self.phrase_panel.update_runtime()
        for b in project.blocks:
            card = self.cards.get(b.id)
            if not card:
                continue
            card.update_diagnostics(project, self.host.engine)
            values = b.outputs.get('density') or b.outputs.get('rhythm') or []
            if str(b.mode).upper() == "LIVE":
                history = self.host._generated_live_events.get(int(b.id), [])
                if history:
                    v = float(history[-1][2])
                    card.set_activity(v, running and v > 0.01)
                else:
                    card.set_activity(0, False)
            elif values:
                idx = (self.host.transport.seq_index.get(b.id, 0) - 1) % len(values)
                v = float(values[idx])
                card.set_activity(abs(v), running and abs(v) > 0.01)
            else:
                card.set_activity(0, False)


class BlockCard(QFrame):
    """Compact block module used in the BLOCKS view.

    Layout intentionally follows a small, information-dense module:
    index/name + mute/menu on top, type + SEQ/LIVE on the second row,
    algorithm and MIDI channel below. Editing actions live in the ⋮ menu
    so the card itself stays visually quiet.
    """
    selected = Signal(int)
    delete_requested = Signal(int)
    mode_changed = Signal(int, str)
    type_changed = Signal(int, str)
    color_changed = Signal(int, str)
    rename_requested = Signal(int)
    mute_changed = Signal(int, bool)

    def __init__(self, block: Block, parent=None):
        super().__init__(parent)
        self.block_id = block.id
        self._accent_color = getattr(block, "color", "") or DEFAULT_BLOCK_COLORS.get(block.block_type, "#7f8c99")
        self.setObjectName("blockCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("blockType", block.block_type)
        self.setProperty("muted", bool(block.muted))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 5, 7, 5)
        layout.setSpacing(2)

        # Header: numbered badge, name, mute and compact overflow menu.
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(5)

        self.index_badge = QLabel(str(block.id))
        self.index_badge.setObjectName("blockIndex")
        self.index_badge.setAlignment(Qt.AlignCenter)
        self.index_badge.setFixedSize(DENSE_HEIGHT, DENSE_HEIGHT)
        top.addWidget(self.index_badge, 0, Qt.AlignVCenter)

        self.name_label = QLabel(block.name)
        self.name_label.setObjectName("blockName")
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(self.name_label, 1, Qt.AlignVCenter)


        self.midi_indicator = QLabel()
        self.midi_indicator.setObjectName("midiSendIndicator")
        self.midi_indicator.setFixedSize(7, 7)
        self.midi_indicator.setToolTip("MIDI activity")
        top.addWidget(self.midi_indicator, 0, Qt.AlignVCenter | Qt.AlignRight)

        self.mute_button = QPushButton("M")
        self.mute_button.setObjectName("blockMute")
        self.mute_button.setCheckable(True)
        self.mute_button.setChecked(bool(block.muted))
        self.mute_button.setFixedSize(DENSE_HEIGHT, DENSE_HEIGHT)
        self.mute_button.setToolTip("Mute block")
        self.mute_button.setFocusPolicy(Qt.NoFocus)
        self.mute_button.setStyleSheet(block_mute_stylesheet())
        self.mute_button.clicked.connect(self._mute_clicked)
        top.addWidget(self.mute_button, 0, Qt.AlignVCenter)

        self.menu_button = QPushButton("⋮")
        self.menu_button.setObjectName("cardMenu")
        self.menu_button.setFixedSize(DENSE_HEIGHT, DENSE_HEIGHT)
        self.menu_button.setToolTip("Block options")
        self.menu_button.setFocusPolicy(Qt.NoFocus)
        self.menu_button.clicked.connect(self._show_menu)
        top.addWidget(self.menu_button, 0, Qt.AlignVCenter)
        layout.addLayout(top)

        # Type + transport mode. Type is display-only here; editing is in ⋮.
        type_row = QHBoxLayout()
        type_row.setContentsMargins(0, 0, 0, 0)
        type_row.setSpacing(6)
        self.type_icon = QLabel()
        self.type_icon.setFixedSize(DENSE_HEIGHT, DENSE_HEIGHT)
        type_row.addWidget(self.type_icon)
        self.type_label = QLabel(block.block_type)
        self.type_label.setObjectName("blockMeta")
        type_row.addWidget(self.type_label, 1, Qt.AlignVCenter)
        self.mode = ModeSwitch(block.mode)
        self.mode.changed.connect(self._mode_changed)
        type_row.addWidget(self.mode, 0, Qt.AlignVCenter)
        layout.addLayout(type_row)

        metadata = QHBoxLayout()
        metadata.setSpacing(5)
        self.algorithm_label = QLabel(block.algorithm)
        self.algorithm_label.setObjectName("blockMeta")
        self.algorithm_label.setMinimumWidth(0)
        self.algorithm_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.algorithm_label.setToolTip(f"Algorithm: {block.algorithm}")
        metadata.addWidget(self.algorithm_label, 1)

        self.midi_label = QLabel(f"CH {int(block.midi_channel)}")
        self.midi_label.setObjectName("blockMeta")
        self.midi_label.setToolTip("MIDI output channel")
        metadata.addWidget(self.midi_label)
        layout.addLayout(metadata)

        self.setFixedHeight(CARD_HEIGHT)
        self.set_block_ref(block)
        self.set_selected(False)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Per-block color stripe, independent of the theme stylesheet.
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self._accent_color)))
        p.drawRoundedRect(0, 2, 6, max(1, self.height() - 4), 3, 3)
        p.end()

    def _show_menu(self):
        menu = QMenu(self)
        menu.addAction("Rename…", self._rename_requested)
        type_menu = menu.addMenu("Type")
        for block_type in BLOCK_TYPES:
            action = type_menu.addAction(block_type_icon(block_type, active_theme().text, 20), block_type)
            action.setCheckable(True)
            action.setChecked(block_type == self._host_project_block.block_type)
            action.triggered.connect(lambda checked=False, value=block_type: self._type_changed(value))
        menu.addSeparator()
        menu.addAction("Change color…", self._choose_block_color)
        menu.addSeparator()
        menu.addAction("Delete block", self._delete_clicked)
        menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))
        menu.deleteLater()

    def _rename_requested(self):
        # The context-menu action must actually rename the block rather than
        # merely selecting it.  Keep the edit local to the card's host window.
        block = getattr(self, "_host_project_block", None)
        if block is None:
            self.selected.emit(self.block_id)
            return
        host = self.window()
        value, ok = QInputDialog.getText(host, "Rename block", "Block name:", text=block.name)
        if ok:
            value = value.strip()
            if value and value != block.name:
                block.name = value
                self.update()
                self.rename_requested.emit(self.block_id)
            self.selected.emit(self.block_id)

    def _choose_block_color(self):
        block = getattr(self, "_host_project_block", None)
        if block is None:
            return
        current = QColor(getattr(block, "color", "") or DEFAULT_BLOCK_COLORS.get(block.block_type, "#7f8c99"))
        color = QColorDialog.getColor(current, self, f"Color — {block.name}")
        if color.isValid():
            block.color = color.name().lower()
            self._accent_color = block.color
            self.color_changed.emit(self.block_id, block.color)
            self.update()

    def set_block_ref(self, block):
        self._host_project_block = block
        self._accent_color = getattr(block, "color", "") or DEFAULT_BLOCK_COLORS.get(block.block_type, "#7f8c99")
        self.name_label.setText(block.name)
        self.name_label.setToolTip(block.name)
        self.type_label.setText(block.block_type)
        self.type_icon.setPixmap(block_type_icon(block.block_type, self._accent_color, DENSE_HEIGHT).pixmap(DENSE_HEIGHT, DENSE_HEIGHT))
        self.type_icon.setToolTip(block.block_type)
        self.algorithm_label.setText(block.algorithm)
        self.algorithm_label.setToolTip(f"Algorithm: {block.algorithm}")
        self.midi_label.setText(f"CH {int(block.midi_channel)}")
        self.mode.set_mode(block.mode)
        dirty_style = (self.property("muted") != bool(block.muted)
                       or self.property("blockType") != block.block_type)
        self.setProperty("muted", bool(block.muted))
        self.setProperty("blockType", block.block_type)
        if dirty_style:
            repolish(self)
        if hasattr(self, "mute_button"):
            self.mute_button.blockSignals(True)
            self.mute_button.setChecked(bool(block.muted))
            self.mute_button.blockSignals(False)
        self.update()

    def set_type_color(self, color, block_type=None):
        # Compatibility for existing callers; the effective color is stored per block.
        if not getattr(self, "_host_project_block", None) or not getattr(self._host_project_block, "color", ""):
            self._accent_color = color
        if block_type:
            self.setProperty("blockType", block_type)
        self.update()

    def set_selected(self, selected):
        if bool(self.property("selected")) != bool(selected):
            self.setProperty("selected", bool(selected))
            self.style().unpolish(self); self.style().polish(self); self.update()

    def _mute_clicked(self, checked):
        self.selected.emit(self.block_id)
        self.setProperty("muted", bool(checked))
        self.style().unpolish(self); self.style().polish(self); self.update()
        self.mute_changed.emit(self.block_id, bool(checked))

    def _mode_changed(self, mode):
        self.selected.emit(self.block_id)
        self.mode_changed.emit(self.block_id, mode)

    def _type_changed(self, block_type):
        self.selected.emit(self.block_id)
        self.type_changed.emit(self.block_id, block_type)

    def _delete_clicked(self):
        self.selected.emit(self.block_id)
        self.delete_requested.emit(self.block_id)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.block_id)
        super().mousePressEvent(event)


class AddBlockDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add block")
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        self.name = QLineEdit(); self.name.setPlaceholderText("Auto name from role"); self.name.setFixedHeight(24)
        self.kind = QComboBox(); self.kind.addItems(BLOCK_TYPES)
        self.algorithm = QComboBox(); setup_algorithm_combo(self.algorithm)
        self.mode = ModeSwitch("SEQ")
        form.addRow("Name", self.name)
        form.addRow("Type", self.kind)
        form.addRow("Algorithm", self.algorithm)
        form.addRow("Mode", self.mode)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class KitStepRuler(QWidget):
    """A transport cursor for every slot in the selected meter."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cursor = -1
        self.steps = 16
        self.offset = 0
        self.setMinimumWidth(176)
        self.setFixedHeight(21)
        self.setAccessibleName("Kit bar playhead")

    def set_cursor(self, cursor, steps=16, offset=0):
        if (cursor, steps, offset) != (self.cursor, self.steps, self.offset):
            self.cursor, self.steps, self.offset = cursor, max(1, steps), offset
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        width = self.width() / self.steps
        font = painter.font(); font.setPixelSize(9 if width < 13 else 10); painter.setFont(font)
        label_width = painter.fontMetrics().horizontalAdvance(str(self.offset + self.steps)) + 4
        stride = 1
        while stride * width < label_width:
            stride *= 2
        for i in range(self.steps):
            rect = QRectF(i * width + 1, 1, max(1, width - 2), 19)
            if i == self.cursor:
                painter.fillRect(rect, QColor("#ffc568"))
            painter.setPen(QColor("#15202b" if i == self.cursor else "#b7c7d6"))
            # Dense compound-meter grids keep legible labels rather than
            # squeezing adjacent two-digit numbers into a single string.
            if i == self.cursor or (i % stride == 0 and
                    (self.cursor < 0 or abs(i - self.cursor) >= stride)):
                painter.drawText(rect.adjusted(-2, 0, 2, 0), Qt.AlignCenter, str(self.offset + i + 1))


class DrumPatternLane(QWidget):
    """One scalable source page; editing retains absolute step indices."""
    step_toggled = Signal(int, bool)
    PAGE_SIZE = 32

    def __init__(self, values, offset=0, voice_name="", parent=None):
        super().__init__(parent)
        self.values = list(values)
        self.offset = int(offset)
        self.voice_name = voice_name
        self.focus_step = 0
        # Reserve the same width for every page so changing Length does not
        # push the Blocks/Inspector divider sideways.
        self.setMinimumWidth(256)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName(f"{voice_name} source pattern, steps {offset + 1}–{offset + len(values)}")

    def set_values(self, values):
        values = list(values)
        if values != self.values:
            self.values = values
            self.focus_step = min(self.focus_step, max(0, len(values) - 1))
            self.update()

    def _step_at(self, position):
        if self.rect().contains(position.toPoint()) and self.values:
            return min(len(self.values) - 1, int(position.x() * len(self.values) / max(1, self.width())))
        return None

    def _toggle(self, index):
        self.focus_step = index
        checked = not (abs(self.values[index]) > 1e-9)
        self.values[index] = 1.0 if checked else 0.0
        self.update()
        self.step_toggled.emit(self.offset + index, checked)

    def mousePressEvent(self, event):
        index = self._step_at(event.position())
        if event.button() == Qt.LeftButton and index is not None:
            self.setFocus(Qt.MouseFocusReason)
            self._toggle(index)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        index = self._step_at(event.position())
        if index is not None:
            self.setToolTip(f"{self.voice_name} · step {self.offset + index + 1} · value {self.values[index]:g}\nClick to toggle; editing selects the Pattern generator.")
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if self.values and event.key() in (Qt.Key_Left, Qt.Key_Right):
            self.focus_step = max(0, min(len(self.values) - 1, self.focus_step + (1 if event.key() == Qt.Key_Right else -1)))
            self.update(); event.accept(); return
        if self.values and event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._toggle(self.focus_step); event.accept(); return
        super().keyPressEvent(event)

    def event(self, event):
        if event.type() == QEvent.ShortcutOverride and event.key() in (Qt.Key_Space, Qt.Key_Left, Qt.Key_Right):
            event.accept()
            return True
        return super().event(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()
        width = self.width() / max(1, len(self.values))
        for index, value in enumerate(self.values):
            rect = QRectF(index * width + 1, 3, max(1, width - 2), 16)
            active = abs(value) > 1e-9
            painter.setBrush(palette.highlight() if active else palette.base())
            painter.setPen(QPen(palette.highlight().color() if active else palette.mid().color(), 1))
            painter.drawRoundedRect(rect, 2, 2)
            if (self.offset + index) % 4 == 0:
                painter.setPen(palette.mid().color())
                painter.drawLine(QPointF(index * width, 0), QPointF(index * width, 21))
            if self.hasFocus() and index == self.focus_step:
                painter.setPen(QPen(palette.text().color(), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 1, 1)


class KitPlanLane(QWidget):
    """Read-only arrangement page with independent beat and bar boundaries."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(256)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.steps, self.cursor = [], -1
        self.output_values = None
        self.groups = (4, 4, 4, 4)
        self.bar_starts = (0,)
        self.setToolTip("Kit plan before processing: green = protected beat, teal = added hit, outline = optional source slot, orange = fill. Bright separators mark bars. Length sets the visible window; Source edits the generator.")

    def set_plan(self, steps, cursor, groups=(4, 4, 4, 4), bar_starts=(0,)):
        if self.output_values is not None:
            self.setToolTip("Kit plan before processing: green = protected beat, teal = added hit, outline = optional source slot, orange = fill.")
        count = sum(groups)
        steps = (list(steps) + [KitStep()] * count)[:count]
        if steps != self.steps or cursor != self.cursor or groups != self.groups or bar_starts != self.bar_starts or self.output_values is not None:
            self.steps, self.cursor = steps, cursor
            self.output_values = None
            self.groups = groups
            self.bar_starts = bar_starts
            self.update()

    def set_output(self, values, cursor, groups, bar_starts=(0,)):
        if self.output_values is None:
            self.setToolTip("Accepted generated output: bar height = velocity, dash = rest, grey = not visited. Includes processing, probability and mute; works without a MIDI port. This is not feedback from the instrument.")
        values = list(values)
        if values != self.output_values or cursor != self.cursor or groups != self.groups or bar_starts != self.bar_starts:
            self.output_values, self.cursor, self.groups = values, cursor, groups
            self.bar_starts = bar_starts
            self.steps = [KitStep()] * len(values)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        width = self.width() / sum(self.groups)
        boundaries = {sum(self.groups[:i]) for i in range(len(self.groups))}
        for i, step in enumerate(self.steps):
            color = "#e2a554" if step.fill else ("#65b9ac" if step.anchor else "#558fa6" if step.force else "#657982" if step.allowed else "#333e49")
            painter.setBrush(QColor(color if step.force or step.fill else "#17212b"))
            painter.setPen(QPen(QColor(color), 1))
            painter.drawRoundedRect(QRectF(i * width + 1, 3, max(1, width - 3), 16), 2, 2)
            if self.output_values is not None:
                value = self.output_values[i]
                rect = QRectF(i * width + 1, 3, max(1, width - 3), 16)
                painter.fillRect(rect, QColor("#28313b" if value is None else "#101923"))
                if value is not None and value > 0:
                    height = max(3., 16 * value)
                    painter.fillRect(QRectF(rect.x(), 19 - height, rect.width(), height), QColor("#65b9ac"))
                elif value == 0:
                    painter.setPen(QPen(QColor("#657982"), 1))
                    painter.drawLine(QPointF(rect.left() + 1, 11), QPointF(rect.right() - 1, 11))
            if i in boundaries:
                painter.setPen(QPen(QColor("#d3dfeb" if i in self.bar_starts else "#8295a6"), 2 if i in self.bar_starts else 1))
                painter.drawLine(QPointF(i * width, 0), QPointF(i * width, 22))
            if i == self.cursor:
                painter.fillRect(QRectF(i * width + 1, 1, max(1, width - 2), 20), QColor(255, 197, 104, 55))
                painter.setPen(QPen(QColor("#ffc568"), 2))
                painter.drawLine(QPointF((i + .5) * width, 0), QPointF((i + .5) * width, 22))


class PatternChanceEditor(QWidget):
    """Compact editor for all source steps, without a wide row of knobs."""
    def __init__(self, host, block, parent=None):
        super().__init__(parent)
        self.host, self.block = host, block
        self.setObjectName("patternChanceEditor")
        self.setToolTip("Chance on every pass, after processing. Steps follow Pattern Reverse/Rotation. 0% mutes the step, 100% always passes it. An active motif uses its own rhythm.")
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(5)
        row.addWidget(QLabel("Step"))
        self.step = ContrastSpinBox(); self.step.setObjectName("patternChanceStep"); self.step.setFixedWidth(54)
        row.addWidget(self.step)
        self.chance = QSlider(Qt.Horizontal); self.chance.setRange(0, 100)
        self.chance.setObjectName("patternChanceValue"); self.chance.setMinimumWidth(70)
        row.addWidget(self.chance, 1)
        self.value_label = QLabel(); self.value_label.setFixedWidth(35); row.addWidget(self.value_label)
        reset = QPushButton("All 100%"); reset.setObjectName("patternChanceReset"); row.addWidget(reset)
        self.step.valueChanged.connect(self._refresh_value)
        self.chance.valueChanged.connect(self._changed)
        reset.clicked.connect(self._reset)
        self.refresh()
        for control in (self, self.step, self.chance, reset):
            bind_help(control, "pattern_step_chances", "generator")

    def refresh(self):
        self.step.blockSignals(True)
        self.step.setRange(1, len(step_chances(self.block.parameters)))
        self.step.blockSignals(False)
        self._refresh_value()

    def _refresh_value(self, *_):
        values = step_chances(self.block.parameters)
        value = round(100 * values[min(self.step.value() - 1, len(values) - 1)])
        self.chance.blockSignals(True); self.chance.setValue(value); self.chance.blockSignals(False)
        self.value_label.setText(f"{value}%")

    def _changed(self, value):
        host = self.host
        block = self.block
        project_ref = host.project
        step_index = int(self.step.value()) - 1
        chance = float(value) / 100.

        def apply_chance():
            if host.project is not project_ref or host.get_entity(block.id) is not block:
                return
            values = step_chances(block.parameters)
            if 0 <= step_index < len(values):
                values[step_index] = chance
                block.parameters["pattern_step_chances"] = values

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            apply_chance, key=("pattern-chance", int(block.id), step_index),
            notification={"dirty": True, "block_id": int(block.id)},
            label=f"pattern chance {block.id}:{step_index}"
        )
        self.value_label.setText(f"{value}%")

    def _reset(self):
        host = self.host
        block = self.block
        project_ref = host.project

        def reset_chances():
            if host.project is project_ref and host.get_entity(block.id) is block:
                block.parameters.pop("pattern_step_chances", None)

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            reset_chances, key=("pattern-chance-reset", int(block.id)),
            notification={"dirty": True, "block_id": int(block.id)},
            label=f"reset pattern chances {block.id}"
        )
        self._refresh_value()


class DrumKitEditor(LayerGroup):
    """Compact Drum Machine editor embedded in the DRUM inspector."""
    VOICE_COLORS = ("#e57373", "#ffb74d", "#fff176", "#81c784", "#64b5f6", "#ba68c8")
    voice_selected = Signal(int)

    @staticmethod
    def structure_key(host, drum):
        return (id(drum), int(host.project.length), bool(getattr(host, "_kit_source_view", False)),
                bool(getattr(host, "_kit_output_view", False)),
                getattr(host, "_kit_pattern_pages", {}).get(drum.id, 0),
                tuple(getattr(host, "_midi_output_names", ())),
                tuple((id(v), v.name, v.algorithm, v.mode, v.midi_channel, v.midi_note,
                       v.midi_port, v.muted, voice_role(v)) for v in drum.drum_voices),
                tuple((key, repr(drum.parameters.get(key))) for key in (
                    "kit_coordinated", "kit_engine", "kit_motif_enabled", "kit_motif_return",
                    "kit_links_enabled", "kit_voice_links")))

    def __init__(self, host, drum, selected_voice_id=None, parent=None):
        expanded = getattr(host, "_inspector_state", {}).get((drum.id, "DRUM KIT"), True)
        super().__init__("DRUM VOICES / KIT", parent, expanded=expanded)
        self.host = host
        self.drum = drum
        self.selected_voice_id = selected_voice_id
        self.plan_lanes = {}
        self.pattern_lanes = {}
        self.voice_buttons = {}
        self.pattern_length = max(1, int(host.project.length))
        pages = getattr(host, "_kit_pattern_pages", {})
        self.pattern_page = min(max(0, pages.get(drum.id, 0)), (self.pattern_length - 1) // DrumPatternLane.PAGE_SIZE)
        self.pattern_offset = self.pattern_page * DrumPatternLane.PAGE_SIZE
        self.source_view = bool(getattr(host, "_kit_source_view", False))
        self._plan_view_cache = None
        ensure_drum_voices(drum)
        self.setObjectName("drumKitEditor")
        self._build()
        self._structure_key = self.structure_key(host, drum)
        self._apply_children_visibility()
        self._sync_layout_geometry()
        self.accordion_toggled.connect(
            lambda checked: self.host._remember_group(self.drum.id, "DRUM KIT", checked)
        )

    def _set_expanded(self, expanded):
        # The kit now lives inside the same scrollable page as the other
        # Inspector sections. Let its natural height update the page instead
        # of preserving the old pinned-panel splitter geometry.
        super()._set_expanded(expanded)

    def _source_values(self, voice):
        if voice.algorithm != "Pattern":
            # Preview the generator before processing. Editing can turn this
            # rhythm into a Pattern without baking the effects twice.
            engine = self.host.engine
            lock = self.host.transport._transport_lock
            if not lock.acquire(blocking=False):
                # The preview is non-critical. Reuse the last published source
                # rhythm rather than making Qt wait for a busy transport tick.
                published = voice.outputs.get("rhythm", []) or [0.0]
                return fixed_pattern(max(1, self.pattern_length), published)
            try:
                length = engine._kit_cycle_length(voice)
                raw = engine._seq_material(voice, length, random.Random(engine._seed_for(voice)))
                zero_is_rest = engine._zero_is_rest(voice)
            finally:
                lock.release()
            values = [0.0 if value is None or (zero_is_rest and abs(float(value)) <= 1e-9)
                      else 1.0 for value in raw]
            return fixed_pattern(length, values or [0.0])
        return parse_number_list(voice.parameters.get("pattern", DEFAULT_PATTERN), float,
                                 parse_number_list(DEFAULT_PATTERN, float))

    def select_voice(self, voice_id):
        self.selected_voice_id = voice_id
        for vid, button in self.voice_buttons.items():
            selected = vid == voice_id
            if bool(button.property("selected")) != selected:
                button.setProperty("selected", selected)
                color = button._voice_color
                button.setStyleSheet(f"QPushButton {{ color:{color}; font-weight:{700 if selected else 600}; text-align:left; padding:2px 4px; border:1px solid {color if selected else 'transparent'}; border-radius:3px; }}")
        valid = self._selected_voice() is not None
        self.copy_voice_button.setEnabled(valid)
        self.paste_voice_button.setEnabled(valid and getattr(self.host, "_drum_voice_clipboard", None) is not None)
        for voice in self.drum.drum_voices:
            self.refresh_pattern(voice)
        self.update_position()

    def _voice_pattern(self, voice):
        # Match the generator: short patterns repeat up to global Length.
        return fixed_pattern(self.pattern_length, self._source_values(voice))

    def refresh_pattern(self, voice):
        lane = self.pattern_lanes.get(voice.id)
        if lane is not None:
            values = self._voice_pattern(voice)
            lane.set_values(values[self.pattern_offset:self.pattern_offset + DrumPatternLane.PAGE_SIZE])

    def _set_pattern(self, voice, index, checked):
        host = self.host
        drum = self.drum
        project_ref = host.project
        voice_id = int(voice.id)
        index = int(index)
        checked = bool(checked)

        def apply_pattern_step():
            if host.project is not project_ref or not any(block is drum for block in project_ref.blocks):
                return
            if host.get_entity(voice_id) is not voice or not 0 <= index < int(project_ref.length):
                return
            engine = host.engine
            if voice.algorithm != "Pattern":
                length = engine._kit_cycle_length(voice)
                raw = engine._seq_material(voice, length, random.Random(engine._seed_for(voice)))
                zero_is_rest = engine._zero_is_rest(voice)
                source = [0.0 if value is None or (zero_is_rest and abs(float(value)) <= 1e-9) else 1.0
                          for value in raw]
            else:
                source = parse_number_list(voice.parameters.get("pattern", DEFAULT_PATTERN), float,
                                           parse_number_list(DEFAULT_PATTERN, float))
            count = max(len(source), int(project_ref.length))
            values = fixed_pattern(count, source)
            if "pattern_step_chances" in voice.parameters:
                chances = step_chances(voice.parameters)
                voice.parameters["pattern_step_chances"] = [chances[i % len(chances)] for i in range(count)]
            values[index] = 1.0 if checked else 0.0
            voice.parameters["pattern"] = ",".join(format(value, ".12g") for value in values)
            if voice.algorithm != "Pattern":
                for name in ("pattern_reverse", "pattern_rotation", "pattern_scale"):
                    voice.parameters.pop(name, None)
            voice.algorithm = "Pattern"
            engine.regenerate(drum)

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            apply_pattern_step, key=("drum-pattern-step", int(drum.id), voice_id, index),
            notification={"dirty": True, "block_id": int(drum.id), "refresh": "SOURCE"},
            label=f"drum pattern {voice_id} step {index}"
        )

    def _changed(self, voice, key, value):
        host = self.host
        drum = self.drum
        project_ref = host.project
        voice_id = int(voice.id)

        def apply_voice_edit():
            if host.project is not project_ref or not any(block is drum for block in project_ref.blocks):
                return
            if host.get_entity(voice_id) is not voice:
                return
            if key == "midi_channel":
                voice.midi_channel = max(1, min(16, int(value)))
                voice.midi_channel_override = voice.midi_channel != int(drum.midi_channel)
            elif key == "midi_note":
                voice.parameters.setdefault("kit_role", voice_role(voice))
                voice.midi_note = max(0, min(127, int(value)))
            elif key == "midi_port":
                voice.midi_port = str(value or "")
                host.transport.refresh_ports()
            elif key == "mode":
                host.transport._release_block_notes(voice.id)
                voice.mode = str(value)
                host.engine.reset_live(voice)
            elif key == "algorithm":
                host.engine.reset_live(voice)
                voice.algorithm = str(value)
            elif key == "muted":
                voice.muted = bool(value)
                host.transport.set_block_muted(voice.id, voice.muted)
            else:
                voice.parameters[key] = value
            host.engine.regenerate(drum)

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            apply_voice_edit, key=("drum-voice-edit", int(drum.id), voice_id, str(key)),
            notification={"dirty": True, "block_id": int(drum.id), "refresh": "SOURCE"},
            label=f"drum voice {voice_id} {key}"
        )

    def _set_config(self, key, value):
        host = self.host
        drum = self.drum
        project_ref = host.project

        def apply_config():
            if host.project is not project_ref or not any(block is drum for block in project_ref.blocks):
                return
            drum.parameters[key] = value
            for voice in drum.drum_voices:
                voice.parameters.setdefault("kit_role", voice_role(voice))
            host.engine.regenerate(drum)

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            apply_config, key=("drum-kit-config", int(drum.id), str(key)),
            notification={"dirty": True, "block_id": int(drum.id), "refresh": "SOURCE",
                          "blocks": key == "kit_coordinated"},
            label=f"drum kit config {drum.id} {key}"
        )

    def _auto_roles(self):
        host = self.host
        drum = self.drum
        project_ref = host.project

        def apply_roles():
            if host.project is not project_ref or not any(block is drum for block in project_ref.blocks):
                return
            for voice in drum.drum_voices:
                voice.parameters["kit_role"] = infer_role(voice.midi_note, voice.name)
            host.engine.regenerate(drum)

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            apply_roles, key=("drum-auto-roles", int(drum.id)),
            notification={"dirty": True, "block_id": int(drum.id), "refresh": "SOURCE"},
            label=f"infer drum roles {drum.id}"
        )

    def _view_changed(self, *_):
        source = self.view_selector.currentData() == "source"
        self.host._kit_output_view = self.view_selector.currentData() == "output"
        self.host._kit_source_view = source
        if source != self.source_view:
            self.host._queue_inspector_refresh()
        else:
            self.update_position()

    def _pattern_page_changed(self, index):
        pages = getattr(self.host, "_kit_pattern_pages", {})
        pages[self.drum.id] = int(index)
        self.host._kit_pattern_pages = pages
        self.host._queue_inspector_refresh()

    def _selected_voice(self):
        return next((v for v in self.drum.drum_voices if v.id == self.selected_voice_id), None)

    def _copy_voice(self, voice=None):
        voice = voice or self._selected_voice()
        if voice is None:
            return
        with self.host.transport._transport_lock:
            if self.host.get_entity(voice.id) is not voice:
                return
            self.host._drum_voice_clipboard = (voice.name, sound_snapshot(voice))
        self.paste_voice_button.setEnabled(self._selected_voice() is not None)
        self.host.set_message(f"Copied sound settings: {voice.name}")

    def _paste_voice(self, voice=None, undo=False):
        voice = voice or self._selected_voice()
        clipboard = getattr(self.host, "_drum_voice_clipboard", None)
        history = getattr(self.host, "_voice_paste_undo", {})
        data = history.get(voice.id) if voice is not None and undo else (clipboard[1] if clipboard else None)
        if voice is None or data is None:
            return
        host = self.host
        drum = self.drum
        project_ref = host.project
        voice_id = int(voice.id)

        def apply_paste():
            if host.project is not project_ref or host.get_entity(voice_id) is not voice:
                return
            previous = sound_snapshot(voice)
            host.engine.performance.stop(voice.id)
            apply_sound(voice, data)
            events = int(host.engine.live_state.get(voice.id, {}).get("events", 0))
            host.engine.live_state[voice.id] = {"events": events, "phase_index": events}
            host.engine.live_rng.pop(voice.id, None)
            current_history = getattr(host, "_voice_paste_undo", {})
            if undo:
                current_history.pop(voice.id, None)
            else:
                current_history[voice.id] = previous
            host._voice_paste_undo = current_history
            host.engine._kit_source_cache.pop(voice.id, None)
            host.engine.regenerate(drum)

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            apply_paste, key=("drum-voice-paste", int(drum.id), voice_id),
            notification={"dirty": True, "block_id": int(drum.id), "refresh": "SOURCE",
                          "message": f"{'Restored' if undo else 'Pasted'} sound settings: {voice.name}"},
            label=f"paste drum voice {voice_id}"
        )

    def _voice_menu(self, voice, button, pos):
        menu = QMenu(self)
        menu.addAction("Copy sound settings", lambda: self._copy_voice(voice))
        paste = menu.addAction("Paste sound settings", lambda: self._paste_voice(voice))
        paste.setEnabled(getattr(self.host, "_drum_voice_clipboard", None) is not None)
        undo = menu.addAction("Undo last paste", lambda: self._paste_voice(voice, undo=True))
        undo.setEnabled(voice.id in getattr(self.host, "_voice_paste_undo", {}))
        menu.exec(button.mapToGlobal(pos))
        menu.deleteLater()

    def update_position(self):
        active = coordinated(self.drum)
        self.style_selector.setEnabled(active)
        self.phrase_length.setEnabled(active)
        self.auto_roles.setEnabled(active)
        self.meter_selector.setEnabled(active)
        self.keep_beat.setEnabled(active)
        self.new_variant.setEnabled(active)
        self.view_selector.setEnabled(active)
        if not active or self.source_view:
            source_steps = min(DrumPatternLane.PAGE_SIZE, self.pattern_length - self.pattern_offset)
            self.plan_ruler.set_cursor(-1, source_steps, self.pattern_offset)
        for knob in self.creative_knobs:
            knob.setEnabled(active)
        self.rhythm_panel.update_state(active)
        roles = {voice_role(v) for v in self.drum.drum_voices if not v.muted}
        missing = [label for label, candidates in (("Kick", {"kick"}), ("Snare/Clap", {"snare", "clap"}),
                    ("Hat", {"closed_hat", "open_hat"})) if not roles & candidates]
        self.role_warning.setText("Missing beat roles: " + ", ".join(missing) + ". Check Role or use Auto roles.")
        self.role_warning.setVisible(active and bool(missing))
        if not active:
            self.plan_status.setText(f"Source: {self.pattern_length} steps · independent timing")
            return
        lock = self.host.transport._transport_lock
        if not lock.acquire(blocking=False):
            return
        try:
            beat = self.host.engine.clock.position_beats
            plan = self.host.engine.drum_plan(self.drum, beat)
            slot = max(0, int(math.floor(beat / STEP_BEATS + 1e-8))) % plan.length
            absolute_slot = max(0, int(math.floor(beat / STEP_BEATS + 1e-8)))
            steps = plan.steps_per_bar
            count = min(DrumPatternLane.PAGE_SIZE, self.pattern_length - self.pattern_offset)
            window_start = absolute_slot // self.pattern_length * self.pattern_length + self.pattern_offset
            cursor = absolute_slot - window_start
            if not self.host.transport.running or not 0 <= cursor < count:
                cursor = -1
            if not self.source_view:
                self.plan_ruler.set_cursor(cursor, count, self.pattern_offset)
            # Length controls the display, while meter/phrase keep musical
            # timing. A page can cross bars and even phrase cycles. Cache the
            # preview so a transport repaint does not recompose future plans.
            key = (plan.token, window_start, count)
            if self._plan_view_cache is None or self._plan_view_cache[0] != key:
                boundaries = {sum(plan.groups[:i]) for i in range(len(plan.groups))}
                cuts = [0] + [i for i in range(1, count) if (window_start + i) % steps in boundaries] + [count]
                groups = tuple(b - a for a, b in zip(cuts, cuts[1:]))
                bar_starts = tuple(i for i in range(count) if (window_start + i) % steps == 0)
                preview = KitCoordinator()
                current_plan = plan
                rows = {vid: [] for vid in self.plan_lanes}
                for i in range(count):
                    position = window_start + i
                    if (not current_plan.start_slot <= position < current_plan.start_slot + current_plan.length
                            or position < current_plan.context.origin_slot
                            or (current_plan.context.end_slot is not None and position >= current_plan.context.end_slot)):
                        current_plan = self.host.engine.drum_plan(self.drum, position * STEP_BEATS, coordinator=preview)
                    for vid in rows:
                        rows[vid].append(current_plan.at(vid, position))
                self._plan_view_cache = (key, rows, groups, bar_starts)
            _, rows, groups, bar_starts = self._plan_view_cache
            for voice_id, lane in self.plan_lanes.items():
                if self.view_selector.currentData() == "output":
                    history = self.host.transport.drum_output_history.get(voice_id, {})
                    lane.set_output([history.get(window_start + i) for i in range(count)], cursor, groups, bar_starts)
                else:
                    lane.set_plan(rows[voice_id], cursor, groups, bar_starts)
        finally:
            lock.release()
        fill = any(plan.at(v.id, slot).fill for v in self.drum.drum_voices)
        self.rhythm_panel.update_state(active, plan, slot // steps)
        self.plan_status.setText(f"View {self.pattern_offset + 1}–{self.pattern_offset + count} · Bar {slot // steps + 1}/{plan.length // steps} · Step {slot % steps + 1:02d}/{steps}" + (" · FILL" if fill else ""))

    def _add_voice(self):
        ensure_drum_voices(self.drum)
        index = len(self.drum.drum_voices) + 1
        voice = DrumVoice(
            id=-(abs(int(self.drum.id)) * 100 + index), parent_id=int(self.drum.id),
            name=f"VOICE {index}", algorithm="Pattern", mode=str(self.drum.mode),
            midi_channel=int(self.drum.midi_channel), midi_channel_override=False,
            midi_port=str(self.drum.midi_port or ""), midi_note=35 + index,
            parameters={"pattern": "1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0",
                        "gate": .78, "live_gate": .65, "fill_density": 1.0,
                        "event_probability": 1.0, "kit_role": "perc"},
        )
        self.drum.drum_voices.append(voice)
        self.host._mark_dirty()
        self.host.engine.regenerate(self.drum)
        # The kit is part of the scrolling Inspector. Preserve the current
        # scroll position in the voice settings after adding a row.
        self.host._queue_inspector_refresh()

    def _build(self):
        # Keep the full kit in one body, just like the other Inspector layers.
        # Live updates can still show/hide individual hints while the body is
        # collapsed without making those hints escape the accordion.
        self.body = QWidget()
        frame = QVBoxLayout(self)
        frame.setContentsMargins(7, 10, 7, 7)
        frame.setSpacing(4)
        frame.addWidget(self.body)
        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(5)
        note = QLabel("Select a voice to edit its generator below. Role is independent of its name and MIDI note.")
        note.setObjectName("muted")
        outer.addWidget(note)
        arrangement = QHBoxLayout()
        enabled = QCheckBox("Coordinated kit")
        enabled.setObjectName("kitCoordinated")
        enabled.setChecked(coordinated(self.drum))
        enabled.setToolTip("Shared 1/16 grid in SEQ and LIVE. Anchors, hat exclusion and one fill lead. Free voices keep independent timing.")
        enabled.toggled.connect(lambda checked: self._set_config("kit_coordinated", bool(checked)))
        bind_help(enabled, "kit_coordinated", "kit")
        arrangement.addWidget(enabled)
        self.style_selector = QComboBox()
        self.style_selector.setObjectName("kitStyle")
        for label, key in KIT_STYLES:
            self.style_selector.addItem(label, key)
        self.style_selector.setCurrentIndex(max(0, self.style_selector.findData(self.drum.parameters.get("kit_style", "straight"))))
        self.style_selector.currentIndexChanged.connect(lambda _: self._set_config("kit_style", self.style_selector.currentData()))
        arrangement.addWidget(self.style_selector)
        self.meter_selector = QComboBox()
        self.meter_selector.setObjectName("kitMeter")
        self.meter_selector.setToolTip("Kit meter on a 1/16 grid. 6/8 and 12/8 use groups of three eighth notes; 7/8 uses 2+2+3. Other blocks keep their timing.")
        for label, groups in KIT_METERS:
            self.meter_selector.addItem(label, label.split(" · ")[0])
        self.meter_selector.setCurrentIndex(max(0, self.meter_selector.findData(self.drum.parameters.get("kit_meter", "4/4"))))
        self.meter_selector.currentIndexChanged.connect(lambda _: self._set_config("kit_meter", self.meter_selector.currentData()))
        arrangement.addWidget(self.meter_selector)
        arrangement.addWidget(QLabel("Phrase · bars"))
        self.phrase_length = ContrastSpinBox()
        self.phrase_length.setObjectName("kitPhraseBars")
        self.phrase_length.setRange(1, 8)
        self.phrase_length.setValue(phrase_bars(self.drum))
        self.phrase_length.setFixedWidth(48)
        self.phrase_length.valueChanged.connect(lambda value: self._set_config("kit_phrase_bars", int(value)))
        arrangement.addWidget(self.phrase_length)
        self.auto_roles = QPushButton("Auto roles")
        self.auto_roles.setObjectName("kitAutoRoles")
        self.auto_roles.setToolTip("Reassign roles from recognizable voice names first, then GM notes. Use this to repair older custom-note kits. MIDI notes, channels and outputs stay as configured.")
        self.auto_roles.clicked.connect(self._auto_roles)
        arrangement.addWidget(self.auto_roles)
        arrangement.addStretch(1)
        self.plan_status = QLabel()
        self.plan_status.setObjectName("kitPosition")
        self.plan_status.setFixedWidth(210)
        arrangement.addWidget(self.plan_status)
        outer.addLayout(arrangement)
        self.role_warning = QLabel()
        self.role_warning.setObjectName("kitRoleWarning")
        self.role_warning.setWordWrap(True)
        outer.addWidget(self.role_warning)
        grid = QGridLayout()
        grid.setHorizontalSpacing(4); grid.setVerticalSpacing(3)
        headers = ["Voice", "M", "Role", "Algorithm", "Mode", "Ch", "Note", "Kit plan / Source", "Out"]
        ports = list(getattr(self.host, "_midi_output_names", []) or [])
        if not ports and not hasattr(self.host, "_midi_output_names"):
            ports, _ = get_midi_output_names()
            self.host._midi_output_names = list(ports)
        for column, label in enumerate(headers):
            title = QLabel(label); title.setObjectName("knobLabel")
            if column == 7:
                header = QWidget(); header_layout = QVBoxLayout(header)
                header_layout.setContentsMargins(0, 0, 0, 0); header_layout.setSpacing(0)
                title_row = QHBoxLayout(); title_row.setContentsMargins(0, 0, 0, 0); title_row.setSpacing(3)
                title.setText("Kit")
                title_row.addWidget(title)
                self.view_selector = QComboBox(); self.view_selector.setObjectName("kitView")
                self.view_selector.addItem("Plan", "plan"); self.view_selector.addItem("Output", "output")
                self.view_selector.addItem("Source", "source")
                self.view_selector.setFixedWidth(76)
                self.view_selector.setCurrentIndex(2 if self.source_view or not coordinated(self.drum) else 1 if getattr(self.host, "_kit_output_view", False) else 0)
                self.view_selector.setToolTip("All views follow global Length, up to 32 steps per page. Plan/Output retain Kit meter and phrase boundaries. Source edits the generator. Output includes processing, probability and mute; it is not MIDI input feedback.")
                self.view_selector.currentIndexChanged.connect(self._view_changed)
                title_row.addWidget(self.view_selector); title_row.addStretch(1)
                self.page_selector = QComboBox()
                self.page_selector.setObjectName("kitPatternPage")
                self.page_selector.setAccessibleName("Drum pattern / plan page")
                for start in range(0, self.pattern_length, DrumPatternLane.PAGE_SIZE):
                    self.page_selector.addItem(f"{start + 1}–{min(start + DrumPatternLane.PAGE_SIZE, self.pattern_length)} / {self.pattern_length}")
                self.page_selector.setCurrentIndex(self.pattern_page)
                self.page_selector.currentIndexChanged.connect(self._pattern_page_changed)
                title_row.addWidget(self.page_selector)
                header_layout.addLayout(title_row)
                self.plan_ruler = KitStepRuler()
                header_layout.addWidget(self.plan_ruler)
                grid.addWidget(header, 0, column)
            else:
                grid.addWidget(title, 0, column, Qt.AlignBottom)
        for row, voice in enumerate(self.drum.drum_voices, 1):
            color = self.VOICE_COLORS[(row - 1) % len(self.VOICE_COLORS)]
            name = QPushButton(f"●  {voice.name}"); name.setFlat(True); name.setCursor(Qt.PointingHandCursor)
            name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            name.setMinimumHeight(22)
            name.setStyleSheet(f"QPushButton {{ color:{color}; font-weight:600; text-align:left; padding:2px 4px; border:1px solid transparent; border-radius:3px; }}")
            if voice.id == self.selected_voice_id:
                name.setProperty("selected", True); name.setStyleSheet(
                    f"QPushButton {{ color:{color}; font-weight:700; text-align:left; padding:2px 4px; border:1px solid {color}; border-radius:3px; }}")
            name.clicked.connect(lambda _=False, v=voice: self.voice_selected.emit(int(v.id)))
            name._voice_color = color
            self.voice_buttons[voice.id] = name
            name.setContextMenuPolicy(Qt.CustomContextMenu)
            name.customContextMenuRequested.connect(lambda pos, v=voice, w=name: self._voice_menu(v, w, pos))
            grid.addWidget(name, row, 0)
            mute = QPushButton("M"); mute.setCheckable(True); mute.setChecked(bool(voice.muted)); mute.setFixedWidth(25)
            mute.setAccessibleName(f"Mute {voice.name}")
            mute.toggled.connect(lambda checked, v=voice: self._changed(v, "muted", bool(checked)))
            grid.addWidget(mute, row, 1)
            algorithm = QComboBox(); setup_algorithm_combo(algorithm, voice.algorithm); algorithm.setFixedWidth(110)
            algorithm.currentTextChanged.connect(lambda value, v=voice: self._changed(v, "algorithm", value))
            grid.addWidget(algorithm, row, 3)
            mode = ModeSwitch(voice.mode); mode.changed.connect(lambda value, v=voice: self._changed(v, "mode", value))
            grid.addWidget(mode, row, 4)
            channel = ContrastSpinBox(); channel.setRange(1, 16); channel.setValue(int(voice.midi_channel)); channel.setFixedWidth(48)
            channel.setToolTip("Follows the DRUM channel until changed here; editing creates a voice override")
            channel.valueChanged.connect(lambda value, v=voice: self._changed(v, "midi_channel", value))
            grid.addWidget(channel, row, 5)
            base_note = ContrastSpinBox(); base_note.setRange(0, 127); base_note.setValue(int(voice.midi_note)); base_note.setFixedWidth(54)
            base_note.valueChanged.connect(lambda value, v=voice: self._changed(v, "midi_note", value))
            grid.addWidget(base_note, row, 6)
            lane = QHBoxLayout(); lane.setContentsMargins(0, 0, 0, 0); lane.setSpacing(2)
            if coordinated(self.drum, voice) and not self.source_view:
                plan_lane = KitPlanLane()
                self.plan_lanes[voice.id] = plan_lane
                lane.addWidget(plan_lane)
            elif voice.mode == "LIVE" and not coordinated(self.drum, voice):
                stream = QLabel("LIVE STREAM  ·  Prob / Min / Max / Phase")
                stream.setObjectName("muted"); lane.addWidget(stream)
            else:
                values = self._voice_pattern(voice)
                pattern_lane = DrumPatternLane(values[self.pattern_offset:self.pattern_offset + DrumPatternLane.PAGE_SIZE], self.pattern_offset, voice.name)
                pattern_lane.step_toggled.connect(lambda index, checked, v=voice: self._set_pattern(v, index, checked))
                self.pattern_lanes[voice.id] = pattern_lane
                lane.addWidget(pattern_lane)
            cell = QWidget(); cell.setLayout(lane); grid.addWidget(cell, row, 7)
            output = QComboBox(); output.addItem("(none)")
            output.addItems(ports)
            current_port = str(voice.midi_port or "")
            if current_port and output.findText(current_port) >= 0:
                output.setCurrentText(current_port)
            output.setFixedWidth(92)
            output.currentTextChanged.connect(lambda value, v=voice: self._changed(v, "midi_port", "" if value == "(none)" else value))
            grid.addWidget(output, row, 8)
            role = QComboBox()
            role.setObjectName(f"kitRole_{voice.id}")
            role.setAccessibleName(f"Role for {voice.name}")
            role.setToolTip("Musical role in the shared kit. Free uses independent timing and generation.")
            for label, key in KIT_ROLES:
                role.addItem(label, key)
            role.setCurrentIndex(role.findData(voice_role(voice)))
            role.setFixedWidth(92)
            role.currentIndexChanged.connect(lambda _, v=voice, w=role: self._changed(v, "kit_role", w.currentData()))
            bind_help(role, "kit_role", "kit")
            for control, key in ((name, "name"), (mute, "muted"), (algorithm, "algorithm"), (mode, "mode"),
                                 (channel, "midi_channel"), (base_note, "midi_note"), (output, "output_port")):
                bind_help(control, key, "identity")
            grid.addWidget(role, row, 2)
        grid.setColumnStretch(7, 1)
        self.page_selector.setVisible(bool(self.pattern_lanes or self.plan_lanes) and self.pattern_length > DrumPatternLane.PAGE_SIZE)
        outer.addLayout(grid)

        def labelled_knob(label, knob):
            return parameter_cell(label, knob, label_factory=source_label)

        controls = QHBoxLayout(); controls.setSpacing(8)
        for key, default in KIT_DEFAULTS.items():
            label = key.removeprefix("kit_").title()
            knob = ParamKnob(kit_value(self.drum, key), default=default)
            knob.bind_parameter(self.drum.id, key)
            knob.setObjectName(key)
            knob.setAccessibleName(f"Kit {label}")
            knob.setToolTip(KIT_TOOLTIPS[key])
            knob.setFixedWidth(54)
            knob.changed.connect(lambda value, k=key: self.host._set_drum_kit_parameter(self.drum, k, float(value)))
            controls.addWidget(labelled_knob(label, knob))
        controls.addStretch(1)
        self.copy_voice_button = QPushButton("Copy voice")
        self.copy_voice_button.setObjectName("copyDrumVoice")
        self.copy_voice_button.setEnabled(self._selected_voice() is not None)
        self.copy_voice_button.setToolTip("Select a voice, then copy its generator, parameters and processing. Right-click any voice for Copy/Paste/Undo.")
        self.copy_voice_button.clicked.connect(lambda: self._copy_voice())
        controls.addWidget(self.copy_voice_button)
        self.paste_voice_button = QPushButton("Paste voice")
        self.paste_voice_button.setObjectName("pasteDrumVoice")
        self.paste_voice_button.setEnabled(self._selected_voice() is not None and getattr(self.host, "_drum_voice_clipboard", None) is not None)
        self.paste_voice_button.setToolTip("Replace selected voice's sound settings. Keep its name, role, mode, mute and MIDI routing. Right-click the voice to undo the last paste. The current voice technique stops.")
        self.paste_voice_button.clicked.connect(lambda: self._paste_voice())
        controls.addWidget(self.paste_voice_button)
        add = QPushButton("+ ADD VOICE"); add.setObjectName("inspectorAddButton"); add.clicked.connect(self._add_voice)
        controls.addWidget(add)
        outer.addLayout(controls)
        creative = QHBoxLayout(); creative.setSpacing(8)
        self.creative_knobs = []
        descriptions = {
            "kit_complexity": ("Complexity", "Adds kick, snare, hat and percussion hits between the core beats."),
            "kit_syncopation": ("Syncopation", "Shifts added hits towards offbeats. Raise Complexity or Toms to hear it."),
            "kit_tom_activity": ("Toms", "Adds tom hits throughout the bar, even when the source pattern is silent. Requires a voice with the Tom role."),
            "kit_variation": ("Variation", "Chooses new weak-beat patterns across bars and phrases; zero repeats the same added pattern. Core beats stay stable."),
        }
        for key, default in CREATIVE_DEFAULTS.items():
            label, tooltip = descriptions[key]
            knob = ParamKnob(creative_value(self.drum, key), default=default)
            knob.bind_parameter(self.drum.id, key)
            knob.setObjectName(key); knob.setAccessibleName(f"Kit {label}")
            knob.setToolTip(tooltip); knob.setFixedWidth(54)
            knob.changed.connect(lambda value, k=key: self.host._set_drum_kit_parameter(self.drum, k, float(value)))
            creative.addWidget(labelled_knob(label, knob)); self.creative_knobs.append(knob)
        creative.addStretch(1)
        self.keep_beat = QCheckBox("Keep beat")
        self.keep_beat.setObjectName("kitKeepBeat")
        self.keep_beat.setChecked(bool(self.drum.parameters.get("kit_protect_anchors", True)))
        self.keep_beat.setToolTip("Restore core beats after rhythm processing and keep the role mask. Disable to let Rotate, Delay and Clock Divide reshape the beat. Shared fill and hat exclusions remain active.")
        self.keep_beat.toggled.connect(lambda checked: self._set_config("kit_protect_anchors", bool(checked)))
        creative.addWidget(self.keep_beat)
        self.new_variant = QPushButton("New variant")
        self.new_variant.setObjectName("kitNewVariant")
        self.new_variant.setToolTip("Generate another reproducible kit pattern with the same meter, roles and settings.")
        self.new_variant.clicked.connect(lambda: self._set_config("kit_variant", int(self.drum.parameters.get("kit_variant", 0)) + 1))
        creative.addWidget(self.new_variant)
        bind_attributes(self, "kit", {"style_selector": "kit_style", "meter_selector": "kit_meter", "phrase_length": "kit_phrase_bars", "keep_beat": "kit_protect_anchors", "new_variant": "kit_variant"})
        outer.addLayout(creative)
        self.rhythm_panel = DrumRhythmPanel(self, ParamKnob, ContrastSpinBox, source_label)
        outer.addWidget(self.rhythm_panel)
        self.update_position()


class MutatorInlineControls(QWidget):
    """One mutation, editable in place without an add/edit dialog."""
    def __init__(self, mutator, block, host, parent=None):
        super().__init__(parent)
        self.mutator, self.block, self.host = mutator, block, host
        self.setObjectName("mutatorRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)
        self.kind = QComboBox()
        self.kind.setMinimumWidth(118)
        self.kind.setAccessibleName("Mutator type")
        self.target = QComboBox()
        targets = ["rhythm", "velocity", "timing"] if block.block_type == "DRUM" else ["rhythm", "pitch", "velocity", "timing"]
        self.target.addItems(targets)
        if mutator.target not in targets:
            self.target.addItem(mutator.target)
            self.target.model().item(self.target.count() - 1).setEnabled(False)
        self.target.setCurrentText(mutator.target)
        self.target.setToolTip("rhythm: hits/rests; pitch: semitones; velocity: 0..1; timing: note gate 0..1.5, not onset. Drum voices keep their assigned MIDI note.")
        self.target.setMinimumWidth(80)
        self.target.setAccessibleName("Mutator target")
        self.amount = ParamKnob(mutator.amount, default=.5)
        self.amount.setFixedWidth(54)
        self.amount.setAccessibleName("Mutator amount")
        self.remove = QPushButton("×")
        self.remove.setObjectName("cardDelete")
        self.remove.setFixedSize(24, 24)
        self.remove.setToolTip("Remove mutator")
        self.remove.setAccessibleName("Remove mutator")
        row.addWidget(self.kind)
        row.addWidget(self.target)
        row.addWidget(self.amount, 0, Qt.AlignTop)
        row.addStretch(1)
        row.addWidget(self.remove, 0, Qt.AlignTop)
        self.kind.currentTextChanged.connect(lambda value: self._changed("name", value))
        self.target.currentTextChanged.connect(lambda value: self._changed("target", value))
        self.amount.changed.connect(lambda value: self._changed("amount", float(value)))
        self.remove.clicked.connect(self._remove)
        self._refresh_types()

    def _refresh_types(self):
        allowed = mutators_for_target(self.mutator.target)
        self.kind.blockSignals(True)
        self.kind.clear()
        self.kind.addItems(allowed)
        if self.mutator.name not in allowed:
            self.kind.addItem(self.mutator.name)
            self.kind.model().item(self.kind.count() - 1).setEnabled(False)
        self.kind.setCurrentText(self.mutator.name)
        self.kind.blockSignals(False)
        valid = self.mutator.name in allowed and not (self.block.block_type == "DRUM" and self.mutator.target == "pitch")
        hint = mutator_help(self.mutator.name, self.mutator.target) if valid else "Bypassed: this mutation is incompatible with its target or the fixed MIDI note of a drum voice."
        self.kind.setToolTip(hint)
        self.amount.setToolTip(hint)
        self.amount.setEnabled(valid)
        bind_help(self.target, "target", "mutation")
        bind_help(self.kind, self.mutator.name, "mutation_type", extra="" if valid else hint)
        bind_help(self.amount, self.mutator.name, "mutation_type", extra="" if valid else hint)

    def _changed(self, field, value):
        # Capture the UI value only. The transport thread owns mutations of
        # the shared Mutator object while playback is active.
        if self.host.get_entity(self.block.id) is not self.block:
            return
        if not any(item is self.mutator for item in self.block.mutators):
            return
        self.host._set_mutator_field(self.block, self.mutator, field, value)

    def _remove(self):
        index = next((i for i, item in enumerate(self.block.mutators) if item is self.mutator), -1)
        if index >= 0 and self.host.get_entity(self.block.id) is self.block:
            self.host.remove_mutator(self.block, index)


class RelationInlineControls(QFrame):
    """An editable signal path, bound to a relation object rather than its index."""
    def __init__(self, relation, editor):
        super().__init__(editor)
        self.relation, self.editor = relation, editor
        self._updating = False
        self.setObjectName("relationRow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(6)

        self.fields = {}
        self.captions = {}
        def add_field(label, widget, stretch=1):
            container = QWidget()
            container.setObjectName('relationControlArea')
            cell = QVBoxLayout(container)
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setSpacing(2)
            caption = QLabel(label)
            caption.setObjectName("muted")
            cell.addWidget(caption, 0, Qt.AlignTop)
            control_area = QWidget()
            control_area.setObjectName("relationControlArea")
            control_area.setFixedHeight(74)
            control_layout = QVBoxLayout(control_area)
            control_layout.setContentsMargins(0, 0, 0, 0)
            alignment = Qt.AlignCenter if isinstance(widget, Knob) else Qt.AlignVCenter
            control_layout.addWidget(widget, 0, alignment)
            cell.addWidget(control_area)
            widget.setAccessibleName(f"Relation {relation.id}: {label}")
            row.addWidget(container, stretch)
            self.fields[label] = container
            self.captions[label] = caption

        self.source = QComboBox()
        self.dest = QComboBox()
        for combo in (self.source, self.dest):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(6)
            combo.setIconSize(QSize(12, 12))
        self.source_part = QComboBox(); self.source_part.addItems(PARTS)
        self.algorithm = QComboBox(); self.algorithm.addItems(RELATIONS)
        self.dest_part = QComboBox(); self.dest_part.addItems(PARTS)
        self.amount = ParamKnob(.5, default=.5)
        self.curve = QComboBox(); self.curve.addItems(["Linear", "Exponential", "Logarithmic", "Threshold", "Quantize"])
        self.delay = QComboBox()
        for label, value in (("Immediate", 0), ("+1 event", 1), ("+2 events", 2), ("+4 events", 4), ("+8 events", 8)):
            self.delay.addItem(label, value)
        self.probability = ParamKnob(1.0, default=1.0)
        self.enabled = QCheckBox("Enabled")
        self.enabled.setAccessibleName(f"Enable relation {relation.id}")
        add_field("Source", self.source, 2)
        add_field("Output", self.source_part)
        add_field("Operation", self.algorithm)
        add_field("Destination", self.dest, 2)
        add_field("Input", self.dest_part)
        add_field("Amount", self.amount)
        add_field("Curve", self.curve)
        add_field("Delay", self.delay)
        add_field("Probability", self.probability)
        add_field("State", self.enabled)
        actions = QVBoxLayout()
        self.duplicate = QPushButton("COPY")
        self.duplicate.setToolTip("Duplicate this relation")
        self.duplicate.setAccessibleName(f"Duplicate relation {relation.id}")
        self.remove = QPushButton("×")
        self.remove.setObjectName("cardDelete")
        self.remove.setToolTip("Remove this relation")
        self.remove.setAccessibleName(f"Remove relation {relation.id}")
        actions.addWidget(self.duplicate)
        actions.addWidget(self.remove)
        row.addLayout(actions)
        layout.addLayout(row)
        self.dialogue = DialogueControls(self, ValueStepper)
        layout.addWidget(self.dialogue)
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.sync()
        for combo in (self.source, self.dest, self.source_part, self.dest_part, self.algorithm, self.curve, self.delay):
            combo.currentIndexChanged.connect(self._changed)
        self.amount.changed.connect(self._changed)
        self.probability.changed.connect(self._changed)
        self.enabled.toggled.connect(self._changed)
        self.remove.clicked.connect(lambda: editor.delete_relation(relation))
        self.duplicate.clicked.connect(lambda: editor.duplicate_relation(relation))

    def sync(self):
        self._updating = True
        try:
            relation = self.relation
            for combo, side in ((self.source, "source"), (self.dest, "destination")):
                block_field = f"{side}_block"
                voice_field = f"{side}_voice_id"
                selected_block = int(getattr(relation, block_field))
                selected_voice = getattr(relation, voice_field, None)
                selected = int(selected_voice) if selected_voice is not None else selected_block
                combo.clear()
                for block in self.editor.project.blocks:
                    swatch = QPixmap(12, 12)
                    swatch.fill(QColor(block_color(self.editor.project, block)))
                    # Keep the legacy numeric block id as item data.  Older
                    # UI code and projects use findData(block_id); a voice is
                    # represented by its own stable negative id.
                    combo.addItem(QIcon(swatch), block.name, int(block.id))
                    combo.setItemData(combo.count() - 1, f"{block.name} · {block.block_type} · ID {block.id}", Qt.ToolTipRole)
                # Keep all ordinary block entries first so legacy UI code can
                # continue to address item 0..N-1 as the block list.  Child
                # voices follow in a second, clearly labelled group.
                for block in self.editor.project.blocks:
                    swatch = QPixmap(12, 12)
                    swatch.fill(QColor(block_color(self.editor.project, block)))
                    for voice in getattr(block, "drum_voices", None) or []:
                        combo.addItem(QIcon(swatch), f"{block.name} / {voice.name}", int(voice.id))
                        combo.setItemData(combo.count() - 1,
                                          f"{block.name} · Drum Voice {voice.name} · MIDI {voice.midi_note} · ID {voice.id}",
                                          Qt.ToolTipRole)
                if combo.findData(selected) < 0:
                    label = f"Missing voice {selected}" if getattr(relation, voice_field, None) is not None else f"Missing block {selected}"
                    combo.addItem(label, selected)
                combo.setCurrentIndex(combo.findData(selected))
            self.source_part.setCurrentText(relation.source_part)
            self.dest_part.setCurrentText(relation.destination_part)
            self.algorithm.setCurrentText(relation.algorithm)
            self.amount.setValue(relation.amount)
            self.curve.setCurrentText(relation.curve)
            if self.delay.findData(relation.delay) < 0:
                self.delay.addItem(f"+{relation.delay} events", relation.delay)
            self.delay.setCurrentIndex(self.delay.findData(relation.delay))
            self.probability.setValue(relation.probability)
            self.enabled.setChecked(relation.enabled)
        finally:
            self._updating = False
        self.apply_theme(active_theme())
        self.update_summary()
        self.dialogue.sync()
        self._sync_operation()

    def apply_theme(self, theme):
        self.setStyleSheet(f"QFrame#relationRow {{ background:{theme.card}; border:1px solid {theme.border}; border-radius:5px; }}"
                           "QWidget#relationControlArea { background:transparent; border:0; }")

    def _sync_operation(self):
        from relation_runtime import RELATION_DESCRIPTIONS
        dialogue = self.relation.algorithm == 'Dialogue'
        description = RELATION_DESCRIPTIONS.get(self.relation.algorithm, '')
        self.algorithm.setToolTip(description)
        for name in ('Output', 'Input', 'Curve', 'Delay'):
            self.fields[name].setVisible(not dialogue)
        self.captions['Amount'].setText('Separation' if dialogue else 'Amount')
        self.captions['Probability'].setText('Cycle chance' if dialogue else 'Probability')
        self.amount.setToolTip('1: strict turns; 0: bypass; intermediate values soften the other instrument.' if dialogue else description)
        self.probability.setToolTip('Probability of using Dialogue for an entire cycle.' if dialogue else 'Relation event probability')
        self.delay.setToolTip('Source steps: SEQ reads earlier pattern positions; LIVE reads previous published attempts. Cycles have at least one step of feedback delay.')
        self.dialogue.setVisible(dialogue)
        if dialogue:
            source = self.editor.host.get_block(self.relation.source_block)
            destination = self.editor.host.get_block(self.relation.destination_block)
            if source and destination:
                self.dialogue.timeline.colors = (block_color(self.editor.project, source), block_color(self.editor.project, destination))
            self.dialogue.update_runtime()
        bind_attributes(self, 'relation')

    def update_summary(self):
        relation = self.relation
        self.source.setToolTip(self.source.currentText())
        self.dest.setToolTip(self.dest.currentText())
        state = "ON" if relation.enabled else "OFF"
        if relation.algorithm == 'Dialogue':
            from instrument_dialogue import settings
            config = settings(relation)
            self.summary.setText(f"#{relation.id} · {state}   {self.source.currentText()} calls → {self.dest.currentText()} responds · "
                                 f"{config['call_bars']} + {config['response_bars']} bars · {config['reply']} · own rhythm")
            return
        self.summary.setText(f"#{relation.id} · {state}   {self.source.currentText()} · {parameter_label(relation.source_part)}"
                             f"  →  {relation.algorithm}  →  {self.dest.currentText()} · {parameter_label(relation.destination_part)}")

    def _changed(self, *_):
        if self._updating or not any(item is self.relation for item in self.editor.host.project.relations):
            return
        if self.source.currentData() is None or self.dest.currentData() is None:
            return
        relation = self.relation
        source_block, source_voice = self._resolve_endpoint(self.source.currentData())
        destination_block, destination_voice = self._resolve_endpoint(self.dest.currentData())
        if source_block is None or destination_block is None:
            return
        values = {
            "source_block": int(source_block),
            "source_voice_id": int(source_voice) if source_voice is not None else None,
            "source_part": self.source_part.currentText(),
            "algorithm": self.algorithm.currentText(),
            "destination_block": int(destination_block),
            "destination_voice_id": int(destination_voice) if destination_voice is not None else None,
            "destination_part": self.dest_part.currentText(),
            "amount": float(self.amount.value()),
            "curve": self.curve.currentText(),
            "delay": int(self.delay.currentData() or 0),
            "probability": float(self.probability.value()),
            "enabled": self.enabled.isChecked(),
        }

        host = self.editor.host
        project_ref = host.project

        def apply_relation_edit():
            if host.project is not project_ref or not any(item is relation for item in project_ref.relations):
                return
            for name, value in values.items():
                setattr(relation, name, value)
            host.engine.apply_relations()

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            apply_relation_edit, key=("relation-edit", int(relation.id)),
            notification={"dirty": True, "relations": True},
            label=f"edit relation {relation.id}"
        )

    def _resolve_endpoint(self, endpoint_id):
        """Map a legacy numeric combo item back to block + optional voice."""
        try:
            wanted = int(endpoint_id)
        except (TypeError, ValueError):
            return None, None
        for block in self.editor.project.blocks:
            if int(block.id) == wanted:
                return int(block.id), None
            for voice in getattr(block, "drum_voices", None) or []:
                if int(voice.id) == wanted:
                    return int(block.id), int(voice.id)
        return None, None


class RelationGraphEditor(QWidget):
    """Scrollable relation inspector: every route is edited in its own row."""
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host, self.project = host, host.project
        self.rows = []
        self._rebuild_pending = False
        self._focus_relation = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel("RELATIONS"); title.setObjectName("pageTitle")
        head.addWidget(title)
        info = QLabel("Add a row, choose blocks and adjust the connection.")
        info.setObjectName("muted")
        head.addWidget(info, 1)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter relations…")
        self.filter_edit.setMaximumWidth(240)
        self.filter_edit.textChanged.connect(self._apply_filter)
        head.addWidget(self.filter_edit)
        layout.addLayout(head)
        builtin = QLabel("Built-in routes: DRUM → BASS groove mask · CHORD → MELODY chord anchor. "
                         "Drum Voices are selectable as KIT / KICK endpoints. An equivalent enabled route replaces the built-in transform.")
        builtin.setObjectName("muted"); builtin.setWordWrap(True)
        layout.addWidget(builtin)
        self.builtin_status = QLabel(); self.builtin_status.setObjectName("muted")
        self.builtin_status.setWordWrap(True)
        layout.addWidget(self.builtin_status)
        inspector = QGroupBox("RELATION INSPECTOR")
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(6, 8, 6, 6)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.page = QWidget()
        self.rows_layout = QVBoxLayout(self.page)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)
        self.rows_layout.setAlignment(Qt.AlignTop)
        self.empty = QLabel("No relations yet. Click + Add to create a connection.")
        self.empty.setObjectName("muted")
        self.rows_layout.addWidget(self.empty)
        self.scroll.setWidget(self.page)
        inspector_layout.addWidget(self.scroll, 1)
        footer = QHBoxLayout()
        self.add_button = QPushButton("+ Add")
        self.add_button.setObjectName("inspectorAddButton")
        self.add_button.setFixedHeight(26)
        self.add_button.setAccessibleName("Add relation")
        self.add_button.clicked.connect(host.add_relation)
        footer.addWidget(self.add_button)
        self.dialogue_button = QPushButton('+ Dialogue')
        self.dialogue_button.setObjectName('inspectorAddButton')
        self.dialogue_button.setFixedHeight(26)
        self.dialogue_button.setAccessibleName('Add Dialogue')
        self.dialogue_button.clicked.connect(lambda: host.add_relation('Dialogue'))
        footer.addWidget(self.dialogue_button)
        footer.addStretch(1)
        self.count_label = QLabel(); self.count_label.setObjectName("muted")
        footer.addWidget(self.count_label)
        inspector_layout.addLayout(footer)
        layout.addWidget(inspector, 1)

    def _queue_rebuild(self, focus=None):
        self._focus_relation = focus
        if self._rebuild_pending:
            return
        self._rebuild_pending = True

        def apply():
            self._rebuild_pending = False
            focus, self._focus_relation = self._focus_relation, None
            self.rebuild(self.host.project)
            if focus is not None:
                # Let the scroll area adopt the new content height first.
                def reveal():
                    row = next((row for row in self.rows if row.relation is focus), None)
                    if row is not None:
                        row.source.setFocus()
                        self.scroll.ensureWidgetVisible(row)
                QTimer.singleShot(0, self, reveal)
        QTimer.singleShot(0, self, apply)

    def add_relation(self, relation):
        host = self.host
        project_ref = self.project

        def add():
            if host.project is not project_ref:
                return
            if not getattr(relation, "id", 0):
                relation.id = next_relation_id(project_ref)
            project_ref.relations.append(relation)
            host.engine.apply_relations()

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            add, key=("relation-add", id(relation)),
            notification={"dirty": True, "relations": True},
            label="add relation"
        )
        self.filter_edit.clear()

    def delete_relation(self, relation):
        host = self.host
        project_ref = self.project

        def remove():
            if host.project is not project_ref or not any(item is relation for item in project_ref.relations):
                return
            project_ref.relations = [item for item in project_ref.relations if item is not relation]
            host.engine.apply_relations()

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            remove, key=("relation-delete", id(relation)),
            notification={"dirty": True, "relations": True},
            label="delete relation"
        )

    def duplicate_relation(self, relation):
        host = self.host
        project_ref = self.project

        def duplicate():
            if host.project is not project_ref:
                return
            index = next((i for i, item in enumerate(project_ref.relations) if item is relation), -1)
            if index < 0:
                return
            duplicate_relation(project_ref, index)
            host.engine.apply_relations()

        host._mark_pending_dirty()
        host.transport.enqueue_gui_command(
            duplicate, key=("relation-duplicate", id(relation)),
            notification={"dirty": True, "relations": True},
            label="duplicate relation"
        )
        self.filter_edit.clear()

    def _apply_filter(self, text):
        query = str(text or "").strip().lower()
        visible = 0
        for row in self.rows:
            haystack = " ".join((row.summary.text(), row.curve.currentText(), row.delay.currentText())).lower()
            match = not query or query in haystack
            row.setVisible(match)
            visible += int(match)
        self.empty.setVisible(not visible)
        self.empty.setText("No matching relations." if self.rows else "No relations yet. Click + Add to create a connection.")
        self.count_label.setText(f"{visible} / {len(self.rows)} relations" if query else f"{len(self.rows)} relations")

    def validate_relations(self):
        return validate_relations(self.project)

    def rebuild(self, project):
        self.project = project
        # Reuse surviving rows: edits, block renames and colour changes do not
        # destroy the focused controls or reassign their relation identity.
        previous = {id(row.relation): row for row in self.rows}
        current = []
        for relation in project.relations:
            row = previous.pop(id(relation), None)
            if row is None:
                row = RelationInlineControls(relation, self)
            else:
                row.sync()
            current.append(row)
        for row in previous.values():
            self.rows_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.rows = current
        for index, row in enumerate(self.rows):
            self.rows_layout.insertWidget(index, row)
        endpoint_count = sum(1 + len(getattr(block, "drum_voices", None) or []) for block in project.blocks)
        self.add_button.setEnabled(endpoint_count >= 2)
        self.dialogue_button.setEnabled(len(project.blocks) >= 2)
        self.add_button.setToolTip("Add a relation" if endpoint_count >= 2 else "Add at least two blocks or Drum Voices first")
        self._apply_filter(self.filter_edit.text())
        self._refresh_builtin_status()

    def update_runtime(self):
        if self.isVisible():
            for row in self.rows:
                if row.isVisible() and row.relation.algorithm == 'Dialogue':
                    row.dialogue.update_runtime()

    def _refresh_builtin_status(self):
        """Show the otherwise implicit role routes in the Relations tab."""
        if not hasattr(self, "builtin_status"):
            return
        lines = []
        for source_type, destination_type, source_part, destination_part, label in (
            ("DRUM", "BASS", "rhythm", "rhythm", "groove mask"),
            ("CHORD", "MELODY", "pitch", "pitch", "chord anchor"),
        ):
            sources = [b for b in self.project.blocks if str(b.block_type).upper() == source_type]
            destinations = [b for b in self.project.blocks if str(b.block_type).upper() == destination_type]
            if not sources or not destinations:
                continue
            for destination in destinations:
                if destination_type == 'MELODY' and self.host.engine.harmonic_runtime.follows(destination):
                    lines.append(f"Harmonic Plan → {destination.name}: chord anchors active")
                    continue
                explicit = [r for r in self.project.relations
                            if getattr(r, "enabled", True)
                            and r.algorithm != 'Dialogue'
                            and int(getattr(r, "destination_block", -1)) == int(destination.id)
                            and str(getattr(r, "destination_part", "")) == destination_part
                            and str(getattr(r, "source_part", "")) == source_part
                            and any(int(getattr(r, "source_block", -1)) == int(source.id) for source in sources)]
                source_names = ", ".join(source.name for source in sources)
                if explicit:
                    route_ids = ", ".join(str(getattr(r, "id", 0) or "?" ) for r in explicit)
                    lines.append(f"{source_type} [{source_names}] → {destination.name}: {label} replaced by route {route_ids}")
                else:
                    lines.append(f"{source_type} [{source_names}] → {destination.name}: {label} active")
        self.builtin_status.setText("Built-in status: " + "   ·   ".join(lines) if lines else "Built-in status: no role pairs in this project")



# Process parameter UI: (key, minimum, maximum, decimals, integer, default).
# "depth" defaults to the process' legacy ``amount`` field.
PROCESS_PARAMETER_SPECS = {
    "Counter": [("length", 1, 64, 0, True, 8), ("step", -8, 8, 2, False, 1.0), ("offset", -64, 64, 2, False, 0.0),
                ("center", -1, 1, 2, False, 0.0), ("phase", 0, 63, 0, True, 0), ("reset", 1, 64, 0, True, 8),
                ("depth", 0, 1, 2, False, None)],
    "Modulo": [("modulus", 1, 64, 0, True, 5), ("offset", -64, 64, 0, True, 0), ("scale", -2, 2, 2, False, 1.0),
               ("center", -1, 1, 2, False, 0.0), ("threshold", 0, 1, 2, False, 0.5), ("depth", 0, 1, 2, False, None)],
    "Compare": [("threshold", -1, 1, 2, False, 0.5), ("true_value", -1, 1, 2, False, 1.0), ("false_value", -1, 1, 2, False, 0.0),
                ("hysteresis", 0, 1, 2, False, 0.0), ("mix", 0, 1, 2, False, 1.0)],
    "Clock Divide": [("factor", 1, 32, 0, True, 2), ("phase", 0, 63, 0, True, 0), ("duty", 0, 1, 2, False, 0.5)],
    "Clock Multiply": [("factor", 1, 32, 0, True, 2), ("phase", 0, 63, 0, True, 0), ("duty", 0, 1, 2, False, 1.0)],
    "Memory": [("delay", 1, 64, 0, True, 1), ("feedback", 0, 1, 2, False, 0.5), ("mix", 0, 1, 2, False, 1.0),
               ("initial", -1, 1, 2, False, 0.0)],
    "Delay": [("delay", 1, 64, 0, True, 1), ("repeats", 1, 32, 0, True, 2), ("feedback", 0, .99, 2, False, 0.5),
              ("mix", 0, 1, 2, False, 0.5), ("decay", 0, 1, 2, False, 0.7), ("initial", -1, 1, 2, False, 0.0)],
    "Feedback": [("feedback", 0, .98, 2, False, 0.5), ("iterations", 1, 32, 0, True, 1), ("decay", 0, 1, 2, False, 1.0),
                 ("mix", 0, 1, 2, False, 1.0), ("bias", -1, 1, 2, False, 0.0), ("clamp", 0, 4, 2, False, 0.0),
                 ("initial", -1, 1, 2, False, 0.0)],
    "Parameter Modulation": [("source_min", -4, 4, 2, False, -1.0), ("source_max", -4, 4, 2, False, 1.0),
                             ("min", -4, 4, 2, False, 0.0), ("max", -4, 4, 2, False, 1.0),
                             ("smoothing", 0, 1, 2, False, 0.0), ("depth", 0, 1, 2, False, None)],
}
# Choice parameters: (key, items). The first item is the engine default.
PROCESS_CHOICE_SPECS = {
    "Counter": [("waveform", ["Ramp", "Triangle", "Sine"])],
    "Modulo": [("mode", ["Add", "Multiply", "Gate"])],
    "Compare": [("operator", [">=", ">", "<", "<=", "=="])],
    "Clock Divide": [("mode", ["Gate", "Hold"])],
    "Clock Multiply": [("mode", ["Gate", "Hold"])],
    "Memory": [("mode", ["Blend", "Replace"])],
    "Delay": [("mode", ["Echo", "Replace", "Gate"])],
}


class ProcessInlineControls(QWidget):
    """All process controls are visible in the main inspector and apply live.

    Building the widgets never writes to the process: only user changes do.
    Double-click on a slider restores the declared default of that parameter.
    """
    def __init__(self, process, project, source_block, parent=None):
        super().__init__(parent)
        self.process = process; self.project = project; self.source_block = source_block; self.host = parent
        grid = QGridLayout(self); grid.setContentsMargins(0, 0, 0, 0); grid.setHorizontalSpacing(4); grid.setVerticalSpacing(4)
        grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.grid = grid; self.index = 0; self._build()

    def _add_cell(self, cell, width=None):
        # Match the compact four-column knob grids used by STRUCTURE/TIMING/MUSICAL.
        # 52 px was too narrow for process labels/controls and caused clipped
        # widgets at normal window sizes.  Process controls need a little more
        # horizontal room while still fitting the compact inspector grid.
        cell.setFixedWidth(82) if width is None else cell.setFixedWidth(int(width))
        self.grid.addWidget(cell, 0, self.index, Qt.AlignLeft | Qt.AlignTop); self.index += 1

    def _changed(self):
        if self.host is not None:
            self.host._process_editor_changed(self.process, self.source_block)

    def _slider(self, key, lo, hi, decimals=2, integer=False, default=None):
        p = self.process.parameters
        if default is None:
            default = self.process.amount
        value = p.get(key, default)
        cell = QWidget(); v = QVBoxLayout(cell); v.setContentsMargins(1,1,1,1); v.setSpacing(0)
        lab = QLabel(parameter_label(key)); lab.setAlignment(Qt.AlignCenter); lab.setObjectName("knobLabel")
        knob = RangeKnob(lo, hi, value, integer, default=default)
        knob.decimals = decimals
        knob._sync_value_label()
        knob.setAccessibleName(parameter_label(key))
        bind_help(knob, key, "process." + self.process.type)
        bind_help(lab, key, "process." + self.process.type)
        knob.changed.connect(lambda x, k=key: self._process_knob_changed(k, x))
        v.addWidget(lab); v.addWidget(knob, 0, Qt.AlignCenter)
        self._add_cell(cell)

    def _process_knob_changed(self, key, value):
        if self.host is not None:
            self.host._set_process_parameter(self.source_block, self.process, key, value)

    def _labeled_cell(self, text, widget, width):
        # Label above the control: side-by-side label+combo in an 82 px cell
        # clipped the combo boxes ("Waveform", "Destination block"...).
        cell = QWidget(); v = QVBoxLayout(cell); v.setContentsMargins(1, 1, 1, 1); v.setSpacing(2)
        lab = QLabel(text); lab.setAlignment(Qt.AlignCenter); lab.setObjectName("knobLabel")
        v.addWidget(lab); v.addWidget(widget); v.addStretch(1)
        widget.setAccessibleName(text)
        self._add_cell(cell, width)

    def _choice(self, key, items):
        cb = QComboBox(); cb.addItems(items)
        current = str(self.process.parameters.get(key, items[0]))
        cb.setCurrentText(current if current in items else items[0])
        cb.currentTextChanged.connect(lambda v, k=key: self._set(k, v))
        bind_help(cb, key, "process." + self.process.type)
        self._labeled_cell(key.replace('_', ' ').title(), cb, 104)

    def _check(self, key):
        cb = QCheckBox(); cb.setChecked(bool(self.process.parameters.get(key, False)))
        cb.toggled.connect(lambda v, k=key: self._set(k, bool(v)))
        bind_help(cb, key, "process." + self.process.type)
        self._labeled_cell(key.replace('_', ' ').title(), cb, 82)

    def _set(self, key, value):
        if self.host is not None:
            self.host._set_process_parameter(self.source_block, self.process, key, value)

    def _build(self):
        kind = self.process.type
        if kind == "Parameter Modulation":
            self._build_route()
        for spec in PROCESS_PARAMETER_SPECS.get(kind, []):
            self._slider(*spec)
        for key, items in PROCESS_CHOICE_SPECS.get(kind, []):
            self._choice(key, items)
        if kind == "Compare":
            self._check("invert")

    def _build_route(self):
        p = self.process.parameters
        dest = QComboBox(); dest.addItem("(none)", -1)
        for b in self.project.blocks:
            dest.addItem(b.name, b.id)
        try:
            wanted = int(p.get('destination_block', -1))
        except (TypeError, ValueError):
            wanted = -1
        dest.setCurrentIndex(max(0, dest.findData(wanted)))
        bind_help(dest, 'destination_block', 'process')
        self._labeled_cell('Destination', dest, 140)
        param = QComboBox(); self._fill_params(param, dest, p.get('destination_parameter', 'fill_density'))
        bind_help(param, 'destination_parameter', 'process')
        self._labeled_cell('Parameter', param, 140)
        dest.currentIndexChanged.connect(lambda _: self._route_changed(dest, param))
        param.currentIndexChanged.connect(lambda _: self._route_param(param))

    def _fill_params(self, cb, dest, wanted):
        cb.blockSignals(True)
        cb.clear()
        b = next((x for x in self.project.blocks if x.id == dest.currentData()), None)
        if b:
            for key in sorted(MusicEngine.parameter_catalog(b)):
                cb.addItem(parameter_label(key), key)
            j = cb.findData(wanted)
            if j >= 0:
                cb.setCurrentIndex(j)
        cb.blockSignals(False)

    def _route_changed(self, dest, param):
        self._set('destination_block', dest.currentData())
        self._fill_params(param, dest, self.process.parameters.get('destination_parameter', 'fill_density'))
        self._route_param(param)

    def _route_param(self, param):
        if param.currentData() is not None:
            self._set('destination_parameter', param.currentData())


class AlgorithmPreviewWidget(QWidget):
    """Small schematic 16-step signal preview; dots show event activity only."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.block = None
        self.project = None
        self.setMinimumHeight(52)
        self.setMaximumHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_block(self, block, project):
        self.block = block
        self.project = project
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect(); pal = self.palette()
        bg = pal.base().color(); fg = pal.text().color(); grid = pal.mid().color(); accent = pal.highlight().color()
        p.fillRect(r, bg)
        b = self.block
        left, top, right, bottom = 8, 7, 8, 12
        w = max(40, r.width() - left - right)
        h = max(20, r.height() - top - bottom)
        n = 16; stepw = w / n
        rhythm = list(b.outputs.get("rhythm", []) or [])[:n] if b else []
        pitch = list(b.outputs.get("pitch", []) or [])[:n] if b else []
        velocity = list(b.outputs.get("velocity", []) or [])[:n] if b else []
        active = [i for i in range(n) if i < len(rhythm) and abs(float(rhythm[i])) > 0.001]
        if not active and b is not None:
            active = [0]
        pitch_vals = [float(pitch[i]) for i in active if i < len(pitch)]
        plo, phi = (min(pitch_vals), max(pitch_vals)) if pitch_vals else (0.0, 1.0)
        pspan = max(1e-6, phi - plo)
        # Four-beat grouping and 16 event positions.
        for i in range(n + 1):
            x = left + i * stepw
            p.setPen(QPen(grid, 2 if i % 4 == 0 else 1))
            p.drawLine(int(x), top, int(x), top + h)
        p.setPen(QPen(grid, 1))
        p.drawLine(left, top + h/2, left + w, top + h/2)
        for i in range(n):
            x = left + (i + 0.5) * stepw
            if i in active:
                pv = float(pitch[i]) if i < len(pitch) else 0.0
                y = top + h - ((pv - plo) / pspan if pspan else 0.5) * (h - 8) - 4
                vel = float(velocity[i]) if i < len(velocity) else 0.8
                rad = 2.5 + 2.5 * max(0.0, min(1.0, vel))
                c = QColor(accent); c.setAlpha(210)
                p.setPen(Qt.NoPen); p.setBrush(QBrush(c)); p.drawEllipse(QPointF(x, y), rad, rad)
            else:
                c = QColor(grid); c.setAlpha(120)
                p.setPen(Qt.NoPen); p.setBrush(QBrush(c)); p.drawEllipse(QPointF(x, top + h/2), 1.4, 1.4)
        p.setPen(QPen(fg, 1))
        title = f"PREVIEW · 16 · {b.algorithm}" if b else "PREVIEW · 16"
        p.drawText(left, r.height() - 12, w, 12, Qt.AlignLeft | Qt.AlignVCenter, title)
        p.end()


class PianoRollWidget(QWidget):
    """MIDI history in a fixed, user-selected number of sixteenth-note steps."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.block = None
        self.project = None
        self.history = []
        self.pattern_seconds = 2.0
        self.seq_interval = 0.125
        self.running = False
        self.view_steps = 16
        self.frozen = False
        self.frozen_history = []
        self.frozen_at = 0.0
        # Anchor the visible history window when playback stops.  Without a
        # fixed time origin, paintEvent keeps using wall-clock time and the
        # piano roll appears to run on after STOP while its time scale shrinks.
        self.stopped_at = None
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self._keyboard_geometry = None
        self.setAccessibleName("MIDI piano roll; note labels use C4 = MIDI 60")

    def set_view_steps(self, steps):
        self.view_steps = max(1, min(4096, int(steps)))
        self.update()

    @property
    def view_seconds(self):
        return self.view_steps * self.seq_interval

    @staticmethod
    def note_label(note):
        return f"{NOTE_NAMES[int(note) % 12]}{int(note) // 12 - 1}"

    def _keyboard_note_at(self, position):
        if self._keyboard_geometry is None:
            return None
        lo, hi, top, height, right = self._keyboard_geometry
        if 3 <= position.x() <= right and top <= position.y() < top + height:
            return hi - int((position.y() - top) * (hi - lo + 1) / height)
        return None

    def mouseMoveEvent(self, event):
        note = self._keyboard_note_at(event.position())
        self.setToolTip(f"{self.note_label(note)} · MIDI {note}" if note is not None else "")
        super().mouseMoveEvent(event)

    def set_data(self, block, history=None, pattern_seconds=None, seq_interval=None, running=False, project=None):
        if project is not None:
            self.project = project
        if self.frozen:
            self.block = block
            return
        was_running = self.running
        self.block = block
        self.history = list(history or [])
        if pattern_seconds is not None:
            self.pattern_seconds = max(0.05, float(pattern_seconds))
        if seq_interval is not None:
            self.seq_interval = max(0.005, float(seq_interval))
        self.running = bool(running)
        if self.running:
            # A new playback run gets a fresh moving time origin.
            self.stopped_at = None
        elif was_running:
            # Capture the exact STOP transition once.  Subsequent idle refreshes
            # must not move the playhead or change the displayed time scale.
            self.stopped_at = time.monotonic()
        elif self.stopped_at is None:
            # Initial/stopped Inspector construction: anchor to the latest
            # known event, not to a clock that continues advancing in the UI.
            stamps = [float(item[0]) for item in self.history if len(item) >= 3]
            self.stopped_at = max(stamps) if stamps else time.monotonic()
        self.update()

    def _display_time(self):
        """Return a stable time origin while stopped or frozen."""
        if self.frozen:
            return float(self.frozen_at)
        if self.running:
            return time.monotonic()
        if self.stopped_at is not None:
            return float(self.stopped_at)
        stamps = [float(item[0]) for item in self.history if len(item) >= 3]
        return max(stamps) if stamps else time.monotonic()

    def set_frozen(self, value, snapshot=None):
        """FREEZE keeps the currently visible history *and* its time base."""
        value = bool(value)
        if value and not self.frozen:
            if snapshot is not None:
                self.frozen_history = list(snapshot[0])
                self.frozen_at = float(snapshot[1])
                if len(snapshot) > 2:
                    self.seq_interval = float(snapshot[2])
            else:
                self.frozen_at = self._display_time()
                # Retain the bounded input history so Length can also be
                # adjusted while frozen, without changing the time anchor.
                self.frozen_history = list(self.history)
        self.frozen = value
        if not value:
            self.frozen_history = []
        self.update()

    def snapshot(self):
        return (list(self.frozen_history), self.frozen_at, self.seq_interval) if self.frozen else None

    def _generated_events(self):
        b = self.block
        if not b:
            return []
        if str(getattr(b, "block_type", "")).upper() == "DRUM" and getattr(b, "drum_voices", None):
            events = []
            for voice in b.drum_voices:
                rhythm = voice.outputs.get("rhythm", []) or []
                velocity = voice.outputs.get("velocity", []) or []
                duration = voice.outputs.get("duration", []) or []
                pitch = voice.outputs.get("pitch", []) or []
                for i, value in enumerate(rhythm):
                    if float(value) <= 0.001:
                        continue
                    note = midi_note_for(self.project, voice, pitch[i] if i < len(pitch) else 0.0)
                    vel = float(velocity[i] if i < len(velocity) else .8)
                    dur = float(duration[i] if i < len(duration) else voice.parameters.get("gate", .78))
                    events.append((i, note, max(.05, dur), max(.05, min(1.0, vel))))
            return events
        rhythm = b.outputs.get('rhythm', []) or []
        pitch = b.outputs.get('pitch', []) or []
        velocity = b.outputs.get('velocity', []) or []
        duration = b.outputs.get('duration', []) or []
        events = []
        if rhythm:
            for i, r in enumerate(rhythm):
                if float(r) <= 0.001:
                    continue
                vel = float(velocity[i] if i < len(velocity) else .8)
                dur = float(duration[i] if i < len(duration) else b.parameters.get('gate', .78))
                root_pitch = pitch[i] if i < len(pitch) else 0.0
                if str(getattr(b, "block_type", "")).upper() in ("CHORD", "PAD"):
                    engine = getattr(self, "engine", None)
                    tones = engine._chord_pitches(b, root_pitch) if engine is not None else [root_pitch]
                    for tone in tones:
                        events.append((i, midi_note_for(self.project, b, tone), max(.05, dur), max(.05, min(1.0, vel))))
                else:
                    events.append((i, midi_note_for(self.project, b, root_pitch), max(.05, dur), max(.05, min(1.0, vel))))
        return events

    def _history_events(self, now=None):
        now = self._display_time() if now is None else float(now)
        start = now - self.view_seconds
        history = self.frozen_history if self.frozen else self.history
        return [(float(t), int(note), float(vel)) for t, note, vel in history
                if start <= float(t) <= now]

    def paintEvent(self, event):
        p = QPainter(self)
        r = self.rect()
        pal = self.palette()
        bg = pal.base().color()
        fg = pal.text().color()
        grid = pal.mid().color()
        accent = pal.highlight().color()
        p.fillRect(r, bg)

        left, top, right, bottom = 58, 20, 8, 20
        w = max(20, r.width() - left - right)
        h = max(20, r.height() - top - bottom)
        history_events = self._history_events()
        use_history = self.running or bool(self.history) or bool(self.frozen_history)

        if use_history:
            notes = [e[1] for e in history_events]
        else:
            generated = [item for item in self._generated_events() if item[0] < self.view_steps]
            notes = [e[1] for e in generated]

        if notes:
            lo = max(0, min(notes) - 2)
            hi = min(127, max(notes) + 2)
        else:
            center = max(0, min(127, int(getattr(self.block, "midi_note", 60))))
            lo, hi = max(0, center - 6), min(127, center + 6)
        # Include both endpoint keys so the highest row stays inside the plot.
        span = max(1, hi - lo + 1)

        # Pitch grid + compact piano keyboard.
        white_names = {0, 2, 4, 5, 7, 9, 11}
        key_left, key_right = 3, left - 5
        self._keyboard_geometry = (lo, hi, top, h, key_right)
        font = p.font()
        label_font = p.font(); label_font.setPixelSize(max(8, min(11, int(h / span) - 2)))
        p.setFont(label_font)
        label_height = p.fontMetrics().height()
        label_notes = []
        # Dense ranges prioritise sounding notes and octave markers instead
        # of overlapping labels. Every key also has its full name on hover.
        for note in sorted(range(lo, hi + 1), key=lambda n: (n not in notes, n % 12 != 0, n)):
            if all(abs(note - other) * h / span >= label_height for other in label_notes):
                label_notes.append(note)
        for note in range(hi, lo - 1, -1):
            y0 = top + h - (note - lo + 1) / span * h
            y1 = top + h - (note - lo) / span * h
            is_white = (note % 12) in white_names
            key_rect = QRectF(key_left, y0, key_right-key_left, max(1.0, y1-y0))
            p.setPen(QPen(QColor("#66707c"), 1))
            p.setBrush(QBrush(QColor("#e8ebef") if is_white else QColor("#242a31")))
            p.drawRect(key_rect)
            if note in label_notes:
                p.setPen(QColor("#26313d") if is_white else QColor("#edf2f7"))
                text_rect = QRectF(key_left + 3, (y0 + y1 - label_height) / 2, key_right - key_left - 6, label_height)
                p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignRight, self.note_label(note))
            p.setPen(QPen(QColor("#555f6b") if note % 12 == 0 else grid, 1))
            p.drawLine(left, int(y1), left + w, int(y1))
        p.setFont(font)
        if not notes:
            p.setPen(grid)
            p.drawText(left + 8, top + 25, "No MIDI notes in this window")

        # The same musical scale is used for generated previews and history.
        # Thin out grid lines in long views instead of painting thousands.
        count = self.view_steps
        stepw = w / count
        stride = max(1, math.ceil(count * 8 / w))
        for i in range(0, count + 1, stride):
            x = left + i * stepw
            p.setPen(QPen(grid, 1 if i % 4 else 2))
            p.drawLine(int(x), top, int(x), top + h)
        p.save()
        p.setClipRect(QRectF(left, top, w, h))
        if use_history:
            now = self._display_time()
            display_seconds = self.view_seconds
            start = now - display_seconds
            # Current playhead is always at the right edge.
            p.setPen(QPen(accent, 2))
            p.drawLine(left + w - 1, top, left + w - 1, top + h)

            for t, note, vel in history_events:
                x = left + ((t - start) / display_seconds) * w
                # Use the transport step duration as a compact note width.
                ww = max(3.0, min(w * .18, w * self.seq_interval / display_seconds * .82))
                y = top + h - (note - lo + 1) / span * h
                hh = max(4.0, h / span * .8)
                color = QColor(accent)
                color.setAlpha(90 + int(150 * max(.0, min(1.0, vel))))
                p.setBrush(QBrush(color))
                p.setPen(QPen(accent, 1))
                p.drawRoundedRect(int(x), int(y), int(ww), int(hh), 2, 2)
            count_text = f"{len(history_events)} events" + (" · FROZEN" if self.frozen else "")
        else:
            for pos, note, dur, vel in generated:
                x = left + pos * stepw + 1
                ww = max(3, min(w / count * max(.5, dur), w))
                y = top + h - (note - lo + 1) / span * h
                hh = max(4, h / span * .8)
                color = QColor(accent)
                color.setAlpha(90 + int(150 * vel))
                p.setBrush(QBrush(color))
                p.setPen(QPen(accent, 1))
                p.drawRoundedRect(int(x), int(y), int(max(3, ww)), int(hh), 2, 2)
            count_text = f"generated pattern · {len(generated)} events"
        p.restore()
        p.setPen(QPen(grid, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(left, top, w, h)
        p.setPen(QPen(fg, 1))
        title = self.block.name if self.block else "Block"
        p.drawText(left, 14, f"{title} · {count} steps · {self.view_seconds:g}s · {count_text}")
        p.end()


class MainWindow(QMainWindow):
    # Transport.tick() runs on the real-time worker.  These signals marshal
    # diagnostics and history updates back to the Qt GUI thread; touching a
    # QLabel, QTimer or monitor widget directly from the MIDI thread is not
    # safe and caused intermittent crashes during PLAY.
    _midi_message_signal = Signal(object, object, object, object)
    _midi_input_signal = Signal(str, object)
    _midi_input_event_signal = Signal(object)
    _generated_event_signal = Signal(object, object, object, object)
    _status_message_signal = Signal(str)
    _transport_command_applied_signal = Signal(object)

    def __init__(self):
        super().__init__()
        self._midi_message_signal.connect(self._handle_midi_message)
        self._midi_input_signal.connect(self._handle_midi_input, Qt.QueuedConnection)
        self._generated_event_signal.connect(self._handle_generated_event)
        self._status_message_signal.connect(self._show_status_message)
        self._transport_command_applied_signal.connect(self._handle_transport_command_applied)
        self.setWindowTitle("Auricle — Algorithmic Music Generator")
        self.setWindowIcon(application_icon())
        screen = self.screen() or QApplication.primaryScreen()
        geometry = initial_window_geometry(screen.availableGeometry())
        self.setMinimumSize(min(820, geometry.width()), min(520, geometry.height()))
        self.setGeometry(geometry)
        self.project = Project()
        self._dirty = False
        self._seed_project()
        ensure_global_macros(self.project)
        self.engine = MusicEngine(self.project)
        self._automation_structure_seen = (id(self.engine), 0)
        self.transport = Transport(self)
        self.selected_block_id = self.project.blocks[0].id if self.project.blocks else None
        self.selected_drum_voice_id = None
        self._midi_events = {}
        self._generated_live_events = {}
        self._piano_freeze = None  # (events, timestamp, step interval) while frozen
        self._view_settings = QSettings("Auricle", "Auricle")
        try:
            self._piano_length_steps = max(1, min(4096, int(
                self._view_settings.value("piano_roll/length_steps", 16))))
        except (TypeError, ValueError, OverflowError):
            self._piano_length_steps = 16
        self.current_path = None
        self._midi_pulse_at = {}
        self._midi_indicator_on = {}
        self._monitor_buffer = []
        self._midi_output_names = []
        self._midi_output_error = None
        self._midi_input_port = None
        self._midi_input_name = ""
        self._midi_input_stop = None
        self._midi_input_thread = None
        self._midi_input_session = None
        self._midi_input_error = ""
        self._midi_diagnostics = MidiInputDiagnostics()
        self._midi_runtime_identity = None
        self._midi_input_available_names = []
        self._midi_input_event_count = 0
        self._midi_learn_target = None
        self._midi_learn_runtime = MidiLearnRuntime()
        self._global_macro_generation_queued = False
        self._pending_param_edits = {}
        self._pending_param_edits_lock = threading.Lock()
        self._build_ui()
        self._apply_style()
        self._inspector_columns = 2
        self._inspector_state = {}
        self._port_change_pending: set[int] = set()
        self._block_type_change_pending: dict[int, int] = {}
        self._inspector_generation = 0
        self._refresh_all()
        if hasattr(self, "midi_sync_button"):
            sync = normalize_midi_sync(self.project.midi_sync)
            self.midi_sync_button.setText("SYNC ON" if sync["clock_out"] or sync["transport_messages"] else "SYNC")
        self.performance.phrase_panel._save_settings()
        self.history_controller = HistoryController(self)

        # MIDI transport clock.  v6 accidentally lost the Qt timer that
        # drives Transport.tick(), so PLAY opened MIDI ports but never
        # advanced the transport. Keep the transport independent from the
        # widget refresh cycle and drive it at 5 ms resolution.
        # v103.1: MIDI transport is no longer driven by the Qt GUI loop.
        from transport_worker import TransportWorker
        self.transport_worker = TransportWorker(self.transport)
        self.transport_worker.start()
        self._sync_midi_input_port()
        self.performance_timer = QTimer(self)
        self.performance_timer.setInterval(80)
        self.performance_timer.timeout.connect(self._refresh_runtime_ui)
        self.performance_timer.start()
        self._sync_transport_buttons()

    def _refresh_runtime_ui(self):
        """Refresh visible views from a consistent runtime state without waiting.

        The non-blocking transport lock replaces the old GUI-only lock, which
        the scheduler did not acquire and therefore did not protect these reads.
        """
        self._sync_transport_buttons()
        self._flush_monitor()
        now = time.monotonic()
        running = bool(self.transport.running)
        state = (running, self.transport.playback_mode)
        state_changed = state != getattr(self, "_runtime_view_state", None)
        # Static controls need no 12.5-Hz polling while stopped. Buttons above
        # still follow the 80-ms heartbeat and edits update their own previews.
        if not running and not state_changed and now - getattr(self, "_idle_view_refresh_at", 0.) < .25:
            return
        lock = self.transport._transport_lock
        if not lock.acquire(blocking=False):
            return
        state_lock = self.transport._state_lock
        if not state_lock.acquire(blocking=False):
            lock.release()
            return
        try:
            self._idle_view_refresh_at = now
            self._runtime_view_state = state
            structure = (id(self.engine), self.engine.section_automation.structure_serial)
            previous_structure = getattr(self, "_automation_structure_seen", structure)
            if structure[0] == previous_structure[0] and structure[1] != previous_structure[1]:
                self._queue_inspector_refresh()
                self._refresh_blocks()
            self._automation_structure_seen = structure
            if self.performance.isVisible():
                self.performance.update_activity(self.project, running)
            elif self.performance.director_panel.isVisible():
                self.performance.director_panel.refresh()
            roll = getattr(self, "piano_roll", None)
            if roll is not None and isValid(roll) and roll.isVisible():
                self._update_piano_roll()
            if self.inspector_scroll.isVisible():
                self._update_motif_status()
                self._update_kit_status()
            if self.performance.harmonic_panel.isVisible():
                self.performance.harmonic_panel.update_runtime()
            if self.relation_graph.isVisible():
                self.relation_graph.update_runtime()
            if self.composition_panel.isVisible() or state_changed:
                self.composition_panel.update_runtime()
            self._update_parameter_sources()
        finally:
            state_lock.release()
            lock.release()

    def _seed_project(self):
        self.project.blocks = [
            Block(1, "DRUM", "DRUM", "Euclidean", "SEQ", 1, "", 60, {"pulses": 5, "gate": 0.78}),
            Block(2, "BASS", "BASS", "Random Walk", "SEQ", 2, "", 60, {"gate": 0.78}),
            Block(3, "MELODY", "MELODY", "Markov", "LIVE", 3, "", 60,
                  {"live_min_beats": .18, "live_max_beats": .65, "live_gate": .72, "gate": .72}),
        ]
        for b in self.project.blocks:
            apply_role_defaults(b)
        ensure_drum_voices(self.project.blocks[0])
        self.project.relations = [
            Relation(1, "rhythm", 2, "rhythm", "Modulate", .35, id=1),
            Relation(2, "pitch", 3, "pitch", "Follow", .30, id=2),
        ]

    def _harmony_changed(self, *_):
        # Header controls are Qt-owned; commit their model changes on the
        # transport thread so a running generator never observes half-updated
        # global harmony and per-block scale settings.
        octave = self.project.root_note // 12 if self.project.root_note >= 12 else 5
        root_note = octave * 12 + self.key.currentIndex()
        scale = self.scale.currentText()

        def apply_harmony():
            self.project.root_note = root_note
            self.project.scale = scale
            for block in self.project.blocks:
                if block.algorithm in ("Markov", "Random Walk", "Interval Walker", "Scale Walker", "Weighted Scale", "Arpeggiator", "Fibonacci", "Recaman", "De Bruijn", "Cellular Automaton", "L-System", "Logistic Chaos", "Turing Machine", "Orbital Sequence", "Geometry Collision"):
                    block.parameters["scale_root"] = root_note
                    block.parameters["scale_name"] = scale
            self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_harmony, key=("global-harmony",),
            notification={"dirty": True, "refresh": "SOURCE"}, label="global harmony edit"
        )

    def _handle_transport_command_applied(self, payload):
        """Apply GUI-only follow-up after a queued model edit has committed."""
        if not isinstance(payload, dict):
            return
        if payload.get("dirty", True):
            self._mark_dirty()
        if payload.get("macros"):
            if hasattr(self, "global_macro_bar"):
                self.global_macro_bar.refresh_from_project()
            panel = getattr(getattr(self, "performance", None), "macro_panel", None)
            if panel is not None:
                panel.refresh_from_project()
        if payload.get("refresh_all"):
            self._refresh_all()
        elif payload.get("blocks"):
            self._refresh_blocks()
            if hasattr(self, "performance"):
                self.performance.refresh_blocks(self.project)
        if payload.get("relations"):
            self._refresh_relations()
            if hasattr(self, "relation_graph"):
                self.relation_graph.update_runtime()
        block_id = payload.get("block_id")
        if block_id is not None:
            block = self.get_entity(block_id)
            if block is not None:
                if (payload.get("mutation_summary") and self._selected_inspector_entity() is block):
                    group = self.inspector_page.findChild(InspectorGroup, "inspectorGroup_MUTATION")
                    if group is not None:
                        group.set_summary(" · ".join(f"{m.name} {m.amount:.2f}" for m in block.mutators) or "none")
                # A MIDI edit changes the model without calling Knob.setValue().
                # Deliver the committed values directly, including collapsed
                # controls and the persistent kit, rather than relying on a
                # visible source caption and the runtime polling timer.
                feedback = payload.get("parameter_feedback", {})
                page = getattr(self, "inspector_page", None)
                if (feedback and payload.get("parameter_entity") is block
                        and page is not None and isValid(page)):
                    for knob in page.findChildren(Knob):
                        binding = getattr(knob, "_auricle_parameter", None)
                        if binding is not None and binding[0] == block_id:
                            value = feedback.get(binding[1])
                            if value is not None:
                                knob.set_runtime_value(value.manual, value.effective)
                self._update_algorithm_preview(block)
        refresh = payload.get("refresh")
        if refresh:
            self._queue_inspector_refresh(str(refresh))
        if payload.get("midi_sync") and hasattr(self, "midi_sync_button"):
            sync = normalize_midi_sync(self.project.midi_sync)
            self.midi_sync_button.setText("SYNC ON" if sync["clock_out"] or sync["transport_messages"] else "SYNC")
        if payload.get("performance") and hasattr(self, "performance"):
            self.performance.update_activity(self.project, self.transport.running)
            self.performance.phrase_panel.update_runtime()
            self._sync_transport_buttons()
        if payload.get("message"):
            self.set_message(str(payload["message"]))

    def set_message(self, message):
        # AutoConnection is direct on the GUI thread and queued when this is
        # called by TransportWorker, so statusBar() is always accessed by Qt's
        # owner thread.
        self._status_message_signal.emit(str(message))

    def _show_status_message(self, message):
        self.statusBar().showMessage(message, 3000)

    def _mark_pending_dirty(self):
        """Show pending edits as unsaved before their transport commit lands."""
        if getattr(self, "_installing_project", False):
            return
        self._dirty = True
        self._update_title()

    def _mark_dirty(self):
        """Mark the project changed and keep the title honest."""
        if getattr(self, "_installing_project", False):
            return
        self._dirty = True
        self._update_title()
        if hasattr(self, "history_controller"):
            self.history_controller.changed()

    def _set_global_macro(self, index, value, source=None):
        """Queue global macro changes and coalesce rapid slider movement."""
        if not 0 <= int(index) < len(GLOBAL_MACRO_DEFS):
            return
        index = int(index)
        value = max(0.0, min(1.0, float(value)))

        def apply_macro():
            macros = ensure_global_macros(self.project)
            macro = macros[index]
            macro["value"] = value
            control = str(macro.get("control", GLOBAL_MACRO_DEFS[index][1]))
            self.engine.director.set_global_macro(control, value)
            self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_macro, key=("global-macro", index),
            notification={"dirty": True, "macros": True}, label=f"global macro {index + 1}"
        )

    def _flush_global_macro(self):
        # Retained for compatibility with older queued callbacks.
        self._global_macro_generation_queued = False
        self.transport.enqueue_gui_command(
            self.engine.generate, key=("global-macro-regenerate",),
            notification={"dirty": False}, label="global macro regeneration"
        )

    def _set_drum_kit_parameter(self, drum, key, value):
        # A continuous kit edit needs model/preview feedback, not a full
        # Inspector rebuild for every movement of the mouse or controller.
        self._set_param(drum, key, max(0.0, min(1.0, float(value))))

    def _flush_drum_kit(self, drum):
        # Compatibility shim for pre-queue callbacks.
        self.transport.enqueue_gui_command(
            lambda: self.engine.regenerate(drum) if any(b is drum for b in self.project.blocks) else None,
            key=("drum-kit-regenerate", int(drum.id)),
            notification={"dirty": False, "block_id": int(drum.id)},
            label=f"drum kit regenerate {drum.id}"
        )

    def _confirm_discard_changes(self):
        """Return whether a destructive navigation may replace this project."""
        if not getattr(self, "_dirty", False):
            return True
        choice = QMessageBox.warning(
            self,
            "Unsaved changes",
            "The current project has unsaved changes.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if choice == QMessageBox.Save:
            return bool(self.save_project())
        return choice == QMessageBox.Discard

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(6, 5, 6, 4)
        outer.setSpacing(4)

        # Global transport / musical context bar stays visible on every tab.
        top = QHBoxLayout(); top.setSpacing(10)
        logo = LogoLabel()
        self.brand_logo = logo
        logo.setObjectName("brandLogo")
        logo.setFixedSize(58, 54)
        logo.setAlignment(Qt.AlignCenter)
        logo.setToolTip("Auricle — Algorithmic Music Generator")
        logo.refresh()
        top.addWidget(logo)
        # Navigation and global musical controls live in the window header so
        # the four macros remain available on every tab.
        self.header_nav = SourceTabBar()
        self.header_nav.setObjectName("headerNavigation")
        self.header_nav.setExpanding(False)
        self.header_nav.setUsesScrollButtons(True)
        self.header_nav.setDrawBase(False)
        self.header_nav.setIconSize(QSize(TAB_ICON_SIZE, TAB_ICON_SIZE))
        self.header_nav.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header_nav.setAccessibleName("Main navigation")
        self.global_macro_bar = GlobalMacroBar(self)
        # Transport controls use the standard media glyphs so their meaning is
        # immediately recognisable without consuming header width with labels.
        self.play = QPushButton(); self.play.setObjectName("transportPlay"); self.play.setCheckable(True)
        self.play.setIcon(transport_icon("play", "#ffffff"))
        self.play.setIconSize(QSize(22, 22)); self.play.setFixedSize(TRANSPORT_WIDTH, TRANSPORT_HEIGHT)
        self.play.setAccessibleName("Play")
        self.stop = QPushButton(); self.stop.setObjectName("transportStop")
        self.stop.setIcon(transport_icon("stop", "#ffffff"))
        self.stop.setIconSize(QSize(22, 22)); self.stop.setFixedSize(TRANSPORT_WIDTH, TRANSPORT_HEIGHT)
        self.stop.setAccessibleName("Stop")
        self.play.setToolTip("Play Blocks for setup, without Composition or Perform (Space)")
        self.stop.setToolTip("Stop all playback and release Auricle notes (Space)")
        self.play.clicked.connect(self._play_clicked)
        self.stop.clicked.connect(self._stop_clicked)
        top.addWidget(self.play); top.addWidget(self.stop)
        top.addSpacing(6)
        self._transport_fields = []
        def add_transport_field(caption, field, width):
            group = QHBoxLayout()
            group.setSpacing(6)
            label = QLabel(caption)
            label.setObjectName("transportLabel")
            group.addWidget(label)
            field.setObjectName("transportField")
            field.setFixedSize(width, TRANSPORT_HEIGHT)
            if isinstance(field, ValueStepper):
                field.minus.setFixedSize(24, TRANSPORT_HEIGHT)
                field.plus.setFixedSize(24, TRANSPORT_HEIGHT)
                field.editor.setFixedHeight(TRANSPORT_HEIGHT)
            group.addWidget(field)
            top.addLayout(group)
            self._transport_fields.append((group, label))

        self.tempo = ContrastSpinBox(); self.tempo.setRange(20, 300); self.tempo.setValue(self.project.tempo)
        self.tempo.valueChanged.connect(self._tempo_changed)
        add_transport_field("BPM", self.tempo, 90)
        self.tempo.set_accessible_label("Tempo (BPM)")
        self.length = ContrastSpinBox(); self.length.setRange(1, 128); self.length.setValue(self.project.length)
        self.length.valueChanged.connect(self._length_changed)
        add_transport_field("LENGTH", self.length, 90)
        self.length.set_accessible_label("Pattern length (steps)")
        self.key = QComboBox(); self.key.addItems(NOTE_NAMES); self.key.setCurrentIndex(self.project.root_note % 12)
        self.key.currentIndexChanged.connect(self._harmony_changed)
        add_transport_field("KEY", self.key, 64)
        self.key.setAccessibleName("Key")
        self.scale = QComboBox(); self.scale.addItems(SCALES); self.scale.setCurrentText(self.project.scale)
        self.scale.currentTextChanged.connect(self._harmony_changed)
        add_transport_field("SCALE", self.scale, 174)
        self.scale.setAccessibleName("Scale")
        top.addStretch()
        self.theme_label = QLabel("THEME")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(theme_names())
        self.theme_combo.setFixedWidth(105)
        self.theme_combo.currentTextChanged.connect(self._theme_changed)
        self.midi_status = QLabel("MIDI")
        self.midi_learn_button = QPushButton("MIDI IN")
        self.midi_learn_button.setObjectName("midiSyncButton")
        self.midi_learn_button.setFixedWidth(76)
        self.midi_learn_button.setToolTip("Connect a MIDI input and manage MIDI Learn mappings")
        self.midi_learn_button.clicked.connect(self._open_midi_learn_dialog)
        self.midi_sync_button = QPushButton("SYNC")
        self.midi_sync_button.setObjectName("midiSyncButton")
        self.midi_sync_button.setToolTip("Configure global MIDI Clock, Start/Stop/Continue and Song Position Pointer output")
        self.midi_sync_button.clicked.connect(self._open_midi_sync_dialog)
        outer.addLayout(top)
        macro_row = QHBoxLayout()
        macro_row.setSpacing(5)
        macro_row.addWidget(self.global_macro_bar, 1)
        outer.addLayout(macro_row)
        nav_row = QHBoxLayout()
        nav_row.setSpacing(5)
        nav_row.addWidget(self.header_nav, 1)
        for widget in (self.theme_label, self.theme_combo, self.midi_status,
                       self.midi_learn_button, self.midi_sync_button):
            nav_row.addWidget(widget, 0, Qt.AlignVCenter)
        outer.addLayout(nav_row)

        self.tabs = QTabWidget()
        self.tabs.setIconSize(QSize(TAB_ICON_SIZE, TAB_ICON_SIZE))
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs, 1)

        # --- BLOCKS TAB ---------------------------------------------------
        blocks_tab = QWidget()
        blocks_layout = QHBoxLayout(blocks_tab)
        blocks_layout.setContentsMargins(0, 3, 0, 0)
        blocks_layout.setSpacing(4)

        splitter = QSplitter(Qt.Horizontal)
        self.blocks_splitter = splitter
        splitter.setChildrenCollapsible(False)
        blocks_layout.addWidget(splitter)

        left = QWidget(); lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 6, 0); lv.setSpacing(6)
        heading = QHBoxLayout(); heading.addWidget(QLabel("BLOCKS")); heading.addStretch()
        addb = QPushButton("+ BLOCK"); addb.clicked.connect(self.add_block); heading.addWidget(addb)
        delb = QPushButton("DELETE"); delb.setObjectName("deleteButton"); delb.clicked.connect(self.delete_block); heading.addWidget(delb)
        lv.addLayout(heading)
        self.block_list = QListWidget()
        self.block_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.block_list.setSpacing(3)
        self.block_list.setMinimumWidth(220)
        self.block_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.block_list.currentRowChanged.connect(self._list_block_selected)
        lv.addWidget(self.block_list, 1)
        splitter.addWidget(left)

        right = QWidget(); rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(3)
        rv.addWidget(QLabel("BLOCK INSPECTOR"))
        # The Drum Kit host is persistent across Inspector rebuilds, but it is
        # attached to each new Inspector page inside QScrollArea. This keeps
        # the kit and all voice settings in one continuous scrollable workflow.
        self.drum_kit_host = QWidget()
        self.drum_kit_host.setObjectName("drumKitHost")
        self.drum_kit_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.drum_kit_layout = QVBoxLayout(self.drum_kit_host)
        self.drum_kit_layout.setContentsMargins(8, 0, 8, 0)
        self.drum_kit_layout.setSpacing(0)
        self.drum_kit_host.hide()
        self.inspector_scroll = QScrollArea()
        self._inspector_fit_timer = QTimer(self)
        self._inspector_fit_timer.setSingleShot(True)
        self._inspector_fit_timer.timeout.connect(self._fit_inspector_page)
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.inspector_scroll.viewport().installEventFilter(self)
        self.inspector_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # A scrollbar appearing changes viewport width and already delivers a
        # Resize event above. Height/range changes must not schedule another
        # fit: the fit itself publishes the page height and would feed back
        # into this signal indefinitely with an expanded Drum Kit.
        # There is only one Inspector page. A QStackedWidget adds an extra
        # geometry layer and can make the scroll area's child report the
        # viewport height instead of the actual content height. Keep the
        # persistent page directly inside QScrollArea so its minimum height
        # is the authoritative scroll extent.
        self.inspector_page = QWidget()
        self.inspector_page.setObjectName("inspectorPage")
        self.inspector_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.inspector_scroll.setWidget(self.inspector_page)
        rv.addWidget(self.inspector_scroll, 1)
        splitter.addWidget(right)
        splitter.setSizes([280, 1000])
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)
        self.tabs.addTab(blocks_tab, monochrome_tab_icon("▦"), "BLOCKS")

        # PATCH overview is kept as an internal compatibility object but is no longer exposed as a tab.
        self.patch_overview = PatchOverview()
        self.patch_overview.block_selected.connect(self.select_block)

        # --- PERFORMANCE TAB --------------------------------------------
        self.performance = PerformancePanel(self)
        self.performance.hide()

        # --- COMPOSITION PLANNER TAB --------------------------------------
        self.composition_panel = CompositionPlannerPanel(self)
        self.composition_panel.attach_performance(self.performance, TechniqueCurveWidget, PhraseStageStrip, block_color)
        self.tabs.addTab(self.composition_panel, monochrome_tab_icon("▤"), "COMPOSITION")

        # --- RELATIONS TAB ------------------------------------------------
        self.relation_graph = RelationGraphEditor(self)
        self.tabs.addTab(self.relation_graph, monochrome_tab_icon("↔"), "RELATIONS")

        # --- MIDI MONITOR TAB --------------------------------------------
        monitor_tab = QWidget()
        mon_layout = QVBoxLayout(monitor_tab)
        mon_layout.setContentsMargins(8, 8, 8, 8)
        mon_layout.setSpacing(5)
        mon_info = QLabel("Live view of MIDI messages sent by the transport. The monitor does not alter MIDI output.")
        mon_info.setObjectName("muted"); mon_info.setWordWrap(True)
        mon_layout.addWidget(mon_info)
        monitor_box = QGroupBox("MIDI MONITOR")
        mv = QVBoxLayout(monitor_box); mv.setContentsMargins(6, 5, 6, 5); mv.setSpacing(4)
        mh = QHBoxLayout(); mh.setSpacing(6)
        self.monitor_enabled = QPushButton("MONITOR ON"); self.monitor_enabled.setObjectName("monitorButton"); self.monitor_enabled.setCheckable(True); self.monitor_enabled.setChecked(True)
        self.monitor_enabled.clicked.connect(self._monitor_toggle); mh.addWidget(self.monitor_enabled)
        clear = QPushButton("CLEAR"); clear.clicked.connect(lambda: (self._monitor_buffer.clear(), self.midi_monitor.clear())); mh.addWidget(clear)
        mh.addStretch(); mv.addLayout(mh)
        self.midi_monitor = QListWidget(); self.midi_monitor.setObjectName("midiMonitor")
        self.midi_monitor.setSelectionMode(QAbstractItemView.NoSelection); mv.addWidget(self.midi_monitor, 1)
        mon_layout.addWidget(monitor_box, 1)
        self.tabs.addTab(monitor_tab, monochrome_tab_icon("≋"), "MIDI MONITOR")

        # --- HELP TAB -----------------------------------------------------
        help_tab = QWidget()
        self.help_tab = help_tab
        self._help_rendered_language = None
        help_layout = QVBoxLayout(help_tab)
        help_layout.setContentsMargins(8, 8, 8, 8)
        help_layout.setSpacing(6)
        help_header = QHBoxLayout()
        help_logo = LogoLabel()
        self.help_logo = help_logo
        help_logo.setObjectName("helpLogo")
        help_logo.setFixedSize(76, 62)
        help_logo.setAlignment(Qt.AlignCenter)
        help_logo.refresh()
        help_header.addWidget(help_logo)
        help_title = QLabel("AURICLE USER GUIDE")
        help_title.setObjectName("sectionTitle")
        help_header.addWidget(help_title)
        help_header.addStretch()
        help_header.addWidget(QLabel("Language"))
        self.help_language = QComboBox()
        self.help_language.addItem("English", "en")
        self.help_language.addItem("Русский", "ru")
        self.help_language.setFixedWidth(120)
        self.help_language.setCurrentIndex(1)
        set_help_language("ru")
        self.help_language.currentIndexChanged.connect(self._update_help_language)
        help_header.addWidget(self.help_language)
        help_layout.addLayout(help_header)
        help_info = QLabel("Markdown · Composition, blocks, all generator/process parameters and MIDI. Наведите курсор на параметр для подсказки.")
        help_info.setObjectName("muted")
        help_info.setWordWrap(True)
        help_layout.addWidget(help_info)
        self.help_view = QTextBrowser()
        self.help_view.setObjectName("helpBrowser")
        self.help_view.setStyleSheet("QTextBrowser#helpBrowser { font-size:14px; padding:8px; }")
        self.help_view.setOpenExternalLinks(False)
        self.help_view.setOpenLinks(False)
        self.help_view.anchorClicked.connect(lambda url: self.help_view.scrollToAnchor(url.fragment()))
        search_row = QHBoxLayout()
        self.help_search = QLineEdit()
        self.help_search.setPlaceholderText("Поиск / Search…")
        self.help_search.setClearButtonEnabled(True)
        self.help_search.setAccessibleName("Search user guide")
        self.help_search.returnPressed.connect(self._find_help)
        search_row.addWidget(self.help_search, 1)
        for caption, backwards in (("←", True), ("→", False)):
            button = QPushButton(caption)
            button.setFixedWidth(32)
            button.setToolTip("Previous match" if backwards else "Next match")
            button.clicked.connect(lambda _checked=False, back=backwards: self._find_help(back))
            search_row.addWidget(button)
        self.help_search_status = QLabel()
        search_row.addWidget(self.help_search_status)
        help_layout.addLayout(search_row)
        help_layout.addWidget(self.help_view)
        self.tabs.addTab(help_tab, monochrome_tab_icon("?"), "HELP")
        self.tabs.currentChanged.connect(self._ensure_help_loaded)
        for attr, key in (("tempo", "bpm"), ("length", "length"), ("key", "key"), ("scale", "scale"), ("seed", "seed")):
            if hasattr(self, attr):
                bind_help(getattr(self, attr), key, "project")

        # QTabWidget keeps the content stack; its native tab row is mirrored
        # into the header so navigation sits beside the global controls.
        self.tabs.tabBar().hide()
        for i in range(self.tabs.count()):
            self.header_nav.addTab(self.tabs.tabIcon(i), self.tabs.tabText(i))
            source = self.tabs.tabText(i).title()
            if source in SOURCE_COLORS:
                self.header_nav.setTabData(i, source)
        self.header_nav.currentChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self._sync_header_nav)
        self.header_nav.setCurrentIndex(self.tabs.currentIndex())

        # Footer: version is intentionally anchored to the lower-left.
        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        self.version_label = QLabel(APP_VERSION)
        self.version_label.setObjectName("versionLabel")
        footer.addWidget(self.version_label, 0, Qt.AlignLeft | Qt.AlignBottom)
        footer.addStretch()
        outer.addLayout(footer)

        menu = self.menuBar().addMenu("Project")
        for text, key, slot in (("New", QKeySequence.New, self.new_project),
                                ("Open…", QKeySequence.Open, self.open_project),
                                ("Save", QKeySequence.Save, self.save_project),
                                ("Save as…", QKeySequence.SaveAs, self.save_project_as)):
            a = menu.addAction(text); a.setShortcut(QKeySequence(key)); a.triggered.connect(lambda _=False, s=slot: s())
        menu.addSeparator()
        a = menu.addAction("Refresh MIDI"); a.setShortcut(QKeySequence(Qt.Key_F5)); a.triggered.connect(lambda _=False: self.refresh_midi())
        menu.addSeparator()
        a = menu.addAction("Quit"); a.setShortcut(QKeySequence(QKeySequence.Quit)); a.triggered.connect(lambda _=False: self.close())
        # Space toggles PLAY/STOP; text fields keep receiving the space key.
        self._play_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        self._play_shortcut.activated.connect(self._toggle_play)
        self.refresh_midi()

    def _sync_header_nav(self, index):
        if hasattr(self, "header_nav") and self.header_nav.currentIndex() != int(index):
            self.header_nav.blockSignals(True)
            self.header_nav.setCurrentIndex(int(index))
            self.header_nav.blockSignals(False)
        self._idle_view_refresh_at = 0.

    def _apply_style(self, theme="Midnight"):
        """Apply colours once through the window's widget tree.

        QApplication.setStyleSheet repolishes every registered widget and its
        descendants repeatedly. A window-scoped sheet traverses one tree;
        parented dialogs/menus inherit it, while the application palette also
        supplies colours to native controls and custom-painted widgets.
        """
        palette = theme_palette(theme)
        set_active_theme(palette)
        self._active_theme = palette
        css = theme_stylesheet(theme)
        app = QApplication.instance()
        if app is not None:
            qpalette = build_qpalette(palette)
            if app.palette() != qpalette:
                app.setPalette(qpalette)
        if self.styleSheet() != css:
            self.setStyleSheet(css)
        self._refresh_theme_assets()
        runtime = getattr(self, "_algo_conf_runtime", None)
        if runtime is not None and isValid(runtime):
            runtime.timer.stop()
            runtime.apply()

    def _refresh_theme_assets(self):
        theme = getattr(self, "_active_theme", None) or active_theme()
        self._refresh_transport_icons(theme)
        if hasattr(self, "global_macro_bar"):
            self.global_macro_bar.apply_theme(theme)
        if hasattr(self, "performance"):
            for card in self.performance.cards.values():
                card.apply_theme(theme)
        for editor in self.findChildren(MidiExpressionEditor):
            editor.apply_theme(theme)
        if hasattr(self, "relation_graph"):
            for row in self.relation_graph.rows:
                row.apply_theme(theme)
        if hasattr(self, "block_list"):
            for i in range(self.block_list.count()):
                card = self.block_list.itemWidget(self.block_list.item(i))
                if card is not None:
                    card.mute_button.setStyleSheet(block_mute_stylesheet())
        if hasattr(self, "patch_overview"):
            self.patch_overview.apply_theme(theme)
        for label, size in ((getattr(self, "brand_logo", None), (56, 53)), (getattr(self, "help_logo", None), (74, 60))):
            if isinstance(label, LogoLabel):
                label.refresh()
            elif label is not None:
                label.setPixmap(logo_pixmap(QSize(*size), label.devicePixelRatioF()))
        if hasattr(self, "tabs"):
            for i in range(self.tabs.count()):
                symbol = NAVIGATION_SYMBOLS.get(self.tabs.tabText(i), "?")
                icon = monochrome_tab_icon(symbol, color=theme.muted)
                self.tabs.setTabIcon(i, icon)
                if hasattr(self, "header_nav") and i < self.header_nav.count():
                    self.header_nav.setTabIcon(i, icon)
            if hasattr(self, "header_nav"):
                self.header_nav.update()

    def _refresh_transport_icons(self, theme=None):
        theme = theme or getattr(self, "_active_theme", None) or active_theme()
        color = "#111111" if is_light_theme(theme) else "#ffffff"
        if hasattr(self, "play"):
            self.play.setIcon(transport_icon("play", color))
        if hasattr(self, "stop"):
            self.stop.setIcon(transport_icon("stop", color))

    def _update_help_language(self, index):
        language = self.help_language.itemData(index) or "ru"
        set_help_language(language)
        self._ensure_help_loaded()

    def _ensure_help_loaded(self, *_):
        if self.tabs.currentWidget() is not self.help_tab:
            return
        language = self.help_language.currentData() or "ru"
        if self._help_rendered_language == language:
            return
        render_help(self.help_view, help_markdown(language))
        self.help_view.moveCursor(self.help_view.textCursor().MoveOperation.Start)
        self._help_rendered_language = language
        self.help_search_status.clear()

    def _find_help(self, backwards=False):
        text = self.help_search.text().strip()
        if not text:
            self.help_search_status.clear()
            return
        flags = QTextDocument.FindBackward if backwards else QTextDocument.FindFlags()
        found = self.help_view.find(text, flags)
        if not found:
            cursor = self.help_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.End if backwards else cursor.MoveOperation.Start)
            self.help_view.setTextCursor(cursor)
            found = self.help_view.find(text, flags)
        self.help_search_status.setText("" if found else ("Не найдено" if self.help_language.currentData() == "ru" else "Not found"))

    def _monitor_toggle(self, checked):
        self.monitor_enabled.setText("MONITOR ON" if checked else "MONITOR OFF")

    def _flush_monitor(self):
        """Append buffered monitor lines once per UI heartbeat."""
        buffer = getattr(self, "_monitor_buffer", None)
        if not buffer or not hasattr(self, "midi_monitor"):
            return
        lines = buffer[-300:]
        buffer.clear()
        # QListWidget otherwise schedules repeated viewport repaints for every
        # MIDI packet in a burst. Batch the mutation into one visual update.
        self.midi_monitor.setUpdatesEnabled(False)
        try:
            self.midi_monitor.addItems(lines)
            excess = max(0, self.midi_monitor.count() - 300)
            for _ in range(excess):
                self.midi_monitor.takeItem(0)
        finally:
            self.midi_monitor.setUpdatesEnabled(True)
        self.midi_monitor.scrollToBottom()

    def record_generated_event(self, block, event):
        if block is None:
            return
        vel = max(0.0, min(1.0, float(event.get("velocity", 0.8))))
        pitches = event.get("pitches")
        if not isinstance(pitches, (list, tuple)) or not pitches:
            pitches = [event.get("pitch", 0.0)]
        timestamp = time.monotonic()
        for pitch in pitches:
            note = midi_note_for(self.project, block, float(pitch))
            self._generated_event_signal.emit(int(block.id), int(note), float(vel), timestamp)

    def _handle_generated_event(self, block_id, note, velocity, timestamp):
        bucket = self._generated_live_events.setdefault(int(block_id), [])
        bucket.append((float(timestamp), int(note), float(velocity)))
        self._generated_live_events[int(block_id)] = bucket[-256:]

    def log_midi_message(self, block, port_name, message):
        """Queue outbound MIDI diagnostics only when the monitor needs them."""
        if message.type not in ("note_on", "note_off") and hasattr(self, "monitor_enabled") and not self.monitor_enabled.isChecked():
            return
        block_id = getattr(block, "id", None) if block is not None else None
        block_name = getattr(block, "name", "MIDI SYNC" if getattr(message, "type", "") in
                              ("clock", "start", "stop", "continue", "songpos") else "MIDI EXPRESSION")
        self._midi_message_signal.emit(block_id, str(block_name), str(port_name or ""), message)

    def _handle_midi_message(self, block_id, block_name, port_name, message):
        """Record and display one outbound message on the Qt thread."""
        # Piano-roll history must not depend on the MIDI Monitor toggle.
        if block_id is not None:
            if message.type in ("note_on", "note_off"):
                self._pulse_midi_indicator(int(block_id))
            if message.type == "note_on" and getattr(message, "velocity", 0) > 0:
                self._midi_events.setdefault(int(block_id), []).append((time.monotonic(), int(message.note), float(message.velocity) / 127.0))
                # The piano roll selects a fixed user-configured time window.
                self._midi_events[int(block_id)] = self._midi_events[int(block_id)][-2048:]

        if not getattr(self, "monitor_enabled", None) or not self.monitor_enabled.isChecked():
            return
        stamp = time.strftime("%H:%M:%S")
        port = port_name or "(port)"
        channel = getattr(message, "channel", None)
        ch = f"CH {channel + 1:02d}" if channel is not None else "CH --"
        if message.type in ("note_on", "note_off"):
            note = getattr(message, "note", 0)
            velocity = getattr(message, "velocity", 0)
            text = f"{stamp}  {block_name:<10} {port[:24]:<24} {ch}  {message.type.upper():<8}  {NOTE_NAMES[note % 12]}{note // 12 - 1}  vel {velocity:3d}"
        elif message.type == "control_change":
            text = f"{stamp}  {block_name:<14} {port[:24]:<24} {ch}  CC {message.control:3d}  value {message.value:3d}"
        elif message.type == "pitchwheel":
            text = f"{stamp}  {block_name:<14} {port[:24]:<24} {ch}  PITCH BEND  {message.pitch:+5d}"
        elif message.type == "aftertouch":
            text = f"{stamp}  {block_name:<14} {port[:24]:<24} {ch}  AFTERTOUCH  {message.value:3d}"
        elif message.type == "polytouch":
            text = f"{stamp}  {block_name:<14} {port[:24]:<24} {ch}  POLY PRESS  {message.note:3d}  {message.value:3d}"
        elif message.type == "songpos":
            text = f"{stamp}  {block_name:<14} {port[:24]:<24} CH --  SONG POS  {message.pos:5d}"
        else:
            text = f"{stamp}  {block_name:<14} {port[:24]:<24} {ch}  {message.type.upper()}"
        # Batched: _flush_monitor() appends on the UI heartbeat, so dense MIDI
        # no longer repaints the list for every single message.
        if not hasattr(self, "_monitor_buffer"):
            self._monitor_buffer = []
        self._monitor_buffer.append(text)
        if len(self._monitor_buffer) > 600:
            del self._monitor_buffer[:-300]

    def _pulse_midi_indicator(self, block_id):
        # Do not capture the card/QLabel in the delayed callback. Changing MIDI
        # settings can rebuild the block list and delete the old Qt widgets
        # before the 85 ms timer fires. Capture only the stable block id and
        # resolve the current card when the timer callback executes.
        self._midi_pulse_at[block_id] = time.monotonic()
        if self._midi_indicator_on.get(block_id):
            return  # already lit; the pending decay re-arms itself
        self._set_midi_indicator(block_id, True)
        QTimer.singleShot(85, self, lambda bid=block_id: self._decay_midi_indicator(bid))

    def _decay_midi_indicator(self, block_id):
        # One timer per burst instead of one timer + restyle per MIDI note.
        age = time.monotonic() - self._midi_pulse_at.get(block_id, 0.0)
        if age < 0.08:
            QTimer.singleShot(max(10, int((0.085 - age) * 1000)), self, lambda bid=block_id: self._decay_midi_indicator(bid))
            return
        self._set_midi_indicator(block_id, False)

    def _set_midi_indicator(self, block_id, active):
        # The block may have been deleted/rebuilt while the timer was pending.
        if not hasattr(self, "block_list") or self.block_list is None:
            return
        for i in range(self.block_list.count()):
            item = self.block_list.item(i)
            card = self.block_list.itemWidget(item)
            if card is not None and getattr(card, "block_id", None) == block_id:
                label = getattr(card, "midi_indicator", None)
                if label is not None and bool(label.property("active")) != bool(active):
                    label.setProperty("active", bool(active))
                    repolish(label)
                break
        self._midi_indicator_on[block_id] = bool(active)
    def _update_piano_roll(self):
        if (hasattr(self, 'piano_roll') and isValid(self.piano_roll)
                and self.selected_block_id is not None):
            b = self._selected_inspector_entity()
            if b:
                interval = 60.0 / max(1, self.project.tempo) / 4.0
                pattern_seconds = max(0.05, interval * max(1, int(self.project.length)))
                history_ids = [int(b.id)]
                if str(getattr(b, "block_type", "")).upper() == "DRUM":
                    history_ids.extend(int(voice.id) for voice in getattr(b, "drum_voices", None) or [])
                history = []
                for history_id in history_ids:
                    history.extend(self._midi_events.get(history_id, []))
                history.sort(key=lambda item: float(item[0]))
                if b.mode == "LIVE" and len(history) < 16:
                    generated = []
                    for history_id in history_ids:
                        generated.extend(self._generated_live_events.get(history_id, []))
                    history.extend(generated)
                    history.sort(key=lambda e: e[0])
                    dedup=[]; seen=set()
                    for e in history:
                        k=(round(float(e[0]),3), int(e[1]))
                        if k in seen: continue
                        seen.add(k); dedup.append(e)
                    history=dedup[-256:]
                self.piano_roll.set_data(
                    b,
                    history,
                    pattern_seconds=pattern_seconds,
                    seq_interval=interval,
                    running=bool(self.transport.running),
                    project=self.project,
                )

    def _refresh_all(self):
        self._refresh_blocks()
        self._refresh_relations()
        self._refresh_inspector()
        if hasattr(self, "patch_overview"): self.patch_overview.rebuild(self.project)
        if hasattr(self, "performance"): self.performance.refresh_blocks(self.project)
        if hasattr(self, "composition_panel"): self.composition_panel.refresh_if_needed()

    @quiet_rebuild
    def _refresh_blocks(self):
        """Update surviving cards in place; only structural changes replace rows."""
        current = self.selected_block_id
        previous = {self.block_list.item(i).data(Qt.UserRole):
                    (self.block_list.item(i), self.block_list.itemWidget(self.block_list.item(i)))
                    for i in range(self.block_list.count())}
        wanted = [b.id for b in self.project.blocks]
        existing = [self.block_list.item(i).data(Qt.UserRole) for i in range(self.block_list.count())]
        self.block_list.blockSignals(True)
        try:
            # Removing a list item destroys its owned card; do it only for
            # deleted/reordered identities, never for a mode/mute/name edit.
            if [bid for bid in existing if bid in wanted] != [bid for bid in wanted if bid in existing]:
                self.block_list.clear()
                previous.clear()
            for bid, (item, card) in list(previous.items()):
                if bid not in wanted:
                    self.block_list.takeItem(self.block_list.row(item))
                    previous.pop(bid)
            for index, b in enumerate(self.project.blocks):
                pair = previous.get(b.id)
                if pair is None:
                    item = QListWidgetItem()
                    card = BlockCard(b)
                    card.selected.connect(self.select_block)
                    card.delete_requested.connect(self.delete_block_by_id)
                    card.mode_changed.connect(self._card_mode_changed)
                    card.type_changed.connect(self._card_type_changed)
                    card.color_changed.connect(self._card_color_changed)
                    card.rename_requested.connect(self._card_rename_requested)
                    card.mute_changed.connect(self._card_mute_changed)
                    item.setData(Qt.UserRole, b.id)
                    item.setSizeHint(QSize(10, CARD_HEIGHT))
                    self.block_list.insertItem(index, item)
                    self.block_list.setItemWidget(item, card)
                else:
                    item, card = pair
                card.set_block_ref(b)
                card.set_type_color(block_color(self.project, b), b.block_type)
                card.set_selected(b.id == current)
                if b.id == current:
                    self.block_list.setCurrentItem(item)
            if current is None and self.block_list.count():
                self.block_list.setCurrentRow(0)
        finally:
            self.block_list.blockSignals(False)

    def _refresh_relations(self):
        if hasattr(self, "relation_graph"):
            self.relation_graph.rebuild(self.project)

    def _new_inspector_page(self):
        # Build the next Inspector completely off-screen. The persistent Drum
        # Kit host is attached only after the new page is built successfully,
        # preserving the visible page if a control raises during construction.
        # The inner grid remains the target for existing block-control placement.
        page = QWidget()
        page.setObjectName("inspectorPage")
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(7)
        page_layout.setSizeConstraint(QLayout.SetMinimumSize)

        content = QWidget(page)
        content.setObjectName("inspectorContent")
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        page_layout.addWidget(content, 0)
        layout = QGridLayout(content)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setHorizontalSpacing(7)
        layout.setVerticalSpacing(7)
        return page, layout

    def _queue_inspector_refresh(self, restore_anchor=None):
        """Rebuild Inspector only after the current Qt signal/event unwinds.

        Inspector rebuilds replace a whole QWidget tree.  Never perform one
        synchronously from a child widget's signal (QComboBox, knob, button,
        checkbox, etc.), because that can destroy the emitting native Qt
        object while Qt is still dispatching its event.  This helper coalesces
        multiple requests into one rebuild and keeps only the latest anchor.
        """
        self._pending_inspector_anchor = restore_anchor
        if getattr(self, "_inspector_refresh_queued", False):
            return
        self._inspector_refresh_queued = True

        def apply():
            if not self._inspector_refresh_queued:
                return  # A synchronous project restore already refreshed it.
            self._inspector_refresh_queued = False
            anchor = getattr(self, "_pending_inspector_anchor", None)
            self._pending_inspector_anchor = None
            self._refresh_inspector(anchor)

        QTimer.singleShot(0, self, apply)

    def _attach_drum_kit_host(self, page):
        """Place the persistent kit host at the top of a completed Inspector page."""
        host = getattr(self, "drum_kit_host", None)
        page_layout = page.layout() if page is not None else None
        if host is None or page_layout is None:
            return
        page_layout.insertWidget(0, host, 0)
        selected = self.get_block(self.selected_block_id)
        if (selected is not None and selected.block_type == "DRUM"
                and getattr(self, "drum_kit_layout", None) is not None and self.drum_kit_layout.count()):
            host.show()
        else:
            host.hide()
        page_layout.invalidate()
        page_layout.activate()

    def _clear_drum_kit_panel(self):
        """Remove the current Drum Kit editor while retaining its scroll host."""
        host = getattr(self, "drum_kit_host", None)
        panel_layout = getattr(self, "drum_kit_layout", None)
        if host is None or panel_layout is None:
            return
        take_at = getattr(panel_layout, "takeAt")
        while panel_layout.count():
            item = take_at(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            child_layout = item.layout()
            if child_layout is not None:
                child_take_at = getattr(child_layout, "takeAt")
                while child_layout.count():
                    child = child_take_at(0)
                    if child.widget() is not None:
                        child.widget().deleteLater()
        host.hide()

    def _refresh_drum_kit_panel(self, drum):
        """Show the selected DRUM block's kit inside the scrolling Inspector."""
        host = getattr(self, "drum_kit_host", None)
        layout = getattr(self, "drum_kit_layout", None)
        if host is None or layout is None:
            return
        if drum is None or str(getattr(drum, "block_type", "")).upper() != "DRUM":
            # Keep the last kit alive while inspecting a pitched instrument.
            # Its structure key includes model identities, so returning after
            # a project/voice change still rebuilds it when necessary.
            host.hide()
            return
        if not any(block is drum for block in self.project.blocks):
            self._clear_drum_kit_panel()
            return
        ensure_drum_voices(drum)
        current = layout.itemAt(0).widget() if layout.count() else None
        if (isinstance(current, DrumKitEditor) and isValid(current)
                and current._structure_key == DrumKitEditor.structure_key(self, drum)):
            current.select_voice(self.selected_drum_voice_id)
            if host.parentWidget() is getattr(self, "inspector_page", None):
                host.show()
            else:
                host.hide()
            return
        self._clear_drum_kit_panel()
        kit_editor = DrumKitEditor(self, drum, self.selected_drum_voice_id)
        kit_editor.voice_selected.connect(self._select_drum_voice)
        layout.addWidget(kit_editor)
        if host.parentWidget() is getattr(self, "inspector_page", None):
            host.show()
        else:
            host.hide()
        host.adjustSize()
        host.updateGeometry()

    def _motif_controls(self, block):
        motif = self.engine.active_motif(block)
        group = InspectorGroup("MOTIF", expanded=self._inspector_state.get((block.id, "MOTIF"), motif is not None))
        group.setObjectName("inspectorGroup_MOTIF")
        group.set_summary(motif.name if motif is not None else "none")
        group.accordion_toggled.connect(lambda checked, bid=block.id: self._remember_group(bid, "MOTIF", checked))
        form = QVBoxLayout(group)
        form.setContentsMargins(7, 6, 7, 6)
        form.setSpacing(4)
        def row(label):
            box = QHBoxLayout()
            caption = QLabel(label)
            caption.setFixedWidth(76)
            box.addWidget(caption)
            box.setSpacing(6)
            form.addLayout(box)
            return box
        source_row = row("Source")
        choice = QComboBox()
        choice.setObjectName("motifChoice")
        choice.setMinimumWidth(180)
        choice.setMaximumWidth(230)
        choice.setAccessibleName("Motif source")
        choice.addItem("Phrase auto", None)
        choice.addItem("Off — generator", "")
        for item in self.engine.director.motifs.motifs.values():
            if str(item.role).upper() == str(block.block_type).upper():
                choice.addItem(item.name or item.id, item.id)
        binding = block.parameters.get("motif_id")
        index = choice.findData(binding)
        if index < 0:
            choice.addItem(f"Unavailable: {binding}", binding)
            index = choice.count() - 1
        choice.setCurrentIndex(index)
        choice.setToolTip("Choose a saved motif for this block/voice. Phrase auto uses the active phrase's role motif; Off uses the generator.")
        choice.currentIndexChanged.connect(lambda _index, b=block, w=choice: self._set_motif_binding(b, w.currentData()))
        source_row.addWidget(choice)
        capture = QPushButton("Capture")
        capture.setObjectName("motifCapture")
        capture.setToolTip("Create and select a new theme from this generator's preview, before mutations, relations and macros. LIVE captures a preview, not MIDI history.")
        capture.clicked.connect(lambda _checked=False, b=block: self._capture_motif(b))
        source_row.addWidget(capture)
        save = QPushButton("Save variant")
        save.setObjectName("motifSaveVariant")
        save.setToolTip("Save the current source variant as a new reusable theme and select it.")
        save.setEnabled(motif is not None)
        save.clicked.connect(lambda _checked=False, b=block: self._capture_motif(b, True))
        source_row.addWidget(save)
        source_row.addStretch(1)
        timing_row = row("Step · beats")
        step = ValueStepper()
        step.setObjectName("motifStepBeats")
        step.setAccessibleName("Motif step in quarter-note beats")
        step.setDecimals(4)
        step.setRange(.0625, 16.0)
        step.setSingleStep(.125)
        step.setValue(self.engine.motif_step_beats(block, motif) if motif is not None else block.parameters.get("motif_step_beats", .25))
        step.setEnabled(motif is not None and self.engine.coordinated_drum(block) is None)
        step.setToolTip("Musical duration of one motif slot, including rests. 1 = quarter note. Independent of generator timing rate and random LIVE intervals.")
        step.valueChanged.connect(lambda value, b=block: self._set_motif_step(b, float(value)))
        timing_row.addWidget(step)
        timing_row.addWidget(QLabel("Develop"))
        development = QComboBox()
        development.setObjectName("motifDevelopment")
        for title, key in MOTIF_MODES:
            development.addItem(title, key)
        config = motif_settings(block.parameters)
        development.setCurrentIndex(development.findData(config["mode"]))
        development.setEnabled(motif is not None)
        development.setToolTip("Develop the original theme at cycle boundaries. Melodic changes scale neighbours; for drums it changes weak accents. Rhythmic changes weak hits/rests.")
        development.currentIndexChanged.connect(lambda _index, b=block, w=development: self._set_motif_development(b, "motif_development", w.currentData()))
        timing_row.addWidget(development)
        timing_row.addStretch(1)
        settings_row = row("Amount")
        for index, (key, name, value, lo, hi, decimals, increment) in enumerate((
                ("motif_amount", "motifAmount", config["amount"], 0, 1, 2, .05),
                ("motif_every", "motifEvery", config["every"], 1, 16, 0, 1),
                ("motif_return", "motifReturn", config["return"], 2, 16, 0, 1))):
            if index:
                settings_row.addWidget(QLabel("Every · cycles" if index == 1 else "Return · variants"))
            control = ValueStepper()
            control.setObjectName(name)
            control.setDecimals(decimals)
            control.setRange(lo, hi)
            control.setSingleStep(increment)
            control.setValue(value)
            control.setEnabled(motif is not None)
            control.setToolTip({"motif_amount": "Fraction of weak positions eligible for bounded development. Zero keeps the theme.",
                                "motif_every": "Keep each variant for this many complete motif cycles.",
                                "motif_return": "Return to the original theme after this many variant periods (including the theme)."}[key] + " Changes during PLAY take effect at the next cycle.")
            control.valueChanged.connect(lambda value, b=block, k=key: self._set_motif_development(b, k, value))
            settings_row.addWidget(control)
            bind_help(control, key, "motif")
        settings_row.addStretch(1)
        memory_row = row("History")
        history = QComboBox()
        history.setObjectName("motifHistory")
        history.setMinimumWidth(180)
        history.setMaximumWidth(230)
        history.setToolTip("Last eight distinct source variants in this session. Recall holds the selected variant; Save variant makes it a reusable theme.")
        memory_row.addWidget(history)
        recall = QPushButton("Recall")
        recall.setObjectName("motifRecall")
        recall.clicked.connect(lambda _checked=False, b=block, w=history: self._recall_motif(b, w.currentData()))
        memory_row.addWidget(recall)
        hold = QCheckBox("Hold")
        hold.setObjectName("motifHold")
        hold.setChecked(bool(config["hold"]))
        hold.setEnabled(motif is not None)
        hold.setToolTip("Keep the current source variant across cycles and project saves. Changes take effect at the next cycle during PLAY.")
        hold.toggled.connect(lambda checked, b=block: self._hold_motif(b, checked))
        memory_row.addWidget(hold)
        memory_row.addStretch(1)
        status = QLabel()
        status.setObjectName("motifPosition")
        status.setProperty("block_id", block.id)
        status.setWordWrap(True)
        status.setText("No motifs in this project" if not self.engine.director.motifs.motifs else "Transport-synced motif playback")
        form.addWidget(status)
        for control, key in ((choice, "motif_id"), (capture, "capture"), (save, "save_variant"), (step, "motif_step_beats"),
                             (development, "motif_development"), (history, "recall"), (recall, "recall"), (hold, "motif_hold")):
            bind_help(control, key, "motif")
        return group

    def _set_motif_binding(self, block, binding):
        block_id = int(block.id)

        def apply_binding():
            if self.get_entity(block_id) is not block:
                return
            if binding is None:
                block.parameters.pop("motif_id", None)
            else:
                block.parameters["motif_id"] = str(binding)
            block.parameters.pop("motif_hold", None)
            self.engine.motif_development.forget(block.id)
            self.engine.regenerate(block)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_binding, key=("motif-binding", block_id),
            notification={"dirty": True, "block_id": block_id, "refresh": "SOURCE"},
            label=f"motif binding {block_id}"
        )

    def _set_motif_step(self, block, value):
        block_id = int(block.id)
        step = max(.0625, min(16.0, float(value)))

        def apply_step():
            if self.get_entity(block_id) is block:
                block.parameters["motif_step_beats"] = step

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_step, key=("motif-step", block_id),
            notification={"dirty": True, "block_id": block_id},
            label=f"motif step {block_id}"
        )

    def _set_motif_development(self, block, key, value):
        block_id = int(block.id)

        def apply_development():
            if self.get_entity(block_id) is not block:
                return
            block.parameters[key] = value
            if not self.transport.running:
                self.engine.regenerate(block)
                self.engine.motif_variant(block)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_development, key=("motif-development", block_id, str(key)),
            notification={"dirty": True, "block_id": block_id, "refresh": "SOURCE"},
            label=f"motif development {block_id} {key}"
        )

    def _hold_motif(self, block, checked):
        block_id = int(block.id)

        def apply_hold():
            if self.get_entity(block_id) is not block:
                return
            changed = self.engine.hold_motif(block, checked)
            if changed and not self.transport.running:
                self.engine.regenerate(block)
                self.engine.motif_variant(block)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_hold, key=("motif-hold", block_id),
            notification={"dirty": True, "block_id": block_id, "refresh": "SOURCE"},
            label=f"motif hold {block_id}"
        )

    def _recall_motif(self, block, token):
        if not token:
            return
        block_id = int(block.id)
        token = str(token)

        def apply_recall():
            if self.get_entity(block_id) is not block:
                return
            changed = self.engine.hold_motif(block, token=token)
            if changed and not self.transport.running:
                self.engine.regenerate(block)
                self.engine.motif_variant(block)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_recall, key=("motif-recall", block_id),
            notification={"dirty": True, "block_id": block_id, "refresh": "SOURCE"},
            label=f"motif recall {block_id}"
        )

    def _capture_motif(self, block, current_variant=False):
        block_id = int(block.id)
        notification = {"dirty": True, "block_id": block_id, "refresh": "SOURCE"}

        def capture():
            if self.get_entity(block_id) is not block:
                return
            motif = self.engine.capture_motif(block, current_variant)
            if motif is None:
                notification["dirty"] = False
            else:
                notification["message"] = f"Saved motif: {motif.name}"

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            capture, key=("motif-capture", block_id), notification=notification,
            label=f"capture motif {block_id}"
        )

    def _update_kit_status(self):
        layout = getattr(self, "drum_kit_layout", None)
        if layout is not None and layout.count():
            panel = layout.itemAt(0).widget()
            if panel is not None and isValid(panel) and panel.isVisible():
                panel.update_position()

    def _update_motif_status(self):
        scroll = getattr(self, "inspector_scroll", None)
        if scroll is None or not isValid(scroll) or scroll.widget() is None:
            return
        label = scroll.widget().findChild(QLabel, "motifPosition")
        block = self._selected_inspector_entity()
        if label is None or block is None or label.property("block_id") != block.id:
            return
        motif = self.engine.active_motif(block)
        editor = scroll.widget().findChild(ValueStepper, "motifStepBeats")
        group = scroll.widget().findChild(InspectorGroup, "inspectorGroup_MOTIF")
        if editor is not None:
            editor.setEnabled(motif is not None and self.engine.coordinated_drum(block) is None)
            if self.engine.coordinated_drum(block) is not None:
                editor.setToolTip("Coordinated Kit uses a shared 1/16 step (0.25 beats). Choose Role = Free for independent motif timing.")
            if motif is not None and not editor.editor.hasFocus():
                effective_step = self.engine.motif_step_beats(block, motif)
                if editor.value() != effective_step:
                    editor.blockSignals(True)
                    editor.setValue(effective_step)
                    editor.blockSignals(False)
        if group is not None:
            group.set_summary(motif.name if motif is not None else "none")
        page = scroll.widget()
        for name in ("motifDevelopment", "motifAmount", "motifEvery", "motifReturn", "motifSaveVariant", "motifHold"):
            control = page.findChild(QWidget, name)
            if control is not None:
                control.setEnabled(motif is not None)
        with self.transport._transport_lock:
            variant = self.engine.motif_development.current(block.id)
            history_items = list(self.engine.motif_development.history.get(block.id, [])) if motif is not None else []
            config = motif_settings(block.parameters)
        history = page.findChild(QComboBox, "motifHistory")
        if history is not None and not history.view().isVisible():
            items = [(f"Cycle {v.cycle + 1} · {v.label}", v.token) for v in reversed(history_items)]
            existing = [(history.itemText(i), history.itemData(i)) for i in range(history.count())]
            if existing != items:
                selection = history.currentData()
                history.blockSignals(True)
                history.clear()
                for title, token in items:
                    history.addItem(title, token)
                index = history.findData(selection)
                history.setCurrentIndex(index if index >= 0 else 0)
                history.blockSignals(False)
            history.setEnabled(bool(items))
        recall = page.findChild(QPushButton, "motifRecall")
        if recall is not None:
            recall.setEnabled(bool(history_items))
        hold = page.findChild(QCheckBox, "motifHold")
        if hold is not None:
            hold.blockSignals(True)
            hold.setChecked(bool(config["hold"]))
            hold.blockSignals(False)
        if motif is None:
            label.setText("No active motif" if self.engine.director.motifs.motifs else "No motifs in this project")
            return
        step = self.engine.motif_step_beats(block, motif)
        beat = self.engine.clock.position_beats
        suffix = f" · {variant.label}" if variant is not None else ""
        if variant is not None and variant.settings_key != motif_digest(config):
            suffix += " · changes next cycle"
        label.setText(f"Step {motif.index_at(beat, step) + 1}/{motif.steps} · Cycle {motif.steps * step:g} beats · Beat {beat:.2f}{suffix}")

    @quiet_rebuild
    def _refresh_inspector(self, restore_anchor=None):
        self._inspector_refresh_queued = False
        # Every rebuild replaces the QScrollArea page.  Previously deferred
        # scroll callbacks captured the old page, which may already have been
        # deleted by QScrollArea::setWidget() when another rebuild occurred
        # (notably PLAY + LIVE + Add Process).  Use a generation token and
        # resolve the current page at callback time instead of retaining a
        # native QWidget wrapper across rebuilds.
        self._inspector_generation = getattr(self, "_inspector_generation", 0) + 1
        inspector_generation = self._inspector_generation
        scroll_value = self.inspector_scroll.verticalScrollBar().value() if hasattr(self, "inspector_scroll") else 0
        page, layout = self._new_inspector_page()
        parent_block = self.get_block(self.selected_block_id)
        b = self._selected_inspector_entity()
        page._auricle_entity = b
        page._auricle_reflow_forms = []
        self._refresh_drum_kit_panel(parent_block)
        if not b:
            layout.addWidget(QLabel("Select a block"), 0, 0, 1, 2)
            layout.setRowStretch(1, 1)
            # Install the empty page; returning without it left a stale page
            # for a block that no longer exists.
            self._attach_drum_kit_host(page)
            self.inspector_page = page
            if hasattr(self, "inspector_scroll"):
                self.inspector_scroll.setWidget(page)
                self._sync_inspector_scroll_extent(page)
            return

        # Five user-facing transformation layers. MONITOR is diagnostic and stays outside the processing chain.
        # Each layer is an accordion section; the Inspector itself is a single vertical workflow.
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setHorizontalSpacing(7); layout.setVerticalSpacing(7)
        layout.setColumnStretch(0, 1); layout.setColumnStretch(1, 1)
        layout.setSizeConstraint(QLayout.SetMinimumSize)

        def make_layer(title, key, summary="", expanded=True):
            layer = LayerGroup(title, expanded=self._inspector_state.get((b.id, key), expanded), summary=summary)
            layer.setObjectName(f"inspectorLayer_{key}")
            layer.accordion_toggled.connect(lambda checked, bid=b.id, k=key: self._remember_group(bid, k, checked))
            content = QWidget()
            cv = QVBoxLayout(content); cv.setContentsMargins(4,4,4,4); cv.setSpacing(6)
            ll = QVBoxLayout(layer); ll.setContentsMargins(7,10,7,7); ll.setSpacing(4); ll.addWidget(content)
            # The layer is constructed before its content widget exists, so
            # apply the initial accordion state once the content is attached.
            layer._apply_children_visibility()
            ll.activate()
            layer._sync_layout_geometry()
            return layer, content, cv

        # BLOCK identity. This is deliberately outside the five layers.
        general = QFrame()
        general.setObjectName("inspectorBlockHeader")
        gf = QGridLayout(general)
        gf.setContentsMargins(8,7,8,7); gf.setHorizontalSpacing(6); gf.setVerticalSpacing(4)
        gf.setColumnStretch(1, 0); gf.setColumnStretch(3, 0); gf.setColumnStretch(5, 1)

        def header_label(text, control=None):
            w = source_label(text, control) if control is not None and getattr(control, "_auricle_parameter", None) else QLabel(text)
            w.setFixedWidth(62)
            w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return w

        name = QLineEdit(b.name); name.setFixedWidth(170); name.setFixedHeight(24)
        name.editingFinished.connect(lambda b=b,w=name:self._rename_entity(b,w.text()))
        block_type=QComboBox(); block_type.addItems(BLOCK_TYPES); block_type.setCurrentText(b.block_type if b.block_type in BLOCK_TYPES else BLOCK_TYPES[0]); block_type.setFixedWidth(118); block_type.setEnabled(not getattr(b, "is_drum_voice", False)); block_type.currentTextChanged.connect(lambda x,b=b:self._set_block_type(b,x))
        block_type.setIconSize(QSize(20, 20))
        for index in range(block_type.count()):
            block_type.setItemIcon(index, block_type_icon(block_type.itemText(index), active_theme().text, 20))
        alg=QComboBox(); setup_algorithm_combo(alg,b.algorithm); alg.setFixedWidth(190); alg.currentTextChanged.connect(lambda x,b=b:self._set_algorithm(b,x))
        alg._auricle_parameter = (b.id, "@algorithm")
        self._attach_automation_context(alg, b.id, "@algorithm")
        mode=ModeSwitch(b.mode); mode.changed.connect(lambda x,b=b:self._set_mode(b,x))

        # MIDI routing belongs to block identity/output configuration and is
        # intentionally kept beside Name / Generator / Type / Mode. This also
        # prevents the user from having to hunt for routing controls at the
        # bottom of a long Inspector.
        ch=ContrastSpinBox(); ch.setRange(1,16); ch.setValue(b.midi_channel); ch.setFixedWidth(58); ch.valueChanged.connect(lambda x,b=b:self._set_channel(b,x))
        note=ContrastSpinBox(); note.setRange(0,127); note.setValue(b.midi_note); note.setFixedWidth(64); note.valueChanged.connect(lambda x,b=b:self._set_note(b,x))
        port=QComboBox(); port.addItem("(none)")
        ports = list(getattr(self, "_midi_output_names", []) or [])
        if not ports and getattr(self, "_midi_output_error", None) is None and not hasattr(self, "_midi_output_names"):
            ports, _ = get_midi_output_names()
        port.addItems(ports); port.setFixedWidth(190)
        port.blockSignals(True)
        if b.midi_port and port.findText(b.midi_port)>=0: port.setCurrentText(b.midi_port)
        port.blockSignals(False)
        port.currentTextChanged.connect(lambda x,b=b:self._set_port(b,x if x!="(none)" else ""))

        identity_fields = [(header_label(caption, control), control) for caption, control in (
            ("Name", name), ("Type", block_type), ("Generator", alg), ("Mode", mode),
            ("MIDI Ch", ch), ("Base note", note), ("MIDI Out", port))]
        for caption, control in identity_fields:
            control.setAccessibleName(caption.text())
            if isinstance(control, ValueStepper):
                control.set_accessible_label(caption.text())
        role = ROLE_PROFILES.get(b.block_type)
        role_label = QLabel(f"ROLE: {role['label']}" if role else "ROLE: rhythmic")
        role_label.setObjectName("muted")
        role_label.setToolTip({
            "BASS": "Low foundation: constrained low register, root/fifth bias and compact motion.",
            "MELODY": "Lead / phrase: mid-high register with wider melodic motion.",
            "PAD": "Harmonic texture: sustained diatonic voicings with sparse attacks.",
            "CHORD": "Harmonic event: explicit simultaneous diatonic voicing.",
            "DRUM": "Rhythmic role: fixed percussion notes.",
        }.get(b.block_type, ""))
        page._auricle_reflow_forms.append(InspectorIdentity(self, gf, identity_fields, role_label))
        layout.addWidget(general,0,0,1,2)

        for control, key in ((name, "name"), (block_type, "block_type"), (alg, "algorithm"), (mode, "mode"),
                             (ch, "midi_channel"), (note, "midi_note"), (port, "output_port")):
            bind_help(control, key, "identity")

        # SOURCE
        source, source_content, source_layout = make_layer("SOURCE","SOURCE",f"{b.algorithm} · generator parameters",True)
        generator=InspectorGroup("GENERATOR",expanded=self._inspector_state.get((b.id,"GENERATOR"),True)); generator.setObjectName("inspectorGroup_GENERATOR"); generator.set_summary(self._generator_summary(b)); generator.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"GENERATOR",checked))
        class _CompactGeneratorForm:
            """Responsive SOURCE parameter grid.

            Cells are retained and reflowed against the real Inspector viewport
            width.  A vertical scrollbar therefore changes the number of
            columns instead of clipping the fourth column.
            """
            CELL_WIDTH = 74
            GAP = 4
            def __init__(self,parent,host):
                self.parent=parent; self.host=host
                self.layout=QGridLayout(parent)
                self.layout.setContentsMargins(5,5,5,5)
                self.layout.setHorizontalSpacing(self.GAP); self.layout.setVerticalSpacing(3)
                self.layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                self.cells=[]; self.full_width=[]; self.columns=0
                parent._auricle_responsive_form=self
                page._auricle_reflow_forms.append(self)
            def _available_width(self):
                scroll=getattr(self.host,"inspector_scroll",None)
                if scroll is not None and scroll.viewport().width()>0:
                    return max(self.CELL_WIDTH, scroll.viewport().width()-42)
                return max(self.CELL_WIDTH, self.parent.width()-10)
            def _column_count(self):
                available=self._available_width()
                return max(1,min(8,int((available+self.GAP)//(self.CELL_WIDTH+self.GAP))))
            def reflow(self, force=False):
                columns=self._column_count()
                if not force and columns==self.columns: return
                self.columns=columns
                for cell in self.cells: self.layout.removeWidget(cell)
                for widget in self.full_width: self.layout.removeWidget(widget)
                for index,cell in enumerate(self.cells):
                    row,col=divmod(index,columns)
                    self.layout.addWidget(cell,row,col,Qt.AlignLeft | Qt.AlignTop)
                row=(len(self.cells)+columns-1)//columns
                for widget in self.full_width:
                    self.layout.addWidget(widget,row,0,1,columns); row+=1
                self.layout.invalidate(); self.layout.activate(); self.parent.updateGeometry()
            def addRow(self,label,widget):
                widget.setAccessibleName(str(label))
                wide = not isinstance(widget, (Knob, QCheckBox))
                cell=QWidget()
                if not wide:
                    cell.setFixedWidth(self.CELL_WIDTH)
                v=QVBoxLayout(cell); v.setContentsMargins(0,0,0,0); v.setSpacing(0)
                lab=source_label(str(label),widget); lab.setAlignment(Qt.AlignCenter); lab.setObjectName("knobLabel")
                v.addWidget(lab); v.addWidget(widget,0,Qt.AlignLeft if wide else Qt.AlignCenter)
                if wide:
                    widget.setMinimumWidth(180)
                    if isinstance(widget, QComboBox):
                        widget.setMaximumWidth(320)
                    self.full_width.append(cell)
                else:
                    self.cells.append(cell)
            def setContentsMargins(self,*args): self.layout.setContentsMargins(*args)
            def setSpacing(self,value): self.layout.setHorizontalSpacing(value); self.layout.setVerticalSpacing(value)
            def setFieldGrowthPolicy(self,*_): pass
            def addWidget(self,widget):
                self.full_width.append(widget); self.reflow(force=True)
        gform=_CompactGeneratorForm(generator,self)
        def add_int(label,key,lo,hi,default):
            w=RangeKnob(lo,hi,int(b.parameters.get(key,default)),True,default=default); w.changed.connect(lambda x,b=b,k=key:self._set_param(b,k,int(x))); w._auricle_randomize_key=key; w.bind_parameter(b.id, key); gform.addRow(parameter_label(key,label),w); return w
        def add_float(label,key,lo,hi,default,step=.05):
            w=RangeKnob(lo,hi,float(b.parameters.get(key,default)),False,default=default); w.changed.connect(lambda x,b=b,k=key:self._set_param(b,k,float(x))); w._auricle_randomize_key=key; w.bind_parameter(b.id, key); gform.addRow(parameter_label(key,label),w); return w
        def add_slider(label,key,default):
            w=ParamKnob(float(b.parameters.get(key,default)),default=float(default)); w.changed.connect(lambda x,b=b,k=key:self._set_param(b,k,x)); w._auricle_randomize_key=key; w.bind_parameter(b.id, key); gform.addRow(parameter_label(key,label),w); return w
        def add_bool(label,key,default=False):
            w=QCheckBox(); w.setChecked(bool(b.parameters.get(key,default))); w.toggled.connect(lambda x,b=b,k=key:self._set_param(b,k,x)); bind_help(w, key); self._attach_automation_context(w, b.id, key); gform.addRow(label,w); return w
        def add_seed(): add_int("Seed","variation_seed",-9999,9999,0)
        def add_choice(label,key,items,default):
            w=QComboBox(); w.addItems(items); w.setCurrentText(str(b.parameters.get(key,default))); w.currentTextChanged.connect(lambda x,b=b,k=key:self._set_param(b,k,x)); bind_help(w, key); self._attach_automation_context(w, b.id, key); gform.addRow(label,w); return w
        def add_text(label,key,default):
            w=QLineEdit(str(b.parameters.get(key,default))); w.editingFinished.connect(lambda b=b,k=key,w=w:self._set_param(b,k,w.text())); bind_help(w, key); self._attach_automation_context(w, b.id, key); gform.addRow(label,w); return w

        if b.algorithm == "Euclidean":
            add_int("Steps", "euclidean_steps", 1, self.project.length, self.project.length)
            add_int("Pulses", "pulses", 1, self.project.length, 5)
            add_int("Rotation", "euclidean_rotation", 0, max(0, self.project.length - 1), 0)
        elif b.algorithm == "Bresenham":
            add_int("Steps", "bres_steps", 1, self.project.length, self.project.length)
            add_int("Pulses", "bres_pulses", 1, self.project.length, 5)
            add_int("Rotation", "bres_rotation", 0, max(0, self.project.length - 1), 0)
        elif b.algorithm == "Polyrhythm":
            add_int("Cycle A", "poly_a", 1, 32, 3); add_int("Cycle B", "poly_b", 1, 32, 4); add_int("Phase A", "poly_phase_a", 0, 31, 0); add_int("Phase B", "poly_phase_b", 0, 31, 0)
            mode=QComboBox(); mode.addItems(["OR","XOR","AND"]); mode.setCurrentText(str(b.parameters.get("poly_mode","OR"))); mode.currentTextChanged.connect(lambda x,b=b:self._set_param(b,"poly_mode",x)); bind_help(mode, "poly_mode"); self._attach_automation_context(mode, b.id, "poly_mode"); gform.addRow("Combine",mode)
        elif b.algorithm == "Thue-Morse":
            add_int("Rotation", "tm_rotation", 0, max(0,self.project.length-1), 0); add_bool("Invert", "tm_invert", False); add_slider("Density", "tm_density", 1.0); add_seed()
        elif b.algorithm == "Fibonacci Rhythm":
            add_slider("Density", "fib_density", .5); add_int("Offset", "fib_offset", 0, max(0,self.project.length-1), 0)
        elif b.algorithm in ("Fibonacci", "Recaman"):
            add_int("Degree span", "sequence_mod", 1, 24, 7)
            add_int("Stride", "sequence_stride", 1, 8, 1); add_int("Offset", "sequence_offset", -24, 24, 0); add_bool("Reverse", "sequence_reverse", False)
        elif b.algorithm == "De Bruijn":
            add_int("Order", "debruijn_order", 1, 5, 3); add_int("Rotation", "debruijn_rotation", 0, max(0,self.project.length-1), 0)
            add_choice("Mode", "debruijn_mode", ["Rhythm", "Pitch"], "Rhythm");
        elif b.algorithm == "Interval Walker":
            add_int("Step", "interval_step", 1, 12, 3); add_slider("Return", "interval_return", .2); add_int("Range", "interval_range", 4, 48, 24); add_slider("Leap", "interval_leap", .08)
            mode=QComboBox(); mode.addItems(["Scale","Chromatic"]); mode.setCurrentText("Scale" if b.parameters.get("interval_quantize",1) else "Chromatic"); mode.currentTextChanged.connect(lambda x,b=b:self._set_param(b,"interval_quantize",x=="Scale")); bind_help(mode, "interval_quantize"); self._attach_automation_context(mode, b.id, "interval_quantize"); gform.addRow("Quantize",mode)
            add_seed();
        elif b.algorithm == "Scale Walker":
            add_int("Step", "scale_step", 1, 4, 1); add_slider("Direction", "scale_direction", .5); add_int("Octaves", "scale_octaves", 1, 4, 2); add_slider("Leap", "scale_leap", .08); add_seed()
        elif b.algorithm == "Weighted Scale":
            add_text("Weights", "scale_weights", "1,1,1,1,1,1,1"); add_slider("Octave spread", "scale_octave_spread", .15); add_seed()
        elif b.algorithm == "Arpeggiator":
            add_text("Pattern", "arp_pattern", "0,2,4,6"); add_int("Octaves","arp_octaves",1,4,1); add_seed()
            add_choice("Direction", "arp_direction", ["Up","Down","Up/Down"], "Up"); add_choice("Octave mode", "arp_octave_mode", ["Cycle","Random"], "Cycle")
        elif b.algorithm == "Cellular Automaton":
            add_int("Rule", "ca_rule", 0, 255, 30)
            add_int("Generations", "ca_generations", 0, 64, 2)
            add_slider("Density", "ca_density", 1.0); add_seed()
            add_choice("Mode", "ca_mode", ["Rhythm", "Pitch"], "Rhythm")
            add_text("Seed cells", "ca_seed", "00100000")
            add_choice("Boundary", "ca_boundary", ["Wrap", "Fixed", "Mirror"], "Wrap")
            add_choice("Evolution", "ca_evolution", ["Final Row", "Evolution Trail", "XOR Trail"], "Final Row")
        elif b.algorithm == "L-System":
            for label,key,default in [("Axiom","ls_axiom","A"),("Rule A","ls_rule_a","AB"),("Rule B","ls_rule_b","A")]:
                add_text(label, key, default)
            add_int("Iterations", "ls_iterations", 0, 10, 3)
            add_choice("Mode", "ls_mode", ["Pitch", "Rhythm", "Turtle Pitch", "Turtle Rhythm"], "Pitch")
            add_text("Pitch map", "ls_mapping", "0,1,2,3,4,5,6")
        elif b.algorithm == "Turing Machine":
            add_choice("Machine", "turing_preset", ["Busy Beaver", "Alternator", "Growth", "Marbles"], "Busy Beaver")
            add_choice("Mode", "turing_mode", ["Rhythm", "Pitch"], "Rhythm")
            add_text("Initial tape", "turing_tape", "00010000")
            add_slider("Density", "turing_density", 1.0); add_seed()
            add_bool("Wrap tape edges", "turing_wrap", True)
        elif b.algorithm == "Orbital Sequence":
            add_int("Orbit A cycle", "orbit_cycle_a", 1, 256, 8)
            add_int("Orbit B cycle", "orbit_cycle_b", 1, 256, 5)
            add_int("Orbit A phase", "orbit_phase_a", -255, 255, 0)
            add_int("Orbit B phase", "orbit_phase_b", -255, 255, 0)
            add_choice("Interaction", "orbit_mode", ["A", "B", "OR", "AND", "XOR", "Interlock"], "OR")
            add_choice("Output", "orbit_output", ["Rhythm", "Pitch"], "Rhythm")
            add_int("Rotation", "orbit_rotation", 0, max(0, self.project.length - 1), 0)
        elif b.algorithm == "Geometry Collision":
            add_choice("Geometry", "geometry_shape", ["Box", "Triangle", "Hexagon", "Circle"], "Box")
            add_choice("Output", "geometry_mode", ["Rhythm", "Pitch"], "Rhythm")
            add_int("Particles", "geometry_particles", 1, 8, 2)
            add_float("Speed", "geometry_speed", 0.1, 4.0, 1.0, .05)
            add_int("Substeps", "geometry_substeps", 4, 96, 24)
            add_seed()
        elif b.algorithm == "Logistic Chaos":
            add_float("R", "chaos_r", 0.0, 4.0, 3.9, .01); add_float("Initial X", "chaos_x", .001, .999, .5, .01); add_int("Octaves", "chaos_octaves", 1, 4, 2); add_int("Burn-in", "chaos_burn_in", 0, 1000, 0); add_slider("Smooth", "chaos_smooth", 0.0)
            mode=QComboBox(); mode.addItems(["Scale","Chromatic"]); mode.setCurrentText("Scale" if b.parameters.get("chaos_quantize",1) else "Chromatic"); mode.currentTextChanged.connect(lambda x,b=b:self._set_param(b,"chaos_quantize",x=="Scale")); bind_help(mode, "chaos_quantize"); self._attach_automation_context(mode, b.id, "chaos_quantize"); gform.addRow("Quantize",mode)
        elif b.algorithm == "Markov":
            add_int("Max jump", "markov_jump", 1, 6, 3)
            add_int("Transpose (degrees)", "markov_transpose", -24, 24, 0)
            add_int("Octave range", "markov_octaves", 0, 2, 0)
            add_slider("Rest", "markov_rest", 0.0); add_slider("Leap", "markov_leap", .12); add_slider("Stay", "markov_stay", 0.0); add_seed();
        elif b.algorithm == "Random Walk":
            add_int("Step", "walk_step", 1, 12, 2)
            add_int("Range", "walk_range", 1, 48, 12)
            add_int("Start", "walk_start", -48, 48, 0)
            add_slider("Return bias", "walk_return_bias", 0.0); add_float("Drift", "walk_drift", -1.0, 1.0, 0.0); add_seed();
        elif b.algorithm == "Probability":
            add_slider("Probability", "probability", .5)
            add_int("Pitch range", "probability_pitch_range", 1, 24, 7)
            add_int("Center", "probability_center", -24, 24, 0)
            add_int("Octave range", "probability_octaves", 0, 2, 0)
            add_slider("Velocity floor", "probability_velocity_floor", 0.4); add_seed()
        elif b.algorithm == "Pattern":
            pattern = QLineEdit(str(b.parameters.get("pattern", "1,0,0.7,0,1,0,0.5,0")))
            pattern.setPlaceholderText("1,0,0.7,0,1,0,...")
            pattern.editingFinished.connect(lambda b=b, w=pattern: self._set_param(b, "pattern", w.text()))
            bind_help(pattern, "pattern"); self._attach_automation_context(pattern, b.id, "pattern"); gform.addRow("Pattern", pattern)
            add_int("Rotation", "pattern_rotation", 0, max(0, self.project.length - 1), 0)
            add_float("Scale", "pattern_scale", 0.0, 4.0, 1.0, .05)
            add_slider("Probability", "pattern_probability", 1.0); add_bool("Reverse", "pattern_reverse", False)
            chance_editor = PatternChanceEditor(self, b)
            bind_help(chance_editor, "pattern_step_chances"); gform.addRow("Step chance", chance_editor)
            pattern.editingFinished.connect(chance_editor.refresh)

        source_layout.addWidget(generator)
        if not (parent_block is not None and parent_block.block_type == "DRUM" and not getattr(b, "is_drum_voice", False)):
            source_layout.insertWidget(0, self._motif_controls(b))
            preview = AlgorithmPreviewWidget(generator)
            preview.set_block(b, self.project)
            gform.addWidget(preview)
            layout.addWidget(source,1,0,1,2)
        else:
            # The kit container has no generator preview. Keep the unused
            # SOURCE subtree owned by the page until the page is replaced.
            # An unowned hidden SOURCE used to be garbage-collected while
            # self.algorithm_preview still pointed to its deleted Qt child.
            source.setParent(page)
            source.hide()

        # STRUCTURE — shape and timing of the generated material.
        structure, structure_content, structure_layout = make_layer(
            "STRUCTURE", "STRUCTURE",
            f"D {float(b.parameters.get('fill_density',1)):.2f} · P {float(b.parameters.get('event_probability',1)):.2f}", False)

        profile = ROLE_PROFILES.get(b.block_type, {})
        # Double-click resets a knob to its real default; callers pass the
        # current value as ``default``, so reset used to be a no-op.
        knob_resets = {
            "structure_length": self.project.length, "fill_density": profile.get("fill_density", 1.0),
            "event_probability": 1.0, "structure_rotation": 0, "timing_rate": 1.0, "timing_swing": 0.0,
            "gate": profile.get("gate", 0.78), "timing_humanize": 0.0, "timing_offset": 0.0,
            "live_min_beats": 0.18, "live_max_beats": 0.85, "live_gate": 0.65,
            "role_center": profile.get("register_anchor", 0), "role_width": profile.get("pitch_range", 24),
            "role_density": profile.get("fill_density", 1.0), "role_duration": profile.get("role_duration", 1.0),
            "role_root_bias": profile.get("root_bias", 0.0), "groove_follow": 0.70, "groove_accent": 0.65,
            "groove_offset": 0, "harmony_anchor": 0.55, "harmony_size": profile.get("harmony_size", 3),
            "harmony_spread": profile.get("harmony_spread", 7), "harmony_inversion": 0,
            "mutation_pitch": 1.0, "mutation_rhythm": 1.0, "mutation_velocity": 1.0, "mutation_timing": 1.0,
        }

        def add_grid_knob(grid, label, key, lo, hi, default, integer=False, col=0, row=0):
            value = b.parameters.get(key, default)
            w = RangeKnob(lo, hi, int(value) if integer else float(value), integer, default=knob_resets.get(key, default))
            w.bind_parameter(b.id, key)
            w.setAccessibleName(parameter_label(key, label))
            if key in ("timing_rate", "live_min_beats", "live_max_beats") and self.engine.coordinated_drum(b) is not None:
                w.setEnabled(False)
                w.setToolTip("Coordinated Kit uses the shared 1/16 grid. Choose Role = Free for independent timing.")
            w.changed.connect(lambda x, b=b, k=key, integer=integer: self._set_param(b, k, int(x) if integer else float(x)))
            cell = parameter_cell(parameter_label(key, label), w, label_factory=source_label)
            grid.addWidget(cell, row, col, Qt.AlignLeft | Qt.AlignTop)
            return w

        def add_grid_choice(grid, label, key, options, col=0, row=0):
            """Add a compact role choice while keeping the value in Block.parameters."""
            combo = QComboBox()
            bind_help(combo, key)
            combo.setFixedWidth(74)
            combo.setAccessibleName(parameter_label(key, label))
            for text, data in options:
                combo.addItem(str(text), data)
            current = b.parameters.get(key, options[0][1] if options else None)
            index = combo.findData(current)
            if index < 0 and options:
                index = 0
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.currentIndexChanged.connect(
                lambda _index, b=b, k=key, w=combo: self._set_param(b, k, w.currentData())
            )
            self._attach_automation_context(combo, b.id, key)
            cell = parameter_cell(parameter_label(key, label), combo, label_factory=source_label)
            grid.addWidget(cell, row, col, Qt.AlignLeft | Qt.AlignTop)
            return combo

        pattern = InspectorGroup("PATTERN", expanded=self._inspector_state.get((b.id,"PATTERN"),True))
        pattern.setObjectName("inspectorGroup_PATTERN"); pattern.set_summary("length · density · probability · rotation")
        pattern.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"PATTERN",checked))
        pf = InspectorControlGrid(pattern); pf.setContentsMargins(7,6,7,6); pf.setHorizontalSpacing(4); pf.setVerticalSpacing(3); pf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        add_grid_knob(pf,"Length","structure_length",1,max(1,self.project.length),int(b.parameters.get("structure_length",self.project.length)),True,0)
        add_grid_knob(pf,"Density","fill_density",0.0,1.0,float(b.parameters.get("fill_density",b.parameters.get("event_density",1.0))),False,1)
        add_grid_knob(pf,"Probability","event_probability",0.0,1.0,float(b.parameters.get("event_probability",1.0)),False,2)
        add_grid_knob(pf,"Rotation","structure_rotation",0,max(0,self.project.length-1),int(b.parameters.get("structure_rotation",0)),True,3)

        timing = InspectorGroup("TIMING", expanded=self._inspector_state.get((b.id,"TIMING"),True))
        timing.setObjectName("inspectorGroup_TIMING"); timing.set_summary("rate · swing · gate · humanize · offset")
        if self.engine.coordinated_drum(b) is not None:
            timing.set_summary("Kit grid · 1/16 · swing · gate · humanize · offset")
        timing.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"TIMING",checked))
        tf = InspectorControlGrid(timing); tf.setContentsMargins(7,5,7,5); tf.setHorizontalSpacing(4); tf.setVerticalSpacing(3); tf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        add_grid_knob(tf,"Rate","timing_rate",0.25,4.0,float(b.parameters.get("timing_rate",1.0)),False,0)
        add_grid_knob(tf,"Swing","timing_swing",0.0,0.5,float(b.parameters.get("timing_swing",0.0)),False,1)
        add_grid_knob(tf,"Gate","gate",0.05,1.5,float(b.parameters.get("gate",0.78)),False,2)
        add_grid_knob(tf,"Humanize","timing_humanize",0.0,0.25,float(b.parameters.get("timing_humanize",0.0)),False,3)
        add_grid_knob(tf,"Offset","timing_offset",-0.5,0.5,float(b.parameters.get("timing_offset",0.0)),False,4)
        if b.mode == "LIVE":
            add_grid_knob(tf,"Min beats","live_min_beats",0.03,4.0,float(b.parameters.get("live_min_beats",.18)),False,0,1)
            add_grid_knob(tf,"Max beats","live_max_beats",0.03,8.0,float(b.parameters.get("live_max_beats",.85)),False,1,1)
            add_grid_knob(tf,"Live gate","live_gate",0.0,1.5,float(b.parameters.get("live_gate",.65)),False,2,1)
        structure_pair = InspectorPair(self, pattern, timing)
        page._auricle_reflow_forms.append(structure_pair)
        structure_layout.addWidget(structure_pair)
        layout.addWidget(structure,2,0,1,2)

        # MUSICAL — scale/pitch and musical representation.
        musical, musical_content, musical_layout = make_layer(
            "MUSICAL", "MUSICAL",
            f"{b.parameters.get('scale_name',self.project.scale)} · T {float(b.parameters.get('transpose',0)):+.0f} · O {float(b.parameters.get('octave',0)):+.0f}", False)

        scale_group = InspectorGroup("SCALE && PITCH", expanded=self._inspector_state.get((b.id,"SCALE & PITCH"),True))
        scale_group.setObjectName("inspectorGroup_SCALE"); scale_group.set_summary("root · scale · transpose · octave · range")
        scale_group.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"SCALE & PITCH",checked))
        sf = InspectorControlGrid(scale_group); sf.setContentsMargins(7,6,7,6); sf.setHorizontalSpacing(4); sf.setVerticalSpacing(3); sf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        root=RangeKnob(0,127,int(b.parameters.get("scale_root",self.project.root_note)),True,default=self.project.root_note); root.changed.connect(lambda x,b=b:self._set_param(b,"scale_root",int(x)))
        root.bind_parameter(b.id, "scale_root")
        sc=QComboBox(); sc.addItems(SCALES); sc.setCurrentText(str(b.parameters.get("scale_name",self.project.scale))); sc.currentTextChanged.connect(lambda x,b=b:self._set_param(b,"scale_name",x))
        trans=RangeKnob(-48,48,float(b.parameters.get("transpose",0)),True,default=0); trans.changed.connect(lambda x,b=b:self._set_param(b,"transpose",float(x)))
        trans.bind_parameter(b.id, "transpose")
        octv=RangeKnob(-4,4,float(b.parameters.get("octave",0)),True,default=0); octv.changed.connect(lambda x,b=b:self._set_param(b,"octave",float(x)))
        octv.bind_parameter(b.id, "octave")
        prange=RangeKnob(1,48,int(b.parameters.get("pitch_range",24)),True,default=24); prange.changed.connect(lambda x,b=b:self._set_param(b,"pitch_range",int(x)))
        prange.bind_parameter(b.id, "pitch_range")
        self._attach_automation_context(sc, b.id, "scale_name")
        bind_help(sc, "scale_name")
        for i,(label,w) in enumerate([("Root",root),("Scale",sc),("Transpose",trans),("Octave",octv),("Range",prange)]):
            cell = parameter_cell(label, w, label_factory=source_label)
            sf.addWidget(cell, 0, i, Qt.AlignLeft | Qt.AlignTop)

        role = InspectorGroup("ROLE", expanded=self._inspector_state.get((b.id,"ROLE"),True))
        role.setObjectName("inspectorGroup_ROLE")
        role.set_summary(f"{b.block_type} · center {float(b.parameters.get('role_center', 0)):+.0f} · width {float(b.parameters.get('role_width', 24)):.0f} · density {float(b.parameters.get('role_density', 1.0)):.2f}")
        role.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"ROLE",checked))
        rof = InspectorControlGrid(role); rof.setContentsMargins(7,6,7,6); rof.setHorizontalSpacing(4); rof.setVerticalSpacing(3); rof.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        role_specs = [
            ("Center", "role_center", -48, 36, float(b.parameters.get("role_center", ROLE_PROFILES.get(b.block_type, {}).get("register_anchor", 0))), True),
            ("Width", "role_width", 6, 48, float(b.parameters.get("role_width", ROLE_PROFILES.get(b.block_type, {}).get("pitch_range", 24))), True),
            ("Density", "role_density", 0.0, 1.0, float(b.parameters.get("role_density", ROLE_PROFILES.get(b.block_type, {}).get("fill_density", 1.0))), False),
            ("Duration", "role_duration", 0.25, 4.0, float(b.parameters.get("role_duration", ROLE_PROFILES.get(b.block_type, {}).get("role_duration", 1.0))), False),
            ("Root bias", "role_root_bias", 0.0, 1.0, float(b.parameters.get("role_root_bias", ROLE_PROFILES.get(b.block_type, {}).get("root_bias", 0.0))), False),
        ]
        if b.block_type == "BASS":
            role_specs.extend([
                ("Groove mask", "groove_follow", 0.0, 1.0, float(b.parameters.get("groove_follow", .70)), False),
                ("Groove accent", "groove_accent", 0.0, 1.0, float(b.parameters.get("groove_accent", .65)), False),
                ("Groove offset", "groove_offset", -127, 127, int(b.parameters.get("groove_offset", 0)), True),
            ])
        elif b.block_type == "MELODY":
            role_specs.append(("Chord anchor", "harmony_anchor", 0.0, 1.0, float(b.parameters.get("harmony_anchor", .55)), False))
        for col,(label,key,lo,hi,val,integer) in enumerate(role_specs):
            grid_row, grid_col = divmod(col, 4)
            add_grid_knob(rof,label,key,lo,hi,int(val) if integer else val,integer,grid_col,grid_row)
        if b.block_type == "BASS":
            drum_sources = [("Auto", -1)] + [
                (source.name, source.id) for source in self.project.blocks
                if str(source.block_type).upper() == "DRUM"
            ]
            add_grid_choice(rof, "Drum source", "relation_drum_source", drum_sources, 0, 2)
            add_grid_choice(rof, "Groove mode", "groove_mode", [("Union", "Union"), ("Replace", "Replace")], 1, 2)
        elif b.block_type == "MELODY":
            chord_sources = [("Auto", -1)] + [
                (source.name, source.id) for source in self.project.blocks
                if str(source.block_type).upper() == "CHORD"
            ]
            add_grid_choice(rof, "Chord source", "relation_chord_source", chord_sources, 2, 1)
        musical_groups = [scale_group]
        if b.block_type in ROLE_PROFILES:  # DRUM has its own nested voice editor
            musical_groups.append(role)

        if b.block_type in ("CHORD", "PAD", "BASS", "MELODY"):
            follow_plan = QCheckBox("Follow harmonic plan (Perform)")
            follow_plan.setChecked(bool(b.parameters.get("harmonic_follow", True)))
            follow_plan.toggled.connect(lambda value, b=b: self._set_param(b, "harmonic_follow", value))
            bind_help(follow_plan, "harmonic_follow")
            self._attach_automation_context(follow_plan, b.id, "harmonic_follow")
            rof.add_footer(follow_plan)
            if b.block_type in ("BASS", "MELODY"):
                add_grid_knob(rof, "Plan anchor", "harmonic_strength", 0, 1, .75, False, 4, 2)

        harmony = InspectorGroup("HARMONY", expanded=self._inspector_state.get((b.id,"HARMONY"),False))
        harmony.setObjectName("inspectorGroup_HARMONY"); harmony.set_summary("voicing · spread · inversion · role")
        harmony.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"HARMONY",checked))
        hf = InspectorControlGrid(harmony); hf.setContentsMargins(7,6,7,6); hf.setHorizontalSpacing(4); hf.setVerticalSpacing(3); hf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        add_grid_knob(hf,"Chord size","harmony_size",1,4,int(b.parameters.get("harmony_size",1)),True,0)
        add_grid_knob(hf,"Spread","harmony_spread",0,24,int(b.parameters.get("harmony_spread",7)),True,1)
        add_grid_knob(hf,"Inversion","harmony_inversion",-3,3,int(b.parameters.get("harmony_inversion",0)),True,2)
        if b.block_type in ("PAD", "CHORD"):  # voicing only affects harmonic roles
            musical_groups.append(harmony)

        representation=InspectorGroup("REPRESENTATION",expanded=self._inspector_state.get((b.id,"MUSICAL REPRESENTATION"),True)); representation.setObjectName("inspectorGroup_REPRESENTATION"); representation.set_summary(f"Vel {float(b.parameters.get('velocity_base',.72)):.2f} · Accent {float(b.parameters.get('velocity_accent',.18)):.2f}"); representation.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"MUSICAL REPRESENTATION",checked))
        rf=InspectorControlGrid(representation); rf.setContentsMargins(7,6,7,6); rf.setHorizontalSpacing(4); rf.setVerticalSpacing(3); rf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        for col,(label,key,default) in enumerate([("Velocity base","velocity_base",.72),("Velocity range","velocity_range",.25),("Velocity random","velocity_random",0.0),("Accent","velocity_accent",.18)]):
            w = ParamKnob(float(b.parameters.get(key, default)), default=default)
            w.bind_parameter(b.id, key)
            w.changed.connect(lambda x, b=b, k=key: self._set_param(b, k, x))
            cell = parameter_cell(parameter_label(key, label), w, label_factory=source_label)
            rf.addWidget(cell, 0, col, Qt.AlignLeft | Qt.AlignTop)
        musical_groups.append(representation)
        musical_pair = InspectorPair(self, *musical_groups)
        page._auricle_reflow_forms.append(musical_pair)
        musical_layout.addWidget(musical_pair)
        layout.addWidget(musical,3,0,1,2)

        # MIDI expression is a transport-level output layer shared by SEQ,
        # LIVE, Blocks, Perform and Composition. It does not alter note generation.
        midi_expression, midi_expression_content, midi_expression_layout = make_layer(
            "MIDI EXPRESSION", "MIDI EXPRESSION", "CC automation · Pitch Bend · Aftertouch", False)
        midi_parent = self.engine.drum_parent_for(b) if getattr(b, "is_drum_voice", False) else None
        own_expression = getattr(b, "midi_expression", {})
        inherited_expression = getattr(midi_parent, "midi_expression", {}) if midi_parent is not None else {}
        editor_expression = own_expression if own_expression else inherited_expression
        if midi_parent is not None and inherited_expression:
            hint_text = ("Voice-specific MIDI expression overrides the parent kit settings."
                         if own_expression else "Currently inheriting the parent kit MIDI expression. Editing here creates a voice-specific override.")
            hint = QLabel(hint_text); hint.setWordWrap(True); hint.setObjectName("muted")
            midi_expression_layout.addWidget(hint)
            if own_expression:
                inherit_button = QPushButton("Inherit Kit Settings")
                inherit_button.setObjectName("inspectorAddButton")
                inherit_button.clicked.connect(lambda _=False, entity=b: self._clear_midi_expression_override(entity))
                midi_expression_layout.addWidget(inherit_button, 0, Qt.AlignLeft)
        elif getattr(b, "is_drum_voice", False) and own_expression:
            inherit_button = QPushButton("Clear Voice Expression")
            inherit_button.setObjectName("inspectorAddButton")
            inherit_button.clicked.connect(lambda _=False, entity=b: self._clear_midi_expression_override(entity))
            midi_expression_layout.addWidget(inherit_button, 0, Qt.AlignLeft)
        midi_expression_editor = MidiExpressionEditor(editor_expression, self)
        midi_expression_editor.changed.connect(
            lambda config, entity=b: self._set_midi_expression(entity, config))
        midi_expression_layout.addWidget(midi_expression_editor)
        layout.addWidget(midi_expression,4,0,1,2)

        # MOTION — only Mutation and Process for now.
        motion, motion_content, motion_layout = make_layer("MOTION","MOTION",f"{len(b.mutators)} mutations · {len(b.processes)} processes",False)
        if b.block_type == "DRUM":
            hint = QLabel("Voice chain → Kit chain. Pitch keeps the voice's fixed MIDI note. Disable Keep beat to allow rhythm shifts outside the role pattern.")
            hint.setWordWrap(True); hint.setObjectName("drumProcessingHint")
            motion_layout.addWidget(hint)
        mutation_amounts=InspectorGroup("MUTATION AMOUNT",expanded=self._inspector_state.get((b.id,"MUTATION AMOUNT"),True)); mutation_amounts.setObjectName("inspectorGroup_MUTATION_AMOUNT"); mutation_amounts.set_summary("pitch · rhythm · velocity · timing"); mutation_amounts.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"MUTATION AMOUNT",checked))
        maf=InspectorControlGrid(mutation_amounts); maf.setContentsMargins(7,6,7,6); maf.setHorizontalSpacing(4); maf.setVerticalSpacing(3); maf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        mutation_controls = [("Pitch","mutation_pitch"),("Rhythm","mutation_rhythm"),("Velocity","mutation_velocity"),("Timing","mutation_timing")]
        if b.block_type == "DRUM":
            mutation_controls = mutation_controls[1:]
            mutation_amounts.set_summary("rhythm · velocity · timing")
        for col,(label,key) in enumerate(mutation_controls):
            add_grid_knob(maf,label,key,0.0,1.0,float(b.parameters.get(key,1.0)),False,col)
        mutation_amounts.setFixedWidth(maf.preferred_width())
        maf.reflow(maf.preferred_width())
        motion_layout.addWidget(mutation_amounts, 0, Qt.AlignLeft)
        mut=InspectorGroup("MUTATION",expanded=self._inspector_state.get((b.id,"MUTATORS"),True)); mut.setObjectName("inspectorGroup_MUTATION"); mut.set_summary(" · ".join(f"{m.name} {m.amount:.2f}" for m in b.mutators) or "none"); mut.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"MUTATORS",checked))
        ml=QVBoxLayout(mut); ml.setContentsMargins(7,6,7,6); ml.setSpacing(3)
        for m in b.mutators:
            ml.addWidget(MutatorInlineControls(m, b, self))
        add=QPushButton("+ Add"); add.setObjectName("inspectorAddButton"); add.setAccessibleName("Add mutator"); add.setFixedHeight(26); add.clicked.connect(self.add_mutator); ml.addWidget(add,0,Qt.AlignLeft); motion_layout.addWidget(mut)
        proc_group=InspectorGroup("PROCESS",expanded=self._inspector_state.get((b.id,"PROCESS LAYER"),True)); proc_group.setObjectName("inspectorGroup_PROCESS"); proc_group.set_summary(f"{len(b.processes)} processes"); proc_group.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"PROCESS LAYER",checked)); proc_layout=QVBoxLayout(proc_group); proc_layout.setContentsMargins(6,6,6,6); proc_layout.setSpacing(3)
        for idx,proc in enumerate(b.processes):
            card=QWidget(); cv=QVBoxLayout(card); cv.setContentsMargins(0,0,0,0); cv.setSpacing(3); head=QHBoxLayout(); head.setSpacing(4); typ=QComboBox(); typ.addItems(PROCESS_TYPES); typ.setCurrentText(proc.type); typ.setFixedWidth(118); typ.currentTextChanged.connect(lambda x,b=b,i=idx:self._set_process_type(b,i,x)); head.addWidget(typ); tgt=QComboBox(); tgt.addItems(PROCESS_TARGETS); tgt.setCurrentText(proc.target); tgt.setFixedWidth(72); tgt.currentTextChanged.connect(lambda x,b=b,i=idx:self._set_process_target(b,i,x)); head.addWidget(tgt); bind_help(typ, "type", "process"); bind_help(tgt, "target", "process"); head.addWidget(QLabel(f"Process {idx+1}"),1); rem=QPushButton("×"); rem.setObjectName("cardDelete"); rem.setFixedSize(22,22); rem.clicked.connect(lambda _,b=b,i=idx:self.remove_process(b,i)); head.addWidget(rem); cv.addLayout(head); cv.addWidget(ProcessInlineControls(proc,self.project,b,self)); proc_layout.addWidget(card)
        addp=QPushButton("+ Add"); addp.setObjectName("inspectorAddButton"); addp.setAccessibleName("Add process"); addp.setFixedHeight(26); addp.clicked.connect(self.add_process); proc_layout.addWidget(addp,0,Qt.AlignLeft); motion_layout.addWidget(proc_group); layout.addWidget(motion,5,0,1,2)

        # MONITOR / diagnostics
        monitor, monitor_content, monitor_layout = make_layer("MONITOR","MONITOR","piano roll",False)
        piano_group=InspectorGroup("MIDI PIANO ROLL"); piano_group.setObjectName("inspectorGroup_PIANO"); piano_group.set_summary("generated note events"); piano_lay=QVBoxLayout(piano_group); piano_lay.setContentsMargins(7,7,7,7); piano_lay.setSpacing(3)
        piano_controls = QHBoxLayout()
        length_label = QLabel("Length (steps)")
        self.piano_roll_length = ValueStepper(self._piano_length_steps)
        self.piano_roll_length.setObjectName("pianoRollLength")
        self.piano_roll_length.setRange(1, 4096)
        self.piano_roll_length.setFixedWidth(94)
        self.piano_roll_length.set_accessible_label("Piano roll length in sixteenth-note steps")
        bind_help(self.piano_roll_length, "length", "piano_roll")
        bind_help(length_label, "length", "piano_roll")
        length_label.setBuddy(self.piano_roll_length.editor)
        piano_controls.addWidget(length_label)
        piano_controls.addWidget(self.piano_roll_length)
        piano_controls.addStretch()
        freeze = QCheckBox("FREEZE")
        bind_help(freeze, "freeze", "piano_roll")
        freeze.setChecked(self._piano_freeze is not None)
        piano_controls.addWidget(freeze)
        piano_lay.addLayout(piano_controls)
        self.piano_roll = PianoRollWidget()
        self.piano_roll.set_view_steps(self._piano_length_steps)
        self.piano_roll.engine = self.engine
        piano_lay.addWidget(self.piano_roll)
        self._update_piano_roll()
        if self._piano_freeze is not None: self.piano_roll.set_frozen(True,self._piano_freeze)
        self.piano_roll_length.valueChanged.connect(self._set_piano_length_steps)
        freeze.toggled.connect(self._set_piano_freeze); monitor_layout.addWidget(piano_group); layout.addWidget(monitor,6,0,1,2); layout.setRowStretch(7,1)

        # The new page has been built successfully. Swap it into the scroll
        # area only now, so a failed rebuild can never leave the Inspector
        # empty. The old page is detached afterwards and may be deleted by Qt.
        # QScrollArea::setWidget() owns the previous child and removes it
        # when a new widget is installed.  Do not touch the previous page
        # afterwards: the underlying C++ QWidget may already have been
        # destroyed, while Python still holds a Shiboken wrapper.  Calling
        # setParent()/deleteLater() on that stale wrapper raises
        # "Internal C++ object ... already deleted".
        self._attach_drum_kit_host(page)
        refresh_tree(page)
        for knob in page.findChildren(Knob):
            if (hasattr(knob, "_auricle_parameter")
                    and not getattr(knob, "_auricle_midi_learn_connected", False)):
                knob.midi_learn_requested.connect(self._arm_midi_learn)
                knob.midi_clear_requested.connect(self._clear_midi_mapping_for_target)
                knob._auricle_midi_learn_connected = True
        self.inspector_page = page
        if hasattr(self, "inspector_scroll"):
            self.inspector_scroll.setWidget(page)

        # Final synchronous layout pass. Recompute every accordion group's
        # own size hint after all of its child controls have been attached.
        # Without this, a QGroupBox can retain the small height it calculated
        # while it was still empty; the knobs then paint outside the group
        # frame and appear vertically clipped.
        for group in page.findChildren(InspectorGroup):
            group._apply_children_visibility()
            group._sync_layout_geometry()
        for group in page.findChildren(LayerGroup):
            group._apply_children_visibility()
            group._sync_layout_geometry()

        # Final synchronous layout pass.  The scroll page uses a minimum-size
        # contract: its child layouts publish their complete natural height and
        # QScrollArea follows the viewport width.  This avoids a manually sized
        # page whose scrollbar range can lag behind the final Inspector rows.
        page_layout = page.layout()
        layout.invalidate()
        layout.activate()
        if page_layout is not None:
            page_layout.invalidate()
            page_layout.activate()
        self._reflow_inspector_responsive_forms()
        self._sync_inspector_scroll_extent(page)
        if hasattr(self, "inspector_scroll"):
            self.inspector_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

            # Force one synchronous geometry pass before restoring the scroll
            # position. This is intentionally a real layout pass, not a timer
            # workaround for control interaction.
            layout.activate()
            page.updateGeometry()
            self.inspector_scroll.updateGeometry()

            def restore_inspector_scroll(value=scroll_value, anchor=restore_anchor, generation=inspector_generation):
                # A later rebuild supersedes this callback.  Do not touch the
                # QWidget captured by the earlier rebuild; it may have been
                # destroyed by QScrollArea.
                if generation != getattr(self, "_inspector_generation", -1):
                    return
                scroll = getattr(self, "inspector_scroll", None)
                if scroll is None:
                    return
                current_page = scroll.widget()
                if current_page is None:
                    return
                self._sync_inspector_scroll_extent(current_page)
                bar = scroll.verticalScrollBar()
                if anchor:
                    target_name = anchor if anchor.startswith("inspector") else ("inspectorGroup_" + anchor)
                    target = current_page.findChild(QWidget, target_name)
                    if target is not None:
                        # Scroll to the edited section, not to the beginning of
                        # the newly rebuilt page.  All objects are resolved from
                        # the current page, so no stale Shiboken wrapper is used.
                        scroll.ensureWidgetVisible(target, 8, 18)
                        y = target.mapTo(current_page, QPoint(0, 0)).y() - 12
                        bar.setValue(max(0, min(y, bar.maximum())))
                        return
                if bar.maximum() <= 0:
                    return
                bar.setValue(max(0, min(value, bar.maximum())))
            QTimer.singleShot(0, self, restore_inspector_scroll)
            QTimer.singleShot(50, self, restore_inspector_scroll)

    def _remember_group(self, block_id, title, checked):
        self._inspector_state[(block_id,title)] = bool(checked)

    def _set_piano_length_steps(self, value):
        self._piano_length_steps = max(1, min(4096, int(value)))
        self._view_settings.setValue("piano_roll/length_steps", self._piano_length_steps)
        if hasattr(self, "piano_roll") and isValid(self.piano_roll):
            self.piano_roll.set_view_steps(self._piano_length_steps)

    def _set_piano_freeze(self, checked):
        # The inspector (and with it the piano roll widget) is rebuilt often,
        # so the frozen snapshot lives on the main window.
        self.piano_roll.set_frozen(bool(checked))
        self._piano_freeze = self.piano_roll.snapshot()

    def _generator_summary(self, b):
        p=b.parameters
        if b.algorithm in ("Euclidean","Bresenham"):
            pulses = p.get("pulses" if b.algorithm == "Euclidean" else "bres_pulses", 5)
            steps = p.get(f"{'euclidean' if b.algorithm == 'Euclidean' else 'bres'}_steps", self.project.length)
            rotation = p.get(f"{'euclidean' if b.algorithm == 'Euclidean' else 'bres'}_rotation", 0)
            return f"{int(pulses)}/{int(steps)} · R {int(rotation)} · D {float(p.get('fill_density',1)):.2f} · P {float(p.get('event_probability',1)):.2f}"
        if b.algorithm == "Polyrhythm": return f"{p.get('poly_a',3)}:{p.get('poly_b',4)} · {p.get('poly_mode','OR')}"
        if b.algorithm == "Markov": return f"jump {p.get('markov_jump',3)} · rest {float(p.get('markov_rest',0)):.2f}"
        if b.algorithm == "Random Walk": return f"step {p.get('walk_step',2)} · range {p.get('walk_range',12)}"
        if b.algorithm == "Probability": return f"P {float(p.get('probability',.5)):.2f} · range {p.get('probability_pitch_range',7)}"
        if b.algorithm == "Logistic Chaos": return f"R {float(p.get('chaos_r',3.9)):.2f} · X {float(p.get('chaos_x',.5)):.2f}"
        if b.algorithm == "Turing Machine": return f"{p.get('turing_preset','Busy Beaver')} · {p.get('turing_mode','Rhythm')}"
        if b.algorithm == "Orbital Sequence": return f"{p.get('orbit_cycle_a',8)}:{p.get('orbit_cycle_b',5)} · {p.get('orbit_mode','OR')}"
        if b.algorithm == "Geometry Collision": return f"{p.get('geometry_shape','Box')} · {p.get('geometry_particles',2)} particles"
        return f"D {float(p.get('fill_density',1)):.2f} · P {float(p.get('event_probability',1)):.2f}"

    def _card_color_changed(self, block_id, color):
        def apply():
            b = self.get_block(block_id)
            if b is not None:
                b.color = str(color).lower()
                self._mark_dirty()
            self._block_colors_changed()
        QTimer.singleShot(0, self, apply)

    def _block_colors_changed(self):
        self._refresh_blocks()
        self._refresh_relations()
        if hasattr(self, "performance"): self.performance.refresh_blocks(self.project)
        if hasattr(self, "patch_overview"): self.patch_overview.rebuild(self.project)
        self._queue_inspector_refresh()

    def _theme_changed(self, name):
        if getattr(self, "_active_theme", None) == theme_palette(name):
            return
        app = QApplication.instance()
        history = getattr(self, "history_controller", None)
        updates_enabled = self.updatesEnabled()
        splitter_sizes = [(splitter, splitter.sizes()) for splitter in self.findChildren(QSplitter)]
        if app is not None and history is not None:
            app.removeEventFilter(history)
        self.setUpdatesEnabled(False)
        try:
            self._apply_style(name)
        finally:
            if self.layout() is not None:
                self.layout().activate()
            for splitter, sizes in splitter_sizes:
                if isValid(splitter): splitter.setSizes(sizes)
            self.setUpdatesEnabled(updates_enabled)
            if app is not None and history is not None:
                app.installEventFilter(history)

    def _play_clicked(self, checked):
        if checked:
            self.transport.start(mode="blocks")
        else:
            self.transport.stop()
        self._sync_transport_buttons()

    def _stop_clicked(self, checked):
        self.transport.stop()
        self._sync_transport_buttons()

    def _sync_transport_buttons(self):
        running = bool(getattr(self.transport, "running", False))
        self.play.blockSignals(True)
        self.play.setChecked(running and self.transport.playback_mode == "blocks")
        self.play.blockSignals(False)
        if hasattr(self, "composition_panel"):
            self.composition_panel.sync_playback_buttons()

    def _toggle_play(self):
        if self.transport.running:
            self.transport.stop()
        else:
            self.transport.start(mode="blocks")
        self._sync_transport_buttons()

    def get_block(self, block_id):
        return next((b for b in self.project.blocks if b.id == block_id), None)

    def get_drum_voice(self, voice_id):
        try:
            wanted = int(voice_id)
        except (TypeError, ValueError):
            return None
        for block in self.project.blocks:
            for voice in getattr(block, "drum_voices", None) or []:
                if int(voice.id) == wanted:
                    return voice
        return None

    def get_entity(self, entity_id):
        return self.get_block(entity_id) or self.get_drum_voice(entity_id)

    def _update_parameter_sources(self, *, force=False):
        update_parameter_sources(self, force=force)

    def _selected_inspector_entity(self):
        parent = self.get_block(self.selected_block_id)
        if parent is not None and str(parent.block_type).upper() == "DRUM":
            voice = self.get_drum_voice(self.selected_drum_voice_id)
            if voice is not None and int(voice.parent_id) == int(parent.id):
                return voice
        return parent

    def _select_drum_voice(self, voice_id):
        voice = self.get_drum_voice(voice_id)
        if voice is None:
            return
        if self.selected_drum_voice_id == int(voice.id):
            return
        self.selected_drum_voice_id = int(voice.id)
        # Voice settings are rendered below the kit in the same scrollable
        # Inspector. Preserve the current scroll position when selecting a voice.
        self._queue_inspector_refresh()

    def _rename_entity(self, entity, value):
        if entity is None:
            return
        name = str(value).strip() or entity.name
        # Moving focus from the name field to a kit mode button also emits
        # editingFinished.  An unchanged name must not queue another rebuild
        # while the mode refresh is restoring the Inspector scroll position.
        if name == entity.name:
            return

        def apply():
            entity.name = name
            self._mark_dirty()
            parent = self.get_block(getattr(entity, "parent_id", -1)) if getattr(entity, "is_drum_voice", False) else entity
            if parent is not None:
                self.engine.regenerate(parent)
            self._refresh_blocks()
            self._queue_inspector_refresh()

        QTimer.singleShot(0, self, apply)

    def select_block(self, block_id):
        if self.get_block(block_id) is None:
            return
        if (self.selected_block_id == block_id and self._selected_inspector_entity()
                is getattr(getattr(self, "inspector_page", None), "_auricle_entity", None)):
            return
        self.selected_block_id = block_id
        if self.get_block(block_id).block_type != "DRUM":
            self.selected_drum_voice_id = None
        # Do not rebuild the block list or performance cards while handling a click.
        # Recreating widgets here used to invalidate the widget that emitted the click,
        # causing intermittent selection/Inspector refresh failures.
        self.block_list.blockSignals(True)
        for i in range(self.block_list.count()):
            item = self.block_list.item(i)
            if item.data(Qt.UserRole) == block_id:
                self.block_list.setCurrentRow(i)
                break
        self.block_list.blockSignals(False)
        for i in range(self.block_list.count()):
            card = self.block_list.itemWidget(self.block_list.item(i))
            if card is not None:
                card.set_selected(card.block_id == block_id)
        if hasattr(self, "performance"):
            for bid, card in self.performance.cards.items():
                card.set_selected(bid == block_id)
        self._queue_inspector_refresh()

    def _list_block_selected(self, row):
        if row >= 0 and row < self.block_list.count():
            block_id = self.block_list.item(row).data(Qt.UserRole)
            if block_id is not None:
                self.selected_block_id = block_id
                block = self.get_block(block_id)
                if block is None or block.block_type != "DRUM":
                    self.selected_drum_voice_id = None
                for i in range(self.block_list.count()):
                    card = self.block_list.itemWidget(self.block_list.item(i))
                    if card is not None:
                        card.set_selected(i == row)
                if hasattr(self, "performance"):
                    for bid, card in self.performance.cards.items():
                        card.set_selected(bid == block_id)
                self._queue_inspector_refresh()

    def _card_rename_requested(self, block_id):
        def apply():
            b = self.get_block(block_id)
            if b:
                self._mark_dirty()
                self.selected_block_id = block_id
                self._refresh_blocks()
                self._refresh_relations()
                self._refresh_inspector()
        QTimer.singleShot(0, self, apply)

    def _card_mute_changed(self, block_id, muted):
        project_ref = self.project
        muted = bool(muted)

        def apply_mute():
            if self.project is not project_ref:
                return
            block = self.get_block(block_id)
            if block is None:
                return
            block.muted = muted
            self.transport.set_block_muted(block_id, muted)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_mute, key=("block-mute", int(block_id)),
            notification={"dirty": True, "blocks": True},
            label=f"mute block {block_id}"
        )

    def _card_mode_changed(self, block_id, mode):
        self.selected_block_id = block_id
        self._set_mode(self.get_block(block_id), mode)

    def _rename_block(self, b, value):
        if b is None:
            return
        name = value.strip() or b.name
        block_id = int(b.id)

        def apply_rename():
            block = self.get_block(block_id)
            if block is b:
                block.name = name

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_rename, key=("block-rename", block_id),
            notification={"dirty": True, "blocks": True, "relations": True},
            label=f"rename block {block_id}"
        )

    def _set_block_type(self, b, value):
        """Queue block-type replacement after the active Qt signal unwinds."""
        if b is None or value not in BLOCK_TYPES:
            return
        block_id = int(b.id)
        requested = str(value)

        def apply_change():
            block = self.get_block(block_id)
            if block is not b or block.block_type == requested:
                return
            self.transport._release_block_notes(block.id)
            block.block_type = requested
            apply_role_defaults(block)
            if requested == "DRUM":
                ensure_drum_voices(block)
            self.engine.reset_live(block)
            self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_change, key=("block-type", block_id),
            notification={"dirty": True, "blocks": True, "block_id": block_id, "refresh": "SOURCE"},
            label=f"change block type {block_id}"
        )

    def _card_type_changed(self, block_id, value):
        b = self.get_block(block_id)
        if b is None:
            return
        self.selected_block_id = block_id
        self._set_block_type(b, value)

    def _set_algorithm(self, b, value):
        """Queue algorithm changes so generator state has one writer."""
        if b is None or value not in GENERATORS:
            return
        block_id = int(b.id)
        requested = str(value)

        def apply_change():
            block = self.get_entity(block_id)
            if block is not b or block.algorithm == requested:
                return
            self.transport._release_block_notes(block.id)
            self.engine.reset_live(block)
            self.engine.parameter_influence.manual(block, '@algorithm', requested)
            self.engine.regenerate(block)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_change, key=("block-algorithm", block_id),
            notification={"dirty": True, "blocks": True, "block_id": block_id, "refresh": "SOURCE"},
            label=f"change algorithm {block_id}"
        )

    def _set_mode(self, b, value):
        if b is None or value not in ("SEQ", "LIVE"):
            return
        block_id = int(b.id)
        requested = str(value)

        def apply_change():
            block = self.get_entity(block_id)
            if block is not b:
                return
            self.transport._release_block_notes(block.id)
            block.mode = requested
            if block.block_type == "DRUM" and not getattr(block, "is_drum_voice", False):
                for voice in ensure_drum_voices(block):
                    voice.mode = requested
            self.engine.reset_live(block)
            self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_change, key=("block-mode", block_id),
            notification={"dirty": True, "blocks": True, "block_id": block_id, "refresh": "SOURCE"},
            label=f"change block mode {block_id}"
        )

    def _sync_block_card(self, block):
        """Refresh one visible block card from the shared Block model."""
        if block is None or not hasattr(self, "block_list"):
            return
        for i in range(self.block_list.count()):
            item = self.block_list.item(i)
            if item.data(Qt.UserRole) != block.id:
                continue
            card = self.block_list.itemWidget(item)
            if card is not None:
                card.set_block_ref(block)
                card.set_selected(block.id == self.selected_block_id)
            return

    def _set_channel(self, b, value):
        if b is None:
            return
        channel = max(1, min(16, int(value)))
        block_id = int(b.id)

        def apply_channel():
            block = self.get_entity(block_id)
            if block is not b:
                return
            block.midi_channel = channel
            if getattr(block, "is_drum_voice", False):
                parent = self.get_block(getattr(block, "parent_id", -1))
                block.midi_channel_override = bool(parent is None or channel != int(parent.midi_channel))
            elif str(getattr(block, "block_type", "")).upper() == "DRUM":
                for voice in ensure_drum_voices(block):
                    if not bool(getattr(voice, "midi_channel_override", False)):
                        voice.midi_channel = channel

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_channel, key=("midi-channel", block_id),
            notification={"dirty": True, "block_id": block_id, "blocks": True, "refresh": "SOURCE"},
            label=f"MIDI channel {block_id}"
        )

    def _set_note(self, b, value):
        if b is None:
            return
        note = max(0, min(127, int(value)))
        block_id = int(b.id)

        def apply_note():
            block = self.get_entity(block_id)
            if block is b:
                block.midi_note = note

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_note, key=("midi-note", block_id),
            notification={"dirty": True, "block_id": block_id, "blocks": True, "refresh": "SOURCE"},
            label=f"MIDI note {block_id}"
        )

    def _set_port(self, b, value):
        """Queue MIDI port routing and let Transport own native port changes."""
        if b is None:
            return
        value = str(value or "")
        block_id = int(b.id)
        old_port = str(getattr(b, "midi_port", "") or "")
        if old_port == value:
            return

        def apply_port():
            block = self.get_entity(block_id)
            if block is not b:
                return
            block.midi_port = value
            if block.block_type == "DRUM" and not getattr(block, "is_drum_voice", False):
                for voice in ensure_drum_voices(block):
                    if not voice.midi_port or voice.midi_port == old_port:
                        voice.midi_port = value
            self.transport.refresh_ports()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_port, key=("midi-port", block_id),
            notification={"dirty": True, "block_id": block_id, "blocks": True, "refresh": "SOURCE"},
            label=f"MIDI port {block_id}"
        )

    def randomize_parameter(self, b, key, amount=0.35):
        if b is None:
            return
        block_id = int(b.id)

        def randomize():
            if self.get_entity(block_id) is b:
                self.engine.randomize_parameter(b, key, amount)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            randomize, key=("randomize-parameter", block_id, str(key)),
            notification={"dirty": True, "block_id": block_id, "refresh": "SOURCE"},
            label=f"randomize {block_id} {key}"
        )

    def _set_midi_expression(self, entity, config):
        """Queue block/voice expression edits without touching the live model."""
        if entity is None:
            return
        normalized = normalize_expression(config) if config else {}
        entity_id = int(entity.id)

        def apply_expression():
            current = self.get_entity(entity_id)
            if current is entity and getattr(entity, "midi_expression", {}) != normalized:
                entity.midi_expression = normalized

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_expression, key=("midi-expression", entity_id),
            notification={"dirty": True, "block_id": entity_id},
            label=f"MIDI expression {entity_id}"
        )

    def _clear_midi_expression_override(self, entity):
        if entity is None:
            return
        entity_id = int(entity.id)

        def clear_expression():
            current = self.get_entity(entity_id)
            if current is entity:
                entity.midi_expression = {}

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            clear_expression, key=("midi-expression", entity_id),
            notification={"dirty": True, "block_id": entity_id, "refresh": "MIDI_EXPRESSION"},
            label=f"clear MIDI expression {entity_id}"
        )

    def _open_midi_sync_dialog(self):
        dialog = MidiSyncDialog(
            getattr(self.project, "midi_sync", {}),
            ports=list(getattr(self, "_midi_output_names", []) or []),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        config = normalize_midi_sync(dialog.config())
        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            lambda: self.transport.set_midi_sync_config(config),
            key=("midi-sync-config",),
            notification={"dirty": True, "midi_sync": True},
            label="MIDI sync configuration"
        )
        self.set_message("MIDI sync settings queued")

    def _set_param(self, b, key, value):
        """Coalesce parameter edits and apply/regenerate once per block/tick."""
        block_id = int(b.id)
        notification = {"dirty": True, "block_id": block_id,
                        "parameter_entity": b, "parameter_feedback": {}}
        with self._pending_param_edits_lock:
            edits = self._pending_param_edits.setdefault(block_id, {})
            edits[str(key)] = value

        def apply_parameter_batch(bid=block_id, expected=b):
            with self._pending_param_edits_lock:
                changes = self._pending_param_edits.pop(bid, {})
            block = self.get_entity(bid)
            if block is not expected or not changes:
                return
            for parameter, parameter_value in changes.items():
                self.engine.parameter_influence.manual(block, parameter, parameter_value)
            if set(changes) != {"kit_swing"}:
                self.engine.regenerate(block)
            # Read under the transport's model lock, then send immutable
            # feedback to Qt. UI readback must neither wait for that lock nor
            # emit another edit. Preserve automatic/output influence as well
            # as the new authored value, just like the normal UI heartbeat.
            snapshot = SourceSnapshot(self.engine)
            notification["parameter_feedback"] = {
                parameter: feedback_value(snapshot, bid, parameter, snapshot.marks(bid, parameter))
                for parameter in changes
            }

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_parameter_batch, key=("parameter-batch", block_id),
            notification=notification,
            label=f"parameter batch block {block_id}"
        )

    def _update_algorithm_preview(self, block):
        """Resolve the preview from the current Qt-owned Inspector page.

        A kit container or empty Inspector has no preview. A pending callback
        may also outlive selection/page changes. Never retain a native widget
        wrapper across rebuilds or update a preview for a different entity.
        """
        # Update the embedded kit source lane in place after generation, including
        # edits to voices that are not currently selected in the Inspector.
        kit_layout = getattr(self, "drum_kit_layout", None)
        if block is not None and kit_layout is not None and kit_layout.count():
            kit = kit_layout.itemAt(0).widget()
            if kit is not None and isValid(kit) and getattr(block, "parent_id", None) == kit.drum.id:
                kit.refresh_pattern(block)
            elif kit is not None and isValid(kit) and block is kit.drum:
                for voice in block.drum_voices or ():
                    kit.refresh_pattern(voice)
                kit._plan_view_cache = None
                kit.update_position()
                selected = self._selected_inspector_entity()
                if selected is not None and getattr(selected, "parent_id", None) == block.id:
                    block = selected
        if block is None or self._selected_inspector_entity() is not block:
            return
        scroll = getattr(self, "inspector_scroll", None)
        if scroll is None or not isValid(scroll):
            return
        page = scroll.widget()
        if page is None:
            return
        preview = page.findChild(AlgorithmPreviewWidget)
        if preview is not None and preview.block is block and preview.project is self.project:
            preview.set_block(block, self.project)

    def _flush_param_regen(self, block_id):
        pending = getattr(self, "_regen_pending", set())
        pending.discard(block_id)
        b = self.get_entity(block_id)
        if b is not None:
            self.engine.regenerate(b)
            # The preview was updated before regeneration and showed the
            # previous pattern; refresh it with the regenerated material.
            self._update_algorithm_preview(b)

    def _mutator_editor_changed(self, b):
        # Compatibility entry point for legacy controls; regeneration is
        # serialized with transport reads.
        if b is None:
            return
        block_id = int(b.id)

        def regenerate():
            if self.get_entity(block_id) is b:
                self.engine.regenerate(b)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            regenerate, key=("mutator-regenerate", block_id),
            notification={"dirty": True, "block_id": block_id},
            label=f"mutator regenerate {block_id}"
        )

    def _set_mutator_field(self, block, mutator, field, value):
        block_id = int(block.id)
        mutator_token = id(mutator)

        def apply_mutator_field():
            if self.get_entity(block_id) is not block or not any(item is mutator for item in block.mutators):
                return
            setattr(mutator, field, value)
            if field == "target":
                allowed = mutators_for_target(value)
                if mutator.name not in allowed:
                    mutator.name = allowed[0]
            self.engine.regenerate(block)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_mutator_field, key=("mutator-field", block_id, mutator_token, str(field)),
            notification=({"dirty": True, "block_id": block_id, "mutation_summary": True}
                          if field == "amount" else
                          {"dirty": True, "block_id": block_id, "refresh": "MUTATION"}),
            label=f"mutator {block_id} {field}"
        )

    def _process_editor_changed(self, process, block=None):
        # Compatibility entry point for editors that have already staged a
        # value; new controls call _set_process_parameter directly.
        b = block or self._selected_inspector_entity()
        if b is None:
            return
        block_id = int(b.id)

        def regenerate():
            if self.get_entity(block_id) is b and any(item is process for item in b.processes):
                self.engine.regenerate(b)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            regenerate, key=("process-regenerate", block_id, id(process)),
            notification={"dirty": True, "block_id": block_id},
            label=f"process regenerate {block_id}"
        )

    def _set_process_parameter(self, block, process, key, value):
        if block is None or process is None:
            return
        block_id = int(block.id)
        process_token = id(process)

        def apply_process_parameter():
            if self.get_entity(block_id) is not block or not any(item is process for item in block.processes):
                return
            process.parameters[str(key)] = value
            self.engine.regenerate(block)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_process_parameter, key=("process-param", block_id, process_token, str(key)),
            notification={"dirty": True, "block_id": block_id},
            label=f"process {block_id} {key}"
        )

    def _set_process_type(self, b, index, value):
        """Queue process type replacement after the emitting Qt signal unwinds."""
        if b is None or not (0 <= index < len(b.processes)):
            return
        block_id = int(b.id)
        requested = str(value)
        process = b.processes[index]

        def apply_change():
            block = self.get_entity(block_id)
            if block is not b or not (0 <= index < len(block.processes)) or block.processes[index] is not process:
                return
            if process.type == requested:
                return
            process.type = requested
            process.parameters = {}
            if requested == "Parameter Modulation":
                destination = next((x for x in self.project.blocks if x.id != block.id), block)
                catalog = MusicEngine.parameter_catalog(destination)
                key_name = "fill_density" if "fill_density" in catalog else next(iter(catalog), "")
                _default, lo, hi = catalog.get(key_name, (0.5, 0.0, 1.0))
                process.target = "pitch"
                process.parameters = {
                    "destination_block": destination.id, "destination_parameter": key_name,
                    "source_min": -1.0, "source_max": 1.0, "min": lo, "max": hi, "smoothing": 0.0,
                }
            self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_change, key=("process-type", block_id, int(index)),
            notification={"dirty": True, "block_id": block_id, "refresh": "PROCESS"},
            label=f"process type {block_id}:{index}"
        )

    def _set_process_target(self, b, index, value):
        if b is None or not (0 <= index < len(b.processes)):
            return
        block_id = int(b.id)
        process = b.processes[index]
        requested = str(value)

        def apply_target():
            block = self.get_entity(block_id)
            if block is b and 0 <= index < len(block.processes) and block.processes[index] is process:
                process.target = requested
                self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_target, key=("process-target", block_id, int(index)),
            notification={"dirty": True, "block_id": block_id, "refresh": "PROCESS"},
            label=f"process target {block_id}:{index}"
        )

    def add_process(self):
        b = self._selected_inspector_entity()
        if not b:
            return
        process = Process("Counter", "velocity" if b.block_type == "DRUM" else "pitch", 0.25,
                           {"length": 8, "step": 1.0, "offset": 0.0, "depth": 0.25})
        block_id = int(b.id)

        def add():
            if self.get_entity(block_id) is b:
                b.processes.append(process)
                self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            add, key=("process-add", block_id, id(process)),
            notification={"dirty": True, "block_id": block_id, "refresh": "PROCESS"},
            label=f"add process {block_id}"
        )

    def remove_process(self, b, index):
        if b is None or not (0 <= index < len(b.processes)):
            return
        block_id = int(b.id)
        process = b.processes[index]

        def remove():
            if self.get_entity(block_id) is b and any(item is process for item in b.processes):
                b.processes.remove(process)
                self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            remove, key=("process-remove", block_id, id(process)),
            notification={"dirty": True, "block_id": block_id, "refresh": "PROCESS"},
            label=f"remove process {block_id}"
        )

    def remove_mutator(self, b, index):
        if b is None or not (0 <= index < len(b.mutators)):
            return
        block_id = int(b.id)
        mutator = b.mutators[index]

        def remove():
            if self.get_entity(block_id) is b and any(item is mutator for item in b.mutators):
                b.mutators.remove(mutator)
                self.engine.regenerate(b)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            remove, key=("mutator-remove", block_id, id(mutator)),
            notification={"dirty": True, "block_id": block_id, "refresh": "MUTATION"},
            label=f"remove mutator {block_id}"
        )

    def _tempo_changed(self, value):
        value = int(value)
        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            lambda: self.transport.set_tempo(value), key=("tempo",),
            notification={"dirty": True}, label="tempo change"
        )

    def _length_changed(self, value):
        length = int(value)

        def apply_length():
            self.project.length = length
            self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            apply_length, key=("project-length",),
            notification={"dirty": True, "refresh": "SOURCE"}, label="project length change"
        )

    def _unique_block_name(self, role):
        """Create a readable unique block name from its musical role."""
        base = (role or "BLOCK").strip().upper()
        names = {getattr(b, "name", "") for b in self.project.blocks}
        if base not in names:
            return base
        idx = 2
        while f"{base} {idx}" in names:
            idx += 1
        return f"{base} {idx}"

    def add_block(self):
        dialog = AddBlockDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        reserved = getattr(self, "_reserved_block_ids", None)
        if reserved is None:
            self._reserved_block_ids = reserved = set()
        existing_ids = [int(block.id) for block in self.project.blocks] + list(reserved)
        new_id = max(existing_ids + [0]) + 1
        existing_colors = [getattr(block, "color", "") for block in self.project.blocks]
        block = Block(new_id, dialog.name.text().strip() or self._unique_block_name(dialog.kind.currentText()),
                      dialog.kind.currentText(), dialog.algorithm.currentText(), dialog.mode.mode(),
                      1, "", 60, {}, color=random_block_color(existing_colors))
        apply_role_defaults(block)
        if block.block_type == "DRUM":
            ensure_drum_voices(block)
            enable_musical_kit(block)
        used_channels = {int(item.midi_channel) for item in self.project.blocks}
        block.midi_channel = next((channel for channel in range(1, 17) if channel not in used_channels), 1)
        project_ref = self.project
        reserved.add(new_id)
        self.selected_block_id = new_id

        def add():
            reserved.discard(new_id)
            if self.project is not project_ref or any(item.id == new_id for item in project_ref.blocks):
                return
            project_ref.blocks.append(block)
            self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            add, key=("block-add", new_id),
            notification={"dirty": True, "refresh_all": True},
            label=f"add block {new_id}"
        )

    def delete_block_by_id(self, block_id):
        if self.selected_block_id != block_id:
            self.selected_block_id = block_id
        self.delete_block()

    def delete_block(self):
        block = self.get_block(self.selected_block_id)
        if block is None:
            return
        if len(self.project.blocks) <= 1:
            self.set_message("At least one block must remain")
            return
        project_ref = self.project
        block_id = int(block.id)
        removed_ids = {block_id, *(int(voice.id) for voice in block.drum_voices or [])}
        next_selection = next((item.id for item in self.project.blocks if item is not block), None)
        self.selected_block_id = next_selection
        self.selected_drum_voice_id = None

        def remove():
            if self.project is not project_ref or not any(item is block for item in project_ref.blocks):
                return
            self.transport._release_block_notes(block_id)
            project_ref.relations = [relation for relation in project_ref.relations
                if relation.source_block not in removed_ids and relation.destination_block not in removed_ids
                and getattr(relation, "source_voice_id", None) not in removed_ids
                and getattr(relation, "destination_voice_id", None) not in removed_ids]
            for owner in removed_ids:
                project_ref.parameter_policies.pop(str(owner), None)
            self.engine.performance.stop(block_id, regenerate=False)
            project_ref.blocks = [item for item in project_ref.blocks if item is not block]
            for macro in project_ref.macros:
                macro["routes"] = [route for route in macro.get("routes", []) or []
                                   if route.get("block_id") != block_id]
            for other in project_ref.blocks:
                for process in other.processes:
                    if process.type == "Parameter Modulation" and process.parameters.get("destination_block") == block_id:
                        process.parameters["destination_block"] = -1
            self.transport.refresh_ports()
            self.engine.generate()

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            remove, key=("block-delete", block_id),
            notification={"dirty": True, "refresh_all": True},
            label=f"delete block {block_id}"
        )

    def add_mutator(self):
        block = self._selected_inspector_entity()
        if block is None:
            return
        target = "rhythm" if block.block_type == "DRUM" else "pitch"
        mutator = Mutator("Rotate", .5, target)
        block_id = int(block.id)

        def add():
            if self.get_entity(block_id) is block:
                block.mutators.append(mutator)
                self.engine.regenerate(block)

        self._mark_pending_dirty()
        self.transport.enqueue_gui_command(
            add, key=("mutator-add", block_id, id(mutator)),
            notification={"dirty": True, "block_id": block_id, "refresh": "MUTATION"},
            label=f"add mutator {block_id}"
        )

    def add_relation(self, operation='Copy'):
        endpoints = []
        for block in self.project.blocks:
            endpoints.append((block, None))
            endpoints.extend((block, voice) for voice in getattr(block, "drum_voices", None) or [])
        if len(endpoints) < 2:
            self.set_message("At least two blocks or Drum Voices are required")
            return
        selected_parent = self.get_block(self.selected_block_id)
        selected_voice = self.get_drum_voice(self.selected_drum_voice_id) if selected_parent is not None else None
        source = (selected_parent, selected_voice) if selected_voice is not None else (selected_parent or self.project.blocks[0], None)
        source_block, source_voice = source
        is_dialogue = operation == 'Dialogue'
        if is_dialogue:
            # Dialogue is a block-level turn-taking relation.  Never create a
            # container-to-child route and then silently discard the child
            # selectors in the dialogue runtime.
            source = (source_block, None)
            destination = next((block, None) for block in self.project.blocks if block.id != source_block.id)
        elif len(self.project.blocks) >= 2:
            # Preserve the established +Add default: two different block
            # owners.  Voices remain available in the inspector dropdown and
            # are selected explicitly by the user.
            destination = next((block, None) for block in self.project.blocks if block.id != source_block.id)
        else:
            source_key = source_voice.id if source_voice is not None else source_block.id
            destination = next(endpoint for endpoint in endpoints
                               if (endpoint[1].id if endpoint[1] is not None else endpoint[0].id) != source_key)
        source_block, source_voice = source
        destination_block, destination_voice = destination
        source_is_drum = source_voice is not None or str(source_block.block_type).upper() == "DRUM"
        destination_is_drum = destination_voice is not None or str(destination_block.block_type).upper() == "DRUM"
        part = "rhythm" if source_is_drum else "pitch"
        destination_part = "rhythm" if destination_is_drum else part
        operation = 'Dialogue' if is_dialogue else 'Copy'
        self.relation_graph.add_relation(Relation(
            source_block.id, part, destination_block.id, destination_part, operation,
            1. if operation == 'Dialogue' else .5,
            source_voice_id=(source_voice.id if source_voice is not None and operation != 'Dialogue' else None),
            destination_voice_id=(destination_voice.id if destination_voice is not None and operation != 'Dialogue' else None),
        ))

    def get_midi_input_names(self):
        names, error = get_midi_input_names()
        self._midi_input_available_names = list(names)
        return names, error

    def midi_learn_diagnostic_snapshot(self):
        """Observe the actual input/GUI/model boundaries without changing them."""
        if self._midi_runtime_identity is None:
            import platform
            from importlib.metadata import version, PackageNotFoundError
            import hashlib
            identity = {"python": sys.version.split()[0], "executable": sys.executable,
                        "platform": platform.platform(), "frozen": bool(getattr(sys, "frozen", False)),
                        "gui_module": str(Path(__file__).resolve()),
                        "reader_module": getattr(sys.modules.get(read_input_loop.__module__), "__file__", None)}
            for package in ("mido", "python-rtmidi", "PySide6"):
                try:
                    identity[package] = version(package)
                except PackageNotFoundError:
                    identity[package] = "not available"
            try:
                identity["gui_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            except OSError:
                identity["gui_sha256"] = "bundled / unavailable"
            self._midi_runtime_identity = identity
        state = self._midi_diagnostics.snapshot()
        request = state.get("last_request")
        if request and state["stage"] == "queued" and self.transport._transport_lock.acquire(blocking=False):
            try:
                target = request["target"]
                if target.get("kind") == "global_macro":
                    manual = self.project.macros[target["macro_index"]]["value"]
                    effective = manual
                else:
                    block = self.get_entity(target.get("block_id"))
                    effective = block.parameters.get(target["parameter"]) if block is not None else None
                    entry = self.engine.parameter_influence.entries.get((target.get("block_id"), target["parameter"]))
                    manual = entry["base"][1] if entry and entry["base"][0] else effective
                state["observed_target"] = {"manual": manual, "effective": effective,
                                            "requested": request["value"]}
                if isinstance(manual, (int, float)) and abs(float(manual) - request["value"]) < 1e-8:
                    self._midi_diagnostics.mark("applied", target=target, manual=manual, effective=effective)
                    state = self._midi_diagnostics.snapshot()
            finally:
                self.transport._transport_lock.release()
        context = dict(self._midi_runtime_identity)
        context.update({
            "backend": str(mido.backend),
            "available_inputs": list(self._midi_input_available_names),
            "saved_input": self.project.midi_input_port,
            "active_input": self._midi_input_name,
            "port_class": type(self._midi_input_port).__module__ + "." + type(self._midi_input_port).__name__,
            "port_api": getattr(self._midi_input_port, "api", None),
            "reader_alive": bool(self._midi_input_thread and self._midi_input_thread.is_alive()),
            "transport_worker_alive": bool(self.transport_worker._thread and self.transport_worker._thread.is_alive()),
            "pending_commands": len(self.transport.gui_command_queue),
            "command_errors": self.transport.gui_command_errors,
            "learn_target": self._midi_learn_target,
            "mappings": list(self.project.midi_mappings or []),
        })
        return {"runtime": context, "midi_input": state}

    def midi_learn_diagnostic_report(self):
        snapshot = self.midi_learn_diagnostic_snapshot()
        return format_diagnostics(snapshot["midi_input"], snapshot["runtime"])

    def connect_midi_input(self, name):
        """Open MIDI IN and drain its queue on a dedicated reader thread.

        Using ``iter_pending()`` avoids backend callback differences between
        RtMidi/Windows/macOS/ALSA and keeps the Qt GUI thread out of the MIDI
        backend callback. The reader only emits normalized plain-Python data.
        """
        name = str(name or "")
        if not name:
            return False
        if (self._midi_input_name == name and self._midi_input_port is not None
                and not getattr(self._midi_input_port, "closed", False)
                and self._midi_input_thread is not None and self._midi_input_thread.is_alive()):
            return True
        self.disconnect_midi_input()
        diagnostics = MidiInputDiagnostics(name)
        self._midi_diagnostics = diagnostics
        diagnostics.mark("opening")
        port = None
        try:
            port = mido.open_input(name)  # deliberately no backend callback
            stop_event = threading.Event()
            session = object()
            self._midi_input_port = port
            self._midi_input_name = name
            self._midi_input_stop = stop_event
            self._midi_input_session = session
            self._midi_input_error = ""
            self._midi_input_event_count = 0
            diagnostics.mark("listening")

            def reader():
                try:
                    read_input_loop(
                        port,
                        lambda event: self._midi_input_signal.emit(
                            name, dict(event, _midi_session=session)),
                        stop_event,
                        poll_interval=0.001,
                        diagnostics=diagnostics,
                    )
                except Exception as exc:
                    if not stop_event.is_set():
                        diagnostics.mark("error", error=str(exc))
                        self._midi_input_signal.emit(
                            name, {"_midi_session": session, "_midi_error": str(exc)})
                finally:
                    # RtMidi.close() is not thread safe. The reader owns its
                    # handle and closes it after all pending reads have ended.
                    try:
                        port.close()
                    except Exception:
                        pass

            thread = threading.Thread(
                target=reader, name="Auricle-MIDI-IN", daemon=True
            )
            self._midi_input_thread = thread
            thread.start()
            self.project.midi_input_port = name
            if hasattr(self, "midi_learn_button"):
                self.midi_learn_button.setText(
                    "LEARN…" if self._midi_learn_target is not None else "MIDI IN ✓"
                )
            self.set_message(f"MIDI input connected: {name} (listening)")
            return True
        except Exception as exc:
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass
            self._midi_input_port = None
            self._midi_input_name = ""
            self._midi_input_stop = None
            self._midi_input_thread = None
            self._midi_input_session = None
            self._midi_input_error = str(exc)
            diagnostics.mark("error", error=str(exc))
            self.set_message(f"MIDI input failed: {exc}")
            return False

    def disconnect_midi_input(self):
        # Invalidate already queued packets before waiting for the reader.
        self._midi_input_session = None
        stop_event, self._midi_input_stop = self._midi_input_stop, None
        thread, self._midi_input_thread = self._midi_input_thread, None
        port, self._midi_input_port = self._midi_input_port, None
        self._midi_input_name = ""
        if stop_event is not None:
            stop_event.set()
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.25)
        if port is not None and thread is None:
            try:
                port.close()
            except Exception:
                pass
        self._midi_learn_runtime.reset()
        if self._midi_diagnostics.snapshot()["stage"] != "error":
            self._midi_diagnostics.mark("disconnected")
        if hasattr(self, "midi_learn_button"):
            self.midi_learn_button.setText(
                "LEARN…" if self._midi_learn_target is not None else "MIDI IN"
            )

    def _sync_midi_input_port(self):
        wanted = str(getattr(self.project, "midi_input_port", "") or "")
        if wanted:
            self.connect_midi_input(wanted)
        elif not wanted and self._midi_input_name:
            self.disconnect_midi_input()

    def _open_midi_learn_dialog(self):
        existing = getattr(self, "_midi_learn_dialog", None)
        if existing is not None and isValid(existing):
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        dialog = MidiLearnDialog(self, self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setModal(False)
        self._midi_learn_dialog = dialog

        def finished(_result):
            if getattr(self, "_midi_learn_dialog", None) is dialog:
                self._midi_learn_dialog = None
        dialog.finished.connect(finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _notify_midi_mappings_changed(self):
        dialog = getattr(self, "_midi_learn_dialog", None)
        if dialog is not None:
            try:
                if isValid(dialog):
                    dialog.queue_refresh()
            except RuntimeError:
                self._midi_learn_dialog = None

    def _arm_midi_learn(self, target):
        if not isinstance(target, dict):
            return
        self._midi_learn_target = dict(target)
        self._midi_diagnostics.mark("armed", target=dict(target))
        if hasattr(self, "midi_learn_button"):
            self.midi_learn_button.setText("LEARN…")
        if not self._midi_input_name:
            self.set_message("MIDI Learn armed. Connect a MIDI input, then move one hardware control.")
            self._open_midi_learn_dialog()
            # Keep Learn armed; the user can connect MIDI IN later.
            if not self._midi_input_name and self._midi_learn_target is not None:
                self.set_message("MIDI Learn is still armed — connect MIDI IN, then move a control.")
                if hasattr(self, "midi_learn_button"):
                    self.midi_learn_button.setText("LEARN…")
        else:
            self.set_message("MIDI Learn armed — move one control on your MIDI device")
        self._notify_midi_mappings_changed()

    def _cancel_midi_learn(self):
        self._midi_learn_target = None
        self._midi_diagnostics.mark("cancelled")
        if hasattr(self, "midi_learn_button"):
            self.midi_learn_button.setText("MIDI IN ✓" if self._midi_input_name else "MIDI IN")
        self._notify_midi_mappings_changed()
        self.set_message("MIDI Learn cancelled")

    def _clear_midi_mapping_for_target(self, target):
        if not isinstance(target, dict):
            return
        kind = target.get("kind", "block_parameter")
        def same(mapping):
            item = mapping.get("target", {})
            if item.get("kind") != kind:
                return False
            if kind == "global_macro":
                return int(item.get("macro_index", -1)) == int(target.get("macro_index", -2))
            return (int(item.get("block_id", -999999)) == int(target.get("block_id", -999998))
                    and item.get("parameter") == target.get("parameter"))
        old = len(self.project.midi_mappings)
        removed = [m for m in self.project.midi_mappings if same(m)]
        self.project.midi_mappings = [m for m in self.project.midi_mappings if not same(m)]
        for mapping in removed:
            self._midi_learn_runtime.remove(mapping.get("id"))
        if len(self.project.midi_mappings) != old:
            self._mark_dirty()
            self._notify_midi_mappings_changed()
            self.set_message("MIDI mapping removed")

    def remove_midi_mapping(self, mapping_id):
        mapping_id = str(mapping_id)
        self.project.midi_mappings = [m for m in self.project.midi_mappings if str(m.get("id")) != mapping_id]
        self._midi_learn_runtime.remove(mapping_id)
        self._mark_dirty()
        self._notify_midi_mappings_changed()

    def clear_midi_mappings(self):
        self.project.midi_mappings = []
        self._midi_learn_runtime.reset()
        self._mark_dirty()
        self._notify_midi_mappings_changed()

    def set_midi_mapping_enabled(self, mapping_id, enabled):
        mapping_id = str(mapping_id)
        for mapping in self.project.midi_mappings:
            if str(mapping.get("id")) == mapping_id:
                mapping["enabled"] = bool(enabled)
                self._midi_learn_runtime.remove(mapping_id)
                self._mark_dirty()
                self._notify_midi_mappings_changed()
                return

    def set_midi_mapping_pickup(self, mapping_id, enabled):
        for mapping in self.project.midi_mappings:
            if str(mapping.get("id")) == str(mapping_id):
                mapping["pickup"] = bool(enabled)
                self._midi_learn_runtime.remove(mapping_id)
                self._mark_dirty()
                self._notify_midi_mappings_changed()
                return

    def _handle_midi_input(self, port_name, message):
        if isinstance(message, dict) and "_midi_session" in message:
            if message["_midi_session"] is not self._midi_input_session:
                return  # Disconnected/replaced port, including a same-name reopen.
            message = dict(message)
            message.pop("_midi_session")
            if "_midi_error" in message:
                self._midi_input_error = str(message["_midi_error"])
                self.disconnect_midi_input()
                self._notify_midi_mappings_changed()
                self.set_message(f"MIDI input read failed: {self._midi_input_error}")
                return
        # New callbacks send normalized dicts; retain compatibility with Mido callers.
        event = (dict(message) if isinstance(message, dict) and
                 message.get("type") in ("cc", "note", "pitchwheel", "aftertouch", "polytouch")
                 else decode_input_message(message))
        if event is None:
            return
        event["port"] = str(port_name)
        self._midi_diagnostics.received(event)
        self._midi_input_event_count = int(getattr(self, "_midi_input_event_count", 0)) + 1
        self._midi_input_event_signal.emit(dict(event))
        if self._midi_learn_target is not None:
            target = dict(self._midi_learn_target)
            if (target.get("kind", "block_parameter") == "block_parameter"
                    and self.get_entity(target.get("block_id")) is None):
                self._cancel_midi_learn()
                self.set_message("MIDI Learn: target was deleted; choose another parameter.")
                return
            mapping = normalize_mapping({
                "source": {"port": port_name, "type": event["type"],
                           "channel": event["channel"], "number": event["number"]},
                "target": target, "min": target.get("min", 0.0),
                "max": target.get("max", 1.0), "initial": target.get("initial", target.get("min", 0.0)),
                # Note velocity is a trigger, often always 127; it cannot
                # sweep through an arbitrary target value for soft takeover.
                "pickup": event["type"] != "note", "enabled": True,
            })
            if mapping is None:
                self.set_message("MIDI Learn: target is invalid; choose Learn on a numeric control again.")
                return
            self._clear_midi_mapping_for_target(target)
            if len(self.project.midi_mappings) >= MAX_MAPPINGS:
                self.set_message(f"MIDI Learn: limit of {MAX_MAPPINGS} mappings reached.")
                return
            self.project.midi_mappings.append(mapping)
            self._midi_diagnostics.mark("learned", mapping_id=mapping["id"], target=mapping["target"])
            self._midi_learn_runtime.prime(mapping["id"], event["value"])
            self._mark_dirty()
            self._midi_learn_target = None
            self._notify_midi_mappings_changed()
            if hasattr(self, "midi_learn_button"):
                self.midi_learn_button.setText("MIDI IN ✓" if self._midi_input_name else "MIDI IN")
            self.set_message(
                f"Learned {event['type'].upper()} "
                f"{event.get('number') if event.get('number') is not None else ''} "
                f"CH {int(event['channel']) + 1 if event.get('channel') is not None else 'OMNI'} "
                f"→ {target.get('parameter', 'Global Macro')}"
            )
            return

        matched = False
        for mapping in list(self.project.midi_mappings or []):
            if not mapping_matches(mapping, port_name, event):
                continue
            matched = True
            target = mapping.get("target", {})
            if target.get("kind") == "global_macro":
                index = int(target.get("macro_index", 0))
                if not 0 <= index < 4:
                    continue
                current = float(self.project.macros[index].get("value", .5))
                integer = False
            else:
                block = self.get_entity(target.get("block_id"))
                key = str(target.get("parameter", ""))
                if block is None or not key:
                    continue
                current = block.parameters.get(key, mapping.get("initial", mapping.get("min", 0.0)))
                # Pickup follows the authored layer, just like a manual knob
                # edit. Perform/Composition may move the effective value on
                # every tick; using it can prevent pickup indefinitely.
                entry = self.engine.parameter_influence.entries.get((block.id, key))
                if entry is not None:
                    exists, base = entry["base"]
                    current = base if exists else mapping.get("initial", mapping.get("min", 0.0))
                if isinstance(current, bool):
                    continue
                integer = bool(target.get("integer", isinstance(current, int)))
            value = self._midi_learn_runtime.value_for(mapping, port_name, event, current)
            if value is None:
                self._midi_diagnostics.mark("pickup", target=target, manual=current,
                                            input_value=event["value"], mapping_id=mapping["id"])
                continue
            if integer:
                value = int(round(value))
            if target.get("kind") == "global_macro":
                self._midi_diagnostics.mark("queued", target=target, value=value, mapping_id=mapping["id"])
                self._set_global_macro(index, value)
            else:
                # A burst can return to the current model value before its
                # first edit commits. Compare with the last queued position,
                # otherwise the return is dropped and the knob stops early.
                with self._pending_param_edits_lock:
                    pending = self._pending_param_edits.get(int(block.id), {}).get(key, current)
                if abs(float(pending) - float(value)) > 1e-9:
                    self._midi_diagnostics.mark("queued", target=target, value=value, mapping_id=mapping["id"])
                    self._set_param(block, key, value)
                else:
                    self._midi_diagnostics.mark("unchanged", target=target, value=value)
        if not matched:
            self._midi_diagnostics.mark("unmatched", event=dict(event))

    def refresh_midi(self):
        ports, err = get_midi_output_names()
        inputs, input_err = get_midi_input_names()
        self._midi_output_names = list(ports)
        self._midi_output_error = err
        self.midi_status.setText(f"MIDI: {len(ports)} out / {len(inputs)} in" if not err and not input_err else "MIDI: ERROR")
        if err or input_err:
            self.set_message(err or input_err)
        if hasattr(self, "inspector_scroll"):
            self._queue_inspector_refresh()

    def _update_title(self):
        name = Path(self.current_path).name if self.current_path else "untitled"
        marker = " *" if getattr(self, "_dirty", False) else ""
        self.setWindowTitle(f"Auricle — {name}{marker}")

    def save_project(self):
        if not self.current_path:
            return self.save_project_as()
        return self._write_project(self.current_path)

    def save_project_as(self):
        start = self.current_path or "auricle_project.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save project", start, "Auricle Project (*.json)")
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".json"
        return self._write_project(path)

    def _write_project(self, path):
        try:
            panel = getattr(getattr(self, "composition_panel", None), "automation_panel", None)
            if panel is not None:
                panel.flush()
            with self.transport._transport_lock:
                self.transport._drain_gui_commands(notify=True)
                save_project(project_from_dict(document_state(self.project, self.engine)), path)
        except Exception as exc:  # serialisation errors are not OSError
            QMessageBox.critical(self, "Save failed", f"Could not save {path}:\n{exc}")
            return False
        self.current_path = path
        self._dirty = False
        self.history_controller.saved()
        self._update_title()
        self.set_message(f"Saved {Path(path).name}")
        return True

    def new_project(self):
        if not self._confirm_discard_changes():
            return
        previous = self.project
        self.project = Project()
        self._seed_project()
        project, self.project = self.project, previous
        self._install_project(project, None, "New project")

    def open_project(self):
        if not self._confirm_discard_changes():
            return
        start = str(Path(self.current_path).parent) if self.current_path else ""
        path, _ = QFileDialog.getOpenFileName(self, "Open project", start, "Auricle Project (*.json)")
        if not path:
            return
        try:
            project = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", f"Could not open {path}:\n{exc}")
            return
        self._install_project(project, path, f"Loaded {Path(path).name}")

    def _restore_parameter_history(self, before, state):
        """Restore knob/macro edits without replacing models or their widgets.

        Only controls with explicit parameter bindings can use this path. Other
        edits retain the complete document restore, including topology changes.
        """
        from copy import deepcopy
        changes = parameter_only_changes(before, state)
        if changes is None:
            return False
        if any(getattr(self, name, None) for name in (
                '_block_type_change_pending', '_algorithm_change_pending',
                '_mode_change_pending', '_process_type_pending', '_port_change_pending')):
            # The full restore also cancels queued structural edits. They must
            # not run after Undo and silently overwrite the restored document.
            return False
        roots = [self.inspector_scroll.widget()]
        if self.drum_kit_layout.count():
            roots.append(self.drum_kit_layout.itemAt(0).widget())
        controls = [control for root in roots if root is not None
                    for control in root.findChildren(Knob)
                    if hasattr(control, '_auricle_parameter')]
        bindings = {control._auricle_parameter for control in controls}
        if any((bid, key) not in bindings for bid, keys in changes.items() for key in keys):
            return False

        resume_mode = self.transport.playback_mode if self.transport.running else None
        self._installing_project = True
        try:
            self.transport.stop()
            self.transport.drum_output_history.clear()
            # All objects remain the same: the Inspector/Kit signal closures,
            # relation rows and Perform cards must keep editing current models.
            def restore(payloads):
                for payload in payloads:
                    block = self.get_entity(payload['id'])
                    block.parameters.clear()
                    block.parameters.update(deepcopy(payload.get('parameters', {})))
                    block.outputs = {}
                    restore(payload.get('drum_voices') or [])
            restore(state['blocks'])
            self.project.macros = deepcopy(state.get('macros', []))
            self.project.performance = deepcopy(state.get('performance', {}))
            self.project.motifs = deepcopy(state.get('motifs', {}))
            self.project.phrase_state = {}
            self.engine = MusicEngine(self.project)
            self._midi_learn_runtime.reset()
            self.engine.composition_runtime.playback_active = (resume_mode == "composition"
                                                               if resume_mode is not None else None)
            self._midi_events.clear(); self._generated_live_events.clear(); self._piano_freeze = None
            self.performance.director_panel.apply_to_engine()
            self.engine.generate()
            for control in controls:
                bid, key = control._auricle_parameter
                block = self.get_entity(bid)
                blocked = control.blockSignals(True)
                try:
                    control.setValue(block.parameters.get(key, control.default))
                finally:
                    control.blockSignals(blocked)
            self.global_macro_bar.refresh_from_project()
            self.performance.phrase_panel.sync_from_project()
            for card in self.performance.cards.values():
                blocked = card.enable.blockSignals(True)
                card.enable.setChecked(False)
                card.enable.setText('ENABLE')
                card.enable.blockSignals(blocked)
                card.status.setText('idle')
            block = self._selected_inspector_entity()
            self._update_algorithm_preview(block)
            if block is not None:
                p = block.parameters
                summaries = {
                    'inspectorGroup_GENERATOR': self._generator_summary(block),
                    'inspectorLayer_STRUCTURE': f"D {float(p.get('fill_density', 1)):.2f} · P {float(p.get('event_probability', 1)):.2f}",
                    'inspectorLayer_MUSICAL': f"{p.get('scale_name', self.project.scale)} · T {float(p.get('transpose', 0)):+.0f} · O {float(p.get('octave', 0)):+.0f}",
                    'inspectorGroup_ROLE': f"{block.block_type} · center {float(p.get('role_center', 0)):+.0f} · width {float(p.get('role_width', 24)):.0f} · density {float(p.get('role_density', 1)):.2f}",
                    'inspectorGroup_REPRESENTATION': f"Vel {float(p.get('velocity_base', .72)):.2f} · Accent {float(p.get('velocity_accent', .18)):.2f}",
                }
                for name, summary in summaries.items():
                    group = self.inspector_scroll.widget().findChild(QWidget, name)
                    if group is not None:
                        group.set_summary(summary)
            if hasattr(self, 'piano_roll') and isValid(self.piano_roll):
                self.piano_roll.engine = self.engine
                self.piano_roll.set_frozen(False)
                freeze = self.piano_roll.parentWidget().findChild(QCheckBox)
                if freeze is not None:
                    blocked = freeze.blockSignals(True)
                    freeze.setChecked(False)
                    freeze.blockSignals(blocked)
            self._update_piano_roll()
            self._update_kit_status()
            self._update_motif_status()
            self.relation_graph._refresh_builtin_status()
            return True
        finally:
            self._installing_project = False

    def _install_project(self, project, path, message, selection=None, *, playback_mode=None, composition_position=0.):
        # Commit edits against the old project before swapping its model graph.
        self.transport.flush_gui_commands(notify=False)
        # Even the same device must start a new input session: its queued
        # events belong to the previous project's mappings and Learn target.
        self.disconnect_midi_input()
        self._installing_project = True
        for name in ("_block_type_change_pending", "_algorithm_change_pending", "_mode_change_pending",
                     "_process_type_pending", "_port_change_pending", "_regen_pending"):
            pending = getattr(self, name, None)
            if pending is not None: pending.clear()
        self.transport.stop()
        self.transport.drum_output_history.clear()
        self._drum_voice_clipboard = None
        self._voice_paste_undo = {}
        self.project = project
        self.project.midi_sync = normalize_midi_sync(getattr(self.project, "midi_sync", {}))
        self.project.midi_mappings = normalize_mappings(getattr(self.project, "midi_mappings", []))
        self.project.midi_input_port = str(getattr(self.project, "midi_input_port", "") or "")
        ensure_global_macros(self.project)
        self.engine = MusicEngine(self.project)
        self.transport.playback_mode = playback_mode or "blocks"
        self.transport.composition_position = float(composition_position)
        self.engine.composition_runtime.playback_active = (playback_mode == "composition"
                                                           if playback_mode is not None else None)
        if hasattr(self, "composition_panel"):
            self.composition_panel.sync_from_project()
        self.transport.app = self
        self.selected_block_id = self.project.blocks[0].id if self.project.blocks else None
        if selection is None:
            # Keep Open/Reload's existing voice selection when it still belongs
            # to the first block; Undo supplies its explicit block/voice pair.
            selection = (self.selected_block_id, self.selected_drum_voice_id)
        self.selected_drum_voice_id = None
        block = self.get_block(selection[0])
        if block is not None:
            self.selected_block_id = block.id
            if any(voice.id == selection[1] for voice in block.drum_voices or []):
                self.selected_drum_voice_id = selection[1]
        self._midi_events.clear(); self._generated_live_events.clear(); self._piano_freeze = None
        if hasattr(self, "midi_sync_button"):
            sync = normalize_midi_sync(self.project.midi_sync)
            self.midi_sync_button.setText("SYNC ON" if sync["clock_out"] or sync["transport_messages"] else "SYNC")
        # Sync the header widgets without firing their handlers: _harmony_changed
        # would otherwise overwrite the loaded per-block scale settings.
        for widget, setter, value in ((self.tempo, self.tempo.setValue, self.project.tempo),
                                      (self.length, self.length.setValue, self.project.length),
                                      (self.key, self.key.setCurrentIndex, self.project.root_note % 12),
                                      (self.scale, self.scale.setCurrentText, self.project.scale)):
            widget.blockSignals(True); setter(value); widget.blockSignals(False)
        self.performance.rebuild_macro_panel()
        if hasattr(self, "global_macro_bar"):
            self.global_macro_bar.refresh_from_project()
        # The engine restores PhraseState from the project, but the phrase
        # combo is a separate widget and otherwise kept its previous value.
        self.performance.phrase_panel.sync_from_project()
        self.performance.phrase_panel._save_settings()
        self.performance.harmonic_panel.sync()
        # Restore saved Director controls before pushing them into the new engine.
        self.performance.director_panel.sync_from_project()
        self.performance.director_panel.apply_to_engine()
        self.engine.generate(); self._refresh_all()
        self.current_path = path
        self._dirty = False
        self._installing_project = False
        self._midi_learn_runtime.reset()
        self._midi_learn_target = None
        self._sync_midi_input_port()
        if hasattr(self, "history_controller"):
            self.history_controller.reset()
        self._update_title()
        self.set_message(message)

    def _reflow_inspector_responsive_forms(self):
        page = getattr(self, "inspector_page", None)
        if page is None:
            return
        for form in getattr(page, "_auricle_reflow_forms", ()):
            form.reflow()

    def _assign_composition_automation(self, entity_id, key):
        panel = self.composition_panel.automation_panel
        if panel.assign(int(entity_id), str(key)):
            self.tabs.setCurrentWidget(self.composition_panel)
            self.composition_panel.composition_tabs.setCurrentWidget(panel)
            self.composition_panel.update_runtime()
            self.set_message('Automation assigned to the selected section; playback is unchanged')

    def _open_automation_influences(self, entity_id, key):
        from parameter_influence_ui import InfluenceDialog
        if self.get_entity(entity_id) is None:
            return
        dialog = InfluenceDialog(self, entity_id, key)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()

    def _attach_automation_context(self, control, entity_id, key):
        from section_automation import parameter_specs
        entity = self.get_entity(entity_id)
        if entity is None or key not in parameter_specs(self.engine, entity):
            return
        control._auricle_parameter = (entity_id, key)
        control.setContextMenuPolicy(Qt.CustomContextMenu)
        def show_menu(position):
            menu = control.createStandardContextMenu() if isinstance(control, QLineEdit) else QMenu(control)
            if isinstance(control, QLineEdit): menu.addSeparator()
            assign = menu.addAction('Automate in Composition…')
            influences = menu.addAction('Parameter influences…')
            chosen = menu.exec(control.mapToGlobal(position))
            if chosen == assign: self._assign_composition_automation(entity_id, key)
            elif chosen == influences: self._open_automation_influences(entity_id, key)
            menu.deleteLater()
        control.customContextMenuRequested.connect(show_menu)

    def _queue_inspector_fit(self):
        timer = getattr(self, "_inspector_fit_timer", None)
        if timer is not None and not timer.isActive():
            timer.start(0)

    def eventFilter(self, obj, event):
        scroll = getattr(self, "inspector_scroll", None)
        if (scroll is not None and event.type() == QEvent.Resize and obj is scroll.viewport()
                and event.size().width() != event.oldSize().width()):
            # The viewport has its final width only after the window layout
            # ran; resizeEvent saw the old width, so the Inspector did not
            # fill the window after maximizing.
            self._queue_inspector_fit()
        return super().eventFilter(obj, event)

    def _sync_inspector_scroll_extent(self, page=None):
        """Recompute the full Inspector content height after dynamic UI changes.

        The Inspector contains a persistent Drum Kit host plus a rebuilt block
        content widget.  Both nested layouts must contribute their *current*
        minimum height to the scroll page; stale minimums used to leave the
        scrollbar short of the final controls after a collapse/expand or edit.
        """
        scroll = getattr(self, "inspector_scroll", None)
        if scroll is None or not isValid(scroll):
            return
        page = page or scroll.widget()
        if page is None or not isValid(page):
            return

        # Re-measure nested accordions from the leaves upward.  In particular,
        # DrumRhythmPanel.Settings can shrink its parent kit editor immediately.
        for group in page.findChildren(InspectorGroup):
            group._sync_layout_geometry()
        for group in page.findChildren(LayerGroup):
            group._sync_layout_geometry()

        content = page.findChild(QWidget, "inspectorContent")
        if content is not None:
            content_layout = content.layout()
            if content_layout is not None:
                content_layout.invalidate()
                content_layout.activate()
                content_hint = content_layout.sizeHint()
                content_min = content_layout.minimumSize()
                content_height = max(content_hint.height(), content_min.height(), 0)
                if content.minimumHeight() != content_height:
                    content.setMinimumHeight(content_height)
                    content.updateGeometry()

        page_layout = page.layout()
        if page_layout is not None:
            page_layout.invalidate()
            page_layout.activate()
            page_hint = page_layout.sizeHint()
            page_min = page_layout.minimumSize()
            required_height = max(page_hint.height(), page_min.height(), 1)
            if page.minimumHeight() != required_height:
                page.setMinimumHeight(required_height)
                page.updateGeometry()

        # With widgetResizable=True, Qt keeps the page at viewport width while
        # respecting the calculated minimum height and updates the scrollbar
        # range after the pending layout pass.
        if page_layout is not None:
            page_layout.invalidate()
            page_layout.activate()
        scroll.updateGeometry()
        scroll.viewport().updateGeometry()

    def _fit_inspector_page(self):
        scroll = getattr(self, "inspector_scroll", None)
        page = scroll.widget() if scroll is not None else None
        if page is None:
            return
        self._reflow_inspector_responsive_forms()
        self._sync_inspector_scroll_extent(page)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "theme_label"):
            compact = self.width() < 1200
            self.theme_label.setVisible(not compact)
            self.midi_status.setVisible(not compact)
            self.theme_combo.setFixedWidth(88 if compact else 105)
            # Stack captions only in compact windows; the larger musical
            # controls retain their full width and height without overlapping.
            for group, label in self._transport_fields:
                group.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)
                group.setSpacing(3 if compact else 6)
                label.setAlignment(Qt.AlignCenter if compact else Qt.AlignVCenter | Qt.AlignLeft)
        # Collapse the Inspector to one column when the available width becomes
        # too small. This avoids squeezing QFormLayout fields until they overlap.
        available = self.inspector_scroll.viewport().width() if hasattr(self, "inspector_scroll") else self.width()
        if hasattr(self, "inspector_page") and hasattr(self, "inspector_scroll"):
            # QScrollArea owns page width; reflow after the viewport has its
            # final dimensions, then republish the complete content extent.
            self._queue_inspector_fit()
        columns = 2 if available >= 620 else 1
        if hasattr(self, "_inspector_columns") and columns != self._inspector_columns:
            self._inspector_columns = columns

    def closeEvent(self, event):
        if not self._confirm_discard_changes():
            event.ignore()
            return
        if hasattr(self, "timer"):
            self.timer.stop()
        if hasattr(self, "performance_timer"):
            self.performance_timer.stop()
        runtime = getattr(self, "_algo_conf_runtime", None)
        if runtime is not None and isValid(runtime):
            runtime.stop()
        self.history_controller.close()
        self.transport.flush_gui_commands(notify=False)
        self.transport.stop()
        if hasattr(self, "transport_worker"):
            self.transport_worker.stop()
        self.transport.close_ports(); self.disconnect_midi_input(); event.accept()


def main():
    import os
    from contextlib import ExitStack
    from tempfile import TemporaryDirectory

    smoke_test = "--smoke-test" in sys.argv
    with ExitStack() as resources:
        if smoke_test:
            # A build check must not offer or modify a user's recovery session.
            recovery = resources.enter_context(TemporaryDirectory(prefix="auricle-smoke-"))
            os.environ["AURICLE_RECOVERY_DIR"] = recovery
            missing = [name for name in REQUIRED_ASSETS if not asset_path(name).is_file()]
            if missing:
                raise RuntimeError("Missing bundled assets: " + ", ".join(missing))
        _run_application(smoke_test)


def _run_application(smoke_test=False):
    # Older algo_conf exports replace their managed block. Keep production
    # playback on the bounded runtime shipped with Auricle after such a save.
    from ui_profile_runtime import _AlgoConfRuntime as profile_runtime
    globals()["_AlgoConfRuntime"] = profile_runtime
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("org.auricle.Auricle")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("Auricle")
    app.setDesktopFileName("auricle")
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")  # consistent base style under the theme stylesheet
    app.setWindowIcon(application_icon())
    win = MainWindow()
    win.show()
    if smoke_test:
        if win.brand_logo.pixmap().isNull() or win.help_logo.pixmap().isNull():
            win.close()
            raise RuntimeError("The bundled logo could not be rendered")
        QTimer.singleShot(500, win, win.close)
    else:
        QTimer.singleShot(350, win, lambda: win.history_controller.offer_recovery(startup=True))
    sys.exit(app.exec())


# >>> ALGO_CONF:BEGIN v1
from ui_profile_runtime import (_algo_conf_install, _AlgoConfRuntime, _ac_tree, _ac_owner, _ac_resolve)

# Geometry now belongs to the shared UI metrics. Keep the profile hook for
# explicit future user customizations without replaying obsolete one-off sizes.
_ALGO_CONF_DATA = {'version': 1, 'window_class': 'MainWindow', 'entries': {}}
_algo_conf_install(globals(), _ALGO_CONF_DATA)
# <<< ALGO_CONF:END v1
if __name__ == "__main__":
    main()
