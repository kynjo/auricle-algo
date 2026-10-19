"""Shared, deterministic Drum Kit controls; voice parameters remain untouched."""

import math


KIT_DEFAULTS = {
    "kit_density": 1.0,
    "kit_swing": 0.0,
    "kit_humanize": 0.0,
    "kit_fill": 0.0,
}

KIT_TOOLTIPS = {
    "kit_density": "Kit hit retention: 0 = silence, 1 = all voice hits, including fills.",
    "kit_swing": "Adds swing to all voices: up to half a step. LIVE alternates long/short intervals.",
    "kit_humanize": "Adds bounded timing jitter (up to ±10%) and velocity variation (up to ±15%).",
    "kit_fill": "Adds hits in the last quarter of each voice's structure cycle; 0 = no added hits. LIVE counts event attempts, including rests.",
}


def kit_value(drum, key):
    default = KIT_DEFAULTS[key]
    try:
        value = float(drum.parameters.get(key, default)) if drum is not None else default
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, value)) if math.isfinite(value) else default


def kit_random(seed, index, lane):
    """Stable per-voice/per-step random value, independent of generator RNG.

    Separate lanes keep density, fills, dynamics and timing independent.
    Changing a knob never reseeds or advances the voice's generator.
    """
    mask = (1 << 64) - 1
    value = (int(seed) + int(index) * 0x9E3779B97F4A7C15 + lane * 0xD1B54A32D192ED03) & mask
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    value ^= value >> 31
    return (value >> 11) / float(1 << 53)


def fill_at(drum, seed, index, cycle_length):
    amount = kit_value(drum, "kit_fill")
    size = max(1, int(cycle_length))
    width = max(1, (size + 3) // 4)
    return (amount > 0.0 and index % size >= size - width
            and kit_random(seed, index, 1) < amount)


def timing_offset(drum, seed, index, voice_swing=0.0, voice_jitter=0.0):
    """Kit displacement as a fraction of a step; never changes the grid."""
    swing = min(.5, voice_swing + 0.5 * kit_value(drum, "kit_swing")) if index % 2 else 0.0
    jitter = (2.0 * kit_random(seed, index, 3) - 1.0) * 0.10 * kit_value(drum, "kit_humanize")
    # Combined extremes must not put an event after the following step.
    return swing + max(-.25, min(.25, voice_jitter + jitter))


def live_timing_factor(drum, seed, index):
    # Difference of boundary offsets alternates long/short intervals and
    # prevents cumulative drift on a fixed-rate stream, including silent steps.
    return 1.0 + timing_offset(drum, seed, index + 1) - timing_offset(drum, seed, index)
