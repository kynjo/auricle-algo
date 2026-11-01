"""Read-only attribution for the Perform, Composition and Relations UI dots.

Parameter writes and output-stream processing are deliberately distinguished:
a Relation or a section can change the notes without rewriting a knob's value.
This module never generates material, writes parameters or advances a runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from auricle_model import relation_endpoint_id
from composition_planner import METERS
from harmonic_plan import normalized as normalized_harmony, metric_weight
from instrument_dialogue import DialogueRuntime
from parameter_influence import KINDS


SOURCE_COLORS = {"Perform": "#bd83f4", "Composition": "#55c5ad", "Relations": "#f2bc61"}
OUTPUT_KEYS = {
    "rhythm": ("fill_density", "kit_density"),
    "density": ("fill_density", "kit_density"),
    "pitch": ("transpose",),
    "velocity": ("velocity_base",),
    "duration": ("gate", "live_gate"),
    "accent": ("velocity_accent",),
}
# A missing authored key must not adopt the transient layer value that the
# modulation catalogue may infer from block.parameters during playback.
DISPLAY_DEFAULTS = {"gate": .78, "live_gate": .65, "velocity_base": .72,
                    "velocity_accent": .18, "velocity_range": .25, "velocity_random": 0.,
                    "timing_rate": 1., "timing_swing": 0., "timing_humanize": 0., "timing_offset": 0.}


@dataclass(frozen=True)
class SourceMark:
    source: str
    active: bool
    details: tuple[str, ...]


def _number(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class SourceSnapshot:
    """One cheap snapshot, to be read under the shared transport state lock."""

    def __init__(self, engine):
        self.engine = engine
        self.owners = {}
        self.parents = {}
        for block in engine.project.blocks:
            self.owners[block.id] = block
            for voice in block.drum_voices or ():
                self.owners[voice.id] = voice
                self.parents[voice.id] = block
        self.routes = engine.relation_runtime.routes()
        self.harmony = normalized_harmony(engine.project.harmonic_plan)
        config = engine.project.composition
        valid = (all(key in config for key in ("enabled", "loop", "meter", "sections"))
                 and config["meter"] in METERS and isinstance(config["sections"], list)
                 and all(isinstance(s, dict) and "bars" in s and "blocks" in s for s in config["sections"]))
        self.context = (engine.composition_runtime.context(engine.clock.position_beats)
                        if valid and engine.composition_runtime.enabled() and config["sections"] else None)
        self.macros = (engine.composition_runtime.effective_macros(self.context["section"],
                       engine.director.global_macro_values, self.context) if self.context is not None else {})
        self.automation_assignments = {}
        for section in config.get('sections', ()):
            for track in section.get('parameter_automation', ()):
                target = (track.get('entity_id'), track.get('parameter'))
                state = engine.section_automation.statuses.get(track.get('id'), {})
                detail = f'{section.get("name", "Section")}: parameter automation · {track.get("timing", "auto")} timing'
                if not track.get('enabled', True): detail += ' · disabled'
                if state.get('state') == 'waiting for boundary':
                    detail += f' · waiting for section beat {state["next_beat"]:g}'
                self.automation_assignments.setdefault(target, []).append(detail)
        # Resolve on a disposable runtime so observation cannot clear the live
        # Dialogue memory when an edited route has not yet reached the worker.
        self.dialogues = {}
        if any(route.algorithm == "Dialogue" for route in engine.project.relations):
            dialogue = DialogueRuntime(engine.project)
            for block in engine.project.blocks:
                route = dialogue.route_for(block)
                if route is not None:
                    relation = route["relation"]
                    self.dialogues[block.id] = (relation, route["config"],
                                               dialogue.status(relation, engine.clock.position_beats))

    def follows_harmony(self, block):
        return (block.block_type in ("BASS", "MELODY", "CHORD", "PAD")
                and self.harmony["enabled"] and bool(self.harmony["chords"])
                and bool(block.parameters.get("harmonic_follow", True)))

    def marks(self, block_id, key):
        found = {name: [] for name in SOURCE_COLORS}

        def add(source, detail, active=True):
            found[source].append((bool(active), detail))

        if block_id is None:
            if self.context is not None:
                section = self.context["section"]
                if self.engine.composition_runtime.macro_is_active(self.context, key, self.engine.director.global_macro_values):
                    add("Composition", f'{section["name"]}: {key.title()} {self.macros[key]:.0%}. '
                        'Section override / curve / incoming blend at the transport position; the manual Global value is preserved.')
                else:
                    add("Composition", f'{section["name"]}: {key.title()} follows Global; '
                        'Composition remains enabled with a neutral macro setting.', False)
        elif block_id in self.owners:
            block = self.owners[block_id]
            self._technique(block, key, add)
            self._director(block, key, add)
            self._composition(block, key, add)
            self._relations(block, key, add)

        return tuple(SourceMark(source, any(active for active, _ in rows),
                                tuple(dict.fromkeys(detail for _, detail in rows)))
                     for source, rows in found.items() if rows)

    def _technique(self, block, key, add):
        layers = self.engine.parameter_influence
        entry = layers.entries.get((block.id, key))
        if entry is None:
            return
        rows = list(entry["rows"].values())
        coefficients = layers.contributions(block, key)
        colors = {'Technique': 'Perform', 'Modulation': 'Relations', 'Composition': 'Composition'}
        for row in rows:
            if row['kind'] not in colors:
                continue
            active = coefficients[row['kind']] > 1e-9 and row["weight"] > 0
            status = "active parameter layer" if active else "assigned, bypassed by weight or control policy"
            value = f'{row["value"]:.4g}' if isinstance(row['value'], (float, int)) else str(row['value'])
            add(colors[row['kind']], f'{row["source"]}: target {value}; {status}.', active)

    def _director(self, block, key, add):
        director = self.engine.director
        if self.follows_harmony(block) and key in ("role_center", "harmonic_strength"):
            add("Perform", "Harmonic plan: chord-tone anchoring and voicing at the transport position. "
                "Applied to output pitches; the generator setting is unchanged.")
        if not self.engine.director_applies(block):
            return
        role = str(block.block_type).upper()
        dimensions = {"velocity_base": "dynamics", "gate": "duration", "live_gate": "duration",
                      "event_probability": "event probability", "role_center": "register center"}
        if role not in ("PAD", "CHORD"):
            dimensions["fill_density"] = "event density"
        if role in ("DRUM", "PERCUSSION"):
            dimensions.pop("role_center", None)
        if key in dimensions:
            add("Perform", f'Musical Director / {director.phrase.phrase_id}: output {dimensions[key]}. '
                'Applied to notes; the generator setting is unchanged.')

    def _composition(self, block, key, add):
        for detail in self.automation_assignments.get((block.id, key), ()):
            add('Composition', detail + '. The authored setting is preserved.', False)
        if self.context is None:
            return
        section = self.context["section"]
        settings = self.engine.composition_runtime.block_settings(section, block.id)
        macros = {name: value if self.engine.composition_runtime.macro_is_active(self.context, name,
                    self.engine.director.global_macro_values) else None for name, value in self.macros.items()}
        details = []
        if key == "kit_density" and block.drum_voices:
            if macros.get("density") is not None:
                details.append(f'section Density {macros["density"]:.0%}')
            for voice in block.drum_voices:
                voice_settings = self.engine.composition_runtime.block_settings(section, voice.id)
                if not voice_settings["enabled"] or voice_settings["density"] != 1.:
                    details.append(f'{voice.name}: ' + (f'event density ×{voice_settings["density"]:.2f}'
                                   if voice_settings["enabled"] else "silent"))
        elif key == "fill_density":
            if not settings["enabled"]:
                details.append("block/voice is silent in this section")
            if settings["density"] != 1.:
                details.append(f'event density ×{settings["density"]:.2f}')
            if macros.get("density") is not None:
                details.append(f'section Density {macros["density"]:.0%}')
        elif key == "velocity_base":
            if not settings["enabled"]:
                details.append("block/voice is silent in this section")
            if key == "velocity_base":
                if settings["velocity"] != 1.:
                    details.append(f'velocity ×{settings["velocity"]:.2f}')
                if settings["accent"]:
                    details.append(f'metric accent {settings["accent"]:.0%}')
                if macros.get("energy") is not None:
                    details.append(f'section Energy {macros["energy"]:.0%}')
            if settings["variation"] > 0:
                details.append(f'velocity variation {settings["variation"]:.0%}')
            if macros.get("variation") is not None:
                details.append(f'section Variation {macros["variation"]:.0%}')
        elif key == "role_center" and block.block_type not in ("DRUM", "PERCUSSION"):
            if settings["register_center"]:
                details.append(f'Register Center offset {settings["register_center"]:+g}; octave placement before scale/harmony')
            if settings["octave_spread"]:
                details.append(f'octave spread {settings["octave_spread"]:.0%}, bounded by the role register')
        elif key in ("gate", "live_gate") and settings["gate"] != 1.:
            details.append(f'note duration ×{settings["gate"]:.2f}')
        elif key == "velocity_accent" and settings["accent"]:
            details.append(f'metric accent {settings["accent"]:.0%}')
        elif key == "harmonic_strength" and self.follows_harmony(block):
            # Section Tension affects chord anchoring even when following Global.
            value = self.macros["tension"]
            if abs(value - .5) > 1e-9:
                details.append(f'chord anchoring from section Tension {value:.0%}')
            if settings["harmony"] != 1.:
                details.append(f'chord anchoring ×{settings["harmony"]:.2f}')
        if details:
            add("Composition", f'{section["name"]}: ' + "; ".join(details)
                + ". Applied to output notes; the generator setting is unchanged.")
        elif key in ("fill_density", "velocity_base") or (key == "kit_density" and block.drum_voices) or (
                key == "role_center" and block.block_type not in ("DRUM", "PERCUSSION")) or (
                key == "harmonic_strength" and self.follows_harmony(block)):
            add("Composition", f'{section["name"]}: neutral section setting. '
                'Composition is enabled; this property passes through unchanged.', False)

    def _relations(self, block, key, add):
        parent = self.parents.get(block.id)
        dialogue = self.dialogues.get(parent.id if parent else block.id)
        if dialogue is not None:
            relation, config, status = dialogue
            keys = {"fill_density", "velocity_base", "gate", "live_gate"}
            if (block.id == relation.destination_block and config["reply"] != "Own phrase"
                    and config["follow"] > 0 and block.block_type not in ("DRUM", "PERCUSSION")):
                keys.add("transpose")
            if key in keys:
                source = self.owners[relation.source_block]
                destination = self.owners[relation.destination_block]
                reason = status["reason"] or status["phase"]
                add("Relations", f'{source.name} ↔ {destination.name}: Dialogue / {reason}. '
                    "Turn-taking is applied to output events; the generator setting is unchanged.", status["active"])
        destinations = {block.id}
        if parent is not None:
            destinations.add(parent.id)
        for route in self.routes:
            destination_id = relation_endpoint_id(route, "destination")
            if destination_id not in destinations or key not in OUTPUT_KEYS.get(route.destination_part, ()):
                continue
            if key == "kit_density" and (parent is not None or not block.drum_voices):
                continue
            source = self.owners[relation_endpoint_id(route, "source")]
            destination = self.owners[destination_id]
            bus = " (Drum bus)" if parent is not None and destination_id == parent.id else ""
            add("Relations", f'{source.name} → {destination.name}{bus}: {route.algorithm}, '
                f'{route.source_part} → {route.destination_part}, amount {route.amount:.0%}, '
                f'probability {route.probability:.0%}. Output stream; the generator setting is unchanged.')
        source = self.engine.role_relation_source(block)
        if source is None:
            return
        if block.block_type == "BASS" and not self.engine._has_explicit_role_route(source, block, "rhythm", "rhythm"):
            depth_key = {"fill_density": "groove_follow", "velocity_base": "groove_accent",
                         "velocity_accent": "groove_accent"}.get(key)
            depth = _number(block.parameters.get(depth_key, .70 if depth_key == "groove_follow" else .65))
            if depth_key and depth > 0:
                add("Relations", f'{source.name} → {block.name}: built-in Drum → Bass, '
                    f'{depth_key.replace("_", " ")} {depth:.0%}. Output stream; the generator setting is unchanged.')
        elif (block.block_type == "MELODY" and key == "transpose"
              and not self.follows_harmony(block)
              and not self.engine._has_explicit_role_route(source, block, "pitch", "pitch")
              and _number(block.parameters.get("harmony_anchor", .55)) > 0):
            add("Relations", f'{source.name} → {block.name}: built-in Chord → Melody anchoring. '
                'Output pitches; the generator transpose is unchanged.')


def parameter_values(engine, block_id, key):
    """Authored and resolved parameter values, without reconciling/writing state."""
    block = engine.find_block(block_id) if block_id is not None else None
    if block is None and block_id is not None:
        block = next((voice for parent in engine.project.blocks for voice in parent.drum_voices or ()
                      if voice.id == block_id), None)
    if block is None:
        return None
    entry = engine.parameter_influence.entries.get((block_id, key))
    configured = engine.parameter_influence.specs.get((block_id, key))
    discrete = engine.parameter_influence.discrete_specs.get((block_id, key))
    default = (configured[0] if configured else DISPLAY_DEFAULTS.get(key, engine.parameter_catalog(block).get(key, (None, 0, 1))[0]))
    if discrete: default = discrete[0]
    base = entry["base"][1] if entry and entry["base"][0] else default if entry else engine.parameter_influence.current_value(block, key, default)
    return base, engine.parameter_influence.current_value(block, key, default)


@dataclass(frozen=True)
class FeedbackValue:
    manual: float
    parameter: float
    effective: float
    mode: str = "Effective parameter"


def feedback_value(snapshot, block_id, key, marks):
    """Read an effective display value; never write it back to the generator.

    For streams, show a parameter-equivalent value using the ratio/difference
    between the clean and processed material. This is explicitly labelled as
    output feedback rather than a new authored parameter value.
    """
    engine = snapshot.engine
    if block_id is None:
        manual = float(engine.director.global_macro_values.get(key, .5))
        effective = manual
        if snapshot.context is not None:
            effective = engine.composition_runtime.effective_macros(
                snapshot.context["section"], engine.director.global_macro_values, snapshot.context)[key]
        return FeedbackValue(manual, manual, effective, "Section macro" if effective != manual else "Effective parameter")
    if block_id not in snapshot.owners:
        return None
    values = parameter_values(engine, block_id, key)
    if values is None or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
        return None
    manual, current = map(float, values)
    value = current
    block = snapshot.owners[block_id]
    if key == "role_center" and block.block_type not in ("DRUM", "PERCUSSION"):
        return FeedbackValue(manual, current, engine.effective_register_center(block), "Effective register center")
    active = {mark.source for mark in marks if mark.active}
    output = False
    director = engine.director
    if engine.director_applies(block) and "Perform" in active:
        role = director.role_state(block.block_type, director._last_state)
        if key == "velocity_base":
            value *= .82 + .36 * role.energy
            output = True
        elif key in ("gate", "live_gate"):
            value *= role.duration_factor
            output = True
        elif key == "fill_density" and role.activity_mode != "harmonic":
            value = director.bounded_combine(value if block.mode == "SEQ" else 1., role.density,
                                            .14 if block.mode == "SEQ" else .12)
            output = True
        elif key == "event_probability":
            value = director.bounded_combine(value, role.probability, .10)
            output = True
    if "Relations" in active:
        before = engine._base_outputs.get(block_id, {})
        after = block.outputs
        index = 0 if block.mode == "LIVE" else int(engine.source_positions.get(block_id, 0))
        def sample(material, part):
            stream = material.get(part, ())
            return float(stream[index % len(stream)]) if stream else None
        if key in ("fill_density", "kit_density"):
            # Rhythm controls represent the complete pattern, not a single
            # hit/rest that would make a density knob flash between 0 and 1.
            part = "density" if any(relation_endpoint_id(r, "destination") == block_id
                    and r.destination_part == "density" for r in snapshot.routes) else "rhythm"
            clean, changed = before.get(part, ()), after.get(part, ())
            if clean and changed:
                density = lambda seq: sum(float(v > 0) if part == "rhythm" else max(0., min(1., float(v)))
                                          for v in seq) / len(seq)
                old, new = density(clean), density(changed)
                value = value * new / old if old > 1e-9 else new
                output = True
        elif key in ("velocity_base", "gate", "live_gate", "transpose", "velocity_accent"):
            part = {"velocity_base": "velocity", "gate": "duration", "live_gate": "duration",
                    "transpose": "pitch", "velocity_accent": "accent"}[key]
            old, new = sample(before, part), sample(after, part)
            if old is not None and new is not None:
                if key == "transpose":
                    value += new - old
                elif key == "velocity_accent":
                    value = new
                elif old > 1e-9:
                    value *= new / old
                elif new > 0:
                    value = new
                output = True
    parent = snapshot.parents.get(block_id)
    dialogue = snapshot.dialogues.get(parent.id if parent else block_id)
    if dialogue is not None and dialogue[2]["active"] and key in ("fill_density", "kit_density"):
        relation, config, status = dialogue
        owner = parent.id if parent else block_id
        participating = ((status["phase"] == "Call" and owner == relation.source_block)
                         or (status["phase"] == "Response" and owner == relation.destination_block))
        if not participating and relation.amount >= 1.:
            value = 0.
            output = True
    frame = getattr(block, "_parameter_feedback_event", None)
    section_key = ((snapshot.context["section_id"], snapshot.context["cycle"])
                   if snapshot.context is not None else None)
    frame_used = False
    if (active and frame and frame["section"] == section_key
            and -.25 <= engine.clock.position_beats - frame["beat"] <= .5 and frame["output"] is not None):
        if key in ("velocity_base", "gate", "live_gate"):
            part = "velocity" if key == "velocity_base" else "duration"
            old, new = frame["input"][part], frame["output"][part]
            if old > 1e-9:
                value *= new / old
            elif new > 0:
                value = new
            frame_used = output = True
        elif key == "transpose" and "Relations" in active and block.block_type not in ("DRUM", "PERCUSSION"):
            value += frame["output"]["pitch"] - frame["input"]["pitch"]
            frame_used = output = True
    if snapshot.context is not None:
        section = snapshot.context["section"]
        settings = engine.composition_runtime.block_settings(section, block_id)
        macros = snapshot.macros
        if key in ("fill_density", "kit_density"):
            density = settings["density"] if settings["enabled"] else 0.
            if key == "kit_density" and block.drum_voices:
                rows = [engine.composition_runtime.block_settings(section, v.id) for v in block.drum_voices]
                density = sum(row["density"] if row["enabled"] else 0. for row in rows) / len(rows)
            value *= density * min(1., max(0., .25 + 1.5 * macros["density"]))
            output = True
        elif key == "velocity_base" and not frame_used:
            # Reuse the real, deterministic section transform. The probe is a
            # fresh dict and cannot publish notes, advance RNG or alter data.
            beat = engine.clock.position_beats
            slot = int(engine.source_positions.get(block_id, 0)) if block.mode == "SEQ" else max(
                0, int(engine.live_state.get(block_id, {}).get("events", 1)) - 1)
            parent = snapshot.parents.get(block_id)
            if parent is not None and parent.parameters.get("kit_coordinated", False):
                slot = int(round(beat * 4))
            event = {"pitch": 0., "duration": 1., "velocity": value,
                     "_composition_slot": slot}
            transformed = engine.apply_composition_event(block, event, beat, gate_checked=True)
            value = float(transformed["velocity"]) if settings["enabled"] and transformed else 0.
            output = True
        elif key in ("gate", "live_gate") and not frame_used:
            value = min(1.5, value * settings["gate"])
            output = settings["gate"] != 1. or output
        elif key == "velocity_accent" and settings["accent"]:
            weight = metric_weight(engine.composition_runtime.config()["meter"],
                                   engine.clock.position_beats % snapshot.context["bar_beats"])
            value += settings["accent"] * (.35 * weight if weight else -.15)
            output = True
        elif key == "harmonic_strength" and snapshot.follows_harmony(block):
            value = max(0., min(1., (value + (.5 - macros["tension"]) * .60) * settings["harmony"]))
            output = True
    return FeedbackValue(manual, current, value, "Output equivalent" if output else "Effective parameter")
