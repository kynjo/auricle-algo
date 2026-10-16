import logging

from transport_queue import TransportEventQueue
from transport_worker import TransportWorker


class FakeTransport:
    def __init__(self):
        self.calls = 0

    def tick(self):
        self.calls += 1


def test_queue_deduplicates_a_tick_key():
    queue = TransportEventQueue()
    calls = []
    callback = lambda: calls.append(1)
    assert queue.push(1.0, callback, key=("tick", 1))
    assert not queue.push(1.0, callback, key=("tick", 1))
    assert len(queue) == 1
    for callback in queue.pop_due(1.0):
        callback()
    assert calls == [1]
    assert len(queue) == 0


def test_worker_schedule_tick_is_idempotent():
    worker = TransportWorker(FakeTransport(), interval=.01, lookahead=.02)
    assert worker.schedule_tick(10.0)
    assert not worker.schedule_tick(10.0)
    assert len(worker.queue) == 1
    assert worker._tick_id == 1


def test_worker_logs_callback_errors_and_continues(caplog):
    worker = TransportWorker(FakeTransport())
    def broken():
        raise RuntimeError("midi callback failed")
    worker.queue.push(0.0, broken, key=("broken", 1))
    with caplog.at_level(logging.ERROR, logger="auricle.transport"):
        worker._dispatch_due(0.0)
    assert worker.error_count == 1
    assert "transport callback failed" in caplog.text


def test_worker_plans_one_tick_per_bpm_grid_step():
    transport = FakeTransport()
    worker = TransportWorker(transport, interval=.125, lookahead=.5)
    for index in range(8):
        worker.schedule_tick(index * .125)
    assert len(worker.queue) == 8
    callbacks = worker.queue.pop_due(10.0)
    for callback in callbacks:
        callback()
    assert transport.calls == 8
