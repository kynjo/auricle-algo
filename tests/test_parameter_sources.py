"""Attribution is read-only and follows the musical runtime, not editor selection."""
from copy import deepcopy

import pytest

from auricle_core import Block, Project, MusicEngine, Relation, ensure_drum_voices
from composition_planner import default_composition, make_section
from harmonic_plan import preset as harmonic_preset
from parameter_sources import SourceSnapshot, parameter_values


def setup(mode="SEQ", block_type="MELODY"):
    source = Block(1, "Source", "MELODY", "Pattern", mode, parameters={"pattern": "1,0"}, mutators=[])
    block = Block(2, "Destination", block_type, "Pattern", mode,
                  parameters={"pattern": "1,0", "fill_density": 1., "gate": .8}, mutators=[])
    project = Project(blocks=[source, block], composition=default_composition())
    engine = MusicEngine(project)
    engine.generate()
    return engine, source, block


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_perform_tracks_real_parameter_layers_and_stop(mode):
    engine, _, block = setup(mode)
    assert not SourceSnapshot(engine).marks(block.id, "gate")
    assert engine.performance.start(block, "staccato", beats=8)
    engine.performance.tick(True, beat_delta=1)
    marks = SourceSnapshot(engine).marks(block.id, "gate")
    assert [m.source for m in marks] == ["Perform"]
    assert marks[0].active and "staccato" in marks[0].details[0]
    engine.performance.stop(block.id)
    assert not SourceSnapshot(engine).marks(block.id, "gate")


@pytest.mark.parametrize("policy,active", [
    ({"mode": "manual"}, False),
    ({"weights": {"Technique": 0}}, False),
    ({"priority": ["Macro", "Technique", "Modulation"]}, False),
    ({"priority": ["Macro", "Technique", "Modulation"], "weights": {"Macro": .4}}, True),
    ({"mode": "blend"}, True),
])
def test_bypassed_technique_is_not_reported_as_active(policy, active):
    engine, _, block = setup()
    engine.set_parameter(block, "gate", .3, source="Technique: staccato")
    engine.set_parameter(block, "gate", .6, source="Macro: Custom")
    engine.parameter_influence.set_policy(block, "gate", policy)
    marks = SourceSnapshot(engine).marks(block.id, "gate")
    assert len(marks) == 1 and marks[0].active is active


@pytest.mark.parametrize("block_type", ["DRUM", "BASS", "MELODY", "CHORD", "PAD"])
@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_composition_marks_only_related_output_controls(block_type, mode):
    engine, _, block = setup(mode, block_type)
    form = engine.project.composition
    form["enabled"] = True
    section = form["sections"][0]
    section["blocks"][str(block.id)] = {"enabled": True, "density": .4, "velocity": .8,
                                      "register_center": 7, "variation": .2}
    snapshot = SourceSnapshot(engine)
    assert any(m.source == "Composition" for m in snapshot.marks(block.id, "fill_density"))
    assert any(m.source == "Composition" for m in snapshot.marks(block.id, "velocity_base"))
    assert bool(snapshot.marks(block.id, "role_center")) == (block_type != "DRUM")
    assert not snapshot.marks(block.id, "transpose")
    assert not snapshot.marks(block.id, "pulses")
    assert not snapshot.marks(block.id, "timing_swing")
    assert block.parameters["fill_density"] == 1.


def test_active_section_and_loop_follow_transport_clock_and_override_toggles():
    engine, _, block = setup()
    first = make_section("Intro", bars=1, neutral=True)
    second = make_section("Drop", bars=1, neutral=True)
    second["macros"]["density"] = .2
    engine.project.composition.update(enabled=True, sections=[first, second])
    assert not SourceSnapshot(engine).marks(None, "density")[0].active
    engine.clock.position_beats = 4
    marks = SourceSnapshot(engine).marks(None, "density")
    assert marks[0].source == "Composition" and "Drop" in marks[0].details[0]
    assert SourceSnapshot(engine).marks(block.id, "fill_density")
    engine.clock.position_beats = 8
    # The loop seam blends from Drop's endpoint into Follow Global.
    assert SourceSnapshot(engine).marks(None, "density")[0].active
    engine.clock.position_beats = 9
    assert not SourceSnapshot(engine).marks(None, "density")[0].active
    engine.clock.position_beats = 4
    engine.project.composition["enabled"] = False
    assert not SourceSnapshot(engine).marks(None, "density")
    assert not SourceSnapshot(engine).marks(block.id, "fill_density")


@pytest.mark.parametrize("part,key", [("rhythm", "fill_density"), ("density", "fill_density"),
                                    ("pitch", "transpose"), ("velocity", "velocity_base"),
                                    ("duration", "gate"), ("accent", "velocity_accent")])
@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_relations_mark_destination_dimension_not_source(part, key, mode):
    engine, source, block = setup(mode)
    route = Relation(source.id, part, block.id, part, "Mix", .7)
    engine.project.relations = [route]
    assert not SourceSnapshot(engine).marks(source.id, key)
    marks = SourceSnapshot(engine).marks(block.id, key)
    assert [m.source for m in marks] == ["Relations"]
    assert "Output stream" in marks[0].details[0]
    for attr in ("enabled", "amount", "probability"):
        old = getattr(route, attr)
        setattr(route, attr, False if attr == "enabled" else 0.)
        assert not SourceSnapshot(engine).marks(block.id, key)
        setattr(route, attr, old)
    engine.project.relations.clear()
    assert not SourceSnapshot(engine).marks(block.id, key)


