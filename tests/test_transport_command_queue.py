import threading

from auricle_engine import MusicEngine
from auricle_model import Block, Project
from auricle_transport import Transport
from transport_queue import TransportCommandQueue


class _App:
    def __init__(self):
        block = Block(1, "Lead", "MELODY", "Pattern", "SEQ", mutators=[])
        self.project = Project(blocks=[block])
        self.engine = MusicEngine(self.project)
        self.applied = []

    def set_message(self, _message):
        pass



def test_command_queue_coalesces_keyed_edits_and_preserves_fifo():
    queue = TransportCommandQueue()
    result = []
    queue.push(lambda: result.append("first"))
    queue.push(lambda: result.append("old"), key=("knob", 1))
    queue.push(lambda: result.append("last"), key=("knob", 1))
    queue.push(lambda: result.append("last-2"), key=("knob", 2))

    commands = queue.pop_all()
    for command in commands:
        command["callback"]()

    assert result == ["first", "last", "last-2"]
    assert len(queue) == 0


def test_transport_tick_drains_gui_commands_even_when_stopped():
    app = _App()
    transport = Transport(app)
    block = app.project.blocks[0]
    transport.enqueue_gui_command(
        lambda: block.parameters.__setitem__("test_value", 0.75),
        key=("test", block.id),
    )

    transport.tick()

    assert block.parameters["test_value"] == 0.75
    assert len(transport.gui_command_queue) == 0


def test_transport_queue_does_not_acquire_gui_lock():
    app = _App()
    transport = Transport(app)
    finished = threading.Event()
    transport.enqueue_gui_command(lambda: finished.set())

    transport._gui_lock.acquire()
    try:
        worker = threading.Thread(target=transport.tick)
        worker.start()
        assert finished.wait(0.5), "transport command drain waited for GUI lock"
        worker.join(timeout=0.5)
    finally:
        transport._gui_lock.release()


def test_transport_flush_applies_commands_before_save_boundary():
    app = _App()
    transport = Transport(app)
    block = app.project.blocks[0]
    transport.enqueue_gui_command(lambda: block.parameters.__setitem__("queued", 42))

    transport.flush_gui_commands(notify=False)

    assert block.parameters["queued"] == 42


def test_command_failure_does_not_discard_following_commands():
    app = _App()
    transport = Transport(app)
    values = []
    transport.enqueue_gui_command(lambda: (_ for _ in ()).throw(RuntimeError("bad command")))
    transport.enqueue_gui_command(lambda: values.append("ok"))

    transport.tick()

    assert values == ["ok"]
    assert transport.gui_command_errors == 1


def test_transport_emits_gui_notification_only_after_successful_command():
    app = _App()

    class _Signal:
        def __init__(self):
            self.items = []
        def emit(self, item):
            self.items.append(item)

    app._transport_command_applied_signal = _Signal()
    transport = Transport(app)
    payload = {"dirty": True, "block_id": 1}
    transport.enqueue_gui_command(lambda: None, notification=payload)
    transport.enqueue_gui_command(
        lambda: (_ for _ in ()).throw(RuntimeError("expected")),
        notification={"dirty": True},
    )

    transport.tick()

    assert app._transport_command_applied_signal.items == [payload]


def test_command_enqueued_during_drain_is_deferred_to_next_tick():
    app = _App()
    transport = Transport(app)
    values = []

    def first():
        values.append("first")
        transport.enqueue_gui_command(lambda: values.append("second"))

    transport.enqueue_gui_command(first)
    transport.tick()
    assert values == ["first"]
    transport.tick()
    assert values == ["first", "second"]
