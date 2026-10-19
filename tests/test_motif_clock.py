"""Musical position, audible MIDI order and transport/Inspector lifecycle."""
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from auricle_core import Block, MusicEngine, Project, Transport, load_project, save_project
from motif_engine import Motif
from musical_clock import MusicalClock


def motif_project(modes=("SEQ", "LIVE")):
    motif = Motif("theme", "Four slots", notes=[0, 2, 4, 7],
                  rhythm=[1, 0, 1, 1], velocity=[.8, .6, .7, .9], step_beats=.5)
    blocks = [Block(i, mode, "MELODY", "Probability", mode,
                    midi_channel=i, midi_port="capture", mutators=[], parameters={
                        "motif_id": motif.id, "probability": 0,
                        "role_center": 0, "role_width": 48, "role_duration": 1,
                        "gate": .7, "live_gate": .7, "fill_density": 1,
                        "harmony_anchor": 0,
                    }) for i, mode in enumerate(modes, 1)]
    return Project(tempo=120, length=7, blocks=blocks, motifs={motif.id: asdict(motif)})


@pytest.fixture
def rig(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("auricle_transport.time.monotonic", lambda: now[0])
    project = motif_project()
    engine = MusicEngine(project)
    sent, errors = [], []
    app = SimpleNamespace(project=project, engine=engine, set_message=lambda _: None,
                          record_generated_event=lambda *_: None,
                          log_midi_message=lambda *_: None)
    transport = Transport(app)
    transport.refresh_ports = lambda: None
    transport._log_error = lambda context, error: errors.append((context, error))
    transport.outputs["capture"] = SimpleNamespace(send=lambda msg: sent.append((now[0], msg)))
    transport.start()
    def tick(seconds):
        now[0] = 100.0 + seconds
        transport.tick()
        assert not errors
    return project, engine, transport, now, sent, tick


def notes(sent, channel):
    return [(round(t - 100, 5), m.note) for t, m in sent if m.type == "note_on" and m.channel == channel]


def test_clock_integrates_tempo_without_jump_or_double_count():
    clock = MusicalClock()
    clock.start(10, 120)
    assert clock.advance(10.5, 60) == 1
    assert clock.advance(11) == .5
    assert clock.advance(10.8) == 0
    assert clock.advance(11.5) == .5
    assert clock.position_beats == 2
    clock.stop(12)
    assert clock.advance(20) == 0
    assert clock.position_beats == 2.5
    clock.start(30, 90)
    assert clock.position_beats == 0
    assert clock.seconds_for_beats(3) == 2


def test_seq_live_share_notes_rests_cycles_and_first_delayed_tick(rig):
    project, engine, transport, now, sent, tick = rig
    for t in (.005, .01, .25, .3, .5, .75, 1, 1.25, 1.5, 1.75, 2):
        tick(t)
    expected = [(.005, 60), (.5, 64), (.75, 67), (1, 60), (1.5, 64), (1.75, 67), (2, 60)]
    assert notes(sent, 0) == notes(sent, 1) == expected
    assert len(project.blocks[0].outputs["rhythm"]) == 4  # not project LENGTH 7
    assert engine.clock.position_beats == 4


def test_bpm_edit_preserves_fractional_beat_and_next_onset(rig):
    project, engine, transport, now, sent, tick = rig
    tick(0)
    now[0] = 100.125
    transport.set_tempo(60)
    assert engine.clock.position_beats == .25
    tick(.375)  # rest at beat .5
    tick(.874)
    assert len(notes(sent, 1)) == 1
    tick(.875)
    assert engine.clock.position_beats == pytest.approx(1)
    assert notes(sent, 0) == notes(sent, 1) == [(0, 60), (.875, 64)]


def test_mute_regeneration_and_mode_switch_do_not_restart_motif(rig):
    project, engine, transport, now, sent, tick = rig
    live = project.blocks[1]
    tick(0)
    live.muted = True
    transport.set_block_muted(live.id, True)
    tick(.25)
    tick(.5)
    engine.regenerate(live)
    engine.reset_live()
    live.mode = "SEQ"
    live.muted = False
    transport.set_block_muted(live.id, False)
    tick(.75)
    live.mode = "LIVE"
    engine.reset_live()
    tick(.76)  # switching within a slot must not duplicate the note
    tick(1)
    assert notes(sent, 1) == [(0, 60), (.75, 67), (1, 60)]


def test_worker_stall_skips_old_slots_and_stop_play_resets(rig):
    project, engine, transport, now, sent, tick = rig
    tick(0)
    tick(1.6)  # beat 3.2, slot 6: one E, not a burst of overdue notes
    assert notes(sent, 0) == notes(sent, 1) == [(0, 60), (1.6, 64)]
    transport.stop()
    tick(10)
    assert engine.clock.position_beats == pytest.approx(3.2)
    transport.start()
    tick(10.005)
    assert notes(sent, 1)[-1] == (10.005, 60)


def test_binding_a_motif_while_playing_joins_global_phase(rig):
    project, engine, transport, now, sent, tick = rig
    live = project.blocks[1]
    live.parameters["motif_id"] = ""
    tick(.1)
    live.parameters["motif_id"] = "theme"
    tick(.3)
    assert notes(sent, 1) == []
    tick(.5)
    assert notes(sent, 1) == [(.5, 64)]


@pytest.mark.parametrize("algorithm,params", [
    ("Pattern", {"pattern": "0"}), ("Probability", {"probability": 0}),
    ("Markov", {"markov_rest": 1}), ("Euclidean", {"pulses": 0}),
])
def test_motif_is_a_source_and_rests_advance_by_position(algorithm, params):
    project = motif_project(("LIVE",))
    block = project.blocks[0]
    block.algorithm = algorithm
    block.parameters.update(params)
    engine = MusicEngine(project)
    assert engine.live_event(block, beat=0)["pitch"] == 0
    assert engine.live_event(block, beat=.5) is None
    assert block.outputs["rhythm"] == [0]
    assert engine.live_event(block, beat=1.5)["pitch"] == 7
    engine.reset_live()
    assert engine.live_event(block, beat=2)["pitch"] == 0
    block.parameters["fill_density"] = 0
    assert engine.live_event(block, beat=2) is None


def test_binding_off_phrase_scope_and_persistence(tmp_path):
    project = motif_project()
    engine = MusicEngine(project)
    a, b = project.blocks
    a.parameters.pop("motif_id")
    b.parameters["motif_id"] = ""
    assert engine.active_motif(a) is None
    engine.performance.start_phrase(project, "opening_bloom", [a.id])
    assert engine.active_motif(a).id == "theme"
    assert engine.active_motif(b) is None
    b.parameters.pop("motif_id")
    assert engine.active_motif(b) is None  # not targeted by the phrase
    a.parameters.update(motif_id="theme", motif_step_beats=.75)
    engine.director.sync_project(project)
    path = tmp_path / "motifs.json"
    save_project(project, path)
    loaded = load_project(path)
    restored = MusicEngine(loaded)
    assert restored.active_motif(loaded.blocks[0]).notes == [0, 2, 4, 7]
    assert restored.motif_step_beats(loaded.blocks[0]) == .75
    assert restored.director.motifs.motifs["theme"].step_beats == .5


@pytest.mark.parametrize("base", [.2, .72, .9])
def test_motif_dynamics_and_gate_match_in_seq_live(base):
    project = motif_project()
    for block in project.blocks:
        block.parameters.update(velocity_base=base, velocity_accent=.1, gate=.4)
    engine = MusicEngine(project)
    engine.generate()
    seq, live = project.blocks
    for slot in (0, 2, 3):
        event = engine.live_event(live, beat=slot * .5)
        assert event["velocity"] == pytest.approx(seq.outputs["velocity"][slot])
        assert event["duration"] == pytest.approx(seq.outputs["duration"][slot])
    if base == .72:
        assert seq.outputs["velocity"][0] == pytest.approx(.835)


def test_phrase_and_technique_catch_up_using_the_same_clock(rig):
    project, engine, transport, now, sent, tick = rig
    engine.performance.start_phrase(project, "climax_release", [1], duration_beats=30)
    tick(0)
    tick(4.5)
    state = engine.director.phrase
    assert state.position_beats == engine.clock.position_beats == 9
    assert state.stage_index == 1
    assert engine.performance.active[1].elapsed_beats == 1


def test_phrase_completion_accounts_only_for_release_overshoot(rig):
    project, engine, transport, now, sent, tick = rig
    engine.performance.start_phrase(project, "climax_release", [1], duration_beats=30)
    tick(0)
    tick(15.25)
    assert not engine.director.phrase.running
    assert engine.director.phrase.position_beats == 30
    assert engine.performance.active_phrase_releases["climax_release"].elapsed_beats == .5
