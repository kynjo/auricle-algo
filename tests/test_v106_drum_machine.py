"""Current Drum Machine container regressions."""

from auricle_core import (BLOCK_TYPES, Block, MusicEngine, Project, Relation,
                          Transport, ensure_drum_voices, load_project, save_project)


class CapturePort:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class App:
    def __init__(self, project):
        self.project = project
        self.engine = MusicEngine(project)

    def record_generated_event(self, *args):
        pass

    def log_midi_message(self, *args):
        pass

    def set_message(self, *args):
        pass


def drum_project(mode="SEQ"):
    drum = Block(1, "DRUM", "DRUM", "Euclidean", mode, midi_channel=1)
    ensure_drum_voices(drum)
    project = Project(length=16, blocks=[drum])
    return project, drum


def test_drum_container_materializes_independent_voices_and_parent_union():
    project, drum = drum_project("SEQ")
    engine = MusicEngine(project)
    engine.generate()
    assert [voice.name for voice in drum.drum_voices] == [
        "KICK", "SNARE", "CLOSED HAT", "OPEN HAT", "CLAP", "PERC"
    ]
    assert len({voice.midi_channel for voice in drum.drum_voices}) == 1
    assert all(not voice.midi_channel_override for voice in drum.drum_voices)
    assert len({voice.midi_note for voice in drum.drum_voices}) == 6
    assert len(drum.outputs["rhythm"]) == project.length
    assert any(value > 0 for value in drum.outputs["rhythm"])


def test_seq_voice_sends_its_own_channel_and_base_note():
    project, drum = drum_project("SEQ")
    engine = MusicEngine(project)
    engine.generate()
    voice = drum.drum_voices[0]
    app = App(project)
    transport = Transport(app)
    port = CapturePort()
    for step in range(project.length):
        transport._seq_event(voice, float(step), port)
        if any(message.type == "note_on" for message in port.messages):
            break
    note_ons = [message for message in port.messages if message.type == "note_on"]
    assert note_ons
    assert note_ons[0].channel == voice.midi_channel - 1
    assert note_ons[0].note == voice.midi_note


def test_drum_voice_channel_override_survives_parent_channel_change():
    project, drum = drum_project("SEQ")
    voice = drum.drum_voices[0]
    voice.midi_channel = 7
    voice.midi_channel_override = True
    drum.midi_channel = 3
    ensure_drum_voices(drum)
    assert voice.midi_channel == 7
    assert all(other.midi_channel == 3 for other in drum.drum_voices[1:])


def test_live_drum_voices_are_independent_transport_owners():
    project, drum = drum_project("LIVE")
    engine = MusicEngine(project)
    engine.generate()
    app = App(project)
    transport = Transport(app)
    playable = list(transport._playable_blocks())
    assert playable == drum.drum_voices
    assert len({voice.id for voice in playable}) == len(playable)
    assert all(voice.mode == "LIVE" for voice in playable)
    events = [engine.live_event(voice) for voice in playable]
    assert any(event is not None for event in events)


def test_percussion_is_removed_from_new_block_catalog():
    assert "PERCUSSION" not in BLOCK_TYPES


def test_parent_drum_union_remains_a_relation_source():
    drum = Block(1, "DRUM", "DRUM", "Euclidean", "SEQ")
    ensure_drum_voices(drum)
    bass = Block(2, "BASS", "BASS", "Pattern", "SEQ", parameters={
        "pattern": "1", "groove_follow": 0.0, "groove_accent": 0.0,
    })
    project = Project(length=16, blocks=[drum, bass], relations=[
        Relation(1, "rhythm", 2, "rhythm", "Copy", 1.0),
    ])
    engine = MusicEngine(project)
    engine.generate()
    assert drum.outputs["rhythm"]
    assert bass.outputs["rhythm"] == drum.outputs["rhythm"]


def test_drum_voice_name_roundtrips(tmp_path):
    drum = Block(1, "DRUM", "DRUM")
    ensure_drum_voices(drum)
    drum.drum_voices[0].name = "MAIN KICK"
    project = Project(blocks=[drum])
    path = tmp_path / "drum.json"
    save_project(project, str(path))
    loaded = load_project(str(path))
    assert loaded.blocks[0].drum_voices[0].name == "MAIN KICK"
