from copy import deepcopy

import pytest

from auricle_core import Block, Project, MusicEngine, MusicalRepresentation
from generators import fibonacci_rhythm
from relation_context import analyze_groove


@pytest.mark.parametrize("length", [0, 1, 2, 3, 8, 16, 24, 31, 32, 64, 128])
def test_fibonacci_density_covers_the_whole_range_and_is_nested(length):
    previous = set()
    for hits in range(length + 1):
        rhythm = fibonacci_rhythm(length, hits / max(1, length))
        current = {i for i, hit in enumerate(rhythm) if hit}
        assert len(rhythm) == length and len(current) == hits
        assert previous <= current
        previous = current


@pytest.mark.parametrize("offset", [-31, -1, 0, 1, 8, 32, 97])
def test_fibonacci_offset_preserves_density_and_pattern(offset):
    base = fibonacci_rhythm(32, .75)
    shifted = fibonacci_rhythm(32, .75, offset)
    assert shifted == [base[(i - offset) % 32] for i in range(32)]


def test_groove_counts_eighth_offbeats_and_only_averages_active_accents():
    straight = analyze_groove([1, 0, 0, 0], [.8, 0, 0, 0])
    eighth = analyze_groove([0, 0, 1, 0], [0, 0, .8, 0])
    sixteenth = analyze_groove([0, 1, 0, 0], [0, .8, 0, 0])
    assert straight["accent"] == eighth["accent"] == sixteenth["accent"] == .8
    assert straight["syncopation"] == 0 < eighth["syncopation"] < sixteenth["syncopation"]
    assert analyze_groove([1, 0, 1, 0], [.6, 1, 1, 1])["accent"] == .8
    assert analyze_groove([0, 0], [1, 1])["accent"] == 0


def representation():
    return MusicalRepresentation([1, 0, 1], [0, 0, 0], [.6, 0, .6], [.8, 0, .8], [1, 0, 1], [0, 0, 0])


@pytest.mark.parametrize("role", ["BASS", "MELODY", "PAD", "CHORD"])
def test_groove_has_one_gain_stage_and_zero_follow_is_neutral(role):
    drum = Block(1, "Drum", "DRUM", mutators=[], outputs={"rhythm": [1, 0, 1, 0], "accent": [1, 0, 1, 0]})
    block = Block(2, role, role, parameters={"groove_follow": 0}, mutators=[])
    engine = MusicEngine(Project(blocks=[drum, block]))
    engine.update_musical_context()
    before = representation(); rep = deepcopy(before)
    engine._apply_relation_context(block, rep)
    engine._apply_groove_to_representation(block, rep)
    assert rep == before
    block.parameters["groove_follow"] = 1
    engine._apply_relation_context(block, rep)
    engine._apply_groove_to_representation(block, rep)
    groove = engine._groove_for_block(block)
    assert rep.velocity[0] == pytest.approx(.6 * (1 + (groove - .5) * .3))
    assert rep.duration[0] == pytest.approx(.8 * (1 - .18 * groove))
    assert rep.velocity[1] == 0


def test_no_drum_source_means_no_hidden_groove_gain_or_duration_change():
    block = Block(2, "Bass", "BASS", parameters={"groove_follow": 1}, mutators=[])
    engine = MusicEngine(Project(blocks=[block]))
    engine.update_musical_context()
    rep = representation(); before = deepcopy(rep)
    engine._apply_relation_context(block, rep)
    engine._apply_groove_to_representation(block, rep)
    assert rep == before
