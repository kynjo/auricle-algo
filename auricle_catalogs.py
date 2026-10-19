"""Catalogs and role defaults for Auricle v107."""

from generators import NOTE_NAMES, SCALE_NAMES


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)

# --------------------------------------------------------------------------
# Catalogs
# --------------------------------------------------------------------------
PARTS = ["rhythm", "pitch", "velocity", "duration", "density", "accent"]
# Drum Machine voices cover fixed-note percussion; there is no standalone
# PERCUSSION block in the current project schema.
BLOCK_TYPES = ["DRUM", "BASS", "MELODY", "PAD", "CHORD"]
PERCUSSIVE_TYPES = ("DRUM", "PERCUSSION")

DRUM_VOICE_DEFAULTS = (
    ("KICK", "Euclidean", 36, {"euclidean_steps": 16, "pulses": 4, "euclidean_rotation": 0}),
    ("SNARE", "Euclidean", 38, {"euclidean_steps": 16, "pulses": 2, "euclidean_rotation": 4}),
    ("CLOSED HAT", "Euclidean", 42, {"euclidean_steps": 16, "pulses": 8, "euclidean_rotation": 0}),
    ("OPEN HAT", "Pattern", 46, {"pattern": "0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0"}),
    ("CLAP", "Euclidean", 39, {"euclidean_steps": 16, "pulses": 2, "euclidean_rotation": 4}),
    ("PERC", "Pattern", 50, {"pattern": "1,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0"}),
)

# Musical role profiles sit between the generator and MIDI output.  The
# generator remains generic, while the role determines register, density,
# duration and (for harmonic roles) voicing.  This keeps one Markov/Walker/etc.
# implementation useful for several musical jobs without creating separate
# BassMarkov/MelodyMarkov/PadMarkov algorithms.
ROLE_PROFILES = {
    "BASS": {
        "label": "Low foundation", "register_min": -36, "register_max": 0, "register_anchor": -24,
        "pitch_range": 36, "fill_density": 0.90, "gate": 0.90, "root_bias": 0.35,
        "role_center": -24, "role_width": 36, "role_duration": 1.10,
        "groove_follow": 0.70, "groove_accent": 0.65, "groove_offset": 0,
        "groove_mode": "Union", "relation_drum_source": -1,
    },
    "MELODY": {
        "label": "Lead / phrase", "register_min": -12, "register_max": 24, "register_anchor": 0,
        "pitch_range": 36, "fill_density": 0.75, "gate": 0.65, "root_bias": 0.0,
        "role_center": 0, "role_width": 36, "role_duration": 0.85,
        "harmony_anchor": 0.55, "relation_chord_source": -1,
    },
    "PAD": {
        "label": "Harmonic texture", "register_min": -24, "register_max": 12, "register_anchor": -12,
        "pitch_range": 24, "fill_density": 0.55, "gate": 1.50, "root_bias": 0.0,
        "role_center": -12, "role_width": 24, "role_duration": 1.75,
        "harmony_size": 3, "harmony_spread": 12, "harmony_inversion": 0,
    },
    "CHORD": {
        "label": "Harmonic event", "register_min": -24, "register_max": 12, "register_anchor": -12,
        "pitch_range": 24, "fill_density": 0.85, "gate": 1.00, "root_bias": 0.0,
        "role_center": -12, "role_width": 24, "role_duration": 1.00,
        "harmony_size": 3, "harmony_spread": 7, "harmony_inversion": 0,
    },
}

def apply_role_defaults(block):
    """Apply non-destructive defaults for a block's musical role."""
    profile = ROLE_PROFILES.get(block.block_type)
    if not profile:
        return
    for key in ("pitch_range", "fill_density", "gate", "role_center", "role_width", "role_duration", "harmony_size", "harmony_spread", "harmony_inversion", "role_root_bias", "pad_sustain", "groove_follow", "groove_accent", "groove_offset", "groove_mode", "relation_drum_source", "harmony_anchor", "relation_chord_source"):
        if key in profile:
            block.parameters.setdefault(key, profile[key])
    block.parameters.setdefault("role_density", profile.get("fill_density", 1.0))
    block.parameters.setdefault("role_root_bias", profile.get("root_bias", 0.0))
    if block.block_type == "PAD":
        block.parameters.setdefault("pad_sustain", profile.get("role_duration", 1.75))
