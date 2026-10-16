"""Pure algorithmic generators used by the Auricle engine.

Every generator returns a list of numbers. Pitch-oriented generators return
semitone offsets relative to the scale root. A value of ``None`` marks an
explicit rest (used by generators whose output can legitimately be 0.0 = the
root note, e.g. Markov or Probability). Purely rhythmic generators use
1.0 / 0.0 for hit / rest.

Generators never touch the global ``random`` module: anything stochastic takes
an explicit ``random.Random`` instance so that a project seed always
reproduces the same material.
"""
from __future__ import annotations

import random
from typing import Callable, Optional, Sequence

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SCALE_INTERVALS = {
    # Diatonic modes
    "Major": [0, 2, 4, 5, 7, 9, 11],
    "Minor": [0, 2, 3, 5, 7, 8, 10],
    "Dorian": [0, 2, 3, 5, 7, 9, 10],
    "Phrygian": [0, 1, 3, 5, 7, 8, 10],
    "Lydian": [0, 2, 4, 6, 7, 9, 11],
    "Mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "Locrian": [0, 1, 3, 5, 6, 8, 10],
    # Minor / modal variants
    "Harmonic Minor": [0, 2, 3, 5, 7, 8, 11],
    "Melodic Minor": [0, 2, 3, 5, 7, 9, 11],
    "Dorian b2": [0, 1, 3, 5, 7, 9, 10],
    "Lydian Dominant": [0, 2, 4, 6, 7, 9, 10],
    "Phrygian Dominant": [0, 1, 4, 5, 7, 8, 10],
    # Pentatonic / blues
    "Pentatonic": [0, 2, 4, 7, 9],
    "Major Pentatonic": [0, 2, 4, 7, 9],
    "Minor Pentatonic": [0, 3, 5, 7, 10],
    "Blues": [0, 3, 5, 6, 7, 10],
    # Symmetric / synthetic
    "Whole Tone": [0, 2, 4, 6, 8, 10],
    "Diminished HW": [0, 1, 3, 4, 6, 7, 9, 10],
    "Diminished WH": [0, 2, 3, 5, 6, 8, 9, 11],
    "Chromatic": list(range(12)),
    # Common extended scales
    "Bebop Dominant": [0, 2, 4, 5, 7, 9, 10, 11],
    "Bebop Major": [0, 2, 4, 5, 7, 8, 9, 11],
    "Acoustic": [0, 2, 4, 6, 7, 9, 10],
    "Hungarian Minor": [0, 2, 3, 6, 7, 8, 11],
    "Double Harmonic Major": [0, 1, 4, 5, 7, 8, 11],
    "Neapolitan Minor": [0, 1, 3, 5, 7, 8, 11],
    "Japanese": [0, 1, 5, 7, 8],
}
SCALE_NAMES = list(SCALE_INTERVALS)


def scale_intervals(name: str) -> list[int]:
    return SCALE_INTERVALS.get(str(name), SCALE_INTERVALS["Major"])


def parse_number_list(text, cast: Callable = float, default: Sequence = ()) -> list:
    """Parse a comma separated list typed by the user.

    Invalid tokens are skipped instead of raising, so a half-typed value in a
    text field can never break regeneration of the whole project.
    """
    out = []
    for token in str(text).split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.append(cast(float(token)) if cast is int else cast(token))
        except (TypeError, ValueError):
            continue
    return out or list(default)


