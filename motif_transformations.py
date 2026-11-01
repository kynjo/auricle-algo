"""Non-destructive, deterministic transformations for reusable Auricle motifs.

The source Motif is never modified. Each operation returns detached event
arrays and records its lineage so transformed material can be saved as a new
library entry without losing the original theme.
"""
from __future__ import annotations

from dataclasses import replace
import math
import random

from generators import scale_intervals
from motif_development import bounded


TRANSFORMATIONS = (
    ("Transpose", "transpose"),
    ("Invert contour", "invert"),
    ("Retrograde", "retrograde"),
    ("Reverse pitch", "retrograde_pitch"),
    ("Rhythm rotate", "rhythm_rotate"),
    ("Augment", "augment"),
    ("Diminish", "diminish"),
    ("Fragment", "fragment"),
    ("Repeat", "repeat"),
    ("Accent shift", "accent_shift"),
    ("Embellish", "embellish"),
    ("Rhythm invert", "rhythm_invert"),
)

TRANSFORM_DEFAULTS = {
    "transpose": 1.0, "invert": 1.0, "retrograde": 1.0,
    "retrograde_pitch": 1.0, "rhythm_rotate": 1.0,
    "augment": 2.0, "diminish": 2.0, "fragment": .5,
    "repeat": 2.0, "accent_shift": 1.0, "embellish": .35,
    "rhythm_invert": 1.0,
}

PITCH_TRANSFORMS = {"transpose", "invert", "retrograde_pitch"}


def transformations_for_role(role):
    role = str(role or "MELODY").upper()
    if role == "DRUM":
        return tuple(item for item in TRANSFORMATIONS if item[1] not in PITCH_TRANSFORMS)
    return TRANSFORMATIONS


def _arrays(motif):
    count = max(1, int(motif.steps))
    notes = [float(motif.notes[i % len(motif.notes)]) if motif.notes else 0.0 for i in range(count)]
    rhythm = [float(motif.rhythm[i % len(motif.rhythm)] > 0) if motif.rhythm else 1.0 for i in range(count)]
    velocity = [bounded(motif.velocity[i % len(motif.velocity)], .72, 0.0, 1.0)
                if motif.velocity else .72 for i in range(count)]
    velocity = [velocity[i] if rhythm[i] else 0.0 for i in range(count)]
    return notes, rhythm, velocity


def _scale_degree_pitch(note, degrees, scale):
    intervals = scale_intervals(scale) or list(range(12))
    count = len(intervals)
    octave = math.floor(float(note) / 12.0)
    index = min(range(count), key=lambda i: (abs(octave * 12 + intervals[i] - note), i))
    target = octave * count + index + int(degrees)
    target_octave, target_index = divmod(target, count)
    return float(target_octave * 12 + intervals[target_index])


def _quantize(note, scale):
    intervals = scale_intervals(scale) or list(range(12))
    octave = math.floor(float(note) / 12.0)
    candidates = [oct * 12 + interval
                  for oct in range(octave - 1, octave + 2) for interval in intervals]
    return float(min(candidates, key=lambda value: (abs(value - note), value)))


def _rotate(values, offset):
    if not values:
        return values
    offset = int(offset) % len(values)
    return values[-offset:] + values[:-offset] if offset else values[:]


