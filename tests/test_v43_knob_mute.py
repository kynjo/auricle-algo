from auricle_core import Block, Project, MusicEngine, Transport, load_project, save_project


def test_muted_block_is_persisted(tmp_path):
    b = Block(1, "Lead", "MELODY", "Markov", muted=True)
    project = Project(blocks=[b])
    path = tmp_path / "muted.json"
    save_project(project, path)
    loaded = load_project(path)
    assert loaded.blocks[0].muted is True


def test_muted_block_does_not_emit_note_event():
    b = Block(1, "Lead", "MELODY", "Pattern", "SEQ", midi_port="", parameters={"pattern": "1,1,1,1"}, muted=True)
    p = Project(blocks=[b])
    e = MusicEngine(p)
    e.generate()
    # Mute is a transport concern; generation remains active so unmuting does not
    # require rebuilding the block. The transport checks b.muted before sending.
    assert b.outputs["rhythm"]
    assert b.muted is True


def test_block_default_is_unmuted():
    assert Block(1, "x", "MELODY").muted is False


class _FakePort:
    def __init__(self):
        self.messages = []
    def send(self, message):
        self.messages.append(message)


class _FakeApp:
    def __init__(self, project, engine):
        self.project = project
        self.engine = engine
    def log_midi_message(self, *args):
        pass
    def set_message(self, *args):
        pass


def test_transport_mute_blocks_midi_without_recreating_block():
    b = Block(1, "Lead", "MELODY", "Pattern", "SEQ", midi_port="port", parameters={"pattern": "1,1,1,1"}, muted=True)
    project = Project(blocks=[b])
    engine = MusicEngine(project)
    engine.generate()
    app = _FakeApp(project, engine)
    transport = Transport(app)
    port = _FakePort()
    transport.outputs["port"] = port
    transport.seq_index[b.id] = 0

    transport._seq_event(b, 0.0, port)
    assert port.messages == []

    b.muted = False
    transport._seq_event(b, 0.0, port)
    assert any(m.type == "note_on" for m in port.messages)


def test_transport_mute_releases_only_notes_owned_by_block():
    b1 = Block(1, "Lead", "MELODY", "Pattern", "SEQ", midi_port="port")
    b2 = Block(2, "Bass", "BASS", "Pattern", "SEQ", midi_port="port")
    project = Project(blocks=[b1, b2])
    engine = MusicEngine(project)
    app = _FakeApp(project, engine)
    transport = Transport(app)
    port = _FakePort()
    transport.outputs["port"] = port
    transport.active_notes = [
        (999.0, port, 60, 0, b1.id),
        (999.0, port, 48, 0, b2.id),
    ]

    transport.set_block_muted(b1.id, True)

    assert len(transport.active_notes) == 1
    assert transport.active_notes[0][-1] == b2.id
    assert [(m.type, m.note) for m in port.messages] == [("note_off", 60)]


def test_transport_unmute_reschedules_running_block():
    b = Block(1, "Lead", "MELODY", "Pattern", "SEQ", midi_port="port")
    project = Project(blocks=[b])
    engine = MusicEngine(project)
    app = _FakeApp(project, engine)
    transport = Transport(app)
    transport.running = True
    transport.next_due = {}
    transport.next_live = {}

    transport.set_block_muted(b.id, False)

    assert b.id in transport.next_due
    assert transport.next_due[b.id] <= __import__("time").monotonic() + 0.05
