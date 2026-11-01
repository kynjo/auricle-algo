"""Shared musical clock and beat-grid primitives.

All musical positions are expressed in quarter-note beats.  Wall-clock seconds
are converted only at the transport boundary; generators, phrases and events
share absolute beat positions.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

_EPSILON = 1e-9


def _finite(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return result if math.isfinite(result) else float(default)


@dataclass(frozen=True)
class MusicalPosition:
    """A beat position expressed in absolute and bar-relative coordinates."""

    absolute_beats: float
    bar_index: int
    beat_in_bar: float
    beats_per_bar: float
    step_index: int = 0
    step_in_bar: int = 0
    step_phase: float = 0.0

    @property
    def bar_number(self) -> int:
        """Human-facing, one-based bar number."""
        return self.bar_index + 1


@dataclass(frozen=True)
class MusicalGrid:
    """A reusable grid for converting absolute beats to discrete musical slots.

    ``step_beats`` is always measured in quarter-note beats.  A sixteenth-note
    grid therefore uses 0.25 regardless of the time signature.  ``origin``
    allows a phrase or section to establish its own grid without changing the
    project's absolute clock.
    """

    step_beats: float = 0.25
    origin_beats: float = 0.0
    beats_per_bar: float = 4.0

    def __post_init__(self):
        step = _finite(self.step_beats, 0.25)
        origin = _finite(self.origin_beats, 0.0)
        bar = _finite(self.beats_per_bar, 4.0)
        object.__setattr__(self, "step_beats", max(1e-6, step))
        object.__setattr__(self, "origin_beats", origin)
        object.__setattr__(self, "beats_per_bar", max(1e-6, bar))

    @classmethod
    def from_meter(cls, numerator=4, denominator=4, step_beats=0.25, origin_beats=0.0):
        """Build a grid from a conventional time signature (e.g. 6/8 = 3 beats)."""
        numerator = max(1, int(numerator))
        denominator = max(1, int(denominator))
        beats_per_bar = numerator * 4.0 / denominator
        return cls(step_beats=step_beats, origin_beats=origin_beats,
                   beats_per_bar=beats_per_bar)

    @staticmethod
    def _round_slot(value: float, mode: str) -> int:
        if mode == "floor":
            return math.floor(value + _EPSILON)
        if mode == "ceil":
            return math.ceil(value - _EPSILON)
        if mode == "nearest":
            return math.floor(value + 0.5 + _EPSILON)
        raise ValueError("mode must be 'floor', 'ceil' or 'nearest'")

    @property
    def steps_per_bar(self) -> float:
        return self.beats_per_bar / self.step_beats

    def slot_at(self, beat: float, mode: str = "floor") -> int:
        """Return the grid slot containing, following or nearest ``beat``."""
        relative = (_finite(beat) - self.origin_beats) / self.step_beats
        return self._round_slot(relative, mode)

    def beat_at(self, slot: int) -> float:
        """Return the absolute beat at the start of an integer slot."""
        return self.origin_beats + int(slot) * self.step_beats

    def quantize(self, beat: float, mode: str = "nearest") -> float:
        """Snap an absolute beat position to this grid."""
        return self.beat_at(self.slot_at(beat, mode))

    def cycle_index(self, beat: float, slots_per_cycle: int) -> int:
        """Return the zero-based cycle containing ``beat``."""
        slots = max(1, int(slots_per_cycle))
        cycle_beats = self.step_beats * slots
        return math.floor((_finite(beat) - self.origin_beats) / cycle_beats + _EPSILON)

    def cycle_origin(self, beat: float, slots_per_cycle: int) -> float:
        """Return the absolute beat at the start of the containing cycle."""
        slots = max(1, int(slots_per_cycle))
        return self.origin_beats + self.cycle_index(beat, slots) * slots * self.step_beats

    def position_at(self, beat: float) -> MusicalPosition:
        """Describe a beat in bars and grid slots using this grid's meter."""
        absolute = _finite(beat)
        relative = absolute - self.origin_beats
        bar_index = math.floor(relative / self.beats_per_bar + _EPSILON)
        beat_in_bar = relative - bar_index * self.beats_per_bar
        if abs(beat_in_bar) < _EPSILON:
            beat_in_bar = 0.0
        slot_value = relative / self.step_beats
        slot_index = math.floor(slot_value + _EPSILON)
        step_in_bar = math.floor(beat_in_bar / self.step_beats + _EPSILON)
        phase = slot_value - slot_index
        if abs(phase) < _EPSILON:
            phase = 0.0
        return MusicalPosition(
            absolute_beats=absolute,
            bar_index=bar_index,
            beat_in_bar=beat_in_bar,
            beats_per_bar=self.beats_per_bar,
            step_index=slot_index,
            step_in_bar=step_in_bar,
            step_phase=phase,
        )


class MusicalClock:
    """Transport-owned musical time, measured in quarter-note beats."""

    def __init__(self, tempo=120):
        self.tempo = max(1.0, _finite(tempo, 120.0))
        self.position_beats = 0.0
        self.running = False
        self._last_time = None

    def start(self, now, tempo):
        self.position_beats = 0.0
        self.tempo = max(1.0, _finite(tempo, 120.0))
        self._last_time = _finite(now)
        self.running = True

    def advance(self, now, tempo=None):
        now = _finite(now, self._last_time if self._last_time is not None else 0.0)
        elapsed = 0.0
        if self.running and self._last_time is not None:
            elapsed = max(0.0, now - self._last_time) * self.tempo / 60.0
            self.position_beats += elapsed
        # A backwards timestamp must not make the same time count twice.
        self._last_time = max(now, self._last_time) if self._last_time is not None else now
        if tempo is not None:
            self.tempo = max(1.0, _finite(tempo, self.tempo))
        return elapsed

    def seek(self, beats, now):
        """Move the shared clock without replaying skipped wall-clock time."""
        self.position_beats = max(0.0, _finite(beats))
        self._last_time = _finite(now)

    def stop(self, now):
        elapsed = self.advance(now)
        self.running = False
        return elapsed

    def seconds_for_beats(self, beats, tempo=None):
        """Convert quarter-note beats to seconds at the selected/current BPM."""
        bpm = max(1.0, _finite(self.tempo if tempo is None else tempo, self.tempo))
        return _finite(beats) * 60.0 / bpm

    def beats_for_seconds(self, seconds, tempo=None):
        """Convert seconds to quarter-note beats at the selected/current BPM."""
        bpm = max(1.0, _finite(self.tempo if tempo is None else tempo, self.tempo))
        return _finite(seconds) * bpm / 60.0

    def grid(self, step_beats=0.25, *, meter=(4, 4), origin_beats=0.0) -> MusicalGrid:
        """Create a grid anchored to the project's current beat convention."""
        numerator, denominator = meter
        return MusicalGrid.from_meter(numerator, denominator, step_beats, origin_beats)

    def musical_position(self, meter=(4, 4), step_beats=0.25) -> MusicalPosition:
        """Return the current position in bar-relative and subdivision terms."""
        return self.grid(step_beats, meter=meter).position_at(self.position_beats)
