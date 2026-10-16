from types import SimpleNamespace

from auricle_core import Block, Transport

class CapturePort:
    def __init__(self):
        self.messages = []
    def send(self, message):
        self.messages.append(message)

class DummyApp:
    def __init__(self):
        self.project = SimpleNamespace(blocks=[])
        self.engine = SimpleNamespace()
    def log_midi_message(self, *args):
        pass
    def set_message(self, *args):
        pass

def test_existing_block_channel_is_used_immediately():
    app = DummyApp()
    transport = Transport(app)
    port = CapturePort()
    block = Block(id=1, name="Bass", block_type="BASS", midi_channel=1, midi_note=60)

    transport._send_event(block, {"pitch": 0, "velocity": 0.8}, port, 0.1)
    assert port.messages[-1].type == "note_on"
    assert port.messages[-1].channel == 0

    block.midi_channel = 7
    transport._send_event(block, {"pitch": 0, "velocity": 0.8}, port, 0.1)
    assert port.messages[-1].type == "note_on"
    assert port.messages[-1].channel == 6
