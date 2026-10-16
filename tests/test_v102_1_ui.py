"""v102.1 UI regression tests: theme contrast, palette, live Perform widgets."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from ui_themes import THEMES, contrast_ratio, mix, on_color, theme_stylesheet  # noqa: E402

GUI = (ROOT / "auricle_gui.py").read_text(encoding="utf-8")
THEME_SRC = (ROOT / "ui_themes.py").read_text(encoding="utf-8")


def test_no_hardcoded_dark_fills_in_theme():
    for hard in ("#244c35", "#4a262b", "#40252a", "color:#fff"):
        assert hard not in THEME_SRC


@pytest.mark.parametrize("name", list(THEMES))
def test_theme_text_contrast_meets_wcag_aa(name):
    c = THEMES[name]
    assert contrast_ratio(on_color(c.accent), c.accent) >= 4.5
    assert contrast_ratio(on_color(c.danger), c.danger) >= 4.5
    assert contrast_ratio(c.text, mix(c.card, c.success, .20)) >= 4.5  # PLAY
    assert contrast_ratio(c.text, mix(c.card, c.danger, .20)) >= 4.5   # STOP
    css = theme_stylesheet(name)
    assert "QCheckBox::indicator" in css and "QScrollBar::handle" in css


def test_group_titles_escape_ampersand():
    assert 'InspectorGroup("SCALE && PITCH"' in GUI
    assert 'InspectorGroup("SCALE & PITCH"' not in GUI


@pytest.fixture(scope="module")
def window():
    from PySide6.QtWidgets import QApplication
    import auricle_gui as g
    app = QApplication.instance() or QApplication([])
    win = g.MainWindow()
    yield g, app, win
    win.performance_timer.stop(); win.transport_worker.stop()


def test_theme_switch_updates_application_palette(window):
    g, app, win = window
    from PySide6.QtGui import QPalette
    win.theme_combo.setCurrentText("Solar")
    assert app.palette().color(QPalette.Highlight).name() == THEMES["Solar"].accent
    assert app.palette().color(QPalette.Base).name() == THEMES["Solar"].panel
    win.theme_combo.setCurrentText("Midnight")


def test_timeline_and_stage_strip_follow_phrase_state(window):
    g, app, win = window
    perf = win.performance
    perf.update_activity(win.project, False)
    assert not hasattr(perf, "form_panel")
    assert not perf.phrase_panel.timeline.running
    assert not perf.phrase_panel.stop.isEnabled()
    pid = perf.phrase_panel.phrase_combo.currentData()
    assert win.engine.performance.start_phrase(win.project, pid, None, 1.0)
    win.engine.director.phrase.stage_index = 1
    perf.update_activity(win.project, True)
    assert perf.phrase_panel.timeline.running
    assert perf.phrase_panel.timeline.stage_index == 1
    assert perf.phrase_panel.stages._pills[1].property("active")
    assert perf.phrase_panel.stop.isEnabled()
    # STOP must stop the running phrase even after the selector moved.
    perf.phrase_panel.phrase_combo.setCurrentIndex((perf.phrase_panel.phrase_combo.currentIndex() + 1) % perf.phrase_panel.phrase_combo.count())
    perf.phrase_panel._stop()
    assert not win.engine.director.phrase.running


def test_perform_card_turns_off_when_gesture_finishes(window):
    g, app, win = window
    card = next(iter(win.performance.cards.values()))
    card._restart()
    assert card.enable.isChecked()
    win.engine.performance.stop(card.block_id)
    card.set_activity(0.0, False)
    assert not card.enable.isChecked()
    assert win.project.performance[str(card.block_id)]["enabled"] is False


def test_diagnostics_are_live(window):
    g, app, win = window
    win.performance.update_activity(win.project, False)
    texts = [c.diagnostics.text() for c in win.performance.cards.values()]
    assert all("--" not in t for t in texts)
    assert any("Groove" in t for t in texts)


def test_knob_reset_uses_real_default(window):
    g, app, win = window
    knob = g.RangeKnob(0.0, 1.0, 0.3, default=1.0)
    knob._reset()
    assert knob.value() == pytest.approx(1.0)


def test_value_stepper_rounds_and_ignores_garbage():
    from PySide6.QtWidgets import QApplication
    import auricle_gui as g
    QApplication.instance() or QApplication([])
    s = g.ValueStepper(10); s.setRange(1, 128)
    s.setValue("12.6"); assert s.value() == 13
    s.setValue("abc"); assert s.value() == 13
