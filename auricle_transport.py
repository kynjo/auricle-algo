"""Real-time MIDI transport and scheduling."""

from __future__ import annotations

import functools
import math
import threading
import time
import traceback
from typing import Any, Optional

import mido

from auricle_catalogs import PERCUSSIVE_TYPES, _clamp, _as_float
from auricle_model import Block, midi_note_for
from auricle_drum import timing_offset
from coordinated_kit import STEP_BEATS, voice_role

def get_midi_output_names():
    """Return available MIDI outputs without crashing when the backend is absent."""
    try:
        return list(mido.get_output_names()), None
    except Exception as exc:
        return [], str(exc)

def _transport_locked(method):
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._state_lock:
            return method(self, *args, **kwargs)
    return wrapped

class Transport:
    """Real-time transport.

    Free generators keep their own SEQ/LIVE schedules. Bound motifs use a
    shared beat clock, with independent musical step lengths per block.
    """
    LOG_FILE = "auricle_transport.log"

    def __init__(self, app: Any):
        self.app = app
        self.running = False
        self.outputs: dict[str, Any] = {}
        self.active_notes: list[tuple[float, Any, int, int, int]] = []
        self.next_due: dict[int, float] = {}
        self.next_live: dict[int, float] = {}
        self.seq_index: dict[int, int] = {}
        # Unswung, unjittered grid time and absolute step number per SEQ
        # block, plus a master 16th clock used to place joining blocks.
        self.grid_due: dict[int, float] = {}
        self.step_count: dict[int, int] = {}
        self._master_due = 0.0
        self._master_step = 0
        self._ports_refreshing = False
        self._state_lock = threading.RLock()
        self._motif_schedule = {}
        self._kit_schedule = {}
        self._drum_mod_slots = {}
        self.drum_output_history = {}

    def _advance_musical_clock(self, now):
        engine = self.app.engine
        delta = engine.clock.advance(now, self.app.project.tempo)
        engine.performance.tick(self.running, beat_delta=delta, now=now)
        engine.update_harmonic_context()

    @_transport_locked
    def set_tempo(self, value):
        """Change tempo at the edit time without jumping the beat position."""
        now = time.monotonic()
        old = max(1.0, float(self.app.project.tempo))
        if self.running:
            self._advance_musical_clock(now)
        self.app.project.tempo = max(1, int(value))
        self.app.engine.clock.tempo = float(self.app.project.tempo)
        ratio = old / self.app.project.tempo
        if self.running:
            for schedule in (self.next_due, self.grid_due, self.next_live):
                for owner, due in schedule.items():
                    schedule[owner] = now + (due - now) * ratio
            self._master_due = now + (self._master_due - now) * ratio

    @property
    def seq_interval(self) -> float:
        """Duration of one SEQ step (a 16th note) at the *current* tempo."""
        return 60.0 / max(1, int(self.app.project.tempo)) / 4.0

    def _playable_blocks(self):
        """Flatten Drum Machine voices into independent transport owners."""
        for block in self.app.project.blocks:
            if str(block.block_type).upper() == "DRUM" and getattr(block, "drum_voices", None):
                yield from block.drum_voices
            else:
                yield block

    @_transport_locked
    def refresh_ports(self):
        """Synchronize native MIDI handles with project routing.

        Port changes originate from Qt ComboBox callbacks, so this method is
        deliberately re-entrancy guarded.  The old handle is released only
        after its Auricle notes are stopped; no UI callback is allowed to
        rebuild widgets from inside the native port operation.
        """
        if self._ports_refreshing:
            return
        self._ports_refreshing = True
        try:
            ports, error = get_midi_output_names()
            if error:
                self.app.set_message(f"MIDI backend unavailable: {error}")
                return
            available = set(ports)
            wanted = {self._resolved_port_name(b) for b in self._playable_blocks() if self._resolved_port_name(b)}
            for name in list(self.outputs):
                if name not in wanted or name not in available:
                    port = self.outputs.pop(name)
                    self._release_port_notes(port)
                    try:
                        port.close()
                    except Exception:
                        pass
            for name in wanted:
                if name in self.outputs:
                    continue
                try:
                    port = mido.open_output(name)
                    self.outputs[name] = port
                except Exception as e:
                    self.app.set_message(f"MIDI open failed: {name}: {e}")
        finally:
            self._ports_refreshing = False

    @_transport_locked
    def close_ports(self):
        for port in list(self.outputs.values()):
            self._release_port_notes(port)
            try:
                port.close()
            except Exception:
                pass
        self.outputs.clear()

    @_transport_locked
    def start(self):
        if self.running:
            return
        self.refresh_ports()
        self.app.engine.reset_live()
        self.app.engine.harmonic_runtime.reset()
        self.app.engine.dialogue_runtime.reset()
        self.app.engine.motif_development.reset_playback()
        self.app.engine.clock.position_beats = 0.0
        self.app.engine.generate()
        now = time.monotonic()
        self.app.engine.clock.start(now, self.app.project.tempo)
        self.app.engine.performance._last_time = now
        if self.app.engine.director.phrase.running:
            self.app.engine.director.phrase.stage_index = -1
        self._motif_schedule.clear()
        self._kit_schedule.clear()
        self._drum_mod_slots.clear()
        self.drum_output_history.clear()
        self.next_due.clear(); self.grid_due.clear(); self.step_count.clear(); self.seq_index.clear()
        self.next_live = {b.id: now for b in self._playable_blocks() if b.mode == "LIVE"}
        self._master_due = now
        self._master_step = 0
        for block in self._playable_blocks():
            if self.app.engine.coordinated_drum(block) is not None:
                self._kit_schedule[block.id] = {
                    "slot": 0, "due": self._motif_due_beat(block, 0, STEP_BEATS), "mode": None,
                }
            motif = self.app.engine.active_motif(block)
            if motif is not None:
                step = self.app.engine.motif_step_beats(block, motif)
                # The worker's first tick arrives after PLAY, not at exactly
                # beat zero. Preserve the opening slot instead of treating
                # every starting block as a late joiner.
                self._motif_schedule[block.id] = {
                    "key": (motif.id, step), "slot": 0,
                    "due": self._motif_due_beat(block, 0, step), "mode": None,
                }
            if block.mode == "SEQ":
                self._anchor_block(block, now)
        self.running = True
        self.app.set_message("PLAY")

    @_transport_locked
    def stop(self):
        now = time.monotonic()
        if self.running:
            self._advance_musical_clock(now)
        self.app.engine.clock.stop(now)
        self.running = False
        self.all_notes_off()
        self.next_due.clear()
        self.next_live.clear()
        self.seq_index.clear()
        self.grid_due.clear()
        self.step_count.clear()
        self._motif_schedule.clear()
        self._kit_schedule.clear()
        self._drum_mod_slots.clear()
        self.app.set_message("STOP")

    @_transport_locked
    def all_notes_off(self):
        """Release notes owned by Auricle without affecting other MIDI clients."""
        # Do not broadcast CC123 here: an output port may be shared with a DAW,
        # another sequencer, or hardware.  STOP must only release Auricle's
        # own notes.  A separate explicit panic action can use CC123 if needed.
        self._release_notes(lambda _due, _port, _note, _channel, _owner_id: True)

    def _release_notes(self, predicate):
        """Release and remove active notes matching *predicate*.

        Identical MIDI notes on one port/channel are reference-counted by the
        active-note list.  A Note Off is emitted only when the removed voice was
        the last Auricle owner of that physical MIDI note.
        """
        removed = []
        remaining = []
        for item in self.active_notes:
            if predicate(*item):
                removed.append(item)
            else:
                remaining.append(item)

        self.active_notes = remaining
        released_keys = set()
        for _due, port, note, channel, _owner_id in removed:
            key = (id(port), note, channel)
            if key in released_keys:
                continue
            still_claimed = any(
                old_port is port and old_note == note and old_channel == channel
                for _d, old_port, old_note, old_channel, _owner in remaining
            )
            if still_claimed:
                continue
            released_keys.add(key)
            try:
                message = mido.Message("note_off", channel=channel, note=note, velocity=0)
                port.send(message)
                self._monitor(None, "", message)
            except Exception:
                pass

    def _release_port_notes(self, port: Any):
        """Release all Auricle claims on a port before that port is closed."""
        self._release_notes(lambda _due, old_port, _note, _channel, _owner_id: old_port is port)

    def _log_error(self, context: str, exc: Exception):
        try:
            with open(self.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {context}: {exc}\n")
                traceback.print_exc(file=f)
        except Exception:
            pass

    def _reopen_port(self, name: str):
        old = self.outputs.pop(name, None)
        if old is not None:
            # Release notes on the physical port before closing it.  Active
            # notes must never be reassigned to a replacement port: the MIDI
            # device that received Note On is the device that must receive
            # the corresponding Note Off.
            self._release_port_notes(old)
            try:
                old.close()
            except Exception:
                pass
        try:
            port = mido.open_output(name)
        except Exception as exc:
            self._log_error(f"reopen MIDI port {name}", exc)
            return None
        self.outputs[name] = port
        return port

    def _block_seq_interval(self, block: Block) -> float:
        """Return this block's STRUCTURE/TIMING rate-adjusted SEQ interval."""
        if self.app.engine.coordinated_drum(block) is not None:
            return STEP_BEATS * 60.0 / max(1, self.app.project.tempo)
        step = self.app.engine.motif_step_beats(block)
        if step is not None:
            return step * 60.0 / max(1, self.app.project.tempo)
        rate = _clamp(float(block.parameters.get("timing_rate", 1.0)), 0.25, 4.0)
        return self.seq_interval / rate

    def _note_duration(self, block: Block, interval: float, event: dict[str, float]) -> float:
        # Gate is a musical duration multiplier, not a scheduler tick.
        # 0.05 = very short staccato, 1.0 = full interval, >1 = legato/overlap.
        gate = float(event.get("duration", block.parameters.get("gate", 0.78)))
        return max(0.025, interval * _clamp(gate, 0.05, 1.5))

    def _monitor(self, block: Optional[Block], port_name: str, message: Any):
        """Send an exact outbound MIDI message to the GUI monitor."""
        try:
            self.app.log_midi_message(block, port_name, message)
        except Exception:
            # Diagnostics must never affect real-time MIDI transport.
            pass

    def _midi_channel(self, block: Block) -> int:
        """Return the MIDI wire channel (0..15) for a block.

        The GUI and project format use the musician-facing 1..16 numbering;
        mido uses the protocol's zero-based 0..15 numbering. Keep this
        conversion in one place so changing an existing block's channel is
        always reflected by the transport immediately.
        """
        try:
            channel = int(block.midi_channel)
        except (TypeError, ValueError):
            channel = 1
        channel = int(_clamp(channel, 1, 16))
        block.midi_channel = channel  # keep the model normalized (old JSON, live UI edits)
        return channel - 1

    def _resolved_port_name(self, block: Block) -> str:
        """Return the effective MIDI port for a block or Drum Voice."""
        own = str(getattr(block, "midi_port", "") or "")
        if own:
            return own
        parent_id = getattr(block, "parent_id", None) if getattr(block, "is_drum_voice", False) else None
        if parent_id is not None:
            parent = next((item for item in self.app.project.blocks if int(item.id) == int(parent_id)), None)
            if parent is not None:
                return str(getattr(parent, "midi_port", "") or "")
        return ""

    def _send_event(self, block: Block, event: dict[str, float], port: Any, interval: float):
        drum = self.app.engine.coordinated_drum(block) if getattr(block, "parent_id", None) is not None else None
        if drum is not None and voice_role(block) in ("closed_hat", "open_hat"):
            hats = {v.id for v in drum.drum_voices if voice_role(v) in ("closed_hat", "open_hat")}
            self._release_notes(lambda _due, _port, _note, _channel, owner: owner in hats)
        # CHORD events carry ``pitches`` and are emitted as simultaneous MIDI
        # note-ons. Non-chord events retain the original scalar path.
        pitches = event.get("pitches")
        if not isinstance(pitches, (list, tuple)) or not pitches:
            pitches = [event.get("pitch", 0.0)]
        for pitch in pitches:
            note_event = dict(event)
            note_event["pitch"] = float(pitch)
            self._send_note(block, note_event, port, interval)

    def _dispatch_event(self, block, event, port, interval):
        """One accepted-event path for SEQ, LIVE, motifs and Drum Voices."""
        engine = self.app.engine
        parent = engine.drum_parent_for(block)
        if block.muted or (parent is not None and parent.muted):
            return None
        event = engine.dialogue_event(block, event)
        if event is None:
            return None
        try:
            self.app.record_generated_event(block, event)
        except Exception:
            pass
        if port is not None:
            self._send_event(block, event, port, interval)
        return event

    def _send_note(self, block: Block, event: dict[str, float], port: Any, interval: float):
        note = midi_note_for(self.app.project, block, event.get("pitch", 0.0))
        velocity = int(_clamp(int(127 * float(event.get("velocity", 0.8))), 1, 127))
        channel = self._midi_channel(block)
        message = mido.Message("note_on", channel=channel, note=note, velocity=velocity)

        owner = block.id
        replaced = []
        remaining = []
        for item in self.active_notes:
            due, old_port, old_note, old_channel, owner_id = item
            if old_port is port and old_note == note and old_channel == channel and owner_id == owner:
                replaced.append(item)
            else:
                remaining.append(item)
        if replaced:
            for _due, old_port, old_note, old_channel, _owner_id in replaced:
                still_claimed = any(
                    old_port is p and old_note == n and old_channel == ch
                    for _d, p, n, ch, _o in remaining
                )
                if not still_claimed:
                    try:
                        old_message = mido.Message("note_off", channel=old_channel, note=old_note, velocity=0)
                        old_port.send(old_message)
                        self._monitor(block, self._resolved_port_name(block), old_message)
                    except Exception:
                        pass
        self.active_notes = remaining

        try:
            port.send(message)
            resolved_port = self._resolved_port_name(block)
            self._monitor(block, resolved_port, message)
        except Exception as exc:
            self._log_error(f"note_on block={block.id} channel={channel + 1} note={note}", exc)
            resolved_port = self._resolved_port_name(block)
            reopened = self._reopen_port(resolved_port) if resolved_port else None
            if reopened is None:
                raise
            reopened.send(message)
            self._monitor(block, resolved_port, message)
            port = reopened

        duration = self._note_duration(block, interval, event)
        if "harmony_remaining_beats" in event:
            duration = min(duration, max(.005, float(event["harmony_remaining_beats"]) * 60.0 / max(1, self.app.project.tempo)))
        if "dialogue_remaining_beats" in event:
            duration = min(duration, max(.005, float(event["dialogue_remaining_beats"]) * 60.0 / max(1, self.app.project.tempo)))
        self.active_notes.append((time.monotonic() + duration, port, note, channel, block.id))

    def _release_due(self, now: float):
        due_items = [item for item in self.active_notes if now >= item[0]]
        if not due_items:
            return
        due_ids = {id(item) for item in due_items}
        remaining = [item for item in self.active_notes if id(item) not in due_ids]
        self.active_notes = remaining
        for _due, port, note, channel, _owner_id in due_items:
            still_claimed = any(
                old_port is port and old_note == note and old_channel == channel
                for _d, old_port, old_note, old_channel, _owner in remaining
            )
            if still_claimed:
                continue
            try:
                message = mido.Message("note_off", channel=channel, note=note, velocity=0)
                port.send(message)
                self._monitor(None, "", message)
            except Exception:
                pass

    def _release_block_notes(self, block_id: int):
        """Immediately release all notes currently owned by one block."""
        owned = {int(block_id)}
        parent = next((block for block in self.app.project.blocks if block.id == int(block_id)), None)
        if parent is not None and getattr(parent, "drum_voices", None):
            owned.update(int(voice.id) for voice in parent.drum_voices)
        self._release_notes(lambda _due, _port, _note, _channel, owner_id: owner_id in owned)

    def set_block_muted(self, block_id: int, muted: bool):
        """Apply mute/unmute immediately to the running transport.

        Mute only releases the block's notes.  Its clock and step index keep
        running (see _seq_event), so unmute resumes in phase with the other
        blocks; removing the schedule used to re-anchor it off the grid.
        """
        if muted:
            self._release_block_notes(block_id)
            return
        if not self.running:
            return
        block = next((b for b in self.app.project.blocks if b.id == block_id), None)
        if block is None:
            return
        now = time.monotonic()
        if block.mode == "SEQ":
            if block_id not in self.next_due or block_id not in self.grid_due:
                self._anchor_block(block, now)
        elif block_id not in self.next_live:
            self.next_live[block_id] = now

    def _swung_time(self, block: Block, grid: float, step: int, interval: float) -> float:
        """Actual time of a grid step: odd steps are delayed by swing, and
        humanize jitters this step only (it never feeds back into the grid)."""
        swing = _clamp(_as_float(block.parameters.get("timing_swing", 0.0), 0.0), 0.0, 0.5)
        humanize = _clamp(_as_float(block.parameters.get("timing_humanize", 0.0), 0.0), 0.0, 0.25)
        if block.mode == "LIVE" and self.app.engine.coordinated_drum(block) is not None:
            swing = _clamp(_as_float(self.app.engine._live_parameter(block, "timing_swing", swing), swing), 0.0, .5)
            humanize = _clamp(_as_float(self.app.engine._live_parameter(block, "timing_humanize", humanize), humanize), 0.0, .25)
        jitter = self.app.engine._rng_for(block).uniform(-humanize, humanize) if humanize else 0.0
        drum = self.app.engine.drum_parent_for(block)
        if drum is not None:
            return grid + timing_offset(drum, self.app.engine._seed_for(block), step, swing, jitter) * interval
        return grid + ((swing if step % 2 else 0.0) + jitter) * interval

    def _anchor_block(self, block: Block, now: float):
        """Place a starting or joining SEQ block on the shared 16th grid."""
        interval = self._block_seq_interval(block)
        if self.running and self._master_due > now:
            rate = self.seq_interval / max(1e-9, interval)
            grid, step = self._master_due, int(round(self._master_step * rate))
        else:
            grid, step = now, 0
        offset = _clamp(_as_float(block.parameters.get("timing_offset", 0.0), 0.0), -0.5, 0.5)
        self.grid_due[block.id] = grid + offset * interval
        self.step_count[block.id] = step
        self.seq_index[block.id] = step
        self.next_due[block.id] = self._swung_time(block, self.grid_due[block.id], step, interval)

    def _advance_seq_clock(self, block: Block, now: float, interval: float):
        """Advance one grid step; after a stall, skip missed steps *and* their
        pattern positions so the block stays on the grid and in phase."""
        grid = self.grid_due.get(block.id, now) + interval
        step = self.step_count.get(block.id, 0) + 1
        skipped = 0
        while grid + interval <= now and skipped < 4096:
            grid += interval
            step += 1
            skipped += 1
        if skipped:
            self.seq_index[block.id] = self.seq_index.get(block.id, 0) + skipped
        self.grid_due[block.id] = grid
        self.step_count[block.id] = step
        self.next_due[block.id] = self._swung_time(block, grid, step, interval)

    def _ordered_tick_blocks(self):
        """Return blocks in a dependency-safe order for one transport tick.

        LIVE relations are evaluated while their destination event is built.
        A destination therefore must run after any LIVE source it reads;
        otherwise a project-list reorder changes the audible result.  SEQ
        blocks are processed first because their current grid position is also
        a source for LIVE destinations.  Cycles remain deterministic by
        keeping the original project order at the cycle boundary.
        """
        blocks = list(self._playable_blocks())
        seq = [block for block in blocks if block.mode == "SEQ"]
        live = [block for block in blocks if block.mode == "LIVE"]
        by_id = {block.id: block for block in live}
        live_ids = set(by_id)
        dependencies = {block.id: [] for block in live}

        for destination in live:
            candidates = []
            built_in = self.app.engine.role_relation_source(destination)
            if built_in is not None:
                if str(built_in.block_type).upper() == "DRUM" and getattr(built_in, "drum_voices", None):
                    candidates.extend(voice.id for voice in built_in.drum_voices if voice.mode == "LIVE")
                elif built_in.mode == "LIVE":
                    candidates.append(built_in.id)
            for relation in self.app.project.relations:
                if not getattr(relation, "enabled", True) or relation.algorithm == 'Dialogue' or relation.destination_block != destination.id:
                    continue
                source_parent = next((item for item in self.app.project.blocks
                                      if item.id == relation.source_block), None)
                if source_parent is not None and str(source_parent.block_type).upper() == "DRUM" and getattr(source_parent, "drum_voices", None):
                    candidates.extend(voice.id for voice in source_parent.drum_voices if voice.mode == "LIVE")
                else:
                    source = by_id.get(relation.source_block)
                    if source is not None:
                        candidates.append(source.id)
            dependencies[destination.id] = list(dict.fromkeys(candidates))

        ordered = []
        visiting = set()
        visited = set()

        def visit(block_id):
            if block_id in visited:
                return
            if block_id in visiting:
                # A relation cycle is diagnosed elsewhere. Do not recurse
                # forever; the first project-order node remains the anchor.
                return
            visiting.add(block_id)
            for source_id in dependencies.get(block_id, []):
                if source_id in live_ids:
                    visit(source_id)
            visiting.remove(block_id)
            visited.add(block_id)
            ordered.append(by_id[block_id])

        for block in live:
            visit(block.id)
        return seq + ordered

    def _seq_event(self, block: Block, now: float, port: Any, absolute_slot=None):
        # Mute is an output gate. Keep the sequencer clock advancing, but
        # never allow direct calls to this low-level sender to bypass mute.
        # This protects both the transport loop and tests/tools that invoke
        # the event generator directly.
        engine = self.app.engine
        rhythm = block.outputs.get("rhythm", [])
        if not rhythm:
            return
        i = self.seq_index.get(block.id, 0) % len(rhythm)
        self.seq_index[block.id] = i + 1
        positions = getattr(engine, "source_positions", None)
        if positions is not None:
            positions[block.id] = i
            parent = engine.drum_parent_for(block)
            if parent is not None:
                positions[parent.id] = i
        parent = engine.drum_parent_for(block)
        if block.muted or (parent is not None and parent.muted):
            # The step index advanced above, so unmute resumes on the current
            # phase (it used to freeze the pattern position while muted).
            engine.collect_parameter_modulations(block, i)
            return
        event = None
        slot = self.step_count.get(block.id, i) if absolute_slot is None else absolute_slot
        if rhythm[i] > 0 and engine.pattern_step_allowed(block, slot):
            probability = engine.event_probability(block)
            if probability >= 1.0 or engine._rng_for(block).random() <= probability:
                pitch = block.outputs.get("pitch", [])
                velocity = block.outputs.get("velocity", [])
                duration = block.outputs.get("duration", [])
                root_pitch = pitch[i] if i < len(pitch) else 0.0
                event = {
                    "pitch": root_pitch,
                    "velocity": velocity[i] if i < len(velocity) else 0.8,
                }
                if block.block_type in ("CHORD", "PAD"):
                    event["pitches"] = engine._chord_pitches(block, root_pitch)
                # Processes may shape the duration stream; honour it in SEQ too.
                if i < len(duration) and duration[i] > 0:
                    event["duration"] = duration[i]
                event = engine.harmonize_event(block, event)
                event = self._dispatch_event(block, event, port, self._block_seq_interval(block))
        engine.collect_parameter_modulations(block, i)
        return event

    def _observe_kit_output(self, block, slot, event):
        """Bounded transport history: missing slot != a generated rest."""
        history = self.drum_output_history.setdefault(block.id, {})
        history[int(slot)] = max(0., min(1., float(event.get("velocity", .8)))) if event else 0.
        if len(history) > 384:
            for old in sorted(history)[:-384]:
                del history[old]

    def _motif_due_beat(self, block, slot, step):
        offset = _clamp(_as_float(block.parameters.get("timing_offset", 0.0), 0.0), -.5, .5)
        return self._swung_time(block, slot * step, slot, step) + offset * step

    def _tick_kit_voice(self, block, now, port):
        """One shared sixteenth grid, including rests and mode changes."""
        engine = self.app.engine
        beat = engine.clock.position_beats
        schedule = self._kit_schedule.get(block.id)
        if schedule is None:
            slot = max(0, int(math.ceil(beat / STEP_BEATS - 1e-8)))
            schedule = {"slot": slot, "due": self._motif_due_beat(block, slot, STEP_BEATS), "mode": None}
            self._kit_schedule[block.id] = schedule
        slot = schedule["slot"]
        if beat >= (slot + 1) * STEP_BEATS - 1e-8:
            slot = max(slot, int(math.floor(beat / STEP_BEATS + 1e-8)))
            schedule["slot"] = slot
            schedule["due"] = self._motif_due_beat(block, slot, STEP_BEATS)
        if beat + 1e-8 < schedule["due"]:
            return
        scheduled_beat = slot * STEP_BEATS
        plan = engine.kit_plan(block, scheduled_beat)
        variant = engine.motif_variant(block, scheduled_beat)
        token = variant.token if variant is not None else None
        if block.mode == "SEQ" and (schedule["mode"] != "SEQ" or
                engine._seq_kit_tokens.get(block.id) != plan.token or
                engine._seq_motif_tokens.get(block.id) != token):
            engine.regenerate(block, motif_beat=scheduled_beat)
        schedule.update(mode=block.mode, slot=slot + 1,
                        due=self._motif_due_beat(block, slot + 1, STEP_BEATS))
        if block.mode == "SEQ":
            self.seq_index[block.id] = slot % plan.length
            accepted_event = self._seq_event(block, now, port, absolute_slot=slot)
        else:
            accepted_event = None
            event = engine.live_event(block, beat=scheduled_beat)
            if event is not None:
                probability = engine.event_probability(block)
                if probability >= 1.0 or engine._rng_for(block).random() <= probability:
                    accepted_event = self._dispatch_event(block, event, port, self._block_seq_interval(block))
        self._observe_kit_output(block, slot, accepted_event)
        parent = engine.drum_parent_for(block)
        engine._aggregate_drum_outputs(parent)
        engine.apply_relations()

    def _tick_motif(self, block, motif, now, port):
        """Schedule SEQ/LIVE motif slots on the same absolute beat clock.

        Rests and muted events consume slots too. Late ticks skip old slots
        instead of playing a burst, and parameter regeneration owns no phase.
        """
        engine = self.app.engine
        beat = engine.clock.position_beats
        step = engine.motif_step_beats(block, motif)
        key = (motif.id, step)
        schedule = self._motif_schedule.get(block.id)
        if schedule is None or schedule["key"] != key:
            slot = max(0, int(math.ceil(beat / step - 1e-8)))
            schedule = {"key": key, "slot": slot, "due": self._motif_due_beat(block, slot, step), "mode": None}
            self._motif_schedule[block.id] = schedule
        slot = schedule["slot"]
        if beat >= (slot + 1) * step - 1e-8:
            slot = max(slot, int(math.floor(beat / step + 1e-8)))
            schedule["slot"] = slot
            schedule["due"] = self._motif_due_beat(block, slot, step)
        if beat + 1e-8 < schedule["due"]:
            return
        # Resolve at the scheduled slot, including early humanized onsets.
        # SEQ must rebuild on a new variant just as LIVE reads the new material.
        variant = engine.motif_variant(block, beat=slot * step)
        if block.mode == "SEQ" and (schedule["mode"] != "SEQ" or
                engine._seq_motifs.get(block.id) is not motif or
                engine._seq_motif_tokens.get(block.id) != variant.token):
            engine.regenerate(block, motif_beat=slot * step)
        schedule["mode"] = block.mode
        schedule["slot"] = slot + 1
        schedule["due"] = self._motif_due_beat(block, slot + 1, step)
        interval = step * 60.0 / max(1, self.app.project.tempo)
        if block.mode == "SEQ":
            self.seq_index[block.id] = slot % motif.steps
            self._seq_event(block, now, port)
        else:
            event = engine.live_event(block, beat=slot * step)
            if event is not None:
                probability = engine.event_probability(block)
                if probability >= 1.0 or engine._rng_for(block).random() <= probability:
                    self._dispatch_event(block, event, port, interval)
        parent = engine.drum_parent_for(block)
        if parent is not None:
            engine._aggregate_drum_outputs(parent)
            engine.apply_relations()

    @_transport_locked
    def tick(self):
        if not self.running:
            return
        now = time.monotonic()
        engine = self.app.engine
        self._advance_musical_clock(now)
        # Apply only values queued during previous ticks. Any modulation
        # generated below is therefore guaranteed at least one tick late.
        engine.apply_pending_parameter_modulations()
        self._release_due(now)
        interval = self.seq_interval
        self._master_step = int(math.floor(engine.clock.position_beats * 4 + 1e-8)) + 1
        self._master_due = now + engine.clock.seconds_for_beats(self._master_step / 4 - engine.clock.position_beats)

        # Process each block independently. A single bad block/port must not
        # terminate the entire musical engine.
        for block in self._ordered_tick_blocks():
            try:
                # Mute is an audio/MIDI output gate, not a generator pause.
                # Keep clocks, sequence indices, LIVE state and modulation
                # running so unmute resumes on the current musical phase.
                parent = engine.drum_parent_for(block)
                muted = bool(block.muted or (parent is not None and parent.muted))
                port_name = self._resolved_port_name(block)
                if muted or not engine.dialogue_runtime.can_play(block, engine.clock.position_beats):
                    self._release_block_notes(block.id)
                port = None if block.muted else (self.outputs.get(port_name) if port_name else None)
                if muted:
                    port = None
                if engine.coordinated_drum(block) is not None:
                    self.grid_due.pop(block.id, None)
                    self._motif_schedule.pop(block.id, None)
                    self._tick_kit_voice(block, now, port)
                    continue
                if self._kit_schedule.pop(block.id, None) is not None:
                    if block.mode == "SEQ":
                        engine.regenerate(block)
                    else:
                        self.next_live[block.id] = now
                motif = engine.active_motif(block)
                if motif is not None:
                    self.grid_due.pop(block.id, None)
                    self._tick_motif(block, motif, now, port)
                    continue
                if self._motif_schedule.pop(block.id, None) is not None:
                    if block.mode == "SEQ":
                        engine.regenerate(block)
                    else:
                        self.next_live[block.id] = now
                if block.mode == "SEQ":
                    block_interval = self._block_seq_interval(block)
                    if block.id not in self.grid_due:
                        self._anchor_block(block, now)  # new or returning block joins the grid
                    due = self.next_due.get(block.id, now)
                    if now >= due:
                        self._seq_event(block, now, port)
                        parent = engine.drum_parent_for(block)
                        if parent is not None:
                            engine._aggregate_drum_outputs(parent)
                            # Re-apply user relations after the child voice
                            # changes the parent source snapshot. Without this
                            # pass, a relation targeting the Drum container
                            # could be overwritten by the next aggregation.
                            engine.apply_relations()
                        self._advance_seq_clock(block, now, block_interval)
                elif block.mode == "LIVE":
                    self.grid_due.pop(block.id, None)  # re-anchor if it returns to SEQ
                    due = self.next_live.get(block.id, now)
                    if now >= due:
                        event = engine.live_event(block)
                        if event is not None:
                            probability = engine.event_probability(block)
                            accepted = probability >= 1.0 or engine._rng_for(block).random() <= probability
                            live_interval = float(event.get("interval", 0.25))
                            if accepted:
                                self._dispatch_event(block, event, port, live_interval)
                        else:
                            live_interval = engine._live_interval(block, engine._rng_for(block))
                        parent = engine.drum_parent_for(block)
                        if parent is not None:
                            engine._aggregate_drum_outputs(parent)
                            engine.apply_relations()
                        self.next_live[block.id] = now + max(0.01, live_interval)
            except Exception as exc:
                # Disable only this block for the current step; keep other
                # generators alive and make the actual failure inspectable.
                self._log_error(f"transport block={block.id} {block.name}", exc)
                self.app.set_message(f"MIDI error: {block.name} — see {self.LOG_FILE}")
                if block.mode == "SEQ":
                    try:
                        self._advance_seq_clock(block, now, self._block_seq_interval(block))
                    except Exception:
                        self.next_due[block.id] = now + interval
                else:
                    self.next_live[block.id] = now + 0.25

        # A kit container is not a playable voice. Sample its modulation tap
        # once per shared grid slot, after all children have updated the bus.
        # Pending values are still applied only on the following tick.
        slot = max(0, int(math.floor(engine.clock.position_beats / STEP_BEATS + 1e-8)))
        for drum in self.app.project.blocks:
            if not getattr(drum, "drum_voices", None) or self._drum_mod_slots.get(drum.id) == slot:
                continue
            self._drum_mod_slots[drum.id] = slot
            try:
                engine.collect_parameter_modulations(drum, engine.source_positions.get(drum.id, slot))
            except Exception as exc:
                self._log_error(f"transport kit modulation={drum.id}", exc)
