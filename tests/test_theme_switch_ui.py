"""Themes recolour existing controls without rebuilding musical UI state."""
from copy import deepcopy

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QSplitter

from auricle_core import Relation
from auricle_drum import KIT_DEFAULTS
from coordinated_kit import CREATIVE_DEFAULTS
from test_kit_preview_lifecycle import inspector
from ui_themes import theme_names, theme_palette


def test_theme_keeps_controls_playback_and_history(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    win.project.relations = [Relation(drum.id, 'rhythm', melody.id, 'rhythm', 'Follow', .5)]
    win.selected_drum_voice_id = drum.drum_voices[0].id
    win._refresh_all(); win.show(); QTest.qWait(60)
    win.relation_graph.filter_edit.setText('Follow')
    win.history_controller.reset()
    before = win.history_controller.snapshot()
    page = win.inspector_scroll.widget()
    kit = win.drum_kit_layout.itemAt(0).widget()
    cards = dict(win.performance.cards)
    blocks = [win.block_list.itemWidget(win.block_list.item(i)) for i in range(win.block_list.count())]
    rows = list(win.relation_graph.rows)
    scene = set(win.patch_overview.scene.items())
    splitter = win.findChild(QSplitter)
    sizes = splitter.sizes()
    win.engine.clock.position_beats = 17.25
    win.transport.running = True

    def forbidden(*args, **kwargs):
        raise AssertionError('Theme rebuilt controls, regenerated music, or restyled all application widgets')

    for name in ('_refresh_all', '_refresh_blocks', '_refresh_inspector', '_queue_inspector_refresh', '_refresh_relations'):
        monkeypatch.setattr(win, name, forbidden)
    monkeypatch.setattr(win.performance, 'refresh_blocks', forbidden)
    monkeypatch.setattr(win.patch_overview, 'rebuild', forbidden)
    monkeypatch.setattr(win.engine, 'generate', forbidden)
    monkeypatch.setattr(win.engine, 'regenerate', forbidden)
    monkeypatch.setattr(QApplication.instance(), 'setStyleSheet', forbidden)
    try:
        for name in theme_names():
            win.theme_combo.setCurrentText(name); QTest.qWait(10)
            theme = theme_palette(name)
            assert win.inspector_scroll.widget() is page
            assert win.drum_kit_layout.itemAt(0).widget() is kit
            assert win.performance.cards == cards and win.relation_graph.rows == rows
            assert set(win.patch_overview.scene.items()) == scene
            assert [win.block_list.itemWidget(win.block_list.item(i)) for i in range(len(blocks))] == blocks
            assert win.relation_graph.filter_edit.text() == 'Follow'
            assert win.engine.clock.position_beats == 17.25 and win.transport.running
            assert win.history_controller.snapshot() == before and not win._dirty
            assert win.updatesEnabled() and splitter.sizes() == sizes
            assert all(theme.card in card.styleSheet() for card in cards.values())
            assert all(theme.card in row.styleSheet() for row in rows)
            assert all(theme.danger in card.mute_button.styleSheet() for card in blocks)
            assert QApplication.palette().color(QPalette.Window).name() == theme.bg
            assert not errors
        # History's temporarily removed event filter must receive gestures again.
        serial = win.history_controller.serial
        QTest.mouseClick(win.theme_combo, Qt.LeftButton, pos=QPoint(20, 10))
        QTest.keyClick(win.theme_combo, Qt.Key_Escape)
        assert win.history_controller.serial > serial
    finally:
        win.transport.running = False


def test_existing_and_new_dialogs_inherit_window_theme(inspector):
    gui, win, drum, melody, errors = inspector
    win.show()
    existing = gui.AddBlockDialog(win)
    existing.show(); QTest.qWait(20)
    try:
        for name in ('Solar', 'Midnight', 'Cream Studio'):
            win.theme_combo.setCurrentText(name)
            fresh = gui.AddBlockDialog(win)
            fresh.show(); QTest.qWait(20)
            try:
                theme = theme_palette(name)
                for dialog in (existing, fresh):
                    assert dialog.palette().color(QPalette.Window).name() == theme.bg
                    assert dialog.palette().color(QPalette.WindowText).name() == theme.text
                    assert dialog.grab().toImage().pixelColor(1, 1).name() == theme.bg
                assert not errors
            finally:
                fresh.close(); fresh.deleteLater()
    finally:
        existing.close(); existing.deleteLater()


def test_kit_captions_above_knobs_and_global_names_on_left(inspector):
    gui, win, drum, melody, errors = inspector
    win.show(); QTest.qWait(40)
    panel = win.drum_kit_layout.itemAt(0).widget()
    values = deepcopy(drum.parameters)
    for key in (*KIT_DEFAULTS, *CREATIVE_DEFAULTS):
        knob = panel.findChild(gui.ParamKnob, key)
        title = knob.parentWidget().findChild(QLabel, 'knobLabel')
        assert title is not None and title.geometry().bottom() <= knob.geometry().top()
        assert abs(title.geometry().center().x() - knob.geometry().center().x()) <= 1
        assert knob.value_label.geometry().top() >= 54
        assert knob.value_label.geometry().bottom() < knob.height()
        assert title.fontMetrics().horizontalAdvance(title.text()) <= title.width()
    for width in (820, 1500):
        win.resize(width, 900); QTest.qWait(30)
        bar = win.global_macro_bar
        for name, slider, value in zip(bar.labels, bar.sliders, bar.values):
            assert name.geometry().right() < slider.geometry().left()
            assert slider.geometry().right() < value.geometry().left()
            assert value.geometry().right() < value.parentWidget().width()
    assert drum.parameters == values and not errors
