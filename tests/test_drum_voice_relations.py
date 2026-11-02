"""Relations can address concrete Drum Machine voices."""

from auricle_core import Block, MusicEngine, Project, Relation, ensure_drum_voices
from auricle_relations import validate_relations


def _kit(mode="SEQ"):
    drum = Block(1, "KIT", "DRUM", "Euclidean", mode)
    ensure_drum_voices(drum)
    for voice in drum.drum_voices[:2]:
        voice.algorithm = "Pattern"
        voice.parameters.update(pattern="1,0", fill_density=1.0)
    return drum


def test_seq_voice_to_voice_relation_uses_child_stream():
    drum = _kit()
    source, destination = drum.drum_voices[:2]
    source.parameters["pattern"] = "1,0,0,0"
    destination.parameters["pattern"] = "0,0,1,0"
    project = Project(length=4, blocks=[drum], relations=[
        Relation(drum.id, "rhythm", drum.id, "rhythm", "Copy", 1.0,
                 source_voice_id=source.id, destination_voice_id=destination.id),
    ])
    engine = MusicEngine(project)
    engine.generate()
    assert destination.outputs["rhythm"] == [1.0, 0.0, 0.0, 0.0]


def test_voice_route_can_drive_an_ordinary_block():
    drum = _kit()
    source = drum.drum_voices[0]
    source.parameters["pattern"] = "1,0,0,0"
    bass = Block(2, "BASS", "BASS", "Pattern", "SEQ", mutators=[], parameters={
        "pattern": "0,1,0,1", "groove_follow": 0.0, "groove_accent": 0.0,
    })
    project = Project(length=4, blocks=[drum, bass], relations=[
        Relation(drum.id, "rhythm", bass.id, "rhythm", "Copy", 1.0,
                 source_voice_id=source.id),
    ])
    engine = MusicEngine(project)
    engine.generate()
    assert bass.outputs["rhythm"] == [1.0, 0.0, 0.0, 0.0]


def test_live_voice_route_is_applied_to_the_current_voice_event():
    drum = _kit("LIVE")
    source, destination = drum.drum_voices[:2]
    relation = Relation(drum.id, "rhythm", drum.id, "rhythm", "Copy", 1.0,
                        source_voice_id=source.id, destination_voice_id=destination.id)
    engine = MusicEngine(Project(length=4, blocks=[drum], relations=[relation]))
    engine.generate()
    engine.relation_runtime.begin_tick()
    assert engine.live_event(source) is not None
    assert engine.live_event(destination) is not None
    engine.relation_runtime.end_tick()


def test_voice_relation_validation_checks_parent_ownership():
    first = _kit()
    second = Block(2, "KIT 2", "DRUM", "Euclidean", "SEQ")
    ensure_drum_voices(second)
    relation = Relation(first.id, "rhythm", second.id, "rhythm", "Copy", 1.0,
                        source_voice_id=first.drum_voices[0].id,
                        destination_voice_id=first.drum_voices[0].id)
    issues = validate_relations(Project(blocks=[first, second], relations=[relation]))
    assert any("destination drum voice belongs" in message for _, message in issues)