def quantize_to_scale(note: float, root: int, scale_name: str) -> float:
    """Return the scale note closest to ``note`` (ties resolve downwards).

    Works for any root, including pitch-class roots 0..11, without clipping
    to the MIDI range.
    """
    intervals = scale_intervals(scale_name)
    octave = int((float(note) - int(root)) // 12)
    candidates = [int(root) + (octave + k) * 12 + i for k in (-1, 0, 1) for i in intervals]
    return float(min(candidates, key=lambda n: (abs(n - note), n)))


def degree_to_note(degree: int, root: int, scale_name: str) -> float:
    intervals = scale_intervals(scale_name)
    octave, idx = divmod(int(degree), len(intervals))
    return float(root + intervals[idx] + octave * 12)


def quantize_interval_to_scale(interval: float, scale_name: str) -> float:
    """Quantize a relative interval to a scale degree without treating it as MIDI.

    Pitch generators operate in offsets from the tonal root. This function keeps
    that contract: input/output are semitone offsets, not absolute notes.
    """
    # Root 0 makes quantize_to_scale work on offsets and also considers the
    # neighbouring octaves (11 -> 12 in a pentatonic scale, not 11 -> 9).
    return quantize_to_scale(float(interval), 0, scale_name)


def _rotate(values: list, rotation: int) -> list:
    if not values:
        return values
    r = int(rotation) % len(values)
    return values[r:] + values[:r] if r else values


def _tile(values: list, length: int) -> list:
    length = max(0, int(length))
    if not values:
        return []
    return (values * (length // len(values) + 1))[:length]


def euclidean(steps: int, pulses: int, rotation: int = 0) -> list[float]:
    """Bjorklund-style even distribution of pulses (bucket algorithm)."""
    steps = max(0, int(steps))
    pulses = max(0, min(steps, int(pulses)))
    if not steps:
        return []
    if not pulses:
        return [0.0] * steps
    if pulses == steps:
        return [1.0] * steps
    pattern = []
    bucket = 0
    for _ in range(steps):
        bucket += pulses
        if bucket >= steps:
            bucket -= steps
            pattern.append(1.0)
        else:
            pattern.append(0.0)
    return _rotate(pattern, rotation)


def bresenham(steps: int, pulses: int, rotation: int = 0) -> list[float]:
    """Line-rasterization rhythm: pulse k lands on floor(k * steps / pulses).

    The first pulse is always on step 0. Unlike the previous implementation the
    line spans the whole loop (0..steps, not 0..steps-1), so the last pulse no
    longer collides with the downbeat of the next cycle.
    """
    steps = max(0, int(steps))
    pulses = max(0, min(steps, int(pulses)))
    if not steps:
        return []
    out = [0.0] * steps
    for k in range(pulses):
        out[(k * steps) // pulses] = 1.0
    return _rotate(out, rotation)


def polyrhythm(length: int, a: int, b: int, phase_a: int = 0, phase_b: int = 0, mode: str = "OR") -> list[float]:
    a = max(1, int(a))
    b = max(1, int(b))
    phase_a = int(phase_a)
    phase_b = int(phase_b)
    mode = str(mode).upper()
    out = []
    for i in range(max(0, int(length))):
        aa = (i + phase_a) % a == 0
        bb = (i + phase_b) % b == 0
        if mode == "AND":
            hit = aa and bb
        elif mode == "XOR":
            hit = aa != bb
        else:
            hit = aa or bb
        out.append(1.0 if hit else 0.0)
    return out


def thue_morse(length: int, rotation: int = 0, invert: bool = False, density: float = 1.0,
               rng: Optional[random.Random] = None) -> list[float]:
    out = [float(bin(i).count("1") % 2) for i in range(max(0, int(length)))]
    if invert:
        out = [1.0 - v for v in out]
    density = max(0.0, min(1.0, float(density)))
    if density < 1:
        rng = rng or random.Random(0)
        out = [v if (v and rng.random() < density) else 0.0 for v in out]
    return _rotate(out, rotation)


def fibonacci_sequence(length: int) -> list[float]:
    a, b = 1, 1
    out = []
    for _ in range(max(0, int(length))):
        out.append(float(a))
        a, b = b, a + b
    return out


def fibonacci_rhythm(length: int, density: float = 0.5, offset: int = 0) -> list[float]:
    """Use Fibonacci positions modulo length, producing sparse non-periodic accents."""
    n = max(1, int(length))
    density = max(0.05, min(1.0, float(density)))
    target = max(1, int(n * density))
    out = [0.0] * n
    seen = set()
    a, b = 1, 2
    while a < n * 8 and len(seen) < target:
        seen.add((a + int(offset)) % n)
        a, b = b, a + b
    for p in seen:
        out[p] = 1.0
    return out


def recaman_sequence(length: int) -> list[float]:
    length = max(0, int(length))
    if not length:
        return []
    out = [0.0]
    seen = {0}
    n = 0
    for i in range(1, length):
        candidate = n - i
        if candidate > 0 and candidate not in seen:
            n = candidate
        else:
            n += i
        seen.add(n)
        out.append(float(n))
    return out


def de_bruijn_binary(order: int) -> list[float]:
    k = 2
    n = max(1, int(order))
    a = [0] * (k * n)
    seq = []

    def db(t: int, p: int):
        if t > n:
            if n % p == 0:
                seq.extend(a[1:p + 1])
        else:
            a[t] = a[t - p]
            db(t + 1, p)
            for j in range(a[t - p] + 1, k):
                a[t] = j
                db(t + 1, t)

    db(1, 1)
    return [float(v) for v in seq]


def de_bruijn(length: int, order: int = 3, mode: str = "Rhythm", root: int = 60, scale_name: str = "Major") -> list[float]:
    """De Bruijn sequence with optional scale-degree mapping for pitch generation."""
    stream = _tile(de_bruijn_binary(order), length)
    if str(mode) == "Pitch":
        # Convert binary symbols into two musically useful scale degrees.
        return [degree_to_note(0 if v == 0 else 2, root, scale_name) - root for v in stream]
    return stream


def markov(length: int, rng: random.Random, jump: int = 3, transpose: int = 0,
           rest_probability: float = 0.0, octave_range: int = 0, stay_probability: float = 0.0,
           root: int = 60, scale_name: str = "Major", scale_mode: bool = True,
           leap_probability: float = 0.12) -> list[Optional[float]]:
    """Scale-aware Markov melody. Most transitions are stepwise; occasional leaps are allowed.

    ``transpose`` is expressed in scale degrees in scale mode. Rests are
    returned as ``None`` because 0.0 is the (perfectly valid) root note.
    """
    intervals = scale_intervals(scale_name)
    degrees = list(range(len(intervals)))
    current = rng.randrange(len(degrees))
    out: list[Optional[float]] = []
    jump = max(1, int(jump))
    leap_probability = max(0.0, min(1.0, float(leap_probability)))
    rest_probability = max(0.0, min(1.0, float(rest_probability)))
    stay_probability = max(0.0, min(1.0, float(stay_probability)))
    octave_range = max(0, int(octave_range))
    for _ in range(max(0, int(length))):
        if rng.random() < rest_probability:
            out.append(None)
        elif scale_mode:
            octave = rng.randint(-octave_range, octave_range)
            out.append(degree_to_note(current + int(transpose) + octave * len(intervals), root, scale_name) - root)
        else:
            out.append(float(current + int(transpose) + rng.randint(-octave_range, octave_range) * 12))
        if stay_probability and rng.random() < stay_probability:
            continue
        if rng.random() < leap_probability:
            candidates = degrees
        else:
            candidates = [d for d in degrees if abs(d - current) <= jump] or degrees
        current = rng.choice(candidates)
    return out


def random_walk(length: int, rng: random.Random, step: int = 2, range_limit: int = 12,
                return_bias: float = 0.0, start: int = 0, root: int = 60, drift: float = 0.0,
                scale_name: str = "Major", quantize: bool = True) -> list[float]:
    value = int(start)
    out = []
    step = max(1, int(step))
    limit = max(1, int(range_limit))
    return_bias = max(0.0, min(1.0, float(return_bias)))
    drift = max(-1.0, min(1.0, float(drift)))
    for _ in range(max(0, int(length))):
        value = random_walk_step(value, rng, step, limit, return_bias, drift)
        out.append(float(quantize_interval_to_scale(value, scale_name)) if quantize else float(value))
    return out


def random_walk_step(value: int, rng: random.Random, step: int, limit: int,
                     return_bias: float, drift: float) -> int:
    """One step of the bounded random walk (shared by SEQ and LIVE)."""
    if return_bias > 0 and rng.random() < return_bias:
        direction = -1 if value > 0 else (1 if value < 0 else rng.choice([-1, 1]))
        value += direction * rng.randint(1, step)
    else:
        value += rng.randint(-step, step)
        if drift and rng.random() < abs(drift):
            value += 1 if drift > 0 else -1
    return max(-limit, min(limit, value))


def probability_pattern(length: int, probability: float, rng: random.Random, pitch_range: int = 7,
                        octave_range: int = 0, center: int = 0) -> list[Optional[float]]:
    """Independent events with probability ``probability``; misses are ``None``."""
    result: list[Optional[float]] = []
    p = max(0.0, min(1.0, float(probability)))
    spread = max(1, int(pitch_range))
    octave_range = max(0, int(octave_range))
    for _ in range(max(0, int(length))):
        if rng.random() < p:
            value = float(int(center) + rng.randint(-spread, spread))
            if octave_range:
                value += rng.randint(-octave_range, octave_range) * 12
            result.append(value)
        else:
            result.append(None)
    return result


def scale_walker(length: int, rng: random.Random, root: int = 60, scale_name: str = "Major",
                 step: int = 1, direction_bias: float = .5, range_octaves: int = 2,
                 leap_probability: float = .08) -> list[float]:
    count = len(scale_intervals(scale_name))
    center, lo, hi = scale_walker_bounds(count, range_octaves)
    idx = center + rng.randrange(count)
    out = []
    for _ in range(max(0, int(length))):
        out.append(float(degree_to_note(idx - center, root, scale_name) - root))
        idx = scale_walker_step(idx, rng, step, direction_bias, lo, hi, leap_probability)
    return out


def scale_walker_bounds(count: int, range_octaves: int) -> tuple[int, int, int]:
    """Return (center, lo, hi) degree indices of the scale-walker range."""
    center = max(0, int(range_octaves)) * count
    return center, 0, center * 2 + count - 1


def scale_walker_step(idx: int, rng: random.Random, step: int, direction_bias: float,
                      lo: int, hi: int, leap_probability: float) -> int:
    """One step of the scale walker (shared by SEQ and LIVE)."""
    if rng.random() < max(0.0, min(1.0, float(leap_probability))):
        delta = rng.choice([-1, 1]) * rng.randint(2, max(2, int(step) + 1))
    else:
        delta = (1 if rng.random() < direction_bias else -1) * rng.randint(1, max(1, int(step)))
    return max(lo, min(hi, idx + delta))


def weighted_scale(length: int, rng: random.Random, root: int = 60, scale_name: str = "Major",
                   weights: str = "1,1,1,1,1,1,1", octave_spread: float = 0.15) -> list[float]:
    intervals = scale_intervals(scale_name)
    raw = parse_number_list(weights, float)
    raw = (raw + [1.0] * len(intervals))[:len(intervals)]
    raw = [max(.01, x) for x in raw]
    spread = max(0.0, min(1.0, float(octave_spread)))
    out = []
    for _ in range(max(0, int(length))):
        degree = rng.choices(range(len(intervals)), weights=raw, k=1)[0]
        octave = rng.choice([-1, 0, 0, 0, 1]) if rng.random() < spread else 0
        out.append(float(degree_to_note(degree + octave * len(intervals), root, scale_name) - root))
    return out


def arpeggiator(length: int, rng: random.Random, root: int = 60, scale_name: str = "Major",
                pattern: str = "0,2,4,6", octaves: int = 1, direction: str = "Up",
                octave_mode: str = "Cycle") -> list[float]:
    values = parse_number_list(pattern, int, [0, 2, 4, 6])
    if direction == "Down":
        values = list(reversed(values))
    elif direction == "Up/Down" and len(values) > 2:
        values = values + values[-2:0:-1]
    octaves = max(0, int(octaves))
    count = len(scale_intervals(scale_name))
    out = []
    for i in range(max(0, int(length))):
        d = values[i % len(values)]
        if octave_mode == "Random":
            octv = rng.randint(0, octaves)
        else:
            octv = (i // len(values)) % (octaves + 1)
        out.append(float(degree_to_note(d + octv * count, root, scale_name) - root))
    return out


def interval_walker_step(value: int, rng: random.Random, step: int, return_bias: float,
                         range_limit: int, leap_probability: float) -> int:
    """One step of the interval walker (shared by SEQ and LIVE)."""
    if rng.random() < return_bias:
        value += -1 if value > 0 else (1 if value < 0 else rng.choice([-1, 1]))
    elif rng.random() < leap_probability:
        value += rng.choice([-1, 1]) * rng.randint(step + 1, max(step + 1, step * 2))
    else:
        value += rng.randint(-step, step)
    return max(-range_limit, min(range_limit, value))


def interval_walker(length: int, rng: random.Random, step: int = 3, return_bias: float = .2,
                    root: int = 60, scale_name: str = "Major", quantize: bool = True,
                    range_limit: int = 24, leap_probability: float = 0.08) -> list[float]:
    value = 0
    out = []
    step = max(1, int(step))
    range_limit = max(1, int(range_limit))
    return_bias = max(0.0, min(1.0, float(return_bias)))
    leap_probability = max(0.0, min(1.0, float(leap_probability)))
    for _ in range(max(0, int(length))):
        value = interval_walker_step(value, rng, step, return_bias, range_limit, leap_probability)
        out.append(float(quantize_interval_to_scale(value, scale_name)) if quantize else float(value))
    return out


def cellular_automaton(length: int, rule: int = 30, seed: str = "00100000", generations: int = 1,
                       mode: str = "Rhythm", root: int = 60, scale_name: str = "Major",
                       density: float = 1.0, rng: Optional[random.Random] = None) -> list[float]:
    row = [1 if c == '1' else 0 for c in str(seed) if c in '01'] or [1, 0, 0, 0, 0, 0, 0, 0]
    rule = max(0, min(255, int(rule)))
    for _ in range(max(0, int(generations))):
        nxt = []
        for i in range(len(row)):
            bits = (row[(i - 1) % len(row)] << 2) | (row[i] << 1) | row[(i + 1) % len(row)]
            nxt.append((rule >> bits) & 1)
        row = nxt
    out = [float(v) for v in _tile(row, length)]
    density = max(0.0, min(1.0, float(density)))
    if density < 1:
        rng = rng or random.Random(0)
        out = [v if (not v or rng.random() < density) else 0.0 for v in out]
    if str(mode) == "Pitch":
        count = len(scale_intervals(scale_name))
        return [degree_to_note(i % count, root, scale_name) - root if v else 0.0 for i, v in enumerate(out)]
    return out


def lsystem_sequence(length: int, axiom: str = "A", rule_a: str = "AB", rule_b: str = "A",
                     iterations: int = 3, mode: str = "Pitch", mapping: str = "0,1,2,3,4,5,6",
                     root: int = 60, scale_name: str = "Major") -> list[float]:
    text = str(axiom)
    for _ in range(max(0, int(iterations))):
        text = ''.join(rule_a if c == 'A' else rule_b if c == 'B' else c for c in text)
        if len(text) > 8192:
            text = text[:8192]
    stream = _tile(list(text), length)
    if str(mode) == "Rhythm":
        return [1.0 if c in "A1X+" else 0.0 for c in stream]
    raw = parse_number_list(mapping, int, range(len(scale_intervals(scale_name))))
    symbols = {chr(ord('A') + i): raw[i % len(raw)] for i in range(26)}
    return [degree_to_note(symbols.get(c, 0), root, scale_name) - root for c in stream]


def logistic_chaos(length: int, r: float = 3.9, x: float = .5, root: int = 60,
                   scale_name: str = "Major", range_octaves: int = 2, quantize: bool = True,
                   smooth: float = 0.0, burn_in: int = 0) -> list[float]:
    r = max(0.0, min(4.0, float(r)))
    x = max(.0001, min(.9999, float(x)))
    smooth = max(0.0, min(0.95, float(smooth)))
    for _ in range(max(0, int(burn_in))):
        x = r * x * (1 - x)
    prev = x  # smoothing starts from the post-burn-in state
    span = max(1, int(range_octaves)) * 12
    out = []
    for _ in range(max(0, int(length))):
        x = r * x * (1 - x)
        x = prev * smooth + x * (1 - smooth)
        prev = x
        note = root - span + x * (2 * span)
        out.append(float(quantize_to_scale(note, root, scale_name) - root) if quantize else float((x - .5) * 2 * span))
    return out


def fixed_pattern(length: int, pattern=None) -> list[float]:
    default = [1, 0, 0.7, 0, 1, 0, 0.5, 0]
    base = list(pattern) if pattern is not None else default
    base = base or default
    return [float(base[i % len(base)]) for i in range(max(0, int(length)))]


def mutate_sequence(values: list[float], mutator, rng: random.Random) -> list[float]:
    if not values:
        return values
    name, amount = mutator.name, mutator.amount
    if name == "Rotate":
        return _rotate(values[:], int(amount * len(values)))
    if name == "Reverse":
        return list(reversed(values))
    if name == "Invert":
        maximum, minimum = max(values), min(values)
        return [maximum - (v - minimum) for v in values]
    if name == "Transpose":
        semitones = round((amount - 0.5) * 24)
        return [v + semitones for v in values]
    if name == "Stretch":
        factor = max(1, round(1 + amount * 3))
        result = []
        for v in values:
            result.extend([v] * factor)
        return result[:len(values)]
    if name == "Compress":
        factor = max(1, round(1 + amount * 3))
        result = [values[i] for i in range(0, len(values), factor)]
        while len(result) < len(values):
            result.append(result[-1])
        return result[:len(values)]
    if name == "Probability":
        return [v if rng.random() < amount else 0.0 for v in values]
    if name == "Mutate":
        return [v + rng.choice([-2, -1, 1, 2]) if rng.random() < amount else v for v in values]
    if name == "Shuffle":
        result = values[:]
        for _ in range(max(1, round(amount * len(result) * 2))):
            a, b = rng.randrange(len(result)), rng.randrange(len(result))
            result[a], result[b] = result[b], result[a]
        return result
    if name == "Mirror":
        split = int(amount * (len(values) - 1))
        left = values[:split + 1]
        return (list(reversed(left)) + values[split + 1:])[:len(values)]
    if name == "Humanize":
        return [v + rng.uniform(-amount * 2, amount * 2) if v else v for v in values]
    if name == "Octave":
        octaves = round((amount - .5) * 4)
        return [v + octaves * 12 for v in values]
    if name == "Threshold":
        threshold = amount * 12
        return [v if abs(v) >= threshold else 0.0 for v in values]
    if name == "Scale":
        factor = .25 + amount * 1.5
        return [v * factor for v in values]
    return values[:]