def transform_motif(motif, operation, amount=1.0, scale="Chromatic", seed=0):
    """Return a transformed copy of ``motif``.

    ``amount`` is interpreted per operation: scale degrees for transpose,
    semitone-axis contour inversion strength, grid slots for rotations,
    duration factor for augment/diminish, fraction for fragment, repeat count
    for repeat, and probability/intensity for embellish/accent operations.
    """
    operation = str(operation or "").strip().lower()
    valid = {key for _, key in TRANSFORMATIONS}
    if operation not in valid:
        raise ValueError(f"Unknown motif transformation: {operation}")
    amount = float(amount)
    if not math.isfinite(amount):
        raise ValueError("Motif transformation amount must be finite")
    notes, rhythm, velocity = _arrays(motif)
    step_beats = float(motif.step_duration())
    role = str(motif.role).upper()
    rng = random.Random(int(seed))

    if operation == "transpose":
        if role == "DRUM":
            raise ValueError("Pitch transpose is not available for DRUM motifs")
        degrees = max(-24, min(24, int(round(amount))))
        notes = [_scale_degree_pitch(note, degrees, scale) for note in notes]

    elif operation == "invert":
        if role == "DRUM":
            raise ValueError("Pitch inversion is not available for DRUM motifs")
        attacks = [note for note, hit in zip(notes, rhythm) if hit]
        pivot = attacks[0] if attacks else (sum(notes) / len(notes) if notes else 0.0)
        strength = bounded(abs(amount), 1.0, 0.0, 2.0)
        notes = [_quantize(pivot + (pivot - note) * strength, scale) for note in notes]

    elif operation == "retrograde":
        notes.reverse(); rhythm.reverse(); velocity.reverse()

    elif operation == "retrograde_pitch":
        if role == "DRUM":
            raise ValueError("Pitch retrograde is not available for DRUM motifs")
        notes.reverse()

    elif operation == "rhythm_rotate":
        offset = max(-len(rhythm), min(len(rhythm), int(round(amount))))
        notes = _rotate(notes, offset)
        rhythm = _rotate(rhythm, offset)
        velocity = _rotate(velocity, offset)

    elif operation == "augment":
        factor = bounded(abs(amount), 2.0, 1.0, 16.0)
        step_beats = min(16.0, step_beats * factor)

    elif operation == "diminish":
        factor = bounded(abs(amount), 2.0, 1.0, 16.0)
        step_beats = max(.0625, step_beats / factor)

    elif operation == "fragment":
        fraction = bounded(abs(amount), .5, .125, 1.0)
        keep = max(1, min(len(notes), int(round(len(notes) * fraction))))
        start = rng.randrange(0, len(notes) - keep + 1) if keep < len(notes) else 0
        end = start + keep
        notes, rhythm, velocity = notes[start:end], rhythm[start:end], velocity[start:end]

    elif operation == "repeat":
        repeats = max(2, min(8, int(round(abs(amount)))))
        notes *= repeats
        rhythm *= repeats
        velocity *= repeats

    elif operation == "accent_shift":
        offset = max(-len(velocity), min(len(velocity), int(round(amount))))
        velocity = _rotate(velocity, offset)
        velocity = [bounded(value, .72, 0.0, 1.0) if hit else 0.0
                    for value, hit in zip(velocity, rhythm)]

    elif operation == "embellish":
        probability = bounded(abs(amount), .35, 0.0, 1.0)
        hits = [i for i, hit in enumerate(rhythm) if hit]
        for i, hit in enumerate(rhythm):
            # Ornament weak slots only; retain the first/last event and never
            # fill every rest at once.
            if not hit and i not in (0, len(rhythm) - 1) and rng.random() < probability:
                rhythm[i] = 1.0
                if role == "DRUM":
                    velocity[i] = max(.18, min(.48, (velocity[hits[i % len(hits)]] * .45) if hits else .32))
                else:
                    source = hits[i % len(hits)] if hits else 0
                    notes[i] = _scale_degree_pitch(notes[source], 1 if i % 2 else -1, scale)
                    velocity[i] = max(.22, min(.55, velocity[source] * .55 if hits else .38))

    elif operation == "rhythm_invert":
        rhythm = [0.0 if hit else 1.0 for hit in rhythm]
        # Do not produce a completely silent motif when the source has at
        # least one event. Restore its first authored attack as the anchor.
        if any(_arrays(motif)[1]) and not any(rhythm):
            rhythm[0] = 1.0
        velocity = [max(.25, min(.65, velocity[i] * .72 if velocity[i] else .42)) if hit else 0.0
                    for i, hit in enumerate(rhythm)]

    # Normalize and detach all arrays; rests never carry a sounding velocity.
    rhythm = [1.0 if value > 0 else 0.0 for value in rhythm]
    velocity = [bounded(value, .72, 0.0, 1.0) if rhythm[i] else 0.0
                for i, value in enumerate(velocity)]
    lineage = dict(getattr(motif, "variations", {}) or {})
    lineage["last_transform"] = {
        "operation": operation, "amount": amount, "scale": str(scale),
        "seed": int(seed), "source_id": str(motif.id),
    }
    return replace(motif, notes=notes, rhythm=rhythm, velocity=velocity,
                   step_beats=step_beats, variations=lineage,
                   parent_id=str(motif.id), transformation=operation,
                   transform_amount=amount)
