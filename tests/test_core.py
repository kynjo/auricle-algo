from auricle_core import GENERATORS, Block, MusicEngine, Project, Relation, load_project, save_project


def make_demo_project():
    p = Project()
    p.blocks = [
        Block(1, 'DRUM', 'DRUM', 'Euclidean', 'SEQ', 1, '', 60, {'pulses': 4, 'gate': .8}),
        Block(2, 'BASS', 'BASS', 'Random Walk', 'SEQ', 2, '', 60, {'gate': .7}),
        Block(3, 'MELODY', 'MELODY', 'Markov', 'LIVE', 3, '', 60,
              {'live_min_beats': .1, 'live_max_beats': .5, 'live_gate': .6}),
    ]
    p.relations = [
        Relation(1, 'rhythm', 2, 'rhythm', 'Modulate', .35),
        Relation(2, 'pitch', 3, 'pitch', 'Follow', .30),
    ]
    return p


def test_core_smoke():
    p = make_demo_project()
    e = MusicEngine(p)
    e.generate()
    assert len(p.blocks[0].outputs['rhythm']) == p.length
    assert len(p.blocks[1].outputs['pitch']) == p.length
    assert {'rhythm', 'pitch', 'velocity', 'duration', 'density', 'accent'} <= set(p.blocks[0].outputs)
    event = e.live_event(p.blocks[2])
    assert event is None or {'pitch', 'velocity', 'duration', 'interval', 'rhythm'} <= event.keys()


def test_every_block_gets_basic_pitch_stages_once():
    b = Block(99, 'TEST', 'MELODY', 'Markov', 'SEQ')
    names = [m.name for m in b.mutators]
    for stage in ('Transpose', 'Scale', 'Octave'):
        assert names.count(stage) == 1
    assert all(m.target == 'pitch' for m in b.mutators[-3:])


def test_fill_zero_silences_every_generator():
    for idx, algorithm in enumerate(GENERATORS, start=1000):
        p = Project(length=16, seed=77)
        b = Block(idx, algorithm, 'MELODY', algorithm, 'SEQ', 1, '', 60, {'fill_density': 0.0})
        p.blocks = [b]
        MusicEngine(p).generate()
        assert all(v == 0.0 for v in b.outputs['rhythm']), algorithm


def test_fill_one_keeps_events_for_pitch_generators():
    for idx, algorithm in enumerate(["Fibonacci", "Recaman", "Random Walk", "Scale Walker", "Weighted Scale",
                                     "Arpeggiator", "L-System", "Logistic Chaos"], start=2000):
        p = Project(length=16, seed=77)
        b = Block(idx, algorithm, 'MELODY', algorithm, 'SEQ', 1, '', 60, {'fill_density': 1.0})
        p.blocks = [b]
        MusicEngine(p).generate()
        assert any(v > 0 for v in b.outputs['rhythm']), algorithm


def test_project_block_colors_roundtrip(tmp_path):
    project = Project(block_colors={"DRUM": "#112233", "BASS": "#445566"})
    path = tmp_path / "colors.json"
    save_project(project, str(path))
    loaded = load_project(str(path))
    assert loaded.block_colors["DRUM"] == "#112233"
    assert loaded.block_colors["BASS"] == "#445566"


def test_live_event_reapplies_relations_to_seq_destination():
    p = Project(length=8, seed=17)
    source = Block(1, "LIVE", "MELODY", "Pattern", "LIVE", 1, "", 60,
                   {"pattern": "1", "pattern_scale": 1.0, "event_probability": 1.0, "fill_density": 1.0,
                    "live_min_beats": .2, "live_max_beats": .2})
    dest = Block(2, "DEST", "DRUM", "Euclidean", "SEQ", 2, "", 60, {"pulses": 2})
    p.blocks = [source, dest]
    p.relations = [Relation(1, "rhythm", 2, "rhythm", "Modulate", 1.0)]
    e = MusicEngine(p)
    e.generate()
    assert any(v == 0.0 for v in dest.outputs["rhythm"])
    event = e.live_event(source)
    assert event is not None
    assert all(v > 0.0 for v in dest.outputs["rhythm"])
    assert any(v == 2.0 for v in dest.outputs["rhythm"])


