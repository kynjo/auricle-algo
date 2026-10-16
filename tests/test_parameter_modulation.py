from auricle_core import Block, Process, Project, MusicEngine, save_project, load_project


def test_parameter_modulation_has_one_tick_latency():
    source = Block(1, "Source", "MELODY", "Pattern", "SEQ", parameters={"pattern": "1,1,1,1"})
    target = Block(2, "Target", "MELODY", "Probability", "SEQ", parameters={"probability": 0.25})
    source.processes = [Process("Parameter Modulation", "pitch", 1.0, {
        "destination_block": 2,
        "destination_parameter": "probability",
        "source_min": 0.0,
        "source_max": 1.0,
        "min": 0.0,
        "max": 1.0,
    })]
    engine = MusicEngine(Project(length=4, blocks=[source, target]))
    engine.generate()
    source.outputs["pitch"] = [1.0] * 4

    engine.collect_parameter_modulations(source, 0)
    assert target.parameters["probability"] == 0.25

    engine.apply_pending_parameter_modulations()
    assert target.parameters["probability"] == 1.0


def test_parameter_modulation_catalog_contains_real_generator_parameters():
    engine = MusicEngine(Project())
    assert "fill_density" in engine.parameter_catalog(Block(1, "x", "MELODY", "Probability"))
    assert "probability" in engine.parameter_catalog(Block(2, "x", "MELODY", "Probability"))
    assert "euclidean_rotation" in engine.parameter_catalog(Block(3, "x", "MELODY", "Euclidean"))
    assert "markov_transpose" in engine.parameter_catalog(Block(4, "x", "MELODY", "Markov"))
    assert "walk_step" in engine.parameter_catalog(Block(5, "x", "MELODY", "Random Walk"))
    assert "chaos_r" in engine.parameter_catalog(Block(6, "x", "MELODY", "Logistic Chaos"))


def test_parameter_modulation_serializes():
    import tempfile
    import os
    source = Block(1, "Source", "MELODY", "Pattern")
    target = Block(2, "Target", "MELODY", "Probability")
    source.processes = [Process("Parameter Modulation", "pitch", 0.5, {
        "destination_block": 2,
        "destination_parameter": "probability",
        "source_min": -1.0,
        "source_max": 1.0,
        "min": 0.0,
        "max": 1.0,
    })]
    project = Project(blocks=[source, target])
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        save_project(project, path)
        loaded = load_project(path)
        p = loaded.blocks[0].processes[0].parameters
        assert p["destination_block"] == 2
        assert p["destination_parameter"] == "probability"
    finally:
        os.unlink(path)
