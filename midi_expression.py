"""Deterministic, beat-synchronised MIDI expression automation.

The module is deliberately independent of Qt and the transport. Project data is
plain JSON-compatible dictionaries; runtime sampling returns small command
records that the MIDI transport converts to mido messages.
"""
from __future__ import annotations

from copy import deepcopy
import math

CURVE_SHAPES = ("linear", "smooth", "step")
AFTERTOUCH_MODES = ("channel", "polyphonic")
MAX_CC_LANES = 16


def _finite(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return result if math.isfinite(result) else float(default)


def _clamp(value, low, high, default=None):
    if default is None:
        default = low
    return max(low, min(high, _finite(value, default)))


def _points(raw, default_points):
    values = {}
    if isinstance(raw, (list, tuple)):
        for point in raw[:64]:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            x = _finite(point[0], -1)
            y = _finite(point[1], -1)
            if 0 <= x <= 1 and 0 <= y <= 1:
                values[round(x, 6)] = y
    if not values:
        values = {float(x): float(y) for x, y in default_points}
    ordered = sorted(values.items())
    values.setdefault(0.0, ordered[0][1])
    values.setdefault(1.0, ordered[-1][1])
    return [[float(x), float(y)] for x, y in sorted(values.items())]


def _shape(value):
    value = str(value or "smooth").lower()
    return value if value in CURVE_SHAPES else "smooth"


def _normalize_lane(raw, index=0):
    raw = raw if isinstance(raw, dict) else {}
    controller = int(_clamp(raw.get("controller", 74), 0, 119, 74))
    lane_id = str(raw.get("id") or f"cc-{controller}-{index + 1}")[:64]
    low = int(_clamp(raw.get("min", 0), 0, 127, 0))
    high = int(_clamp(raw.get("max", 127), 0, 127, 127))
    if high < low:
        low, high = high, low
    return {
        "id": lane_id,
        "enabled": bool(raw.get("enabled", False)),
        "controller": controller,
        "min": low,
        "max": high,
        "period_beats": _clamp(raw.get("period_beats", 4.0), 0.0625, 1024.0, 4.0),
        "rate_beats": _clamp(raw.get("rate_beats", 0.25), 0.0625, 64.0, 0.25),
        "phase_beats": _clamp(raw.get("phase_beats", 0.0), -1024.0, 1024.0, 0.0),
        "timebase": "section" if raw.get("timebase") == "section" else "loop",
        "shape": _shape(raw.get("shape")),
        "points": _points(raw.get("points"), ((0.0, 0.0), (1.0, 1.0))),
    }


def _normalize_continuous(raw, kind):
    raw = raw if isinstance(raw, dict) else {}
    if kind == "pitch_bend":
        return {
            "enabled": bool(raw.get("enabled", False)),
            "range_semitones": int(_clamp(raw.get("range_semitones", 2), 1, 24, 2)),
            "period_beats": _clamp(raw.get("period_beats", 4.0), 0.0625, 1024.0, 4.0),
            "rate_beats": _clamp(raw.get("rate_beats", 0.25), 0.0625, 64.0, 0.25),
            "phase_beats": _clamp(raw.get("phase_beats", 0.0), -1024.0, 1024.0, 0.0),
            "timebase": "section" if raw.get("timebase") == "section" else "loop",
            "shape": _shape(raw.get("shape")),
            # 0.5 is the neutral pitch-bend position.
            "points": _points(raw.get("points"), ((0.0, 0.5), (1.0, 0.5))),
        }
    mode = str(raw.get("mode", "channel")).lower()
    return {
        "enabled": bool(raw.get("enabled", False)),
        "mode": mode if mode in AFTERTOUCH_MODES else "channel",
        "sensitivity": _clamp(raw.get("sensitivity", 1.0), 0.0, 2.0, 1.0),
        "period_beats": _clamp(raw.get("period_beats", 4.0), 0.0625, 1024.0, 4.0),
        "rate_beats": _clamp(raw.get("rate_beats", 0.25), 0.0625, 64.0, 0.25),
        "phase_beats": _clamp(raw.get("phase_beats", 0.0), -1024.0, 1024.0, 0.0),
        "timebase": "section" if raw.get("timebase") == "section" else "loop",
        "shape": _shape(raw.get("shape")),
        "points": _points(raw.get("points"), ((0.0, 0.0), (1.0, 0.0))),
    }


def normalize_expression(raw):
    """Return a bounded, JSON-safe expression document."""
    raw = raw if isinstance(raw, dict) else {}
    raw_lanes = raw.get("cc_lanes", [])
    if not isinstance(raw_lanes, (list, tuple)):
        raw_lanes = []
    lanes = []
    used_ids = set()
    used_controllers = set()
    for index, item in enumerate(raw_lanes[:MAX_CC_LANES]):
        lane = _normalize_lane(item, index)
        # Two lanes on the same MIDI channel cannot independently drive the
        # same CC number; keep the first lane to avoid order-dependent output.
        if lane["controller"] in used_controllers:
            continue
        used_controllers.add(lane["controller"])
        base = lane["id"]
        suffix = 2
        while lane["id"] in used_ids:
            lane["id"] = f"{base[:58]}-{suffix}"
            suffix += 1
        used_ids.add(lane["id"])
        lanes.append(lane)
    return {
        "cc_lanes": lanes,
        "pitch_bend": _normalize_continuous(raw.get("pitch_bend"), "pitch_bend"),
        "aftertouch": _normalize_continuous(raw.get("aftertouch"), "aftertouch"),
    }


def normalize_midi_sync(raw):
    raw = raw if isinstance(raw, dict) else {}
    port = str(raw.get("clock_port", "*") or "*")
    return {
        "clock_out": bool(raw.get("clock_out", False)),
        "transport_messages": bool(raw.get("transport_messages", False)),
        "song_position_pointer": bool(raw.get("song_position_pointer", True)),
        "clock_port": port[:256],
    }


def normalize_expression_override(raw):
    """Normalize only explicitly supplied section override dimensions."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    if "cc_lanes" in raw:
        result["cc_lanes"] = normalize_expression({"cc_lanes": raw.get("cc_lanes")})["cc_lanes"]
    if isinstance(raw.get("pitch_bend"), dict):
        result["pitch_bend"] = _normalize_continuous(raw["pitch_bend"], "pitch_bend")
    if isinstance(raw.get("aftertouch"), dict):
        result["aftertouch"] = _normalize_continuous(raw["aftertouch"], "aftertouch")
    return result


def merge_expression_configs(base, override):
    """Merge a sparse override over a base config; CC lanes replace as a set."""
    base = normalize_expression(base)
    if not isinstance(override, dict) or not override:
        return base
    merged = deepcopy(base)
    if "cc_lanes" in override:
        merged["cc_lanes"] = normalize_expression({"cc_lanes": override.get("cc_lanes")})["cc_lanes"]
    for key in ("pitch_bend", "aftertouch"):
        if isinstance(override.get(key), dict):
            merged[key] = _normalize_continuous(merged[key] | override[key], key)
    return normalize_expression(merged)


def entity_expression_config(entity, parent=None, section=None):
    """Resolve parent kit -> voice/block -> section precedence."""
    config = normalize_expression(getattr(parent, "midi_expression", {}) if parent is not None else {})
    own = getattr(entity, "midi_expression", {})
    if isinstance(own, dict) and own:
        config = merge_expression_configs(config, own)
    if isinstance(section, dict):
        overrides = section.get("midi_automation", {})
        override = overrides.get(str(int(entity.id))) if isinstance(overrides, dict) else None
        if isinstance(override, dict) and override:
            config = merge_expression_configs(config, override)
    return config


def curve_value(points, progress, shape="smooth"):
    """Evaluate a normalized curve with bounded, non-overshooting segments."""
    pts = _points(points, ((0.0, 0.0), (1.0, 1.0)))
    x = _clamp(progress, 0.0, 1.0, 0.0)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            t = (x - x0) / max(1e-12, x1 - x0)
            if shape == "step":
                t = 0.0
            elif shape == "smooth":
                t = t * t * (3.0 - 2.0 * t)
            return max(0.0, min(1.0, y0 + (y1 - y0) * t))
    return pts[-1][1]


def _phase(raw, beat, context):
    if raw.get("timebase") == "section" and context is not None:
        return _clamp(context.get("section_progress", 0.0), 0.0, 1.0, 0.0)
    period = max(1e-9, float(raw.get("period_beats", 4.0)))
    phase = float(beat) + float(raw.get("phase_beats", 0.0))
    return (phase % period) / period


def _sample_beat(raw, beat, context):
    if raw.get("timebase") == "section" and context is not None:
        return max(0.0, _finite(context.get("local_beat", 0.0)))
    return max(0.0, _finite(beat))


class MidiExpressionRuntime:
    """Rate-limited deterministic sampler for CC, Pitch Bend and Aftertouch."""
    def __init__(self):
        self._slots = {}
        self._last_values = {}
        self._signatures = {}

    def reset(self):
        self._slots.clear()
        self._last_values.clear()
        self._signatures.clear()

    def note_released(self, owner_id, note):
        """Allow a retriggered pitch to receive poly pressure in the same slot."""
        owner_id = int(owner_id)
        key = (owner_id, "aftertouch_notes", "main")
        notes = tuple(value for value in self._last_values.get(key, ()) if value != int(note))
        self._last_values[key] = notes
        self._slots.pop((owner_id, "aftertouch", "main"), None)

    @staticmethod
    def _signature(lane):
        # A tuple avoids JSON serialisation in the hot path.
        return (lane.get("enabled"), lane.get("controller"), lane.get("min"), lane.get("max"),
                lane.get("period_beats"), lane.get("rate_beats"), lane.get("phase_beats"),
                lane.get("timebase"), lane.get("shape"), tuple(tuple(p) for p in lane.get("points", ())))

    def _due(self, key, lane, beat, context):
        sample_beat = _sample_beat(lane, beat, context)
        rate = max(1e-6, float(lane.get("rate_beats", 0.25)))
        slot = int(math.floor((sample_beat + 1e-9) / rate))
        if self._slots.get(key) == slot:
            return False
        self._slots[key] = slot
        return True

    def sample(self, owner_id, config, beat, context=None, active_notes=(), *, normalized=False):
        # Transport caches normalized configs; avoid re-normalizing each tick.
        if not normalized:
            config = normalize_expression(config)
        owner_id = int(owner_id)
        commands = []

        for lane in config["cc_lanes"]:
            if not lane["enabled"]:
                continue
            key = (owner_id, "cc", lane["id"])
            signature = self._signature(lane)
            if not self._due(key, lane, beat, context):
                continue
            progress = _phase(lane, beat, context)
            raw = curve_value(lane["points"], progress, lane["shape"])
            value = int(round(lane["min"] + raw * (lane["max"] - lane["min"])))
            if self._signatures.get(key) != signature or self._last_values.get(key) != value:
                commands.append({"type": "control_change", "lane_id": lane["id"],
                                 "control": lane["controller"], "value": value})
                self._last_values[key] = value
                self._signatures[key] = signature

        bend = config["pitch_bend"]
        if bend["enabled"]:
            key = (owner_id, "pitch_bend", "main")
            signature = self._signature(bend) + (bend["range_semitones"],)
            if self._due(key, bend, beat, context):
                raw = curve_value(bend["points"], _phase(bend, beat, context), bend["shape"])
                value = int(max(-8192, min(8191, round(raw * 16383.0 - 8191.5))))
                if self._signatures.get(key) != signature or self._last_values.get(key) != value:
                    commands.append({"type": "pitchwheel", "lane_id": "main", "pitch": value,
                                     "range_semitones": bend["range_semitones"]})
                    self._last_values[key] = value
                    self._signatures[key] = signature

        pressure = config["aftertouch"]
        if pressure["enabled"]:
            key = (owner_id, "aftertouch", "main")
            signature = self._signature(pressure) + (pressure["mode"], pressure["sensitivity"])
            due = self._due(key, pressure, beat, context)
            signature_changed = self._signatures.get(key) != signature
            raw = curve_value(pressure["points"], _phase(pressure, beat, context), pressure["shape"])
            value = int(max(0, min(127, round(raw * 127 * pressure["sensitivity"]))))
            if pressure["mode"] == "polyphonic":
                # Poly pressure is also checked on non-due ticks: a Note On may
                # occur after the first expression pass of this transport tick.
                notes = sorted({int(note) for note in active_notes if 0 <= int(note) <= 127})
                sent_key = (owner_id, "aftertouch_notes", "main")
                sent_notes = set(self._last_values.get(sent_key, ()))
                previous_value = self._last_values.get(key)
                if not notes:
                    # Keep the slot open so a note started later in this same
                    # scheduler interval can receive pressure immediately.
                    self._slots.pop(key, None)
                else:
                    removed_notes = sorted(sent_notes - set(notes))
                    for note in removed_notes:
                        commands.append({"type": "polytouch", "lane_id": "main", "note": note, "value": 0})
                    value_changed = signature_changed or (due and previous_value != value)
                    if value_changed:
                        targets = notes
                    else:
                        # Existing notes need no duplicate pressure packet when
                        # the curve is unchanged; newly started notes do.
                        targets = [note for note in notes if note not in sent_notes]
                    commands.extend({"type": "polytouch", "lane_id": "main", "note": note,
                                     "value": value} for note in targets)
                    if due or signature_changed or previous_value is None:
                        self._last_values[key] = value
                        self._signatures[key] = signature
                    self._last_values[sent_key] = tuple(notes)
            elif due and (signature_changed or self._last_values.get(key) != value):
                commands.append({"type": "aftertouch", "lane_id": "main", "value": value})
                self._last_values[key] = value
                self._signatures[key] = signature
        return commands


__all__ = ["CURVE_SHAPES", "AFTERTOUCH_MODES", "MAX_CC_LANES", "normalize_expression",
           "normalize_expression_override", "normalize_midi_sync", "merge_expression_configs", "entity_expression_config",
           "curve_value", "MidiExpressionRuntime"]