def test_reopen_port_releases_old_port_notes(monkeypatch):
    from auricle_core import Transport

    class FakePort:
        def __init__(self, name):
            self.name = name
            self.messages = []
            self.closed = False
        def send(self, message):
            self.messages.append(message)
        def close(self):
            self.closed = True

    class App:
        def __init__(self):
            self.project = Project()
            self.messages = []
        def set_message(self, message):
            self.messages.append(message)

    old = FakePort("old")
    new = FakePort("new")
    app = App()
    transport = Transport(app)
    transport.outputs["P"] = old
    transport.active_notes = [(999.0, old, 60, 0, 1)]
    monkeypatch.setattr("auricle_core.mido.open_output", lambda name: new)
    result = transport._reopen_port("P")
    assert result is new
    assert old.closed
    assert any(msg.type == "note_off" and msg.note == 60 and msg.channel == 0 for msg in old.messages)
    assert transport.active_notes == []
    assert transport.outputs["P"] is new


def test_seq_event_uses_rate_adjusted_note_interval():
    from auricle_core import Transport

    class App:
        def __init__(self):
            self.project = Project(tempo=120, length=4)
            self.messages = []
        def set_message(self, message):
            self.messages.append(message)

    app = App()
    b = Block(1, "B", "MELODY", "Pattern", "SEQ", 1, "", 60, {"pattern": "1,1,1,1", "timing_rate": 2.0})
    app.project.blocks = [b]
    app.engine = MusicEngine(app.project)
    app.engine.generate()
    transport = Transport(app)
    captured = []
    transport._send_event = lambda block, event, port, interval: captured.append(interval)
    transport._seq_event(b, 0.0, object())
    assert captured == [transport.seq_interval / 2.0]


def test_close_ports_releases_notes_before_closing():
    from auricle_core import Transport

    class FakePort:
        def __init__(self):
            self.messages = []
            self.closed = False
        def send(self, message):
            self.messages.append(message)
        def close(self):
            self.closed = True

    class App:
        def __init__(self):
            self.project = Project()
        def set_message(self, message):
            pass

    app = App()
    transport = Transport(app)
    port = FakePort()
    transport.outputs["P"] = port
    transport.active_notes = [(999.0, port, 64, 2, 1)]
    transport.close_ports()
    assert port.closed
    assert transport.active_notes == []
    assert any(msg.type == "note_off" and msg.note == 64 and msg.channel == 2 for msg in port.messages)



def test_identical_note_is_shared_between_block_owners():
    from auricle_core import Transport

    class FakePort:
        def __init__(self): self.messages = []
        def send(self, message): self.messages.append(message)

    class App:
        def __init__(self):
            self.project = Project(tempo=120)
            self.engine = MusicEngine(self.project)
            self.logged = []
        def set_message(self, message): pass
        def log_midi_message(self, block, port_name, message): self.logged.append(message)

    app = App(); port = FakePort(); t = Transport(app)
    b1 = Block(1, "A", "MELODY", "Pattern", "SEQ", 1, "P", 60, {"gate": 1.0})
    b2 = Block(2, "B", "MELODY", "Pattern", "SEQ", 1, "P", 60, {"gate": 1.0})
    t._send_event(b1, {"pitch": 0, "velocity": .8}, port, .5)
    t._send_event(b2, {"pitch": 0, "velocity": .8}, port, .5)
    assert [m.type for m in port.messages] == ["note_on", "note_on"]
    assert len(t.active_notes) == 2
    # Releasing one owner must not kill the other owner's identical note.
    t._release_block_notes(b1.id)
    assert [m.type for m in port.messages] == ["note_on", "note_on"]
    assert len(t.active_notes) == 1
    t._release_block_notes(b2.id)
    assert [m.type for m in port.messages] == ["note_on", "note_on", "note_off"]
    assert not t.active_notes


def test_stop_does_not_broadcast_cc123():
    from auricle_core import Transport

    class FakePort:
        def __init__(self): self.messages = []
        def send(self, message): self.messages.append(message)

    class App:
        def __init__(self): self.project = Project(); self.engine = MusicEngine(self.project)
        def set_message(self, message): pass
        def log_midi_message(self, block, port_name, message): pass

    app = App(); port = FakePort(); t = Transport(app); t.outputs["P"] = port
    t.stop()
    assert not any(m.type == "control_change" and m.control == 123 for m in port.messages)


def test_seq_event_records_generated_history():
    from auricle_core import Transport

    class FakePort:
        def send(self, message): pass

    class App:
        def __init__(self):
            self.project = Project(length=4)
            self.engine = MusicEngine(self.project)
            self.history = []
        def record_generated_event(self, block, event): self.history.append((block.id, dict(event)))
        def set_message(self, message): pass
        def log_midi_message(self, block, port_name, message): pass

    app = App()
    b = Block(1, "SEQ", "MELODY", "Pattern", "SEQ", 1, "P", 60, {"pattern": "1", "event_probability": 1.0})
    app.project.blocks = [b]; app.engine.generate()
    t = Transport(app)
    t._seq_event(b, 0.0, FakePort())
    assert app.history and app.history[0][0] == 1
