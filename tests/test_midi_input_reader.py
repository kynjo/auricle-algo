import threading

from midi_input_reader import read_input_loop


class FakeMessage:
    type = "control_change"
    channel = 0
    control = 74
    value = 96


class FakePort:
    def __init__(self):
        self.calls = 0

    def iter_pending(self):
        self.calls += 1
        if self.calls == 1:
            return [FakeMessage()]
        return []


def test_reader_drains_pending_messages_and_normalizes_cc():
    port = FakePort()
    stop = threading.Event()
    received = []

    def emit(event):
        received.append(event)
        stop.set()

    read_input_loop(port, emit, stop, poll_interval=0.0005)

    assert len(received) == 1
    assert received[0] == {
        "type": "cc", "channel": 0, "number": 74, "value": 96 / 127.0
    }


def test_reader_ignores_unsupported_midi_messages():
    class Unsupported:
        type = "clock"

    port = FakePort()
    port.iter_pending = lambda: [Unsupported()]
    stop = threading.Event()
    calls = []

    def emit(event):
        calls.append(event)
        stop.set()

    # Stop after one polling cycle without emitting an event.
    original_wait = stop.wait
    waits = {"n": 0}
    def wait(_interval):
        waits["n"] += 1
        stop.set()
        return original_wait(0)
    stop.wait = wait
    read_input_loop(port, emit, stop, poll_interval=0.0005)
    assert calls == []
