import random

from auricle_core import Block, GENERATORS, MusicEngine, Project, save_project, load_project
from generators import cellular_automaton
from experimental_generators import (
    cellular_automaton_evolved,
    geometry_collision,
    lsystem_sequence_extended,
    orbital_sequence,
    turing_machine,
)


def test_experimental_generators_are_registered():
    assert {"Turing Machine", "Orbital Sequence", "Geometry Collision"}.issubset(GENERATORS)


def test_turing_machine_presets_are_deterministic_and_bounded():
    for preset in ("Busy Beaver", "Alternator", "Growth", "Marbles"):
        first = turing_machine(64, preset=preset, rng=random.Random(123))
        second = turing_machine(64, preset=preset, rng=random.Random(123))
        assert first == second
        assert len(first) == 64
        assert set(first).issubset({0.0, 1.0})
        assert any(first), preset


def test_turing_pitch_mode_uses_explicit_rests_and_scale_notes():
    result = turing_machine(64, preset="Alternator", mode="Pitch", scale_name="Dorian",
                            rng=random.Random(8))
    allowed = {0, 2, 3, 5, 7, 9, 10}
    assert any(value is None for value in result)
    assert all(value is None or round(value) % 12 in allowed for value in result)


def test_orbital_sequence_combination_and_pitch_rest_semantics():
    a = orbital_sequence(64, cycle_a=8, cycle_b=5, combine="A")
    b = orbital_sequence(64, cycle_a=8, cycle_b=5, combine="B")
    both = orbital_sequence(64, cycle_a=8, cycle_b=5, combine="AND")
    union = orbital_sequence(64, cycle_a=8, cycle_b=5, combine="OR")
    interlock = orbital_sequence(64, cycle_a=8, cycle_b=5, combine="Interlock")
    assert sum(both) <= min(sum(a), sum(b))
    assert sum(union) >= max(sum(a), sum(b))
    assert interlock != orbital_sequence(64, cycle_a=8, cycle_b=5, combine="XOR")
    pitch = orbital_sequence(64, output="Pitch", combine="XOR", scale_name="Minor")
    assert any(value is None for value in pitch)
    assert any(value is not None for value in pitch)


def test_geometry_collision_generates_repeatable_box_and_circle_material():
    for shape in ("Box", "Triangle", "Hexagon", "Circle"):
        first = geometry_collision(64, shape=shape, rng=random.Random(777))
        second = geometry_collision(64, shape=shape, rng=random.Random(777))
        assert first == second
        assert len(first) == 64
        assert set(first).issubset({0.0, 1.0})
        assert any(first), shape
        pitch = geometry_collision(64, shape=shape, mode="Pitch", scale_name="Dorian",
                                    rng=random.Random(777))
        allowed = {0, 2, 3, 5, 7, 9, 10}
        assert any(value is None for value in pitch)
        assert all(value is None or round(value) % 12 in allowed for value in pitch)


def test_cellular_automaton_evolution_modes_and_pitch_rests():
    final = cellular_automaton_evolved(32, generations=2, evolution="Final Row", rng=random.Random(4))
    legacy = cellular_automaton(32, rule=30, seed="00100000", generations=2,
                                mode="Rhythm", density=1.0, rng=random.Random(4))
    assert final == legacy
    trail = cellular_automaton_evolved(32, evolution="Evolution Trail", rng=random.Random(4))
    xor = cellular_automaton_evolved(32, evolution="XOR Trail", rng=random.Random(4))
    assert len(final) == len(trail) == len(xor) == 32
    assert trail != final
    pitch = cellular_automaton_evolved(32, mode="Pitch", evolution="Evolution Trail",
                                       rng=random.Random(4))
    assert any(value is None for value in pitch)
    assert any(value is not None for value in pitch)


def test_l_system_turtle_modes_handle_branch_commands():
    rhythm = lsystem_sequence_extended(32, axiom="A", rule_a="A[+B]A", rule_b="B[-A]B",
                                       iterations=2, mode="Turtle Rhythm")
    pitch = lsystem_sequence_extended(32, axiom="A", rule_a="A[+B]A", rule_b="B[-A]B",
                                      iterations=2, mode="Turtle Pitch")
    assert len(rhythm) == len(pitch) == 32
    assert set(rhythm).issubset({0.0, 1.0})
    assert any(value is None for value in pitch)
    assert any(value is not None for value in pitch)


def test_all_new_generators_run_in_seq_and_live():
    project = Project(length=32, root_note=60, scale="Dorian")
    engine = MusicEngine(project)
    for idx, name in enumerate(("Turing Machine", "Orbital Sequence", "Geometry Collision"), 101):
        block = Block(idx, name, "MELODY", name, "SEQ")
        project.blocks = [block]
        engine.generate_block(block)
        assert len(block.outputs["rhythm"]) == project.length
        assert len(block.outputs["pitch"]) == project.length
        block.mode = "LIVE"
        engine.reset_live()
        events = [engine.live_event(block) for _ in range(64)]
        assert any(event is not None for event in events), name


def test_every_registered_generator_still_generates_seq_material():
    project = Project(length=24, root_note=60, scale="Minor")
    engine = MusicEngine(project)
    for idx, name in enumerate(GENERATORS, 1):
        block = Block(idx, name, "MELODY", name, "SEQ")
        project.blocks = [block]
        engine.generate_block(block)
        assert len(block.outputs["rhythm"]) == project.length, name
        assert len(block.outputs["pitch"]) == project.length, name


def test_experimental_generator_parameters_survive_project_roundtrip(tmp_path):
    project = Project(length=32, root_note=60, scale="Dorian")
    block = Block(901, "Orbit", "MELODY", "Orbital Sequence", "SEQ")
    block.parameters.update({"orbit_cycle_a": 13, "orbit_cycle_b": 7, "orbit_mode": "Interlock",
                             "orbit_output": "Pitch", "orbit_phase_a": 2})
    project.blocks = [block]
    path = tmp_path / "experimental-project.json"
    save_project(project, str(path))
    restored = load_project(str(path))
    loaded = restored.blocks[0]
    assert loaded.algorithm == "Orbital Sequence"
    assert loaded.parameters["orbit_cycle_a"] == 13
    assert loaded.parameters["orbit_cycle_b"] == 7
    assert loaded.parameters["orbit_mode"] == "Interlock"
    assert loaded.parameters["orbit_output"] == "Pitch"
    assert loaded.parameters["orbit_phase_a"] == 2
