from auricle_core import Block, MusicEngine, Project


def test_chord_expands_to_three_diatonic_voices():
    p = Project(root_note=60, scale="Major", length=4)
    b = Block(1, "CHORD", "CHORD", "Pattern", "SEQ", 1, "", 60,
              {"pattern": "1,1,1,1", "harmony_size": 3, "harmony_spread": 7})
    p.blocks = [b]
    e = MusicEngine(p)
    e.generate()
    # Musical representation remains one event per tick; MIDI expansion is
    # performed at the transport boundary.
    assert b.outputs["rhythm"][0] > 0
    assert e._chord_pitches(b, 0.0) == [-12.0, -8.0, -5.0]


def test_chord_transport_sends_multiple_notes_without_scalar_duplicate():
    from auricle_core import Transport

    class FakePort:
        def __init__(self): self.messages = []
        def send(self, message): self.messages.append(message)

    class App:
        def __init__(self):
            self.project = Project(root_note=60, scale="Major")
            self.project.blocks = []
            self.engine = MusicEngine(self.project)
        def set_message(self, message): pass
        def log_midi_message(self, *args): pass

    app = App()
    b = Block(1, "CHORD", "CHORD", "Pattern", "SEQ", 1, "", 60,
              {"harmony_size": 3, "harmony_spread": 7})
    app.project.blocks = [b]
    t = Transport(app)
    port = FakePort()
    t._send_event(b, {"pitch": 0.0, "pitches": [0.0, 4.0, 7.0], "velocity": .8}, port, .1)
    ons = [m for m in port.messages if m.type == "note_on"]
    assert [m.note for m in ons] == [60, 64, 67]
    assert len(ons) == 3
