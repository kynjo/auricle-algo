from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auricle_core import Block, MusicEngine, Project


def test_phrase_stop_restores_exact_pre_phrase_snapshot():
    project = Project(blocks=[Block(1, "MELODY", "MELODY", "Markov", "SEQ", 1, "", 60, {
        "velocity_base": 0.63,
        "fill_density": 0.41,
        "custom_value": 17,
    })])
    engine = MusicEngine(project)
    block = project.blocks[0]
    assert engine.performance.start_phrase(project, "opening_bloom", [1], 1.0)
    engine.performance._last_time -= .2
    engine.performance.tick(True)
    assert block.parameters["velocity_base"] != 0.63
    engine.performance.stop_phrase("opening_bloom")
    assert "opening_bloom" in engine.performance.active_phrase_releases
    for _ in range(30):
        engine.performance._last_time -= .1
        engine.performance.tick(True)
    assert "opening_bloom" not in engine.performance.active_phrase_releases
    assert block.parameters["velocity_base"] == 0.63
    assert block.parameters["fill_density"] == 0.41
    assert block.parameters["custom_value"] == 17


def test_phrase_snapshot_does_not_get_rebased_by_runtime_changes():
    project = Project(blocks=[Block(1, "DRUM", "DRUM", "Euclidean", "SEQ", 1, "", 36, {
        "velocity_base": 0.52,
    })])
    engine = MusicEngine(project)
    block = project.blocks[0]
    assert engine.performance.start_phrase(project, "opening_bloom", [1], 1.0)
    original = engine.director.phrase.memory["snapshot"][1]["velocity_base"][1]
    assert original == 0.52
    block.parameters["velocity_base"] = 0.91
    engine.performance.stop_phrase("opening_bloom")
    for _ in range(30):
        engine.performance._last_time -= .1
        engine.performance.tick(True)
    assert block.parameters["velocity_base"] == 0.52
