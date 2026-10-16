"""Auricle UI themes.

Theme data and the Qt stylesheet live here so the main window does not own
visual design decisions.  Block identity colours remain independent from the
application theme.
"""
from __future__ import annotations

from dataclasses import dataclass


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


# The first five are based on the visual language in the supplied references:
# Midnight, Solar, Forest, Synthwave and Slate.  The remaining five extend
# that family without changing the layout or component language.
THEMES = {
    "Midnight": Theme("Midnight", "#0b121b", "#0e1722", "#131e2b", "#101a26", "#2a3a4d", "#e7eef7", "#8fa0b5", "#4f8cff", "#7ab8ff", "#132237", "#1b3150", "#4f8cff", "#40556d", "#38c979", "#e05261", "#f2bd52", "#1d477d"),
    "Solar": Theme("Solar", "#f3f1ec", "#ffffff", "#faf8f3", "#ffffff", "#c9c4b8", "#272622", "#706c64", "#d97a19", "#f0a43a", "#ece8df", "#ffffff", "#d97a19", "#aaa49a", "#258a58", "#bd3f48", "#c58b18", "#f3dfc2"),
    "Forest": Theme("Forest", "#09140f", "#0d1c15", "#12271d", "#0e2118", "#29483a", "#e5f1e9", "#8fa99a", "#49c878", "#8be39f", "#10271b", "#183a27", "#49c878", "#426b56", "#4fd18a", "#e35d67", "#d8b44a", "#20583a"),
    "Synthwave": Theme("Synthwave", "#100b1d", "#150e27", "#21133a", "#190f30", "#4a2c68", "#f5ecff", "#ae9ac4", "#b45cff", "#ff4fb3", "#1e1234", "#35195b", "#c05dff", "#654583", "#43e3b0", "#ff5578", "#ffc857", "#54247d"),
    "Slate": Theme("Slate", "#10161d", "#151d25", "#1b252f", "#18212a", "#354553", "#e3e9ee", "#8e9ba7", "#54a7c8", "#8fc9dc", "#19242e", "#243442", "#54a7c8", "#526473", "#53c58b", "#df5a67", "#d8af4b", "#28506a"),
    "Ocean": Theme("Ocean", "#07131c", "#0a1b27", "#0f2533", "#0c202d", "#245064", "#e4f7ff", "#88a9b8", "#25b8df", "#4ee3ff", "#0c2534", "#123b50", "#27c1e7", "#3d6879", "#42d39b", "#e95c67", "#e6bd50", "#16516b"),
    "Ember": Theme("Ember", "#170f0c", "#201511", "#2a1b15", "#241713", "#5b392c", "#f8eee8", "#b79e91", "#ff8a3d", "#ffb347", "#291a13", "#472519", "#ff8a3d", "#7a4b3a", "#55cf87", "#ef5b5b", "#f0bd4d", "#68371f"),
    "Aurora": Theme("Aurora", "#091017", "#0d171d", "#122027", "#0e1a20", "#2e4d4c", "#e9f6f2", "#91aba7", "#58d5bb", "#8b7cff", "#102329", "#19383b", "#5bd9c2", "#456a68", "#55d790", "#e55d73", "#d6bd55", "#225e59"),
    "Mono": Theme("Mono", "#101010", "#151515", "#1c1c1c", "#181818", "#3b3b3b", "#f1f1f1", "#a4a4a4", "#d6d6d6", "#ffffff", "#202020", "#2b2b2b", "#d6d6d6", "#555555", "#d0d0d0", "#e06a6a", "#d0b36a", "#3a3a3a"),
    "Copper": Theme("Copper", "#130f0d", "#1a1411", "#241b16", "#1e1713", "#4e3b30", "#f2e8df", "#aa988a", "#d48a55", "#e0b27a", "#211713", "#35231b", "#d9955f", "#675044", "#61c08a", "#df5b65", "#d7b34f", "#5d3c28"),
    "Nordic": Theme("Nordic", "#20262e", "#252d36", "#2e3742", "#26303a", "#45515d", "#eceff4", "#a8b1bf", "#88c0d0", "#81a1c1", "#303b48", "#3b4a5b", "#88c0d0", "#596777", "#a3be8c", "#bf616a", "#ebcb8b", "#36566d"),
    "Deep Space": Theme("Deep Space", "#070a12", "#0c1020", "#11182b", "#0d1424", "#293452", "#edf2ff", "#8d99b5", "#6c8cff", "#c084fc", "#141e38", "#26345d", "#6c8cff", "#435074", "#54d18a", "#e06b75", "#f2c14e", "#2b4a9a"),
    "Cream Studio": Theme("Cream Studio", "#ebe6dc", "#f6f1e8", "#fffaf1", "#faf5ec", "#c8bda9", "#29241f", "#756d63", "#b56b2a", "#d99a4b", "#eee4d3", "#fffaf1", "#b56b2a", "#a18f78", "#4d9b67", "#b84c57", "#b8862e", "#e1c49b"),
}


