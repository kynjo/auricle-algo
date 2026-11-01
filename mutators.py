"""Typed mutations shared by SEQ, LIVE, drum voices and the inspector.

Pitch is a semitone offset (zero is a valid tonic), rhythm is binary,
velocity is 0..1, and timing is a gate multiplier 0..1.5, not onset time.
"""
from __future__ import annotations

import random

MUTATORS = [
    "Rotate", "Reverse", "Invert", "Transpose", "Stretch", "Compress",
    "Probability", "Mutate", "Shuffle", "Mirror", "Humanize", "Octave", "Threshold", "Scale",
]
TARGETS = ("rhythm", "pitch", "velocity", "timing")
SEQUENCE_MUTATORS = frozenset({"Rotate", "Reverse", "Invert", "Stretch", "Compress", "Shuffle", "Mirror"})
_COMPATIBILITY = {
    "Transpose": {"pitch"}, "Octave": {"pitch"},
    "Probability": {"rhythm", "velocity", "timing"},
    "Threshold": {"velocity", "timing"},
    "Scale": {"pitch", "velocity", "timing"},
    "Humanize": {"pitch", "velocity", "timing"},
}


def mutators_for_target(target: str) -> list[str]:
    return [name for name in MUTATORS if target in _COMPATIBILITY.get(name, TARGETS)] if target in TARGETS else []


def mutation_active(mutator) -> bool:
    """Neutral rows must not select another LIVE source path or consume RNG."""
    if mutator.name not in mutators_for_target(getattr(mutator, "target", "pitch")):
        return False
    amount = max(0.0, min(1.0, float(mutator.amount)))
    name = mutator.name
    if name == "Transpose":
        return round((amount - .5) * 24) != 0
    if name == "Octave":
        return round((amount - .5) * 4) != 0
    if name == "Scale":
        return amount != .5
    if name == "Probability":
        return amount < 1
    if name in ("Stretch", "Compress"):
        return round(1 + amount * 3) > 1
    if name == "Rotate":
        return 0 < amount < 1
    return amount > 0


def mutator_help(name: str, target: str) -> str:
    if name not in mutators_for_target(target):
        return "Unsupported target: this saved mutation is bypassed. Choose a compatible type or target."
    unit = {"pitch": "semitones", "rhythm": "binary hits/rests", "velocity": "0..1", "timing": "gate 0..1.5"}[target]
    descriptions = {
        "Rotate": "Left rotation by Amount × window length (1 = a full turn).",
        "Reverse": "Reverse the window; Amount 0 bypasses, otherwise enabled.",
        "Invert": "Reflect pitch around its range, or invert within the target's fixed range; Amount 0 bypasses.",
        "Transpose": "Amount 0..1 = -12..+12 semitones; 0.5 is neutral.",
        "Octave": "Amount 0..1 = -2..+2 octaves; 0.5 is neutral.",
        "Stretch": "Repeat each value 1..4 times, keeping the window length.",
        "Compress": "Read every 1st..4th value and repeat the shortened motif.",
        "Probability": "Keep probability: 0 removes all events, 1 keeps all events.",
        "Mutate": "Chance of a hit/rest flip, a ±1/2-semitone pitch step, or a bounded value change.",
        "Shuffle": "Number of random swaps; 0 leaves the window unchanged.",
        "Mirror": "Mirror an increasing prefix; Amount 1 makes the whole window a palindrome, 0 bypasses.",
        "Humanize": "Small deviations in the target's units. Velocity/gate zeros remain closed.",
        "Threshold": "Remove values below Amount × target maximum (1 for velocity, 1.5 for gate).",
        "Scale": "Multiply values by 0.25..1.75; 0.5 is neutral. This is not scale/key quantization.",
    }
    return f"{unit}. {descriptions[name]} Mutation Amount blends the result with the original; 0 bypasses. Timing changes note length, not swing or onset."


def mutate_sequence(values: list[float], mutator, rng: random.Random, *, strength: float = 1.0) -> list[float]:
    """Apply an allowed operation, then blend its effect without moving its neutral point."""
    original = list(values)
    target = getattr(mutator, "target", "pitch")
    name = mutator.name
    strength = max(0.0, min(1.0, float(strength)))
    if not original or strength <= 0 or not mutation_active(mutator):
        return original
    amount = max(0.0, min(1.0, float(mutator.amount)))
    maximum = 1.5 if target == "timing" else 1.0
    n = len(original)
    result = original[:]
    if name == "Rotate":
        shift = int(amount * n) % n
        result = original[shift:] + original[:shift]
    elif name == "Reverse" and amount > 0:
        result.reverse()
    elif name == "Invert" and amount > 0:
        center = max(original) + min(original) if target == "pitch" else maximum
        result = [center - value for value in original]
    elif name == "Transpose":
        result = [value + round((amount - .5) * 24) for value in original]
    elif name == "Octave":
        result = [value + 12 * round((amount - .5) * 4) for value in original]
    elif name == "Stretch":
        factor = round(1 + amount * 3)
        result = [original[i // factor] for i in range(n)]
    elif name == "Compress":
        compressed = original[::round(1 + amount * 3)]
        result = [compressed[i % len(compressed)] for i in range(n)]
    elif name == "Probability":
        result = [value if rng.random() < amount else 0.0 for value in original]
    elif name == "Mutate":
        for i, value in enumerate(original):
            if rng.random() < amount:
                if target == "rhythm":
                    result[i] = 1.0 - value
                elif target == "pitch":
                    result[i] = value + rng.choice((-2, -1, 1, 2))
                elif value > 0:
                    result[i] = value + rng.choice((-1, 1)) * maximum * .2
    elif name == "Shuffle":
        for _ in range(round(amount * n * 2)):
            a, b = rng.randrange(n), rng.randrange(n)
            result[a], result[b] = result[b], result[a]
    elif name == "Mirror" and amount > 0 and n > 1:
        size = max(2, min(n, round(amount * n)))
        for i in range((size + 1) // 2, size):
            result[i] = original[size - 1 - i]
    elif name == "Humanize":
        span = 2.0 if target == "pitch" else maximum * .12
        result = [value + rng.uniform(-amount * span, amount * span)
                  if target == "pitch" or value > 0 else 0.0 for value in original]
    elif name == "Threshold":
        result = [value if value >= amount * maximum else 0.0 for value in original]
    elif name == "Scale":
        result = [value * (.25 + amount * 1.5) for value in original]
    if target == "rhythm":
        # Never blend hit masks into fractional hits: a tiny nonzero value
        # would otherwise become a full MIDI event downstream.
        return [float((new if strength >= 1 or rng.random() < strength else old) > .5)
                for old, new in zip(original, result)]
    result = [old + strength * (new - old) for old, new in zip(original, result)]
    if target != "pitch":
        result = [max(0.0, min(maximum, value)) for value in result]
    return result
