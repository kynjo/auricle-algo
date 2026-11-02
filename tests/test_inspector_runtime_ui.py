"""Regressions for Inspector sizing and stopped piano-roll time anchoring."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from auricle_core import Block
from test_kit_preview_lifecycle import inspector
from test_midi_learn_runtime_ui import app


def _assert_inspector_reaches_end(gui, win):
    QTest.qWait(40)
    page = win.inspector_scroll.widget()
    assert page is not None
    bar = win.inspector_scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    QTest.qWait(30)
    visible_bottom = bar.value() + win.inspector_scroll.viewport().height()
    # The page's full minimum-height contract must be reachable; checking only
    # the last visible group would miss clipped trailing margins/stretch rows.
    assert page.height() <= visible_bottom + 3


def test_drum_rhythm_settings_really_collapse_and_recalculate_height(inspector):
    gui, win, drum, _melody, errors = inspector
    win.selected_block_id, win.selected_drum_voice_id = drum.id, None
    win._refresh_inspector()
    QTest.qWait(50)

    kit = win.drum_kit_layout.itemAt(0).widget()
    rhythm = kit.rhythm_panel
    assert rhythm.body.isHidden()

    rhythm.more.click()
    QTest.qWait(40)
    assert not rhythm.body.isHidden()
    expanded_height = kit.minimumHeight()
    expanded_page_height = win.inspector_scroll.widget().minimumHeight()

    rhythm.more.click()
    QTest.qWait(40)
    assert rhythm.body.isHidden()
    QTest.qWait(30)
    assert kit.minimumHeight() < expanded_height
    assert win.inspector_scroll.widget().minimumHeight() < expanded_page_height
    assert not errors


def test_inspector_scroll_reaches_bottom_for_drum_voice_and_other_block(inspector):
    gui, win, drum, melody, errors = inspector

    win.selected_block_id, win.selected_drum_voice_id = drum.id, None
    win._refresh_inspector()
    _assert_inspector_reaches_end(gui, win)

    win._select_drum_voice(drum.drum_voices[0].id)
    _assert_inspector_reaches_end(gui, win)

    win.selected_block_id, win.selected_drum_voice_id = melody.id, None
    win._refresh_inspector()
    _assert_inspector_reaches_end(gui, win)
    assert not errors


def test_piano_roll_time_and_sparse_history_stop_advancing(monkeypatch, app):
    import auricle_gui as gui

    clock = [105.0]
    monkeypatch.setattr(gui.time, "monotonic", lambda: clock[0])
    widget = gui.PianoRollWidget()
    block = SimpleNamespace(block_type="MELODY", midi_note=60, outputs={}, parameters={})
    history = [(100.0 + i * .25, 60 + (i % 5), .8) for i in range(20)]

    widget.set_data(block, history, pattern_seconds=1.0, seq_interval=.125, running=True)
    clock[0] = 110.0
    widget.set_data(block, history, pattern_seconds=1.0, seq_interval=.125, running=False)
    stopped_at = widget._display_time()
    visible_at_stop = widget._history_events()

    clock[0] = 125.0
    assert widget._display_time() == stopped_at == 110.0
    assert widget._history_events() == visible_at_stop
    # Old events stay outside the fixed window; a sparse history must never
    # force the timeline to expand to a minimum event count.
    assert visible_at_stop == []

    widget.set_data(block, history, pattern_seconds=1.0, seq_interval=.125, running=True)
    assert widget._display_time() == 125.0
