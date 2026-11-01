"""Auricle UI themes.

Theme data and the Qt stylesheet live here so the main window does not own
visual design decisions.  Block identity colours remain independent from the
application theme.
"""
from __future__ import annotations

from dataclasses import dataclass
from auricle_resources import asset_path
from ui_metrics import CONTROL_HEIGHT, DENSE_HEIGHT, TRANSPORT_HEIGHT, TRANSPORT_WIDTH


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    panel: str
    card: str
    input: str
    border: str
    text: str
    muted: str
    accent: str
    accent2: str
    tab: str
    tabsel: str
    slider: str
    spinbtn: str
    success: str
    danger: str
    warning: str
    selection: str


# Ten curated palettes: five softened dark themes and five light themes.
# Dark palettes deliberately use lifted charcoal/navy/plum/green/brown surfaces
# rather than near-black backgrounds.  Light palettes are built as layered
# surfaces: a tinted window (bg) < a lighter content well (panel) < near-white
# cards and buttons (card) < white fields (input).  Borders sit around 1.7-1.9:1
# against cards so outlines, slider grooves and card edges stay visible, and
# control edges (checkbox, scrollbar handle) reach 3:1.  Muted text keeps
# >= 4.5:1 on every surface (>= 5:1 on window, cards and tabs).  Accents are
# dark enough (>= 5:1 on white) to carry white label text, and the accent never
# shares a hue with "success", so selected and active/OK states stay distinct.
THEMES = {
    # Dark
    "Graphite": Theme("Graphite", "#20262E", "#252D37", "#2D3743", "#252F3A", "#465463", "#EEF2F6", "#B2BECA", "#76A9FA", "#A4C5FF", "#293440", "#35485D", "#83B4FF", "#64788D", "#65C995", "#F0787D", "#E9BD65", "#3B5878"),
    "Blue Hour": Theme("Blue Hour", "#202B3B", "#263448", "#2D3D53", "#26364A", "#4A607A", "#EDF4FC", "#B2C2D5", "#70B7D8", "#9AD8EF", "#2B3C52", "#38536D", "#7BC5E2", "#5D7893", "#65C99A", "#F07B83", "#EBC16D", "#3A5C78"),
    "Soft Plum": Theme("Soft Plum", "#2C2633", "#332C3C", "#3C3447", "#342D3E", "#5B5067", "#F4EEF8", "#C2B5CC", "#C19AE8", "#D7B8F5", "#382F43", "#4B3A5D", "#C9A5ED", "#79658B", "#71C9A0", "#F07C88", "#E8C16C", "#604779"),
    "Pine": Theme("Pine", "#222D2A", "#293732", "#31423A", "#2A3A33", "#4C6256", "#EDF5EF", "#B5C8BB", "#83C7A0", "#B0E0C0", "#2E4037", "#3B5947", "#8BD1A8", "#65816E", "#6BCB91", "#EF7C7C", "#E7C46C", "#41634D"),
    "Espresso": Theme("Espresso", "#302923", "#3A3129", "#45392F", "#3B3129", "#695647", "#F6F0E9", "#CBB9A8", "#D9A477", "#F0C49B", "#40352C", "#594535", "#DFAE82", "#8B7059", "#7CC69A", "#EF8079", "#EAC477", "#705238"),

    # Light
    "Porcelain": Theme("Porcelain", "#E9EDF1", "#F4F6F9", "#FBFCFD", "#FEFEFF", "#B1BECD", "#19222F", "#465872", "#2662BC", "#4584E3", "#D7DEE7", "#E6EDF6", "#3273D5", "#869AB2", "#196D46", "#B32A3C", "#7E590E", "#CAD9EE"),
    "Cloud": Theme("Cloud", "#E9F0F2", "#F3F8F9", "#FBFDFD", "#FEFFFF", "#A6C2C8", "#16262C", "#3E5E6C", "#116E80", "#0F91AC", "#D6E4E8", "#E4EFF0", "#148196", "#739EA9", "#1A6F41", "#B52B3D", "#805A0E", "#C5DCE0"),
    "Sage": Theme("Sage", "#EAF0EA", "#F4F8F4", "#FBFDFB", "#FEFFFE", "#ACC2AB", "#1A261C", "#46614A", "#14725F", "#13967B", "#D9E5D9", "#E4EFEB", "#17846F", "#7EA17D", "#1C6F27", "#B22F34", "#7D5B0E", "#C6DDD7"),
    "Lavender": Theme("Lavender", "#EDE9F2", "#F6F3F9", "#FCFBFD", "#FEFEFF", "#C3B7D3", "#271C32", "#604C78", "#7949C2", "#9A6FD9", "#DED6E8", "#EFE9F7", "#895FCA", "#A290BB", "#196B4B", "#B02949", "#80560E", "#DED2EF"),
    "Sand": Theme("Sand", "#F3EFE7", "#FBF7F2", "#FEFCFA", "#FFFFFE", "#CCBA9C", "#2B221A", "#6A5745", "#9A5119", "#D16817", "#EAE2D3", "#F6E8D2", "#B45F1D", "#AF9364", "#1D6E46", "#B7283B", "#7B5D08", "#ECD5B5"),
}


