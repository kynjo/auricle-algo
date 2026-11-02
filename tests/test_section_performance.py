"""Assigned gestures must follow musical time, mode and section ownership."""
from copy import deepcopy

import pytest

from auricle_core import Block, MusicEngine, Project, ensure_drum_voices
from auricle_persistence import save_project, load_project
from composition_performance import normalize_performance
from composition_planner import make_section, normalize_composition, section_color, available_section_color
from performance_presets import phrase_for, phrase_with_duration
from test_coordinated_kit import setup_transport


def score(mode="SEQ", meter="4/4", bars=2, phrase="opening_bloom"):
    blocks = [Block(i, name, role, "Pattern", mode, parameters={"pattern": "1,2,3,4"}, mutators=[])
              for i, name, role in ((1, "Bass", "BASS"), (2, "Lead", "MELODY"))]
    project = Project(blocks=blocks, tempo=120, length=16)
    first = make_section("Build", blocks, bars=bars, neutral=True)
    first["performance"]["phrase_id"] = phrase
    second = make_section("Verse", blocks, bars=bars, neutral=True)
    project.composition = normalize_composition({"enabled": True, "meter": meter, "loop": False,
                                                 "end_action": "hold", "sections": [first, second]})
    engine = MusicEngine(project)
    engine.composition_runtime.playback_active = True
    engine.generate()
    return project, list(blocks), engine


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("meter,beats", [("2/4", 2), ("4/4", 4), ("6/8", 3), ("7/8", 3.5)])
def test_fitted_phrase_enters_seek_stage_then_cleans_up_at_neutral_section(mode, meter, beats):
    project, blocks, engine = score(mode, meter, bars=1)
    runtime = engine.section_performance
    runtime.advance(0)
    state = engine.director.phrase
    assert state.memory["total_beats"] == pytest.approx(beats)
    assert state.stage_index == 0
    runtime.advance(beats * .8, force=True)
    assert engine.director.phrase.stage_index == 2
    assert all(a.elapsed_beats > 0 for a in engine.performance.active.values())
    runtime.advance(beats)
    assert not engine.performance.active and not engine.director.phrase.running
    assert not any(row["kind"] == "Technique" for entry in engine.parameter_influence.entries.values() for row in entry["rows"].values())


@pytest.mark.parametrize("pid", ["opening_bloom", "climax_release", "breath"])
@pytest.mark.parametrize("beats", [1, 2, 3.5, 768])
def test_section_fit_has_exact_length_including_short_unequal_stages(pid, beats):
    phrase = phrase_with_duration(phrase_for(pid), beats, section_fit=True)
    assert phrase.total_beats == pytest.approx(beats)
    assert phrase_for(pid).total_beats >= 12


def test_explicit_override_and_none_exclude_only_techniques_not_director():
    project, blocks, engine = score()
    section = project.composition["sections"][0]
    section["performance"]["techniques"] = {"1": {"preset_id": "staccato"}, "2": {"preset_id": "none"}}
    engine.section_performance.advance(0)
    assert engine.performance.active[1].preset_id == "staccato"
    assert engine.performance.active[1].owner_section == section["id"]
    assert 2 not in engine.performance.active
    assert all(engine.director_applies(block) for block in blocks)
    engine.section_performance.advance(6)
    assert engine.performance.active[1].preset_id == "staccato"
    assert 2 not in engine.performance.active


@pytest.mark.parametrize("targets", [[], [2], None])
def test_targets_scope_both_director_and_inherited_techniques(targets):
    project, blocks, engine = score()
    project.composition["sections"][0]["performance"]["block_ids"] = targets
    engine.section_performance.advance(0)
    wanted = {1, 2} if targets is None else set(targets)
    assert set(engine.performance.active) == wanted
    assert {b.id for b in blocks if engine.director_applies(b)} == wanted


def test_drum_parent_targets_include_voices_and_skip_other_blocks():
    project, blocks, engine = score()
    drum = Block(3, "Kit", "DRUM")
    drum.drum_voices = ensure_drum_voices(drum)
    project.blocks.append(drum)
    project.composition["sections"][0]["performance"]["block_ids"] = [3]
    engine.section_performance.advance(0)
    assert engine.director_applies(drum)
    assert all(engine.director_applies(voice) for voice in drum.drum_voices)
    assert not any(engine.director_applies(block) for block in blocks)


def test_standalone_override_holds_endpoint_without_regenerating_each_tick(monkeypatch):
    project, blocks, engine = score(phrase=None)
    project.composition["sections"][0]["performance"]["techniques"] = {
        "2": {"preset_id": "staccato", "fit_to_section": False, "beats": 1}}
    engine.section_performance.advance(0)
    engine.section_performance.advance(2)
    active = engine.performance.active[2]
    calls = []
    monkeypatch.setattr(engine, "regenerate", lambda block: calls.append(block.id))
    engine.section_performance.advance(2.1)
    engine.section_performance.advance(2.2)
    assert engine.performance.active[2] is active and active.hold
    assert calls == []


def test_disabling_form_removes_layers_and_rebuilds_cached_material(monkeypatch):
    project, blocks, engine = score()
    engine.section_performance.advance(2)
    calls = []
    original = engine.generate
    monkeypatch.setattr(engine, "generate", lambda: (calls.append(True), original()))
    project.composition["enabled"] = False
    engine.section_performance.advance(3)
    assert not engine.performance.active and not engine.director.phrase.running
    assert calls == [True]


def test_loop_reenters_first_stage_and_seek_does_not_replay_skipped_stages():
    project, blocks, engine = score(bars=1)
    project.composition["loop"] = True
    engine.section_performance.advance(3.8)
    assert engine.director.phrase.stage_index == 2
    engine.section_performance.advance(8.5)
    assert engine.director.phrase.stage_index == 0
    assert engine.director.phrase.position_beats == pytest.approx(.5)
    engine.section_performance.advance(2.8, force=True)
    assert engine.director.phrase.stage_index == 2


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_main_blocks_bypasses_section_performance_and_stop_restores(monkeypatch, mode):
    project, blocks, engine = score(mode)
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    tick(.2)
    assert not engine.performance.active and not engine.director.phrase.running
    transport.start(mode="composition")
    assert engine.performance.active and engine.director.phrase.running
    transport.seek(3)
    assert engine.director.phrase.position_beats == pytest.approx(3)
    transport.stop()
    assert not engine.performance.active and not engine.director.phrase.running
    transport.start()
    assert not engine.performance.active and not engine.director.phrase.running


def test_performance_colors_roundtrip_and_normalize_malformed_settings(tmp_path):
    project, blocks, engine = score()
    section = project.composition["sections"][0]
    section["color"] = "#123abc"
    section["performance"]["techniques"] = {"2": {"preset_id": "staccato", "amount": .4}}
    path = str(tmp_path / "form.json")
    save_project(project, path)
    restored = load_project(path)
    assert restored.composition == normalize_composition(project.composition)
    assert section_color(restored.composition["sections"][0]) == "#123abc"
    assert available_section_color(project.composition["sections"], "#123abc") != "#123abc"
    assert normalize_performance({"phrase_id": [], "amount": float('nan'), "block_ids": [True, 2, -1, "bad"],
                                  "techniques": {"a": {}, "2": None}}) == {
        "phrase_id": None, "amount": 1, "fit_to_section": True, "duration_beats": 16,
        "block_ids": [2], "techniques": {}}
