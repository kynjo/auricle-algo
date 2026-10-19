"""Behavioral coverage for bounded development and audible cycle changes."""
from copy import deepcopy
from dataclasses import asdict

import pytest

from auricle_core import Block, Project, MusicEngine, ensure_drum_voices, load_project, save_project
from generators import scale_intervals
from motif_engine import Motif
from motif_development import MotifDevelopment, anchor_slots, develop, settings
from auricle_catalogs import GENERATORS
from test_motif_clock import rig, notes, motif_project


def theme(role="MELODY"):
    return Motif("theme", "Theme", role=role, notes=[0, 3, 7, 10, 7, 5, 3, 0],
                 rhythm=[1, 1, 0, 1, 1, 0, 1, 1],
                 velocity=[.9, .65, 0, .72, .8, 0, .62, .75], step_beats=.5)


@pytest.mark.parametrize("role", ["MELODY", "BASS", "CHORD", "PAD", "DRUM"])
@pytest.mark.parametrize("mode", ["melodic", "rhythmic", "combined"])
def test_variants_preserve_theme_anchors_and_are_bounded(role, mode):
    source = theme(role)
    original = asdict(source)
    cfg = settings({"motif_development": mode, "motif_amount": 1})
    variant = develop(source, 1, .5, cfg, "Minor", 27).motif
    anchors = anchor_slots(source, .5)
    for i in anchors:
        assert (variant.notes[i], variant.rhythm[i], variant.velocity[i]) == (
            source.notes[i], source.rhythm[i], source.velocity[i])
    assert asdict(source) == original
    assert variant.steps == source.steps
    assert sum(variant.rhythm) >= 2
    assert variant.notes != source.notes or variant.rhythm != source.rhythm or variant.velocity != source.velocity
    if role != "DRUM":
        assert all(n % 12 in scale_intervals("Minor") for n in variant.notes)
        if mode == "melodic":
            assert max(abs(a - b) for a, b in zip(variant.notes, source.notes)) <= 4
    if mode == "melodic":
        assert variant.rhythm == source.rhythm


def test_period_return_and_determinism_without_cumulative_drift():
    source = theme()
    cfg = settings({"motif_development": "combined", "motif_amount": .8, "motif_every": 2, "motif_return": 4})
    variants = [develop(source, cycle, .5, cfg, "Minor", 22) for cycle in range(9)]
    assert variants[0].token == variants[1].token == variants[8].token
    assert variants[2].token == variants[3].token != variants[0].token
    assert variants[8].label == "Return"
    for cycle in (101, 2, 19, 2):
        result = develop(source, cycle, .5, cfg, "Minor", 22)
        assert result == develop(deepcopy(source), cycle, .5, cfg, "Minor", 22)
    assert develop(source, 2, .5, cfg, "Minor", 22) == variants[2]


@pytest.mark.parametrize("parameters", [{}, {"motif_development": "combined", "motif_amount": 0}])
def test_off_or_zero_amount_is_audibly_identical_to_theme(parameters):
    source = theme()
    material = develop(source, 123, .5, settings(parameters), "Minor", 5).motif
    assert material.notes == source.notes
    assert material.rhythm == source.rhythm
    assert material.velocity == source.velocity


def test_silent_or_single_note_motifs_remain_safe():
    cfg = settings({"motif_development": "combined", "motif_amount": 1})
    for rhythm in ([0] * 8, [1]):
        source = Motif("short", "Short", notes=[0], rhythm=rhythm)
        for cycle in range(10):
            variant = develop(source, cycle, .25, cfg, "Minor", 4).motif
            assert variant.rhythm == rhythm


def test_fully_protected_theme_explains_why_it_did_not_change():
    source = Motif("protected", "Protected", notes=[0, 3, 7, 0], rhythm=[1] * 4, step_beats=2)
    variant = develop(source, 1, 2, settings({"motif_development": "combined"}), "Minor", 5)
    assert variant.motif.notes == source.notes
    assert variant.label == "Theme · protected positions"


def test_pending_settings_commit_only_at_boundary_and_history_is_bounded():
    source = theme()
    runtime = MotifDevelopment()
    params = {"motif_development": "combined", "motif_amount": .8}
    resolve = lambda beat: runtime.resolve(1, source, beat, .5, params, "Minor", 33, True)
    current = resolve(4)
    params["motif_amount"] = 0
    assert resolve(7.99) is current
    assert resolve(8).motif.notes == source.notes
    params["motif_amount"] = .8
    for cycle in range(3, 40):
        resolve(cycle * 4)
    assert 2 <= len(runtime.history[1]) <= 8
    current = runtime.current(1)
    assert resolve(current.cycle * 4 - .01) is current  # early humanized attack cannot rewind


def test_transport_plays_same_variants_in_seq_live_and_returns(rig):
    project, engine, transport, now, sent, tick = rig
    transport.stop()
    engine.director.motifs.register(theme())
    project.scale = "Minor"
    for block in project.blocks:
        block.parameters.update(motif_development="combined", motif_amount=.8)
    transport.start()
    for slot in range(40):
        tick(slot * .25)
        if slot == 11:
            engine.generate()  # not a new variation
    assert notes(sent, 0) == notes(sent, 1)
    by_cycle = []
    for cycle in range(5):
        by_cycle.append([(round(t - cycle * 2, 4), note) for t, note in notes(sent, 0) if cycle * 2 <= t < (cycle + 1) * 2])
    assert by_cycle[0] == by_cycle[4]
    assert by_cycle[1] != by_cycle[0]
    assert engine.director.motifs.motifs["theme"].notes == theme().notes


