"""Contracts at the data, engine, LIVE and editable UI boundaries."""
from copy import deepcopy
import random

import pytest

from auricle_core import Block, Project, MusicEngine, Mutator, MusicalRepresentation, GENERATORS
from mutators import MUTATORS, TARGETS, mutate_sequence, mutators_for_target


def mutate(values, name, amount, target, strength=1):
    return mutate_sequence(values, Mutator(name, amount, target), random.Random(47), strength=strength)


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("name", MUTATORS)
def test_types_and_master_bypass(target, name):
    values = {"rhythm": [1, 0, 0, 1, 0, 1, 0, 0], "pitch": [-12, 0, 2, 7, 9, 12, 17, 24],
              "velocity": [0, .2, .4, .6, .8, 1, .3, 0], "timing": [0, .2, .4, .6, .8, 1, 1.5, 0]}[target]
    assert mutate(values, name, .9, target, 0) == values
    for amount in (0, .01, .5, 1):
        result = mutate(values, name, amount, target)
        assert len(result) == len(values)
        if name not in mutators_for_target(target):
            assert result == values
        if target == "rhythm":
            assert set(result) <= {0., 1.}
        elif target != "pitch":
            assert all(0 <= v <= (1.5 if target == "timing" else 1) for v in result)


@pytest.mark.parametrize("name", ["Transpose", "Octave", "Scale"])
def test_master_intensity_keeps_neutral_point_and_direction(name):
    values = [-12, 0, 7, 24]
    for strength in (0, .01, .25, .5, 1):
        assert mutate(values, name, .5, "pitch", strength) == values
    for amount in (.1, .9):
        full = mutate(values, name, amount, "pitch")
        half = mutate(values, name, amount, "pitch", .5)
        assert half == pytest.approx([(old + new) / 2 for old, new in zip(values, full)])


def test_rhythm_intensity_is_probabilistic_not_fractional_and_invert_can_create_hits():
    values = [0.] * 4096
    counts = [sum(mutate(values, "Invert", 1, "rhythm", strength)) for strength in (0, .01, .25, .5, 1)]
    assert counts == sorted(counts)
    assert counts[0] == 0 and counts[-1] == len(values) and counts[1] < 100