SCALES = SCALE_NAMES
GENERATORS = [
    "Euclidean", "Bresenham", "Polyrhythm", "Thue-Morse", "Fibonacci Rhythm",
    "Fibonacci", "Recaman", "De Bruijn", "Markov", "Random Walk", "Interval Walker",
    "Scale Walker", "Weighted Scale", "Arpeggiator", "Probability", "Pattern",
    "Cellular Automaton", "L-System", "Logistic Chaos",
]
RHYTHM_ALGORITHMS = {"Euclidean", "Bresenham", "Polyrhythm", "Thue-Morse", "Fibonacci Rhythm"}
# LIVE mode steps through the SEQ material of these generators in order.
CYCLIC_LIVE_ALGORITHMS = {
    "Bresenham", "Polyrhythm", "Thue-Morse", "Fibonacci Rhythm", "De Bruijn", "Cellular Automaton",
    "Fibonacci", "Recaman", "Weighted Scale", "Arpeggiator", "L-System", "Logistic Chaos",
}
MUTATORS = [
    "Rotate", "Reverse", "Invert", "Transpose", "Stretch", "Compress",
    "Probability", "Mutate", "Shuffle", "Mirror", "Humanize", "Octave", "Threshold", "Scale",
]
RELATION_CURVES = ["Linear", "Exponential", "Logarithmic", "Threshold", "Quantize"]
RELATION_DELAYS = [0, 1, 2, 4, 8]
RELATIONS = ["Copy", "Mix", "Quantize To", "Modulate", "Follow", "Trigger", "Dialogue"]
PROCESS_TYPES = ["Counter", "Modulo", "Compare", "Clock Divide", "Clock Multiply", "Memory", "Delay", "Feedback", "Parameter Modulation"]
PROCESS_TARGETS = list(PARTS)
DEFAULT_PATTERN = "1,0,0.7,0,1,0,0.5,0"

# Block parameters that are text/choice values and therefore never modulation
# or macro destinations.
NON_NUMERIC_PARAMETERS = frozenset({
    "harmonic_follow",
    "pattern_step_chances",
    "kit_meter", "kit_protect_anchors", "kit_variant",
    "scale_name", "pattern", "arp_pattern", "arp_direction", "arp_octave_mode", "ls_axiom",
    "ls_rule_a", "ls_rule_b", "ls_mode", "ls_mapping", "ca_seed", "scale_weights",
    "variation_seed", "poly_mode", "debruijn_mode", "ca_mode", "groove_mode", "motif_id", "motif_step_beats",
    "motif_development", "motif_amount", "motif_every", "motif_return", "motif_hold",
    "kit_coordinated", "kit_style", "kit_phrase_bars", "kit_role",
})

