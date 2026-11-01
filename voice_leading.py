"""Voice leading utilities for Auricle v100."""
from __future__ import annotations

from dataclasses import dataclass
import math
from itertools import product

@dataclass
class Voice:
    name: str
    pitch: float

class VoiceLeading:
    """Small deterministic solver that smooths melodic/harmonic movement."""
    def __init__(self, max_leap: float = 7.0, smoothness: float = 0.6):
        self.max_leap = float(max_leap)
        # Public contract:
        # 0.0 = free movement (keep the closest harmonic target)
        # 1.0 = maximum smoothing (follow the resolved voice path).
        # Clamp here so UI, presets and projects cannot invert the meaning.
        self.smoothness = max(0.0, min(1.0, float(smoothness)))
        self.previous: dict[str, float] = {}

    def reset(self):
        self.previous.clear()

    @staticmethod
    def resolve_chord(notes, previous=None, *, register=None):
        """Place distinct chord voices, preserving pitch classes and inversion.

        Keep an authored voicing when an octave translation fits the register.
        Otherwise fold voices by octaves, keeping their pitch-class order.
        If the requested width cannot contain the chord, choose the smallest
        overhang; never clip several voices to a shared register boundary.
        """
        notes = sorted(int(round(note)) for note in notes)
        if not notes: return []
        # Small scales can stack the same pitch class twice; an inversion
        # must keep those as separate octaves, never as duplicate MIDI notes.
        for i in range(1, len(notes)):
            while notes[i] <= notes[i-1]: notes[i] += 12
        low_octave = math.ceil(-notes[0] / 12)
        high_octave = math.floor((127-notes[-1]) / 12)
        candidates = [[note + 12*octave for note in notes] for octave in range(low_octave, high_octave+1)]
        candidates = [chord for chord in candidates if len(set(chord)) == len(chord)]
        reference = sorted(previous or notes)
        lo, hi = register if register is not None else (0, 127)
        lo, hi = max(0, min(127, lo)), max(0, min(127, hi))
        def score(chord):
            return (
            max(0, lo-chord[0], chord[-1]-hi),
            sum(max(0, lo-note, note-hi) for note in chord),
            sum(abs(note-reference[min(i, len(reference)-1)]) for i, note in enumerate(chord)),
            sum(abs((b-a)-(d-c)) for a,b,c,d in zip(chord, chord[1:], notes, notes[1:])), tuple(chord))
        fitting = [chord for chord in candidates if lo <= chord[0] and chord[-1] <= hi]
        if fitting: return min(fitting, key=score)
        lower, upper = max(0, math.floor(lo)-24), min(127, math.ceil(hi)+24)
        options = [[n for n in range(lower, upper+1) if n % 12 == note % 12] for note in notes]
        for chord in product(*options):
            if all(a < b for a,b in zip(chord, chord[1:])):
                candidates.append(list(chord))
        return min(candidates, key=score)

    def resolve_pitch(self, voice: str, target: float) -> float:
        """Resolve one note of a voice.

        0.0 returns the target unchanged.  Higher values prefer the octave of
        the target that is closest to the previous note and tighten the leap
        limit (24 st at 0 -> ``max_leap`` at 1).  No fractional blending: the
        old ``old*(1-s) + best*s`` froze the voice at s=0 and produced pitches
        between scale steps.
        """
        target = float(target)
        s = max(0.0, min(1.0, float(self.smoothness)))
        old = self.previous.get(voice)
        if old is None or s <= 0.0:
            self.previous[voice] = target
            return target
        candidates = [target + 12.0 * n for n in range(-4, 5)]
        best = min(candidates, key=lambda x: (s * abs(x - old) + (1.0 - s) * abs(x - target), abs(x - target)))
        limit = self.max_leap + (24.0 - self.max_leap) * (1.0 - s)
        if abs(best - old) > limit:
            best = old + max(-limit, min(limit, best - old))
        self.previous[voice] = best
        return best

    def process_sequence(self, sequence: list[float], voice="main") -> list[float]:
        return [self.resolve_pitch(voice, p) for p in sequence]