def test_hold_recall_save_and_reload_preserve_material(tmp_path):
    project = motif_project()
    engine = MusicEngine(project)
    engine.director.motifs.register(theme())
    project.scale = "Minor"
    block = project.blocks[0]
    block.parameters.update(motif_development="combined", motif_amount=.8)
    first = engine.motif_variant(block, 4)
    later = engine.motif_variant(block, 12)
    assert engine.hold_motif(block, token=first.token)
    held = engine.motif_variant(block, 16)
    assert held.token == first.token
    assert engine.motif_variant(block, 400).token == first.token
    engine.director.sync_project(project)
    path = tmp_path / "held.json"
    save_project(project, path)
    restored = MusicEngine(load_project(path))
    assert restored.motif_variant(restored.project.blocks[0], 0).token == first.token
    saved = engine.capture_motif(block, current_variant=True)
    assert saved.notes == first.motif.notes
    assert block.parameters["motif_development"] == "off"
    assert "motif_hold" not in block.parameters
    assert saved.id != "theme" and saved.id in project.motifs
    saved.notes[0] = 99
    assert engine.director.motifs.motifs["theme"].notes[0] == 0


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("role", ["MELODY", "BASS", "CHORD", "PAD", "DRUM"])
def test_capture_available_for_every_role_and_drum_voice(role, mode, tmp_path):
    parent = Block(1, role, role, "Pattern", mode, parameters={"pattern": "1,0,2,0"}, mutators=[])
    block = ensure_drum_voices(parent)[0] if role == "DRUM" else parent
    block.algorithm, block.mode = "Pattern", mode
    block.parameters.update(pattern="1,0,2,0")
    project = Project(length=8, blocks=[parent])
    engine = MusicEngine(project)
    before = deepcopy(engine.live_state)
    captured = engine.capture_motif(block)
    assert captured is not None and captured.role == role
    assert captured.steps == 8
    assert captured.rhythm == [1, 0, 1, 0, 1, 0, 1, 0]
    assert engine.active_motif(block) is captured
    assert engine.live_state == before
    path = tmp_path / "capture.json"
    save_project(project, path)
    restored = MusicEngine(load_project(path))
    assert captured.id in restored.director.motifs.motifs
    if role == "DRUM":
        assert "motif_id" not in parent.parameters
        assert engine.capture_motif(parent) is None


def test_changing_source_does_not_recall_old_history():
    runtime = MotifDevelopment()
    source = theme()
    runtime.resolve(1, source, 4, .5, {"motif_development": "combined"}, "Minor", 5, True)
    old = runtime.current(1).token
    source = Motif("other", "Other", notes=[7, 0])
    runtime.resolve(1, source, 4, .5, {}, "Minor", 5, True)
    assert runtime.hold(1, source.id, old) is None
    assert len(runtime.history[1]) == 1


@pytest.mark.parametrize("algorithm", GENERATORS)
def test_generator_capture_produces_complete_reusable_streams(algorithm):
    block = Block(1, "Capture", "MELODY", algorithm, "LIVE", mutators=[])
    engine = MusicEngine(Project(length=16, blocks=[block]))
    captured = engine.capture_motif(block)
    assert len(captured.notes) == len(captured.rhythm) == len(captured.velocity) == 16
    assert all(value in (0, 1) for value in captured.rhythm)
    assert engine.active_motif(block) is captured


def test_early_cycle_switch_and_mode_change_do_not_revert_variant(rig):
    project, engine, transport, now, sent, tick = rig
    transport.stop()
    project.scale = "Minor"
    engine.director.motifs.register(theme())
    for block in project.blocks:
        block.parameters.update(motif_development="combined", motif_amount=.8, timing_offset=-.25)
    transport.start()
    for slot in range(9):
        tick(max(0, slot * .25 - .0625))
    seq = project.blocks[0]
    variant = engine.motif_development.current(seq.id)
    assert variant.cycle == 1  # first note of cycle 1 is played before beat 4
    engine.regenerate(seq)
    assert engine.motif_development.current(seq.id) is variant
    seq.mode = "LIVE"
    engine.reset_live()
    tick(2)
    assert engine.motif_development.current(seq.id) is variant
    assert notes(sent, 0) == notes(sent, 1)


def test_early_drum_variant_does_not_advance_siblings():
    drum = Block(1, "Kit", "DRUM", mutators=[])
    drum.drum_voices = ensure_drum_voices(drum)[:2]
    for voice in drum.drum_voices:
        voice.parameters.update(motif_id="theme", motif_development="combined", motif_amount=.8)
    engine = MusicEngine(Project(blocks=[drum]))
    engine.director.motifs.register(theme("DRUM"))
    engine.clock.start(100, 120)
    engine.clock.position_beats = 3.9
    engine.generate()
    first, second = drum.drum_voices
    previous = engine.motif_development.current(second.id)
    outputs = deepcopy(second.outputs)
    engine.regenerate(first, motif_beat=4)
    assert engine.motif_development.current(first.id).cycle == 1
    assert engine.motif_development.current(second.id) is previous
    assert previous.cycle == 0 and second.outputs == outputs
