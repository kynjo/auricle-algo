"""Auricle Qt user interface."""
from __future__ import annotations

import math
import random
import sys
import time
from pathlib import Path
from shiboken6 import isValid

from PySide6.QtCore import Qt, Signal, QTimer, QSize, QRectF, QPoint, QPointF, QEvent
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPixmap, QIcon, QPalette, QKeySequence, QShortcut, QPainterPath
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QSlider, QComboBox,
    QListWidget, QListWidgetItem, QGroupBox, QLineEdit, QDialog,
    QDialogButtonBox, QMessageBox, QFileDialog, QSplitter, QScrollArea, QMenu,
    QFrame, QButtonGroup, QSizePolicy, QAbstractItemView, QCheckBox, QInputDialog, QLayout,
    QTabWidget, QTabBar, QTextBrowser, QProgressBar, QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem, QColorDialog,
)

from auricle_core import (
    APP_VERSION, BLOCK_TYPES, GENERATORS, MUTATORS, NON_NUMERIC_PARAMETERS, NOTE_NAMES, PARTS, ROLE_PROFILES, apply_role_defaults,
    PROCESS_TARGETS, PROCESS_TYPES, RELATIONS, SCALES, Block, MusicEngine, Mutator, Process,
    Project, Relation, Transport, DrumVoice, ensure_drum_voices, get_midi_output_names, load_project, midi_note_for, save_project,
    next_relation_id, remove_relation, duplicate_relation, validate_relations, presets_for, preset_for,
)

from performance_presets import phrases as performance_phrases, phrase_for, phrase_with_duration, interpolate_preset
from ui_themes import theme_names, theme_palette, theme_stylesheet, mix as theme_mix, on_color
from help_content import help_html
from auricle_drum import KIT_DEFAULTS, KIT_TOOLTIPS, kit_value
from coordinated_kit import (ROLES as KIT_ROLES, STYLES as KIT_STYLES, METERS as KIT_METERS,
                             CREATIVE_DEFAULTS, creative_value, KitStep, coordinated,
                             voice_role, infer_role, phrase_bars, STEP_BEATS)
from motif_development import MODES as MOTIF_MODES, settings as motif_settings, digest as motif_digest
from pattern_chance import step_chances
from drum_editing import sound_snapshot, apply_sound
from project_history_ui import HistoryController
from project_history import document_state, parameter_only_changes
from auricle_persistence import project_from_dict
from harmonic_plan_ui import HarmonicPlanPanel
from instrument_dialogue_ui import DialogueControls
from auricle_resources import asset_path, REQUIRED_ASSETS

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
    "ca_generations": "Generations", "ca_density": "Density", "ls_iterations": "Iterations",
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
        f"QPushButton#blockMute {{ background:{t.input}; color:{t.muted}; border:1px solid {t.border}; border-radius:5px; font-weight:700; padding:0; }}"
        f"QPushButton#blockMute:hover {{ border-color:{t.accent}; color:{t.text}; }}"
        f"QPushButton#blockMute:checked {{ background:{t.danger}; color:{on_color(t.danger)}; border:2px solid {t.danger}; }}"
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
}

ALGORITHM_AFFINITY_COLORS = {
    "rhythm": "#2f7de1",  # blue
    "pitch": "#e58a24",   # orange
}

def algorithm_affinity(name: str) -> str:
    """Return the GUI classification for an algorithm."""
    return ALGORITHM_AFFINITY.get(str(name), "both")


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


def monochrome_tab_icon(symbol: str, size: int = 16, color: str | None = None) -> QIcon:
    """Small monochrome tab glyph; avoids theme-dependent colored system icons."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(QColor(color or active_theme().muted), 1.5))
    font = p.font()
    font.setPixelSize(12)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pix.rect(), Qt.AlignCenter, symbol)
    p.end()
    return QIcon(pix)


class Knob(QWidget):
    """Compact circular control with a layout-owned numeric readout.

    The dial is painted only in the upper region.  The value is a real QLabel
    child, so accordion/scroll-area geometry cannot clip it independently of
    the control's size hint.
    """
    changed = Signal(float)

    def __init__(self, value=0.5, parent=None, default=None, lo=0.0, hi=1.0, integer=False, decimals=2):
        super().__init__(parent)
        self.lo=float(lo); self.hi=float(hi); self.integer=bool(integer); self.decimals=int(decimals)
        self.default=float(value if default is None else default)
        self._value=float(value)
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
        self.setToolTip(self.toolTip() + " · Click value or right-click for parameter influences")

    def _norm(self):
        if self.hi == self.lo: return 0.0
        return max(0.0, min(1.0, (self._value-self.lo)/(self.hi-self.lo)))

    def _formatted(self):
        if self.integer: return str(int(round(self._value)))
        if self.decimals <= 0: return str(int(round(self._value)))
        return f"{self._value:.{self.decimals}f}"

    def value(self):
        return int(round(self._value)) if self.integer else self._value

    def _sync_value_label(self):
        if hasattr(self, "value_label"):
            self.value_label.setText(self._formatted())

    def setValue(self, value):
        v=max(self.lo,min(self.hi,float(value)))
        if self.integer: v=round(v)
        changed=abs(v-self._value)>1e-12
        self._value=v
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
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.addButton(self.seq)
        self.group.addButton(self.live)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addWidget(self.seq)
        layout.addWidget(self.live)
        self.setFixedHeight(22)
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
        hint = layout.sizeHint()
        if hint.isValid():
            self.setMinimumHeight(max(0, hint.height()))
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
            hint = layout.sizeHint()
            if hint.isValid():
                self.setMinimumHeight(max(0, hint.height()))
        else:
            self.setMinimumHeight(0)
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
            self.scene.addItem(line)
            txt=QGraphicsTextItem(f"{r.source_part} → {r.algorithm} → {r.destination_part}")
            txt.setDefaultTextColor(QColor(active_theme().text))
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
                txt=QGraphicsTextItem(f"+1 tick  →  {proc.parameters.get('destination_parameter','parameter')}")
                txt.setDefaultTextColor(QColor(active_theme().muted))
                txt.setPos((a.center().x()+d.center().x())/2-50,(a.center().y()+d.center().y())/2+6)
                self.scene.addItem(txt)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-30,-30,30,30))


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
        self.setMinimumHeight(56)
        self.setMaximumHeight(62)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_technique(self, preset, amount=1.0, shape="in"):
        self.preset = preset
        self.amount = float(amount)
        self.shape = str(shape or "in")
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
        curve_colors = (QColor(theme.accent), QColor(theme.accent2), QColor(theme.success), QColor(theme.warning), QColor(theme.danger))
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
        self.host.project.performance["_phrase"] = {
            "phrase_id": self.phrase_combo.currentData(),
            "duration_beats": float(self.duration.value()),
            "amount": self.amount.value() / 100.0,
            "block_ids": self._selected_ids(),
        }
        self.host._mark_dirty()

    def _duration_changed(self, value):
        with self.host.transport._state_lock:
            state = self.host.engine.director.phrase
            if state.running and state.phrase_id == self.phrase_combo.currentData():
                self.host.engine.performance.update_phrase_duration(float(value))
        self._refresh_phrase_preview()
        self.update_runtime()
        self._save_settings()

    def _selected_ids(self):
        return sorted(self._target_ids) or [b.id for b in self.host.project.blocks if not b.muted]

    def _amount_changed(self, value):
        self.amount_label.setText(f"{value}%")
        updater = getattr(self.host.engine.performance, "update_phrase_amount", None)
        if updater is not None:
            updater(value / 100.0)
        self._save_settings()

    def _start(self):
        ids = self._selected_ids()
        pid = self.phrase_combo.currentData()
        with self.host.transport._state_lock:
            started = self.host.engine.performance.start_phrase(
                self.host.project, pid, ids, self.amount.value()/100.0,
                duration_beats=float(self.duration.value()))
        if started:
            self._save_settings()
            if not self.host.transport.running:
                self.host.transport.start()
            self.start.setText("RESTART PHRASE")
            self.host.set_message(f"Phrase: {self.phrase_combo.currentText()}")

    def _stop(self):
        # Stop the phrase that is actually running, even if the selector was
        # moved to another phrase after it started (that used to do nothing).
        state = self.host.engine.director.phrase
        pid = state.phrase_id if state.running and state.phrase_id else self.phrase_combo.currentData()
        self.host.engine.performance.stop_phrase(pid)
        self.start.setText("PLAY PHRASE")
        self.host.set_message("Phrase stopped")

    def update_runtime(self):
        """Reflect the live PhraseState; called from the UI heartbeat."""
        state = self.host.engine.director.phrase
        running = bool(state.running)
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
        # The card's own stylesheet overrides the application rules, so the
        # selected state must be declared here too (it was never visible).
        theme = active_theme()
        self.setStyleSheet(
            f"QFrame#performCard {{ border:1px solid {theme_mix(accent, theme.border, .45)}; border-left:4px solid {accent}; border-radius:7px; background:{theme.card}; }}"
            f"QFrame#performCard[selected=\"true\"] {{ border:2px solid {theme.accent}; border-left:4px solid {accent}; }}"
        )

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
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background:{accent}; border-radius:2px;")
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

        # Legacy wording retained in this comment for project migration tools:
        # self.mute_button = QPushButton("MUTED" if block.muted else "MUTE")
        # Legacy wording retained in this comment for project migration tools: self.mute_button = QPushButton("MUTED" if block.muted else "MUTE")
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
        if state.get("enabled") and not getattr(getattr(self.host, "history_controller", None), "restoring", False):
            running = self.host.engine.performance.active.get(self.block_id)
            if running is not None and getattr(running, "phrase_id", None) is None:
                # Card rebuilt while its gesture plays: reflect, do not restart.
                self.enable.blockSignals(True)
                self.enable.setChecked(True)
                self.enable.setText("DISABLE")
                self.enable.blockSignals(False)
            else:
                self._restart()

    def _load_catalog(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for preset in presets_for(self.block.block_type, self.block.algorithm):
            self.preset_combo.addItem(preset.name, preset.id)
        self.preset_combo.blockSignals(False)
        self._preset_changed(self.preset_combo.currentIndex())

    def _preset_changed(self, _index):
        preset = preset_for(self.block.block_type, self.block.algorithm, self.preset_combo.currentData())
        if not preset:
            return
        self.description.setText(preset.description)
        self.description.setToolTip(preset.description)
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
        self.host.project.performance[str(self.block_id)] = {
            "preset_id": self.preset_combo.currentData(),
            "amount": self.amount.value() / 100.0,
            "shape": self._shape_value(),
            "beats": self._beats(),
            "enabled": bool(self.enable.isChecked() if enabled is None else enabled),
        }
        if hasattr(self.host, "_mark_dirty"):
            self.host._mark_dirty()

    def _settings_changed(self, *_):
        self.amount_label.setText(f"{self.amount.value()}%")
        preset = preset_for(self.block.block_type, self.block.algorithm, self.preset_combo.currentData())
        if preset:
            self.technique_curve.set_technique(preset, self.amount.value() / 100.0, self._shape_value())
        if getattr(self, "_restoring_settings", False): return
        state = self.host.engine.performance.active.get(self.block_id)
        if state:
            state.amount = self.amount.value() / 100.0
            state.shape = self._shape_value()
            state.beats = self._beats()
        self._save_performance_state()

    def _toggle(self, checked):
        if checked:
            self._restart()
        else:
            self.host.engine.performance.stop(self.block_id)
            self.status.setText("idle")
            self.enable.setText("ENABLE")
            self._save_performance_state(False)

    def _restart(self):
        pid = self.preset_combo.currentData()
        ok = bool(pid and self.host.engine.performance.start(self.block, pid, self.amount.value()/100.0, self._shape_value(), self._beats()))
        self.enable.blockSignals(True)
        self.enable.setChecked(ok)
        self.enable.setText("DISABLE" if ok else "ENABLE")
        self.enable.blockSignals(False)
        if ok:
            self.status.setText("armed · 0%")
            self.activity.setValue(0)
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
        with self.host.transport._state_lock:
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

    def set_selected(self, selected):
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
        self.setObjectName("globalMacroBar")
        self.setToolTip("Global Director controls: Energy, Tension, Density and Variation")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)
        title = QLabel("GLOBAL")
        title.setObjectName("muted")
        title.setToolTip("Global musical character")
        layout.addWidget(title)
        for index, (default_name, control) in enumerate(GLOBAL_MACRO_DEFS):
            column = QVBoxLayout()
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            name = QLabel(default_name)
            name.setAlignment(Qt.AlignCenter)
            name.setObjectName("knobLabel")
            color = GLOBAL_MACRO_COLORS[index]
            name.setStyleSheet(f"color:{color}; font-weight:700;")
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            # Let the four header controls share the available width.  A
            # fixed 150 px slider left unused space on wide windows and made
            # the header crowd itself at the minimum window width.
            slider.setMinimumWidth(72)
            slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            slider.setStyleSheet(
                f"QSlider::groove:horizontal {{ height:6px; background:{theme_mix(active_theme().border, color, .35)}; border-radius:3px; }}"
                f"QSlider::sub-page:horizontal {{ background:{color}; border-radius:3px; }}"
                f"QSlider::add-page:horizontal {{ background:{active_theme().input}; border-radius:3px; }}"
                f"QSlider::handle:horizontal {{ background:{color}; border:1px solid {color}; width:14px; margin:-5px 0; border-radius:7px; }}"
                f"QSlider::handle:horizontal:hover {{ background:{active_theme().text}; }}"
            )
            slider.setAccessibleName(f"Global {default_name}")
            slider.setToolTip(f"{default_name} Director control")
            value = QLabel("0%")
            value.setAlignment(Qt.AlignCenter)
            value.setObjectName("knobValue")
            value.setStyleSheet(f"color:{color}; font-weight:600;")
            column.addWidget(name)
            column.addWidget(slider)
            column.addWidget(value)
            layout.addLayout(column, 1)
            self.labels.append(name)
            self.sliders.append(slider)
            self.values.append(value)
            slider.valueChanged.connect(lambda raw, i=index: self._changed(i, raw))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.refresh_from_project()

    def _changed(self, index, raw):
        self.values[index].setText(f"{int(raw)}%")
        self.host._set_global_macro(index, float(raw) / 100.0, self)

    def refresh_from_project(self):
        macros = ensure_global_macros(self.host.project)
        for index, (default_name, _control) in enumerate(GLOBAL_MACRO_DEFS):
            macro = macros[index]
            name = str(macro.get("name") or default_name)
            value = max(0, min(100, int(round(float(macro.get("value", .5)) * 100))))
            self.labels[index].setText(name)
            self.labels[index].setToolTip(f"{name} → Director {macro.get('control', _control)}")
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

    def _control_changed(self, name, value):
        d=getattr(self.host.engine,"director",None)
        if d is None: return
        d.set_control(name,float(value)/100.0)
        if name in self.control_values:
            self.control_values[name].setText(f"{int(value)}%")
            self.controls[name].setToolTip(f"{name}: {int(value)}%")
        if name=="Voice Smooth":
            try:
                # UI and engine share the same meaning:
                # 0% = free voice movement, 100% = maximum smoothing.
                self.host.engine.voice_leading.smoothness=max(0.0, min(1.0, float(value)/100.0))
                self.host.engine.director.voice_smooth=max(0.0, min(1.0, float(value)/100.0))
            except Exception:
                pass
        if not self._control_update_queued:
            self._control_update_queued = True
            QTimer.singleShot(35, self._flush_control_update)

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
                    value = max(0.0, min(1.0, float(smooth.value()) / 100.0))
                    self.host.engine.voice_leading.smoothness = value
                    self.host.engine.director.voice_smooth = value
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
            lambda *_: QTimer.singleShot(0, self._relayout_cards))

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
        self._clear()
        self._grid_columns = 0
        for b in project.blocks:
            card = PerformanceBlockCard(b, self.host)
            card.selected.connect(self.host.select_block)
            card.mute_changed.connect(self.host._card_mute_changed)
            card.mode_changed.connect(self.host._card_mode_changed)
            card.set_selected(b.id == self.host.selected_block_id)
            self.cards[b.id] = card
        self._relayout_cards()

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
        layout.setContentsMargins(9, 6, 9, 7)
        layout.setSpacing(2)

        # Header: numbered badge, name, mute and compact overflow menu.
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(7)

        self.index_badge = QLabel(str(block.id))
        self.index_badge.setObjectName("blockIndex")
        self.index_badge.setAlignment(Qt.AlignCenter)
        self.index_badge.setFixedSize(30, 30)
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
        self.mute_button.setFixedSize(30, 30)
        self.mute_button.setToolTip("Mute block")
        self.mute_button.setFocusPolicy(Qt.NoFocus)
        self.mute_button.setStyleSheet(block_mute_stylesheet())
        self.mute_button.clicked.connect(self._mute_clicked)
        top.addWidget(self.mute_button, 0, Qt.AlignVCenter)

        self.menu_button = QPushButton("⋮")
        self.menu_button.setObjectName("cardMenu")
        self.menu_button.setFixedSize(28, 30)
        self.menu_button.setToolTip("Block options")
        self.menu_button.setFocusPolicy(Qt.NoFocus)
        self.menu_button.clicked.connect(self._show_menu)
        top.addWidget(self.menu_button, 0, Qt.AlignVCenter)
        layout.addLayout(top)

        # Type + transport mode. Type is display-only here; editing is in ⋮.
        type_row = QHBoxLayout()
        type_row.setContentsMargins(37, 0, 0, 0)
        type_row.setSpacing(6)
        self.type_label = QLabel(f"Type: {block.block_type}")
        self.type_label.setObjectName("blockMeta")
        type_row.addWidget(self.type_label, 1, Qt.AlignVCenter)
        self.mode = ModeSwitch(block.mode)
        self.mode.changed.connect(self._mode_changed)
        type_row.addWidget(self.mode, 0, Qt.AlignVCenter)
        layout.addLayout(type_row)

        self.algorithm_label = QLabel(f"Algorithm: {block.algorithm}")
        self.algorithm_label.setObjectName("blockMeta")
        self.algorithm_label.setToolTip(f"Algorithm: {block.algorithm}")
        layout.addWidget(self.algorithm_label)

        self.midi_label = QLabel(f"MIDI Ch: {int(block.midi_channel)}")
        self.midi_label.setObjectName("blockMeta")
        layout.addWidget(self.midi_label)

        self.setMinimumHeight(106)
        self.setMaximumHeight(112)
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
            action = type_menu.addAction(block_type)
            action.setCheckable(True)
            action.setChecked(block_type == self._host_project_block.block_type)
            action.triggered.connect(lambda checked=False, value=block_type: self._type_changed(value))
        menu.addSeparator()
        menu.addAction("Change color…", self._choose_block_color)
        menu.addSeparator()
        menu.addAction("Delete block", self._delete_clicked)
        menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

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
        self.type_label.setText(f"Type: {block.block_type}")
        self.algorithm_label.setText(f"Algorithm: {block.algorithm}")
        self.midi_label.setText(f"MIDI Ch: {int(block.midi_channel)}")
        self.setProperty("muted", bool(block.muted))
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
        self.setMinimumWidth(176)
        self.setFixedHeight(21)
        self.setAccessibleName("Kit bar playhead")

    def set_cursor(self, cursor, steps=16):
        if cursor != self.cursor or steps != self.steps:
            self.cursor, self.steps = cursor, steps
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        width = self.width() / self.steps
        font = painter.font(); font.setPixelSize(9 if width < 13 else 10); painter.setFont(font)
        stride = 2 if width < 13 else 1
        for i in range(self.steps):
            rect = QRectF(i * width + 1, 1, max(1, width - 2), 19)
            if i == self.cursor:
                painter.fillRect(rect, QColor("#ffc568"))
            painter.setPen(QColor("#15202b" if i == self.cursor else "#b7c7d6"))
            # Dense compound-meter grids keep legible labels rather than
            # squeezing adjacent two-digit numbers into a single string.
            if i == self.cursor or (i % stride == 0 and
                    (self.cursor < 0 or abs(i - self.cursor) >= stride)):
                painter.drawText(rect.adjusted(-2, 0, 2, 0), Qt.AlignCenter, str(i + 1))


class KitPlanLane(QWidget):
    """Read-only arrangement for the current bar; source editing stays below."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(176)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.steps, self.cursor = [], -1
        self.output_values = None
        self.groups = (4, 4, 4, 4)
        self.setToolTip("Kit plan before processing: green = protected beat, teal = added hit, outline = optional source slot, orange = fill. The playhead crosses the whole bar, including rests. Edit the generator in SOURCE below.")

    def set_plan(self, steps, cursor, groups=(4, 4, 4, 4)):
        if self.output_values is not None:
            self.setToolTip("Kit plan before processing: green = protected beat, teal = added hit, outline = optional source slot, orange = fill.")
        count = sum(groups)
        steps = (list(steps) + [KitStep()] * count)[:count]
        if steps != self.steps or cursor != self.cursor or groups != self.groups or self.output_values is not None:
            self.steps, self.cursor = steps, cursor
            self.output_values = None
            self.groups = groups
            self.update()

    def set_output(self, values, cursor, groups):
        if self.output_values is None:
            self.setToolTip("Accepted generated output: bar height = velocity, dash = rest, grey = not visited. Includes processing, probability and mute; works without a MIDI port. This is not feedback from the instrument.")
        values = list(values)
        if values != self.output_values or cursor != self.cursor or groups != self.groups:
            self.output_values, self.cursor, self.groups = values, cursor, groups
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
                painter.setPen(QPen(QColor("#8295a6"), 1))
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
        with self.host.transport._state_lock:
            if self.host.get_entity(self.block.id) is not self.block:
                return
            values = step_chances(self.block.parameters)
            values[self.step.value() - 1] = value / 100.
            self.block.parameters["pattern_step_chances"] = values
        self.value_label.setText(f"{value}%"); self.host._mark_dirty()

    def _reset(self):
        with self.host.transport._state_lock:
            if self.host.get_entity(self.block.id) is not self.block:
                return
            self.block.parameters.pop("pattern_step_chances", None)
        self.host._mark_dirty(); self._refresh_value()


