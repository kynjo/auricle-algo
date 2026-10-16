"""Voice leading utilities for Auricle v100."""
from __future__ import annotations

from dataclasses import dataclass

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
