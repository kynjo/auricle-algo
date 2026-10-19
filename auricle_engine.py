"""Music generation, relations, mutations and LIVE event production."""

from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, replace
from typing import Optional

from auricle_catalogs import *  # noqa: F401,F403
from auricle_catalogs import _clamp, _as_float
from auricle_model import *  # noqa: F401,F403
from generators import *  # noqa: F401,F403
from performance_presets import PerformanceRuntime, presets_for, preset_for
from motif_engine import Motif, MotifEngine, PhraseState, TensionCurve
from music_director import MusicDirector
from voice_leading import VoiceLeading
from relation_context import MusicalContext, analyze_groove, default_relations
from auricle_drum import fill_at, kit_value, kit_random, live_timing_factor
from musical_clock import MusicalClock
from motif_development import MotifDevelopment
from coordinated_kit import KitCoordinator, coordinated, STEP_BEATS, CREATIVE_DEFAULTS
from motif_development import digest
from pattern_chance import chance_at
from parameter_influence import ParameterInfluence
from harmonic_plan import HarmonicRuntime
from instrument_dialogue import DialogueRuntime

class MusicEngine:
    def __init__(self, project: Project):
        self.project = project
        self.parameter_influence = ParameterInfluence()
        self.harmonic_runtime = HarmonicRuntime(project)
        self.dialogue_runtime = DialogueRuntime(project)
        self.live_rng: dict[int, random.Random] = {}
        self.live_state: dict[int, dict[str, Any]] = {}
        self.pending_parameter_modulations: dict[tuple[int, str], float] = {}
        self.parameter_modulation_state: dict[tuple[int, str], float] = {}
        self.delayed_parameter_modulations: list[tuple[int, tuple[int, str], float]] = []
        # Pre-relation SEQ material per block. Relations are always applied on
        # top of this, so calling apply_relations() repeatedly is idempotent.
        self._base_outputs: dict[int, dict[str, list[float]]] = {}
        self.clock = MusicalClock(project.tempo)
        self._seq_motifs = {}
        self._seq_motif_tokens = {}
        self.motif_development = MotifDevelopment()
        self.kit_coordinator = KitCoordinator()
        self._seq_kit_tokens = {}
        self._kit_source_cache = {}
        self._kit_live_slots = {}
        self.performance = PerformanceRuntime(project, self)
        # v100 musical director pipeline
        self.director = MusicDirector(project)
        self.voice_leading = VoiceLeading()
        # v101 rhythm-first relations context
        self.musical_context = MusicalContext()
        self.relation_templates = default_relations()
        # Last SEQ step played per block (set by the transport).  LIVE
        # relation destinations read their sources at this position.
        self.source_positions: dict[int, int] = {}

    # ---- helpers ----------------------------------------------------------
    def _seed_for(self, block: Block) -> int:
        try:
            variation_seed = int(block.parameters.get("variation_seed", 0))
        except (TypeError, ValueError):
            variation_seed = 0
        return self.project.seed + block.id * 1009 + variation_seed * 7919

    def _rng_for(self, block: Block) -> random.Random:
        if block.id not in self.live_rng:
            self.live_rng[block.id] = random.Random(self._seed_for(block))
        return self.live_rng[block.id]

    def _root(self, block: Block) -> int:
        return block_root(self.project, block)

    def _apply_relation_context(self, block: Block, representation):
        """v101.1 lightweight live relations: rhythm-first influence layer."""
        role = str(block.block_type).upper()
        ctx = self.musical_context
        # Rhythm authority: drums define groove density for rhythmic roles.
        if role == "BASS":
            source = self.role_relation_source(block)
            groove = self._groove_for_block(block)
            groove_active = source is not None and bool(source.outputs.get("rhythm", []))
        else:
            groove = ctx.groove
            groove_active = role in ("PERCUSSION", "MELODY") and bool(ctx.values.get("groove_sources"))
        if groove_active:
            factor = 0.85 + groove * 0.30
            for i, hit in enumerate(representation.rhythm):
                if hit > 0:
                    representation.velocity[i] = _clamp(representation.velocity[i] * factor, 0.0, 1.0)
        # Harmony authority: melodic/harmonic roles become slightly more stable
        # when harmony confidence is high.
        if role in ("MELODY", "PAD", "CHORD"):
            self.musical_context.values["harmony_follow"] = ctx.harmony

    def _apply_groove_to_representation(self, block: Block, representation):
        """Apply the active groove context to generated material.

        v101.2 exposed groove parameters but not every generation path consumed
        them. This keeps groove as a musical transformation stage after basic
        relations context and before final role/scale processing.
        """
        role = str(block.block_type).upper()
        if role in ("PERCUSSION", "DRUM"):
            return
        params = block.parameters
        follow = _clamp(float(params.get("groove_follow", 0.0)), 0.0, 1.0)
        if follow <= 0.0:
            return
        groove = self._groove_for_block(block)
        for i, hit in enumerate(representation.rhythm):
            if hit <= 0:
                continue
            # Higher groove confidence tightens duration and accent stability.
            tighten = 1.0 - 0.18 * groove * follow
            representation.duration[i] = max(0.03, representation.duration[i] * tighten)
            representation.velocity[i] = _clamp(
                representation.velocity[i] * (0.9 + 0.2 * groove * follow), 0.0, 1.0
            )
        self.musical_context.values["groove_applied"] = {
            "block": block.id, "amount": follow, "groove": groove
        }

    def _groove_for_block(self, block: Block) -> float:
        """Return the groove authority that applies to this destination.

        The project-wide context remains useful for roles without an explicit
        drum relation.  BASS, however, has a selectable Drum source; its
        timing/velocity shaping must use the same source as its groove mask.
        """
        role = str(block.block_type).upper()
        if role == "BASS":
            source = self.role_relation_source(block)
            if source is not None:
                rhythm = source.outputs.get("rhythm", [])
                accents = source.outputs.get("accent", []) or source.outputs.get("velocity", [])
                if not rhythm:
                    return 0.0
                return _clamp(float(analyze_groove(rhythm, accents)["groove"]), 0.0, 1.0)
            if not self.musical_context.values.get("groove_sources"):
                return 0.0
        if not self.musical_context.values.get("groove_sources"):
            return 0.0
        return _clamp(float(self.musical_context.groove), 0.0, 1.0)

    @staticmethod
    def _stream_value(stream: list[float], index: int, default: float = 0.0) -> float:
        """Read a cyclic relation stream without assuming equal block lengths."""
        if not stream:
            return default
        try:
            return float(stream[index % len(stream)])
        except (TypeError, ValueError):
            return default

    def _apply_drum_to_bass(self, drum: Block, bass: Block):
        """Apply the v101.2 groove mask and accents to one bass block.

        The operation is performed from the pre-relation snapshot, so it is
        deterministic and idempotent. ``groove_follow=1`` is a strict drum
        mask; lower values add selected drum hits while preserving bass hits.
        ``groove_accent`` transfers kick/snare accents into bass velocity.
        """
        params = bass.parameters
        amount = _clamp(float(params.get("groove_follow", 0.70)), 0.0, 1.0)
        accent_amount = _clamp(float(params.get("groove_accent", 0.65)), 0.0, 1.0)
        if amount <= 0.0 and accent_amount <= 0.0:
            return
        base_rhythm = list(bass.outputs.get("rhythm", []))
        base_velocity = list(bass.outputs.get("velocity", []))
        base_duration = list(bass.outputs.get("duration", []))
        base_accent = list(bass.outputs.get("accent", []))
        if not base_rhythm:
            return
        groove = drum.outputs.get("rhythm", [])
        groove_accents = drum.outputs.get("accent", []) or drum.outputs.get("velocity", [])
        offset = int(_as_float(params.get("groove_offset", 0), 0))
        replace = str(params.get("groove_mode", "Union")).strip().lower() == "replace"
        # A LIVE bass holds one event: align it with the drum's current step.
        live_base = self.source_positions.get(drum.id, 0) if bass.mode == "LIVE" and (drum.mode != "LIVE" or coordinated(drum)) else 0
        rhythm, velocity, duration, accents = [], [], [], []
        for i, base_hit in enumerate(base_rhythm):
            source_index = live_base + i + offset
            drum_hit = self._stream_value(groove, source_index)
            drum_accent = _clamp(self._stream_value(groove_accents, source_index), 0.0, 1.0)
            if amount >= 0.999:
                hit = 1.0 if drum_hit > 0.0 else 0.0
            elif amount > 0.0 and drum_hit > 0.0:
                # Stable per-step selection makes the amount meaningful while
                # keeping the generated groove unchanged on every regeneration.
                selector = ((self.project.seed + bass.id * 7919 + (live_base + i) * 104729) % 1000) / 1000.0
                add_hit = selector < amount
                if replace:
                    # Replace: the bass keeps only the selected drum hits
                    # (this branch used to behave exactly like Union).
                    hit = 1.0 if add_hit else 0.0
                else:
                    hit = 1.0 if (base_hit > 0.0 or add_hit) else 0.0
            elif replace and amount > 0.0:
                hit = 0.0
            else:
                hit = 1.0 if base_hit > 0.0 else 0.0
            old_velocity = self._stream_value(base_velocity, i, 0.8)
            old_duration = self._stream_value(base_duration, i, float(params.get("gate", 0.90)))
            old_accent = self._stream_value(base_accent, i, 1.0 if old_velocity >= 0.85 else 0.0)
            if hit > 0.0 and old_velocity <= 0.0:
                old_velocity = _clamp(float(params.get("velocity_base", 0.72)), 0.05, 1.0)
            if hit > 0.0 and old_duration <= 0.0:
                old_duration = _clamp(float(params.get("gate", 0.90)), 0.05, 1.5)
            if hit > 0.0 and accent_amount > 0.0:
                old_velocity = _clamp(old_velocity * (1.0 + drum_accent * accent_amount * 0.35), 0.0, 1.0)
                old_accent = max(old_accent, 1.0 if drum_accent * accent_amount >= 0.5 else 0.0)
            rhythm.append(hit)
            velocity.append(old_velocity if hit > 0.0 else 0.0)
            duration.append(old_duration if hit > 0.0 else 0.0)
            accents.append(old_accent if hit > 0.0 else 0.0)
        bass.outputs["rhythm"] = rhythm
        bass.outputs["density"] = list(rhythm)
        bass.outputs["velocity"] = velocity
        bass.outputs["duration"] = duration
        bass.outputs["accent"] = accents
        self.musical_context.values["drum_to_bass"] = {
            "source": drum.id, "target": bass.id, "groove_follow": amount,
            "groove_accent": accent_amount,
        }

    def _apply_chord_to_melody(self, chord: Block, melody: Block):
        """Pull melody pitches toward the nearest active chord tone."""
        if self.harmonic_runtime.follows(melody):
            return  # The bar plan is resolved once, after all stream relations.
        base_amount = _clamp(float(melody.parameters.get("harmony_anchor", 0.55)), 0.0, 1.0)
        # MusicalContext is the harmonic authority.  Keep the default context
        # neutral (0.5 => unchanged) while allowing active chord confidence to
        # strengthen or soften the configured anchor amount.
        harmony = _clamp(float(self.musical_context.harmony), 0.0, 1.0)
        amount = _clamp(base_amount * (0.75 + 0.5 * harmony), 0.0, 1.0)
        if amount <= 0.0:
            return
        melody_pitch = list(melody.outputs.get("pitch", []))
        melody_rhythm = melody.outputs.get("rhythm", [])
        chord_pitch = chord.outputs.get("pitch", [])
        chord_rhythm = chord.outputs.get("rhythm", [])
        if not melody_pitch or not chord_pitch:
            return
        out = list(melody_pitch)
        live_base = self.source_positions.get(chord.id, 0) if melody.mode == "LIVE" and chord.mode != "LIVE" else 0
        for i, value in enumerate(melody_pitch):
            if self._stream_value(melody_rhythm, i) <= 0.0:
                continue
            chord_index = (live_base + i) % len(chord_pitch)
            # A sustained chord may span rests in its source pattern. Reuse
            # the nearest previous active chord event for a stable harmony.
            chord_active = not chord_rhythm or self._stream_value(chord_rhythm, chord_index) > 0.0
            if not chord_active:
                found = False
                # Search only earlier steps in this cycle.  Wrapping with `%`
                # here made a melody at bar start borrow a chord that had not
                # happened yet later in the bar.
                for distance in range(1, chord_index + 1):
                    candidate = chord_index - distance
                    if self._stream_value(chord_rhythm, candidate) > 0.0:
                        chord_index = candidate
                        found = True
                        break
                # There is no earlier chord to reuse yet.  Keep the melody's
                # own pitch until a harmonic authority becomes active.
                if not found:
                    continue
            root_pitch = self._stream_value(chord_pitch, chord_index)
            tones = self._chord_pitches(chord, root_pitch)
            candidates = [tone + 12.0 * octave for tone in tones for octave in range(-8, 9)]
            anchor = min(candidates, key=lambda candidate: abs(candidate - float(value)))
            # Relations may pull toward a chord tone but must not leave the
            # melody's scale (unquantized blends produced C#, Bb, Ab in C).
            out[i] = self._quantize_pitch(melody, float(value) * (1.0 - amount) + anchor * amount)
        melody.outputs["pitch"] = out
        self.musical_context.values["chord_to_melody"] = {
            "source": chord.id, "target": melody.id, "harmony_anchor": amount,
            "configured_anchor": base_amount, "harmony": harmony,
        }

    def _apply_role_relations(self, skip_destination: int | None = None):
        """Run the built-in v101.2 relations on the current output snapshot."""
        drums = [b for b in self.project.blocks if str(b.block_type).upper() == "DRUM"]
        basses = [b for b in self.project.blocks if str(b.block_type).upper() == "BASS"]
        chords = [b for b in self.project.blocks if str(b.block_type).upper() == "CHORD"]
        melodies = [b for b in self.project.blocks if str(b.block_type).upper() == "MELODY"]
        # The source is selectable per destination (relation_drum_source /
        # relation_chord_source); the first block is only the fallback.
        for bass in basses:
            if skip_destination is not None and bass.id == skip_destination:
                continue
            source = self._select_role_source(drums, bass, "relation_drum_source")
            if source is not None and not self._has_explicit_role_route(source, bass, "rhythm", "rhythm"):
                self._apply_drum_to_bass(source, bass)
        for melody in melodies:
            if skip_destination is not None and melody.id == skip_destination:
                continue
            source = self._select_role_source(chords, melody, "relation_chord_source")
            if source is not None and not self._has_explicit_role_route(source, melody, "pitch", "pitch"):
                self._apply_chord_to_melody(source, melody)

    def _has_explicit_role_route(self, source: Block, destination: Block,
                                 source_part: str, destination_part: str) -> bool:
        """Return whether a visible relation replaces a built-in role route."""
        return any(
            getattr(relation, "enabled", True)
            and relation.algorithm != 'Dialogue'
            and int(getattr(relation, "source_block", -1)) == int(source.id)
            and int(getattr(relation, "destination_block", -1)) == int(destination.id)
            and str(getattr(relation, "source_part", "")) == source_part
            and str(getattr(relation, "destination_part", "")) == destination_part
            for relation in self.project.relations
        )


    def _scale(self, block: Block) -> str:
        return str(block.parameters.get("scale_name", self.project.scale))

    def _quantize_pitch(self, block: Block, pitch: float) -> float:
        """Quantize a *relative* pitch (offset from the block root) to its scale.

        Generated pitches are offsets from the root; MIDI adds the key later.
        Quantizing the offset against the absolute root (e.g. 69 for A)
        shifted the scale by the key, so non-C keys produced wrong notes
        (A major sent D#).
        """
        root = self._root(block)
        return float(round(quantize_to_scale(root + float(pitch), root, self._scale(block)) - root))

    def _scale_degree(self, block: Block, pitch: float) -> int:
        """Scale-degree index (octaves included) of a relative pitch."""
        intervals = scale_intervals(self._scale(block))
        q = int(round(self._quantize_pitch(block, pitch)))
        octave, pc = divmod(q, 12)
        idx = intervals.index(pc) if pc in intervals else min(range(len(intervals)), key=lambda k: abs(intervals[k] - pc))
        return octave * len(intervals) + idx

    @staticmethod
    def _select_role_source(candidates: list, target: Block, key: str):
        """Source chosen by ``key`` (block id) on the target, else the first one."""
        try:
            wanted = int(target.parameters.get(key, -1))
        except (TypeError, ValueError):
            wanted = -1
        for item in candidates:
            if item.id == wanted:
                return item
        return candidates[0] if candidates else None

    def role_relation_source(self, block: Block):
        """Built-in relation source of a BASS (DRUM) or MELODY (CHORD) block."""
        role = str(block.block_type).upper()
        kind, key = {"BASS": ("DRUM", "relation_drum_source"), "MELODY": ("CHORD", "relation_chord_source")}.get(role, (None, None))
        if kind is None:
            return None
        pool = [b for b in self.project.blocks if str(b.block_type).upper() == kind]
        return self._select_role_source(pool, block, key)

    def _relation_participant(self, block: Block) -> bool:
        if str(block.block_type).upper() in ("DRUM", "BASS", "CHORD", "MELODY"):
            return True
        return any(getattr(r, "enabled", True) and block.id in (r.source_block, r.destination_block)
                   for r in self.project.relations)

    def _sync_rhythm_dependents(self, block: Block):
        """Keep velocity/duration/density/accent consistent with a rhythm that
        a relation changed (new hits used to keep velocity 0 -> sent as 1)."""
        out = block.outputs
        rhythm = list(out.get("rhythm", []))
        p = block.parameters
        default_velocity = _clamp(_as_float(p.get("velocity_base", 0.72), 0.72), 0.05, 1.0)
        gate = _clamp(_as_float(p.get("gate", 0.78), 0.78), 0.05, 1.5)

        def fit(name):
            return (list(out.get(name, [])) + [0.0] * len(rhythm))[:len(rhythm)]

        velocity, duration = fit("velocity"), fit("duration")
        for i, r in enumerate(rhythm):
            if r > 0:
                if velocity[i] <= 0:
                    velocity[i] = default_velocity
                if duration[i] <= 0:
                    duration[i] = gate
            else:
                velocity[i] = 0.0
                duration[i] = 0.0
        out["velocity"] = velocity
        out["duration"] = duration
        out["density"] = [1.0 if r > 0 else 0.0 for r in rhythm]
        out["accent"] = [1.0 if (r > 0 and v >= 0.85) else 0.0 for r, v in zip(rhythm, velocity)]

    def reset_live(self):
        self.live_rng.clear()
        self.live_state.clear()
        self.pending_parameter_modulations.clear()
        self.parameter_modulation_state.clear()
        self.delayed_parameter_modulations.clear()
        self.source_positions.clear()
        self._kit_live_slots.clear()
        self._kit_source_cache.clear()
        # Voice-leading history belongs to a live session.  Keeping it after
        # reset or STOP->PLAY causes the first notes of a new phrase to be
        # pulled toward an unrelated previous phrase.
        if hasattr(self, "voice_leading"):
            self.voice_leading.reset()
        if hasattr(self, "performance"):
            self.performance.active.clear()

    def find_block(self, block_id) -> Optional[Block]:
        return next((b for b in self.project.blocks if b.id == block_id), None)

    def event_probability(self, block: Block) -> float:
        base = _clamp(float(block.parameters.get("event_probability", 1.0)), 0.0, 1.0)
        if getattr(self.director.phrase, "running", False):
            snap=self.director.snapshot()
            role=self.director.role_state(str(block.block_type).upper(),snap)
            # Do not multiply Macro/Technique/Director activity repeatedly.
            # A low explicit block value is still respected, but performance
            # layers cannot accidentally collapse a healthy part to silence.
            return self.director.bounded_combine(base,role.probability,.10)
        return base

    def _fill_density_value(self, block: Block) -> float:
        # `event_density` is retained as a backwards-compatible alias for
        # projects created before the universal Fill/Density control existed.
        # Density is a user-facing generator control.  role_density is a
        # derived role/profile value and must not override the explicit knob.
        return _clamp(float(block.parameters.get(
            "fill_density", block.parameters.get("event_density", block.parameters.get("role_density", 1.0)))), 0.0, 1.0)

    def _zero_is_rest(self, block: Block) -> bool:
        """True for generators where a 0.0 value means "no event".

        Pitch generators legitimately emit 0.0 (the root note); they mark rests
        with ``None`` instead.
        """
        p = block.parameters
        if block.algorithm in RHYTHM_ALGORITHMS or block.algorithm == "Pattern":
            return True
        if block.algorithm == "De Bruijn":
            return str(p.get("debruijn_mode", "Rhythm")) == "Rhythm"
        if block.algorithm == "Cellular Automaton":
            return str(p.get("ca_mode", "Rhythm")) == "Rhythm"
        if block.algorithm == "L-System":
            return str(p.get("ls_mode", "Pitch")) == "Rhythm"
        return False

    def _sequence_pitches(self, block: Block, raw: list[float]) -> list[float]:
        """Map a Fibonacci/Recaman number stream onto scale degrees."""
        p = block.parameters
        mod = max(1, int(p.get("sequence_mod", 7)))
        stride = int(p.get("sequence_stride", 1))
        offset = int(p.get("sequence_offset", 0))
        if p.get("sequence_reverse", 0):
            raw = list(reversed(raw))
        root, scale = self._root(block), self._scale(block)
        return [degree_to_note((int(v) * stride + offset) % mod, root, scale) - root for v in raw]

    def _pattern_values(self, block: Block, length: Optional[int] = None) -> list[float]:
        """Pattern generator values after reverse/rotation/scale.

        With ``length`` the pattern is first tiled to the project length (SEQ);
        without it the transforms apply to one pattern cycle (LIVE).
        """
        p = block.parameters
        values = parse_number_list(p.get("pattern", DEFAULT_PATTERN), float,
                                   parse_number_list(DEFAULT_PATTERN, float))
        if length is not None:
            values = fixed_pattern(length, values)
        if p.get("pattern_reverse", 0):
            values = list(reversed(values))
        rotate = int(p.get("pattern_rotation", 0)) % max(1, len(values))
        if rotate:
            values = values[rotate:] + values[:rotate]
        scale = max(0.0, float(p.get("pattern_scale", 1.0)))
        return [v * scale for v in values]

    def pattern_step_allowed(self, block, slot):
        """A reproducible per-pass output gate, independent of cached SEQ data."""
        if (block.algorithm != "Pattern" or "pattern_step_chances" not in block.parameters
                or self.active_motif(block) is not None):
            return True
        buffered = (block.mode == "SEQ" or self.coordinated_drum(block) is not None
                    or self._drum_window_processing_needed(block))
        cycle = self._kit_cycle_length(block) if buffered else None
        chance = chance_at(block.parameters, slot, cycle)
        return chance >= 1. or (chance > 0. and kit_random(self._seed_for(block), int(slot), 113) < chance)

    # ---- SEQ generation ---------------------------------------------------
    def _seq_material(self, block: Block, length: int, rng: random.Random) -> list:
        p = block.parameters
        alg = block.algorithm
        root, scale = self._root(block), self._scale(block)
        if alg == "Euclidean":
            steps = max(1, min(length, int(p.get("euclidean_steps", length))))
            return euclidean(steps, min(int(p.get("pulses", 5)), steps), int(p.get("euclidean_rotation", 0)))
        if alg == "Bresenham":
            steps = max(1, min(length, int(p.get("bres_steps", length))))
            return bresenham(steps, min(int(p.get("bres_pulses", 5)), steps), int(p.get("bres_rotation", 0)))
        if alg == "Polyrhythm":
            return polyrhythm(length, int(p.get("poly_a", 3)), int(p.get("poly_b", 4)),
                              int(p.get("poly_phase_a", 0)), int(p.get("poly_phase_b", 0)), str(p.get("poly_mode", "OR")))
        if alg == "Thue-Morse":
            return thue_morse(length, int(p.get("tm_rotation", 0)), bool(p.get("tm_invert", 0)),
                              float(p.get("tm_density", 1.0)), rng)
        if alg == "Fibonacci Rhythm":
            return fibonacci_rhythm(length, float(p.get("fib_density", .5)), int(p.get("fib_offset", 0)))
        if alg == "Fibonacci":
            return self._sequence_pitches(block, fibonacci_sequence(length))
        if alg == "Recaman":
            return self._sequence_pitches(block, recaman_sequence(length))
        if alg == "De Bruijn":
            seq = de_bruijn(length, int(p.get("debruijn_order", 3)), str(p.get("debruijn_mode", "Rhythm")), root, scale)
            rot = int(p.get("debruijn_rotation", 0)) % max(1, len(seq))
            return seq[rot:] + seq[:rot] if rot else seq
        if alg == "Interval Walker":
            return interval_walker(length, rng, int(p.get("interval_step", 3)), float(p.get("interval_return", .2)),
                                   root, scale, bool(p.get("interval_quantize", 1)), int(p.get("interval_range", 24)),
                                   float(p.get("interval_leap", .08)))
        if alg == "Scale Walker":
            return scale_walker(length, rng, root, scale, int(p.get("scale_step", 1)), float(p.get("scale_direction", .5)),
                                int(p.get("scale_octaves", 2)), float(p.get("scale_leap", .08)))
        if alg == "Weighted Scale":
            return weighted_scale(length, rng, root, scale, str(p.get("scale_weights", "1,1,1,1,1,1,1")),
                                  float(p.get("scale_octave_spread", .15)))
        if alg == "Arpeggiator":
            return arpeggiator(length, rng, root, scale, str(p.get("arp_pattern", "0,2,4,6")), int(p.get("arp_octaves", 1)),
                               str(p.get("arp_direction", "Up")), str(p.get("arp_octave_mode", "Cycle")))
        if alg == "Cellular Automaton":
            return cellular_automaton(length, int(p.get("ca_rule", 30)), str(p.get("ca_seed", "00100000")),
                                      int(p.get("ca_generations", 2)), str(p.get("ca_mode", "Rhythm")), root, scale,
                                      float(p.get("ca_density", 1.0)), rng)
        if alg == "L-System":
            return lsystem_sequence(length, str(p.get("ls_axiom", "A")), str(p.get("ls_rule_a", "AB")), str(p.get("ls_rule_b", "A")),
                                    int(p.get("ls_iterations", 3)), str(p.get("ls_mode", "Pitch")),
                                    str(p.get("ls_mapping", "0,1,2,3,4,5,6")), root, scale)
        if alg == "Logistic Chaos":
            return logistic_chaos(length, float(p.get("chaos_r", 3.9)), float(p.get("chaos_x", .5)), root, scale,
                                  int(p.get("chaos_octaves", 2)), bool(p.get("chaos_quantize", 1)),
                                  float(p.get("chaos_smooth", 0.0)), int(p.get("chaos_burn_in", 0)))
        if alg == "Markov":
            return markov(length, rng, int(p.get("markov_jump", 3)), int(p.get("markov_transpose", 0)),
                          float(p.get("markov_rest", 0.0)), int(p.get("markov_octaves", 0)), float(p.get("markov_stay", 0.0)),
                          root, scale, bool(p.get("markov_scale", 1)), float(p.get("markov_leap", .12)))
        if alg == "Random Walk":
            return random_walk(length, rng, int(p.get("walk_step", 2)), int(p.get("walk_range", 12)),
                               float(p.get("walk_return_bias", 0.0)), int(p.get("walk_start", 0)), root,
                               float(p.get("walk_drift", 0.0)), scale, bool(p.get("walk_quantize", 1)))
        if alg == "Probability":
            return probability_pattern(length, float(p.get("probability", 0.5)), rng, int(p.get("probability_pitch_range", 7)),
                                       int(p.get("probability_octaves", 0)), int(p.get("probability_center", 0)))
        # Pattern (also the fallback for unknown algorithm names)
        sequence = self._pattern_values(block, length)
        gate_prob = _clamp(float(p.get("pattern_probability", 1.0)), 0.0, 1.0)
        if gate_prob < 1.0:
            sequence = [v if rng.random() < gate_prob else 0.0 for v in sequence]
        return sequence

    def _role_pitch(self, block: Block, pitch: float) -> float:
        """Place a generated pitch inside the musical register of its role."""
        profile = ROLE_PROFILES.get(block.block_type)
        if not profile or block.block_type in PERCUSSIVE_TYPES:
            return float(pitch)
        value = float(pitch)
        anchor = float(block.parameters.get("role_center", profile["register_anchor"]))
        width = max(6.0, float(block.parameters.get("role_width", profile["pitch_range"])))
        lo = anchor - width / 2.0
        hi = anchor + width / 2.0
        # Preserve pitch class while moving material into the role register.
        # BASS/PAD/CHORD have an explicit register anchor; MELODY intentionally
        # preserves the generator's octave choices whenever they fit.
        if block.block_type in ("BASS", "PAD", "CHORD"):
            while value - anchor > 6.0:
                value -= 12.0
            while value - anchor < -6.0:
                value += 12.0
        while value < lo:
            value += 12.0
        while value > hi:
            value -= 12.0
        return _clamp(value, lo, hi)

    def _apply_role_profile(self, block: Block, representation: MusicalRepresentation, rng: random.Random):
        """Give the generic musical representation its block-role semantics."""
        profile = ROLE_PROFILES.get(block.block_type)
        if not profile or block.block_type in PERCUSSIVE_TYPES:
            return
        # Rests are placed too: a relation can turn a rest into a hit, and its
        # pitch must then already sit in the role register.
        representation.pitch = [self._role_pitch(block, v) for v in representation.pitch]
        if block.block_type == "BASS" and profile.get("root_bias", 0.0) > 0:
            root_candidates = []
            for octave in range(-4, 4):
                root_candidates.extend([12.0 * octave, 7.0 + 12.0 * octave])
            anchor = float(block.parameters.get("role_center", profile["register_anchor"]))
            width = max(6.0, float(block.parameters.get("role_width", profile["pitch_range"])))
            lo, hi = anchor - width / 2.0, anchor + width / 2.0
            root_candidates = [self._role_pitch(block, x) for x in root_candidates if lo <= self._role_pitch(block, x) <= hi]
            if root_candidates:
                bias = _clamp(float(block.parameters.get("role_root_bias", profile["root_bias"])), 0.0, 1.0)
                for i, r in enumerate(representation.rhythm):
                    if r > 0 and rng.random() < bias:
                        current = representation.pitch[i]
                        representation.pitch[i] = min(root_candidates, key=lambda x: abs(x - current))
        # Role duration is an explicit, user-visible musical-role control.
        # It replaces the former hidden per-type multipliers.
        duration_factor = _clamp(float(block.parameters.get(
            "role_duration", profile.get("role_duration", 1.0))), 0.25, 4.0)
        representation.duration = [d * duration_factor if r > 0 else 0.0
                                   for d, r in zip(representation.duration, representation.rhythm)]

    def drum_parent_for(self, block):
        """Return the owning DRUM container for a child voice, if any."""
        parent_id = getattr(block, "parent_id", None)
        if parent_id is None:
            return None
        return next((item for item in self.project.blocks
                     if item.id == int(parent_id) and str(item.block_type).upper() == "DRUM"), None)

    def _aggregate_drum_outputs(self, drum: Block):
        """Expose the union of child voices as the parent DRUM source."""
        voices = ensure_drum_voices(drum)
        size = max((len(v.outputs.get("rhythm", [])) for v in voices), default=0)
        if coordinated(drum):
            size = self.kit_coordinator.plan(drum, self.project.seed, self.clock.position_beats).length
        if not size:
            drum.outputs = {part: [] for part in PARTS}
            self._base_outputs[drum.id] = {part: [] for part in PARTS}
            return
        rhythm = [0.0] * size
        velocity = [0.0] * size
        duration = [0.0] * size
        accent = [0.0] * size
        for voice in voices:
            if voice.muted:
                continue
            for i in range(size):
                if coordinated(drum, voice) and voice.mode == "LIVE":
                    slot = self._kit_live_slots.get(voice.id)
                    if slot is None or i != slot % size:
                        continue
                hit = self._stream_value(voice.outputs.get("rhythm", []), i)
                rhythm[i] = max(rhythm[i], hit)
                velocity[i] = max(velocity[i], self._stream_value(voice.outputs.get("velocity", []), i))
                duration[i] = max(duration[i], self._stream_value(voice.outputs.get("duration", []), i))
                accent[i] = max(accent[i], self._stream_value(voice.outputs.get("accent", []), i))
        drum.outputs = {
            "rhythm": rhythm, "pitch": [0.0] * size, "velocity": velocity,
            "duration": duration, "density": list(rhythm), "accent": accent,
        }
        self._base_outputs[drum.id] = {part: list(values) for part, values in drum.outputs.items()}

    def _generate_drum_container(self, drum: Block):
        """Generate all SEQ child voices and publish their union."""
        for voice in ensure_drum_voices(drum):
            if voice.mode == "SEQ":
                self.generate_block(voice)
            elif not self.live_state.get(voice.id, {}).get("events"):
                voice.outputs = {part: [] for part in PARTS}
        self._aggregate_drum_outputs(drum)

    def _kit_cycle_length(self, block):
        return max(1, min(int(self.project.length), int(block.parameters.get("structure_length", self.project.length))))

    def _kit_fill_at(self, block, index):
        drum = self.drum_parent_for(block)
        if coordinated(drum, block):
            return False
        return drum is not None and fill_at(drum, self._seed_for(block), index, self._kit_cycle_length(block))

    def coordinated_drum(self, block):
        drum = self.drum_parent_for(block)
        return drum if coordinated(drum, block) else None

    def kit_plan(self, block, beat=None):
        drum = self.coordinated_drum(block)
        if drum is None:
            return None
        return self.kit_coordinator.plan(drum, self.project.seed,
                                         self.clock.position_beats if beat is None else beat)

    def _apply_kit_plan(self, block, representation, plan, start_slot):
        if plan is None:
            return
        for i, hit in enumerate(representation.rhythm):
            decision = plan.at(block.id, start_slot + i)
            if not decision.allowed:
                for part in ("rhythm", "velocity", "duration", "density", "accent"):
                    getattr(representation, part)[i] = 0.0
            elif hit > 0 or decision.force:
                representation.rhythm[i] = representation.density[i] = 1.0
                velocity = representation.velocity[i] if hit > 0 else float(self._live_parameter(block, "velocity_base", .72))
                representation.velocity[i] = _clamp(velocity * decision.accent, 0.0, 1.0)
                if hit <= 0:
                    representation.duration[i] = float(self._live_parameter(block, "gate", block.parameters.get("live_gate", .78)))
                representation.accent[i] = float(representation.velocity[i] >= .85)

    def _drum_window_processing_needed(self, block):
        parent = self.drum_parent_for(block)
        return parent is not None and any(owner.processes or any(m.target != "pitch" for m in owner.mutators)
                                          for owner in (block, parent))

    def _kit_live_source(self, block, slot, plan, variant):
        """Process a complete musical window, then read the scheduled slot.

        LIVE used to run Rotate/Delay/Counter on a one-element list, losing
        both phase and history. Source edits invalidate this bounded cache.
        """
        parent = self.drum_parent_for(block)
        active = self.performance.active.get(block.id)
        source = replace(block, parameters={**block.parameters, **(active.current_values if active is not None else {})})
        # LIVE gate may differ from the sequencer gate. Preserve the live
        # adapter override while processing durations over the whole window.
        source.parameters["gate"] = self._live_parameter(block, "gate", block.parameters.get("live_gate", .65))
        size = plan.length if plan is not None else (variant.motif.steps if variant is not None else self._kit_cycle_length(block))
        start = plan.start_slot if plan is not None else (slot // size) * size
        key = (start, size, plan.token if plan else None, variant.token if variant else None,
               source.algorithm, digest(source.parameters), digest([asdict(m) for m in source.mutators]),
               digest([asdict(p) for p in source.processes]),
               digest((parent.parameters, [asdict(m) for m in parent.mutators], [asdict(p) for p in parent.processes])),
               self._seed_for(block))
        cached = self._kit_source_cache.get(block.id)
        if cached is None or cached[0] != key:
            rng = random.Random(self._seed_for(block) + (start // size) * 7919)
            cycle = self._kit_cycle_length(block)
            seq = list(self._seq_material(source, cycle, rng))[:cycle]
            seq = (seq * (cycle // len(seq) + 1))[:cycle] if seq else [None] * cycle
            rotation = int(source.parameters.get("structure_rotation", 0)) % cycle
            seq = seq[rotation:] + seq[:rotation]
            seq = [seq[(start + i) % cycle] for i in range(size)]
            rep = self._make_representation(source, seq, rng)
            if plan is None:
                self._apply_kit_fills(source, rep)
            self._apply_active_motif(source, rep, variant=variant, start_slot=start)
            self._apply_kit_plan(source, rep, plan, start)
            self._apply_fill_density(source, rep, rng)
            self._process_kit_material(source, rep, rng, plan, start)
            self._kit_source_cache[block.id] = (key, rep)
        else:
            rep = cached[1]
        i = slot % size
        return MusicalRepresentation(**{part: [getattr(rep, part)[i]] for part in PARTS})

    def _process_kit_material(self, block, representation, rng, plan=None, start_slot=0):
        parent = self.drum_parent_for(block)
        if parent is None:
            self._apply_representation_mutators(block, representation, rng)
            self._apply_processes(block, representation, rng)
            return
        protect = bool(parent.parameters.get("kit_protect_anchors", True))
        anchors = {i for i, hit in enumerate(representation.rhythm)
                   if protect and plan is not None and hit > 0 and plan.at(block.id, start_slot + i).anchor}
        old_accent = list(representation.accent)
        owners = (block, parent)
        for owner in owners:
            self._apply_drum_mutators(owner, representation, rng)
            for process in owner.processes:
                previous = list(representation.rhythm)
                self._apply_processes(replace(owner, processes=[process]), representation, rng)
                if process.target == "rhythm" and process.type != "Parameter Modulation":
                    self._seed_new_drum_hits(owner, representation, previous)
        for i in anchors:
            # Rhythm-only stages retain dynamics, so no velocity/duration
            # restoration is necessary. In particular, a later rhythm gate
            # must not undo an explicit velocity, duration or density zero.
            representation.rhythm[i] = 1.
        if parent is not None:
            targets = {p.target for owner in owners for p in owner.processes if p.type != "Parameter Modulation"}
            for i, hit in enumerate(representation.rhythm):
                if "accent" in targets:
                    representation.velocity[i] = _clamp(representation.velocity[i] + .18 *
                        (_clamp(representation.accent[i], 0., 1.) - old_accent[i]), 0., 1.)
                gated = "density" in targets and kit_random(self._seed_for(block), start_slot + i, 94) >= _clamp(representation.density[i], 0., 1.)
                if hit <= 0 or gated or representation.velocity[i] <= 0 or representation.duration[i] <= 0:
                    for part in ("rhythm", "velocity", "duration", "density", "accent"):
                        getattr(representation, part)[i] = 0.
                else:
                    representation.rhythm[i] = 1.
                    representation.velocity[i] = _clamp(representation.velocity[i], 0., 1.)

    @staticmethod
    def _seed_new_drum_hits(owner, representation, previous):
        """Give new rhythm hits a voice without undoing explicit dynamics gates."""
        for i, hit in enumerate(representation.rhythm):
            if hit > 0 and previous[i] <= 0:
                representation.velocity[i] = _clamp(float(owner.parameters.get("velocity_base", .72)), .05, 1.)
                representation.duration[i] = _clamp(float(owner.parameters.get("gate", .78)), .03, 1.5)
                representation.density[i] = 1.

    def _apply_drum_mutators(self, owner, representation, rng):
        # The generic mutation normalizer rebuilds density/accent/duration,
        # even for an empty chain. On a kit bus that erased the voice's prior
        # processes and revived explicit velocity/duration zeroes.
        for target, part in (("rhythm", "rhythm"), ("pitch", "pitch"),
                             ("velocity", "velocity"), ("timing", "duration")):
            intensity = _clamp(float(owner.parameters.get(f"mutation_{target}", 1.)), 0., 1.)
            for mutator in owner.mutators:
                if mutator.target != target or intensity <= 0:
                    continue
                previous = list(representation.rhythm)
                scaled = Mutator(mutator.name, float(mutator.amount) * intensity, target)
                values = mutate_sequence(list(getattr(representation, part)), scaled, rng)
                if target == "rhythm":
                    values = [float(v > .5) for v in values]
                elif target == "velocity":
                    values = [_clamp(v, 0., 1.) for v in values]
                elif target == "timing":
                    values = [max(0., v) for v in values]
                setattr(representation, part, values)
                if target == "rhythm":
                    self._seed_new_drum_hits(owner, representation, previous)

    def _apply_kit_fills(self, block, representation):
        """Add candidates before voice density, mutations and processes."""
        if self.drum_parent_for(block) is None:
            return
        for i, hit in enumerate(representation.rhythm):
            if hit <= 0 and self._kit_fill_at(block, i):
                representation.rhythm[i] = representation.density[i] = 1.0
                representation.pitch[i] = 0.0
                representation.velocity[i] = _clamp(float(block.parameters.get("velocity_base", .72)), .05, 1.0)
                representation.duration[i] = _clamp(float(block.parameters.get("gate", .78)), .05, 1.5)
                representation.accent[i] = float(representation.velocity[i] >= .85)

    def _apply_kit_output(self, block, representation, start_index=0):
        """Master retention and expressive dynamics, after voice processing."""
        drum = self.drum_parent_for(block)
        if drum is None:
            return
        density = kit_value(drum, "kit_density")
        humanize = kit_value(drum, "kit_humanize")
        seed = self._seed_for(block)
        plan = self.kit_plan(block, start_index * STEP_BEATS)
        voice_silent = self._fill_density_value(block) <= 0
        for i, hit in enumerate(representation.rhythm):
            if hit <= 0:
                continue
            index = start_index + i
            if voice_silent or (plan is not None and not plan.can_emit(block.id, index, bool(drum.parameters.get("kit_protect_anchors", True)))) or density <= 0 or (density < 1 and kit_random(seed, index, 0) >= density):
                for part in ("rhythm", "velocity", "duration", "density", "accent"):
                    getattr(representation, part)[i] = 0.0
            elif humanize:
                factor = 1.0 + (2.0 * kit_random(seed, index, 2) - 1.0) * .15 * humanize
                representation.velocity[i] = _clamp(representation.velocity[i] * factor, 0.0, 1.0)

    def active_motif(self, block):
        """Explicit per-entity binding, or the selected phrase's role motif."""
        if "motif_id" in block.parameters:
            candidates = [self.director.motifs.motifs.get(str(block.parameters["motif_id"]))]
        else:
            state = self.director.phrase
            owner = getattr(block, "parent_id", block.id)
            if not state.running or (state.block_ids and block.id not in state.block_ids and owner not in state.block_ids):
                return None
            candidates = [self.director.motifs.motifs.get(mid) for mid in state.active_motifs]
        return next((m for m in candidates if m and str(m.role).upper() == str(block.block_type).upper()), None)

    def motif_step_beats(self, block, motif=None):
        motif = motif or self.active_motif(block)
        if motif is None:
            return None
        if self.coordinated_drum(block) is not None:
            return STEP_BEATS
        # Motif timing is explicit musical time. Generator timing_rate and
        # random LIVE intervals do not change the motif's rhythmic identity.
        return motif.step_duration(block.parameters.get("motif_step_beats"))

    def _motif_velocity(self, block, motif, index):
        authored = float(motif.velocity[index % len(motif.velocity)]) if motif.velocity else .72
        target = _clamp(float(self._live_parameter(block, "velocity_base", .72)), 0.0, 1.0)
        accent = _clamp(float(self._live_parameter(block, "velocity_accent", 0.0)), 0.0, 1.0)
        # Preserve the authored contour at neutral settings. A gentle offset
        # keeps dynamics responsive to Perform without compressing the motif
        # toward a constant velocity differently in SEQ and LIVE.
        return _clamp(authored + (target - .72) * .55 + accent * .35, 0.0, 1.0)

    def motif_variant(self, block, beat=None):
        source = self.active_motif(block)
        if source is None:
            return None
        position = self.clock.position_beats if beat is None else max(0.0, float(beat))
        return self.motif_development.resolve(
            block.id, source, position, self.motif_step_beats(block, source),
            block.parameters, self._scale(block), self.project.seed, self.clock.running)

    def hold_motif(self, block, enabled=True, token=None):
        source = self.active_motif(block)
        if not enabled:
            block.parameters.pop("motif_hold", None)
            return True
        if source is None:
            return False
        self.motif_variant(block)
        hold = self.motif_development.hold(block.id, source.id, token)
        if hold is None:
            return False
        block.parameters["motif_hold"] = hold
        return True

    def capture_motif(self, block, current_variant=False):
        """Capture a raw generator theme or save the current source variant.

        Capturing precedes mutations, relations and macros, so assigning the
        resulting motif doesn't apply those transformations twice. For LIVE,
        this is a deterministic generator preview, not a MIDI recording.
        """
        if getattr(block, "drum_voices", None) is not None and not getattr(block, "is_drum_voice", False):
            return None
        if current_variant:
            variant = self.motif_variant(block)
            if variant is None:
                return None
            material = variant.motif
            title = f"{block.name} · {variant.label}"
        else:
            length = max(1, min(128, int(self.project.length), int(block.parameters.get("structure_length", self.project.length))))
            rng = random.Random(self._seed_for(block))
            source = replace(block, parameters={**block.parameters, "velocity_base": .72, "velocity_accent": 0.0})
            seq = list(self._seq_material(source, length, rng))[:length]
            seq = (seq * (length // len(seq) + 1))[:length] if seq else [None] * length
            rotation = int(block.parameters.get("structure_rotation", 0)) % length
            seq = seq[rotation:] + seq[:rotation]
            rep = self._make_representation(source, seq, rng)
            step = .25 / _clamp(float(block.parameters.get("timing_rate", 1)), .25, 4)
            material = Motif("", "", role=block.block_type, notes=list(rep.pitch),
                             rhythm=list(rep.rhythm), velocity=list(rep.velocity), step_beats=step)
            title = f"{block.name} · theme"
        number = 1
        while f"captured_{number}" in self.director.motifs.motifs:
            number += 1
        motif = replace(material, id=f"captured_{number}", name=f"{title} {number}",
                        notes=list(material.notes), rhythm=list(material.rhythm),
                        velocity=list(material.velocity), variations={})
        self.director.motifs.register(motif)
        # Project data owns new captures immediately, including headless saves.
        self.project.motifs[motif.id] = asdict(motif)
        block.parameters.update(motif_id=motif.id, motif_step_beats=motif.step_duration(), motif_development="off")
        block.parameters.pop("motif_hold", None)
        self.motif_development.forget(block.id)
        self.regenerate(block)
        return motif

    def _apply_active_motif(self, block, representation, beat=None, variant=None, start_slot=None):
        variant = variant or self.motif_variant(block, beat)
        if variant is None:
            return
        motif = variant.motif
        start = motif.index_at(beat, self.motif_step_beats(block, motif)) if beat is not None else 0
        if start_slot is not None:
            start = start_slot % motif.steps
        gate = _clamp(float(self._live_parameter(block, "gate", block.parameters.get("live_gate", .78))), .05, 1.5)
        for i in range(len(representation.rhythm)):
            index = (start + i) % motif.steps
            hit = float(motif.rhythm[index % len(motif.rhythm)]) > 0 if motif.rhythm else True
            representation.rhythm[i] = representation.density[i] = float(hit)
            representation.pitch[i] = float(motif.notes[index % len(motif.notes)]) if motif.notes else 0.0
            velocity = self._motif_velocity(block, motif, index)
            representation.velocity[i] = _clamp(velocity, 0.0, 1.0) if hit else 0.0
            representation.duration[i] = gate if hit else 0.0
            representation.accent[i] = float(hit and velocity >= .85)

    def _apply_global_macros(self, block: Block, representation):
        """Apply the always-visible global character controls.

        The midpoint is deliberately neutral, so existing projects keep their
        generated material until a user moves a header macro. Density affects
        event retention, Energy affects dynamics and Variation adds controlled
        accent movement. Tension remains a Director trajectory control and is
        consumed by phrase snapshots.
        """
        values = getattr(self.director, "global_macro_values", {})
        energy = max(0.0, min(1.0, float(values.get("energy", .5))))
        density = max(0.0, min(1.0, float(values.get("density", .5))))
        variation = max(0.0, min(1.0, float(values.get("variation", .5))))
        keep = max(0.0, min(1.0, .25 + 1.5 * density))
        energy_scale = .70 + .60 * energy
        role = str(block.block_type).upper()
        for i, hit in enumerate(representation.rhythm):
            if hit <= 0:
                continue
            if keep < .999 and self.director.decision_value(block.id, "global_density", slot=i) > keep:
                representation.rhythm[i] = 0.0
                representation.velocity[i] = 0.0
                representation.duration[i] = 0.0
                continue
            representation.velocity[i] = _clamp(representation.velocity[i] * energy_scale, 0.0, 1.0)
            if abs(variation - .5) > 1e-9:
                direction = 1.0 if (i % (2 if role in PERCUSSIVE_TYPES else 3) == 0) else -1.0
                depth = (variation - .5) * (.32 if role in PERCUSSIVE_TYPES else .20)
                representation.velocity[i] = _clamp(representation.velocity[i] * (1.0 + direction * depth), 0.0, 1.0)

    def generate_block(self, block: Block, motif_beat=None):
        if (str(block.block_type).upper() == "DRUM"
                and not getattr(block, "is_drum_voice", False)
                and getattr(block, "drum_voices", None) is not None):
            self._generate_drum_container(block)
            return
        rng = random.Random(self._seed_for(block))
        motif = self.active_motif(block)
        variant = self.motif_variant(block, motif_beat)
        plan = self.kit_plan(block, motif_beat)
        project_length = plan.length if plan is not None else (motif.steps if motif is not None else max(1, int(self.project.length)))
        cycle_length = self._kit_cycle_length(block) if plan is not None else (project_length if motif is not None else max(1, min(project_length, int(block.parameters.get("structure_length", project_length)))))
        sequence = list(self._seq_material(block, cycle_length, rng))[:cycle_length]
        sequence = (sequence * (cycle_length // max(1, len(sequence)) + 1))[:cycle_length] if sequence else [None] * cycle_length
        # STRUCTURE rotation is a post-generator operation: it is independent
        # of algorithm-specific rotations and rotates the complete musical event.
        rotation = int(block.parameters.get("structure_rotation", 0)) % max(1, cycle_length)
        if rotation:
            sequence = sequence[rotation:] + sequence[:rotation]
        # Keep the transport length equal to the project length while allowing
        # each block to have its own shorter musical cycle.
        if plan is not None:
            sequence = [sequence[(plan.start_slot + i) % len(sequence)] for i in range(project_length)]
        else:
            sequence = (sequence * (project_length // max(1, len(sequence)) + 1))[:project_length]
        representation = self._make_representation(block, sequence, rng)
        self._apply_kit_fills(block, representation)
        self._apply_active_motif(block, representation, variant=variant, start_slot=plan.start_slot if plan is not None else None)
        self._apply_kit_plan(block, representation, plan, plan.start_slot if plan is not None else 0)
        self._apply_fill_density(block, representation, rng)
        self._process_kit_material(block, representation, rng, plan, plan.start_slot if plan is not None else 0)
        self._apply_relation_context(block, representation)
        if str(block.block_type).upper() not in ("DRUM", "CHORD"):
            self.update_musical_context()
        self._apply_groove_to_representation(block, representation)  # same stage as LIVE
        self._apply_global_macros(block, representation)
        snap = self.director.snapshot()
        if self.director.phrase.running:
            role = str(block.block_type).upper()
            rstate = self.director.role_state(role, snap)

            # Event density has role semantics. Percussive and melodic voices
            # can shed individual events; harmonic layers preserve chord/pad
            # attacks and express low activity mainly through longer duration,
            # dynamics and probability at the transport/live level.
            if rstate.activity_mode != "harmonic":
                base_density=self._fill_density_value(block)
                keep=self.director.bounded_combine(base_density,rstate.density,.14)
                # Stable within musical windows and deterministic from the
                # project seed. Each step has a stable slot within the window.
                window=max(.25,float(self.director.decision_window_beats))
                steps_per_window=max(1,int(round(len(representation.rhythm)*window/max(1.0,float(self.project.length)))))
                for i, hit in enumerate(representation.rhythm):
                    if hit > 0:
                        beat=float(i)*float(self.project.length)/max(1,len(representation.rhythm))
                        slot=i % steps_per_window
                        if self.director.decision_value(block.id,"density",beat,slot) > keep:
                            representation.rhythm[i]=0.0; representation.velocity[i]=0.0; representation.duration[i]=0.0

            energy_gain = 0.82 + 0.36 * rstate.energy
            for i, hit in enumerate(representation.rhythm):
                if hit > 0:
                    representation.velocity[i] = _clamp(representation.velocity[i] * energy_gain, 0.0, 1.0)
                    representation.duration[i] = max(0.03, representation.duration[i] * rstate.duration_factor)
                    if role in ("DRUM", "PERCUSSION"):
                        representation.velocity[i] = _clamp(
                            representation.velocity[i] * (1.0 + (rstate.variation-.5)*.18*(1 if i%2==0 else -1)), 0.0, 1.0)
                    elif role in ("MELODY", "BASS"):
                        representation.velocity[i] = _clamp(
                            representation.velocity[i] * (1.0 + (rstate.variation-.5)*.11*(1 if i%3==0 else -1)), 0.0, 1.0)
                    elif role in ("PAD", "CHORD"):
                        # Harmonic variation is intentionally gentle: preserve
                        # the voicing while allowing phrase-shaped expression.
                        representation.velocity[i] = _clamp(
                            representation.velocity[i] * (1.0 + (rstate.variation-.5)*.05), 0.0, 1.0)

            if role not in PERCUSSIVE_TYPES:
                for i, hit in enumerate(representation.rhythm):
                    if hit > 0:
                        representation.pitch[i] = float(representation.pitch[i]) + rstate.register_shift
        # Role placement is deliberately last so Director/voice-leading cannot
        # escape BASS/PAD/CHORD registers.
        if self.director.phrase.running and self.director.voice_leading and block.block_type not in PERCUSSIVE_TYPES:
            active=[i for i,r in enumerate(representation.rhythm) if r>0]
            if active:
                # A SEQ pattern is smoothed as a whole loop from a clean voice;
                # history from the previous regeneration made it non-deterministic.
                voice=f"seq:{block.id}"
                self.voice_leading.previous.pop(voice, None)
                vals=self.voice_leading.process_sequence([representation.pitch[i] for i in active], voice)
                for i,v in zip(active,vals): representation.pitch[i]=round(v)
        self._apply_role_profile(block, representation, rng)
        # Director/voice-leading may move notes for musical smoothness, but
        # the final output must still obey the selected key.
        if block.block_type not in PERCUSSIVE_TYPES:
            representation.pitch = [self._quantize_pitch(block, v) for v in representation.pitch]
        self._apply_kit_output(block, representation, plan.start_slot if plan is not None else 0)
        block.outputs = representation.as_outputs()
        self._base_outputs[block.id] = representation.as_outputs()
        self._seq_motifs[block.id] = motif
        self._seq_motif_tokens[block.id] = variant.token if variant is not None else None
        self._seq_kit_tokens[block.id] = plan.token if plan is not None else None

    def update_musical_context(self):
        """Refresh shared context from the current authorities."""
        state = self.director.snapshot()
        self.musical_context.update_from_director(state)
        drums = [b for b in self.project.blocks if str(b.block_type).upper() == "DRUM"]
        if drums:
            size = max((len(b.outputs.get("rhythm", [])) for b in drums), default=0)
            rhythm = [0.0] * size
            accents = [0.0] * size
            for drum in drums:
                for i in range(size):
                    rhythm[i] = max(rhythm[i], self._stream_value(drum.outputs.get("rhythm", []), i))
                    accents[i] = max(accents[i], self._stream_value(drum.outputs.get("accent", []), i))
            metrics = self.musical_context.update_from_drum(rhythm, accents)
            self.musical_context.values["groove_sources"] = [b.id for b in drums]
        else:
            metrics = {
                "groove": 0.0, "density": 0.0,
                "syncopation": 0.0, "accent": 0.0,
            }
            self.musical_context.values["groove_metrics"] = metrics
            self.musical_context.groove = 0.0
            self.musical_context.density = 0.0
            self.musical_context.values["groove_sources"] = []

        # Chords are the harmonic authority.  Keep this pass independent from
        # the drum branch so both contexts are refreshed together.
        chords = [b for b in self.project.blocks if str(b.block_type).upper() == "CHORD"]
        if chords:
            size = max((len(b.outputs.get("rhythm", [])) for b in chords), default=0)
            rhythm = [0.0] * size
            pitches = [0.0] * size
            for chord in chords:
                for i in range(size):
                    value = self._stream_value(chord.outputs.get("rhythm", []), i)
                    if value > rhythm[i]:
                        rhythm[i] = value
                        pitches[i] = self._stream_value(chord.outputs.get("pitch", []), i)
            self.musical_context.update_from_chord(rhythm, pitches)
            self.musical_context.values["harmony_sources"] = [b.id for b in chords]
        else:
            self.musical_context.harmony = 0.5
            self.musical_context.values["harmony_metrics"] = {
                "harmony": 0.5, "density": 0.0, "changes": 0.0,
            }
            self.musical_context.values["harmony_sources"] = []
        return metrics

    def generate(self):
        # Macro routes are part of the persisted project state.  Apply them
        # before rebuilding material so opening a project produces the same
        # result as touching one of its macro controls once.
        self.apply_macros()
        # Generate rhythm/harmony authorities first so dependent generators
        # receive a real MusicalContext during their own generation pass.
        authorities = [b for b in self.project.blocks
                       if str(b.block_type).upper() in ("DRUM", "CHORD")
                       and (b.mode == "SEQ" or b.drum_voices is not None)]
        dependents = [b for b in self.project.blocks
                      if b.mode == "SEQ" and b not in authorities]
        for block in authorities:
            self.generate_block(block)
        self.update_musical_context()
        for block in dependents:
            self.generate_block(block)
        self.apply_relations()

    def regenerate(self, block: Block, motif_beat=None):
        """Regenerate one block after an edit and re-apply all relations."""
        parent = self.drum_parent_for(block)
        targeted_voice = parent is not None and motif_beat is not None
        if targeted_voice:
            # An early humanized attack advances only its own motif. Passing
            # that future beat to siblings could replace their last old-cycle
            # notes with the next variant before those notes were played.
            self.generate_block(block, motif_beat=motif_beat)
            self._aggregate_drum_outputs(parent)
        if parent is not None:
            block = parent
        is_kit = str(block.block_type).upper() == "DRUM" and block.drum_voices is not None
        if not targeted_voice and (block.mode == "SEQ" or is_kit):
            self.generate_block(block, motif_beat=motif_beat)
        self.update_musical_context()
        # A changed Drum/Chord is an authority for every dependent SEQ block.
        # Rebuild those dependents so their pre-relation groove/harmony stage
        # sees the new authority, matching a full Generate operation.
        if (block.mode == "SEQ" or is_kit) and str(block.block_type).upper() in ("DRUM", "CHORD"):
            dependents = [b for b in self.project.blocks
                          if b.mode == "SEQ" and str(b.block_type).upper() not in ("DRUM", "CHORD")]
            for dependent in dependents:
                self.generate_block(dependent)
        self.apply_relations()

    def _make_representation(self, block: Block, sequence: list, rng: random.Random) -> MusicalRepresentation:
        """Convert raw generator material into independent musical dimensions."""
        p = block.parameters
        zero_is_rest = self._zero_is_rest(block)
        # For rhythm generators the value is a hit/accent strength, not a pitch
        # offset (previously a 1.0 hit played the base note +1 semitone).
        # Pattern values remain pitch offsets, as in LIVE mode.
        value_is_pitch = not zero_is_rest or block.algorithm == "Pattern"
        rhythm, pitch, values = [], [], []
        for v in sequence:
            v = None if v is None else float(v)
            values.append(0.0 if v is None else v)
            pitch.append(v if (v is not None and value_is_pitch) else 0.0)
            rhythm.append(0.0 if v is None or (zero_is_rest and abs(v) <= 1e-9) else 1.0)
        base = float(p.get("velocity_base", 0.72))
        span = float(p.get("velocity_range", 0.25))
        randomness = float(p.get("velocity_random", 0.0))
        accent_amount = float(p.get("velocity_accent", 0.18))
        floor = 0.05
        if block.algorithm == "Probability":
            floor = max(floor, _clamp(float(p.get("probability_velocity_floor", 0.4)), 0.0, 1.0))
        velocity = []
        for r, v in zip(rhythm, values):
            if r <= 0:
                velocity.append(0.0)
                continue
            value = base + min(1.0, abs(v) / 12.0) * span
            if abs(v) > 0.75:
                value += accent_amount
            if randomness:
                value += rng.uniform(-randomness, randomness)
            velocity.append(_clamp(value, floor, 1.0))
        gate = _clamp(float(p.get("gate", 0.78)), 0.05, 1.5)
        duration = [gate if r else 0.0 for r in rhythm]
        accent = [1.0 if v >= 0.85 else 0.0 for v in velocity]
        return MusicalRepresentation(rhythm, pitch, velocity, duration, rhythm[:], accent)

    def _apply_fill_density(self, block: Block, representation: MusicalRepresentation, rng: random.Random):
        """Apply the universal generator Fill/Density gate.

        Independent of algorithm-specific density parameters (Fibonacci
        density, CA density...): those shape the algorithm, Fill controls how
        many of the resulting candidate events are allowed through.
        """
        fill = self._fill_density_value(block)
        if fill >= 1.0 or not representation.rhythm:
            return
        for i, r in enumerate(representation.rhythm):
            if fill > 0.0 and r > 0.0 and rng.random() < fill:
                continue
            for part in ("rhythm", "velocity", "duration", "density", "accent"):
                getattr(representation, part)[i] = 0.0

    def _apply_representation_mutators(self, block: Block, representation: MusicalRepresentation, rng: random.Random):
        """Apply mutators independently to rhythm, pitch and velocity."""
        p = block.parameters

        def run(target: str, values: list[float]) -> list[float]:
            intensity = _clamp(float(p.get(f"mutation_{target}", 1.0)), 0.0, 1.0)
            for mutator in block.mutators:
                if getattr(mutator, "target", "pitch") == target:
                    if intensity <= 0.0:
                        continue
                    if intensity >= 0.999:
                        values = mutate_sequence(values, mutator, rng)
                    else:
                        scaled = Mutator(mutator.name, float(mutator.amount) * intensity, target)
                        values = mutate_sequence(values, scaled, rng)
            return list(values)

        representation.rhythm = [1.0 if v > 0.5 else 0.0 for v in run("rhythm", representation.rhythm)]
        # A rhythm mutator (Rotate, Shuffle, Invert...) can switch on a step that
        # was a rest and therefore has no velocity/duration yet. Give such steps
        # the block's base velocity instead of sending velocity-1 ghost notes.
        default_velocity = _clamp(float(p.get("velocity_base", 0.72)), 0.05, 1.0)
        gate = _clamp(float(p.get("gate", 0.78)), 0.05, 1.5)
        velocity = list(representation.velocity)
        for i, r in enumerate(representation.rhythm):
            if r > 0 and (i >= len(velocity) or velocity[i] <= 0):
                if i >= len(velocity):
                    velocity.extend([0.0] * (i + 1 - len(velocity)))
                velocity[i] = default_velocity
        representation.pitch = run("pitch", representation.pitch)
        representation.velocity = [_clamp(float(v), 0.0, 1.0) for v in run("velocity", velocity)]
        representation.duration = [max(0.0, float(v)) for v in run("timing", representation.duration)]
        representation.density = representation.rhythm[:]
        representation.accent = [1.0 if v >= 0.85 else 0.0 for v in representation.velocity]
        old_duration = representation.duration
        representation.duration = [
            ((old_duration[i] if i < len(old_duration) and old_duration[i] > 0 else gate) if r > 0 else 0.0)
            for i, r in enumerate(representation.rhythm)
        ]
        # Cross-block virtual pitch controls. They are real block parameters,
        # applied here so they affect every generator uniformly.
        transpose = float(p.get("transpose", 0.0))
        octave = float(p.get("octave", 0.0)) * 12.0
        if transpose or octave:
            representation.pitch = [v + transpose + octave for v in representation.pitch]

    # ---- parameters, modulation, macros, randomize ------------------------
    @staticmethod
    def parameter_catalog(block: Block) -> dict[str, tuple[float, float, float]]:
        catalog = dict(COMMON_MOD_PARAMETERS)
        if block.block_type in ("BASS", "MELODY"):
            catalog["harmonic_strength"] = (.75, 0., 1.)
        catalog.update(GENERATOR_MOD_PARAMETERS.get(block.algorithm, {}))
        if getattr(block, "drum_voices", None) is not None:
            catalog.update({key: (value, 0., 1.) for key, value in CREATIVE_DEFAULTS.items()})
            catalog.update({key: (default, 0., 1.) for key, default in (("kit_density", 1.), ("kit_swing", 0.), ("kit_humanize", 0.), ("kit_fill", 0.))})
        # Any numeric parameter already stored in a project is a real
        # destination too; use a conservative range around its value.
        for key, value in block.parameters.items():
            if key in NON_NUMERIC_PARAMETERS or key in catalog or isinstance(value, bool):
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            span = max(1.0, abs(v))
            catalog[key] = (v, -span * 4.0, span * 4.0)
        return catalog

    def set_parameter(self, block: Block, key: str, value: float, source=None) -> bool:
        """Write a catalog parameter, clamped to its range and keeping its type."""
        catalog = self.parameter_catalog(block)
        if key not in catalog:
            return False
        default, lo, hi = catalog[key]
        value = _clamp(float(value), lo, hi)
        current = block.parameters.get(key, default)
        if isinstance(current, bool):
            value = bool(value >= 0.5)
        elif key in FLOAT_MOD_KEYS:
            value = float(value)
        elif isinstance(current, int):
            value = int(round(value))
        else:
            value = float(value)
        if source is None:
            self.parameter_influence.manual(block, key, value)
        else:
            self.parameter_influence.write(block, key, value, source)
        return True

    def apply_pending_parameter_modulations(self) -> list[Block]:
        """Apply values produced on a previous tick, never the current one.

        A route with ``delay`` N is applied exactly N ticks after it was queued.
        """
        pending = self.pending_parameter_modulations
        self.pending_parameter_modulations = {}
        # Age delayed routes *after* taking this tick's pending values, so a
        # delayed value becomes pending for the following tick.
        still_delayed = []
        for remaining, key, value in self.delayed_parameter_modulations:
            remaining -= 1
            if remaining <= 0:
                self.pending_parameter_modulations[key] = value
            else:
                still_delayed.append((remaining, key, value))
        self.delayed_parameter_modulations = still_delayed

        changed = set()
        for (block_id, key), value in pending.items():
            block = self.find_block(block_id)
            if block is not None and self.set_parameter(block, key, value, source="Parameter Modulation"):
                changed.add(block.id)
        changed_blocks = [b for b in self.project.blocks if b.id in changed and
                          (b.mode == "SEQ" or getattr(b, "drum_voices", None) is not None)]
        for block in changed_blocks:
            self.generate_block(block)
        if changed_blocks:
            self.apply_relations()
        return changed_blocks

    def queue_parameter_modulation(self, source: Block, source_value: float, process: Process):
        p = process.parameters
        try:
            destination_id = int(p.get("destination_block", -1))
        except (TypeError, ValueError):
            return
        destination = self.find_block(destination_id)
        if destination is None:
            return
        key = str(p.get("destination_parameter", "fill_density"))
        catalog = self.parameter_catalog(destination)
        if key not in catalog:
            return
        default, cat_lo, cat_hi = catalog[key]
        src_lo = float(p.get("source_min", -1.0))
        src_hi = float(p.get("source_max", 1.0))
        if abs(src_hi - src_lo) < 1e-12:
            normalized = 0.5
        else:
            normalized = (float(source_value) - src_lo) / (src_hi - src_lo)
        normalized = _clamp(normalized, 0.0, 1.0) ** _clamp(float(p.get("curve", 1.0)), 0.1, 8.0)
        minimum = float(p.get("min", cat_lo))
        maximum = float(p.get("max", cat_hi))
        target = minimum + (maximum - minimum) * normalized
        amount = _clamp(float(p.get("depth", process.amount)), 0.0, 1.0)
        current = float(destination.parameters.get(key, default))
        target = current + (target - current) * amount
        smoothing = _clamp(float(p.get("smoothing", 0.0)), 0.0, 1.0)
        state_key = (destination.id, key)
        if smoothing:
            previous = self.parameter_modulation_state.get(state_key, current)
            target = previous + (target - previous) * (1.0 - smoothing)
        self.parameter_modulation_state[state_key] = target
        # Crucial: this is only queued. It is applied at a later transport tick.
        delay = max(1, int(p.get("delay", 1)))
        if delay <= 1:
            self.pending_parameter_modulations[state_key] = target
        else:
            self.delayed_parameter_modulations.append((delay - 1, state_key, target))

    def collect_parameter_modulations(self, source: Block, index: int = 0):
        for process in source.processes:
            if process.type != "Parameter Modulation":
                continue
            part = process.target if process.target in PARTS else "pitch"
            values = source.outputs.get(part, [])
            if values:
                self.queue_parameter_modulation(source, float(values[index % len(values)]), process)

    def apply_macros(self):
        """Apply project macro routes to real block parameters.

        The mapping is idempotent: each route remembers the parameter value it
        started from (``base``) and Amount blends between that base and the
        macro target, so applying the same macro value twice gives the same
        result.
        """
        touched = set()
        for macro in self.project.macros or []:
            value = _clamp(float(macro.get("value", 0.5)), 0.0, 1.0)
            for route in macro.get("routes", []) or []:
                try:
                    block = self.find_block(int(route.get("block_id", -1)))
                except (TypeError, ValueError):
                    block = None
                if block is None:
                    continue
                key = str(route.get("parameter", "fill_density"))
                catalog = self.parameter_catalog(block)
                if key not in catalog:
                    continue
                default, lo, hi = catalog[key]
                rlo = float(route.get("min", lo))
                rhi = float(route.get("max", hi))
                curve = float(route.get("curve", 1.0))
                x = value if curve <= 0 else value ** curve
                target = rlo + (rhi - rlo) * x
                amount = _clamp(float(route.get("amount", 1.0)), 0.0, 1.0)
                if "base" not in route:
                    route["base"] = float(block.parameters.get(key, default))
                base = float(route["base"])
                if self.set_parameter(block, key, base + (target - base) * amount,
                                      source="Macro: " + str(macro.get("name", "Macro"))):
                    touched.add(block.id)
        for block in self.project.blocks:
            if block.id in touched and (block.mode == "SEQ" or getattr(block, "drum_voices", None) is not None):
                self.generate_block(block)
        self.apply_relations()

    def randomize_block(self, block: Block, categories=None, amount=0.35, rng=None):
        """Bounded randomization of real block parameters.

        Values move towards a random target inside each parameter's catalog
        range by ``amount``. Unless an ``rng`` is supplied, the result differs
        on every call (time-seeded) - that is the point of "randomize".
        """
        categories = set(categories or {"Generator", "Density", "Pitch", "Mutators", "Processes"})
        rng = rng or random.Random(time.time_ns() ^ (block.id * 7919))
        catalog = self.parameter_catalog(block)
        keys = []
        if "Generator" in categories:
            keys.extend(k for k in catalog if k not in COMMON_MOD_PARAMETERS)
        if "Density" in categories:
            keys.extend(["fill_density", "event_probability"])
        if "Pitch" in categories:
            keys.extend(["transpose", "octave"])
        amount = _clamp(float(amount), 0.0, 1.0)
        for key in dict.fromkeys(keys):
            if key not in catalog:
                continue
            default, lo, hi = catalog[key]
            current = _clamp(float(block.parameters.get(key, default)), lo, hi)
            self.set_parameter(block, key, current + (rng.uniform(lo, hi) - current) * amount)
        if "Mutators" in categories:
            for m in block.mutators:
                m.amount = _clamp(m.amount + rng.uniform(-amount, amount), 0.0, 1.0)
        if "Processes" in categories:
            for proc in block.processes:
                for key, val in list(proc.parameters.items()):
                    if isinstance(val, bool) or not isinstance(val, (int, float)) or key == "destination_block":
                        continue
                    span = max(1.0, abs(float(val)))
                    new = float(val) + rng.uniform(-span, span) * amount
                    proc.parameters[key] = int(round(new)) if isinstance(val, int) else new
        self.regenerate(block)

    def randomize_parameter(self, block: Block, key: str, amount: float = 0.35, rng=None) -> bool:
        """Randomize one real generator parameter within its catalog bounds."""
        rng = rng or random.Random(time.time_ns() ^ (block.id * 104729))
        if key == "variation_seed":
            block.parameters[key] = rng.randint(-9999, 9999)
            self.regenerate(block)
            return True
        catalog = self.parameter_catalog(block)
        if key not in catalog:
            return False
        default, lo, hi = catalog[key]
        amount = _clamp(float(amount), 0.0, 1.0)
        current = _clamp(float(block.parameters.get(key, default)), lo, hi)
        self.set_parameter(block, key, current + (rng.uniform(float(lo), float(hi)) - current) * amount)
        self.regenerate(block)
        return True

    # ---- LIVE generation --------------------------------------------------
    def _live_parameter(self, block: Block, key: str, default=None):
        """Read a block parameter plus any active LIVE technique override."""
        performance = getattr(self, "performance", None)
        if performance is not None:
            override = performance.live_value(block.id, key, None)
            if override is not None:
                return override
        return block.parameters.get(key, default)

    def _live_interval(self, block: Block, rng: random.Random) -> float:
        if self.coordinated_drum(block) is not None:
            return STEP_BEATS * 60.0 / max(1, self.project.tempo)
        step = self.motif_step_beats(block)
        if step is not None:
            return step * 60.0 / max(1, self.project.tempo)
        # Continuous timing: a real-valued interval in seconds. No fixed
        # 16-step grid is used in LIVE mode.
        base = 60.0 / max(1, self.project.tempo)
        minimum = max(0.03, float(self._live_parameter(block, "live_min_beats", .18)))
        maximum = max(minimum, float(self._live_parameter(block, "live_max_beats", .85)))
        rate = _clamp(float(self._live_parameter(block, "timing_rate", 1.0)), .25, 4.0)
        swing = _clamp(float(self._live_parameter(block, "timing_swing", 0.0)), 0.0, 0.5)
        humanize = _clamp(float(self._live_parameter(block, "timing_humanize", 0.0)), 0.0, 0.25)
        offset = _clamp(float(self._live_parameter(block, "timing_offset", 0.0)), -0.5, 0.5)
        # LIVE has no fixed 16th grid, so swing alternates successive accepted
        # event intervals. This gives Rubato/Swing a meaningful continuous
        # interpretation while retaining deterministic event order.
        event_index = int(self.live_state.get(block.id, {}).get("events", 0))
        swing_factor = 1.0 + (swing * 0.5 if event_index % 2 else 0.0)
        humanize_factor = 1.0 + rng.uniform(-humanize, humanize) if humanize else 1.0
        rate_factor = 1.0 / rate
        offset_factor = max(0.05, 1.0 + offset)
        drum = self.drum_parent_for(block)
        kit_factor = live_timing_factor(drum, self._seed_for(block), max(0, event_index - 1)) if drum is not None else 1.0
        if block.algorithm == "Euclidean":
            density = _clamp(float(self._live_parameter(block, "pulses", 5)) / max(1, self.project.length), 0.05, 1.0)
            interval = max(0.08, max(minimum, 1.0 - density * 0.7))
            return base * interval * rate_factor * swing_factor * humanize_factor * offset_factor * kit_factor
        if block.algorithm == "Probability":
            probability = _clamp(float(self._live_parameter(block, "probability", 0.5)), 0.01, 1.0)
            # Lower probability means more time between accepted events.
            interval = _clamp(rng.expovariate(probability), minimum, maximum)
            return base * interval * rate_factor * swing_factor * humanize_factor * offset_factor * kit_factor
        interval = rng.uniform(minimum, maximum)
        return base * interval * rate_factor * swing_factor * humanize_factor * offset_factor * kit_factor

    def _next_phase(self, state: dict, size: int) -> int:
        """Return the current step of a cyclic LIVE sequence and advance it."""
        index = int(state.get("phase_index", 0)) % max(1, size)
        state["phase_index"] = (index + 1) % max(1, size)
        return index

    def _live_rest(self, block: Block):
        """Publish a LIVE rest so downstream relations see the current step.

        A LIVE generator can return early for a pattern rest, probability gate
        or Director density decision.  Leaving the previous event in
        ``block.outputs`` made a following LIVE Bass/Melody read stale source
        material and sound through a rest.  Keep a one-step zero snapshot and
        run the same relation pass as a successful event.
        """
        block.outputs = {
            "rhythm": [0.0], "pitch": [0.0], "velocity": [0.0],
            "duration": [0.0], "density": [0.0], "accent": [0.0],
        }
        self._base_outputs[block.id] = {part: list(values) for part, values in block.outputs.items()}
        if self._relation_participant(block):
            # A rest must remain a rest for this destination.  Relations from
            # other blocks may still read the zero snapshot, but built-in or
            # user-authored relations must not turn the skipped event back
            # into a hit before live_event() returns.
            self.apply_relations(skip_destination=block.id)
        return None

    def live_event(self, block: Block, beat: float | None = None) -> Optional[dict[str, float]]:
        rng = self._rng_for(block)
        state = self.live_state.setdefault(block.id, {"pitch": 0.0, "last": 0.0})
        state["events"] = int(state.get("events", 0)) + 1
        kit_index = state["events"] - 1
        kit_fill = self._kit_fill_at(block, kit_index)
        p = block.parameters
        alg = block.algorithm
        length = max(1, int(self.project.length))
        root, scale = self._root(block), self._scale(block)
        motif_beat = self.clock.position_beats if beat is None else max(0.0, float(beat))
        variant = self.motif_variant(block, motif_beat)
        motif = variant.motif if variant is not None else None
        plan = self.kit_plan(block, motif_beat)
        kit_source = None

        if plan is not None or self._drum_window_processing_needed(block):
            if plan is not None:
                kit_index = max(0, int(math.floor(motif_beat / STEP_BEATS + 1e-8)))
                self._kit_live_slots[block.id] = kit_index
                self.source_positions[self.drum_parent_for(block).id] = kit_index % plan.length
            elif motif is not None:
                kit_index = max(0, int(math.floor(motif_beat / self.motif_step_beats(block, motif) + 1e-8)))
            kit_source = self._kit_live_source(block, kit_index, plan, variant)
            if not kit_source.rhythm[0]:
                return self._live_rest(block)
            pitch, velocity = kit_source.pitch[0], kit_source.velocity[0]
        elif motif is not None:
            # Motif onsets are a source, not a mask gated by an unrelated
            # generator's early returns. Its own rests still publish zeros.
            index = motif.index_at(motif_beat, self.motif_step_beats(block, motif))
            if motif.rhythm and float(motif.rhythm[index % len(motif.rhythm)]) <= 0:
                return self._live_rest(block)
            pitch = float(motif.notes[index % len(motif.notes)]) if motif.notes else 0.0
            velocity = self._motif_velocity(block, motif, index)
        elif alg in CYCLIC_LIVE_ALGORITHMS:
            # Deterministic material is stepped through in order (step 0 first).
            seq = self._seq_material(block, length, rng)
            if not seq:
                return self._live_rest(block)
            value = seq[self._next_phase(state, len(seq))]
            if self._zero_is_rest(block):
                if not value and not kit_fill:
                    return self._live_rest(block)
                pitch = 0.0
            else:
                pitch = float(value or 0.0)
            velocity = .8 if alg in RHYTHM_ALGORITHMS or alg in ("De Bruijn", "Cellular Automaton") else rng.uniform(.5, 1.0)
        elif alg == "Scale Walker":
            count = len(scale_intervals(scale))
            center, lo, hi = scale_walker_bounds(count, int(p.get("scale_octaves", 2)))
            if "scale_index" not in state:
                state["scale_index"] = center + rng.randrange(count)
            idx = max(lo, min(hi, int(state["scale_index"])))
            pitch = degree_to_note(idx - center, root, scale) - root
            state["scale_index"] = scale_walker_step(idx, rng, int(p.get("scale_step", 1)), float(p.get("scale_direction", .5)),
                                                     lo, hi, float(p.get("scale_leap", .08)))
            velocity = rng.uniform(.5, 1.0)
        elif alg == "Interval Walker":
            value = int(state.get("walk_value", 0))
            value = interval_walker_step(value, rng, max(1, int(p.get("interval_step", 3))),
                                         _clamp(float(p.get("interval_return", .2)), 0.0, 1.0),
                                         max(1, int(p.get("interval_range", 24))),
                                         _clamp(float(p.get("interval_leap", .08)), 0.0, 1.0))
            state["walk_value"] = value
            pitch = quantize_interval_to_scale(value, scale) if p.get("interval_quantize", 1) else float(value)
            state["pitch"] = pitch
            velocity = rng.uniform(.5, 1.0)
        elif alg == "Euclidean":
            steps = max(1, min(length, int(self._live_parameter(block, "euclidean_steps", length))))
            pulses = max(1, min(steps, int(self._live_parameter(block, "pulses", 5))))
            # A rotating continuous phase, rather than a fixed step counter.
            phase = (state.get("phase", 0.0) + pulses / float(steps)) % 1.0
            state["phase"] = phase
            rotation = int(self._live_parameter(block, "euclidean_rotation", 0)) % max(1, steps)
            rotated_phase = (phase + rotation / float(max(1, steps))) % 1.0
            if rotated_phase > pulses / float(steps) and not kit_fill:
                return self._live_rest(block)
            pitch = 0.0
            velocity = 0.8
        elif alg == "Markov":
            count = len(scale_intervals(scale))
            jump = max(1, int(p.get("markov_jump", 3)))
            if "markov_degree" not in state:
                state["markov_degree"] = rng.randrange(count)
            current_degree = int(state["markov_degree"])
            candidates = [d for d in range(count) if abs(d - current_degree) <= jump]
            if rng.random() < float(p.get("markov_leap", .12)):
                candidates = list(range(count))
            if rng.random() < float(p.get("markov_rest", 0.0)) and not kit_fill:
                return self._live_rest(block)
            if rng.random() < _clamp(float(p.get("markov_stay", 0.0)), 0.0, 1.0):
                next_degree = current_degree
            else:
                next_degree = rng.choice(candidates or list(range(count)))
            state["markov_degree"] = next_degree
            octaves = max(0, int(p.get("markov_octaves", 0)))
            octave = rng.randint(-octaves, octaves)
            # markov_transpose is in scale degrees, exactly as in SEQ mode.
            degree = next_degree + int(p.get("markov_transpose", 0)) + octave * count
            pitch = degree_to_note(degree, root, scale) - root
            state["pitch"] = pitch
            velocity = rng.uniform(0.55, 1.0)
        elif alg == "Random Walk":
            value = int(state.get("walk_value", int(p.get("walk_start", 0))))
            value = random_walk_step(value, rng, max(1, int(p.get("walk_step", 2))), max(1, int(p.get("walk_range", 12))),
                                     _clamp(float(p.get("walk_return_bias", 0.0)), 0.0, 1.0),
                                     _clamp(float(p.get("walk_drift", 0.0)), -1.0, 1.0))
            state["walk_value"] = value
            pitch = quantize_interval_to_scale(value, scale) if p.get("walk_quantize", 1) else float(value)
            state["pitch"] = pitch
            velocity = rng.uniform(0.45, 0.95)
        elif alg == "Probability":
            if rng.random() > _clamp(float(p.get("probability", 0.5)), 0.0, 1.0) and not kit_fill:
                return self._live_rest(block)
            spread = max(1, int(p.get("probability_pitch_range", 7)))
            pitch = float(int(p.get("probability_center", 0)) + rng.randint(-spread, spread))
            octaves = max(0, int(p.get("probability_octaves", 0)))
            if octaves:
                pitch += rng.randint(-octaves, octaves) * 12
            velocity = rng.uniform(float(p.get("probability_velocity_floor", 0.4)), 1.0)
        else:
            # Pattern: step through the pattern in order; 0 is a rest, as in SEQ.
            values = self._pattern_values(block)
            value = values[self._next_phase(state, len(values))]
            if (not value or rng.random() > float(p.get("pattern_probability", 1.0))) and not kit_fill:
                return self._live_rest(block)
            pitch = float(value)
            velocity = rng.uniform(0.5, 0.9)

        live_gate_override = self._live_parameter(block, "gate", None)
        live_gate = _clamp(float(live_gate_override if live_gate_override is not None else p.get("live_gate", .65)), .03, 1.5)
        velocity_base_override = self._live_parameter(block, "velocity_base", None)
        velocity_accent_override = self._live_parameter(block, "velocity_accent", None)
        if velocity_base_override is not None and motif is None and plan is None:
            velocity_range = _clamp(float(p.get("velocity_range", .25)), 0.0, 1.0)
            # LIVE already has a natural per-event velocity.  Treat a
            # technique's velocity_base as a target around the normal .72
            # center and blend toward it, rather than replacing the natural
            # event outright.  Direct replacement made Crescendo start
            # unnaturally quiet (.58) and then jump toward .92 at the phrase
            # peak.
            target = _clamp(float(velocity_base_override), 0.0, 1.0)
            velocity = _clamp(float(velocity) * .45 + target * .55, 0.0, 1.0)
        if velocity_accent_override is not None and motif is None and plan is None:
            velocity = _clamp(float(velocity) + float(velocity_accent_override) * .35, 0.0, 1.0)
        representation = MusicalRepresentation(
            rhythm=[1.0], pitch=[float(pitch)], velocity=[float(velocity)],
            duration=[live_gate], density=[1.0], accent=[1.0 if velocity >= 0.85 else 0.0],
        )
        if kit_source is not None:
            representation = kit_source
        else:
            self._apply_active_motif(block, representation, beat=motif_beat, variant=variant)
        if kit_source is None:
            self._process_kit_material(block, representation, rng, plan, kit_index)
        self._apply_relation_context(block, representation)
        self.update_musical_context()
        self._apply_groove_to_representation(block, representation)
        # LIVE events must receive the same always-visible character controls
        # as SEQ material.  Previously energy/density/variation only affected
        # generate_block(), so header macros appeared inert during LIVE play.
        self._apply_global_macros(block, representation)
        if self.director.phrase.running:
            snap=self.director.snapshot()
            role=str(block.block_type).upper()
            rstate=self.director.role_state(role,snap)
            # Harmonic roles keep their attacks more reliably; their Director
            # density is expressed primarily as harmonic activity/sustain.
            # Event probability is applied once, by the transport
            # (event_probability() already includes the Director); applying
            # it here too thinned LIVE parts twice.  Only role density here.
            if rstate.activity_mode != "harmonic":
                live_keep=self.director.bounded_combine(1.0,rstate.density,.12)
                if self.director.decision_value(block.id,"live",slot=int(state.get("events",0))) > live_keep:
                    return self._live_rest(block)
            if representation.rhythm[0] > 0:
                representation.velocity[0]=_clamp(representation.velocity[0] * (0.82 + 0.36*rstate.energy),0.0,1.0)
                representation.duration[0]=max(0.03,representation.duration[0]*rstate.duration_factor)
            if role not in PERCUSSIVE_TYPES and representation.rhythm[0] > 0:
                representation.pitch[0] += rstate.register_shift
            if self.director.voice_leading and block.block_type not in PERCUSSIVE_TYPES:
                representation.pitch[0]=round(self.voice_leading.resolve_pitch(str(block.id),representation.pitch[0]))
        self._apply_role_profile(block, representation, rng)
        if block.block_type not in PERCUSSIVE_TYPES and representation.pitch:
            representation.pitch[0] = self._quantize_pitch(block, representation.pitch[0])
        self._apply_kit_output(block, representation, kit_index)
        if not self.pattern_step_allowed(block, kit_index):
            return self._live_rest(block)
        block.outputs = representation.as_outputs()
        self._base_outputs[block.id] = representation.as_outputs()
        # LIVE blocks are not part of the initial generate() pass.  Re-apply
        # relations so the event is a valid source downstream and so relations
        # aimed at this block shape it.  Blocks outside every relation skip
        # the project-wide pass.
        if self._relation_participant(block):
            self.apply_relations()
        self.collect_parameter_modulations(block, 0)
        fill = self._fill_density_value(block)
        if fill <= 0.0 or (kit_source is None and fill < 1.0 and rng.random() >= fill):
            return self._live_rest(block)
        # Emit the *post-relation* event.  It used to be built from the
        # representation before relations, so Follow/Copy/groove/chord anchor
        # aimed at a LIVE block were computed but never heard.
        out = block.outputs
        rhythm0 = self._stream_value(out.get("rhythm", []), 0, representation.rhythm[0] if representation.rhythm else 0.0)
        if rhythm0 <= 0:
            return self._live_rest(block)
        root_pitch = self._stream_value(out.get("pitch", []), 0, representation.pitch[0] if representation.pitch else pitch)
        if block.block_type not in PERCUSSIVE_TYPES:
            root_pitch = self._quantize_pitch(block, root_pitch)
        velocity_out = self._stream_value(out.get("velocity", []), 0, 0.0)
        if velocity_out <= 0:
            velocity_out = representation.velocity[0] if representation.velocity else velocity
        duration_out = self._stream_value(out.get("duration", []), 0, 0.0)
        if duration_out <= 0:
            duration_out = representation.duration[0] if representation.duration else live_gate
        event = {
            "pitch": root_pitch,
            "velocity": _clamp(velocity_out, 0.0, 1.0),
            "duration": duration_out,
            "interval": self._live_interval(block, rng),
            "rhythm": rhythm0,
        }
        if block.block_type in ("CHORD", "PAD"):
            event["pitches"] = self._chord_pitches(block, root_pitch)
        event = self.harmonize_event(block, event, motif_beat)
        return event

    def harmonize_event(self, block, event, beat=None):
        beat = self.clock.position_beats if beat is None else beat
        self.update_harmonic_context(beat)
        return self.harmonic_runtime.apply(block, event, beat)

    def dialogue_event(self, block, event, beat=None):
        """Final accepted event: turn-taking after probability and mute gates."""
        beat = self.clock.position_beats if beat is None else beat
        result = self.dialogue_runtime.apply(block, event, beat)
        if result is not None and result.pop('dialogue_pitch_changed', False):
            result['pitch'] = self._quantize_pitch(block, self._role_pitch(block, result['pitch']))
            # A response contour must obey today's chord, not replay the call's
            # old harmony or copy the caller's absolute octave.
            result = self.harmonize_event(block, result, beat)
        return result

    def update_harmonic_context(self, beat=None):
        beat = self.clock.position_beats if beat is None else beat
        harmony = self.harmonic_runtime.at(beat)
        if harmony is not None:
            self.musical_context.values["harmonic_plan"] = harmony
        else:
            self.musical_context.values.pop("harmonic_plan", None)
        return harmony

    def _chord_pitches(self, block: Block, root_pitch: float) -> list[float]:
        """Expand a harmonic role into a simultaneous diatonic voicing."""
        if block.block_type not in ("CHORD", "PAD"):
            return [float(root_pitch)]
        p = block.parameters
        profile = ROLE_PROFILES.get(block.block_type, ROLE_PROFILES["CHORD"])
        size = max(1, min(4, int(p.get("harmony_size", profile.get("harmony_size", 3)))))
        spread = max(0, int(p.get("harmony_spread", profile.get("harmony_spread", 7))))
        inversion = int(p.get("harmony_inversion", profile.get("harmony_inversion", 0)))
        root = self._root(block)
        scale = self._scale(block)

        # Diatonic thirds: 1-3-5-7.  Scale quality therefore follows the
        # selected Major/Minor/Dorian/etc. context automatically.
        # Thirds are stacked on the scale degree the generated root falls on,
        # so II/III/VI/VII chords keep the scale's quality.  Transposing one
        # fixed chord shape onto every root produced chromatic chords
        # (A-C#-E in C major).  ``chord_degree`` is an optional degree offset.
        offset = int(_as_float(p.get("chord_degree", p.get("harmony_degree", 0)), 0))
        degree = self._scale_degree(block, root_pitch) + offset
        pitches = [float(degree_to_note(degree + 2 * i, root, scale) - root) for i in range(size)]
        if spread > 0 and size > 1:
            for i in range(1, size):
                target = (spread * i) / float(size - 1)
                current = pitches[i] - pitches[0]
                while current < target:
                    pitches[i] += 12.0
                    current += 12.0
        if inversion > 0:
            for _ in range(min(inversion, size - 1)):
                pitches[0] += 12.0
                pitches = pitches[1:] + pitches[:1]
        elif inversion < 0:
            for _ in range(min(-inversion, size - 1)):
                pitches[-1] -= 12.0
                pitches = pitches[-1:] + pitches[:-1]
        # Move the complete voicing as one object so intervals are never
        # destroyed by role-register normalization.
        lo = float(profile["register_min"])
        hi = float(profile["register_max"])
        anchor = float(profile["register_anchor"])
        while max(pitches) > hi:
            pitches = [x - 12.0 for x in pitches]
        while min(pitches) < lo:
            pitches = [x + 12.0 for x in pitches]
        center = (pitches[0] + pitches[-1]) * 0.5
        while center - anchor > 6.0 and min(pitches) - 12.0 >= lo:
            pitches = [x - 12.0 for x in pitches]
            center -= 12.0
        while center - anchor < -6.0 and max(pitches) + 12.0 <= hi:
            pitches = [x + 12.0 for x in pitches]
            center += 12.0
        return [float(_clamp(x, lo, hi)) for x in pitches]


    # ---- processes and relations ------------------------------------------
    def _apply_processes(self, block: Block, representation: MusicalRepresentation, rng: random.Random):
        """Apply deterministic process primitives after generation/mutators.

        Processes are simple, composable transforms on musical dimensions
        rather than raw MIDI notes, so they can be chained and recalled.
        """
        streams = representation.as_outputs()
        n = len(representation.rhythm)
        for proc in block.processes:
            if proc.type == "Parameter Modulation":
                # A modulation *tap*: the stream is read by
                # collect_parameter_modulations() and must not be altered here.
                continue
            target = proc.target if proc.target in streams else "pitch"
            values = list(streams[target])
            if not values:
                continue
            p = proc.parameters
            amount = _clamp(float(p.get("depth", proc.amount)), 0.0, 1.0)
            if proc.type == "Counter":
                length = max(1, int(p.get("length", 8)))
                step = float(p.get("step", 1.0))
                offset = float(p.get("offset", 0.0))
                center = float(p.get("center", 0.0))
                waveform = str(p.get("waveform", "Ramp"))
                phase = float(p.get("phase", 0.0))
                reset = max(1, int(p.get("reset", length)))
                vals = []
                for i in range(n):
                    position = (i % reset) + phase
                    x = position / max(1.0, length - 1)
                    if waveform == "Triangle":
                        q = 1.0 - abs(2.0 * (x % 1.0) - 1.0)
                    elif waveform == "Sine":
                        q = (math.sin(2 * math.pi * (x % 1.0)) + 1.0) * 0.5
                    else:  # Ramp: honours phase and reset like the other waveforms
                        q = (position % length) / max(1.0, length - 1)
                    vals.append(center + (((q * step * length + offset) / max(1.0, length)) - 0.5) * 2.0)
                values = [v + vals[i] * amount for i, v in enumerate(values)]
            elif proc.type == "Modulo":
                modulus = max(1, int(p.get("modulus", 5)))
                offset = int(p.get("offset", 0))
                scale = float(p.get("scale", 1.0))
                mode = str(p.get("mode", "Add"))
                center = float(p.get("center", 0.0))
                vals = [(((i + offset) % modulus) / max(1, modulus - 1)) * scale for i in range(n)]
                if mode == "Multiply":
                    values = [v * (1.0 + vals[i] * amount) for i, v in enumerate(values)]
                elif mode == "Gate":
                    threshold = float(p.get("threshold", 0.5))
                    values = [v if vals[i] >= threshold else center for i, v in enumerate(values)]
                else:
                    values = [v + (vals[i] - center) * amount for i, v in enumerate(values)]
            elif proc.type == "Compare":
                threshold = float(p.get("threshold", 0.5))
                true_value = float(p.get("true_value", 1.0))
                false_value = float(p.get("false_value", 0.0))
                tolerance = max(1e-9, float(p.get("hysteresis", 0.0)))
                invert = bool(p.get("invert", False))
                op = str(p.get("operator", ">="))
                compare = {
                    ">": lambda v, t=threshold: v > t,
                    ">=": lambda v, t=threshold: v >= t,
                    "<": lambda v, t=threshold: v < t,
                    "<=": lambda v, t=threshold: v <= t,
                    "==": lambda v, t=threshold, tol=tolerance: abs(v - t) < tol,
                }.get(op, lambda v, t=threshold: v >= t)
                mix = _clamp(float(p.get("mix", amount)), 0.0, 1.0)
                values = [(true_value if compare(v) != invert else false_value) * mix + v * (1 - mix) for v in values]
            elif proc.type in ("Clock Divide", "Clock Multiply"):
                factor = max(1, int(p.get("factor", 2)))
                phase = int(p.get("phase", 0))
                duty = _clamp(float(p.get("duty", 0.5)), 0.0, 1.0)
                mode = str(p.get("mode", "Gate"))
                if proc.type == "Clock Divide":
                    divided = []
                    for i, v in enumerate(values):
                        active = ((i + phase) % (factor * 2)) / float(factor * 2) < duty
                        if mode == "Hold" and not active and divided:
                            divided.append(divided[-1])
                        else:
                            divided.append(v if active else 0.0)
                    values = divided
                else:
                    values = [values[((i + phase) // factor) % len(values)] for i in range(n)]
                    if mode == "Gate":
                        values = [v if (((i + phase) % factor) / factor) < duty else 0.0 for i, v in enumerate(values)]
            elif proc.type == "Memory":
                delay = max(1, int(p.get("delay", 1)))
                feedback = _clamp(float(p.get("feedback", amount)), 0.0, 1.0)
                mix = _clamp(float(p.get("mix", 1.0)), 0.0, 1.0)
                mode = str(p.get("mode", "Blend"))
                initial = float(p.get("initial", 0.0))
                out = []
                for i, v in enumerate(values):
                    past = values[i - delay] if i >= delay else initial
                    mem = past * feedback + v * (1 - feedback)
                    out.append(mem if mode == "Replace" else v * (1 - mix) + mem * mix)
                values = out
            elif proc.type == "Delay":
                delay = max(1, int(p.get("delay", 1)))
                repeats = max(1, int(p.get("repeats", 2)))
                feedback = _clamp(float(p.get("feedback", 0.5)), 0.0, 0.99)
                mix = _clamp(float(p.get("mix", amount)), 0.0, 1.0)
                decay = _clamp(float(p.get("decay", 0.7)), 0.0, 1.0)
                mode = str(p.get("mode", "Echo"))
                initial = float(p.get("initial", 0.0))
                out = []
                for i, v in enumerate(values):
                    delayed = 0.0
                    for r in range(1, repeats + 1):
                        j = i - delay * r
                        if j >= 0:
                            delayed += values[j] * (feedback ** (r - 1)) * (decay ** r)
                        elif r == 1:
                            delayed += initial * decay
                    if mode == "Replace":
                        out.append(delayed)
                    elif mode == "Gate":
                        out.append(v if delayed > 0 else 0.0)
                    else:
                        out.append(v * (1 - mix) + delayed * mix)
                values = out
            elif proc.type == "Feedback":
                feedback = _clamp(float(p.get("feedback", amount)), 0.0, 0.98)
                iterations = max(1, int(p.get("iterations", 1)))
                decay = _clamp(float(p.get("decay", 1.0)), 0.0, 1.0)
                mix = _clamp(float(p.get("mix", 1.0)), 0.0, 1.0)
                bias = float(p.get("bias", 0.0))
                clamp = max(0.0, float(p.get("clamp", 0.0)))
                out = list(values)
                for _ in range(iterations):
                    prev = float(p.get("initial", 0.0))
                    nxt = []
                    for v in out:
                        cur = v * (1 - feedback) + (prev + bias) * feedback * decay
                        if clamp > 0:
                            cur = _clamp(cur, -clamp, clamp)
                        nxt.append(cur)
                        prev = cur
                    out = nxt
                values = [old * (1 - mix) + new * mix for old, new in zip(values, out)]
            streams[target] = values
        for part in PARTS:
            setattr(representation, part, streams[part])

    @staticmethod
    def _relation_curve(value: float, curve: str) -> float:
        """Map normalized relation amount through a predictable curve."""
        x = _clamp(float(value), 0.0, 1.0)
        if curve == "Exponential":
            return x * x
        if curve == "Logarithmic":
            return 1.0 - (1.0 - x) * (1.0 - x)
        if curve == "Threshold":
            return 1.0 if x >= 0.5 else 0.0
        if curve == "Quantize":
            return round(x * 4.0) / 4.0
        return x

    def relation_cycles(self) -> list[list[int]]:
        """Return block-id cycles. Disabled relations do not participate."""
        graph = {}
        for r in self.project.relations:
            if getattr(r, "enabled", True) and r.algorithm != 'Dialogue':
                graph.setdefault(int(r.source_block), set()).add(int(r.destination_block))
        cycles=[]
        def visit(start):
            stack=[(start,[start])]; seen=set()
            while stack:
                node,path=stack.pop()
                for nxt in graph.get(node,()):
                    if nxt == start and len(path)>1:
                        cycles.append(path+[start]); continue
                    if nxt not in path and (node,nxt) not in seen:
                        seen.add((node,nxt)); stack.append((nxt,path+[nxt]))
        for node in graph: visit(node)
        unique=[]; keys=set()
        for c in cycles:
            k=tuple(c)
            if k not in keys: keys.add(k); unique.append(c)
        return unique

    def apply_relations(self, skip_destination: int | None = None):
        """Apply model relations with curve, probability and event delay.

        Relation evaluation is deterministic for a fixed project seed and
        relation position, so regenerating a project does not randomly flicker.
        Cyclic graphs are allowed only as a diagnostic; each relation reads the
        current snapshot and therefore never recursively evaluates another relation.
        """
        for block in self.project.blocks:
            base = self._base_outputs.get(block.id)
            if base is not None:
                block.outputs = {part: list(values) for part, values in base.items()}
        # Built-in rhythm-first relations run from the clean snapshot before
        # user-authored model relations. Rebuilding outputs therefore remains
        # idempotent and does not accumulate previous relation passes.
        self._apply_role_relations(skip_destination=skip_destination)
        for ridx, relation in enumerate(self.project.relations):
            if not getattr(relation, "enabled", True) or relation.algorithm == 'Dialogue':
                continue
            source = self.find_block(relation.source_block)
            destination = self.find_block(relation.destination_block)
            if source is None or destination is None:
                continue
            if skip_destination is not None and destination.id == skip_destination:
                continue
            src = source.outputs.get(relation.source_part, [])
            if not src:
                continue
            dst = list(destination.outputs.get(relation.destination_part) or [])
            n = len(dst) or len(src)
            dst = (dst + [0.0] * n)[:n]
            delay = max(0, int(getattr(relation, "delay", 0)))
            # A LIVE destination holds one event: read the source at its
            # current transport position instead of always at step 0.
            base = self.source_positions.get(source.id, 0) if destination.mode == "LIVE" and (source.mode != "LIVE" or coordinated(source)) else 0
            src = [src[(base + i - delay) % len(src)] for i in range(n)]
            probability = _clamp(float(getattr(relation, "probability", 1.0)), 0.0, 1.0)
            seed = self.project.seed + (int(getattr(relation, "id", 0)) or ridx + 1) * 104729
            if destination.mode == "LIVE":
                # One gate decision per LIVE event, not the same one forever.
                seed += 7919 * int(self.live_state.get(destination.id, {}).get("events", 0))
            rng = random.Random(seed)
            a = self._relation_curve(float(relation.amount), getattr(relation, "curve", "Linear"))
            if probability < 1.0:
                gate = [rng.random() < probability for _ in range(n)]
            else:
                gate = [True] * n
            result=[]
            for s,d,g in zip(src,dst,gate):
                if not g:
                    result.append(d); continue
                if relation.algorithm in ("Copy", "Mix", "Follow"):
                    result.append(d * (1-a) + s*a)
                elif relation.algorithm == "Quantize To":
                    result.append(d + (round(s) - d) * a)
                elif relation.algorithm == "Modulate":
                    result.append(d + s * a)
                elif relation.algorithm == "Trigger":
                    threshold = max(0.0, 1.0 - a)
                    result.append(1.0 if s > threshold else 0.0)
                else:
                    result.append(s)
            if relation.destination_part == "pitch" and destination.block_type not in PERCUSSIVE_TYPES:
                # Relations must not leave the destination's scale.
                result = [self._quantize_pitch(destination, v) for v in result]
            destination.outputs[relation.destination_part] = result
            if relation.destination_part == "rhythm":
                self._sync_rhythm_dependents(destination)



