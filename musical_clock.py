"""Transport-owned musical time, measured in quarter-note beats."""
from __future__ import annotations


class MusicalClock:
    def __init__(self, tempo=120):
        self.tempo = max(1.0, float(tempo))
        self.position_beats = 0.0
        self.running = False
        self._last_time = None

    def start(self, now, tempo):
        self.position_beats = 0.0
        self.tempo = max(1.0, float(tempo))
        self._last_time = float(now)
        self.running = True

    def advance(self, now, tempo=None):
        now = float(now)
        elapsed = 0.0
        if self.running and self._last_time is not None:
            elapsed = max(0.0, now - self._last_time) * self.tempo / 60.0
            self.position_beats += elapsed
        # A backwards timestamp must not make the same time count twice.
        self._last_time = max(now, self._last_time) if self._last_time is not None else now
        if tempo is not None:
            self.tempo = max(1.0, float(tempo))
        return elapsed

    def stop(self, now):
        elapsed = self.advance(now)
        self.running = False
        return elapsed

    def seconds_for_beats(self, beats):
        return float(beats) * 60.0 / self.tempo
