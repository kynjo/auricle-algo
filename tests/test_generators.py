from auricle_core import (
    GENERATORS, Project, Block, MusicEngine,
)


def test_all_generators_seq():
    project = Project(length=32, root_note=60, scale="Dorian")
    engine = MusicEngine(project)
    for idx, name in enumerate(GENERATORS, 1):
        block = Block(idx, name, "MELODY", name, "SEQ")
        project.blocks = [block]
        engine.generate_block(block)
        assert len(block.outputs["pitch"]) == project.length, name
        assert len(block.outputs["rhythm"]) == project.length, name


def test_all_generators_live():
    project = Project(length=16, root_note=60, scale="Minor")
    engine = MusicEngine(project)
    for idx, name in enumerate(GENERATORS, 1):
        block = Block(idx, name, "MELODY", name, "LIVE")
        project.blocks = [block]
        engine.reset_live()
        events = [engine.live_event(block) for _ in range(24)]
        assert any(event is not None for event in events), name


def test_scale_generators_stay_quantized():
    project = Project(length=16, root_note=60, scale="Dorian")
    engine = MusicEngine(project)
    for idx, name in enumerate(("Fibonacci", "Recaman", "Scale Walker", "Weighted Scale", "Arpeggiator", "Logistic Chaos"), 1):
        block = Block(idx, name, "MELODY", name, "SEQ")
        project.blocks = [block]
        engine.generate_block(block)
        dorian = {0, 2, 3, 5, 7, 9, 10}
        assert all(round(v) % 12 in dorian for v in block.outputs["pitch"]), name


def test_expanded_scale_catalog_and_quantization():
    from auricle_core import SCALES
    from generators import SCALE_INTERVALS, quantize_to_scale
    assert len(SCALES) == 27
    expected = {
        "Locrian", "Harmonic Minor", "Melodic Minor", "Whole Tone",
        "Diminished HW", "Diminished WH", "Chromatic", "Bebop Dominant",
        "Hungarian Minor", "Double Harmonic Major", "Neapolitan Minor", "Japanese",
    }
    assert expected.issubset(SCALES)
    for name in SCALES:
        intervals = SCALE_INTERVALS[name]
        assert intervals == sorted(set(intervals))
        assert intervals[0] == 0 and intervals[-1] < 12
        for note in range(36, 84):
            q = int(quantize_to_scale(note, 60, name))
            assert (q - 60) % 12 in intervals
