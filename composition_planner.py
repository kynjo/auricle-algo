"""Section-based composition form and deterministic runtime controls.

The planner is project data first: its helpers do not depend on Qt, MIDI, or
wall-clock timers. Sections are measured in quarter-note beats and are resolved
against the shared transport clock, so SEQ and LIVE read the same form.
"""
from __future__ import annotations

import colorsys
import re
import hashlib
import math
import uuid
from composition_automation import normalize_curve, section_macro
from section_automation import normalize_tracks
from composition_performance import normalize_performance
from musical_clock import MusicalGrid
from midi_expression import normalize_expression_override

SECTION_TYPES = ("Intro", "Verse", "Build", "Drop", "Break", "Bridge", "Transition", "Outro")
SECTION_COLORS = {"Intro": "#68a9ff", "Verse": "#b98be8", "Build": "#4fc99d",
                  "Drop": "#ee7890", "Break": "#d8b05b", "Bridge": "#55c7d4",
                  "Transition": "#ed995f", "Outro": "#91a0d8"}


def section_color(section):
    value = section.get("color")
    return value.lower() if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else SECTION_COLORS.get(section.get("type"), SECTION_COLORS["Verse"])


def available_section_color(sections, preferred):
    used = {section_color(section) for section in sections}
    if preferred.lower() not in used:
        return preferred.lower()
    r, g, b = (int(preferred[i:i+2], 16) / 255 for i in (1, 3, 5))
    hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
    for index in range(1, 129):
        rgb = colorsys.hsv_to_rgb((hue + index * .073) % 1, saturation, value)
        color = "#" + "".join(f"{round(v * 255):02x}" for v in rgb)
        if color not in used:
            return color
    return preferred.lower()


METERS = ("2/4", "3/4", "4/4", "5/4", "6/8", "7/8", "12/8")
MACRO_KEYS = ("energy", "tension", "density", "variation")
MACRO_LABELS = {"energy": "Energy", "tension": "Tension", "density": "Density", "variation": "Variation"}
END_ACTIONS = (("loop", "Loop form"), ("stop", "Stop at end"), ("hold", "Hold last section"))
CONTROLLED_PARAMETERS = (
    ("Section macros", "Energy · Tension · Density · Variation"),
    ("Block / Drum Voice", "Active · Density · Velocity · Register Center · Variation"),
    ("Expression", "Gate · Accent · Octave spread · Harmony"),
    ("Section performance", "Phrase · Amount · Targets · Duration · per-instrument Technique / Shape / Fit"),
)
METER_BEATS = {meter: int(meter.split("/")[0]) * 4.0 / int(meter.split("/")[1]) for meter in METERS}

# Event-stage expression controls; never overwrite a generator's manual values.
EXPRESSION_SPECS = {
    "gate": ("Gate", 1.0, .25, 2.0, .05,
             "Note duration multiplier; final MIDI gate is limited to 1.5 steps."),
    "accent": ("Accent", 0.0, 0.0, 1.0, .05,
               "Emphasize meter accents and soften weak subdivisions."),
    "octave_spread": ("Octave spread", 0.0, 0.0, 1.0, .05,
                      "Probability of shifting a complete event by one octave within its role register. Pitched blocks only."),
    "harmony": ("Harmony", 1.0, 0.0, 1.5, .05,
                "Chord-tone anchoring multiplier for BASS/MELODY following Harmonic Plan; zero frees the line."),
}


def expression_settings(raw):
    return {key: _clamp(raw.get(key, spec[1]), spec[2], spec[3]) for key, spec in EXPRESSION_SPECS.items()}

# Values are starter suggestions, not locked behaviours. Users can edit every
# section and every block after inserting it.
TYPE_MACRO_PRESETS = {
    "Intro":      {"energy": .30, "tension": .25, "density": .36, "variation": .20},
    "Verse":      {"energy": .55, "tension": .40, "density": .58, "variation": .32},
    "Build":      {"energy": .72, "tension": .76, "density": .76, "variation": .68},
    "Drop":       {"energy": .94, "tension": .72, "density": .92, "variation": .58},
    "Break":      {"energy": .25, "tension": .46, "density": .28, "variation": .24},
    "Bridge":     {"energy": .54, "tension": .62, "density": .54, "variation": .60},
    "Transition": {"energy": .62, "tension": .72, "density": .62, "variation": .74},
    "Outro":      {"energy": .30, "tension": .22, "density": .32, "variation": .18},
}

