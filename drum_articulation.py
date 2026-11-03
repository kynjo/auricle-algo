"""Bounded, deterministic Ratchet/Flam expansion after a source hit is accepted.

Offsets and lengths are quarter-note beats. Flam is causal in SEQ and LIVE:
the grace starts on the source onset and the principal follows after Gap.
Only the first principal of a ratchet receives a flam (at most nine notes).
"""
from dataclasses import dataclass
import math

from auricle_drum import kit_random


ARTICULATION_PARAMETERS = {
    "drum_ratchet_probability": (0., 0., 1.),
    "drum_ratchet_count": (2, 1, 8),
    "drum_ratchet_spread": (1., .1, 1.),
    "drum_ratchet_decay": (.8, 0., 1.),
    "drum_flam_probability": (0., 0., 1.),
    "drum_flam_spacing": (.04, .01, .12),
    "drum_flam_velocity": (.45, .05, 1.),
}


def articulation_values(parameters):
    result = {}
    for key, (default, low, high) in ARTICULATION_PARAMETERS.items():
        try:
            value = float(parameters.get(key, default))
            if not math.isfinite(value):
                value = default
        except (TypeError, ValueError, OverflowError):
            value = default
        value = max(low, min(high, value))
        result[key] = int(round(value)) if isinstance(default, int) else float(value)
    return result


def supports_articulation(block):
    return (str(block.block_type).upper() in ("DRUM", "PERCUSSION")
            and not getattr(block, "drum_voices", None))


@dataclass(frozen=True)
class ArticulationHit:
    offset: float
    duration: float
    velocity: float
    kind: str = "main"


def articulate(event, parameters, seed):
    """Expand a canonical MusicalEvent; probabilities are drawn once per hit.

    Fixed source identity and absolute beat make decisions independent of
    voice order, cache regeneration and seeking. A rest is never expanded.
    """
    if event.rhythm <= 0 or event.velocity <= 0 or event.duration_beats <= 0:
        return ()
    values = articulation_values(parameters)
    owner = int(event.source_id or 0)
    pulse = int(round(event.beat * 1_000_000))
    seed = int(seed) + owner * 1009
    ratchet = kit_random(seed, pulse, 811) < values["drum_ratchet_probability"]
    flam = kit_random(seed, pulse, 812) < values["drum_flam_probability"]
    count = values["drum_ratchet_count"] if ratchet else 1
    interval = max(1e-6, event.interval_beats)
    spacing = interval * (values["drum_ratchet_spread"] if count > 1 else 1.) / count
    if count == 1 and not flam:
        return (ArticulationHit(0., event.duration_beats, event.velocity),)
    gap = min(values["drum_flam_spacing"], spacing * .45) if flam else 0.
    hits = []
    if flam:
        hits.append(ArticulationHit(0., min(event.duration_beats, gap * .5),
                                    event.velocity * values["drum_flam_velocity"], "grace"))
    for index in range(count):
        offset = gap if index == 0 else index * spacing
        next_offset = (index + 1) * spacing if index + 1 < count else interval
        duration = min(event.duration_beats, max(1e-6, next_offset - offset) * .8)
        velocity = event.velocity * values["drum_ratchet_decay"] ** index
        if velocity > 0:
            hits.append(ArticulationHit(offset, duration, velocity, "main" if index == 0 else "ratchet"))
    return tuple(hits)
