"""Phrase length changes must reach the player, Director and saved project."""
import os

import pytest

from auricle_core import Block, MusicEngine, Project
from auricle_persistence import load_project, save_project
from performance_presets import phrase_for, phrase_with_duration

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def engine(monkeypatch):
    # Freeze the tick clock; each test chooses an exact musical position.
    monkeypatch.setattr("performance_presets.time.monotonic", lambda: 100.0)
    project = Project(blocks=[
        Block(1, "Bass", "BASS", "Random Walk", mode="SEQ"),
        Block(2, "Melody", "MELODY", "Markov", mode="LIVE"),
    ])
    return MusicEngine(project)


def test_duration_scales_stages_without_changing_catalog_or_stop_release():
    original = phrase_for("climax_release")
    stretched = phrase_with_duration(original, 30)
    assert [stage.beats for stage in stretched.stages] == [8, 2, 8, 12]
    assert original.total_beats == 15
    assert stretched.release_beats == original.release_beats


@pytest.mark.parametrize("duration", [4, 30, 256])
def test_scaled_phrase_enters_each_stage_and_finishes_on_time(engine, duration):
    runtime = engine.performance
    assert runtime.start_phrase(engine.project, "climax_release", duration_beats=duration)
    state = engine.director.phrase
    scaled = phrase_with_duration(phrase_for("climax_release"), duration)
    cursor = 0
    for index, stage in enumerate(scaled.stages):
        state.position_beats = cursor + stage.beats / 2
        runtime.tick()
        assert state.running
        assert state.stage_index == index
        for block in engine.project.blocks:
            assert runtime.active[block.id].beats == pytest.approx(stage.beats)
        assert engine.director.snapshot().progress == pytest.approx(state.position_beats / duration)
        cursor += stage.beats
    state.position_beats = duration - .001
    runtime.tick()
    assert state.running
    state.position_beats = duration
    runtime.tick()
    assert not state.running
    assert not runtime.active


def test_live_duration_edit_preserves_curve_and_stage_progress(engine):
    runtime = engine.performance
    runtime.start_phrase(engine.project, "climax_release", duration_beats=30)
    state = engine.director.phrase
    state.position_beats = 9
    runtime.tick()
    for active in runtime.active.values():
        active.elapsed_beats = 1
    before = engine.director.snapshot()
    runtime.update_phrase_duration(60)
    assert state.position_beats == 18
    assert state.stage_index == 1
    assert state.memory["total_beats"] == 60
    after = engine.director.snapshot()
    assert after.progress == pytest.approx(before.progress)
    assert after.tension == pytest.approx(before.tension)
    for active in runtime.active.values():
        assert active.beats == 4
        assert active.elapsed_beats == 2
    runtime.tick()
    assert state.stage_index == 1
    state.position_beats = 20
    runtime.tick()
    assert state.stage_index == 2


def test_saved_running_phrase_retains_duration_and_stage_timing(engine, tmp_path):
    engine.performance.start_phrase(engine.project, "climax_release", duration_beats=30)
    engine.director.phrase.position_beats = 9
    engine.performance.tick()
    engine.director.sync_project(engine.project)
    path = tmp_path / "phrase.json"
    save_project(engine.project, str(path))
    restored = MusicEngine(load_project(str(path)))
    restored.performance.tick()
    assert restored.director.phrase.memory["total_beats"] == 30
    assert restored.director.phrase.stage_index == 1
    assert restored.performance.active[1].beats == 2


def test_phrase_ui_duration_controls_runtime_and_survives_save(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication
    import auricle_gui as gui

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui, "get_midi_output_names", lambda: ([], None))
    win = gui.MainWindow()
    win.performance_timer.stop()
    win.transport_worker.stop()
    # PLAY PHRASE is exercised without opening a physical MIDI device.
    monkeypatch.setattr(win.transport, "start", lambda: None)
    try:
        panel = win.performance.phrase_panel
        panel.phrase_combo.setCurrentIndex(panel.phrase_combo.findData("climax_release"))
        assert panel.duration.value() == 15
        panel.duration.setValue(30)
        panel._start()
        state = win.engine.director.phrase
        assert state.memory["total_beats"] == 30
        state.position_beats = 9
        panel.duration.setValue(60)
        assert state.position_beats == 18
        assert panel.timeline.progress == pytest.approx(.3)
        assert panel.timeline.phrase.total_beats == 60
        panel._stop()

        path = tmp_path / "ui_phrase.json"
        win.engine.director.sync_project(win.project)
        save_project(win.project, str(path))
        win._install_project(load_project(str(path)), str(path), "Phrase restored")
        panel = win.performance.phrase_panel
        assert panel.phrase_combo.currentData() == "climax_release"
        assert panel.duration.value() == 60
        assert panel.timeline.phrase.total_beats == 60
        panel._start()
        assert win.engine.director.phrase.memory["total_beats"] == 60
    finally:
        win.performance_timer.stop()
        win.transport_worker.stop()
        win.hide()
        win.deleteLater()
        app.processEvents()
