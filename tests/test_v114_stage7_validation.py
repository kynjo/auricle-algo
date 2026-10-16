from auricle_core import Project, Block, MusicEngine, midi_note_for
from generators import quantize_to_scale, SCALE_INTERVALS


def test_major_keys_remain_in_scale_after_generation():
    for root in (60, 62, 67, 65, 69):
        project = Project(length=64, root_note=root, scale="Major")
        engine = MusicEngine(project)
        block = Block(1, "Scale Walker", "MELODY", "Scale Walker", "SEQ")
        project.blocks = [block]
        engine.generate_block(block)
        allowed = set(SCALE_INTERVALS["Major"])
        # Check what is actually sent: generated pitches are offsets from the
        # root and MIDI adds the key (the old check compared offsets with the
        # absolute root and hid wrong notes in non-C keys).
        notes = [midi_note_for(project, block, v) for r, v in zip(block.outputs["rhythm"], block.outputs["pitch"]) if r > 0]
        assert notes and all((n - root) % 12 in allowed for n in notes)


def test_quantize_non_c_root():
    for root in (62, 67, 69):
        for note in range(40, 90):
            q = quantize_to_scale(note, root, "Major")
            assert int(q - root) % 12 in SCALE_INTERVALS["Major"]


def test_live_generation_produces_events_after_validation_pipeline():
    project = Project(length=16, root_note=62, scale="Major")
    engine = MusicEngine(project)
    block = Block(1, "Live Walker", "MELODY", "Scale Walker", "LIVE")
    project.blocks = [block]
    engine.reset_live()
    events = [engine.live_event(block) for _ in range(32)]
    assert any(event is not None for event in events)
