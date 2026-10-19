"""Bounded, repeatable motif development from an immutable source theme.

Only musical cycle boundaries commit pending settings. No mutation depends on
worker tick frequency, regeneration count, MIDI routing or a block's mode.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import random

from generators import scale_intervals
from motif_engine import Motif


MODES = (("Off", "off"), ("Melodic", "melodic"),
         ("Rhythmic", "rhythmic"), ("Combined", "combined"))


def bounded(value, default, lo, hi):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = default
    return max(lo, min(hi, value)) if math.isfinite(value) else default


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def settings(parameters):
    mode = str(parameters.get("motif_development", "off"))
    return {
        "mode": mode if mode in dict((v, k) for k, v in MODES) else "off",
        "amount": bounded(parameters.get("motif_amount", .35), .35, 0, 1),
        "every": int(bounded(parameters.get("motif_every", 1), 1, 1, 16)),
        "return": int(bounded(parameters.get("motif_return", 4), 4, 2, 16)),
        "hold": parameters.get("motif_hold"),
    }


def anchor_slots(motif, step):
    """Protect strong-beat hits/rests, first/last attacks and authored accents."""
    hits = [i for i in range(motif.steps)
            if not motif.rhythm or motif.rhythm[i % len(motif.rhythm)] > 0]
    anchors = {i for i in range(motif.steps) if abs(i * step / 2 - round(i * step / 2)) < 1e-7}
    if hits:
        anchors.update((hits[0], hits[-1]))
    anchors.update(i for i in hits if motif.velocity and motif.velocity[i % len(motif.velocity)] >= .85)
    return anchors


@dataclass(frozen=True)
class MotifVariant:
    motif: Motif
    cycle: int
    generation: int
    label: str
    token: str
    settings_key: str


def develop(motif, cycle, step, config, scale, seed):
    """Produce one variant from the original, never from the previous variant."""
    generation = cycle // config["every"]
    label = "Theme" if generation == 0 else "Return"
    # Always make detached lists; snapshots/holds must never alias the theme.
    notes = [float(motif.notes[i % len(motif.notes)]) if motif.notes else 0.0 for i in range(motif.steps)]
    rhythm = [float(motif.rhythm[i % len(motif.rhythm)] > 0) if motif.rhythm else 1.0 for i in range(motif.steps)]
    velocity = [float(motif.velocity[i % len(motif.velocity)]) if motif.velocity else .72 for i in range(motif.steps)]
    original = (notes[:], rhythm[:], velocity[:])
    mode, amount = config["mode"], config["amount"]
    hold = config["hold"]
    held = False
    if isinstance(hold, dict) and hold.get("source_id") == motif.id:
        data = hold.get("material", {})
        arrays = [data.get(key) for key in ("notes", "rhythm", "velocity")]
        if all(isinstance(a, list) and len(a) == motif.steps and
               all(isinstance(x, (int, float)) and math.isfinite(x) for x in a) for a in arrays):
            notes, rhythm, velocity = [list(a) for a in arrays]
            label = "Held · " + str(hold.get("label", "variant"))
            held = True
    if not held and mode != "off" and amount > 0 and generation % config["return"] and any(rhythm):
        anchors = anchor_slots(motif, step)
        seed_key = digest((int(seed), motif.id, generation, scale))
        rng = random.Random(int(seed_key[:16], 16))
        pitched = str(motif.role).upper() != "DRUM"
        # One or two neighbouring scale degrees, limited to half the mutable
        # attacks even at maximum Amount. Stable priority order as Amount grows.
        if pitched and mode in ("melodic", "combined"):
            candidates = [i for i, hit in enumerate(rhythm) if hit and i not in anchors]
            rng.shuffle(candidates)
            count = min(len(candidates), math.ceil(len(candidates) * amount * .5))
            intervals = scale_intervals(scale)
            for i in candidates[:count]:
                octave = math.floor(notes[i] / 12)
                degrees = [(octave + o) * len(intervals) + j for o in (-1, 0, 1) for j in range(len(intervals))]
                to_pitch = lambda d: 12 * (d // len(intervals)) + intervals[d % len(intervals)]
                degree = min(degrees, key=lambda d: (abs(to_pitch(d) - notes[i]), to_pitch(d)))
                shift = rng.choice((-1, 1)) * (2 if amount >= .75 else 1)
                notes[i] = float(to_pitch(degree + shift))
        # DRUM has no pitch trajectory: melodic mode develops weak accents.
        if not pitched and mode in ("melodic", "combined"):
            candidates = [i for i, hit in enumerate(rhythm) if hit and i not in anchors]
            rng.shuffle(candidates)
            count = min(len(candidates), math.ceil(len(candidates) * amount * .5))
            for i in candidates[:count]:
                velocity[i] = bounded(velocity[i] + rng.choice((-1, 1)) * .18 * amount, .72, .1, 1)
        if mode in ("rhythmic", "combined"):
            candidates = [i for i in range(motif.steps) if i not in anchors]
            rng.shuffle(candidates)
            count = min(len(candidates), math.ceil(len(candidates) * amount * .5))
            for i in candidates[:count]:
                rhythm[i] = 1.0 - rhythm[i]
                if rhythm[i]:
                    previous = next((j for j in range(i - 1, -1, -1) if rhythm[j]), None)
                    notes[i] = notes[previous] if previous is not None else notes[i]
                    velocity[i] = min(.68, max(.35, velocity[previous] * .75 if previous is not None else .55))
                else:
                    velocity[i] = 0.0
        label = f"Variation {generation} · {mode}"
    elif not held and (mode == "off" or amount == 0):
        label = "Theme"
    if label.startswith("Variation") and (notes, rhythm, velocity) == original:
        label = "Theme · protected positions"
    material = replace(motif, notes=notes, rhythm=rhythm, velocity=velocity,
                       variations={}, step_beats=step)
    token = digest((motif.id, notes, rhythm, velocity))
    return MotifVariant(material, cycle, generation, label, token, digest(config))


class MotifDevelopment:
    def __init__(self):
        self.states = {}
        self.history = {}

    def reset_playback(self):
        self.states.clear()

    def forget(self, owner):
        self.states.pop(owner, None)
        self.history.pop(owner, None)

    def resolve(self, owner, motif, beat, step, parameters, scale, seed, running):
        cycle = max(0, int(math.floor(max(0.0, beat) / (motif.steps * step) + 1e-8)))
        source_key = digest((asdict(motif), step, scale, seed))
        config = settings(parameters)
        state = self.states.get(owner)
        if state is not None and state[0] == source_key:
            previous = state[1]
            # An early humanized onset may prepare the next cycle before the
            # visual clock reaches it. UI/parameter regeneration cannot rewind it.
            if (running and previous.cycle >= cycle) or (
                    not running and previous.cycle == cycle and previous.settings_key == digest(config)):
                return previous
        elif state is not None:
            self.history.pop(owner, None)
        variant = develop(motif, cycle, step, config, scale, seed)
        self.states[owner] = (source_key, variant)
        history = self.history.setdefault(owner, [])
        if not history or history[-1].token != variant.token:
            history.append(variant)
            del history[:-8]
        return variant

    def current(self, owner):
        state = self.states.get(owner)
        return state[1] if state is not None else None

    def hold(self, owner, source_id, token=None):
        variant = self.current(owner) if token is None else next(
            (v for v in reversed(self.history.get(owner, [])) if v.token == token), None)
        if variant is None or variant.motif.id != source_id:
            return None
        return {"source_id": source_id, "label": variant.label.removeprefix("Held · "),
                "material": asdict(variant.motif)}
