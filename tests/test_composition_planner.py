import pytest
from copy import deepcopy

from auricle_model import Block, Project, ensure_drum_voices
from auricle_engine import MusicEngine
from auricle_persistence import project_from_dict, save_project, load_project
from composition_planner import (
    CompositionRuntime, SECTION_TYPES, default_composition, make_section,
    normalize_composition,
)


def _section(section_type, sid, bars, macros=None, blocks=None):
    return {
        "id": sid, "type": section_type, "name": sid, "bars": bars,
        "macros": macros or {"energy": None, "tension": None, "density": None, "variation": None},
        "blocks": blocks or {},
    }


def test_default_composition_is_neutral_and_disabled():
    config = default_composition()
    assert config["enabled"] is False
    assert config["meter"] == "4/4"
    assert config["loop"] is True
    assert config["sections"][0]["bars"] == 8
    assert all(value is None for value in config["sections"][0]["macros"].values())
    assert len(SECTION_TYPES) == 8


def test_section_positions_follow_duration_meter_and_loop():
    project = Project()
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Intro", "intro", 2), _section("Drop", "drop", 1)],
    })
    runtime = CompositionRuntime(project)
    assert runtime.context(0)["section_id"] == "intro"
    assert runtime.context(7.99)["section_id"] == "intro"
    assert runtime.context(8)["section_id"] == "drop"
    assert runtime.context(12)["section_id"] == "intro"
    project.composition["meter"] = "7/8"
    assert runtime.context(7.0)["section_id"] == "drop"


def test_non_looping_form_holds_last_section_after_end():
    project = Project()
    project.composition = normalize_composition({
        "enabled": True, "meter": "3/4", "loop": False,
        "sections": [_section("Intro", "a", 1), _section("Outro", "b", 1)],
    })
    runtime = CompositionRuntime(project)
    assert runtime.context(3.0)["section_id"] == "b"
    context = runtime.context(100.0)
    assert context["section_id"] == "b"
    assert context["section_bar"] == 1


def test_type_preset_creates_independent_block_settings():
    drum = Block(1, "KIT", "DRUM")
    ensure_drum_voices(drum)
    melody = Block(2, "LEAD", "MELODY")
    section = make_section("Drop", [*drum.drum_voices, melody], bars=8)
    assert section["bars"] == 8
    assert section["macros"]["energy"] > .8
    assert section["blocks"][str(drum.drum_voices[0].id)]["density"] == 1.0
    assert section["blocks"][str(melody.id)]["enabled"] is True
    assert section["blocks"][str(melody.id)]["register_center"] == 0


def test_composition_event_uses_section_macro_override_and_block_settings():
    block = Block(2, "LEAD", "MELODY", midi_note=60)
    project = Project(blocks=[block])
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Drop", "drop", 4,
            macros={"energy": 1.0, "tension": .5, "density": 1.0, "variation": .5},
            blocks={"2": {"enabled": True, "density": 1.0, "velocity": .5,
                          "register_center": 7, "variation": 0.0}})],
    })
    engine = MusicEngine(project)
    event = {"pitch": 2.0, "velocity": .5, "duration": .5, "_composition_slot": 0}
    result = engine.apply_composition_event(block, event, 0.0)
    assert result is not None
    assert result["pitch"] == 2.0  # register placement precedes this expression stage
    assert engine.effective_register_center(block) == 7.0
    # Global Energy .5 has a neutral scale of 1.0; section Energy 1.0 scales 1.3.
    assert abs(result["velocity"] - .325) < 1e-8
    assert "_composition_slot" not in result


def test_composition_can_restore_density_removed_by_old_global_macro_path():
    block = Block(2, "LEAD", "MELODY", "Euclidean", "SEQ", parameters={"euclidean_steps": 16, "pulses": 8})
    project = Project(blocks=[block])
    project.macros = [{"name": "Density", "control": "density", "value": .05, "routes": []}]
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Drop", "drop", 4,
            macros={"energy": None, "tension": None, "density": 1.0, "variation": None},
            blocks={"2": {"enabled": True, "density": 1.0, "velocity": 1.0,
                          "register_center": 0, "variation": 0.0}})],
    })
    engine = MusicEngine(project)
    engine.generate_block(block)
    assert sum(1 for hit in block.outputs["rhythm"] if hit > 0) == 8
    result = engine.apply_composition_event(block, {"pitch": 0, "velocity": .7, "duration": .4}, 0.0)
    assert result is not None