def theme_names() -> tuple[str, ...]:
    """Return the ten supported themes in presentation order (dark, then light)."""
    return tuple(THEMES)


def theme_palette(name: str = "Graphite") -> Theme:
    """Return a theme palette; unknown/retired names fall back to Graphite."""
    return THEMES.get(name, THEMES["Graphite"])


def _rgb(color: str) -> tuple[int, int, int]:
    value = str(color).lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """Blend colour ``a`` toward ``b`` (t=0 -> a, t=1 -> b)."""
    ra, rb = _rgb(a), _rgb(b)
    t = max(0.0, min(1.0, float(t)))
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(ra, rb))


def luminance(color: str) -> float:
    """WCAG 2.x relative luminance."""
    def channel(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)))
    return (lb + 0.05) / (la + 0.05)


def on_color(background: str, light: str = "#ffffff", dark: str = "#111111") -> str:
    """Readable text colour for a filled background (higher WCAG contrast)."""
    return light if contrast_ratio(light, background) >= contrast_ratio(dark, background) else dark


def is_light_theme(theme: Theme) -> bool:
    return luminance(theme.bg) > 0.45


def theme_stylesheet(name: str = "Graphite") -> str:
    """Qt stylesheet for a theme.

    Every colour is derived from the theme tokens (no hard-coded dark fills),
    so light themes stay readable.  Text on filled accent/success/danger
    surfaces uses ``on_color`` for contrast.
    """
    c = theme_palette(name)
    on_accent = on_color(c.accent)
    on_success = on_color(c.success)
    on_danger = on_color(c.danger)
    hover = mix(c.card, c.accent, .12)
    checked = mix(c.card, c.accent, .28)
    play_bg = mix(c.card, c.success, .20)
    play_hover = mix(c.card, c.success, .34)
    stop_bg = mix(c.card, c.danger, .20)
    stop_hover = mix(c.card, c.danger, .34)
    danger_bg = mix(c.card, c.danger, .14)
    disabled_fg = mix(c.muted, c.bg, .40)
    handle = mix(c.border, c.muted, .45)
    indicator_off = mix(c.border, c.muted, .30)
    field_hover = mix(c.border, c.accent, .50)
    done_stage = mix(c.card, c.accent, .16)
    dropdown_arrow = asset_path("dropdown_arrow.png").as_posix()
    return f"""
    QWidget {{ background:{c.bg}; color:{c.text}; font-size:11px; }}
    QMainWindow, QDialog {{ background:{c.bg}; }}
    QLabel, QCheckBox, QRadioButton {{ background:transparent; }}
    QLabel#brand {{ font-size:17px; font-weight:700; letter-spacing:2px; padding-right:10px; }}
    QLabel#sectionTitle {{ font-size:15px; font-weight:700; letter-spacing:1px; }}
    QLabel#pageTitle {{ font-size:14px; font-weight:800; letter-spacing:1px; }}
    QLabel#brandLogo, QLabel#helpLogo {{ background:transparent; border:0; }}
    QLabel#blockName {{ font-weight:700; font-size:14px; }}
    QLabel#blockIndex {{ background:{c.tabsel}; color:{c.text}; border:1px solid {c.border}; border-radius:15px; font-size:13px; font-weight:700; }}
    QLabel#blockMeta {{ color:{c.muted}; font-size:11px; }}
    QLabel#muted, QLabel#ports {{ color:{c.muted}; }} QLabel#ports {{ font-size:10px; }}
    QLabel#knobLabel {{ color:{c.muted}; font-size:10px; }}
    QLabel#knobValue {{ color:{c.text}; font-size:10px; }}
    QPushButton#cardMenu {{ background:transparent; border:0; color:{c.muted}; font-size:20px; font-weight:700; padding:0; min-height:0; }}
    QPushButton#cardMenu:hover {{ color:{c.text}; background:{c.tab}; border-radius:5px; }}
    QPushButton {{ background:{c.card}; color:{c.text}; border:1px solid {c.border}; border-radius:4px; padding:2px 8px; min-height:{CONTROL_HEIGHT - 6}px; font-weight:600; }}
    QPushButton:hover {{ border-color:{c.accent}; background:{hover}; }}
    QPushButton:pressed {{ background:{c.input}; }}
    QPushButton:checked {{ background:{checked}; border-color:{c.accent}; }}
    QPushButton:disabled {{ color:{disabled_fg}; background:{c.panel}; border-color:{c.border}; }}
    QPushButton#collapseHeader {{ text-align:left; background:{c.tab}; border:1px solid {c.border}; padding:3px 7px; min-height:21px; font-weight:700; }}
    QPushButton#inspectorAddButton {{ min-width:100px; min-height:{CONTROL_HEIGHT - 6}px; padding:2px 8px; }}
    QPushButton#transportPlay, QPushButton#transportStop {{ min-width:{TRANSPORT_WIDTH - 2}px; max-width:{TRANSPORT_WIDTH}px; min-height:{TRANSPORT_HEIGHT - 2}px; max-height:{TRANSPORT_HEIGHT - 2}px; padding:0; font-size:14px; font-weight:800; border-radius:6px; color:{c.text}; }}
    QPushButton#transportPlay {{ background:{play_bg}; border-color:{c.success}; }}
    QPushButton#transportPlay:hover {{ background:{play_hover}; }}
    QPushButton#transportPlay:checked {{ background:{c.success}; color:{on_success}; }}
    QPushButton#transportStop {{ background:{stop_bg}; border-color:{c.danger}; }}
    QPushButton#transportStop:hover {{ background:{stop_hover}; }}
    QPushButton#transportStop:pressed {{ background:{c.danger}; color:{on_danger}; }}
    QPushButton#deleteButton, QPushButton#cardDelete {{ background:{danger_bg}; border-color:{c.danger}; color:{c.text}; }}
    QPushButton#deleteButton:hover, QPushButton#cardDelete:hover {{ background:{c.danger}; color:{on_danger}; }}
    QPushButton#cardDelete {{ padding:0; min-height:{DENSE_HEIGHT - 2}px; min-width:{DENSE_HEIGHT - 2}px; }}
    QPushButton#blockMute {{ padding:0; min-width:0; min-height:0; }}
    QPushButton#modeButton {{ min-width:0; min-height:0; padding:0; border-radius:3px; font-size:10px; }}
    QPushButton#modeButton:checked {{ background:{c.accent}; color:{on_accent}; border-color:{c.accent}; }}
    QPushButton#performMute:checked {{ background:{c.danger}; color:{on_danger}; border-color:{c.danger}; }}
    QPushButton#valueStepperButton {{ padding:0; min-width:0; min-height:{DENSE_HEIGHT - 2}px; border-radius:0; font-size:13px; font-weight:700; }}
    QLineEdit#valueStepperEditor {{ border-radius:0; padding:0 2px; min-height:{DENSE_HEIGHT - 2}px; }}
    QWidget#transportField QLineEdit {{ font-size:13px; }}
    QComboBox#transportField {{ min-height:{TRANSPORT_HEIGHT - 4}px; font-size:12px; }}
    QWidget#transportField QPushButton#valueStepperButton {{ font-size:15px; min-width:24px; max-width:24px; }}
    QLabel#transportLabel {{ color:{c.muted}; font-weight:600; }}
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background:{c.input}; color:{c.text}; border:1px solid {c.border}; border-radius:4px; padding:1px 4px; min-height:{DENSE_HEIGHT - 4}px; selection-background-color:{c.selection}; selection-color:{c.text}; }}
    QComboBox {{ border-radius:6px; }}
    QComboBox::drop-down {{ subcontrol-origin:padding; subcontrol-position:top right; width:18px; border:0; border-top-right-radius:6px; border-bottom-right-radius:6px; }}
    QComboBox::down-arrow {{ image:url("{dropdown_arrow}"); width:10px; height:6px; }}
    QComboBox:hover, QLineEdit:hover {{ border-color:{field_hover}; }}
    QComboBox:focus, QLineEdit:focus {{ border-color:{c.accent}; }}
    QComboBox:disabled, QLineEdit:disabled {{ color:{disabled_fg}; }}
    QComboBox QAbstractItemView {{ background:{c.card}; color:{c.text}; border:1px solid {c.border}; border-radius:6px; padding:3px; selection-background-color:{c.selection}; selection-color:{c.text}; outline:0; }}
    QSpinBox#minimalSpinBox, QDoubleSpinBox#minimalSpinBox {{ background:{c.input}; color:{c.text}; border:0; border-radius:0; padding:1px 2px; min-height:22px; }}
    QLineEdit#minimalSpinEdit {{ background:transparent; color:{c.text}; border:0; border-radius:0; padding:0; min-height:0; }}
    QCheckBox {{ spacing:6px; }}
    QCheckBox::indicator {{ width:13px; height:13px; border:1px solid {handle}; border-radius:3px; background:{c.input}; }}
    QCheckBox::indicator:hover {{ border-color:{c.accent}; }}
    QCheckBox::indicator:checked {{ background:{c.accent}; border-color:{c.accent}; }}
    QCheckBox::indicator:disabled {{ background:{c.panel}; }}
    QListWidget {{ background:{c.panel}; border:1px solid {c.border}; border-radius:6px; }}
    QListWidget::item {{ padding:3px; border:0; }} QListWidget::item:selected {{ background:transparent; }}
    QFrame#blockCard {{ background:{c.card}; border:1px solid {c.border}; border-radius:7px; }}
    QFrame#blockCard[muted="true"] {{ background:{c.panel}; border-color:{c.muted}; }}
    QFrame#blockCard:hover {{ border-color:{c.accent}; }} QFrame#blockCard[selected="true"] {{ border:2px solid {c.accent}; background:{c.tabsel}; }}
    QFrame#inspectorBlockHeader {{ background:{c.card}; border:1px solid {c.border}; border-radius:6px; }}
    QLabel#midiSendIndicator {{ background:{indicator_off}; border-radius:3px; }}
    QLabel#midiSendIndicator[active="true"] {{ background:{c.success}; }}
    QLabel#performMidi {{ background:{indicator_off}; border-radius:4px; }}
    QLabel#performMidi[active="true"] {{ background:{c.success}; }}
    QLabel#formStage, QLabel#phraseStage {{ background:{c.card}; color:{c.muted}; border:1px solid {c.border}; padding:7px 10px; font-weight:600; }}
    QLabel#phraseStage {{ border-radius:4px; }}
    QLabel#phraseStage[done="true"] {{ background:{done_stage}; color:{c.text}; }}
    QLabel#formStage[active="true"], QLabel#phraseStage[active="true"] {{ background:{c.accent}; color:{on_accent}; border-color:{c.accent}; }}
    QLabel#phraseArrow {{ color:{c.muted}; font-size:16px; font-weight:700; }}
    QLabel#directorMeter {{ background:{c.card}; color:{c.text}; border:1px solid {c.border}; border-radius:4px; padding:3px 6px; }}
    QLabel#blockSummary, QLabel#miniMeter {{ color:{c.muted}; font-size:9px; }} QLabel#blockAlgorithm {{ color:{c.text}; font-size:10px; font-weight:600; }}
    QLabel#miniMeter {{ padding:1px 3px; border:1px solid {c.border}; border-radius:3px; }} QCheckBox#muteSwitch {{ background:transparent; }}
    QProgressBar {{ background:{c.input}; border:1px solid {c.border}; border-radius:3px; text-align:center; min-height:6px; }} QProgressBar::chunk {{ background:{c.accent}; border-radius:2px; }}
    QGraphicsView {{ background:{c.panel}; border:1px solid {c.border}; border-radius:5px; }}
    QGroupBox {{ border:1px solid {c.border}; border-radius:5px; margin-top:7px; padding-top:6px; }} QGroupBox::title {{ subcontrol-origin:margin; left:8px; padding:0 4px; color:{c.muted}; background:{c.bg}; }}
    QSlider::groove:horizontal {{ height:4px; background:{c.border}; border-radius:2px; }}
    QSlider::sub-page:horizontal {{ background:{c.accent}; border-radius:2px; }}
    QSlider::handle:horizontal {{ width:12px; margin:-5px 0; border-radius:6px; background:{c.slider}; }}
    QSlider::handle:horizontal:hover {{ background:{c.accent2}; }}
    QScrollArea {{ border:0; background:{c.panel}; }} QListWidget#midiMonitor {{ font-family:monospace; font-size:11px; background:{c.panel}; }}
    QTextBrowser {{ background:{c.panel}; border:1px solid {c.border}; border-radius:5px; padding:6px; }}
    QScrollBar:vertical {{ background:transparent; width:10px; margin:0; border:0; }}
    QScrollBar:horizontal {{ background:transparent; height:10px; margin:0; border:0; }}
    QScrollBar::handle:vertical {{ background:{handle}; min-height:28px; border-radius:4px; margin:2px; }}
    QScrollBar::handle:horizontal {{ background:{handle}; min-width:28px; border-radius:4px; margin:2px; }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background:{c.muted}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; border:0; background:transparent; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
    QMenuBar {{ background:{c.bg}; }} QMenuBar::item {{ background:transparent; padding:3px 9px; }} QMenuBar::item:selected {{ background:{c.tab}; border-radius:4px; }}
    QMenu {{ background:{c.card}; border:1px solid {c.border}; padding:4px; }} QMenu::item {{ padding:4px 24px 4px 14px; border-radius:3px; }}
    QMenu::item:selected {{ background:{c.selection}; }} QMenu::item:disabled {{ color:{disabled_fg}; }} QMenu::separator {{ height:1px; background:{c.border}; margin:4px 6px; }}
    QTabWidget::pane {{ border:1px solid {c.border}; border-radius:6px; background:{c.panel}; }}
    QTabBar::tab {{ background:{c.tab}; border:1px solid {c.border}; border-bottom:0; border-top-left-radius:6px; border-top-right-radius:6px; padding:5px 12px; margin-right:3px; color:{c.muted}; }}
    QTabBar#headerNavigation::tab {{ border-bottom:1px solid {c.border}; border-radius:6px; padding:5px 12px; margin-right:4px; }}
    QTabBar::tab:selected {{ background:{c.tabsel}; color:{c.text}; border-color:{c.accent}; }}
    QTabBar#headerNavigation::tab:selected {{ border-color:{c.accent}; }}
    QTabBar::tab:hover:!selected {{ color:{c.text}; }}
    QLabel#versionLabel {{ color:{c.muted}; font-size:9px; padding-left:2px; }} QLabel#midiIndicator {{ background:{c.muted}; border-radius:2px; }} QLabel#performDot {{ background:{c.muted}; border-radius:4px; }} QSplitter::handle {{ background:{c.border}; }} QStatusBar {{ color:{c.muted}; }}
    QToolTip {{ background:{c.card}; color:{c.text}; border:1px solid {c.border}; padding:4px; }}
    QTableWidget {{ background:{c.panel}; alternate-background-color:{c.card}; gridline-color:{c.border}; color:{c.text}; }}
    QHeaderView::section {{ background:{c.tab}; color:{c.text}; border:1px solid {c.border}; padding:4px; }}
    QTableWidget::item:selected {{ background:{c.selection}; color:{c.text}; }}
    """