class DrumKitEditor(QGroupBox):
    """Compact Drum Machine editor embedded in the DRUM inspector."""
    VOICE_COLORS = ("#e57373", "#ffb74d", "#fff176", "#81c784", "#64b5f6", "#ba68c8")
    voice_selected = Signal(int)

    def __init__(self, host, drum, selected_voice_id=None, parent=None):
        super().__init__("DRUM VOICES / KIT", parent)
        self.host = host
        self.drum = drum
        self.selected_voice_id = selected_voice_id
        self.plan_lanes = {}
        ensure_drum_voices(drum)
        self.setObjectName("drumKitEditor")
        self._build()

    def _voice_pattern(self, voice):
        raw = str(voice.parameters.get("pattern", "1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0"))
        values = []
        for token in raw.replace(";", ",").split(","):
            try:
                values.append(float(token.strip()))
            except (TypeError, ValueError):
                values.append(0.0)
        return (values or [1.0, 0.0] * 8)[:16]

    def _set_pattern(self, voice, index, checked):
        values = self._voice_pattern(voice)
        values[index] = 1.0 if checked else 0.0
        voice.parameters["pattern"] = ",".join(str(int(value)) for value in values)
        voice.algorithm = "Pattern"
        self.host._mark_dirty()
        self.host.engine.regenerate(self.drum)
        if voice.id == getattr(self.host, "selected_drum_voice_id", None):
            self.host._queue_inspector_refresh("SOURCE")

    def _changed(self, voice, key, value):
        with self.host.transport._state_lock:
            if not any(block is self.drum for block in self.host.project.blocks):
                return
            self._change_voice(voice, key, value)

    def _change_voice(self, voice, key, value):
        if key == "midi_channel":
            voice.midi_channel = max(1, min(16, int(value)))
            voice.midi_channel_override = voice.midi_channel != int(self.drum.midi_channel)
        elif key == "midi_note":
            voice.parameters.setdefault("kit_role", voice_role(voice))
            voice.midi_note = max(0, min(127, int(value)))
        elif key == "midi_port":
            voice.midi_port = str(value or "")
        elif key == "mode":
            voice.mode = str(value)
            self.host.engine.reset_live()
        elif key == "algorithm":
            voice.algorithm = str(value)
        elif key == "muted":
            voice.muted = bool(value)
        else:
            voice.parameters[key] = value
        self.host._mark_dirty()
        self.host.engine.regenerate(self.drum)
        # The ModeSwitch lives inside the pinned kit.  Rebuild the kit after
        # the signal unwinds so its lane changes immediately between the
        # 16-step Pattern controls and the LIVE STREAM label.  The deferred
        # refresh also avoids deleting the emitting Qt button mid-signal.
        if key in ("mode", "kit_role") or voice.id == getattr(self.host, "selected_drum_voice_id", None):
            self.host._queue_inspector_refresh()

    def _set_config(self, key, value):
        with self.host.transport._state_lock:
            if not any(block is self.drum for block in self.host.project.blocks):
                return
            self.drum.parameters[key] = value
            for voice in self.drum.drum_voices:
                voice.parameters.setdefault("kit_role", voice_role(voice))
            self.host.engine.regenerate(self.drum)
        self.host._mark_dirty()
        self.update_position()
        if key == "kit_coordinated":
            self.host._queue_inspector_refresh()

    def _auto_roles(self):
        # An explicit repair action also fixes files saved by stage 3 with
        # every custom-note voice misclassified as Perc. Keep MIDI routing.
        with self.host.transport._state_lock:
            if not any(block is self.drum for block in self.host.project.blocks):
                return
            for voice in self.drum.drum_voices:
                voice.parameters["kit_role"] = infer_role(voice.midi_note, voice.name)
            self.host.engine.regenerate(self.drum)
        self.host._mark_dirty()
        self.host._queue_inspector_refresh()

    def _view_changed(self, *_):
        self.host._kit_output_view = self.view_selector.currentData() == "output"
        self.update_position()

    def _selected_voice(self):
        return next((v for v in self.drum.drum_voices if v.id == self.selected_voice_id), None)

    def _copy_voice(self, voice=None):
        voice = voice or self._selected_voice()
        if voice is None:
            return
        with self.host.transport._state_lock:
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
        with self.host.transport._state_lock:
            if self.host.get_entity(voice.id) is not voice:
                return
            previous = sound_snapshot(voice)
            self.host.engine.performance.stop(voice.id)
            apply_sound(voice, data)
            # Reset generator-specific memory while retaining the number of
            # elapsed steps. Copying a walk/Markov source must not keep the
            # previous sound's hidden state or restart the voice's clock.
            events = int(self.host.engine.live_state.get(voice.id, {}).get("events", 0))
            self.host.engine.live_state[voice.id] = {"events": events, "phase_index": events}
            self.host.engine.live_rng.pop(voice.id, None)
            if undo:
                history.pop(voice.id, None)
            else:
                history[voice.id] = previous
            self.host._voice_paste_undo = history
            self.host.engine._kit_source_cache.pop(voice.id, None)
            self.host.engine.regenerate(self.drum)
        self.host._mark_dirty()
        self.host.set_message(f"{'Restored' if undo else 'Pasted'} sound settings: {voice.name}")
        self.host._queue_inspector_refresh()

    def _voice_menu(self, voice, button, pos):
        menu = QMenu(self)
        menu.addAction("Copy sound settings", lambda: self._copy_voice(voice))
        paste = menu.addAction("Paste sound settings", lambda: self._paste_voice(voice))
        paste.setEnabled(getattr(self.host, "_drum_voice_clipboard", None) is not None)
        undo = menu.addAction("Undo last paste", lambda: self._paste_voice(voice, undo=True))
        undo.setEnabled(voice.id in getattr(self.host, "_voice_paste_undo", {}))
        menu.exec(button.mapToGlobal(pos))

    def update_position(self):
        active = coordinated(self.drum)
        self.style_selector.setEnabled(active)
        self.phrase_length.setEnabled(active)
        self.auto_roles.setEnabled(active)
        self.meter_selector.setEnabled(active)
        self.keep_beat.setEnabled(active)
        self.new_variant.setEnabled(active)
        self.view_selector.setEnabled(active)
        for knob in self.creative_knobs:
            knob.setEnabled(active)
        roles = {voice_role(v) for v in self.drum.drum_voices if not v.muted}
        missing = [label for label, candidates in (("Kick", {"kick"}), ("Snare/Clap", {"snare", "clap"}),
                    ("Hat", {"closed_hat", "open_hat"})) if not roles & candidates]
        self.role_warning.setText("Missing beat roles: " + ", ".join(missing) + ". Check Role or use Auto roles.")
        self.role_warning.setVisible(active and bool(missing))
        if not active:
            self.plan_status.setText("Independent voice timing")
            return
        with self.host.transport._state_lock:
            beat = self.host.engine.clock.position_beats
            plan = self.host.engine.kit_coordinator.plan(self.drum, self.host.project.seed, beat)
            slot = max(0, int(math.floor(beat / STEP_BEATS + 1e-8))) % plan.length
            absolute_slot = max(0, int(math.floor(beat / STEP_BEATS + 1e-8)))
            steps = plan.steps_per_bar
            bar_start = slot // steps * steps
            cursor = slot % steps if self.host.transport.running else -1
            self.plan_ruler.set_cursor(cursor, steps)
            for voice_id, lane in self.plan_lanes.items():
                if self.view_selector.currentData() == "output":
                    history = self.host.transport.drum_output_history.get(voice_id, {})
                    absolute_bar = absolute_slot // steps * steps
                    lane.set_output([history.get(absolute_bar + i) for i in range(steps)], cursor, plan.groups)
                else:
                    lane.set_plan([plan.at(voice_id, bar_start + i) for i in range(steps)],
                                  cursor, plan.groups)
        fill = any(plan.at(v.id, slot).fill for v in self.drum.drum_voices)
        self.plan_status.setText(f"Bar {slot // steps + 1}/{plan.length // steps} · Step {slot % steps + 1:02d}/{steps}" + (" · FILL" if fill else ""))

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
        # The kit is pinned above the scrolling Inspector.  Preserve the
        # user's current voice-parameter scroll position after adding a row.
        self.host._queue_inspector_refresh()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(7, 7, 7, 7)
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
                self.view_selector.setFixedWidth(76)
                self.view_selector.setCurrentIndex(1 if getattr(self.host, "_kit_output_view", False) else 0)
                self.view_selector.setToolTip("Plan: arrangement before processing. Output: accepted generated events after processing, probability and mute, even without a MIDI port. Grey = not visited, dash = rest, bar height = velocity. Coordinated voices only; this is not MIDI input feedback.")
                self.view_selector.currentIndexChanged.connect(self._view_changed)
                title_row.addWidget(self.view_selector); title_row.addStretch(1)
                header_layout.addLayout(title_row)
                self.plan_ruler = KitStepRuler()
                self.plan_ruler.setVisible(coordinated(self.drum))
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
            if coordinated(self.drum, voice):
                plan_lane = KitPlanLane()
                self.plan_lanes[voice.id] = plan_lane
                lane.addWidget(plan_lane)
            elif voice.mode == "LIVE":
                stream = QLabel("LIVE STREAM  ·  Prob / Min / Max / Phase")
                stream.setObjectName("muted"); lane.addWidget(stream)
            else:
                values = self._voice_pattern(voice)
                for index, value in enumerate(values):
                    step = QPushButton(""); step.setCheckable(True); step.setChecked(value > 0); step.setFixedSize(14, 18)
                    step.setToolTip(f"{voice.name} step {index + 1}")
                    step.toggled.connect(lambda checked, v=voice, i=index: self._set_pattern(v, i, checked))
                    lane.addWidget(step)
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
            grid.addWidget(role, row, 2)
        grid.setColumnStretch(7, 1)
        outer.addLayout(grid)

        controls = QHBoxLayout(); controls.setSpacing(8)
        for key, default in KIT_DEFAULTS.items():
            label = key.removeprefix("kit_").title()
            controls.addWidget(QLabel(label))
            knob = ParamKnob(kit_value(self.drum, key), default=default)
            knob.bind_parameter(self.drum.id, key)
            knob.setObjectName(key)
            knob.setAccessibleName(f"Kit {label}")
            knob.setToolTip(KIT_TOOLTIPS[key])
            knob.setFixedWidth(54)
            knob.changed.connect(lambda value, k=key: self.host._set_drum_kit_parameter(self.drum, k, float(value)))
            controls.addWidget(knob)
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
            creative.addWidget(QLabel(label))
            knob = ParamKnob(creative_value(self.drum, key), default=default)
            knob.bind_parameter(self.drum.id, key)
            knob.setObjectName(key); knob.setAccessibleName(f"Kit {label}")
            knob.setToolTip(tooltip); knob.setFixedWidth(54)
            knob.changed.connect(lambda value, k=key: self.host._set_drum_kit_parameter(self.drum, k, float(value)))
            creative.addWidget(knob); self.creative_knobs.append(knob)
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
        outer.addLayout(creative)
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
        self.kind.addItems(MUTATORS)
        self.kind.setCurrentText(mutator.name)
        self.kind.setMinimumWidth(118)
        self.kind.setAccessibleName("Mutator type")
        self.target = QComboBox()
        self.target.addItems(["rhythm", "pitch", "velocity", "timing"])
        self.target.setCurrentText(mutator.target)
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

    def _changed(self, field, value):
        # A queued rebuild may leave an old row alive for one event-loop turn.
        if self.host.get_entity(self.block.id) is not self.block:
            return
        if not any(item is self.mutator for item in self.block.mutators):
            return
        setattr(self.mutator, field, value)
        self.host._mutator_editor_changed(self.block)

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
            for combo, selected in ((self.source, relation.source_block), (self.dest, relation.destination_block)):
                combo.clear()
                for block in self.editor.project.blocks:
                    swatch = QPixmap(12, 12)
                    swatch.fill(QColor(block_color(self.editor.project, block)))
                    combo.addItem(QIcon(swatch), block.name, block.id)
                    combo.setItemData(combo.count() - 1, f"{block.name} · {block.block_type} · ID {block.id}", Qt.ToolTipRole)
                if combo.findData(selected) < 0:
                    combo.addItem(f"Missing block {selected}", selected)
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
        theme = active_theme()
        self.setStyleSheet(f"QFrame#relationRow {{ background:{theme.card}; border:1px solid {theme.border}; border-radius:5px; }}"
                           "QWidget#relationControlArea { background:transparent; border:0; }")
        self.update_summary()
        self.dialogue.sync()
        self._sync_operation()

    def _sync_operation(self):
        dialogue = self.relation.algorithm == 'Dialogue'
        for name in ('Output', 'Input', 'Curve', 'Delay'):
            self.fields[name].setVisible(not dialogue)
        self.captions['Amount'].setText('Separation' if dialogue else 'Amount')
        self.captions['Probability'].setText('Cycle chance' if dialogue else 'Probability')
        self.amount.setToolTip('1: strict turns; 0: bypass; intermediate values soften the other instrument.' if dialogue else 'Relation amount')
        self.probability.setToolTip('Probability of using Dialogue for an entire cycle.' if dialogue else 'Relation event probability')
        self.dialogue.setVisible(dialogue)
        if dialogue:
            source = self.editor.host.get_block(self.relation.source_block)
            destination = self.editor.host.get_block(self.relation.destination_block)
            if source and destination:
                self.dialogue.timeline.colors = (block_color(self.editor.project, source), block_color(self.editor.project, destination))
            self.dialogue.update_runtime()

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
        with self.editor.host.transport._state_lock:
            relation = self.relation
            relation.source_block = int(self.source.currentData())
            relation.source_part = self.source_part.currentText()
            relation.algorithm = self.algorithm.currentText()
            relation.destination_block = int(self.dest.currentData())
            relation.destination_part = self.dest_part.currentText()
            relation.amount = float(self.amount.value())
            relation.curve = self.curve.currentText()
            relation.delay = int(self.delay.currentData() or 0)
            relation.probability = float(self.probability.value())
            relation.enabled = self.enabled.isChecked()
            self.editor.host.engine.apply_relations()
        self.editor.host._mark_dirty()
        self._sync_operation()
        self.update_summary()
        self.editor._refresh_builtin_status()
        self.editor._apply_filter(self.editor.filter_edit.text())


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
                         "An equivalent enabled route replaces the built-in transform.")
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
                QTimer.singleShot(0, reveal)
        QTimer.singleShot(0, apply)

    def add_relation(self, relation):
        with self.host.transport._state_lock:
            if not getattr(relation, "id", 0):
                relation.id = next_relation_id(self.project)
            self.project.relations.append(relation)
            self.host.engine.apply_relations()
        self.host._mark_dirty()
        self.filter_edit.clear()
        self._queue_rebuild(relation)

    def delete_relation(self, relation):
        index = next((i for i, item in enumerate(self.project.relations) if item is relation), -1)
        if index < 0:
            return
        with self.host.transport._state_lock:
            remove_relation(self.project, index)
            self.host.engine.apply_relations()
        self.host._mark_dirty()
        self._queue_rebuild()

    def duplicate_relation(self, relation):
        index = next((i for i, item in enumerate(self.project.relations) if item is relation), -1)
        if index < 0:
            return
        with self.host.transport._state_lock:
            duplicate = duplicate_relation(self.project, index)
            self.host.engine.apply_relations()
        self.host._mark_dirty()
        self.filter_edit.clear()
        self._queue_rebuild(duplicate)

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
        self.add_button.setEnabled(len(project.blocks) >= 2)
        self.dialogue_button.setEnabled(len(project.blocks) >= 2)
        self.add_button.setToolTip("Add a relation" if len(project.blocks) >= 2 else "Add at least two blocks first")
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
        knob.changed.connect(lambda x, k=key: self._process_knob_changed(k, x))
        v.addWidget(lab); v.addWidget(knob, 0, Qt.AlignCenter)
        self._add_cell(cell)

    def _process_knob_changed(self, key, value):
        self.process.parameters[key] = value
        self._changed()

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
        self._labeled_cell(key.replace('_', ' ').title(), cb, 104)

    def _check(self, key):
        cb = QCheckBox(); cb.setChecked(bool(self.process.parameters.get(key, False)))
        cb.toggled.connect(lambda v, k=key: self._set(k, bool(v)))
        self._labeled_cell(key.replace('_', ' ').title(), cb, 82)

    def _set(self, key, value):
        self.process.parameters[key] = value
        self._changed()

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
        self._labeled_cell('Destination', dest, 140)
        param = QComboBox(); self._fill_params(param, dest, p.get('destination_parameter', 'fill_density'))
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
        self.process.parameters['destination_block'] = dest.currentData()
        self._fill_params(param, dest, self.process.parameters.get('destination_parameter', 'fill_density'))
        self._route_param(param)

    def _route_param(self, param):
        if param.currentData() is not None:
            self.process.parameters['destination_parameter'] = param.currentData()
        self._changed()


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
    """Rolling MIDI piano roll.

    While the transport is running, show the most recent *pattern-length*
    window of actual outbound MIDI note-on events.  This makes the roll a
    history view rather than a single-current-note display.  When no outbound
    history exists yet, fall back to the generated SEQ pattern.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.block = None
        self.project = None
        self.history = []
        self.pattern_seconds = 2.0
        self.seq_interval = 0.125
        self.running = False
        self.live_min_events = 16
        self.frozen = False
        self.frozen_history = []
        self.frozen_at = 0.0
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(False)

    def set_data(self, block, history=None, pattern_seconds=None, seq_interval=None, running=False, project=None):
        if project is not None:
            self.project = project
        if self.frozen:
            self.block = block
            return
        self.block = block
        self.history = list(history or [])
        if pattern_seconds is not None:
            self.pattern_seconds = max(0.05, float(pattern_seconds))
        if seq_interval is not None:
            self.seq_interval = max(0.005, float(seq_interval))
        self.running = bool(running)
        if not self.frozen: self.update()

    def set_frozen(self, value, snapshot=None):
        """FREEZE keeps the currently visible history *and* its time base."""
        value = bool(value)
        if value and not self.frozen:
            if snapshot is not None:
                self.frozen_history, self.frozen_at = snapshot
            else:
                self.frozen_at = time.monotonic()
                self.frozen_history = self._history_events(self.frozen_at)
        self.frozen = value
        if not value:
            self.frozen_history = []
        self.update()

    def snapshot(self):
        return (list(self.frozen_history), self.frozen_at) if self.frozen else None

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
        if not self.history:
            return []
        now = time.monotonic() if now is None else now
        start = now - self.pattern_seconds
        all_events = [(float(t), int(note), float(vel)) for t, note, vel in self.history if float(t) <= now]
        if not all_events:
            return []
        # LIVE must remain useful even when its event interval is longer than the
        # nominal pattern window. Always keep at least 16 previous note-ons,
        # while preferring the normal pattern-length time window when it contains
        # enough events. This prevents the piano roll from collapsing to a single
        # current note for sparse LIVE generators.
        recent = [e for e in all_events if e[0] >= start]
        if len(recent) < self.live_min_events:
            recent = all_events[-self.live_min_events:]
        return recent

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
        history_events = list(self.frozen_history) if self.frozen else self._history_events()
        use_history = bool(history_events)

        if use_history:
            notes = [e[1] for e in history_events]
        else:
            generated = self._generated_events()
            notes = [e[1] for e in generated]

        if not notes:
            p.setPen(pal.mid().color())
            p.drawText(left, top + 25, "No generated MIDI notes yet")
            p.end()
            return

        lo = max(0, min(notes) - 2)
        hi = min(127, max(notes) + 2)
        span = max(1, hi - lo)

        # Pitch grid + compact piano keyboard.
        white_names = {0, 2, 4, 5, 7, 9, 11}
        key_left, key_right = 3, left - 5
        for note in range(hi, lo - 1, -1):
            y0 = top + h - (note - lo + 1) / span * h
            y1 = top + h - (note - lo) / span * h
            is_white = (note % 12) in white_names
            key_rect = QRectF(key_left, y0, key_right-key_left, max(1.0, y1-y0))
            p.setPen(QPen(QColor("#66707c"), 1))
            p.setBrush(QBrush(QColor("#e8ebef") if is_white else QColor("#242a31")))
            p.drawRect(key_rect)
            if note % 12 in (0,):
                p.setPen(QPen(QColor("#555f6b"), 1))
                p.drawLine(left, int(y1), left + w, int(y1))
                p.setPen(QPen(fg, 1))
                p.drawText(key_left + 2, int((y0+y1)/2 + 4), f"C{note // 12 - 1}")
            else:
                p.setPen(QPen(grid, 1))
                p.drawLine(left, int(y1), left + w, int(y1))
        # Black keys are inset to the right edge of the keyboard.
        black_names = {1, 3, 6, 8, 10}
        for note in range(hi, lo - 1, -1):
            if note % 12 not in black_names:
                continue
            y0 = top + h - (note - lo + 1) / span * h
            y1 = top + h - (note - lo) / span * h
            kh = max(2.0, (y1-y0)*0.68)
            kr = QRectF(key_left, y0, (key_right-key_left)*0.62, kh)
            p.setPen(QPen(QColor("#0d1116"), 1)); p.setBrush(QBrush(QColor("#171c22"))); p.drawRoundedRect(kr, 2, 2)

        # Time grid: one line per musical step and a stronger line per pattern.
        if use_history:
            now = self.frozen_at if self.frozen else time.monotonic()
            display_seconds = self.pattern_seconds
            if history_events:
                display_seconds = max(display_seconds, now - history_events[0][0])
            step_px = w * self.seq_interval / display_seconds
            steps = max(1, int(round(display_seconds / self.seq_interval)))
            for i in range(steps + 1):
                x = left + i * step_px
                if x > left + w + 1:
                    break
                pen = QPen(grid, 1 if i % 4 else 2)
                p.setPen(pen)
                p.drawLine(int(x), top, int(x), top + h)
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
            oldest_age = max(0.0, now - history_events[0][0]) if history_events else 0.0
            count_text = f"{len(history_events)} events · history {oldest_age:.1f}s" + (" · FROZEN" if self.frozen else "")
        else:
            generated = self._generated_events()
            # One column per step of the pattern, independent of where the last note is.
            count = max(1, len(self.block.outputs.get('rhythm', []) or []) if self.block else 1)
            stepw = w / count
            for i in range(count + 1):
                x = left + i * stepw
                p.setPen(QPen(grid, 1 if i % 4 else 2))
                p.drawLine(int(x), top, int(x), top + h)
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

        p.setPen(QPen(grid, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(left, top, w, h)
        p.setPen(QPen(fg, 1))
        title = self.block.name if self.block else "Block"
        p.drawText(left, 14, f"{title} · MIDI piano roll · {count_text}")
        p.end()


class MainWindow(QMainWindow):
    # Transport.tick() runs on the real-time worker.  These signals marshal
    # diagnostics and history updates back to the Qt GUI thread; touching a
    # QLabel, QTimer or monitor widget directly from the MIDI thread is not
    # safe and caused intermittent crashes during PLAY.
    _midi_message_signal = Signal(object, object, object, object)
    _generated_event_signal = Signal(object, object, object, object)
    _status_message_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self._midi_message_signal.connect(self._handle_midi_message)
        self._generated_event_signal.connect(self._handle_generated_event)
        self._status_message_signal.connect(self._show_status_message)
        self.setWindowTitle("Auricle — Algorithmic Music Generator")
        logo_path = asset_path("auricle_logo.png")
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))
        self.resize(1250, 760)
        self.setMinimumSize(820, 520)
        self.project = Project()
        self._dirty = False
        self._seed_project()
        ensure_global_macros(self.project)
        self.engine = MusicEngine(self.project)
        self.transport = Transport(self)
        self.selected_block_id = self.project.blocks[0].id if self.project.blocks else None
        self.selected_drum_voice_id = None
        self._midi_events = {}
        self._generated_live_events = {}
        self._piano_freeze = None  # (events, timestamp) while the piano roll is frozen
        self.current_path = None
        self._midi_pulse_at = {}
        self._midi_indicator_on = {}
        self._monitor_buffer = []
        self._midi_output_names = []
        self._midi_output_error = None
        self._global_macro_generation_queued = False
        self._build_ui()
        self._apply_style()
        self._inspector_columns = 2
        self._inspector_state = {}
        self._port_change_pending: set[int] = set()
        self._block_type_change_pending: dict[int, int] = {}
        self._inspector_generation = 0
        self._refresh_all()
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
        self.performance_timer = QTimer(self)
        self.performance_timer.setInterval(80)
        self.performance_timer.timeout.connect(lambda: self.performance.update_activity(self.project, bool(self.transport.running)))
        self.performance_timer.timeout.connect(self._update_piano_roll)
        # UI-only refreshes live on the 80 ms heartbeat, not on the 5 ms MIDI clock.
        self.performance_timer.timeout.connect(self._sync_transport_buttons)
        self.performance_timer.timeout.connect(self._update_motif_status)
        self.performance_timer.timeout.connect(self._update_kit_status)
        self.performance_timer.timeout.connect(self._flush_monitor)
        self.performance_timer.timeout.connect(self.performance.harmonic_panel.update_runtime)
        self.performance_timer.timeout.connect(self.relation_graph.update_runtime)
        self.performance_timer.start()
        self._sync_transport_buttons()

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
        # Keep the octave of the current root: KEY selects a pitch class, and
        # generators need a real MIDI root (0..11 used to squash low notes).
        octave = self.project.root_note // 12 if self.project.root_note >= 12 else 5
        self.project.root_note = octave * 12 + self.key.currentIndex()
        self.project.scale = self.scale.currentText()
        self._mark_dirty()
        # Keep generator-local values synchronized with the global musical context.
        for b in self.project.blocks:
            if b.algorithm in ("Markov", "Random Walk", "Interval Walker", "Scale Walker", "Weighted Scale", "Arpeggiator", "Fibonacci", "Recaman", "De Bruijn", "Cellular Automaton", "L-System", "Logistic Chaos"):
                b.parameters["scale_root"] = self.project.root_note
                b.parameters["scale_name"] = self.project.scale
        self.engine.generate()
        if not self.transport.running:
            self._queue_inspector_refresh("SOURCE")

    def set_message(self, message):
        # AutoConnection is direct on the GUI thread and queued when this is
        # called by TransportWorker, so statusBar() is always accessed by Qt's
        # owner thread.
        self._status_message_signal.emit(str(message))

    def _show_status_message(self, message):
        self.statusBar().showMessage(message, 3000)

    def _mark_dirty(self):
        """Mark the project changed and keep the title honest."""
        if getattr(self, "_installing_project", False):
            return
        self._dirty = True
        self._update_title()
        if hasattr(self, "history_controller"):
            self.history_controller.changed()

    def _set_global_macro(self, index, value, source=None):
        """Update the shared header/Perform macro and its Director target."""
        macros = ensure_global_macros(self.project)
        if not 0 <= int(index) < len(GLOBAL_MACRO_DEFS):
            return
        index = int(index)
        macro = macros[index]
        value = max(0.0, min(1.0, float(value)))
        macro["value"] = value
        control = str(macro.get("control", GLOBAL_MACRO_DEFS[index][1]))
        self.engine.director.set_global_macro(control, value)
        self._mark_dirty()
        if hasattr(self, "global_macro_bar") and source is not self.global_macro_bar:
            self.global_macro_bar.refresh_from_project()
        panel = getattr(getattr(self, "performance", None), "macro_panel", None)
        if panel is not None and source is not panel:
            panel.refresh_from_project()
        # Slider drags emit many valueChanged signals. Regenerate once after
        # the drag burst instead of blocking the GUI on every pixel movement.
        if not self._global_macro_generation_queued:
            self._global_macro_generation_queued = True
            QTimer.singleShot(35, self._flush_global_macro)

    def _flush_global_macro(self):
        self._global_macro_generation_queued = False
        # Apply parameter routes once for the complete drag burst.  Calling
        # this from every QSlider.valueChanged event made the UI regenerate
        # and rebuild relation outputs dozens of times per pixel.
        self.engine.generate()

    def _set_drum_kit_parameter(self, drum, key, value):
        # Kit edits share the transport lock, keep the pinned editor alive,
        # and coalesce expensive SEQ regeneration while dragging a knob.
        with self.transport._state_lock:
            self.engine.parameter_influence.manual(drum, key, max(0.0, min(1.0, float(value))))
        self._mark_dirty()
        if key == "kit_swing":
            return  # Read directly by the next timing calculation.
        pending = getattr(self, "_kit_regen_pending", None)
        if pending is None:
            self._kit_regen_pending = pending = set()
        if id(drum) not in pending:
            pending.add(id(drum))
            QTimer.singleShot(35, lambda d=drum: self._flush_drum_kit(d))

    def _flush_drum_kit(self, drum):
        self._kit_regen_pending.discard(id(drum))
        if not any(block is drum for block in self.project.blocks):
            return  # A different project may have been opened meanwhile.
        with self.transport._state_lock:
            self.engine.regenerate(drum)
        selected = self._selected_inspector_entity()
        if selected is not None and (selected is drum or getattr(selected, "parent_id", None) == drum.id):
            self._update_algorithm_preview(selected)

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
        top = QHBoxLayout(); top.setSpacing(5)
        logo = QLabel()
        self.brand_logo = logo
        logo.setObjectName("brandLogo")
        logo.setFixedSize(58, 54)
        logo.setAlignment(Qt.AlignCenter)
        logo.setToolTip("Auricle — Algorithmic Music Generator")
        logo_path = asset_path("auricle_logo.png")
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            logo.setPixmap(pixmap.scaled(56, 53, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo.setText("AURICLE")
        top.addWidget(logo)
        # Navigation and global musical controls live in the window header so
        # the four macros remain available on every tab.
        self.header_nav = QTabBar()
        self.header_nav.setExpanding(False)
        self.header_nav.setUsesScrollButtons(True)
        self.header_nav.setDrawBase(False)
        self.header_nav.setAccessibleName("Main navigation")
        self.global_macro_bar = GlobalMacroBar(self)
        self.play = QPushButton("PLAY"); self.play.setObjectName("transportPlay"); self.play.setCheckable(True)
        self.stop = QPushButton("STOP"); self.stop.setObjectName("transportStop")
        self.play.setToolTip("Start playback (Space)")
        self.stop.setToolTip("Stop playback and release all Auricle notes (Space)")
        self.play.clicked.connect(self._play_clicked)
        self.stop.clicked.connect(self._stop_clicked)
        top.addWidget(self.play); top.addWidget(self.stop)
        top.addSpacing(6)
        top.addWidget(QLabel("BPM"))
        self.tempo = ContrastSpinBox(); self.tempo.setRange(20, 300); self.tempo.setValue(self.project.tempo)
        self.tempo.valueChanged.connect(self._tempo_changed); top.addWidget(self.tempo)
        self.tempo.set_accessible_label("Tempo (BPM)")
        top.addWidget(QLabel("LENGTH"))
        self.length = ContrastSpinBox(); self.length.setRange(1, 128); self.length.setValue(self.project.length)
        self.length.valueChanged.connect(self._length_changed); top.addWidget(self.length)
        self.length.set_accessible_label("Pattern length (steps)")
        top.addSpacing(4)
        top.addWidget(QLabel("KEY"))
        self.key = QComboBox(); self.key.addItems(NOTE_NAMES); self.key.setCurrentIndex(self.project.root_note % 12)
        self.key.currentIndexChanged.connect(self._harmony_changed); top.addWidget(self.key)
        self.key.setAccessibleName("Key")
        top.addWidget(QLabel("SCALE"))
        self.scale = QComboBox(); self.scale.addItems(SCALES); self.scale.setCurrentText(self.project.scale)
        self.scale.currentTextChanged.connect(self._harmony_changed); top.addWidget(self.scale)
        self.scale.setAccessibleName("Scale")
        top.addStretch()
        self.theme_label = QLabel("THEME")
        top.addWidget(self.theme_label)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(theme_names())
        self.theme_combo.setFixedWidth(105)
        self.theme_combo.currentTextChanged.connect(self._theme_changed)
        top.addWidget(self.theme_combo)
        self.midi_status = QLabel("MIDI")
        top.addWidget(self.midi_status)
        outer.addLayout(top)
        macro_row = QHBoxLayout()
        macro_row.setSpacing(5)
        macro_row.addWidget(self.global_macro_bar, 1)
        outer.addLayout(macro_row)
        nav_row = QHBoxLayout()
        nav_row.setSpacing(5)
        nav_row.addWidget(self.header_nav, 0, Qt.AlignCenter)
        nav_row.addStretch(1)
        outer.addLayout(nav_row)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs, 1)

        # --- BLOCKS TAB ---------------------------------------------------
        blocks_tab = QWidget()
        blocks_layout = QHBoxLayout(blocks_tab)
        blocks_layout.setContentsMargins(0, 3, 0, 0)
        blocks_layout.setSpacing(4)

        splitter = QSplitter(Qt.Horizontal)
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
        # The Drum Kit is a persistent, pinned control surface.  It must stay
        # visible while the selected voice's full Inspector is scrolled below.
        # Keeping this host outside QScrollArea also prevents a voice click
        # from making the kit disappear when the Inspector is rebuilt.
        self.drum_kit_host = QWidget()
        self.drum_kit_host.setObjectName("drumKitHost")
        self.drum_kit_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.drum_kit_layout = QVBoxLayout(self.drum_kit_host)
        self.drum_kit_layout.setContentsMargins(0, 0, 0, 0)
        self.drum_kit_layout.setSpacing(0)
        self.drum_kit_host.hide()
        rv.addWidget(self.drum_kit_host, 0)
        self.inspector_scroll = QScrollArea()
        self.inspector_scroll.setWidgetResizable(False)
        self.inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inspector_scroll.viewport().installEventFilter(self)
        self.inspector_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Scrollbar appearance changes viewport width even without a window resize.
        self.inspector_scroll.verticalScrollBar().rangeChanged.connect(
            lambda _lo, _hi: QTimer.singleShot(0, self._reflow_inspector_responsive_forms)
        )
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
        splitter.setSizes([310, 940])
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)
        self.tabs.addTab(blocks_tab, monochrome_tab_icon("▦"), "BLOCKS")

        # PATCH overview is kept as an internal compatibility object but is no longer exposed as a tab.
        self.patch_overview = PatchOverview()
        self.patch_overview.block_selected.connect(self.select_block)

        # --- PERFORMANCE TAB --------------------------------------------
        self.performance = PerformancePanel(self)
        self.tabs.addTab(self.performance, monochrome_tab_icon("▶"), "PERFORM")

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
        help_layout = QVBoxLayout(help_tab)
        help_layout.setContentsMargins(8, 8, 8, 8)
        help_layout.setSpacing(6)
        help_header = QHBoxLayout()
        help_logo = QLabel()
        self.help_logo = help_logo
        help_logo.setObjectName("helpLogo")
        help_logo.setFixedSize(76, 62)
        help_logo.setAlignment(Qt.AlignCenter)
        logo_path = asset_path("auricle_logo.png")
        if logo_path.exists():
            help_logo.setPixmap(QPixmap(str(logo_path)).scaled(74, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
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
        self.help_language.currentIndexChanged.connect(self._update_help_language)
        help_header.addWidget(self.help_language)
        help_layout.addLayout(help_header)
        help_info = QLabel("Complete guide: workflow, algorithms, mutators, Process Layers, Perform and Relations.")
        help_info.setObjectName("muted")
        help_info.setWordWrap(True)
        help_layout.addWidget(help_info)
        self.help_view = QTextBrowser()
        self.help_view.setOpenExternalLinks(False)
        self.help_view.setHtml(help_html("en"))
        help_layout.addWidget(self.help_view)
        self.tabs.addTab(help_tab, monochrome_tab_icon("?"), "HELP")

        # QTabWidget keeps the content stack; its native tab row is mirrored
        # into the header so navigation sits beside the global controls.
        self.tabs.tabBar().hide()
        for i in range(self.tabs.count()):
            self.header_nav.addTab(self.tabs.tabIcon(i), self.tabs.tabText(i))
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

    def _apply_style(self, theme="Midnight"):
        """Apply a theme: application stylesheet *and* a matching QPalette.

        Applied application-wide so dialogs and menus follow the theme, and
        the palette makes knobs, piano roll and preview use theme colours.
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
            if app.styleSheet() != css:
                app.setStyleSheet(css)
            if self.styleSheet():
                self.setStyleSheet("")
        else:
            self.setStyleSheet(css)
        self._refresh_theme_assets()

    def _refresh_theme_assets(self):
        theme = getattr(self, "_active_theme", None) or active_theme()
        path = asset_path("auricle_logo.png")
        if path.exists():
            for label, size in ((getattr(self, "brand_logo", None), (56, 53)), (getattr(self, "help_logo", None), (74, 60))):
                if label is not None:
                    # Preserve the current artwork's own background and colours.
                    label.setPixmap(QPixmap(str(path)).scaled(
                        *size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if hasattr(self, "tabs"):
            for i, symbol in enumerate(("▦", "▶", "↔", "≋", "?")):
                if i < self.tabs.count():
                    icon = monochrome_tab_icon(symbol, color=theme.muted)
                    self.tabs.setTabIcon(i, icon)
                    if hasattr(self, "header_nav") and i < self.header_nav.count():
                        self.header_nav.setTabIcon(i, icon)

    def _update_help_language(self, index):
        language = self.help_language.itemData(index) if hasattr(self, "help_language") else "en"
        self.help_view.setHtml(help_html(language or "en"))

    def _monitor_toggle(self, checked):
        self.monitor_enabled.setText("MONITOR ON" if checked else "MONITOR OFF")

    def _flush_monitor(self):
        """Append buffered monitor lines once per UI heartbeat."""
        buffer = getattr(self, "_monitor_buffer", None)
        if not buffer or not hasattr(self, "midi_monitor"):
            return
        lines = buffer[-300:]
        buffer.clear()
        self.midi_monitor.addItems(lines)
        for _ in range(max(0, self.midi_monitor.count() - 300)):
            self.midi_monitor.takeItem(0)
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
        """Queue every outbound MIDI message for the GUI thread."""
        block_id = getattr(block, "id", None) if block is not None else None
        block_name = getattr(block, "name", "NOTE-OFF") if block is not None else "NOTE-OFF"
        self._midi_message_signal.emit(block_id, str(block_name), str(port_name or ""), message)

    def _handle_midi_message(self, block_id, block_name, port_name, message):
        """Record and display one outbound message on the Qt thread."""
        # Piano-roll history must not depend on the MIDI Monitor toggle.
        if block_id is not None:
            self._pulse_midi_indicator(int(block_id))
            if message.type == "note_on" and getattr(message, "velocity", 0) > 0:
                self._midi_events.setdefault(int(block_id), []).append((time.monotonic(), int(message.note), float(message.velocity) / 127.0))
                # Keep a generous history; the piano roll itself selects exactly one pattern window.
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
            text = f"{stamp}  {block_name:<10} {port[:24]:<24} {ch}  CC {message.control:3d}  value {message.value:3d}"
        else:
            text = f"{stamp}  {block_name:<10} {port[:24]:<24} {ch}  {message.type.upper()}"
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
        QTimer.singleShot(85, lambda bid=block_id: self._decay_midi_indicator(bid))

    def _decay_midi_indicator(self, block_id):
        # One timer per burst instead of one timer + restyle per MIDI note.
        age = time.monotonic() - self._midi_pulse_at.get(block_id, 0.0)
        if age < 0.08:
            QTimer.singleShot(max(10, int((0.085 - age) * 1000)), lambda bid=block_id: self._decay_midi_indicator(bid))
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
        if hasattr(self, 'piano_roll') and self.selected_block_id is not None:
            b = self.get_block(self.selected_block_id)
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

    def _refresh_blocks(self):
        current = self.selected_block_id
        self.block_list.blockSignals(True)
        self.block_list.clear()
        for b in self.project.blocks:
            item = QListWidgetItem()
            card = BlockCard(b)
            card.set_block_ref(b)
            card.set_type_color(block_color(self.project, b), b.block_type)
            card.selected.connect(self.select_block)
            card.delete_requested.connect(self.delete_block_by_id)
            card.mode_changed.connect(self._card_mode_changed)
            card.type_changed.connect(self._card_type_changed)
            card.color_changed.connect(self._card_color_changed)
            card.rename_requested.connect(self._card_rename_requested)
            card.mute_changed.connect(self._card_mute_changed)
            item.setData(Qt.UserRole, b.id)
            item.setSizeHint(QSize(10, card.sizeHint().height()))  # width follows the list
            self.block_list.addItem(item)
            self.block_list.setItemWidget(item, card)
            card.set_selected(b.id == current)
        if current is not None:
            for i in range(self.block_list.count()):
                if self.block_list.item(i).data(Qt.UserRole) == current:
                    self.block_list.setCurrentRow(i); break
        elif self.block_list.count():
            self.block_list.setCurrentRow(0)
        self.block_list.blockSignals(False)

    def _refresh_relations(self):
        if hasattr(self, "relation_graph"):
            self.relation_graph.rebuild(self.project)

    def _new_inspector_page(self):
        # Build the next Inspector completely off-screen.  Do not destroy the
        # currently visible page before construction succeeds: if a control
        # raises during a rebuild (for example after adding a mutator), the
        # user must keep the previous Inspector rather than getting a blank
        # panel.  The completed page is swapped into QScrollArea atomically
        # at the end of _refresh_inspector().
        page = QWidget()
        page.setObjectName("inspectorPage")
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QGridLayout(page)
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

        QTimer.singleShot(0, apply)

    def _clear_drum_kit_panel(self):
        """Remove the currently pinned Drum Kit editor from the host."""
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
        """Show the selected DRUM block's kit outside the scrolling Inspector."""
        host = getattr(self, "drum_kit_host", None)
        layout = getattr(self, "drum_kit_layout", None)
        if host is None or layout is None or drum is None or str(getattr(drum, "block_type", "")).upper() != "DRUM":
            self._clear_drum_kit_panel()
            return
        ensure_drum_voices(drum)
        self._clear_drum_kit_panel()
        kit_editor = DrumKitEditor(self, drum, self.selected_drum_voice_id)
        kit_editor.voice_selected.connect(self._select_drum_voice)
        layout.addWidget(kit_editor)
        host.show()
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
        return group

    def _set_motif_binding(self, block, binding):
        with self.transport._state_lock:
            if binding is None:
                block.parameters.pop("motif_id", None)
            else:
                block.parameters["motif_id"] = str(binding)
            block.parameters.pop("motif_hold", None)
            self.engine.motif_development.forget(block.id)
            self.engine.regenerate(block)
        self._mark_dirty()
        self._queue_inspector_refresh("SOURCE")

    def _set_motif_step(self, block, value):
        with self.transport._state_lock:
            block.parameters["motif_step_beats"] = max(.0625, min(16.0, value))
        self._mark_dirty()
        self._update_motif_status()

    def _set_motif_development(self, block, key, value):
        with self.transport._state_lock:
            block.parameters[key] = value
            if not self.transport.running:
                self.engine.regenerate(block)
                self.engine.motif_variant(block)
        self._mark_dirty()
        self._update_motif_status()

    def _hold_motif(self, block, checked):
        with self.transport._state_lock:
            changed = self.engine.hold_motif(block, checked)
            if changed and not self.transport.running:
                self.engine.regenerate(block)
                self.engine.motif_variant(block)
        if changed:
            self._mark_dirty()
        self._update_motif_status()

    def _recall_motif(self, block, token):
        if not token:
            return
        with self.transport._state_lock:
            changed = self.engine.hold_motif(block, token=token)
            if changed and not self.transport.running:
                self.engine.regenerate(block)
                self.engine.motif_variant(block)
        if changed:
            self._mark_dirty()
        self._update_motif_status()

    def _capture_motif(self, block, current_variant=False):
        with self.transport._state_lock:
            motif = self.engine.capture_motif(block, current_variant)
        if motif is not None:
            self._mark_dirty()
            self.set_message(f"Saved motif: {motif.name}")
            self._queue_inspector_refresh("SOURCE")

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
        with self.transport._state_lock:
            variant = self.engine.motif_development.current(block.id)
            if motif is not None and (variant is None or variant.motif.id != motif.id):
                variant = self.engine.motif_variant(block)
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
        self._refresh_drum_kit_panel(parent_block)
        if not b:
            layout.addWidget(QLabel("Select a block"), 0, 0, 1, 2)
            layout.setRowStretch(1, 1)
            # Install the empty page; returning without it left a stale page
            # for a block that no longer exists.
            self.inspector_page = page
            if hasattr(self, "inspector_scroll"):
                self.inspector_scroll.setWidget(page)
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

        def header_label(text):
            w = QLabel(text)
            w.setFixedWidth(62)
            w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return w

        name = QLineEdit(b.name); name.setFixedWidth(170); name.setFixedHeight(24)
        name.editingFinished.connect(lambda b=b,w=name:self._rename_entity(b,w.text()))
        block_type=QComboBox(); block_type.addItems(BLOCK_TYPES); block_type.setCurrentText(b.block_type if b.block_type in BLOCK_TYPES else BLOCK_TYPES[0]); block_type.setFixedWidth(118); block_type.setEnabled(not getattr(b, "is_drum_voice", False)); block_type.currentTextChanged.connect(lambda x,b=b:self._set_block_type(b,x))
        alg=QComboBox(); setup_algorithm_combo(alg,b.algorithm); alg.setFixedWidth(190); alg.currentTextChanged.connect(lambda x,b=b:self._set_algorithm(b,x))
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

        gf.addWidget(header_label("Name"),0,0); gf.addWidget(name,0,1)
        gf.addWidget(header_label("Type"),0,2); gf.addWidget(block_type,0,3)
        gf.addWidget(header_label("Generator"),1,0); gf.addWidget(alg,1,1)
        gf.addWidget(header_label("Mode"),1,2); gf.addWidget(mode,1,3)
        gf.addWidget(header_label("MIDI Ch"),2,0); gf.addWidget(ch,2,1)
        gf.addWidget(header_label("Base note"),2,2); gf.addWidget(note,2,3)
        gf.addWidget(header_label("MIDI Out"),2,4); gf.addWidget(port,2,5)
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
        gf.addWidget(role_label,3,0,1,6)
        layout.addWidget(general,0,0,1,2)

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
            def _available_width(self):
                scroll=getattr(self.host,"inspector_scroll",None)
                if scroll is not None and scroll.viewport().width()>0:
                    return max(self.CELL_WIDTH, scroll.viewport().width()-42)
                return max(self.CELL_WIDTH, self.parent.width()-10)
            def _column_count(self):
                available=self._available_width()
                return max(1,min(4,int((available+self.GAP)//(self.CELL_WIDTH+self.GAP))))
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
                cell=QWidget(); cell.setFixedWidth(self.CELL_WIDTH)
                v=QVBoxLayout(cell); v.setContentsMargins(0,0,0,0); v.setSpacing(0)
                lab=QLabel(str(label)); lab.setAlignment(Qt.AlignCenter); lab.setObjectName("knobLabel")
                v.addWidget(lab); v.addWidget(widget,0,Qt.AlignCenter)
                self.cells.append(cell); self.reflow(force=True)
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
            w=QCheckBox(); w.setChecked(bool(b.parameters.get(key,default))); w.toggled.connect(lambda x,b=b,k=key:self._set_param(b,k,x)); gform.addRow(label,w); return w
        def add_seed(): add_int("Seed","variation_seed",-9999,9999,0)
        def add_choice(label,key,items,default):
            w=QComboBox(); w.addItems(items); w.setCurrentText(str(b.parameters.get(key,default))); w.currentTextChanged.connect(lambda x,b=b,k=key:self._set_param(b,k,x)); gform.addRow(label,w); return w
        def add_text(label,key,default):
            w=QLineEdit(str(b.parameters.get(key,default))); w.editingFinished.connect(lambda b=b,k=key,w=w:self._set_param(b,k,w.text())); gform.addRow(label,w); return w

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
            mode=QComboBox(); mode.addItems(["OR","XOR","AND"]); mode.setCurrentText(str(b.parameters.get("poly_mode","OR"))); mode.currentTextChanged.connect(lambda x,b=b:self._set_param(b,"poly_mode",x)); gform.addRow("Combine",mode)
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
            mode=QComboBox(); mode.addItems(["Scale","Chromatic"]); mode.setCurrentText("Scale" if b.parameters.get("interval_quantize",1) else "Chromatic"); mode.currentTextChanged.connect(lambda x,b=b:self._set_param(b,"interval_quantize",x=="Scale")); gform.addRow("Quantize",mode)
            add_seed();
        elif b.algorithm == "Scale Walker":
            add_int("Step", "scale_step", 1, 4, 1); add_slider("Direction", "scale_direction", .5); add_int("Octaves", "scale_octaves", 1, 4, 2); add_slider("Leap", "scale_leap", .08); add_seed()
        elif b.algorithm == "Weighted Scale":
            add_text("Weights", "scale_weights", "1,1,1,1,1,1,1"); add_slider("Octave spread", "scale_octave_spread", .15); add_seed()
        elif b.algorithm == "Arpeggiator":
            add_text("Pattern", "arp_pattern", "0,2,4,6"); add_int("Octaves","arp_octaves",1,4,1); add_seed()
            add_choice("Direction", "arp_direction", ["Up","Down","Up/Down"], "Up"); add_choice("Octave mode", "arp_octave_mode", ["Cycle","Random"], "Cycle")
        elif b.algorithm == "Cellular Automaton":
            add_int("Rule", "ca_rule", 0, 255, 30); add_int("Generations", "ca_generations", 0, 16, 2); add_slider("Density", "ca_density", 1.0); add_seed()
            add_choice("Mode", "ca_mode", ["Rhythm","Pitch"], "Rhythm"); add_text("Seed cells", "ca_seed", "00100000");
        elif b.algorithm == "L-System":
            for label,key,default in [("Axiom","ls_axiom","A"),("Rule A","ls_rule_a","AB"),("Rule B","ls_rule_b","A")]:
                add_text(label, key, default)
            add_int("Iterations", "ls_iterations", 0, 8, 3); add_choice("Mode", "ls_mode", ["Pitch","Rhythm"], "Pitch"); add_text("Pitch map", "ls_mapping", "0,1,2,3,4,5,6")
        elif b.algorithm == "Logistic Chaos":
            add_float("R", "chaos_r", 0.0, 4.0, 3.9, .01); add_float("Initial X", "chaos_x", .001, .999, .5, .01); add_int("Octaves", "chaos_octaves", 1, 4, 2); add_int("Burn-in", "chaos_burn_in", 0, 1000, 0); add_slider("Smooth", "chaos_smooth", 0.0)
            mode=QComboBox(); mode.addItems(["Scale","Chromatic"]); mode.setCurrentText("Scale" if b.parameters.get("chaos_quantize",1) else "Chromatic"); mode.currentTextChanged.connect(lambda x,b=b:self._set_param(b,"chaos_quantize",x=="Scale")); gform.addRow("Quantize",mode)
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
            gform.addRow("Pattern", pattern)
            add_int("Rotation", "pattern_rotation", 0, max(0, self.project.length - 1), 0)
            add_float("Scale", "pattern_scale", 0.0, 4.0, 1.0, .05)
            add_slider("Probability", "pattern_probability", 1.0); add_bool("Reverse", "pattern_reverse", False)
            chance_editor = PatternChanceEditor(self, b)
            gform.addRow("Step chance", chance_editor)
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
            cell = QWidget(); cell.setFixedWidth(74)
            cv = QVBoxLayout(cell); cv.setContentsMargins(0,0,0,0); cv.setSpacing(0)
            lab = QLabel(parameter_label(key, label)); lab.setAlignment(Qt.AlignCenter); lab.setObjectName("knobLabel")
            cv.addWidget(lab); cv.addWidget(w,0,Qt.AlignCenter)
            grid.addWidget(cell,row,col,Qt.AlignLeft | Qt.AlignTop)
            return w

        def add_grid_choice(grid, label, key, options, col=0, row=0):
            """Add a compact role choice while keeping the value in Block.parameters."""
            combo = QComboBox()
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
            cell = QWidget(); cell.setFixedWidth(74)
            cv = QVBoxLayout(cell); cv.setContentsMargins(0,0,0,0); cv.setSpacing(0)
            lab = QLabel(parameter_label(key, label)); lab.setAlignment(Qt.AlignCenter); lab.setObjectName("knobLabel")
            cv.addWidget(lab); cv.addWidget(combo)
            grid.addWidget(cell, row, col, Qt.AlignLeft | Qt.AlignTop)
            return combo

        pattern = InspectorGroup("PATTERN", expanded=self._inspector_state.get((b.id,"PATTERN"),True))
        pattern.setObjectName("inspectorGroup_PATTERN"); pattern.set_summary("length · density · probability · rotation")
        pattern.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"PATTERN",checked))
        pf = QGridLayout(pattern); pf.setContentsMargins(7,6,7,6); pf.setHorizontalSpacing(4); pf.setVerticalSpacing(3); pf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        add_grid_knob(pf,"Length","structure_length",1,max(1,self.project.length),int(b.parameters.get("structure_length",self.project.length)),True,0)
        add_grid_knob(pf,"Density","fill_density",0.0,1.0,float(b.parameters.get("fill_density",b.parameters.get("event_density",1.0))),False,1)
        add_grid_knob(pf,"Probability","event_probability",0.0,1.0,float(b.parameters.get("event_probability",1.0)),False,2)
        add_grid_knob(pf,"Rotation","structure_rotation",0,max(0,self.project.length-1),int(b.parameters.get("structure_rotation",0)),True,3)
        structure_layout.addWidget(pattern)

        timing = InspectorGroup("TIMING", expanded=self._inspector_state.get((b.id,"TIMING"),True))
        timing.setObjectName("inspectorGroup_TIMING"); timing.set_summary("rate · swing · gate · humanize · offset")
        if self.engine.coordinated_drum(b) is not None:
            timing.set_summary("Kit grid · 1/16 · swing · gate · humanize · offset")
        timing.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"TIMING",checked))
        tf = QGridLayout(timing); tf.setContentsMargins(7,5,7,5); tf.setHorizontalSpacing(4); tf.setVerticalSpacing(3); tf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        add_grid_knob(tf,"Rate","timing_rate",0.25,4.0,float(b.parameters.get("timing_rate",1.0)),False,0)
        add_grid_knob(tf,"Swing","timing_swing",0.0,0.5,float(b.parameters.get("timing_swing",0.0)),False,1)
        add_grid_knob(tf,"Gate","gate",0.05,1.5,float(b.parameters.get("gate",0.78)),False,2)
        add_grid_knob(tf,"Humanize","timing_humanize",0.0,0.25,float(b.parameters.get("timing_humanize",0.0)),False,3)
        add_grid_knob(tf,"Offset","timing_offset",-0.5,0.5,float(b.parameters.get("timing_offset",0.0)),False,4)
        if b.mode == "LIVE":
            add_grid_knob(tf,"Min beats","live_min_beats",0.03,4.0,float(b.parameters.get("live_min_beats",.18)),False,0,1)
            add_grid_knob(tf,"Max beats","live_max_beats",0.03,8.0,float(b.parameters.get("live_max_beats",.85)),False,1,1)
            add_grid_knob(tf,"Live gate","live_gate",0.0,1.5,float(b.parameters.get("live_gate",.65)),False,2,1)
        structure_layout.addWidget(timing)
        layout.addWidget(structure,2,0,1,2)

        # MUSICAL — scale/pitch and musical representation.
        musical, musical_content, musical_layout = make_layer(
            "MUSICAL", "MUSICAL",
            f"{b.parameters.get('scale_name',self.project.scale)} · T {float(b.parameters.get('transpose',0)):+.0f} · O {float(b.parameters.get('octave',0)):+.0f}", False)

        scale_group = InspectorGroup("SCALE && PITCH", expanded=self._inspector_state.get((b.id,"SCALE & PITCH"),True))
        scale_group.setObjectName("inspectorGroup_SCALE"); scale_group.set_summary("root · scale · transpose · octave · range")
        scale_group.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"SCALE & PITCH",checked))
        sf = QGridLayout(scale_group); sf.setContentsMargins(7,6,7,6); sf.setHorizontalSpacing(4); sf.setVerticalSpacing(3); sf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        root=RangeKnob(0,127,int(b.parameters.get("scale_root",self.project.root_note)),True,default=self.project.root_note); root.changed.connect(lambda x,b=b:self._set_param(b,"scale_root",int(x)))
        root.bind_parameter(b.id, "scale_root")
        sc=QComboBox(); sc.addItems(SCALES); sc.setCurrentText(str(b.parameters.get("scale_name",self.project.scale))); sc.currentTextChanged.connect(lambda x,b=b:self._set_param(b,"scale_name",x))
        trans=RangeKnob(-48,48,float(b.parameters.get("transpose",0)),True,default=0); trans.changed.connect(lambda x,b=b:self._set_param(b,"transpose",float(x)))
        trans.bind_parameter(b.id, "transpose")
        octv=RangeKnob(-4,4,float(b.parameters.get("octave",0)),True,default=0); octv.changed.connect(lambda x,b=b:self._set_param(b,"octave",float(x)))
        octv.bind_parameter(b.id, "octave")
        prange=RangeKnob(1,48,int(b.parameters.get("pitch_range",24)),True,default=24); prange.changed.connect(lambda x,b=b:self._set_param(b,"pitch_range",int(x)))
        prange.bind_parameter(b.id, "pitch_range")
        for i,(label,w) in enumerate([("Root",root),("Scale",sc),("Transpose",trans),("Octave",octv),("Range",prange)]):
            cell=QWidget(); cell.setFixedWidth(74); cv=QVBoxLayout(cell); cv.setContentsMargins(0,0,0,0); cv.setSpacing(0); lab=QLabel(label); lab.setAlignment(Qt.AlignCenter); lab.setObjectName("knobLabel"); cv.addWidget(lab); cv.addWidget(w,0,Qt.AlignCenter); sf.addWidget(cell,0,i,Qt.AlignLeft | Qt.AlignTop)
        musical_layout.addWidget(scale_group)

        role = InspectorGroup("ROLE", expanded=self._inspector_state.get((b.id,"ROLE"),True))
        role.setObjectName("inspectorGroup_ROLE")
        role.set_summary(f"{b.block_type} · center {float(b.parameters.get('role_center', 0)):+.0f} · width {float(b.parameters.get('role_width', 24)):.0f} · density {float(b.parameters.get('role_density', 1.0)):.2f}")
        role.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"ROLE",checked))
        rof = QGridLayout(role); rof.setContentsMargins(7,6,7,6); rof.setHorizontalSpacing(4); rof.setVerticalSpacing(3); rof.setAlignment(Qt.AlignLeft | Qt.AlignTop)
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
            add_grid_knob(rof,label,key,lo,hi,int(val) if integer else val,integer,col)
        if b.block_type == "BASS":
            drum_sources = [("Auto", -1)] + [
                (source.name, source.id) for source in self.project.blocks
                if str(source.block_type).upper() == "DRUM"
            ]
            add_grid_choice(rof, "Drum source", "relation_drum_source", drum_sources, 0, 1)
            add_grid_choice(rof, "Groove mode", "groove_mode", [("Union", "Union"), ("Replace", "Replace")], 1, 1)
        elif b.block_type == "MELODY":
            chord_sources = [("Auto", -1)] + [
                (source.name, source.id) for source in self.project.blocks
                if str(source.block_type).upper() == "CHORD"
            ]
            add_grid_choice(rof, "Chord source", "relation_chord_source", chord_sources, 0, 1)
        if b.block_type in ROLE_PROFILES:  # DRUM has its own nested voice editor
            musical_layout.addWidget(role)

        if b.block_type in ("CHORD", "PAD", "BASS", "MELODY"):
            follow_plan = QCheckBox("Follow harmonic plan (Perform)")
            follow_plan.setChecked(bool(b.parameters.get("harmonic_follow", True)))
            follow_plan.toggled.connect(lambda value, b=b: self._set_param(b, "harmonic_follow", value))
            rof.addWidget(follow_plan, 2, 0, 1, 4)
            if b.block_type in ("BASS", "MELODY"):
                add_grid_knob(rof, "Plan anchor", "harmonic_strength", 0, 1, .75, False, 4, 2)

        harmony = InspectorGroup("HARMONY", expanded=self._inspector_state.get((b.id,"HARMONY"),False))
        harmony.setObjectName("inspectorGroup_HARMONY"); harmony.set_summary("voicing · spread · inversion · role")
        harmony.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"HARMONY",checked))
        hf = QGridLayout(harmony); hf.setContentsMargins(7,6,7,6); hf.setHorizontalSpacing(4); hf.setVerticalSpacing(3); hf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        add_grid_knob(hf,"Chord size","harmony_size",1,4,int(b.parameters.get("harmony_size",1)),True,0)
        add_grid_knob(hf,"Spread","harmony_spread",0,24,int(b.parameters.get("harmony_spread",7)),True,1)
        add_grid_knob(hf,"Inversion","harmony_inversion",-3,3,int(b.parameters.get("harmony_inversion",0)),True,2)
        if b.block_type in ("PAD", "CHORD"):  # voicing only affects harmonic roles
            musical_layout.addWidget(harmony)

        representation=InspectorGroup("REPRESENTATION",expanded=self._inspector_state.get((b.id,"MUSICAL REPRESENTATION"),True)); representation.setObjectName("inspectorGroup_REPRESENTATION"); representation.set_summary(f"Vel {float(b.parameters.get('velocity_base',.72)):.2f} · Accent {float(b.parameters.get('velocity_accent',.18)):.2f}"); representation.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"MUSICAL REPRESENTATION",checked))
        rf=QGridLayout(representation); rf.setContentsMargins(7,6,7,6); rf.setHorizontalSpacing(4); rf.setVerticalSpacing(3); rf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        for col,(label,key,default) in enumerate([("Velocity base","velocity_base",.72),("Velocity range","velocity_range",.25),("Velocity random","velocity_random",0.0),("Accent","velocity_accent",.18)]):
            w=ParamKnob(float(b.parameters.get(key,default)),default=default); w.bind_parameter(b.id, key); w.changed.connect(lambda x,b=b,k=key:self._set_param(b,k,x)); cell=QWidget(); cell.setFixedWidth(74); cv=QVBoxLayout(cell); cv.setContentsMargins(0,0,0,0); cv.setSpacing(0); lab=QLabel(parameter_label(key,label)); lab.setAlignment(Qt.AlignCenter); lab.setObjectName("knobLabel"); cv.addWidget(lab); cv.addWidget(w,0,Qt.AlignCenter); rf.addWidget(cell,0,col,Qt.AlignLeft | Qt.AlignTop)
        musical_layout.addWidget(representation); layout.addWidget(musical,3,0,1,2)

        # MOTION — only Mutation and Process for now.
        motion, motion_content, motion_layout = make_layer("MOTION","MOTION",f"{len(b.mutators)} mutations · {len(b.processes)} processes",False)
        if b.block_type == "DRUM":
            hint = QLabel("Voice chain → Kit chain. Pitch keeps the voice's fixed MIDI note. Disable Keep beat to allow rhythm shifts outside the role pattern.")
            hint.setWordWrap(True); hint.setObjectName("drumProcessingHint")
            motion_layout.addWidget(hint)
        mutation_amounts=InspectorGroup("MUTATION AMOUNT",expanded=self._inspector_state.get((b.id,"MUTATION AMOUNT"),True)); mutation_amounts.setObjectName("inspectorGroup_MUTATION_AMOUNT"); mutation_amounts.set_summary("pitch · rhythm · velocity · timing"); mutation_amounts.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"MUTATION AMOUNT",checked))
        maf=QGridLayout(mutation_amounts); maf.setContentsMargins(7,6,7,6); maf.setHorizontalSpacing(4); maf.setVerticalSpacing(3); maf.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        for col,(label,key) in enumerate([("Pitch","mutation_pitch"),("Rhythm","mutation_rhythm"),("Velocity","mutation_velocity"),("Timing","mutation_timing")]):
            add_grid_knob(maf,label,key,0.0,1.0,float(b.parameters.get(key,1.0)),False,col)
        motion_layout.addWidget(mutation_amounts)
        mut=InspectorGroup("MUTATION",expanded=self._inspector_state.get((b.id,"MUTATORS"),True)); mut.setObjectName("inspectorGroup_MUTATION"); mut.set_summary(" · ".join(f"{m.name} {m.amount:.2f}" for m in b.mutators) or "none"); mut.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"MUTATORS",checked))
        ml=QVBoxLayout(mut); ml.setContentsMargins(7,6,7,6); ml.setSpacing(3)
        for m in b.mutators:
            ml.addWidget(MutatorInlineControls(m, b, self))
        add=QPushButton("+ Add"); add.setObjectName("inspectorAddButton"); add.setAccessibleName("Add mutator"); add.setFixedHeight(26); add.clicked.connect(self.add_mutator); ml.addWidget(add,0,Qt.AlignLeft); motion_layout.addWidget(mut)
        proc_group=InspectorGroup("PROCESS",expanded=self._inspector_state.get((b.id,"PROCESS LAYER"),True)); proc_group.setObjectName("inspectorGroup_PROCESS"); proc_group.set_summary(f"{len(b.processes)} processes"); proc_group.accordion_toggled.connect(lambda checked,bid=b.id:self._remember_group(bid,"PROCESS LAYER",checked)); proc_layout=QVBoxLayout(proc_group); proc_layout.setContentsMargins(6,6,6,6); proc_layout.setSpacing(3)
        for idx,proc in enumerate(b.processes):
            card=QWidget(); cv=QVBoxLayout(card); cv.setContentsMargins(0,0,0,0); cv.setSpacing(3); head=QHBoxLayout(); head.setSpacing(4); typ=QComboBox(); typ.addItems(PROCESS_TYPES); typ.setCurrentText(proc.type); typ.setFixedWidth(118); typ.currentTextChanged.connect(lambda x,b=b,i=idx:self._set_process_type(b,i,x)); head.addWidget(typ); tgt=QComboBox(); tgt.addItems(PROCESS_TARGETS); tgt.setCurrentText(proc.target); tgt.setFixedWidth(72); tgt.currentTextChanged.connect(lambda x,b=b,i=idx:self._set_process_target(b,i,x)); head.addWidget(tgt); head.addWidget(QLabel(f"Process {idx+1}"),1); rem=QPushButton("×"); rem.setObjectName("cardDelete"); rem.setFixedSize(22,22); rem.clicked.connect(lambda _,b=b,i=idx:self.remove_process(b,i)); head.addWidget(rem); cv.addLayout(head); cv.addWidget(ProcessInlineControls(proc,self.project,b,self)); proc_layout.addWidget(card)
        addp=QPushButton("+ Add"); addp.setObjectName("inspectorAddButton"); addp.setAccessibleName("Add process"); addp.setFixedHeight(26); addp.clicked.connect(self.add_process); proc_layout.addWidget(addp,0,Qt.AlignLeft); motion_layout.addWidget(proc_group); layout.addWidget(motion,4,0,1,2)

        # MONITOR / diagnostics
        monitor, monitor_content, monitor_layout = make_layer("MONITOR","MONITOR","piano roll",False)
        piano_group=InspectorGroup("MIDI PIANO ROLL"); piano_group.setObjectName("inspectorGroup_PIANO"); piano_group.set_summary("generated note events"); piano_lay=QVBoxLayout(piano_group); piano_lay.setContentsMargins(7,7,7,7); piano_lay.setSpacing(3)
        freeze=QCheckBox("FREEZE"); freeze.setToolTip("Hold the currently visible note history"); freeze.setChecked(self._piano_freeze is not None); piano_lay.addWidget(freeze,0,Qt.AlignRight); self.piano_roll=PianoRollWidget(); self.piano_roll.engine = self.engine; piano_lay.addWidget(self.piano_roll); interval=60.0/max(1,self.project.tempo)/4.0; pattern_seconds=max(.05,interval*max(1,int(self.project.length))); self.piano_roll.set_data(b,self._midi_events.get(b.id,[]),pattern_seconds=pattern_seconds,seq_interval=interval,running=bool(self.transport.running),project=self.project);
        if self._piano_freeze is not None: self.piano_roll.set_frozen(True,self._piano_freeze)
        freeze.toggled.connect(self._set_piano_freeze); monitor_layout.addWidget(piano_group); layout.addWidget(monitor,5,0,1,2); layout.setRowStretch(6,1)

        # The new page has been built successfully. Swap it into the scroll
        # area only now, so a failed rebuild can never leave the Inspector
        # empty. The old page is detached afterwards and may be deleted by Qt.
        # QScrollArea::setWidget() owns the previous child and removes it
        # when a new widget is installed.  Do not touch the previous page
        # afterwards: the underlying C++ QWidget may already have been
        # destroyed, while Python still holds a Shiboken wrapper.  Calling
        # setParent()/deleteLater() on that stale wrapper raises
        # "Internal C++ object ... already deleted".
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

        # Final synchronous layout pass. The page itself is persistent, so this
        # is only a geometry refresh, not a widget-lifecycle workaround.
        layout.activate()
        content_hint = layout.sizeHint()
        if content_hint.isValid():
            page.setMinimumHeight(max(page.minimumHeight(), content_hint.height() + 4))
        page.updateGeometry()
        # Publish the real content height to QScrollArea. With widgetResizable
        # enabled, a minimum height larger than the viewport is what makes the
        # vertical scrollbar appear. Do not clamp the page to viewport height.
        required_h = max(content_hint.height() + 4, 1) if content_hint.isValid() else 1
        # Keep the Inspector at its natural vertical size.  The scroll area
        # must scroll the content rather than asking the page to fit the
        # viewport vertically.  widgetResizable=False is intentional here:
        # the page height is its content height, so a tall Inspector produces
        # a real vertical scrollbar instead of compressed/clipped rows.
        page.setMinimumHeight(required_h)
        page.adjustSize()
        # Let QScrollArea own the horizontal geometry while preserving the
        # page's natural vertical extent.  With widgetResizable=True this
        # gives Qt a real minimum content height, so the vertical scrollbar
        # appears whenever the Inspector is taller than the viewport instead
        # of shrinking nested rows until controls overlap.
        viewport_width = self.inspector_scroll.viewport().width() if hasattr(self, "inspector_scroll") else page.sizeHint().width()
        page.setMinimumWidth(max(1, viewport_width))
        natural_h = max(required_h, page.sizeHint().height(), page.minimumHeight())
        page.resize(max(1, viewport_width), max(1, natural_h))
        page.updateGeometry()
        self._reflow_inspector_responsive_forms()
        # Re-activate after responsive SOURCE may have changed row count.
        layout.invalidate(); layout.activate()
        responsive_h = max(layout.sizeHint().height() + 4, page.minimumHeight())
        if responsive_h > page.height():
            page.setMinimumHeight(responsive_h)
            page.resize(max(1, viewport_width), responsive_h)
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
            QTimer.singleShot(0, restore_inspector_scroll)
            QTimer.singleShot(50, restore_inspector_scroll)

    def _remember_group(self, block_id, title, checked):
        self._inspector_state[(block_id,title)] = bool(checked)

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
        return f"D {float(p.get('fill_density',1)):.2f} · P {float(p.get('event_probability',1)):.2f}"

    def _card_color_changed(self, block_id, color):
        def apply():
            b = self.get_block(block_id)
            if b is not None:
                b.color = str(color).lower()
                self._mark_dirty()
            self._block_colors_changed()
        QTimer.singleShot(0, apply)

    def _block_colors_changed(self):
        self._refresh_blocks()
        self._refresh_relations()
        if hasattr(self, "performance"): self.performance.refresh_blocks(self.project)
        if hasattr(self, "patch_overview"): self.patch_overview.rebuild(self.project)
        self._queue_inspector_refresh()

    def _theme_changed(self, name):
        self._apply_style(name)
        self._block_colors_changed()

    def _play_clicked(self, checked):
        if checked:
            self.transport.start()
        else:
            self.transport.stop()
        self._sync_transport_buttons()

    def _stop_clicked(self, checked):
        self.transport.stop()
        self._sync_transport_buttons()

    def _sync_transport_buttons(self):
        running = bool(getattr(self.transport, "running", False))
        self.play.blockSignals(True)
        self.play.setChecked(running)
        self.play.blockSignals(False)

    def _toggle_play(self):
        if self.transport.running:
            self.transport.stop()
        else:
            self.transport.start()
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
        # Voice settings are rendered below the pinned kit.  Do not jump the
        # scroll area to SOURCE when selecting a voice: the kit remains fixed
        # and the current Inspector position is preserved.
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

        QTimer.singleShot(0, apply)

    def select_block(self, block_id):
        if self.get_block(block_id) is None:
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
        QTimer.singleShot(0, apply)

    def _card_mute_changed(self, block_id, muted):
        # Rebuilding either card view destroys the emitting widget, so defer the
        # shared-state refresh until the current Qt click signal has unwound.
        project = self.project
        def apply():
            if self.project is not project: return
            b = self.get_block(block_id)
            if b is None:
                return
            b.muted = bool(muted)
            self._mark_dirty()
            self.transport.set_block_muted(block_id, b.muted)
            # Sync both card views in place; rebuilding them restarted
            # Perform gestures and dropped hover/selection state.
            self._sync_block_card(b)
            if hasattr(self, "performance"):
                self.performance.sync_block(b)
            self.set_message(f"{b.name}: {'muted' if b.muted else 'unmuted'}")
        QTimer.singleShot(0, apply)

    def _card_mode_changed(self, block_id, mode):
        project = self.project
        def apply():
            if self.project is not project: return
            b = self.get_block(block_id)
            if b:
                mode_value = "LIVE" if mode == "LIVE" else "SEQ"
                b.mode = mode_value
                self._mark_dirty()
                self.selected_block_id = block_id
                # Mode is generator state, not just presentation: clear stale LIVE
                # state and regenerate before both views are rebuilt.
                self.engine.reset_live()
                self.engine.generate()
                self._refresh_blocks()
                self._refresh_inspector()
                if hasattr(self, "performance"):
                    self.performance.refresh_blocks(self.project)
                self.set_message(f"{b.name}: {mode_value}")
        QTimer.singleShot(0, apply)

    def _rename_block(self, b, value):
        b.name = value.strip() or b.name
        self._mark_dirty()
        self._refresh_blocks(); self._refresh_relations()

    def _set_block_type(self, b, value):
        """Change a block type outside the ComboBox signal stack.

        Block type changes rebuild a substantial part of the Inspector and can
        also change generator/transport state.  Doing that synchronously from
        QComboBox.currentTextChanged can destroy the emitting widget while Qt
        is still dispatching its native event.  Under PLAY/LIVE this used to
        be able to terminate the process with a native SIGSEGV.

        Defer the mutation until the current Qt event has returned and coalesce
        rapid changes so only the latest requested type is applied.  Active MIDI
        notes owned by the block are released before its generator state is
        replaced, preventing notes from the old block type from surviving the
        transition.
        """
        if b is None or value not in BLOCK_TYPES:
            return
        pending = self._block_type_change_pending
        token = pending.get(b.id, 0) + 1
        pending[b.id] = token

        def apply_change(block_id=b.id, requested=value, change_token=token):
            if pending.get(block_id) != change_token:
                return
            pending.pop(block_id, None)
            block = self.get_block(block_id)
            if block is None or block.block_type == requested:
                return

            # Stop voices owned by the old type before mutating its generator
            # state. This is safe while Transport is running.
            # Notes are released, but the block keeps its clock position so
            # it stays on the shared grid with the other blocks.
            self.transport._release_block_notes(block.id)

            block.block_type = requested
            self._mark_dirty()
            apply_role_defaults(block)
            if requested == "DRUM":
                ensure_drum_voices(block)
            self.engine.reset_live()
            self.engine.generate()
            self._refresh_blocks()
            self.performance.refresh_blocks(self.project)
            if self.selected_block_id == block.id:
                self._refresh_inspector("SOURCE")

        QTimer.singleShot(0, apply_change)

    def _card_type_changed(self, block_id, value):
        b = self.get_block(block_id)
        if b is None:
            return
        self.selected_block_id = block_id
        self._set_block_type(b, value)

    def _set_algorithm(self, b, value):
        """Apply an algorithm change outside the QComboBox signal stack.

        Changing an algorithm rebuilds the generator controls and therefore
        replaces the Inspector page.  Doing that synchronously from
        currentTextChanged can destroy the emitting QComboBox while Qt is
        still dispatching its native event.  Under PLAY/LIVE this can become a
        native Qt/rtmidi use-after-free and terminate the process with SIGSEGV.
        Coalesce rapid changes and perform the mutation only after the current
        Qt event has returned.
        """
        if b is None or value not in GENERATORS:
            return
        pending = getattr(self, "_algorithm_change_pending", None)
        if pending is None:
            pending = {}
            self._algorithm_change_pending = pending
        token = pending.get(b.id, 0) + 1
        pending[b.id] = token

        def apply_change(block=b, requested=value, change_token=token):
            current = self._algorithm_change_pending.get(block.id)
            if current != change_token:
                return
            self._algorithm_change_pending.pop(block.id, None)
            live_block = self.get_entity(block.id)
            if live_block is None:
                return
            if live_block.algorithm == requested:
                return
            live_block.algorithm = requested
            self._mark_dirty()
            # Reset generator state when its algorithm changes, but leave the
            # transport running.  This is important for LIVE blocks during PLAY.
            self.engine.generate()
            parent = self.get_block(getattr(live_block, "parent_id", -1)) if getattr(live_block, "is_drum_voice", False) else live_block
            if parent is not None:
                self.engine.regenerate(parent)
            self._refresh_blocks()
            self.performance.refresh_blocks(self.project)  # technique catalog depends on the algorithm
            if self.selected_block_id == live_block.id or self.selected_drum_voice_id == live_block.id:
                self._refresh_inspector("SOURCE")

        QTimer.singleShot(0, apply_change)

    def _set_mode(self, b, value):
        if b is None:
            return
        pending = getattr(self, "_mode_change_pending", None)
        if pending is None:
            pending = {}
            self._mode_change_pending = pending
        token = pending.get(b.id, 0) + 1
        pending[b.id] = token

        def apply_change(bid=b.id, requested=value, change_token=token):
            if pending.get(bid) != change_token:
                return
            pending.pop(bid, None)
            block = self.get_entity(bid)
            if block is None:
                return
            block.mode = requested
            if block.block_type == "DRUM" and not getattr(block, "is_drum_voice", False):
                for voice in ensure_drum_voices(block):
                    voice.mode = requested
            self._mark_dirty()
            self.engine.reset_live()
            self.engine.generate()
            self._refresh_blocks()
            self.performance.refresh_blocks(self.project)
            if self.selected_block_id == bid or self.selected_drum_voice_id == bid:
                self._refresh_inspector("SOURCE")

        QTimer.singleShot(0, apply_change)

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
        # MIDI channel is a live transport property. The transport reads it
        # directly from Block for every note_on, so update the model and the
        # existing card synchronously; only Inspector rebuilding is deferred.
        if b is None:
            return
        b.midi_channel = max(1, min(16, int(value)))
        if getattr(b, "is_drum_voice", False):
            parent = self.get_block(getattr(b, "parent_id", -1))
            # A voice channel equal to its parent follows the parent; any
            # different value is an explicit per-voice override, regardless of
            # whether the edit came from the pinned kit or full Inspector.
            b.midi_channel_override = bool(parent is None or b.midi_channel != int(parent.midi_channel))
        elif str(getattr(b, "block_type", "")).upper() == "DRUM":
            for voice in ensure_drum_voices(b):
                if not bool(getattr(voice, "midi_channel_override", False)):
                    voice.midi_channel = b.midi_channel
        self._mark_dirty()
        self._sync_block_card(b)
        if self.selected_block_id == b.id:
            self._queue_inspector_refresh("SOURCE")
        elif self.selected_drum_voice_id == b.id:
            self._queue_inspector_refresh("SOURCE")

    def _set_note(self, b, value):
        if b is None:
            return
        b.midi_note = max(0, min(127, int(value)))
        self._mark_dirty()
        if self.selected_block_id == b.id:
            self._queue_inspector_refresh("SOURCE")
        elif self.selected_drum_voice_id == b.id:
            self._queue_inspector_refresh("SOURCE")
        else:
            self._refresh_blocks()

    def _set_port(self, b, value):
        """Change a block's MIDI output outside the ComboBox signal stack.

        Rebuilding the Inspector while Qt is delivering currentTextChanged can
        destroy the emitting QComboBox.  More importantly, closing an rtmidi
        handle from that nested callback has triggered native ALSA segfaults.
        Defer the actual port lifecycle operation until the event returns.
        """
        value = value or ""
        if b.midi_port == value and b.id not in self._port_change_pending:
            return
        old_port = b.midi_port
        b.midi_port = value
        if b.block_type == "DRUM" and not getattr(b, "is_drum_voice", False):
            for voice in ensure_drum_voices(b):
                if not voice.midi_port or voice.midi_port == old_port:
                    voice.midi_port = value
        self._mark_dirty()
        if b.id in self._port_change_pending:
            return
        self._port_change_pending.add(b.id)

        def apply_port_change(bid=b.id):
            self._port_change_pending.discard(bid)
            block = self.get_entity(bid)
            if block is None:
                return
            try:
                self.transport.refresh_ports()
            except Exception as exc:
                self.set_message(f"MIDI port error: {exc}")
                return
            if self.selected_block_id == bid or self.selected_drum_voice_id == bid:
                self._refresh_inspector()
            else:
                self._refresh_blocks()

        QTimer.singleShot(0, apply_port_change)

    def randomize_parameter(self, b, key, amount=0.35):
        if self.engine.randomize_parameter(b, key, amount):
            self._mark_dirty()
            self._queue_inspector_refresh()
            if hasattr(self, "performance"): self.performance.refresh_blocks(self.project)

    def _set_param(self, b, key, value):
        with self.transport._state_lock:
            self.engine.parameter_influence.manual(b, key, value)
        self._mark_dirty()
        pending = getattr(self, "_regen_pending", None)
        if pending is None:
            self._regen_pending = set()
            pending = self._regen_pending
        if b.id not in pending:
            pending.add(b.id)
            QTimer.singleShot(0, lambda bid=b.id: self._flush_param_regen(bid))
        self._update_algorithm_preview(b)

    def _update_algorithm_preview(self, block):
        """Resolve the preview from the current Qt-owned Inspector page.

        A kit container or empty Inspector has no preview. A pending callback
        may also outlive selection/page changes. Never retain a native widget
        wrapper across rebuilds or update a preview for a different entity.
        """
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
        self._mark_dirty()
        self.engine.regenerate(b)
        if self._selected_inspector_entity() is b:
            self._update_algorithm_preview(b)
            group = self.inspector_page.findChild(InspectorGroup, "inspectorGroup_MUTATION")
            if group is not None:
                group.set_summary(" · ".join(f"{m.name} {m.amount:.2f}" for m in b.mutators) or "none")

    def _process_editor_changed(self, process, block=None):
        # Process controls are live; avoid rebuilding the widget tree on every
        # drag. SEQ regenerates the owning block; LIVE uses the new process
        # state on the next event.
        b = block or self._selected_inspector_entity()
        if b is not None:
            self._mark_dirty()
            self.engine.regenerate(b)

    def _set_process_type(self, b, index, value):
        """Change process type outside the ComboBox signal callback.

        A process-type ComboBox lives inside the Inspector page that this
        method may rebuild. Rebuilding that page synchronously from
        currentTextChanged destroys the emitting QComboBox while Qt is still
        delivering its native event. This is especially dangerous during PLAY,
        where the GUI and MIDI transport are active, and can end in a native
        Qt/rtmidi SIGSEGV rather than a Python exception. Queue the mutation
        until the current Qt event has completely unwound.
        """
        if not (0 <= index < len(b.processes)):
            return
        value = str(value)
        key = (b.id, index)
        pending = getattr(self, "_process_type_pending", None)
        if pending is None:
            self._process_type_pending = {}
            pending = self._process_type_pending
        pending[key] = value
        if key in getattr(self, "_process_type_queued", set()):
            return
        if not hasattr(self, "_process_type_queued"):
            self._process_type_queued = set()
        self._process_type_queued.add(key)

        def apply_change(bid=b.id, proc_index=index):
            key2 = (bid, proc_index)
            self._process_type_queued.discard(key2)
            new_type = self._process_type_pending.pop(key2, None)
            block = self.get_entity(bid)
            if block is None or not (0 <= proc_index < len(block.processes)) or new_type is None:
                return
            proc = block.processes[proc_index]
            if proc.type == new_type:
                return
            proc.type = new_type
            self._mark_dirty()
            # Parameters of the previous process type have different meanings
            # (e.g. "mode") - start the new type from its own defaults.
            proc.parameters = {}
            if new_type == "Parameter Modulation":
                destination = next((x for x in self.project.blocks if x.id != block.id), block)
                catalog = MusicEngine.parameter_catalog(destination)
                key_name = "fill_density" if "fill_density" in catalog else next(iter(catalog), "")
                default, lo, hi = catalog.get(key_name, (0.5, 0.0, 1.0))
                proc.target = "pitch"
                proc.parameters = {
                    "destination_block": destination.id,
                    "destination_parameter": key_name,
                    "source_min": -1.0, "source_max": 1.0,
                    "min": lo, "max": hi, "smoothing": 0.0,
                }
            # Do not call the native MIDI layer here. Engine regeneration is
            # pure Python and the Inspector is rebuilt only after the signal
            # callback has returned to Qt.
            self.engine.generate()
            if self._selected_inspector_entity() is block:
                self._refresh_inspector("PROCESS")
            else:
                self._refresh_blocks()

        QTimer.singleShot(0, apply_change)

    def _set_process_target(self, b, index, value):
        if index < len(b.processes):
            b.processes[index].target = value
            self._mark_dirty()
            self.engine.generate()

    def add_process(self):
        b = self._selected_inspector_entity()
        if not b:
            return
        target = "velocity" if b.block_type == "DRUM" else "pitch"
        b.processes.append(Process("Counter", target, 0.25, {"length": 8, "step": 1.0, "offset": 0.0, "depth": 0.25}))
        self._mark_dirty()
        self.engine.generate(); self._queue_inspector_refresh("PROCESS")

    def remove_process(self, b, index):
        if 0 <= index < len(b.processes):
            b.processes.pop(index)
            self._mark_dirty()
            self.engine.generate(); self._queue_inspector_refresh("PROCESS")

    def remove_mutator(self, b, index):
        if 0 <= index < len(b.mutators):
            b.mutators.pop(index)
            self._mark_dirty()
            self.engine.generate(); self._queue_inspector_refresh("MUTATION")

    def _tempo_changed(self, value):
        self.transport.set_tempo(value)
        self._mark_dirty()

    def _length_changed(self, value):
        self.project.length = int(value)
        self._mark_dirty()
        self.engine.generate(); self._queue_inspector_refresh("SOURCE")

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
        d = AddBlockDialog(self)
        if d.exec() != QDialog.Accepted:
            return
        new_id = max([b.id for b in self.project.blocks] + [0]) + 1
        existing_colors = [getattr(block, "color", "") for block in self.project.blocks]
        b = Block(new_id, d.name.text().strip() or self._unique_block_name(d.kind.currentText()), d.kind.currentText(),
                  d.algorithm.currentText(), d.mode.mode(), 1, "", 60, {},
                  color=random_block_color(existing_colors))
        # New blocks get their role defaults (gate, register, voicing...) like
        # loaded and seeded blocks, and the first free MIDI channel.
        apply_role_defaults(b)
        if b.block_type == "DRUM":
            ensure_drum_voices(b)
        used_channels = {int(x.midi_channel) for x in self.project.blocks}
        b.midi_channel = next((ch for ch in range(1, 17) if ch not in used_channels), 1)
        self.project.blocks.append(b)
        self._mark_dirty()
        self.selected_block_id = new_id
        self.engine.generate(); self._refresh_all()

    def delete_block_by_id(self, block_id):
        if self.selected_block_id != block_id:
            self.selected_block_id = block_id
        self.delete_block()

    def delete_block(self):
        b = self.get_block(self.selected_block_id)
        if not b:
            return
        if len(self.project.blocks) <= 1:
            self.set_message("At least one block must remain")
            return
        # Stop/release this block before removing it from the model.  Otherwise
        # long gates can leave its active MIDI notes alive until their old due
        # time, even though the block no longer exists.
        self.transport._release_block_notes(b.id)
        self.project.relations = [r for r in self.project.relations
                                  if r.source_block != b.id and r.destination_block != b.id]
        self.project.blocks = [x for x in self.project.blocks if x.id != b.id]
        self._mark_dirty()
        self.transport.refresh_ports()
        # Drop macro routes and parameter-modulation routes aimed at the deleted block.
        for macro in self.project.macros:
            macro["routes"] = [r for r in macro.get("routes", []) or [] if r.get("block_id") != b.id]
        for other in self.project.blocks:
            for proc in other.processes:
                if proc.type == "Parameter Modulation" and proc.parameters.get("destination_block") == b.id:
                    proc.parameters["destination_block"] = -1
        if hasattr(self, "performance"): self.performance.rebuild_macro_panel()
        self.selected_block_id = self.project.blocks[0].id if self.project.blocks else None
        self.engine.generate(); self._refresh_all()

    def add_mutator(self):
        b = self._selected_inspector_entity()
        if not b:
            return
        target = "rhythm" if b.block_type == "DRUM" else "pitch"
        b.mutators.append(Mutator("Rotate", .5, target))
        self._mark_dirty()
        self.engine.generate(); self._queue_inspector_refresh("MUTATION")

    def add_relation(self, operation='Copy'):
        if len(self.project.blocks) < 2:
            self.set_message("At least two blocks are required")
            return
        source = self.get_block(self.selected_block_id) or self.project.blocks[0]
        destination = next(block for block in self.project.blocks if block.id != source.id)
        part = "rhythm" if source.block_type == "DRUM" else "pitch"
        operation = 'Dialogue' if operation == 'Dialogue' else 'Copy'
        self.relation_graph.add_relation(Relation(source.id, part, destination.id, part, operation, 1. if operation == 'Dialogue' else .5))

    def refresh_midi(self):
        ports, err = get_midi_output_names()
        self._midi_output_names = list(ports)
        self._midi_output_error = err
        self.midi_status.setText(f"MIDI: {len(ports)} outputs" if not err else "MIDI: ERROR")
        if err:
            self.set_message(err)
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
            with self.transport._state_lock:
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

    def _install_project(self, project, path, message, selection=None):
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
        ensure_global_macros(self.project)
        self.engine = MusicEngine(self.project)
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
        if hasattr(self, "history_controller"):
            self.history_controller.reset()
        self._update_title()
        self.set_message(message)

    def _reflow_inspector_responsive_forms(self):
        page = getattr(self, "inspector_page", None)
        if page is None:
            return
        for widget in page.findChildren(QWidget):
            form = getattr(widget, "_auricle_responsive_form", None)
            if form is not None:
                form.reflow()

    def eventFilter(self, obj, event):
        scroll = getattr(self, "inspector_scroll", None)
        if scroll is not None and event.type() == QEvent.Resize and obj is scroll.viewport():
            # The viewport has its final width only after the window layout
            # ran; resizeEvent saw the old width, so the Inspector did not
            # fill the window after maximizing.
            QTimer.singleShot(0, self._fit_inspector_page)
        return super().eventFilter(obj, event)

    def _fit_inspector_page(self):
        scroll = getattr(self, "inspector_scroll", None)
        page = scroll.widget() if scroll is not None else None
        if page is None:
            return
        width = max(1, scroll.viewport().width())
        page.setMinimumWidth(width)
        self._reflow_inspector_responsive_forms()
        if page.layout() is not None:
            page.layout().activate()
        page.resize(width, max(1, page.minimumHeight(), page.sizeHint().height()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "theme_label"):
            compact = self.width() < 1040
            self.theme_label.setVisible(not compact)
            self.midi_status.setVisible(not compact)
            self.theme_combo.setFixedWidth(88 if compact else 105)
            self.scale.setMaximumWidth(120 if compact else 16777215)
            for button in (self.play, self.stop):
                button.setStyleSheet("min-width:60px;" if compact else "")
        # Collapse the Inspector to one column when the available width becomes
        # too small. This avoids squeezing QFormLayout fields until they overlap.
        available = self.inspector_scroll.viewport().width() if hasattr(self, "inspector_scroll") else self.width()
        if hasattr(self, "inspector_page") and hasattr(self, "inspector_scroll"):
            # Width follows the viewport, but height deliberately remains the
            # natural content height so the QScrollArea supplies vertical
            # scrolling instead of compressing the Inspector.
            natural_h = max(self.inspector_page.minimumHeight(), self.inspector_page.sizeHint().height())
            self.inspector_page.resize(max(1, available), max(1, natural_h))
            self._reflow_inspector_responsive_forms()
        columns = 2 if available >= 620 else 1
        if hasattr(self, "_inspector_columns") and columns != self._inspector_columns:
            self._inspector_columns = columns
            if hasattr(self, "selected_block_id"):
                self._queue_inspector_refresh()

    def closeEvent(self, event):
        if not self._confirm_discard_changes():
            event.ignore()
            return
        if hasattr(self, "timer"):
            self.timer.stop()
        if hasattr(self, "performance_timer"):
            self.performance_timer.stop()
        self.history_controller.close()
        self.transport.stop()
        if hasattr(self, "transport_worker"):
            self.transport_worker.stop()
        self.transport.close_ports(); event.accept()


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
    app = QApplication(sys.argv)
    app.setApplicationName("Auricle")
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")  # consistent base style under the theme stylesheet
    logo_path = asset_path("auricle_logo.png")
    if logo_path.exists():
        app.setWindowIcon(QIcon(str(logo_path)))
    win = MainWindow()
    win.show()
    if smoke_test:
        if win.brand_logo.pixmap().isNull() or win.help_logo.pixmap().isNull():
            win.close()
            raise RuntimeError("The bundled logo could not be rendered")
        QTimer.singleShot(500, win.close)
    else:
        QTimer.singleShot(350, lambda: win.history_controller.offer_recovery(startup=True))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
