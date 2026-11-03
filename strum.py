"""Stateless strumming of accepted CHORD/PAD voicings, in quarter-note beats."""
from dataclasses import dataclass
import math
import random


STRUM_PARAMETERS = {
    "strum_probability": (0., 0., 1.),
    "strum_spacing": (.04, 0., .5),
    "strum_dynamics": (0., -1., 1.),
    "strum_humanize": (0., 0., 1.),
}
STRUM_DIRECTIONS = (("Up", "up"), ("Down", "down"),
                    ("Alternate · steps", "alternate"), ("Random", "random"))
STRUM_GATES = (("Shared end", "shared"), ("Per note", "per_note"))
STRUM_CHOICES = {"strum_direction": ("up", tuple(key for _, key in STRUM_DIRECTIONS)),
                 "strum_gate_mode": ("shared", tuple(key for _, key in STRUM_GATES))}


def supports_strum(block):
    return str(block.block_type).upper() in ("CHORD", "PAD")


def strum_values(parameters):
    values = {}
    for key, (default, low, high) in STRUM_PARAMETERS.items():
        try:
            value = float(parameters.get(key, default))
            if not math.isfinite(value):
                value = default
        except (TypeError, ValueError, OverflowError):
            value = default
        values[key] = max(low, min(high, value))
    for key, (default, choices) in STRUM_CHOICES.items():
        value = parameters.get(key, default)
        values[key] = value if value in choices else default
    return values


@dataclass(frozen=True)
class StrumHit:
    pitch: float
    offset: float
    duration: float
    velocity: float


def strum_hits(event, parameters, seed, note_for=None, source_step=None):
    """None bypasses exactly; otherwise return each physical note once.

    Probability is sampled once for the chord. Direction and humanization are
    repeatable at an absolute source beat, including after a seek. Alternate
    follows source-step parity (rests also advance the alternating pattern).
    """
    values = strum_values(parameters)
    if (values["strum_probability"] <= 0 or len(event.pitches) < 2
            or event.rhythm <= 0 or event.velocity <= 0 or event.duration_beats <= 0):
        return None
    rng = random.Random(int(seed) * 1_000_003 + int(event.source_id or 0) * 1009
                        + int(round(event.beat * 1_000_000)) * 9176)
    if rng.random() >= values["strum_probability"]:
        return None
    # Sort the actual MIDI notes, not unvoiced scale degrees. Clipped duplicate
    # pitches must not retrigger a wire note several times inside one chord.
    note_for = note_for or (lambda pitch: pitch)
    unique = {}
    for pitch in event.pitches:
        unique.setdefault(note_for(pitch), pitch)
    pitches = [unique[note] for note in sorted(unique)]
    direction = values["strum_direction"]
    step = max(1e-9, event.interval_beats)
    source_step = math.floor(event.beat / step + 1e-7) if source_step is None else int(source_step)
    if direction == "down" or direction == "alternate" and source_step % 2:
        pitches.reverse()
    elif direction == "random":
        rng.shuffle(pitches)
    count = len(pitches)
    if count == 1:
        return (StrumHit(pitches[0], 0., event.duration_beats, event.velocity),)
    available = min(step, event.duration_beats)
    limits = []
    for key in ("harmony_remaining_beats", "dialogue_remaining_beats"):
        try:
            value = float(event.extras.get(key, float("inf")))
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(value):
            limits.append(max(0., value))
    if limits:
        available = min(available, *limits)
    if available <= 1e-9:
        return ()
    spacing = min(values["strum_spacing"], available * .9 / (count - 1))
    hits = []
    for index, pitch in enumerate(pitches):
        offset = index * spacing
        if index and spacing:
            offset += rng.uniform(-.2, .2) * spacing * values["strum_humanize"]
            offset = min(available * .9, offset)
        position = 2. * index / (count - 1) - 1.
        velocity = event.velocity * (1. + .5 * values["strum_dynamics"] * position)
        velocity *= 1. + rng.uniform(-.1, .1) * values["strum_humanize"]
        duration = event.duration_beats
        if values["strum_gate_mode"] == "shared":
            duration -= offset
        if limits:
            duration = min(duration, min(limits) - offset)
        hits.append(StrumHit(pitch, offset, max(0., duration), max(.001, min(1., velocity))))
    return tuple(hits)
