"""Blocks audition must not run an armed form or restart Perform automation."""
from copy import deepcopy

import pytest

from composition_planner import make_section
from parameter_sources import SourceSnapshot
from project_history import document_state
from test_composition_playback import free
from test_coordinated_kit import setup_transport


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_blocks_audition_ignores_enabled_form_silence_macros_center_and_end(monkeypatch, mode):
    project, block, engine = free(mode)
    section = project.composition["sections"][0]
    section["blocks"][str(block.id)] = {"enabled": False, "density": 0,
                                      "velocity": 0, "register_center": 24}
    section["macros"].update(energy=0., density=0., tension=1.)
    before = deepcopy(project.composition)
    engine.performance.start_phrase(project, "opening_bloom")
    engine.performance.tick(True, beat_delta=1)
    assert engine.director.phrase.running and engine.performance.active
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    for index in range(25):
        tick(index * .125)
    assert transport.running and engine.clock.position_beats == 6.
    assert transport.playback_mode == "blocks"
    assert not engine.composition_runtime.enabled()
    assert not engine.director.phrase.running
    assert not engine.performance.active and not engine.performance.active_phrase_releases
    assert engine.apply_composition_event(block, {"pitch": 0, "velocity": .7}, 6) == {"pitch": 0, "velocity": .7}
    assert SourceSnapshot(engine).context is None
    assert any(message.type == "note_on" and message.velocity > 1 for _, message in sent)
    assert project.composition == before


def test_switching_modes_releases_notes_and_uses_only_new_form_controls(monkeypatch):
    project, block, engine = free()
    section = project.composition["sections"][0]
    section["blocks"][str(block.id)] = {"enabled": False}
    before = deepcopy(project.composition)
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    tick(0)
    assert transport.active_notes
    transport.start(mode="composition")
    assert transport.running and engine.composition_runtime.enabled()
    assert transport.active_notes == []
    assert any(message.type == "note_off" for _, message in sent)
    sent.clear()
    tick(.125)
    assert not any(message.type == "note_on" for _, message in sent)
    assert SourceSnapshot(engine).context is not None
    transport.start(mode="blocks")
    tick(.125)
    assert not engine.composition_runtime.enabled()
    assert any(message.type == "note_on" for _, message in sent)
    assert project.composition == before


def test_stop_clears_phrase_technique_and_release_layers_before_next_blocks_start(monkeypatch):
    project, block, engine = free()
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    engine.performance.start_phrase(project, "opening_bloom")
    tick(.5)
    assert engine.director.phrase.running
    assert engine.performance.active
    engine.performance.stop_phrase("opening_bloom")
    assert engine.performance.active_phrase_releases
    transport.stop()
    assert not engine.director.phrase.running
    assert not engine.performance.active and not engine.performance.active_phrase_releases
    assert not any(row["kind"] == "Technique" for entry in engine.parameter_influence.entries.values()
                   for row in entry["rows"].values())
    transport.start()
    tick(.75)
    assert not engine.director.phrase.running and not engine.performance.active


def test_blocks_clock_does_not_advance_stored_composition_cursor(monkeypatch):
    project, block, engine = free()
    project.composition["sections"].append(make_section("Build", bars=4))
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    tick(.75)
    transport.stop()
    cursor = transport.composition_position
    assert cursor == 1.5
    before = document_state(project, engine)
    transport.start(mode="blocks")
    tick(4)
    assert transport.composition_position == cursor
    assert document_state(project, engine) == before


def test_unknown_mode_cannot_interrupt_playing_transport(monkeypatch):
    project, block, engine = free()
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    with pytest.raises(ValueError):
        transport.start(mode="typo")
    assert transport.running and transport.playback_mode == "blocks"