# Per-block Density is a keep multiplier, Velocity is a multiplier, Transpose
# is in semitones, and Variation adds deterministic velocity motion.
ROLE_PRESETS = {
    "Intro":      {"DRUM": (.55, .76, .10), "BASS": (.68, .80, .08), "MELODY": (.48, .82, .10), "CHORD": (.68, .78, .06), "PAD": (.90, .82, .04), "PERCUSSION": (.42, .68, .12)},
    "Verse":      {"DRUM": (.78, .90, .16), "BASS": (.82, .92, .12), "MELODY": (.72, .90, .16), "CHORD": (.76, .86, .10), "PAD": (.80, .78, .06), "PERCUSSION": (.62, .82, .18)},
    "Build":      {"DRUM": (.92, .96, .28), "BASS": (.82, .94, .20), "MELODY": (.86, .94, .26), "CHORD": (.76, .88, .16), "PAD": (.66, .82, .12), "PERCUSSION": (.84, .90, .30)},
    "Drop":       {"DRUM": (1.00, 1.00, .22), "BASS": (.98, 1.00, .18), "MELODY": (.92, .96, .22), "CHORD": (.86, .90, .14), "PAD": (.56, .78, .10), "PERCUSSION": (.94, .94, .26)},
    "Break":      {"DRUM": (.20, .72, .12), "BASS": (.42, .78, .10), "MELODY": (.74, .88, .18), "CHORD": (.62, .80, .10), "PAD": (.86, .86, .08), "PERCUSSION": (.22, .66, .14)},
    "Bridge":     {"DRUM": (.62, .86, .22), "BASS": (.72, .88, .18), "MELODY": (.82, .92, .24), "CHORD": (.74, .86, .16), "PAD": (.78, .82, .12), "PERCUSSION": (.62, .80, .24)},
    "Transition": {"DRUM": (.72, .88, .30), "BASS": (.68, .86, .24), "MELODY": (.78, .90, .30), "CHORD": (.66, .82, .18), "PAD": (.62, .78, .16), "PERCUSSION": (.80, .82, .32)},
    "Outro":      {"DRUM": (.36, .78, .10), "BASS": (.48, .82, .08), "MELODY": (.42, .82, .10), "CHORD": (.62, .82, .06), "PAD": (.82, .84, .04), "PERCUSSION": (.30, .70, .10)},
}


def _clamp(value, low=0.0, high=1.0):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = low
    if not math.isfinite(number):
        number = low
    return max(low, min(high, number))


def _section_id():
    return "sec-" + uuid.uuid4().hex[:10]


def default_composition():
    """Neutral, disabled starter form: opening projects keep their old sound."""
    return {
        "enabled": False,
        "meter": "4/4",
        "loop": True,
        "end_action": "hold",
        "sections": [{
            "id": "section-1", "type": "Verse", "name": "Main", "bars": 8,
            "macros": {key: None for key in MACRO_KEYS},
            "blocks": {}, "macro_curves": {}, "midi_automation": {}, "parameter_automation": [], "transition_bars": 0.0,
            "color": SECTION_COLORS["Verse"], "performance": normalize_performance(),
        }],
    }


def normalize_composition(data):
    """Return a safe composition document while preserving valid user values."""
    if not isinstance(data, dict):
        data = {}
    meter = str(data.get("meter", "4/4"))
    if meter not in METERS:
        meter = "4/4"
    raw_sections = data.get("sections")
    if not isinstance(raw_sections, (list, tuple)):
        raw_sections = []
    sections = []
    used_ids = set()
    for index, raw in enumerate(raw_sections[:128]):
        if not isinstance(raw, dict):
            continue
        section_type = str(raw.get("type", "Verse"))
        if section_type not in SECTION_TYPES:
            section_type = "Verse"
        sid = str(raw.get("id") or _section_id())[:80]
        if sid in used_ids:
            sid = _section_id()
        used_ids.add(sid)
        name = str(raw.get("name") or section_type).strip()[:80] or section_type
        try:
            bars = max(1, min(128, int(raw.get("bars", 4))))
        except (TypeError, ValueError, OverflowError):
            bars = 4
        raw_macros = raw.get("macros") if isinstance(raw.get("macros"), dict) else {}
        macros = {}
        for key in MACRO_KEYS:
            value = raw_macros.get(key)
            macros[key] = None if value is None else _clamp(value)
        raw_curves = raw.get("macro_curves") if isinstance(raw.get("macro_curves"), dict) else {}
        curves = {key: curve for key in MACRO_KEYS
                  if (curve := normalize_curve(raw_curves.get(key), macros[key] if macros[key] is not None else .5)) is not None}
        raw_blocks = raw.get("blocks") if isinstance(raw.get("blocks"), dict) else {}
        raw_automation = raw.get("midi_automation") if isinstance(raw.get("midi_automation"), dict) else {}
        midi_automation = {str(key): normalize_expression_override(value) for key, value in raw_automation.items()
                           if isinstance(value, dict) and value}
        blocks = {}
        for block_id, raw_setting in raw_blocks.items():
            if not isinstance(raw_setting, dict):
                continue
            blocks[str(block_id)] = {
                "enabled": bool(raw_setting.get("enabled", True)),
                "density": _clamp(raw_setting.get("density", 1.0), 0.0, 1.0),
                "velocity": _clamp(raw_setting.get("velocity", 1.0), 0.0, 1.5),
                "register_center": _clamp(raw_setting.get("register_center", 0), -24, 24),
                "variation": _clamp(raw_setting.get("variation", 0.0), 0.0, 1.0),
                **expression_settings(raw_setting),
            }
        sections.append({"id": sid, "type": section_type, "name": name, "bars": bars,
                         "macros": macros, "blocks": blocks, "macro_curves": curves,
                         "midi_automation": midi_automation,
                         "parameter_automation": normalize_tracks(raw.get("parameter_automation")),
                         "color": section_color(raw | {"type": section_type}),
                         "performance": normalize_performance(raw.get("performance")),
                         "transition_bars": _clamp(raw.get("transition_bars", 0.0), 0.0, 8.0)})
    if not sections:
        sections = default_composition()["sections"]
    return {"enabled": bool(data.get("enabled", False)), "meter": meter,
            "loop": bool(data.get("loop", True)),
            "end_action": "stop" if data.get("end_action") == "stop" else "hold", "sections": sections}


