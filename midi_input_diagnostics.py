"""Bounded, thread-safe observations for the MIDI input / Learn pipeline."""
from __future__ import annotations

from copy import deepcopy
import json
import threading
import time

BUILD = "midi-learn-diagnostics-2"


class MidiInputDiagnostics:
    def __init__(self, port=""):
        self._lock = threading.Lock()
        self._state = {
            "build": BUILD, "requested_port": str(port), "stage": "disconnected",
            "polls": 0, "raw_messages": 0, "decoded_messages": 0,
            "gui_messages": 0, "matched_messages": 0, "queued_changes": 0,
            "last_raw": None, "last_event": None, "last_request": None,
            "error": "", "last_poll": None,
        }

    def poll(self):
        with self._lock:
            self._state["polls"] += 1
            self._state["last_poll"] = time.monotonic()

    def observe(self, message):
        # System Exclusive may contain complete presets: keep its type/length,
        # never its payload. All other input records stay bounded as well.
        raw = {"type": str(getattr(message, "type", "unknown"))}
        for key in ("channel", "control", "value", "note", "velocity", "pitch", "program"):
            value = getattr(message, key, None)
            if isinstance(value, (int, float)):
                raw[key] = value
        if raw["type"] == "sysex":
            raw["data_length"] = len(getattr(message, "data", ()))
        with self._lock:
            self._state["raw_messages"] += 1
            self._state["last_raw"] = raw

    def decoded(self, event):
        with self._lock:
            self._state["decoded_messages"] += 1

    def received(self, event):
        with self._lock:
            self._state["gui_messages"] += 1
            self._state["last_event"] = dict(event)

    def mark(self, stage, **details):
        with self._lock:
            self._state["stage"] = str(stage)
            self._state["details"] = deepcopy(details)
            if stage in ("pickup", "queued", "unchanged"):
                self._state["matched_messages"] += 1
            if stage == "queued":
                self._state["queued_changes"] += 1
                self._state["last_request"] = deepcopy(details)
            if stage == "error":
                self._state["error"] = str(details.get("error", "Unknown error"))

    def snapshot(self):
        with self._lock:
            result = deepcopy(self._state)
        last_poll = result.pop("last_poll")
        result["seconds_since_poll"] = (None if last_poll is None
                                        else round(max(0., time.monotonic() - last_poll), 3))
        return result


def format_diagnostics(snapshot, context):
    """No environment dump, external transmission, or unbounded MIDI log."""
    return json.dumps({"runtime": context, "midi_input": snapshot},
                      ensure_ascii=False, indent=2, allow_nan=False)
