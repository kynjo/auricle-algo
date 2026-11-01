"""Section-authored phrases and techniques, driven by the transport clock."""
from __future__ import annotations

import math
from copy import deepcopy

from performance_presets import phrase_for, preset_for_entity


def finite(value, low, high, default):
    try:
        value = float(value)
        return max(low, min(high, value)) if math.isfinite(value) else default
    except (ValueError, TypeError, OverflowError):
        return default


def normalize_performance(raw=None):
    raw = raw if isinstance(raw, dict) else {}
    ids = raw.get("block_ids")
    targets = None if ids is None else sorted({i for i in ids if isinstance(i, int) and not isinstance(i, bool) and i >= 0}) if isinstance(ids, (list, tuple)) else None
    techniques = {}
    items = raw.get("techniques")
    for key, value in (items.items() if isinstance(items, dict) else ()):
        if not str(key).isdigit() or not isinstance(value, dict) or not isinstance(value.get("preset_id"), str):
            continue
        techniques[str(int(key))] = {
            "preset_id": value["preset_id"][:80],
            "amount": finite(value.get("amount", 1), 0, 1, 1),
            "shape": value.get("shape") if value.get("shape") in ("in", "out", "in_out", "pulse") else "in",
            "fit_to_section": bool(value.get("fit_to_section", True)),
            "beats": finite(value.get("beats", 4), .25, 1024, 4),
        }
    pid = raw.get("phrase_id")
    return {"phrase_id": pid if isinstance(pid, str) and phrase_for(pid) else None,
            "amount": finite(raw.get("amount", 1), 0, 1, 1),
            "fit_to_section": bool(raw.get("fit_to_section", True)),
            "duration_beats": finite(raw.get("duration_beats", 16), 1, 1024, 16),
            "block_ids": targets, "techniques": techniques}


class SectionPerformanceRuntime:
    def __init__(self, engine):
        self.engine = engine
        self.token = None
        self.last_local = 0.
        self.owns_performance = False
        self.section_id = None

    def reset(self, clear_layers=True):
        if clear_layers and self.owns_performance:
            self.engine.performance.reset()
        self.token = None
        self.last_local = 0.
        self.owns_performance = False
        self.section_id = None

    def advance(self, beat, *, now=None, force=False):
        engine = self.engine
        context = engine.composition_runtime.context_at(beat)
        if context is None:
            had_layers = self.owns_performance
            self.reset()
            if had_layers:
                engine.generate()
            return
        section = context["section"]
        duration = float(section["bars"]) * context["bar_beats"]
        settings = normalize_performance(section.get("performance"))
        token = (context["cycle"], section["id"], duration, settings)
        local = max(0., min(duration, float(context["local_beat"])))
        if force or token != self.token or local < self.last_local:
            had_layers = self.owns_performance
            self.reset()
            self.token = deepcopy(token)
            self.last_local = local
            self.section_id = section["id"]
            blocks = {b.id: b for b in engine.project.blocks}
            overrides = {int(key): value for key, value in settings["techniques"].items()
                         if int(key) in blocks and (value["preset_id"] == "none"
                             or preset_for_entity(blocks[int(key)], value["preset_id"]) is not None)}
            targets = set(blocks) if settings["block_ids"] is None else set(settings["block_ids"]) & set(blocks)
            authored = bool((settings["phrase_id"] and targets) or any(v["preset_id"] != "none" for v in overrides.values()))
            if not authored:
                if had_layers:
                    engine.generate()
                return
            # An explicit form launch owns these layers; no MIDI note-off is
            # sent at a musical stage/section boundary.
            engine.performance.reset()
            self.owns_performance = True
            if settings["phrase_id"] and targets:
                length = duration if settings["fit_to_section"] else settings["duration_beats"]
                engine.performance.start_phrase(engine.project, settings["phrase_id"], sorted(targets),
                    settings["amount"], duration_beats=length, section_fit=True)
                state = engine.director.phrase
                state.position_beats = min(local, length)
                state.memory.update(technique_exclusions=list(overrides), section_owner=section["id"],
                                    section_hold=settings["fit_to_section"])
            for bid, value in overrides.items():
                if value["preset_id"] == "none":
                    continue
                length = duration if value["fit_to_section"] else value["beats"]
                if engine.performance.start(blocks[bid], value["preset_id"], value["amount"], value["shape"], length):
                    active = engine.performance.active[bid]
                    active.elapsed_beats = min(local, length)
                    active.hold = True
                    active.owner_section = section["id"]
            engine.performance.tick(True, beat_delta=0., now=now)
            engine.generate()
        else:
            delta = max(0., local - self.last_local)
            self.last_local = local
            if self.owns_performance:
                engine.performance.tick(True, beat_delta=delta, now=now)