def block_role(block):
    if bool(getattr(block, "is_drum_voice", False)):
        name = str(getattr(block, "name", "")).upper()
        if "KICK" in name or "BASS DRUM" in name: return "DRUM"
        if "SNARE" in name or "CLAP" in name: return "DRUM"
        if "HAT" in name or "CYMBAL" in name: return "PERCUSSION"
        return "PERCUSSION"
    role = str(getattr(block, "block_type", "MELODY")).upper()
    return role if role in ("DRUM", "BASS", "MELODY", "CHORD", "PAD", "PERCUSSION") else "MELODY"


def default_block_settings(section_type, block):
    role = block_role(block)
    density, velocity, variation = ROLE_PRESETS.get(section_type, ROLE_PRESETS["Verse"]).get(role, (.75, .9, .12))
    return {"enabled": True, "density": density, "velocity": velocity,
            "register_center": 0.0, "variation": variation, **expression_settings({})}


def make_section(section_type="Verse", blocks=(), bars=4, name=None, neutral=False):
    if section_type not in SECTION_TYPES:
        section_type = "Verse"
    macros = {key: None for key in MACRO_KEYS} if neutral else dict(TYPE_MACRO_PRESETS[section_type])
    block_settings = {str(int(block.id)): default_block_settings(section_type, block) for block in blocks}
    return {"id": _section_id(), "type": section_type,
            "name": str(name or section_type), "bars": max(1, min(128, int(bars))),
            "macros": macros, "blocks": block_settings, "macro_curves": {}, "midi_automation": {}, "parameter_automation": [], "transition_bars": .25,
            "color": SECTION_COLORS[section_type], "performance": normalize_performance()}


def deterministic_sample(seed, block_id, section_id, beat, salt="density"):
    slot = int(round(max(0.0, float(beat)) * 960.0))
    payload = f"{int(seed)}|{int(block_id)}|{section_id}|{slot}|{salt}".encode("utf-8")
    raw = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(raw, "big") / float(1 << 64)