@pytest.mark.parametrize("n", [1, 2, 3, 7, 8, 16, 31, 32])
def test_full_mirror_is_a_palindrome(n):
    values = list(range(n))
    result = mutate(values, "Mirror", 1, "pitch")
    assert result == result[::-1]
    assert result[:(n + 1) // 2] == values[:(n + 1) // 2]
    assert mutate(values, "Mirror", 0, "pitch") == values


def test_compress_repeats_the_shortened_motif_instead_of_holding_its_last_note():
    assert mutate([0, 1, 2, 3, 4, 5, 6, 7], "Compress", 1 / 3, "pitch") == [0, 2, 4, 6, 0, 2, 4, 6]


def test_normalized_threshold_and_humanize_have_target_units():
    assert mutate([0, .2, .4, .6, .8, 1], "Threshold", .5, "velocity") == [0, 0, 0, .6, .8, 1]
    assert mutate([0, .6, .9, 1.5], "Threshold", .5, "timing") == [0, 0, .9, 1.5]
    assert any(mutate([0.] * 20, "Humanize", 1, "pitch"))  # tonic is a note
    for target in ("velocity", "timing"):
        assert mutate([0.] * 20, "Humanize", 1, target) == [0.] * 20
        assert max(abs(v - .5) for v in mutate([.5] * 100, "Humanize", 1, target)) <= .18


def block_for(role="MELODY", mode="SEQ", mutators=(), **parameters):
    return Block(1, role, role, "Pattern", mode, mutators=list(mutators), parameters={
        "pattern": "1,0,2,0,0,5,0,0", "velocity_base": .6, "velocity_range": 0,
        "velocity_accent": 0, "velocity_random": 0, "gate": .8, "live_gate": .8,
        "fill_density": 1, "role_duration": 1, "role_root_bias": 0,
        "groove_follow": 0, "groove_accent": 0, "harmony_anchor": 0, **parameters})


def output(block, count=8):
    engine = MusicEngine(Project(length=count, blocks=[block], scale="Chromatic"))
    if block.mode == "SEQ":
        engine.generate_block(block)
        return deepcopy(block.outputs)
    result = {part: [] for part in ("rhythm", "pitch", "velocity", "duration", "density", "accent")}
    for i in range(count):
        engine.live_event(block, beat=i * .25)
        for part in result:
            result[part].append(block.outputs[part][0])
    return result


@pytest.mark.parametrize("role", ["DRUM", "BASS", "MELODY", "CHORD", "PAD"])
@pytest.mark.parametrize("name,amount", [("Rotate", .25), ("Reverse", 1), ("Invert", 1), ("Stretch", .7),
                                        ("Compress", .3), ("Mirror", 1), ("Mutate", 1), ("Probability", 0)])
def test_rhythm_transform_is_audible_and_equal_across_seq_live(role, name, amount):
    results = [output(block_for(role, mode, [Mutator(name, amount, "rhythm")])) for mode in ("SEQ", "LIVE")]
    assert results[0]["rhythm"] == results[1]["rhythm"]
    expected = mutate([1, 0, 1, 0, 0, 1, 0, 0], name, amount, "rhythm")
    assert results[0]["rhythm"] == expected
    for result in results:
        assert all(v > 0 and d > 0 for r, v, d in zip(result["rhythm"], result["velocity"], result["duration"]) if r)


@pytest.mark.parametrize("role", ["DRUM", "BASS", "MELODY", "CHORD", "PAD"])
@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("target", ["velocity", "timing"])
def test_explicit_zero_is_never_replaced_by_a_default_gate(role, mode, target):
    result = output(block_for(role, mode, [Mutator("Probability", 0, target)]))
    assert not any(result["rhythm"])
    assert not any(result["velocity"])
    assert not any(result["duration"])


def test_pitch_window_reverse_uses_neighbours_in_live_and_is_repeatable():
    block = block_for(mutators=[Mutator("Reverse", 1, "pitch")], pattern="1,2,3,4,5,6,7,8")
    a = output(block)
    block.mode = "LIVE"
    b = output(block)
    assert a["pitch"] == b["pitch"] == [8, 7, 6, 5, 4, 3, 2, 1]
    assert output(block) == b


def test_mutators_do_not_change_input_in_place_or_revive_closed_gates():
    rep = MusicalRepresentation([1, 0], [0, 2], [0, 0], [0, 0], [0, 0], [0, 0])
    block = block_for(mutators=[Mutator("Transpose", .5, "pitch")])
    engine = MusicEngine(Project(blocks=[block]))
    engine._apply_representation_mutators(block, rep, random.Random(1))
    assert rep.rhythm == [0, 0] and rep.duration == [0, 0]


@pytest.mark.parametrize("name,amount,target", [
    ("Rotate", 0, "rhythm"), ("Reverse", 0, "pitch"), ("Mirror", 0, "velocity"),
    ("Probability", 1, "rhythm"), ("Octave", 1, "rhythm"), ("Scale", .5, "velocity"),
    ("Stretch", 0, "timing"), ("Invert", 0, "pitch"), ("Shuffle", 0, "rhythm")])
def test_neutral_and_invalid_mutators_preserve_the_native_live_stream(name, amount, target):
    block = block_for(mode="LIVE")
    block.algorithm = "Random Walk"
    before = output(block, 32)
    block.mutators = [Mutator(name, amount, target)]
    assert output(block, 32) == before
    rng = random.Random(10); state = rng.getstate()
    mutate_sequence([0, 1, 0, 1], block.mutators[0], rng)
    assert rng.getstate() == state


@pytest.mark.parametrize("algorithm", GENERATORS)
def test_each_generator_supports_live_sequence_mutations_and_restarts(algorithm):
    block = block_for(mode="LIVE", mutators=[Mutator("Rotate", .25, "rhythm"), Mutator("Mirror", 1, "pitch")])
    block.algorithm = algorithm
    first = output(block, 32)
    assert output(block, 32) == first
    assert set(first["rhythm"]) <= {0., 1.}
    assert all(0 <= v <= 1 for v in first["velocity"])
    assert all(0 <= v <= 1.5 for v in first["duration"])
