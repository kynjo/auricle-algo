"""MIDI input learning and deterministic controller-to-parameter mapping."""
from __future__ import annotations

import math
import uuid

SUPPORTED_INPUT_TYPES = ("cc", "note", "pitchwheel", "aftertouch", "polytouch")
MAX_MAPPINGS = 512


def _finite(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return value if math.isfinite(value) else float(default)


def normalize_mapping(raw):
    raw = raw if isinstance(raw, dict) else {}
    source = raw.get("source", {}) if isinstance(raw.get("source"), dict) else {}
    target = raw.get("target", {}) if isinstance(raw.get("target"), dict) else {}
    kind = str(source.get("type", "cc")).lower()
    if kind not in SUPPORTED_INPUT_TYPES:
        kind = "cc"
    channel = source.get("channel")
    try:
        channel = None if channel in (None, "", "omni") else max(0, min(15, int(channel)))
    except (TypeError, ValueError, OverflowError):
        channel = None
    number = source.get("number")
    if kind in ("cc", "note", "polytouch"):
        try:
            number = max(0, min(127, int(number)))
        except (TypeError, ValueError, OverflowError):
            number = 0
    else:
        number = None
    target_kind = str(target.get("kind", "block_parameter"))
    if target_kind not in ("block_parameter", "global_macro"):
        target_kind = "block_parameter"
    result_target = {"kind": target_kind}
    if target_kind == "block_parameter":
        try:
            result_target["block_id"] = int(target.get("block_id"))
        except (TypeError, ValueError, OverflowError):
            return None
        parameter = str(target.get("parameter", ""))[:96]
        if not parameter:
            return None
        result_target["parameter"] = parameter
        result_target["integer"] = bool(target.get("integer", False))
    else:
        try:
            result_target["macro_index"] = max(0, min(3, int(target.get("macro_index", 0))))
        except (TypeError, ValueError, OverflowError):
            result_target["macro_index"] = 0
    lo = _finite(raw.get("min", 0.0), 0.0)
    hi = _finite(raw.get("max", 1.0), 1.0)
    if hi < lo:
        lo, hi = hi, lo
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex)[:64],
        "enabled": bool(raw.get("enabled", True)),
        "source": {
            "port": str(source.get("port", ""))[:256],
            "type": kind,
            "channel": channel,
            "number": number,
        },
        "target": result_target,
        "min": lo,
        "max": hi,
        "curve": str(raw.get("curve", "linear")).lower() if str(raw.get("curve", "linear")).lower() in ("linear", "smooth", "exp") else "linear",
        "pickup": bool(raw.get("pickup", True)),
        "initial": _finite(raw.get("initial", lo), lo),
    }


def normalize_mappings(raw):
    if not isinstance(raw, (list, tuple)):
        return []
    result, ids = [], set()
    for item in raw[:MAX_MAPPINGS]:
        mapping = normalize_mapping(item)
        if mapping is None:
            continue
        base = mapping["id"]
        suffix = 2
        while mapping["id"] in ids:
            mapping["id"] = f"{base[:56]}-{suffix}"
            suffix += 1
        ids.add(mapping["id"])
        result.append(mapping)
    return result


def decode_input_message(message):
    """Convert a mido input message to a normalized source/value record."""
    kind = getattr(message, "type", "")
    channel = getattr(message, "channel", None)
    if channel is not None:
        channel = int(channel)
    if kind == "control_change":
        return {"type": "cc", "channel": channel, "number": int(message.control),
                "value": max(0, min(127, int(message.value))) / 127.0}
    if kind == "note_on" and int(getattr(message, "velocity", 0)) > 0:
        return {"type": "note", "channel": channel, "number": int(message.note),
                "value": max(0, min(127, int(message.velocity))) / 127.0}
    if kind == "pitchwheel":
        return {"type": "pitchwheel", "channel": channel, "number": None,
                "value": max(0.0, min(1.0, (int(message.pitch) + 8192) / 16383.0))}
    if kind == "aftertouch":
        return {"type": "aftertouch", "channel": channel, "number": None,
                "value": max(0, min(127, int(message.value))) / 127.0}
    if kind == "polytouch":
        return {"type": "polytouch", "channel": channel, "number": int(message.note),
                "value": max(0, min(127, int(message.value))) / 127.0}
    return None


def mapping_matches(mapping, port, event):
    mapping = normalize_mapping(mapping)
    if mapping is None or not mapping["enabled"] or event is None:
        return False
    source = mapping["source"]
    return (source["type"] == event["type"]
            and (not source["port"] or source["port"] == str(port))
            and (source["channel"] is None or source["channel"] == event["channel"])
            and (source["number"] is None or source["number"] == event["number"]))


def shape_value(value, curve="linear"):
    value = max(0.0, min(1.0, _finite(value)))
    if curve == "smooth":
        return value * value * (3.0 - 2.0 * value)
    if curve == "exp":
        return value * value
    return value


class MidiLearnRuntime:
    """Soft-takeover state for mappings; project mappings remain plain JSON."""
    def __init__(self):
        self._pickup = {}

    def reset(self):
        self._pickup.clear()

    def prime(self, mapping_id, input_value):
        self._pickup[str(mapping_id)] = {"last": max(0.0, min(1.0, _finite(input_value))), "picked": False}

    def value_for(self, mapping, port, event, current_value):
        """Return a mapped target value, or None until soft takeover is acquired."""
        normalized = normalize_mapping(mapping)
        if normalized is None or not mapping_matches(normalized, port, event):
            return None
        raw = max(0.0, min(1.0, _finite(event["value"])))
        shaped = shape_value(raw, normalized["curve"])
        state = self._pickup.setdefault(normalized["id"], {"last": None, "picked": not normalized["pickup"]})
        current = normalized["min"] if normalized["max"] == normalized["min"] else current_value
        try:
            current_norm = (float(current) - normalized["min"]) / max(1e-12, normalized["max"] - normalized["min"])
        except (TypeError, ValueError, OverflowError):
            current_norm = 0.0
        current_norm = max(0.0, min(1.0, current_norm))
        if normalized["pickup"] and not state["picked"]:
            previous = state["last"]
            # Compare in target space. Comparing an unshaped CC against a
            # shaped target acquires exp/smooth mappings before pickup and
            # makes the first applied value jump away from the current value.
            previous = None if previous is None else shape_value(previous, normalized["curve"])
            crossed = previous is not None and (previous - current_norm) * (shaped - current_norm) <= 0.0
            near = abs(shaped - current_norm) <= 0.025
            state["last"] = raw
            if not (crossed or near):
                return None
            state["picked"] = True
        else:
            state["last"] = raw
        return normalized["min"] + (normalized["max"] - normalized["min"]) * shaped

    def remove(self, mapping_id):
        self._pickup.pop(str(mapping_id), None)


__all__ = ["SUPPORTED_INPUT_TYPES", "normalize_mapping", "normalize_mappings",
           "decode_input_message", "mapping_matches", "shape_value", "MidiLearnRuntime"]
