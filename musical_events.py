"""Canonical musical-event model shared by generators and MIDI transport.

Generator output arrays remain backward compatible.  At the transport boundary
those arrays and LIVE dictionaries are normalized into this event model, where
onsets and durations are expressed in quarter-note beats rather than seconds or
ambiguous gate multipliers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
import math


def _number(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return result if math.isfinite(result) else float(default)


def _bounded(value, default, low, high):
    return max(low, min(high, _number(value, default)))


@dataclass(frozen=True)
class MusicalEvent:
    """One normalized note/trigger event on the absolute musical timeline.

    ``gate`` preserves Auricle's legacy ``duration`` multiplier.  The new
    ``duration_beats`` field is the actual musical duration.  Keeping both
    makes old processors compatible while giving scheduling code an
    unambiguous time value.
    """

    beat: float
    interval_beats: float
    duration_beats: float
    pitch: float = 0.0
    pitches: tuple[float, ...] = ()
    velocity: float = 0.8
    gate: float = 0.78
    rhythm: float = 1.0
    probability: float = 1.0
    importance: float = 0.5
    event_class: str = "support"
    source_id: int | None = None
    role: str | None = None
    channel: int | None = None
    port: str | None = None
    composition_slot: int | None = None
    extras: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
        *,
        beat: float | None = None,
        interval_beats: float = 0.25,
        source_id: int | None = None,
        role: str | None = None,
        channel: int | None = None,
        port: str | None = None,
        recompute_duration: bool = False,
    ) -> "MusicalEvent":
        """Normalize a legacy event dictionary without discarding its extras."""
        raw = dict(values or {})
        resolved_beat = _number(raw.get("beat", 0.0) if beat is None else beat)
        gate = _bounded(raw.get("duration", raw.get("gate", 0.78)), 0.78, 0.05, 1.5)
        interval = max(0.0, _number(raw.get("interval_beats", interval_beats), 0.25))
        if not recompute_duration and raw.get("duration_beats") is not None:
            duration_beats = max(0.0, _number(raw.get("duration_beats"), interval * gate))
        else:
            duration_beats = interval * gate

        raw_pitches = raw.get("pitches", ())
        if not isinstance(raw_pitches, (list, tuple)):
            raw_pitches = ()
        pitches = tuple(_number(item) for item in raw_pitches)

        resolved_source = source_id if source_id is not None else raw.get("source_id")
        try:
            resolved_source = int(resolved_source) if resolved_source is not None else None
        except (TypeError, ValueError, OverflowError):
            resolved_source = None
        resolved_channel = channel if channel is not None else raw.get("channel")
        try:
            resolved_channel = max(1, min(16, int(resolved_channel))) if resolved_channel is not None else None
        except (TypeError, ValueError, OverflowError):
            resolved_channel = None
        resolved_slot = raw.get("_composition_slot", raw.get("composition_slot"))
        try:
            resolved_slot = int(resolved_slot) if resolved_slot is not None else None
        except (TypeError, ValueError, OverflowError):
            resolved_slot = None

        known = {
            "beat", "interval_beats", "duration_beats", "pitch", "pitches", "velocity", "duration", "gate",
            "rhythm", "probability", "importance", "source_id", "role", "channel", "port",
            "event_class", "_composition_slot", "composition_slot",
        }
        extras = {key: value for key, value in raw.items() if key not in known}
        return cls(
            beat=resolved_beat,
            interval_beats=interval,
            duration_beats=duration_beats,
            pitch=_number(raw.get("pitch", pitches[0] if pitches else 0.0)),
            pitches=pitches,
            velocity=_bounded(raw.get("velocity", 0.8), 0.8, 0.0, 1.0),
            gate=gate,
            rhythm=_bounded(raw.get("rhythm", 1.0), 1.0, 0.0, 1.0),
            probability=_bounded(raw.get("probability", 1.0), 1.0, 0.0, 1.0),
            importance=_bounded(raw.get("importance", 0.5), 0.5, 0.0, 1.0),
            event_class=(str(raw.get("event_class", "support")).lower()
                         if str(raw.get("event_class", "support")).lower() in ("anchor", "support", "ornament")
                         else "support"),
            source_id=resolved_source,
            role=str(role if role is not None else raw.get("role")) if (role is not None or raw.get("role") is not None) else None,
            channel=resolved_channel,
            port=str(port if port is not None else raw.get("port")) if (port is not None or raw.get("port") is not None) else None,
            composition_slot=resolved_slot,
            extras=extras,
        )

    @classmethod
    def from_outputs(
        cls,
        outputs: Mapping[str, Any],
        index: int,
        *,
        beat: float,
        interval_beats: float,
        source_id: int | None = None,
        role: str | None = None,
        channel: int | None = None,
        port: str | None = None,
        composition_slot: int | None = None,
        event_class: str = "support",
        importance: float = 0.5,
    ) -> "MusicalEvent | None":
        """Create an event from one slot of the legacy generator output arrays."""
        def at(part, default):
            stream = outputs.get(part, ())
            try:
                return stream[index] if index < len(stream) else default
            except (TypeError, IndexError):
                return default

        rhythm = _number(at("rhythm", 0.0))
        if rhythm <= 0.0:
            return None
        values = {
            "rhythm": rhythm,
            "pitch": at("pitch", 0.0),
            "velocity": at("velocity", 0.8),
            "duration": at("duration", 0.78),
            "event_class": event_class,
            "importance": importance,
        }
        if composition_slot is not None:
            values["_composition_slot"] = int(composition_slot)
        return cls.from_mapping(
            values, beat=beat, interval_beats=interval_beats,
            source_id=source_id, role=role, channel=channel, port=port,
        )

    def to_mapping(self) -> dict[str, Any]:
        """Return a legacy-compatible dict enriched with canonical beat data."""
        result = dict(self.extras)
        result.update({
            "beat": float(self.beat),
            "interval_beats": float(self.interval_beats),
            "duration_beats": float(self.duration_beats),
            "pitch": float(self.pitch),
            "velocity": float(self.velocity),
            "duration": float(self.gate),
            "rhythm": float(self.rhythm),
            "probability": float(self.probability),
            "importance": float(self.importance),
            "event_class": str(self.event_class),
        })
        if self.pitches:
            result["pitches"] = list(self.pitches)
        if self.source_id is not None:
            result["source_id"] = self.source_id
        if self.role is not None:
            result["role"] = self.role
        if self.channel is not None:
            result["channel"] = self.channel
        if self.port is not None:
            result["port"] = self.port
        if self.composition_slot is not None:
            result["_composition_slot"] = self.composition_slot
        return result

    def duration_seconds(self, tempo: float) -> float:
        """Return event duration in seconds at a tempo in quarter-note BPM."""
        bpm = max(1.0, _number(tempo, 120.0))
        return self.duration_beats * 60.0 / bpm
