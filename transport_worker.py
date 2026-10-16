"""v106 transport scheduler with queue and look-ahead."""
from __future__ import annotations
import threading
import time
import logging
from transport_queue import TransportEventQueue

log = logging.getLogger("auricle.transport")

class TransportWorker:
    def __init__(self, transport, interval=0.002, lookahead=0.020):
        self.transport = transport
        self.interval = interval
        self.lookahead = lookahead
        self.queue = TransportEventQueue()
        self._stop = threading.Event()
        self._thread = None
        self._tick_id = 0
        self._last_planned = None
        self.error_count = 0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="AuricleTransport", daemon=True)
        self._thread.start()

    def schedule_tick(self, when):
        # Use the scheduled grid time as the idempotence key. ``round`` keeps
        # harmless floating-point drift from creating a second key for the
        # same musical tick.
        key = ("tick", round(float(when), 9))
        accepted = self.queue.push(when, self.transport.tick, key=key)
        if accepted:
            self._tick_id += 1
            self._last_planned = float(when)
        return accepted

    def _run(self):
        next_plan = time.monotonic()
        while not self._stop.is_set():
            now=time.monotonic()
            while next_plan < now + self.lookahead:
                self.schedule_tick(next_plan)
                next_plan += self.interval
            self._dispatch_due(now)
            self._stop.wait(min(self.interval,0.002))

    def _dispatch_due(self, now=None):
        """Run due callbacks while keeping the scheduler alive on failure."""
        for callback in self.queue.pop_due(now):
            try:
                callback()
            except Exception:
                self.error_count += 1
                log.exception("transport callback failed")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
            self._thread=None