def test_individual_drum_voice_and_parent_bus_are_resolved_separately():
    engine, source, _ = setup()
    drum = Block(3, "Kit", "DRUM")
    ensure_drum_voices(drum)
    engine.project.blocks.append(drum)
    first, second = drum.drum_voices[:2]
    route = Relation(source.id, "rhythm", drum.id, "rhythm", "Copy", .8, destination_voice_id=first.id)
    engine.project.relations = [route]
    assert SourceSnapshot(engine).marks(first.id, "fill_density")
    assert not SourceSnapshot(engine).marks(second.id, "fill_density")
    assert not SourceSnapshot(engine).marks(drum.id, "kit_density")
    assert parameter_values(engine, first.id, "fill_density") is not None
    route.destination_voice_id = None
    assert "Drum bus" in SourceSnapshot(engine).marks(first.id, "fill_density")[0].details[0]
    assert SourceSnapshot(engine).marks(drum.id, "kit_density")


def test_kit_summary_observes_voice_composition_without_changing_kit_density():
    engine, _, _ = setup()
    drum = Block(3, "Kit", "DRUM")
    ensure_drum_voices(drum)
    engine.project.blocks.append(drum)
    engine.project.composition["enabled"] = True
    section = engine.project.composition["sections"][0]
    section["blocks"][str(drum.drum_voices[0].id)] = {"density": .3}
    marks = SourceSnapshot(engine).marks(drum.id, "kit_density")
    assert "KICK" in marks[0].details[0]
    assert "kit_density" not in drum.parameters


def test_three_sources_combine_without_duplicated_badges():
    engine, source, block = setup()
    engine.set_parameter(block, "fill_density", .7, source="Technique: density_drop")
    engine.project.composition["enabled"] = True
    engine.project.composition["sections"][0]["macros"]["density"] = .2
    engine.project.relations = [Relation(source.id, "rhythm", block.id, "rhythm", "Mix", .6),
                                Relation(source.id, "density", block.id, "density", "Copy", .2)]
    marks = SourceSnapshot(engine).marks(block.id, "fill_density")
    assert [m.source for m in marks] == ["Perform", "Composition", "Relations"]
    assert len(marks[2].details) == 2


def test_builtin_role_connections_and_harmonic_plan_are_not_mislabeled():
    engine, source, block = setup(block_type="BASS")
    drum = Block(3, "Kit", "DRUM")
    ensure_drum_voices(drum)
    engine.project.blocks.append(drum)
    assert "built-in Drum" in SourceSnapshot(engine).marks(block.id, "fill_density")[0].details[0]
    block.parameters.update(groove_follow=0., groove_accent=0.)
    assert not SourceSnapshot(engine).marks(block.id, "fill_density")
    engine.project.harmonic_plan = harmonic_preset()
    marks = SourceSnapshot(engine).marks(block.id, "role_center")
    assert marks[0].source == "Perform" and "Harmonic plan" in marks[0].details[0]
    block.parameters["harmonic_follow"] = False
    assert not SourceSnapshot(engine).marks(block.id, "role_center")


def test_dialogue_uses_both_participants_and_respects_disabled_routes():
    engine, source, block = setup()
    route = Relation(source.id, "pitch", block.id, "pitch", "Dialogue", 1.)
    engine.project.relations = [route]
    assert SourceSnapshot(engine).marks(source.id, "fill_density")[0].source == "Relations"
    assert "Dialogue" in SourceSnapshot(engine).marks(block.id, "transpose")[0].details[0]
    route.enabled = False
    assert not SourceSnapshot(engine).marks(block.id, "transpose")


def test_snapshot_never_generates_reconciles_or_advances_musical_state(monkeypatch):
    engine, source, block = setup()
    engine.project.harmonic_plan = harmonic_preset()
    engine.project.composition["enabled"] = True
    engine.set_parameter(block, "gate", .4, source="Technique: staccato")
    engine.project.relations = [Relation(source.id, "rhythm", block.id, "rhythm", "Copy", 1.)]
    before = deepcopy((engine.project, engine.parameter_influence.entries, engine.harmonic_runtime.__dict__,
                       engine.clock.__dict__))
    def unexpected(*args, **kwargs):
        pytest.fail("Attribution must not invoke a musical mutation")
    for method in ("generate", "regenerate", "set_parameter", "apply_relations"):
        monkeypatch.setattr(engine, method, unexpected)
    monkeypatch.setattr(engine.parameter_influence, "_reconcile", unexpected)
    for _ in range(3):
        snapshot = SourceSnapshot(engine)
        for key in ("gate", "fill_density", "transpose", "role_center", "harmonic_strength"):
            snapshot.marks(block.id, key)
            parameter_values(engine, block.id, key)
    after = (engine.project, engine.parameter_influence.entries, engine.harmonic_runtime.__dict__, engine.clock.__dict__)
    # Runtime dictionaries contain a project reference; compare only stable state.
    assert before[0] == after[0]
    assert before[1] == after[1]
    assert before[2]["_configuration"] == after[2]["_configuration"]
    assert before[2]["voicings"] == after[2]["voicings"]
    assert before[3] == after[3]