def test_block_density_zero_and_inactive_section_silence_event():
    block = Block(2, "LEAD", "MELODY")
    project = Project(blocks=[block])
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Verse", "verse", 4,
            blocks={"2": {"enabled": True, "density": 0.0, "velocity": 1.0,
                          "register_center": 0, "variation": 0.0}})],
    })
    engine = MusicEngine(project)
    assert engine.apply_composition_event(block, {"pitch": 0, "velocity": .8, "duration": .5}, 0.0) is None
    project.composition["sections"][0]["blocks"]["2"]["density"] = 1.0
    project.composition["sections"][0]["blocks"]["2"]["enabled"] = False
    assert engine.apply_composition_event(block, {"pitch": 0, "velocity": .8, "duration": .5}, 0.0) is None


def test_composition_variation_is_deterministic_for_same_musical_event():
    block = Block(2, "LEAD", "MELODY")
    project = Project(seed=19, blocks=[block])
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Build", "build", 4,
            macros={"energy": None, "tension": None, "density": 1.0, "variation": .9},
            blocks={"2": {"enabled": True, "density": 1.0, "velocity": 1.0,
                          "register_center": 0, "variation": .8}})],
    })
    engine = MusicEngine(project)
    a = engine.apply_composition_event(block, {"pitch": 0, "velocity": .6, "duration": .5, "_composition_slot": 3}, .75)
    b = engine.apply_composition_event(block, {"pitch": 0, "velocity": .6, "duration": .5, "_composition_slot": 3}, .75)
    assert a == b


def test_composition_roundtrips_through_project_json(tmp_path):
    project = Project(blocks=[Block(1, "LEAD", "MELODY")])
    project.composition = normalize_composition({
        "enabled": True, "meter": "5/4", "loop": False,
        "sections": [_section("Intro", "intro", 3, blocks={"1": {"enabled": False}})],
    })
    path = tmp_path / "composition.json"
    save_project(project, str(path))
    restored = load_project(str(path))
    assert restored.composition["enabled"] is True
    assert restored.composition["meter"] == "5/4"
    assert restored.composition["sections"][0]["id"] == "intro"
    assert restored.composition["sections"][0]["blocks"]["1"]["enabled"] is False


def test_legacy_project_without_composition_loads_neutral_form():
    project = project_from_dict({"tempo": 120, "length": 16, "blocks": [{"id": 1, "name": "LEAD", "block_type": "MELODY"}]})
    runtime = CompositionRuntime(project)
    assert runtime.enabled() is False
    assert runtime.context(0)["section"]["name"] == "Main"


def test_section_tension_controls_harmonic_anchor_strength(monkeypatch):
    import harmonic_plan
    block = Block(2, "LEAD", "MELODY", midi_note=60, parameters={"harmonic_follow": True, "harmonic_strength": .5})
    project = Project(blocks=[block])
    project.harmonic_plan = {"enabled": True, "meter": "4/4", "loop": True,
                             "chords": [{"root": 0, "quality": "major", "bars": 1}]}
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Break", "break", 4,
            macros={"energy": None, "tension": 0.0, "density": 1.0, "variation": None})],
    })
    strengths = []
    monkeypatch.setattr(harmonic_plan, "anchor_selected",
                        lambda seed, block_id, beat, strength, bias=0.0: strengths.append(strength) or False)
    engine = MusicEngine(project)
    engine.harmonize_event(block, {"pitch": 1.0, "velocity": .7, "rhythm": 1.0}, 0.0)
    project.composition["sections"][0]["macros"]["tension"] = 1.0
    engine.harmonize_event(block, {"pitch": 1.0, "velocity": .7, "rhythm": 1.0}, 0.0)
    assert strengths == [.8, .2]


def test_transport_dispatch_applies_section_controls_to_actual_event():
    from types import SimpleNamespace
    from threading import RLock
    from auricle_transport import Transport

    block = Block(2, "LEAD", "MELODY")
    project = Project(blocks=[block])
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Drop", "drop", 4,
            macros={"energy": .5, "tension": .5, "density": 1.0, "variation": .5},
            blocks={"2": {"enabled": True, "density": 1.0, "velocity": .5,
                          "register_center": 24, "variation": 0.0}})],
    })
    engine = MusicEngine(project)
    recorded = []
    app = SimpleNamespace(project=project, engine=engine,
                          record_generated_event=lambda owner, event: recorded.append((owner.id, deepcopy(event))))
    transport = Transport(app)
    result = transport._dispatch_event(block, {"pitch": 2.0, "velocity": .8, "duration": .4}, None, .25, beat=0.0)
    assert result is not None
    assert result["pitch"] == 14.0
    assert result["pitch"] % 12 == 2.0
    assert abs(result["velocity"] - .4) < 1e-8
    assert recorded and recorded[0][1]["pitch"] == 14.0


