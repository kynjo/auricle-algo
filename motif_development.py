"""Bounded, repeatable motif development from an immutable source theme.

Only musical cycle boundaries commit pending settings. No mutation depends on
worker tick frequency, regeneration count, MIDI routing or a block's mode.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace, fields
import hashlib
import json
import math
import random

from generators import scale_intervals
from motif_engine import Motif


MODES = (("Off", "off"), ("Melodic", "melodic"),
         ("Rhythmic", "rhythmic"), ("Combined", "combined"),
         ("Sequence", "sequence"), ("Inversion", "inversion"),
         ("Call & Response", "call_response"), ("Retrograde", "retrograde"))


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


def _scale_pitch(note, degree_shift, scale):
    """Move a pitch by scale degrees without leaving the selected scale."""
    intervals = scale_intervals(scale) or list(range(12))
    count = len(intervals)
    octave = math.floor(float(note) / 12)
    degree = min(range(count), key=lambda i: (abs(octave * 12 + intervals[i] - note), i))
    absolute_degree = octave * count + degree + int(degree_shift)
    target_octave, target_degree = divmod(absolute_degree, count)
    return float(target_octave * 12 + intervals[target_degree])


def _nearest_scale_pitch(note, scale):
    intervals = scale_intervals(scale) or list(range(12))
    candidates = [octave * 12 + interval
                  for octave in range(math.floor(note / 12) - 1, math.floor(note / 12) + 2)
                  for interval in intervals]
    return float(min(candidates, key=lambda value: (abs(value - note), value)))


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
        if mode in ("sequence", "inversion", "call_response", "retrograde"):
            if mode == "sequence":
                direction = 1 if generation % 2 else -1
                shift = direction * max(1, min(3, round(1 + amount * 2)))
                if pitched:
                    for i, hit in enumerate(rhythm):
                        if hit and i not in anchors:
                            notes[i] = _scale_pitch(notes[i], shift, scale)
                else:
                    for i, hit in enumerate(rhythm):
                        if hit and i not in anchors:
                            velocity[i] = bounded(velocity[i] + direction * .12 * amount, .72, .1, 1)
            elif mode == "inversion":
                if pitched:
                    pivot_slots = [i for i in sorted(anchors) if i < len(notes) and rhythm[i]]
                    pivot = notes[pivot_slots[0]] if pivot_slots else notes[0]
                    for i, hit in enumerate(rhythm):
                        if hit and i not in anchors:
                            notes[i] = _nearest_scale_pitch(2 * pivot - notes[i], scale)
                else:
                    candidates = [i for i, hit in enumerate(rhythm) if hit and i not in anchors]
                    for i in candidates:
                        velocity[i] = bounded(.9 - velocity[i] * .45, .55, .1, 1)
            elif mode == "call_response":
                midpoint = max(1, len(rhythm) // 2)
                call_notes, call_rhythm, call_velocity = notes[:], rhythm[:], velocity[:]
                for i in range(midpoint, len(rhythm)):
                    if i in anchors:
                        continue
                    source_index = i - midpoint
                    if pitched:
                        pivot = call_notes[0] if call_notes else 0.0
                        notes[i] = _nearest_scale_pitch(2 * pivot - call_notes[source_index], scale)
                    rhythm[i] = call_rhythm[source_index]
                    velocity[i] = min(.72, call_velocity[source_index] * .82) if rhythm[i] else 0.0
            elif mode == "retrograde":
                notes.reverse(); rhythm.reverse(); velocity.reverse()
                # Preserve the original metric anchors after reversing the
                # phrase so its downbeat and authored accents remain stable.
                for i in anchors:
                    notes[i] = original[0][i]
                    rhythm[i] = original[1][i]
                    velocity[i] = original[2][i]
        else:
            # One or two neighbouring scale degrees, limited to half the
            # mutable attacks even at maximum Amount. Stable priority order
            # as Amount grows.
            if pitched and mode in ("melodic", "combined"):
                candidates = [i for i, hit in enumerate(rhythm) if hit and i not in anchors]
                rng.shuffle(candidates)
                count = min(len(candidates), math.ceil(len(candidates) * amount * .5))
                for i in candidates[:count]:
                    notes[i] = _scale_pitch(notes[i], rng.choice((-1, 1)) * (2 if amount >= .75 else 1), scale)
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
    MEMORY_VERSION = 1
    HISTORY_LIMIT = 8

    def __init__(self, memory=None):
        self.states = {}
        self.history = {}
        self.history_source = {}
        self.load_memory(memory)

    @staticmethod
    def _owner_key(owner):
        try:
            return int(owner)
        except (TypeError, ValueError):
            return str(owner)

    @staticmethod
    def _variant_from_dict(data):
        if not isinstance(data, dict) or not isinstance(data.get("motif"), dict):
            return None
        motif_data = data["motif"]
        allowed = {item.name for item in fields(Motif)}
        for key in ("notes", "rhythm", "velocity"):
            values = motif_data.get(key, [])
            if not isinstance(values, list) or any(
                    not isinstance(value, (int, float)) or not math.isfinite(float(value))
                    for value in values):
                return None
        try:
            motif = Motif(**{key: value for key, value in motif_data.items() if key in allowed})
            return MotifVariant(
                motif=motif, cycle=max(0, int(data.get("cycle", 0))),
                generation=max(0, int(data.get("generation", 0))),
                label=str(data.get("label", "Saved variant")),
                token=str(data.get("token", digest(asdict(motif)))),
                settings_key=str(data.get("settings_key", "")),
            )
        except (TypeError, ValueError):
            return None

    def load_memory(self, memory):
        """Restore bounded variant histories from a project JSON payload."""
        self.history.clear()
        self.history_source.clear()
        if not isinstance(memory, dict):
            return
        owners = memory.get("owners", {})
        if not isinstance(owners, dict):
            return
        for owner, record in owners.items():
            if not isinstance(record, dict):
                continue
            key = self._owner_key(owner)
            raw_variants = record.get("variants", [])
            if not isinstance(raw_variants, list):
                continue
            variants = [self._variant_from_dict(item) for item in raw_variants]
            variants = [item for item in variants if item is not None]
            if variants:
                self.history[key] = variants[-self.HISTORY_LIMIT:]
                self.history_source[key] = str(record.get("source_id") or variants[-1].motif.id)

    def export_memory(self):
        """Return JSON-safe, versioned project memory (not live runtime state)."""
        owners = {}
        for owner, variants in self.history.items():
            if not variants:
                continue
            owners[str(owner)] = {
                "source_id": self.history_source.get(owner, variants[-1].motif.id),
                "variants": [{
                    "motif": asdict(item.motif), "cycle": item.cycle,
                    "generation": item.generation, "label": item.label,
                    "token": item.token, "settings_key": item.settings_key,
                } for item in variants[-self.HISTORY_LIMIT:]],
            }
        return {"version": self.MEMORY_VERSION, "owners": owners}

    def reset_playback(self):
        self.states.clear()

    def forget(self, owner):
        self.states.pop(owner, None)
        self.history.pop(owner, None)
        self.history_source.pop(owner, None)

    def resolve(self, owner, motif, beat, step, parameters, scale, seed, running):
        cycle = max(0, int(math.floor(max(0.0, beat) / (motif.steps * step) + 1e-8)))
        source_key = digest((asdict(motif), step, scale, seed))
        config = settings(parameters)
        state = self.states.get(owner)
        if self.history_source.get(owner) not in (None, motif.id):
            self.history.pop(owner, None)
            self.history_source.pop(owner, None)
        if state is not None and state[0] == source_key:
            previous = state[1]
            # An early humanized onset may prepare the next cycle before the
            # visual clock reaches it. UI/parameter regeneration cannot rewind it.
            if (running and previous.cycle >= cycle) or (
                    not running and previous.cycle == cycle and previous.settings_key == digest(config)):
                return previous
        variant = develop(motif, cycle, step, config, scale, seed)
        self.states[owner] = (source_key, variant)
        history = self.history.setdefault(owner, [])
        if not history or history[-1].token != variant.token:
            history.append(variant)
            del history[:-self.HISTORY_LIMIT]
        self.history_source[owner] = motif.id
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
