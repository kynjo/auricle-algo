from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auricle_core import Block, MusicEngine, Project
from performance_presets import PerformancePhrase, PhraseStage, phrase_for, phrases, phrase_techniques


def test_phrase_catalog_is_composed_and_role_aware():
    items = phrases()
    assert len(items) >= 5
    assert all(isinstance(p, PerformancePhrase) and p.stages for p in items)
    phrase = phrase_for("climax_release")
    assert phrase is not None
    assert phrase.total_beats == 15
    for block_type in ("DRUM", "BASS", "MELODY", "PAD", "CHORD"):
        ids = phrase_techniques(phrase, block_type)
        assert len(ids) == len(phrase.stages)


def test_phrase_runtime_stages_across_multiple_blocks():
    project = Project(blocks=[
        Block(1, "DRUM", "DRUM", "Euclidean", "SEQ", 1, "", 36, {"pulses": 4}),
        Block(2, "MELODY", "MELODY", "Markov", "SEQ", 1, "", 60, {"markov_leap": .1}),
        Block(3, "PAD", "PAD", "Weighted Scale", "SEQ", 1, "", 48, {}),
    ])
    engine = MusicEngine(project)
    assert engine.performance.start_phrase(project, "climax_release", [1, 2, 3], 1.0)
    state = engine.director.phrase
    assert state.phrase_id == "climax_release" and state.stage_index == -1
    engine.performance._last_time -= .2
    engine.performance.tick(True)
    assert state.stage_index == 0
    assert engine.performance.active
    # Move into the third stage without relying on wall-clock precision.
    state.position_beats = 5.2
    engine.performance.tick(True)
    assert state.stage_index == 2
    assert 1 in engine.performance.active and 2 in engine.performance.active


def test_phrase_can_be_stopped_without_leaking_active_techniques():
    project = Project(blocks=[Block(1, "BASS", "BASS", "Random Walk")])
    engine = MusicEngine(project)
    assert engine.performance.start_phrase(project, "breath", [1])
    engine.performance._last_time -= .2
    engine.performance.tick(True)
    assert 1 in engine.performance.active
    engine.performance.stop_phrase("breath")
    assert not engine.director.phrase.running
    assert 1 not in engine.performance.active


def test_phrase_stage_is_immutable_data():
    stage = PhraseStage("crescendo", 4, .8, "in", "Crescendo")
    assert stage.technique_id == "crescendo"
    assert stage.beats == 4
