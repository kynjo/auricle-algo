import threading

from auricle_engine import MusicEngine
from auricle_model import Project
from auricle_transport import Transport


class _App:
    def __init__(self):
        self.project = Project()
        self.engine = MusicEngine(self.project)

    def set_message(self, _message):
        pass


def test_transport_tick_does_not_wait_for_gui_state_lock():
    transport = Transport(_App())
    finished = threading.Event()
    transport._gui_lock.acquire()
    try:
        worker = threading.Thread(target=lambda: (transport.tick(), finished.set()))
        worker.start()
        assert finished.wait(0.5), "transport tick was blocked by GUI lock"
        worker.join(timeout=0.5)
    finally:
        transport._gui_lock.release()


def test_gui_state_lock_does_not_wait_for_transport_lock():
    transport = Transport(_App())
    acquired = threading.Event()
    transport._transport_lock.acquire()
    try:
        def take_gui_lock():
            with transport._gui_lock:
                acquired.set()
        worker = threading.Thread(target=take_gui_lock)
        worker.start()
        assert acquired.wait(0.5), "GUI lock was coupled to transport lock"
        worker.join(timeout=0.5)
    finally:
        transport._transport_lock.release()


def test_transport_commands_are_serialized_by_transport_lock():
    transport = Transport(_App())
    entered = threading.Event()
    transport._transport_lock.acquire()
    try:
        worker = threading.Thread(target=lambda: (transport.set_tempo(123), entered.set()))
        worker.start()
        assert not entered.wait(0.05)
        transport._transport_lock.release()
        assert entered.wait(0.5)
        worker.join(timeout=0.5)
    finally:
        # RLock is owned by this thread and is already released above.
        pass