# Real generator parameters exposed to cross-block Parameter Modulation,
# macros and Randomize. Values are (default, minimum, maximum). Numeric
# parameters present in a block's JSON are added automatically, so the catalog
# is also backward-compatible with custom/older projects.
FLOAT_MOD_KEYS = {
    "harmonic_strength",
    "kit_density", "kit_swing", "kit_humanize", "kit_fill", "kit_complexity",
    "kit_syncopation", "kit_tom_activity", "kit_variation",
    "fill_density", "event_probability", "transpose", "octave", "tm_density", "fib_density",
    "markov_rest", "markov_leap", "markov_stay", "walk_return_bias", "walk_drift",
    "interval_return", "interval_leap", "scale_direction", "scale_leap", "scale_octave_spread",
    "probability", "probability_velocity_floor", "pattern_scale", "pattern_probability",
    "ca_density", "chaos_r", "chaos_x", "chaos_smooth",
}
COMMON_MOD_PARAMETERS = {
    "fill_density": (1.0, 0.0, 1.0),
    "event_probability": (1.0, 0.0, 1.0),
    "transpose": (0.0, -48.0, 48.0),
    "octave": (0.0, -4.0, 4.0),
    "structure_length": (16, 1, 128),
    "structure_rotation": (0, 0, 127),
    "timing_rate": (1.0, 0.25, 4.0),
    "timing_swing": (0.0, 0.0, 0.5),
    "timing_humanize": (0.0, 0.0, 0.25),
    "timing_offset": (0.0, -0.5, 0.5),
    "pitch_range": (24, 1, 48),
    "groove_follow": (0.70, 0.0, 1.0),
    "groove_accent": (0.65, 0.0, 1.0),
    "groove_offset": (0, -127, 127),
    "harmony_anchor": (0.55, 0.0, 1.0),
}
GENERATOR_MOD_PARAMETERS = {
    "Euclidean": {"euclidean_steps": (16, 1, 128), "pulses": (5, 1, 128), "euclidean_rotation": (0, 0, 127)},
    "Bresenham": {"bres_steps": (16, 1, 128), "bres_pulses": (5, 1, 128), "bres_rotation": (0, 0, 127)},
    "Polyrhythm": {"poly_a": (3, 1, 32), "poly_b": (4, 1, 32), "poly_phase_a": (0, 0, 31), "poly_phase_b": (0, 0, 31)},
    "Thue-Morse": {"tm_rotation": (0, 0, 127), "tm_density": (1.0, 0.0, 1.0)},
    "Fibonacci Rhythm": {"fib_density": (0.5, 0.0, 1.0), "fib_offset": (0, 0, 127)},
    "Fibonacci": {"sequence_mod": (7, 1, 24), "sequence_stride": (1, 1, 8), "sequence_offset": (0, -24, 24)},
    "Recaman": {"sequence_mod": (7, 1, 24), "sequence_stride": (1, 1, 8), "sequence_offset": (0, -24, 24)},
    "De Bruijn": {"debruijn_order": (3, 1, 5), "debruijn_rotation": (0, 0, 127)},
    "Markov": {"markov_jump": (3, 1, 6), "markov_transpose": (0, -24, 24), "markov_octaves": (0, 0, 2), "markov_rest": (0.0, 0.0, 1.0), "markov_leap": (0.12, 0.0, 1.0), "markov_stay": (0.0, 0.0, 1.0)},
    "Random Walk": {"walk_step": (2, 1, 12), "walk_range": (12, 1, 48), "walk_start": (0, -48, 48), "walk_return_bias": (0.0, 0.0, 1.0), "walk_drift": (0.0, -1.0, 1.0)},
    "Interval Walker": {"interval_step": (3, 1, 12), "interval_return": (0.2, 0.0, 1.0), "interval_range": (24, 4, 48), "interval_leap": (0.08, 0.0, 1.0)},
    "Scale Walker": {"scale_step": (1, 1, 4), "scale_direction": (0.5, 0.0, 1.0), "scale_octaves": (2, 1, 4), "scale_leap": (0.08, 0.0, 1.0)},
    "Weighted Scale": {"scale_octave_spread": (0.15, 0.0, 1.0)},
    "Arpeggiator": {"arp_octaves": (1, 1, 4)},
    "Probability": {"probability": (0.5, 0.0, 1.0), "probability_pitch_range": (7, 1, 24), "probability_center": (0, -24, 24), "probability_octaves": (0, 0, 2), "probability_velocity_floor": (0.4, 0.0, 1.0)},
    "Pattern": {"pattern_rotation": (0, 0, 127), "pattern_scale": (1.0, 0.0, 4.0), "pattern_probability": (1.0, 0.0, 1.0)},
    "Cellular Automaton": {"ca_rule": (30, 0, 255), "ca_generations": (2, 0, 16), "ca_density": (1.0, 0.0, 1.0)},
    "L-System": {"ls_iterations": (3, 0, 8)},
    "Logistic Chaos": {"chaos_r": (3.9, 0.0, 4.0), "chaos_x": (0.5, 0.001, 0.999), "chaos_octaves": (2, 1, 4), "chaos_smooth": (0.0, 0.0, 1.0), "chaos_burn_in": (0, 0, 1000)},
}


