"""Native controls must reflect independently selected playback modes."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy

import pytest
pytest.importorskip("PySide6")

from composition_planner import make_section
from parameter_sources import SourceSnapshot
from test_kit_preview_lifecycle import inspector


def prepare(win, monkeypatch):
    monkeypatch.setattr(win.transport, "refresh_ports", lambda: None)
    win.project.composition.update(enabled=True, sections=[make_section("Drop", bars=2)])
    win.composition_panel.sync_from_project()
    win.history_controller.reset()


def test_main_play_is_plain_audition_and_form_controls_do_not_light_up(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    prepare(win, monkeypatch)
    panel = win.composition_panel
    before = deepcopy(win.project.composition)
    win.engine.performance.start_phrase(win.project, "opening_bloom")
    win.play.click()
    panel.update_runtime()
    assert win.play.isChecked() and not panel.play_button.isChecked()
    assert not panel.stop_button.isEnabled()
    assert panel.enabled.isChecked() and win.project.composition == before
    assert not win.engine.director.phrase.running
    assert not win.engine.performance.active
    assert SourceSnapshot(win.engine).context is None
    assert not panel.timeline.running
    assert panel.status.text().startswith("BYPASS")
    # Editing Active or the form cursor must not cut notes / seek the sound check.
    released = []
    monkeypatch.setattr(win.transport, "_release_block_notes", released.append)
    panel._set_block_setting(panel._selected_section()["id"], melody.id, "enabled", False)
    assert not released
    win.engine.clock.position_beats = 6.
    panel._seek_composition(1.)
    assert win.engine.clock.position_beats == 6.
    assert win.transport.composition_position == 4.
    panel._stop_composition()
    assert win.transport.running and win.play.isChecked()
    win.stop.click()
    assert not errors


def test_composition_play_and_blocks_play_switch_exclusively(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    prepare(win, monkeypatch)
    panel = win.composition_panel
    win.play.click()
    panel.play_button.click()
    assert panel.play_button.isChecked() and not win.play.isChecked()
    assert win.transport.running and win.transport.playback_mode == "composition"
    assert win.engine.composition_runtime.enabled()
    win.play.click()
    panel.update_runtime()
    assert win.play.isChecked() and not panel.play_button.isChecked()
    assert not win.engine.composition_runtime.enabled()
    win.stop.click()
    panel.play_button.click()
    assert panel.play_button.isChecked()
    panel.play_button.click()
    assert not win.transport.running
    assert not win.play.isChecked() and not panel.play_button.isChecked()
    assert not errors


def test_explicit_perform_start_starts_phrase_without_composition_or_main_play(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    prepare(win, monkeypatch)
    phrase = win.performance.phrase_panel
    phrase._start()
    assert win.transport.running and win.transport.playback_mode == "perform"
    assert win.engine.director.phrase.running
    assert not win.play.isChecked()
    assert not win.composition_panel.play_button.isChecked()
    assert not win.engine.composition_runtime.enabled()
    win.stop.click()
    assert not win.engine.director.phrase.running
    win.play.click()
    assert win.play.isChecked() and not win.engine.director.phrase.running
    win.stop.click()
    assert not errors


def test_saved_enabled_technique_is_not_restarted_by_card_rebuild(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    prepare(win, monkeypatch)
    win.project.performance[str(melody.id)] = {"preset_id": "staccato", "enabled": True}
    card = gui.PerformanceBlockCard(melody, win)
    assert not win.transport.running
    assert not win.engine.performance.active
    assert not card.enable.isChecked()
    card.enable.click()
    assert win.transport.running and melody.id in win.engine.performance.active
    gesture = win.engine.performance.active[melody.id]
    replacement = gui.PerformanceBlockCard(melody, win)
    assert replacement.enable.isChecked()
    assert win.engine.performance.active[melody.id] is gesture
    win.stop.click()
    card.deleteLater()
    replacement.deleteLater()
    assert not errors


@pytest.mark.parametrize("mode", ["blocks", "composition"])
@pytest.mark.parametrize("edit", ["parameter", "structure"])
def test_undo_redo_preserves_playback_mode_and_composition_gate(inspector, monkeypatch, mode, edit):
    gui, win, drum, melody, errors = inspector
    prepare(win, monkeypatch)
    win.selected_block_id = melody.id
    win._refresh_inspector()
    win.transport.start(mode=mode)
    win.transport.composition_position = 3.
    win.engine.clock.position_beats = 5.
    win.history_controller.reset()
    if edit == "parameter":
        knob = next(knob for knob in win.findChildren(gui.Knob)
                    if getattr(knob, "_auricle_parameter", None) == (melody.id, "velocity_base"))
        knob.setValue(.29)
    else:
        melody.name = "Renamed lead"
        win._mark_dirty()
    win.history_controller.flush()
    for redo in (False, True):
        win.history_controller.move(redo)
        assert win.transport.running and win.transport.playback_mode == mode
        assert win.engine.composition_runtime.enabled() == (mode == "composition")
        assert win.engine.clock.position_beats == 5.
        assert win.transport.composition_position == 3.
        assert win.play.isChecked() == (mode == "blocks")
        assert win.composition_panel.play_button.isChecked() == (mode == "composition")
    win.transport.stop()
    assert not errors


def test_opening_another_project_clears_old_form_cursor_and_playback_mode(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    prepare(win, monkeypatch)
    win.transport.start(mode="composition")
    win.engine.clock.position_beats = 20.
    win.transport.stop()
    win._install_project(gui.Project(blocks=[gui.Block(1, "New lead", "MELODY")]), None, "New project")
    assert win.transport.composition_position == 0
    assert win.transport.playback_mode == "blocks"
    assert not win.transport.running
    assert not win.composition_panel.play_button.isChecked()
    assert not errors