def theme_names() -> tuple[str, ...]:
    return tuple(THEMES)


def theme_palette(name: str = "Midnight") -> Theme:
    return THEMES.get(name, THEMES["Midnight"])


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


def theme_stylesheet(name: str = "Midnight") -> str:
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
    QPushButton {{ background:{c.card}; color:{c.text}; border:1px solid {c.border}; border-radius:4px; padding:2px 8px; min-height:19px; font-weight:600; }}
    QPushButton:hover {{ border-color:{c.accent}; background:{hover}; }}
    QPushButton:pressed {{ background:{c.input}; }}
    QPushButton:checked {{ background:{checked}; border-color:{c.accent}; }}
    QPushButton:disabled {{ color:{disabled_fg}; background:{c.panel}; border-color:{c.border}; }}
    QPushButton#collapseHeader {{ text-align:left; background:{c.tab}; border:1px solid {c.border}; padding:3px 7px; min-height:21px; font-weight:700; }}
    QPushButton#inspectorAddButton {{ min-width:124px; min-height:26px; padding:3px 9px; }}
    QPushButton#transportPlay, QPushButton#transportStop {{ min-width:88px; min-height:34px; font-size:14px; font-weight:800; border-radius:6px; color:{c.text}; }}
    QPushButton#transportPlay {{ background:{play_bg}; border-color:{c.success}; }}
    QPushButton#transportPlay:hover {{ background:{play_hover}; }}
    QPushButton#transportPlay:checked {{ background:{c.success}; color:{on_success}; }}
    QPushButton#transportStop {{ background:{stop_bg}; border-color:{c.danger}; }}
    QPushButton#transportStop:hover {{ background:{stop_hover}; }}
    QPushButton#transportStop:pressed {{ background:{c.danger}; color:{on_danger}; }}
    QPushButton#deleteButton, QPushButton#cardDelete {{ background:{danger_bg}; border-color:{c.danger}; color:{c.text}; }}
    QPushButton#deleteButton:hover, QPushButton#cardDelete:hover {{ background:{c.danger}; color:{on_danger}; }}
    QPushButton#cardDelete {{ padding:0; min-height:0; }}
    QPushButton#modeButton {{ min-width:48px; min-height:18px; padding:2px 6px; border-radius:0; }}
    QPushButton#modeButton:checked {{ background:{c.accent}; color:{on_accent}; border-color:{c.accent}; }}
    QPushButton#performMute:checked {{ background:{c.danger}; color:{on_danger}; border-color:{c.danger}; }}
    QPushButton#valueStepperButton {{ padding:0; min-width:0; border-radius:0; font-size:13px; font-weight:700; }}
    QLineEdit#valueStepperEditor {{ border-radius:0; padding:0 2px; }}
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background:{c.input}; color:{c.text}; border:1px solid {c.border}; border-radius:4px; padding:1px 4px; min-height:18px; selection-background-color:{c.selection}; selection-color:{c.text}; }}
    QComboBox:hover, QLineEdit:hover {{ border-color:{field_hover}; }}
    QComboBox:focus, QLineEdit:focus {{ border-color:{c.accent}; }}
    QComboBox:disabled, QLineEdit:disabled {{ color:{disabled_fg}; }}
    QComboBox QAbstractItemView {{ background:{c.card}; color:{c.text}; border:1px solid {c.border}; selection-background-color:{c.selection}; selection-color:{c.text}; outline:0; }}
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
    QTabWidget::pane {{ border:1px solid {c.border}; border-radius:5px; background:{c.panel}; }} QTabBar::tab {{ background:{c.tab}; border:1px solid {c.border}; border-bottom:0; padding:5px 12px; margin-right:2px; color:{c.muted}; }} QTabBar::tab:selected {{ background:{c.tabsel}; color:{c.text}; border-color:{c.accent}; }} QTabBar::tab:hover:!selected {{ color:{c.text}; }}
    QLabel#versionLabel {{ color:{c.muted}; font-size:9px; padding-left:2px; }} QLabel#midiIndicator {{ background:{c.muted}; border-radius:2px; }} QLabel#performDot {{ background:{c.muted}; border-radius:4px; }} QSplitter::handle {{ background:{c.border}; }} QStatusBar {{ color:{c.muted}; }}
    QToolTip {{ background:{c.card}; color:{c.text}; border:1px solid {c.border}; padding:4px; }}
    QTableWidget {{ background:{c.panel}; alternate-background-color:{c.card}; gridline-color:{c.border}; color:{c.text}; }}
    QHeaderView::section {{ background:{c.tab}; color:{c.text}; border:1px solid {c.border}; padding:4px; }}
    QTableWidget::item:selected {{ background:{c.selection}; color:{c.text}; }}
    """
