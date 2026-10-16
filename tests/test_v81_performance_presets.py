from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auricle_core import Block, MusicEngine, Project, presets_for
from performance_presets import PerformancePreset, interpolate_preset, preset_for


def test_every_block_type_algorithm_pair_has_named_techniques():
    algorithms = [
        "Euclidean", "Bresenham", "Polyrhythm", "Thue-Morse", "Fibonacci Rhythm",
        "Fibonacci", "Recaman", "De Bruijn", "Markov", "Random Walk", "Interval Walker",
        "Scale Walker", "Weighted Scale", "Arpeggiator", "Probability", "Pattern",
        "Cellular Automaton", "L-System", "Logistic Chaos",
    ]
    for block_type in ("DRUM", "BASS", "MELODY", "PAD", "CHORD"):
        for algorithm in algorithms:
            items = presets_for(block_type, algorithm)
            assert items, (block_type, algorithm)
            assert all(isinstance(item, PerformancePreset) for item in items)
            assert len({item.id for item in items}) == len(items)


def test_interpolation_supports_all_shapes():
    preset = preset_for("MELODY", "Markov", "crescendo")
    for shape in ("in", "out", "in_out", "pulse"):
        values = interpolate_preset(preset, .5, 1.0, shape)
        assert values
        assert all(isinstance(v, float) for v in values.values())


def test_runtime_gesture_changes_seq_parameters_and_expires():
    project = Project(blocks=[Block(1, "DRUM", "DRUM", "Euclidean", "SEQ", 1, "", 60, {"pulses": 4})])
    engine = MusicEngine(project)
    block = project.blocks[0]
    assert engine.performance.start(block, "euclidean_fill", amount=1.0, beats=.25)
    state = engine.performance.active[block.id]
    state.elapsed_beats = .24
    engine.performance._last_time -= 0.2
    engine.performance.tick(True)
    assert block.parameters["pulses"] >= 4
    assert block.outputs
    assert block.id not in engine.performance.active


def test_performance_stop_is_model_safe():
    project = Project(blocks=[Block(1, "BASS", "BASS", "Random Walk")])
    engine = MusicEngine(project)
    assert engine.performance.start(project.blocks[0], "walk_drift")
    engine.performance.stop(1)
    assert 1 not in engine.performance.active
