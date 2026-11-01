"""Anchor/support/ornament classification for probability-aware generation.

The module is intentionally independent from the engine and Qt.  It receives
plain block/plan data and returns stable, deterministic musical categories.
"""
from __future__ import annotations

import math

ANCHOR = "anchor"
SUPPORT = "support"
ORNAMENT = "ornament"
EVENT_CLASSES = (ANCHOR, SUPPORT, ORNAMENT)

CLASS_PARAMETER = {
    ANCHOR: "anchor_strength",
    SUPPORT: "support_probability",
    ORNAMENT: "ornament_probability",
}

DEFAULT_CLASS_PROBABILITIES = {
    "anchor_strength": 1.0,
    "support_probability": 1.0,
    "ornament_probability": 1.0,
}


def _finite(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _near(value, target, epsilon=1e-7):
    return abs(float(value) - float(target)) <= epsilon


def _role(block):
    parameters = getattr(block, "parameters", {}) or {}
    role = str(parameters.get("kit_role", "")).strip().lower()
    if role in {"kick", "snare", "closed_hat", "open_hat", "clap", "tom", "perc"}:
        return role
    if role == "free":
        role = ""
    name = str(getattr(block, "name", "")).casefold().replace("_", " ").replace("-", " ")
    note = int(getattr(block, "midi_note", 60) or 60)
    if any(token in name for token in ("kick", "bass drum", "бочка")) or note in (35, 36):
        return "kick"
    if any(token in name for token in ("snare", "снейр")) or note in (38, 40):
        return "snare"
    if "clap" in name or "хлопок" in name or note == 39:
        return "clap"
    if "open hat" in name or "open hihat" in name or note == 46:
        return "open_hat"
    if any(token in name for token in ("hat", "hihat", "cymbal")) or note in (42, 44):
        return "closed_hat"
    if "tom" in name or note in (41, 43, 45, 47, 48, 50):
        return "tom"
    if getattr(block, "is_drum_voice", False):
        return "perc"
    return str(getattr(block, "block_type", "MELODY")).upper()


def classify_event(
    block,
    beat,
    *,
    meter=(4, 4),
    kit_step=None,
    phrase_awareness=True,
    phrase_bars=4,
    event=None,
):
    """Return ``(event_class, importance)`` for an event at absolute beat.

    Coordinated-kit annotations take precedence, except that the kit editor's
    legacy Keep-beat mask also marks eighth-note hats as protected. Those
    non-downbeat hat pulses are Support rather than metric Anchors, so Density
    and the class probability controls can still thin them musically.
    """
    event = event if isinstance(event, dict) else {}
    supplied = str(event.get("event_class", "")).lower()
    if supplied in EVENT_CLASSES:
        default_importance = {ANCHOR: 1.0, SUPPORT: .65, ORNAMENT: .25}[supplied]
        return supplied, max(0.0, min(1.0, _finite(event.get("importance", default_importance), default_importance)))

    role = _role(block)
    try:
        numerator, denominator = int(meter[0]), int(meter[1])
    except (TypeError, ValueError, IndexError):
        numerator, denominator = 4, 4
    numerator = max(1, numerator)
    denominator = max(1, denominator)
    beats_per_bar = numerator * 4.0 / denominator
    absolute = max(0.0, _finite(beat))
    bar_index = int(math.floor((absolute + 1e-8) / beats_per_bar))
    beat_in_bar = absolute - bar_index * beats_per_bar
    if abs(beat_in_bar) < 1e-7 or abs(beat_in_bar - beats_per_bar) < 1e-7:
        beat_in_bar = 0.0
    downbeat = _near(beat_in_bar, 0.0)
    on_quarter = _near(beat_in_bar % 1.0, 0.0)
    on_eighth = _near((beat_in_bar * 2.0) % 1.0, 0.0)

    # Kit annotations identify exact authored events. Keep the distinction
    # between the editor's protection mask and the musical event hierarchy.
    if kit_step is not None and bool(getattr(kit_step, "allowed", False)):
        importance = max(0.0, min(1.0, _finite(getattr(kit_step, "importance", .5), .5)))
        if bool(getattr(kit_step, "anchor", False)):
            if role in ("closed_hat", "open_hat") and not downbeat:
                if importance >= .60:
                    return SUPPORT, max(.60, importance)
                return ORNAMENT, importance
            return ANCHOR, 1.0
        if bool(getattr(kit_step, "fill", False)):
            return ORNAMENT, .25
        if importance >= .60:
            return SUPPORT, max(.60, importance)
        return ORNAMENT, importance

    # Compound meters have two or more dotted-quarter pulses. 7/8 uses its
    # conventional 2+2+3 grouping, represented here in quarter-note beats.
    if denominator == 8 and numerator % 3 == 0:
        pulse = 1.5
        primary = (0.0, pulse) if beats_per_bar >= 3.0 else (0.0,)
    elif numerator == 7 and denominator == 8:
        primary = (0.0, 2.0)
    elif beats_per_bar >= 4.0:
        primary = (0.0, 2.0)
    else:
        primary = (0.0,)

    phrase_bars = max(1, min(32, int(_finite(phrase_bars, 4))))
    phrase_start = downbeat and (bar_index % phrase_bars == 0)

    if role == "kick":
        if any(_near(beat_in_bar, point) for point in primary):
            return ANCHOR, 1.0
        if on_quarter:
            return SUPPORT, .72
        return ORNAMENT, .25

    if role in ("snare", "clap"):
        if denominator == 8 and numerator % 3 == 0:
            backbeats = (1.5,) if beats_per_bar >= 3.0 else ()
        elif numerator == 7 and denominator == 8:
            backbeats = (1.0,)
        elif beats_per_bar >= 4.0:
            backbeats = (1.0, 3.0)
        elif beats_per_bar >= 3.0:
            backbeats = (1.0,)
        else:
            backbeats = (beats_per_bar / 2.0,)
        if any(_near(beat_in_bar, point) for point in backbeats):
            return ANCHOR, 1.0
        if on_quarter:
            return SUPPORT, .68
        return ORNAMENT, .25

    if role in ("closed_hat", "open_hat"):
        if downbeat:
            return ANCHOR, 1.0
        if on_eighth:
            return SUPPORT, .68
        return ORNAMENT, .25

    if role == "BASS":
        if any(_near(beat_in_bar, point) for point in primary):
            return ANCHOR, 1.0
        if on_quarter:
            return SUPPORT, .72
        return ORNAMENT, .25

    if role in ("tom", "perc", "PERCUSSION", "DRUM"):
        if downbeat:
            return ANCHOR, 1.0
        if on_quarter:
            return SUPPORT, .62
        return ORNAMENT, .25

    if role in ("CHORD", "PAD"):
        if downbeat:
            return ANCHOR, 1.0
        if on_quarter:
            return SUPPORT, .72
        return ORNAMENT, .25

    # Melodic phrases: the first downbeat of each phrase is an anchor;
    # quarter-note events are structural support, subdivisions are ornaments.
    if phrase_awareness and phrase_start:
        return ANCHOR, 1.0
    if on_quarter:
        return SUPPORT, .68
    return ORNAMENT, .25

def class_probability(parameters, event_class):
    key = CLASS_PARAMETER.get(str(event_class).lower())
    if key is None:
        return 1.0
    return max(0.0, min(1.0, _finite((parameters or {}).get(key, DEFAULT_CLASS_PROBABILITIES[key]), 1.0)))


def density_probability(event_class, density, variation=.5):
    """Density preserves anchors; Variation only changes ornament survival.

    Density 0 remains an explicit silence control. The default Variation .5
    is neutral (factor 1); lower values thin ornaments while higher values
    retain all available ornaments.
    """
    density = max(0.0, min(1.0, _finite(density, 1.0)))
    if density <= 0.0:
        return 0.0
    event_class = str(event_class).lower()
    if event_class == ANCHOR:
        return 1.0
    if event_class == ORNAMENT:
        variation = max(0.0, min(1.0, _finite(variation, .5)))
        return density * min(1.0, variation * 2.0)
    return density