class CompositionRuntime:
    """Resolve the active section and its per-block/global macro settings."""
    def __init__(self, project):
        self.project = project
        # None keeps stopped/standalone editing previews. Playback overrides
        # are transient and never change the saved Enable composition flag.
        self.playback_active = None

    def config(self):
        data = getattr(self.project, "composition", None)
        sections = data.get("sections") if isinstance(data, dict) else None
        malformed = (not isinstance(data, dict) or not isinstance(sections, list) or not sections
                     or any(key not in data for key in ("enabled", "meter", "loop")))
        if not malformed:
            malformed = any(not isinstance(section, dict) or "bars" not in section or "blocks" not in section
                            for section in sections)
        if malformed:
            data = normalize_composition(data if isinstance(data, dict) else default_composition())
            self.project.composition = data
        if data.get("meter") not in METERS:
            data["meter"] = "4/4"
        return data

    def enabled(self):
        return self.playback_active is not False and bool(self.config().get("enabled", False))

    def bar_beats(self):
        config = self.config()
        meter = str(config.get("meter", "4/4"))
        try:
            numerator, denominator = (int(part) for part in meter.split("/", 1))
            return MusicalGrid.from_meter(numerator, denominator).beats_per_bar
        except (TypeError, ValueError, ZeroDivisionError):
            return METER_BEATS.get(meter, 4.0)

    def total_bars(self):
        return sum(max(1, int(section.get("bars", 1))) for section in self.config().get("sections", []))

    def total_beats(self):
        return self.total_bars() * self.bar_beats()

    def ending(self):
        config = self.config()
        return "loop" if config["loop"] else "stop" if config.get("end_action") == "stop" else "hold"

    def finished(self, beat):
        return self.enabled() and self.ending() == "stop" and float(beat) >= self.total_beats() - 1e-9

    def section_start(self, section_id):
        beats = 0.0
        for section in self.config()["sections"]:
            if section["id"] == section_id:
                return beats
            beats += max(1, int(section["bars"])) * self.bar_beats()
        return 0.0

    def context(self, beat=0.0):
        config = self.config()
        sections = config["sections"]
        bar_beats = self.bar_beats()
        total_bars = sum(max(1, min(128, int(section.get("bars", 1)))) for section in sections)
        total_beats = total_bars * bar_beats
        beat = max(0.0, float(beat or 0.0))
        cycle = int(beat // total_beats) if config["loop"] and total_beats > 0 else 0
        local = beat % total_beats if config["loop"] and total_beats > 0 else min(beat, total_beats)
        cursor = 0.0
        start_bar = 0
        for index, section in enumerate(sections):
            duration = max(1, min(128, int(section.get("bars", 1)))) * bar_beats
            end = cursor + duration
            if local < end - 1e-9 or index == len(sections) - 1:
                section_local = max(0.0, local - cursor)
                section_bars = max(1, min(128, int(section.get("bars", 1))))
                bar_in_section = min(section_bars, int(section_local // bar_beats) + 1)
                total_bar = cycle * total_bars + start_bar + bar_in_section
                return {"index": index, "section": section, "section_id": str(section.get("id", f"section-{index+1}")),
                        "start_beat": cycle * total_beats + cursor,
                        "end_beat": cycle * total_beats + end,
                        "local_beat": section_local, "section_bar": bar_in_section,
                        "bar": total_bar, "bar_beats": bar_beats,
                        "section_progress": _clamp(section_local / max(.001, duration)),
                        "total_bars": total_bars, "total_beats": total_beats,
                        "cycle": cycle, "loop": config["loop"]}
            cursor = end
            start_bar += section["bars"]
        # normalize_composition always returns at least one section.
        return {"index": 0, "section": sections[0], "section_id": str(sections[0].get("id", "section-1")),
                "start_beat": 0.0, "end_beat": total_beats, "local_beat": 0.0,
                "section_bar": 1, "bar": 1, "bar_beats": bar_beats,
                "section_progress": 0.0, "total_bars": total_bars,
                "total_beats": total_beats, "cycle": 0, "loop": config["loop"]}

    def block_settings(self, section, block_id):
        raw = section.get("blocks", {}).get(str(int(block_id)), {})
        return {"enabled": bool(raw.get("enabled", True)),
                "density": _clamp(raw.get("density", 1.0)),
                "velocity": _clamp(raw.get("velocity", 1.0), 0.0, 1.5),
                "register_center": _clamp(raw.get("register_center", 0), -24, 24),
                "variation": _clamp(raw.get("variation", 0.0)), **expression_settings(raw)}

    def effective_macros(self, section, global_values, context=None):
        progress = context["section_progress"] if context is not None else 0.0
        values = {key: section_macro(section, key, global_values, progress) for key in MACRO_KEYS}
        if context is None:
            return values
        # Blend from the previous endpoint, including the loop seam. The first
        # start has no outgoing section and uses its own authored first point.
        sections = self.config()["sections"]
        index = context["index"]
        if index == 0 and not (context["loop"] and context["cycle"] > 0):
            return values
        duration = max(0., context["end_beat"] - context["start_beat"])
        overlap = min(duration, _clamp(section.get("transition_bars", 0), 0, 8) * context["bar_beats"])
        if overlap <= 0 or context["local_beat"] >= overlap:
            return values
        previous = sections[index - 1]
        t = _clamp(context["local_beat"] / overlap)
        t = t * t * (3.0 - 2.0 * t)
        return {key: section_macro(previous, key, global_values, 1.0) * (1. - t) + value * t
                for key, value in values.items()}

    def macro_is_active(self, context, key, global_values):
        section = context["section"]
        if section.get("macros", {}).get(key) is not None:
            return True
        value = self.effective_macros(section, global_values, context)[key]
        return abs(value - float(global_values.get(key, .5))) > 1e-9

    def context_at(self, beat):
        if not self.enabled():
            return None
        return self.context(beat)

    def block_is_enabled(self, block_id, beat):
        context = self.context_at(beat)
        if context is None:
            return True
        return self.block_settings(context["section"], block_id)["enabled"]

    def effective_tension(self, beat, global_values):
        context = self.context_at(beat)
        if context is None:
            return None
        return self.effective_macros(context["section"], global_values, context)["tension"]
