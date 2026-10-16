from pathlib import Path
from auricle_core import Block, MusicEngine, Project, Transport, apply_role_defaults

class FakePort:
    def __init__(self): self.messages=[]
    def send(self, message): self.messages.append(message)

class FakeApp:
    def __init__(self, block):
        self.project=Project(root_note=60, scale="Major", length=4, blocks=[block])
        self.engine=MusicEngine(self.project)
    def set_message(self, _message): pass
    def log_midi_message(self, *_args): pass
    def record_generated_event(self, *_args): pass

def harmonic_block(role, mode="SEQ"):
    b=Block(1, role, role, "Pattern", mode, 3, "fake", 60, {
        "pattern":"1,1,1,1", "event_probability":1.0, "fill_density":1.0,
        "harmony_size":3, "harmony_spread":7,
    })
    apply_role_defaults(b)
    return b

def test_pad_and_chord_seq_events_emit_polyphonic_midi():
    for role in ("PAD","CHORD"):
        b=harmonic_block(role)
        app=FakeApp(b); app.engine.generate()
        transport=Transport(app); port=FakePort()
        transport._seq_event(b, 0.0, port)
        ons=[m for m in port.messages if m.type=="note_on"]
        assert len(ons)==3, (role, port.messages)
        assert all(m.channel==2 for m in ons)

def test_pad_and_chord_live_events_have_voicing_and_send():
    for role in ("PAD","CHORD"):
        b=harmonic_block(role, "LIVE")
        app=FakeApp(b)
        event=None
        for _ in range(16):
            event=app.engine.live_event(b)
            if event is not None: break
        assert event is not None, role
        assert len(event.get("pitches", []))==3
        transport=Transport(app); port=FakePort()
        transport._send_event(b,event,port,float(event.get("interval",.1)))
        assert len([m for m in port.messages if m.type=="note_on"])==3

def test_seq_harmonic_path_uses_app_engine_not_missing_transport_engine():
    source=(Path(__file__).resolve().parents[1]/"auricle_transport.py").read_text(encoding="utf-8")
    start=source.index("    def _seq_event")
    end=source.index("    def tick",start)
    block=source[start:end]
    assert 'event["pitches"] = engine._chord_pitches' in block
    assert 'self.engine._chord_pitches' not in block

def test_channel_setter_syncs_visible_card_immediately():
    source=(Path(__file__).resolve().parents[1]/"auricle_gui.py").read_text(encoding="utf-8")
    start=source.index("    def _set_channel")
    end=source.index("    def _set_note",start)
    block=source[start:end]
    assert "b.midi_channel = max(1, min(16, int(value)))" in block
    assert "self._sync_block_card(b)" in block
    assert block.index("self._sync_block_card(b)") < block.index("self._queue_inspector_refresh")