def test_section_density_override_can_restore_source_events_with_global_density_low():
    block = Block(2, "LEAD", "MELODY")
    project = Project(seed=11, blocks=[block])
    project.macros = [{"name": "Density", "control": "density", "value": .0, "routes": []}]
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Drop", "drop", 4,
            macros={"energy": None, "tension": None, "density": 1.0, "variation": None},
            blocks={"2": {"enabled": True, "density": 1.0, "velocity": 1.0,
                          "register_center": 0, "variation": 0.0}})],
    })
    engine = MusicEngine(project)
    event = engine.apply_composition_event(block, {"pitch": 0, "velocity": .8, "duration": .4}, 0.0)
    assert event is not None


def test_composition_output_gate_is_separate_from_relation_source_stream():
    block = Block(2, "LEAD", "MELODY", "Markov", "LIVE", parameters={"fill_density": 1.0, "event_probability": 1.0})
    project = Project(blocks=[block])
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Break", "break", 4,
            macros={"energy": None, "tension": None, "density": 1.0, "variation": None},
            blocks={"2": {"enabled": False, "density": 1.0, "velocity": 1.0,
                          "register_center": 0, "variation": 0.0}})],
    })
    engine = MusicEngine(project)
    # The generated stream remains available to Relations; the final dispatch
    # gate prevents this block from sounding in the current section.
    assert engine.composition_event_allowed(block, 0.0, 0) is False
    event = engine.live_event(block, beat=0.0)
    assert event is not None or block.outputs.get("rhythm") == [0.0]
    assert engine.apply_composition_event(block, {"pitch": 0, "velocity": .8, "duration": .4}, 0.0) is None


def test_transport_releases_notes_when_section_turns_a_block_off():
    from types import SimpleNamespace
    from auricle_transport import Transport
    block = Block(2, "LEAD", "MELODY")
    project = Project(blocks=[block])
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": False,
        "sections": [
            _section("Verse", "verse", 1, blocks={"2": {"enabled": True}}),
            _section("Break", "break", 1, blocks={"2": {"enabled": False}}),
        ],
    })
    engine = MusicEngine(project)
    app = SimpleNamespace(project=project, engine=engine)
    transport = Transport(app)
    transport._composition_context = engine.composition_runtime.context(0)
    transport._composition_section_key = (0, "verse")
    released = []
    transport._release_block_notes = lambda block_id: released.append(block_id)
    transport._sync_composition_section(4.0)
    assert released == [2]


def test_composition_form_is_included_in_undo_document_state():
    from project_history import ProjectHistory, document_state
    project = Project(blocks=[Block(1, "LEAD", "MELODY")])
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [_section("Verse", "verse", 4)],
    })
    before = document_state(project)
    history = ProjectHistory(before)
    project.composition["sections"][0]["bars"] = 8
    after = document_state(project)
    assert history.commit(after)
    assert history.undo()["composition"]["sections"][0]["bars"] == 4
    assert history.redo()["composition"]["sections"][0]["bars"] == 8


def test_composition_settings_are_isolated_per_section():
    block = Block(1, "LEAD", "MELODY")
    project = Project(seed=31, blocks=[block])
    project.composition = normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True,
        "sections": [
            _section("Intro", "intro", 1,
                macros={"energy": None, "tension": None, "density": 1.0, "variation": None},
                blocks={"1": {"enabled": False, "density": 0.0, "velocity": .4, "register_center": 0, "variation": 0.0}}),
            _section("Drop", "drop", 1,
                macros={"energy": 1.0, "tension": .5, "density": 1.0, "variation": .5},
                blocks={"1": {"enabled": True, "density": 1.0, "velocity": 1.0, "register_center": 0, "variation": 0.0}}),
        ],
    })
    engine = MusicEngine(project)
    assert engine.apply_composition_event(block, {"pitch": 0, "velocity": .8, "duration": .4}, 0.0) is None
    event = engine.apply_composition_event(block, {"pitch": 0, "velocity": .5, "duration": .4}, 4.0)
    assert event is not None
    assert event["velocity"] == pytest.approx(.65)


def test_global_macro_energy_and_variation_are_not_applied_twice():
    from auricle_model import MusicalRepresentation
    block = Block(1, "LEAD", "MELODY")
    project = Project(blocks=[block])
    engine = MusicEngine(project)
    representation = MusicalRepresentation(
        rhythm=[1.0], pitch=[0.0], velocity=[.6], duration=[.5], density=[1.0], accent=[0.0])
    engine._apply_global_macros(block, representation)
    # Neutral Global Energy/Variation must be an identity transform.
    assert representation.velocity == [.6]
