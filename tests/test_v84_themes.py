from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui_themes import THEMES, theme_names, theme_palette, theme_stylesheet


def test_theme_catalog_contains_reference_and_new_themes():
    expected = {"Midnight", "Solar", "Forest", "Synthwave", "Slate", "Ocean", "Ember", "Aurora", "Mono", "Copper"}
    assert expected.issubset(set(theme_names()))
    assert len(THEMES) >= 10


def test_every_theme_has_complete_palette_and_stylesheet():
    fields = ("bg", "panel", "card", "input", "border", "text", "muted", "accent", "accent2", "tab", "tabsel", "slider", "spinbtn", "success", "danger", "warning", "selection")
    for name in theme_names():
        theme = theme_palette(name)
        assert all(getattr(theme, field).startswith("#") for field in fields)
        css = theme_stylesheet(name)
        assert "QWidget" in css
        assert theme.accent in css
        assert theme.border in css


def test_unknown_theme_falls_back_to_midnight():
    assert theme_palette("does-not-exist") == theme_palette("Midnight")
