"""v101 Relations: shared musical state and rhythm-first relation defaults."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


def analyze_groove(rhythm, accents=None) -> dict[str, float]:
    """Summarize a drum pattern into a stable 0..1 groove signal."""
    values = [1.0 if float(v) > 0.0 else 0.0 for v in (rhythm or [])]
    if not values:
        return {"groove": 0.0, "density": 0.0, "syncopation": 0.0, "accent": 0.0}
    hits = [i for i, value in enumerate(values) if value]
    density = len(hits) / len(values)
    offbeat = sum(1 for i in hits if i % 4 in (1, 3)) / max(1, len(hits))
    accent_values = [float(v) for v in (accents or [])]
    accent = (sum(max(0.0, min(1.0, v)) for v in accent_values) /
              max(1, len(accent_values))) if accent_values else density
    # Density anchors the signal; offbeat activity and accents distinguish
    # straight, sparse and syncopated patterns without introducing randomness.
    groove = max(0.0, min(1.0, density * 0.55 + offbeat * 0.25 + accent * 0.20))
    return {"groove": groove, "density": density, "syncopation": offbeat, "accent": accent}


def analyze_harmony(rhythm, pitches=None) -> dict[str, float]:
    """Summarize chord activity into a stable MusicalContext harmony signal."""
    values = [1.0 if float(value) > 0.0 else 0.0 for value in (rhythm or [])]
    if not values:
        return {"harmony": 0.0, "density": 0.0, "changes": 0.0}
    active = [float(pitch) for pitch, value in zip(pitches or [], values) if value]
    changes = 0.0
    if len(active) > 1:
        changes = sum(1 for left, right in zip(active, active[1:])
                      if abs(left - right) > 1e-9) / max(1, len(active) - 1)
    density = sum(values) / len(values)
    harmony = max(0.0, min(1.0, density * 0.5 + (1.0 - changes) * 0.5))
    return {"harmony": harmony, "density": density, "changes": changes}

@dataclass
class MusicalContext:
    groove: float = 0.5
    harmony: float = 0.5
    energy: float = 0.5
    tension: float = 0.2
    density: float = 0.5
    motif_activity: float = 0.5
    rhythm_authority: str = "DRUM"
    values: dict[str, Any] = field(default_factory=dict)

    def snapshot(self):
        return asdict(self)

    def update_from_director(self, director_state):
        """Copy the Director envelope from either a mapping or its dataclass.

        MusicDirector.snapshot() returns PerformanceState, while older callers
        passed dictionaries.  The old ``dict``-only branch silently ignored
        the dataclass and froze the shared context at its defaults.
        """
        if isinstance(director_state, dict):
            get = director_state.get
        else:
            get = lambda name, default: getattr(director_state, name, default)
        self.energy = float(get("energy", self.energy))
        self.tension = float(get("tension", self.tension))

    def update_from_drum(self, rhythm, accents=None):
        metrics = analyze_groove(rhythm, accents)
        self.groove = metrics["groove"]
        self.density = metrics["density"]
        self.values["groove_metrics"] = metrics
        return metrics

    def update_from_chord(self, rhythm, pitches=None):
        metrics = analyze_harmony(rhythm, pitches)
        self.harmony = metrics["harmony"]
        self.values["harmony_metrics"] = metrics
        return metrics

RELATION_TEMPLATES = [
    ("DRUM", "BASS", "groove", "bias", 0.7),
    ("DRUM", "PERCUSSION", "groove", "bias", 0.8),
    ("DRUM", "MELODY", "rhythm", "bias", 0.35),
    ("CHORD", "PAD", "harmony", "hard", 0.85),
    ("CHORD", "MELODY", "harmony", "bias", 0.55),
    ("DIRECTOR", "ALL", "energy", "bias", 0.8),
]

def default_relations():
    return [{"source":s,"target":t,"channel":c,"mode":m,"strength":a}
            for s,t,c,m,a in RELATION_TEMPLATES]
