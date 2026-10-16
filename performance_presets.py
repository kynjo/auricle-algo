"""Musical performance techniques for Auricle.

The catalog deliberately uses musical vocabulary rather than raw parameter names.
A preset is a small performance gesture: crescendo, ritardando, staccato,
stringendo, rubato, smorzando, etc.  Each gesture maps to real block parameters.

The catalog is data-driven so Perform can evolve independently from the Qt UI.
Block-type defaults and algorithm-specific gestures are merged at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
import math
import time


@dataclass(frozen=True)
class PerformanceMove:
    parameter: str
    start: float
    end: float
    label: str = ""


@dataclass(frozen=True)
class PerformancePreset:
    id: str
    name: str
    family: str
    description: str
    moves: tuple[PerformanceMove, ...]
    default_shape: str = "in"
    default_beats: float = 4.0
    tags: tuple[str, ...] = ()


# Common gestures are intentionally phrased as musical actions.  The numeric
# mappings are normalized around the parameters already exposed by Auricle.
COMMON = (
    PerformancePreset("crescendo", "Crescendo", "Dynamics", "Gradually increases dynamics.",
                      (PerformanceMove("velocity_base", .58, .92), PerformanceMove("fill_density", .65, 1.0)), "in", 4),
    PerformancePreset("diminuendo", "Diminuendo", "Dynamics", "Gradually reduces dynamics.",
                      (PerformanceMove("velocity_base", .88, .42), PerformanceMove("fill_density", 1.0, .35)), "out", 4),
    PerformancePreset("sforzando", "Sforzando", "Dynamics", "A short accent followed by a return to the previous dynamic.",
                      (PerformanceMove("velocity_accent", .05, .55),), "pulse", 1),
    PerformancePreset("accelerando", "Accelerando", "Agogic", "Gradually accelerates the motion.",
                      (PerformanceMove("timing_rate", 1.0, 1.55),), "in", 4),
    PerformancePreset("ritardando", "Ritardando", "Agogic", "Gradually slows the motion.",
                      (PerformanceMove("timing_rate", 1.0, .58),), "out", 4),
    PerformancePreset("stringendo", "Stringendo", "Agogic", "Accelerates while increasing tension.",
                      (PerformanceMove("timing_rate", 1.0, 1.45), PerformanceMove("velocity_base", .62, .9)), "in", 4),
    PerformancePreset("smorzando", "Smorzando", "Expression", "Fades and settles toward rest.",
                      (PerformanceMove("velocity_base", .82, .28), PerformanceMove("fill_density", .9, .15), PerformanceMove("timing_rate", 1.0, .72)), "out", 6),
    PerformancePreset("staccato", "Staccato", "Articulation", "Short, detached events.",
                      (PerformanceMove("gate", .85, .28),), "in", 2),
    PerformancePreset("tenuto", "Tenuto", "Articulation", "Sustains notes for a more connected articulation.",
                      (PerformanceMove("gate", .55, .95),), "in", 2),
    PerformancePreset("rubato", "Rubato", "Agogic", "Gentle timing fluctuation without a permanent tempo shift.",
                      (PerformanceMove("timing_humanize", .0, .10), PerformanceMove("timing_swing", .0, .08)), "pulse", 8),
    PerformancePreset("register_rise", "Register Rise", "Pitch", "Gradually opens the register upward.",
                      (PerformanceMove("transpose", 0.0, 7.0),), "in", 8),
    PerformancePreset("register_fall", "Register Fall", "Pitch", "Gradually moves the register downward.",
                      (PerformanceMove("transpose", 0.0, -7.0),), "out", 8),
    PerformancePreset("density_swell", "Density Swell", "Texture", "Gradually increases event density.",
                      (PerformanceMove("fill_density", .25, 1.0), PerformanceMove("event_probability", .55, 1.0)), "in", 4),
    PerformancePreset("density_drop", "Density Drop", "Texture", "Rapidly opens space by reducing density.",
                      (PerformanceMove("fill_density", 1.0, .08), PerformanceMove("event_probability", 1.0, .35)), "out", 2),
    PerformancePreset("accent_build", "Accent Build", "Expression", "Builds accents without necessarily raising average loudness.",
                      (PerformanceMove("velocity_accent", .05, .5),), "in", 4),
)

TYPE_GESTURES = {
    "DRUM": (
        "density_swell", "density_drop", "crescendo", "diminuendo", "accelerando", "ritardando",
        "staccato", "sforzando", "accent_build",
    ),
    "PERCUSSION": (
        "density_swell", "density_drop", "crescendo", "diminuendo", "accelerando", "ritardando",
        "staccato", "sforzando", "accent_build",
    ),
    "BASS": (
        "crescendo", "diminuendo", "accelerando", "ritardando", "stringendo", "staccato",
        "tenuto", "register_rise", "register_fall", "smorzando",
    ),
    "MELODY": (
        "crescendo", "diminuendo", "accelerando", "ritardando", "rubato", "staccato", "tenuto",
        "register_rise", "register_fall", "stringendo", "smorzando",
    ),
    "PAD": (
        "crescendo", "diminuendo", "ritardando", "rubato", "tenuto", "register_rise", "register_fall",
        "smorzando", "density_swell", "density_drop",
    ),
    "CHORD": (
        "crescendo", "diminuendo", "accelerando", "ritardando", "tenuto", "staccato",
        "register_rise", "register_fall", "density_swell", "smorzando",
    ),
}

# Algorithm-specific gestures. Every generator has its own vocabulary in
# addition to the musical gestures inherited from its block type.
ALGORITHM_GESTURES: dict[str, tuple[PerformancePreset, ...]] = {
    "Euclidean": (
        PerformancePreset("euclidean_fill", "Euclidean Fill", "Algorithm", "Increases the number of Euclidean rhythm pulses.",
                           (PerformanceMove("pulses", 2, 12),), "in", 4),
        PerformancePreset("euclidean_rotate", "Euclidean Rotate", "Algorithm", "Gradually rotates the pattern phase.",
                           (PerformanceMove("euclidean_rotation", 0, 7),), "in", 4),
    ),
    "Bresenham": (
        PerformancePreset("bres_fill", "Bresenham Fill", "Algorithm", "Increases Bresenham pattern density.",
                           (PerformanceMove("bres_pulses", 2, 12),), "in", 4),
        PerformancePreset("bres_rotate", "Bresenham Rotate", "Algorithm", "Rotates the rhythm phase.",
                           (PerformanceMove("bres_rotation", 0, 7),), "in", 4),
    ),
    "Polyrhythm": (
        PerformancePreset("poly_unison", "Polyrhythm Unison", "Algorithm", "Brings two cycles toward a common pulse.",
                           (PerformanceMove("poly_a", 3, 4), PerformanceMove("poly_b", 5, 4)), "in", 8),
        PerformancePreset("poly_spread", "Polyrhythm Spread", "Algorithm", "Separates the cycles to increase polyrhythmic tension.",
                           (PerformanceMove("poly_a", 3, 7), PerformanceMove("poly_b", 4, 9)), "in", 8),
    ),
    "Thue-Morse": (
        PerformancePreset("tm_density", "Thue–Morse Density", "Algorithm", "Increases fractal rhythm density.",
                           (PerformanceMove("tm_density", .3, 1.0),), "in", 4),
        PerformancePreset("tm_rotate", "Thue–Morse Rotate", "Algorithm", "Rotates the fractal pattern.",
                           (PerformanceMove("tm_rotation", 0, 7),), "in", 4),
    ),
    "Fibonacci Rhythm": (
        PerformancePreset("fib_rise", "Fibonacci Rise", "Algorithm", "Gradually opens the Fibonacci rhythm.",
                           (PerformanceMove("fib_density", .2, 1.0),), "in", 8),
        PerformancePreset("fib_fade", "Fibonacci Fade", "Algorithm", "Reduces the Fibonacci rhythm.",
                           (PerformanceMove("fib_density", 1.0, .12),), "out", 8),
    ),
    "Fibonacci": (
        PerformancePreset("fib_register", "Fibonacci Register", "Algorithm", "Widens the sequence range.",
                           (PerformanceMove("sequence_mod", 4, 12), PerformanceMove("sequence_stride", 1, 3)), "in", 8),
    ),
    "Recaman": (
        PerformancePreset("recaman_widen", "Recamán Widen", "Algorithm", "Increases the range of the numeric material.",
                           (PerformanceMove("sequence_mod", 4, 14), PerformanceMove("sequence_stride", 1, 3)), "in", 8),
    ),
    "De Bruijn": (
        PerformancePreset("debruijn_rotate", "De Bruijn Rotate", "Algorithm", "Rotates the De Bruijn phase.",
                           (PerformanceMove("debruijn_rotation", 0, 15),), "in", 8),
        PerformancePreset("debruijn_order", "De Bruijn Expansion", "Algorithm", "Expands the combination space.",
                           (PerformanceMove("debruijn_order", 2, 4),), "in", 8),
    ),
    "Markov": (
        PerformancePreset("markov_unstable", "Markov Unstable", "Algorithm", "Increases leaps and reduces repetition.",
                           (PerformanceMove("markov_leap", .04, .45), PerformanceMove("markov_stay", .2, .02)), "in", 8),
        PerformancePreset("markov_settle", "Markov Settle", "Algorithm", "Settles the chain by increasing repetition.",
                           (PerformanceMove("markov_leap", .4, .03), PerformanceMove("markov_stay", .02, .45)), "out", 8),
    ),
    "Random Walk": (
        PerformancePreset("walk_drift", "Walk Drift", "Algorithm", "Gradually introduces directional motion.",
                           (PerformanceMove("walk_drift", 0.0, .8),), "in", 8),
        PerformancePreset("walk_return", "Walk Return", "Algorithm", "Returns the walk toward its center.",
                           (PerformanceMove("walk_return_bias", .0, .85),), "in", 8),
    ),
    "Interval Walker": (
        PerformancePreset("interval_leap", "Interval Leaps", "Algorithm", "Increases the probability of large intervals.",
                           (PerformanceMove("interval_leap", .02, .5),), "in", 8),
        PerformancePreset("interval_tame", "Interval Tame", "Algorithm", "Tames the material into smoother motion.",
                           (PerformanceMove("interval_leap", .45, .02), PerformanceMove("interval_return", .1, .65)), "out", 8),
    ),
    "Scale Walker": (
        PerformancePreset("scale_climb", "Scale Climb", "Algorithm", "Strengthens upward scale motion.",
                           (PerformanceMove("scale_direction", .5, 1.0), PerformanceMove("scale_leap", .05, .2)), "in", 8),
        PerformancePreset("scale_wander", "Scale Wander", "Algorithm", "Increases unpredictability of motion.",
                           (PerformanceMove("scale_direction", .5, .5), PerformanceMove("scale_leap", .02, .35)), "in", 8),
    ),
    "Weighted Scale": (
        PerformancePreset("weighted_open", "Weighted Open", "Algorithm", "Widens the register distribution.",
                           (PerformanceMove("scale_octave_spread", .05, .8),), "in", 8),
    ),
    "Arpeggiator": (
        PerformancePreset("arp_expand", "Arpeggio Expand", "Algorithm", "Expands the arpeggio across octaves.",
                           (PerformanceMove("arp_octaves", 1, 4),), "in", 8),
    ),
    "Probability": (
        PerformancePreset("prob_open", "Probability Open", "Algorithm", "Opens event probability.",
                           (PerformanceMove("probability", .2, 1.0),), "in", 4),
        PerformancePreset("prob_close", "Probability Close", "Algorithm", "Reduces the event stream.",
                           (PerformanceMove("probability", 1.0, .08),), "out", 4),
    ),
    "Pattern": (
        PerformancePreset("pattern_bloom", "Pattern Bloom", "Algorithm", "Increases pattern scale and probability.",
                           (PerformanceMove("pattern_scale", .5, 1.5), PerformanceMove("pattern_probability", .5, 1.0)), "in", 4),
        PerformancePreset("pattern_rotate", "Pattern Rotate", "Algorithm", "Gradually rotates the pattern.",
                           (PerformanceMove("pattern_rotation", 0, 7),), "in", 4),
    ),
    "Cellular Automaton": (
        PerformancePreset("ca_birth", "Cellular Birth", "Algorithm", "Increases cellular-automaton density.",
                           (PerformanceMove("ca_density", .2, 1.0),), "in", 8),
    ),
    "L-System": (
        PerformancePreset("ls_growth", "L-System Growth", "Algorithm", "Reveals more L-System generations.",
                           (PerformanceMove("ls_iterations", 1, 6),), "in", 8),
    ),
    "Logistic Chaos": (
        PerformancePreset("chaos_heat", "Chaos Heat", "Algorithm", "Moves the system toward more intense chaotic motion.",
                           (PerformanceMove("chaos_r", 3.4, 3.98), PerformanceMove("chaos_smooth", .5, .0)), "in", 8),
        PerformancePreset("chaos_cool", "Chaos Cool", "Algorithm", "Smooths chaotic material.",
                           (PerformanceMove("chaos_r", 3.98, 3.2), PerformanceMove("chaos_smooth", 0.0, .8)), "out", 8),
    ),
}

_PRESET_BY_ID = {p.id: p for p in COMMON}
for _items in ALGORITHM_GESTURES.values():
    for _p in _items:
        _PRESET_BY_ID[_p.id] = _p


def _available(block_type: str, algorithm: str) -> list[PerformancePreset]:
    """Return a curated catalogue for one concrete block/algorithm pair."""
    ids = TYPE_GESTURES.get(str(block_type).upper(), TYPE_GESTURES["MELODY"])
    result = [_PRESET_BY_ID[i] for i in ids if i in _PRESET_BY_ID]
    result.extend(ALGORITHM_GESTURES.get(str(algorithm), ()))
    # Every algorithm gets a generic expression vocabulary even if it has no
    # specialized mapping. This guarantees complete coverage of the catalog.
    seen = {p.id for p in result}
    for p in COMMON:
        if p.id not in seen and p.id in {"crescendo", "diminuendo", "accelerando", "ritardando"}:
            result.append(p)
    return result


def presets_for(block_type: str, algorithm: str) -> list[PerformancePreset]:
    return _available(block_type, algorithm)


def preset_for(block_type: str, algorithm: str, preset_id: str) -> PerformancePreset | None:
    return next((p for p in _available(block_type, algorithm) if p.id == preset_id), None)


def _shape(x: float, shape: str) -> float:
    """Map progress to an easing curve without reversing gesture direction."""
    x = max(0.0, min(1.0, x))
    if shape == "out":
        return 1.0 - (1.0 - x) * (1.0 - x)
    if shape == "in_out":
        return 2.0 * x * x if x < .5 else 1.0 - pow(-2.0 * x + 2.0, 2) / 2.0
    if shape == "pulse":
        # A compact attack/decay gesture, peaking near the centre.
        return math.sin(math.pi * x)
    # ``in``: slow attack, increasingly fast movement.
    return x * x


def interpolate_preset(preset: PerformancePreset, progress: float, amount: float = 1.0, shape: str | None = None) -> dict[str, float]:
    """Return parameter values for a normalized point on the gesture."""
    shape = shape or preset.default_shape
    t = _shape(progress, shape)
    amount = max(0.0, min(1.0, float(amount)))
    values: dict[str, float] = {}
    for move in preset.moves:
        base = move.start + (move.end - move.start) * t
        values[move.parameter] = move.start + (base - move.start) * amount
    return values


@dataclass
class ActivePerformance:
    preset_id: str
    amount: float = 1.0
    shape: str = "in"
    beats: float = 4.0
    elapsed_beats: float = 0.0
    enabled: bool = True
    last_regenerated_progress: float = -1.0
    phrase_id: str | None = None
    # Stage transitions overlap briefly. The incoming technique fades in from
    # the parameter values present at activation instead of jumping to its
    # preset start value.
    crossfade_beats: float = 0.0
    crossfade_from: dict[str, float] = field(default_factory=dict)
    # Values are kept separately from Block.parameters so LIVE can consume
    # temporary technique targets without permanently rewriting the project.
    current_values: dict[str, float] = field(default_factory=dict)


@dataclass
class ActivePhraseRelease:
    """Snapshot-based return path for a stopped/completed phrase."""
    phrase_id: str
    elapsed_beats: float
    beats: float
    targets: dict[int, dict[str, tuple[bool, float]]]
    missing_keys: dict[int, set[str]]


class PerformanceRuntime:
    """Runtime for musical gestures; independent of the Qt Perform UI."""

    def __init__(self, project: Any, engine: Any):
        self.project = project
        self.engine = engine
        self.active: dict[int, ActivePerformance] = {}
        self.active_phrase_releases: dict[str, ActivePhraseRelease] = {}
        self._last_time = time.monotonic()

    def start(self, block: Any, preset_id: str, amount: float = 1.0, shape: str | None = None, beats: float | None = None, phrase_id: str | None = None):
        preset = preset_for(block.block_type, block.algorithm, preset_id)
        if preset is None and phrase_id is not None:
            preset = _PRESET_BY_ID.get(str(preset_id))
        if preset is None:
            return False
        crossfade_from={}
        crossfade_beats=0.0
        if phrase_id is not None:
            for move in preset.moves:
                try:
                    crossfade_from[move.parameter]=float(block.parameters.get(move.parameter, move.start))
                except (TypeError,ValueError):
                    crossfade_from[move.parameter]=float(move.start)
            # About half a beat, capped so short stages still have room to act.
            crossfade_beats=min(.75,max(.20,float(beats if beats is not None else preset.default_beats)*.18))
        self.active[block.id] = ActivePerformance(
            preset_id=preset.id,
            amount=max(0.0, min(1.0, float(amount))),
            shape=shape or preset.default_shape,
            beats=max(.25, float(beats if beats is not None else preset.default_beats)),
            elapsed_beats=0.0,
            enabled=True,
            phrase_id=phrase_id,
            crossfade_beats=crossfade_beats,
            crossfade_from=crossfade_from,
        )
        return True

    def stop(self, block_id: int):
        self.active.pop(int(block_id), None)

    def live_value(self, block_id: int, key: str, default=None):
        """Return the active technique value for a LIVE-only destination.

        SEQ techniques write their interpolated values into the cached block
        representation. LIVE has no cache, so it reads this transient map on
        the next generated event. Removing the active performance immediately
        restores the block's ordinary LIVE parameters.
        """
        state = self.active.get(int(block_id))
        if state is None:
            return default
        return state.current_values.get(str(key), default)

    def toggle(self, block: Any, enabled: bool):
        if not enabled:
            self.stop(block.id)
            return
        state = self.active.get(block.id)
        if state is None:
            self.start(block, "crescendo")
        else:
            state.enabled = True

    def _phrase_parameter_keys(self, block: Any, phrase: PerformancePhrase) -> set[str]:
        keys: set[str] = set()
        for stage_index in range(len(phrase.stages)):
            stage = resolve_phrase_stage(phrase, block.block_type, stage_index)
            preset = preset_for(block.block_type, block.algorithm, stage.technique_id) or _PRESET_BY_ID.get(stage.technique_id)
            if preset:
                keys.update(move.parameter for move in preset.moves)
        return keys

    def _snapshot_phrase(self, project: Any, phrase: PerformancePhrase, block_ids: set[int]) -> tuple[dict[int, dict[str, tuple[bool, float]]], dict[int, set[str]]]:
        targets: dict[int, dict[str, tuple[bool, float]]] = {}
        missing: dict[int, set[str]] = {}
        for block in project.blocks:
            if block.id not in block_ids:
                continue
            for key in self._phrase_parameter_keys(block, phrase):
                if key in block.parameters:
                    try:
                        targets.setdefault(block.id, {})[key] = (True, float(block.parameters[key]))
                    except (TypeError, ValueError):
                        continue
                else:
                    # Keep the serialized state exact. During release we move
                    # towards the engine's catalog default and remove the key
                    # at the end, restoring the pre-phrase representation.
                    try:
                        default = float(self.engine.parameter_catalog(block).get(key, (0.0, 0.0, 0.0))[0])
                    except (TypeError, ValueError, KeyError):
                        default = 0.0
                    targets.setdefault(block.id, {})[key] = (False, default)
                    missing.setdefault(block.id, set()).add(key)
        return targets, missing

    def start_phrase(self, project: Any, phrase_id: str, block_ids: list[int] | None = None, amount: float = 1.0,
                     duration_beats: float | None = None):
        phrase = phrase_with_duration(phrase_for(phrase_id), duration_beats)
        if phrase is None or not phrase.stages:
            return False
        wanted = set(int(x) for x in block_ids) if block_ids else {b.id for b in project.blocks}
        self.active_phrase_releases.pop(str(phrase.id), None)
        targets, missing = self._snapshot_phrase(project, phrase, wanted)
        # PhraseState is the only phrase runtime state. Legacy active_phrases was removed in v100 cleanup.
        curve = self.engine.director.phrase.tension
        curve_length = max((point.beat for point in curve.points), default=phrase.total_beats)
        if curve_length > 0:
            curve = replace(curve, points=[replace(point, beat=point.beat * phrase.total_beats / curve_length)
                                           for point in curve.points])
        self.engine.director.motifs.set_phrase(phrase.id, phrase.name, list(self.engine.director.motifs.motifs), curve)
        state = self.engine.director.motifs.phrase_state
        self.engine.director.phrase = state
        state.position_beats = 0.0
        state.stage_index = -1
        state.intensity = max(0.0, min(1.0, float(amount)))
        state.block_ids = sorted(wanted)
        state.running = True
        state.memory = {
            "snapshot": targets,
            "snapshot_missing": missing,
            "total_beats": float(phrase.total_beats),
        }
        # Prime the multidimensional Director state at the exact phrase start.
        self.engine.director.snapshot(0.0)
        return True

    def update_phrase_duration(self, duration_beats: float):
        """Stretch the current phrase while preserving its musical progress."""
        state = self.engine.director.phrase
        phrase = phrase_with_duration(phrase_for(state.phrase_id), duration_beats)
        if phrase is None:
            return
        original = phrase_for(state.phrase_id)
        old_total = float(state.memory.get("total_beats", original.total_beats))
        ratio = phrase.total_beats / max(.25, old_total)
        state.position_beats *= ratio
        state.memory["total_beats"] = phrase.total_beats
        state.tension = replace(state.tension, points=[replace(point, beat=point.beat * ratio)
                                                      for point in state.tension.points])
        for active in self.active.values():
            if active.phrase_id == state.phrase_id:
                active.beats *= ratio
                active.elapsed_beats *= ratio
                active.crossfade_beats *= ratio
        self.engine.director.snapshot()

    def update_phrase_amount(self, amount: float):
        """Apply a new phrase amount to the running stage immediately."""
        state = self.engine.director.phrase
        value = max(0.0, min(1.0, float(amount)))
        state.intensity = value
        if not state.running:
            return
        phrase = phrase_for(state.phrase_id)
        if phrase is None or state.stage_index < 0:
            return
        for block in self.project.blocks:
            active = self.active.get(block.id)
            if active is None or active.phrase_id != phrase.id:
                continue
            stage = resolve_phrase_stage(phrase, block.block_type, state.stage_index)
            active.amount = max(0.0, min(1.0, float(stage.amount) * value))
            active.current_values.clear()

    def _begin_phrase_release(self, pid: str, state: Any, phrase: PerformancePhrase):
        targets = state.memory.get("snapshot", {})
        missing = state.memory.get("snapshot_missing", {})
        if not targets:
            return
        self.active_phrase_releases[pid] = ActivePhraseRelease(
            phrase_id=pid, elapsed_beats=0.0, beats=max(.5, float(getattr(phrase, "release_beats", 2.0))),
            targets=targets, missing_keys=missing,
        )

    def stop_phrase(self, phrase_id: str):
        state = self.engine.director.phrase
        pid = str(phrase_id)
        phrase = phrase_with_duration(phrase_for(pid), state.memory.get("total_beats"))
        if state.running and state.phrase_id == pid and phrase is not None:
            self._begin_phrase_release(pid, state, phrase)
        for block_id, active in list(self.active.items()):
            if active.phrase_id == pid:
                self.active.pop(block_id, None)
        if state.phrase_id == pid:
            state.running = False
            state.stage_index = -1
            state.memory = {}

    def _activate_phrase_stage(self, project: Any, state: Any, phrase: PerformancePhrase, stage_index: int):
        state.stage_index = stage_index
        wanted=set(state.block_ids)
        for block in project.blocks:
            if block.id not in wanted:
                continue
            stage = resolve_phrase_stage(phrase, block.block_type, stage_index)
            self.start(block, stage.technique_id, amount=stage.amount * state.intensity, shape=stage.shape or phrase.stages[stage_index].shape or "in", beats=stage.beats, phrase_id=phrase.id)

    def tick(self, running: bool = True):
        now = time.monotonic()
        dt = max(0.0, min(.1, now - self._last_time))
        self._last_time = now
        if not running:
            return
        beat_dt = dt * float(getattr(self.project, "tempo", 120)) / 60.0
        state=self.engine.director.phrase
        if state.running:
            phrase=phrase_with_duration(phrase_for(state.phrase_id), state.memory.get("total_beats"))
            if phrase is None:
                state.running=False
            else:
                state.advance(beat_dt)
                elapsed=state.position_beats
                cursor=0.0; stage_index=len(phrase.stages)-1
                for i,stage in enumerate(phrase.stages):
                    cursor += max(.25,float(stage.beats))
                    if elapsed < cursor:
                        stage_index=i; break
                if stage_index != state.stage_index:
                    self._activate_phrase_stage(self.project,state,phrase,stage_index)
                if elapsed >= phrase.total_beats:
                    self.stop_phrase(phrase.id)
        # Snapshot-based release is deliberately processed separately from
        # active techniques, so STOP cannot jump directly to the old values.
        for release_id, release in list(self.active_phrase_releases.items()):
            release.elapsed_beats += beat_dt
            progress = min(1.0, release.elapsed_beats / max(.5, release.beats))
            t = _shape(progress, "out")
            for block in list(self.project.blocks):
                values = release.targets.get(block.id)
                if not values:
                    continue
                for key, (_, target) in values.items():
                    current = block.parameters.get(key, target)
                    try:
                        current_f = float(current)
                    except (TypeError, ValueError):
                        current_f = target
                    value = current_f + (target - current_f) * t
                    if not self.engine.set_parameter(block, key, value):
                        block.parameters[key] = float(value)
                if block.mode == "SEQ" and progress < 1.0:
                    self.engine.regenerate(block)
            if progress >= 1.0:
                for block in list(self.project.blocks):
                    missing = release.missing_keys.get(block.id, set())
                    for key in missing:
                        block.parameters.pop(key, None)
                    if block.id in release.targets and block.mode == "SEQ":
                        self.engine.regenerate(block)
                self.active_phrase_releases.pop(release_id, None)
        for block in list(self.project.blocks):
            state = self.active.get(block.id)
            if state is None or not state.enabled:
                continue
            preset = preset_for(block.block_type, block.algorithm, state.preset_id)
            if preset is None and state.phrase_id is not None:
                preset = _PRESET_BY_ID.get(state.preset_id)
            if preset is None:
                self.stop(block.id)
                continue
            state.elapsed_beats += beat_dt
            progress = min(1.0, state.elapsed_beats / max(.25, state.beats))
            values = interpolate_preset(preset, progress, state.amount, state.shape)
            # Smooth stage boundary: blend from the outgoing parameter state
            # into the incoming stage during a short musical overlap.
            if state.phrase_id is not None and state.crossfade_beats > 0 and state.elapsed_beats < state.crossfade_beats:
                xf=_shape(state.elapsed_beats/state.crossfade_beats,"in_out")
                for key,value in list(values.items()):
                    if key in state.crossfade_from:
                        values[key]=state.crossfade_from[key] + (float(value)-state.crossfade_from[key])*xf
            state.current_values = {str(key): float(value) for key, value in values.items()}
            for key, value in values.items():
                if key == "gate":
                    block.parameters[key] = max(.05, min(1.0, float(value)))
                elif not self.engine.set_parameter(block, key, value):
                    # Representation parameters such as velocity_base and
                    # velocity_accent are valid performance destinations even
                    # when an older project did not serialize them explicitly.
                    block.parameters[key] = float(value)
            # LIVE reads parameters on the next event. SEQ needs regeneration
            # so a gesture changes the cached representation, but regenerating
            # at 5 ms transport resolution would waste CPU and can reshuffle a
            # pattern too aggressively. Rebuild at musical gesture increments.
            if block.mode == "SEQ" and (progress >= 1.0 or progress - state.last_regenerated_progress >= .04):
                self.engine.regenerate(block)
                state.last_regenerated_progress = progress
            if progress >= 1.0:
                # A gesture is a performance event, not a permanent override.
                self.stop(block.id)
                self.engine.regenerate(block)

# ---------------------------------------------------------------------------
# Musical phrases: composed performance gestures spanning multiple blocks.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PhraseStage:
    technique_id: str
    beats: float
    amount: float = 1.0
    shape: str | None = None
    label: str = ""


@dataclass(frozen=True)
class PerformancePhrase:
    id: str
    name: str
    description: str
    stages: tuple[PhraseStage, ...]
    roles: dict[str, tuple[str, ...]] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    release_beats: float = 2.0

    @property
    def total_beats(self) -> float:
        return sum(max(.25, float(s.beats)) for s in self.stages)


PHRASES = (
    PerformancePhrase(
        "opening_bloom", "Opening Bloom",
        "Calm opening: density and dynamics grow as the register gradually opens.",
        (PhraseStage("crescendo", 4, .8, "in", "Crescendo"),
         PhraseStage("density_swell", 4, .9, "in", "Density Swell"),
         PhraseStage("register_rise", 4, .65, "in", "Register Rise")),
        roles={"DRUM": ("crescendo", "density_swell", "density_swell"),
               "PERCUSSION": ("crescendo", "density_swell", "density_swell"),
               "BASS": ("crescendo", "density_swell", "register_rise"),
               "MELODY": ("crescendo", "density_swell", "register_rise"),
               "PAD": ("crescendo", "crescendo", "register_rise"),
               "CHORD": ("crescendo", "density_swell", "register_rise")},
        tags=("intro", "build", "multi-block")),
    PerformancePhrase(
        "tension_rise", "Tension Rise",
        "Rising tension: stringendo → accent build → register expansion.",
        (PhraseStage("stringendo", 4, .9, "in", "Stringendo"),
         PhraseStage("accent_build", 4, 1.0, "in", "Accent Build"),
         PhraseStage("register_rise", 4, .8, "in", "Register Rise")),
        roles={"DRUM": ("density_swell", "accent_build", "accelerando"),
               "PERCUSSION": ("density_swell", "accent_build", "accelerando"),
               "BASS": ("stringendo", "accent_build", "register_rise"),
               "MELODY": ("stringendo", "accent_build", "register_rise"),
               "PAD": ("crescendo", "accent_build", "register_rise"),
               "CHORD": ("stringendo", "accent_build", "register_rise")},
        tags=("tension", "build", "climax")),
    PerformancePhrase(
        "climax_release", "Climax → Release",
        "A climax followed by ritardando and diminuendo.",
        (PhraseStage("crescendo", 4, 1.0, "in", "Crescendo"),
         PhraseStage("sforzando", 1, 1.0, "pulse", "Sforzando"),
         PhraseStage("ritardando", 4, .85, "out", "Ritardando"),
         PhraseStage("diminuendo", 6, .9, "out", "Diminuendo")),
        roles={"DRUM": ("crescendo", "sforzando", "ritardando", "diminuendo"),
               "PERCUSSION": ("crescendo", "sforzando", "ritardando", "diminuendo"),
               "BASS": ("crescendo", "sforzando", "ritardando", "diminuendo"),
               "MELODY": ("crescendo", "sforzando", "ritardando", "diminuendo"),
               "PAD": ("crescendo", "sforzando", "ritardando", "smorzando"),
               "CHORD": ("crescendo", "sforzando", "ritardando", "diminuendo")},
        tags=("climax", "release", "cadence")),
    PerformancePhrase(
        "breath", "Breath",
        "A breathing phrase: expansion, a brief hold, and a gentle release.",
        (PhraseStage("density_swell", 4, .7, "in", "Expand"),
         PhraseStage("tenuto", 2, .7, "in", "Hold"),
         PhraseStage("rubato", 4, .8, "pulse", "Rubato"),
         PhraseStage("smorzando", 6, .8, "out", "Release")),
        roles={"DRUM": ("density_swell", "tenuto", "rubato", "smorzando"),
               "PERCUSSION": ("density_swell", "tenuto", "rubato", "smorzando"),
               "BASS": ("density_swell", "tenuto", "rubato", "smorzando"),
               "MELODY": ("density_swell", "tenuto", "rubato", "smorzando"),
               "PAD": ("density_swell", "tenuto", "rubato", "smorzando"),
               "CHORD": ("density_swell", "tenuto", "rubato", "smorzando")},
        tags=("phrase", "breath", "rubato")),
    PerformancePhrase(
        "accelerando_release", "Accelerando → Release",
        "Gradual acceleration, a peak of activity, then an organized slowdown.",
        (PhraseStage("accelerando", 6, .9, "in", "Accelerando"),
         PhraseStage("density_swell", 4, 1.0, "in", "Density"),
         PhraseStage("ritardando", 6, .9, "out", "Ritardando")),
        roles={"DRUM": ("accelerando", "density_swell", "ritardando"),
               "PERCUSSION": ("accelerando", "density_swell", "ritardando"),
               "BASS": ("accelerando", "density_swell", "ritardando"),
               "MELODY": ("accelerando", "density_swell", "ritardando"),
               "PAD": ("accelerando", "crescendo", "ritardando"),
               "CHORD": ("accelerando", "density_swell", "ritardando")},
        tags=("tempo", "build", "release")),
)

_PHRASE_BY_ID = {p.id: p for p in PHRASES}


def phrases() -> list[PerformancePhrase]:
    return list(PHRASES)


def phrase_for(phrase_id: str) -> PerformancePhrase | None:
    return _PHRASE_BY_ID.get(str(phrase_id))


def phrase_with_duration(phrase: PerformancePhrase | None, beats: float | None = None) -> PerformancePhrase | None:
    """Return a scaled copy; the shared phrase catalog remains immutable."""
    if phrase is None or beats is None:
        return phrase
    try:
        total = float(beats)
    except (TypeError, ValueError):
        return phrase
    if not math.isfinite(total):
        return phrase
    # Four beats keeps even the shortest catalog stage above the runtime's
    # quarter-beat minimum; longer phrases can span up to 64 bars in 4/4.
    total = max(4.0, min(256.0, total))
    ratio = total / phrase.total_beats
    return replace(phrase, stages=tuple(replace(stage, beats=stage.beats * ratio) for stage in phrase.stages))


def phrase_techniques(phrase: PerformancePhrase, block_type: str) -> tuple[str, ...]:
    role = str(block_type).upper()
    return phrase.roles.get(role, tuple(s.technique_id for s in phrase.stages))


def resolve_phrase_stage(phrase: PerformancePhrase, block_type: str, stage_index: int) -> PhraseStage:
    ids = phrase_techniques(phrase, block_type)
    if not ids:
        return phrase.stages[min(stage_index, len(phrase.stages) - 1)]
    idx = min(stage_index, len(ids) - 1)
    desired = ids[idx]
    base = phrase.stages[min(stage_index, len(phrase.stages) - 1)]
    preset = preset_for(block_type, "", desired)
    if preset is None:
        preset = _PRESET_BY_ID.get(desired)
    if preset is None:
        desired = base.technique_id
    return PhraseStage(desired, base.beats, base.amount, base.shape, base.label or desired)
