"""Avoid repeated native layout inspection, hidden polling and stale callbacks."""
import sys
import threading
import time

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from shiboken6 import isValid

import ui_profile_runtime as profile_runtime
from ui_metrics import TRANSPORT_WIDTH
from test_kit_preview_lifecycle import inspector


def test_style_events_do_not_restart_profile_tree_scans(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    QTest.qWait(120)
    runtime = win._algo_conf_runtime
    runtime.timer.stop()
    calls = []
    original = profile_runtime._ac_tree
    monkeypatch.setattr(profile_runtime, "_ac_tree", lambda root: (calls.append(root), original(root))[1])
    for _ in range(30):
        QCoreApplication.sendEvent(win.tempo, QEvent(QEvent.StyleChange))
        QCoreApplication.sendEvent(win.tempo, QEvent(QEvent.FontChange))
    assert not runtime.timer.isActive()
    QTest.qWait(70)
    assert not calls and not errors


def test_size_only_profile_never_inspects_borrowed_layout_items(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    def forbidden(*_args):
        raise AssertionError("Size/font overrides must not search layout ownership")
    monkeypatch.setattr(profile_runtime, "_ac_owner", forbidden)
    win._algo_conf_runtime.apply()
    assert win.composition_panel.play_button.width() == TRANSPORT_WIDTH
    assert win.composition_panel.play_button.size() == win.play.size()
    assert not errors


def test_switching_voices_keeps_one_pinned_kit_and_updates_selection(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.drum_kit_layout.itemAt(0).widget()
    for voice in drum.drum_voices * 3:
        win._select_drum_voice(voice.id)
        QTest.qWait(30)
        assert win.drum_kit_layout.itemAt(0).widget() is panel
        assert panel.selected_voice_id == voice.id
        assert panel.voice_buttons[voice.id].property("selected")
        assert panel.copy_voice_button.isEnabled()
    assert not errors


def test_refresh_reuses_unchanged_performance_cards(inspector):
    gui, win, drum, melody, errors = inspector
    before = dict(win.performance.cards)
    section_before = dict(win.composition_panel.instrument_grid.cards)
    win.performance.refresh_blocks(win.project)
    assert win.performance.cards == before
    assert win.composition_panel.instrument_grid.cards == section_before
    drum.name = "Renamed kit"
    win.performance.refresh_blocks(win.project)
    assert win.performance.cards[melody.id] is before[melody.id]
    assert win.composition_panel.instrument_grid.cards[melody.id] is section_before[melody.id]
    assert win.performance.cards[drum.id] is not before[drum.id]
    assert not errors


def test_heartbeat_updates_only_the_visible_page(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    win.show(); QTest.qWait(60)
    calls = []
    monkeypatch.setattr(win.performance, "update_activity", lambda *_: calls.append("manual"))
    monkeypatch.setattr(win.composition_panel, "update_runtime", lambda: calls.append("composition"))
    win._runtime_view_state = (False, win.transport.playback_mode)
    win._idle_view_refresh_at = 0
    win._refresh_runtime_ui()
    assert not calls
    win.tabs.setCurrentWidget(win.composition_panel)
    win._idle_view_refresh_at = 0
    win._refresh_runtime_ui()
    assert calls == ["composition"]
    assert not errors


def test_busy_worker_cannot_block_ui_refresh(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    acquired, release = threading.Event(), threading.Event()
    def worker():
        with win.transport._state_lock:
            acquired.set(); release.wait(2)
    thread = threading.Thread(target=worker); thread.start()
    try:
        assert acquired.wait(1)
        calls = []
        monkeypatch.setattr(win, "_update_parameter_sources", lambda **_: calls.append(True))
        win._idle_view_refresh_at = 0
        start = time.perf_counter(); win._refresh_runtime_ui()
        assert time.perf_counter() - start < .1 and not calls
    finally:
        release.set(); thread.join(2)
    assert not errors


def test_pending_inspector_and_midi_timers_are_cancelled_with_their_window(inspector, monkeypatch):
    gui, host, drum, melody, errors = inspector
    window = gui.MainWindow()
    window.performance_timer.stop(); window.transport_worker.stop()
    window._queue_inspector_refresh()
    window._pulse_midi_indicator(window.project.blocks[0].id)
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QTest.qWait(120)
    assert not isValid(window) and not errors


def test_scheduler_coalesces_stale_polls_but_keeps_other_callbacks():
    from transport_worker import TransportWorker
    calls = []
    class Transport:
        def tick(self): calls.append("tick")
    worker = TransportWorker(Transport())
    worker.schedule_tick(0)
    worker.queue.push(.001, lambda: calls.append("other"))
    worker.schedule_tick(.002); worker.schedule_tick(.004)
    worker._dispatch_due(1, coalesce_ticks=True)
    assert calls == ["other", "tick"] and not worker.error_count
