"""Real-time MIDI transport and scheduling."""

from __future__ import annotations

import functools
import heapq
from dataclasses import dataclass
import math
import threading
import time
import traceback
from typing import Any, Optional

import mido

from auricle_catalogs import _clamp, _as_float
from auricle_model import Block, midi_note_for, relation_endpoint_id
from auricle_drum import timing_offset
from coordinated_kit import STEP_BEATS, voice_role
from musical_clock import MusicalGrid
from musical_events import MusicalEvent
from drum_articulation import articulate, articulation_values, supports_articulation
from piano_roll_history import clock_beat_at
from strum import strum_hits, supports_strum
from transport_queue import TransportCommandQueue
from midi_expression import MidiExpressionRuntime, entity_expression_config, normalize_midi_sync


@dataclass(frozen=True)
class _PendingArticulation:
    owner: Any
    event: dict
    port: Any
    expires: float
    context: tuple | None
    route: tuple
    mode: str
    block_type: str

def get_midi_input_names():
    """Return available MIDI inputs without crashing when the backend is absent."""
    try:
        return list(mido.get_input_names()), None
    except Exception as exc:
        return [], str(exc)


def get_midi_output_names():
    """Return available MIDI outputs without crashing when the backend is absent."""
    try:
        return list(mido.get_output_names()), None
    except Exception as exc:
        return [], str(exc)

def _transport_locked(method):
    """Serialize transport commands without taking the GUI/model lock.

    The transport worker must never hold the lock used by Qt callbacks and
    widget refreshes.  GUI code may call transport commands while holding its
    own lock; the worker therefore uses this independent lock domain only.
    """
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._transport_lock:
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
        self.playback_mode = "blocks"
        self.composition_position = 0.0
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
        # Independent lock domains:
        # - _state_lock / _gui_lock: legacy GUI-local lock retained for panels
        #   not yet migrated to enqueue_gui_command(). It does NOT protect data
        #   from the transport worker and must not be treated as a shared-model
        #   synchronization primitive.
        # - _transport_lock: serializes scheduler state, MIDI ports, model
        #   command application and transport commands. Qt painting uses it
        #   only non-blockingly; model edits go through gui_command_queue.
        self._state_lock = threading.RLock()
        self._gui_lock = self._state_lock
        self._transport_lock = threading.RLock()
        self._motif_schedule = {}
        self._kit_schedule = {}
        self._drum_mod_slots = {}
        self.drum_output_history = {}
        self._composition_section_key = None
        self._composition_context = None
        self.expression_runtime = MidiExpressionRuntime()
        self._expression_routes = {}
        self._expression_owner_state = {}
        self._pitch_bend_ranges = {}
        self._clock_next_due = None
        self._clock_interval = None
        self._clock_active_ports = {}
        self._ordered_tick_signature = None
        self._ordered_tick_cache = ()
        # GUI edits are staged here and applied by the transport thread at a
        # tick boundary. This prevents concurrent mutation of model/engine
        # objects while a generator or Relations pass is reading them.
        self.gui_command_queue = TransportCommandQueue()
        self.gui_command_errors = 0
        self._articulation_queue = []
        self._articulation_serial = 0
        self._articulation_note_beats = {}

    def enqueue_gui_command(self, callback, *, key=None, notification=None, label="GUI edit"):
        """Submit a model edit for serialized application on the transport thread.

        Keyed commands coalesce rapid control changes; unkeyed commands retain
        FIFO order. The caller must keep callbacks free of Qt widget access.
        """
        return self.gui_command_queue.push(
            callback, key=key, notification=notification, label=label
        )

    def _drain_gui_commands(self, *, notify=True):
        """Apply the pending GUI transaction batch on the transport thread."""
        for command in self.gui_command_queue.pop_all():
            try:
                command["callback"]()
            except Exception as exc:
                self.gui_command_errors += 1
                self._log_error(f"GUI command: {command.get('label', 'edit')}", exc)
                continue
            notification = command.get("notification")
            signal = getattr(self.app, "_transport_command_applied_signal", None)
            # History/save can win the race with the next worker tick. A quiet
            # commit must still deliver numeric readback, without dirtying the
            # document or replaying structural refresh notifications.
            if not notify and isinstance(notification, dict) and notification.get("parameter_feedback"):
                notification = {key: notification[key] for key in
                                ("block_id", "parameter_entity", "parameter_feedback")
                                if key in notification}
                notification["dirty"] = False
            elif not notify:
                continue
            if notification is not None and signal is not None:
                try:
                    signal.emit(notification)
                except Exception:
                    pass

    @_transport_locked
    def flush_gui_commands(self, *, notify=True):
        """Synchronously apply queued edits before save/project replacement."""
        self._drain_gui_commands(notify=notify)

    def _advance_musical_clock(self, now):
        engine = self.app.engine
        delta = engine.clock.advance(now, self.app.project.tempo)
        runtime = engine.composition_runtime
        if runtime.finished(engine.clock.position_beats):
            end = runtime.total_beats()
            delta = max(0., delta - max(0., engine.clock.position_beats - end))
            engine.clock.position_beats = end
        if self.playback_mode == "composition":
            engine.section_performance.advance(engine.clock.position_beats, now=now)
            engine.section_automation.advance(engine.clock.position_beats)
        else:
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
            # Articulated gates, like their pending onsets, retain musical time.
            retimed = []
            deadlines = {}
            for item in self.active_notes:
                end = self._articulation_note_beats.get(id(item))
                if end is not None:
                    item = (now + self.app.engine.clock.seconds_for_beats(
                        max(0., end - self.app.engine.clock.position_beats), self.app.project.tempo), *item[1:])
                    deadlines[id(item)] = end
                retimed.append(item)
            self.active_notes = retimed
            self._articulation_note_beats = deadlines
            for schedule in (self.next_due, self.grid_due, self.next_live):
                for owner, due in schedule.items():
                    schedule[owner] = now + (due - now) * ratio
            self._master_due = now + (self._master_due - now) * ratio
            # Re-anchor the 24-PPQN clock to the new tempo immediately; without
            # this, the first pulse after a tempo edit can use the old interval.
            sync = normalize_midi_sync(getattr(self.app.project, "midi_sync", {}))
            self._clock_next_due = (now + 60.0 / max(1.0, float(self.app.project.tempo)) / 24.0
                                    if sync["clock_out"] else None)

    @property
    def seq_interval(self) -> float:
        """Duration of one SEQ step (a 16th note) at the *current* tempo."""
        return self.app.engine.clock.seconds_for_beats(0.25, self.app.project.tempo)

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
            sync = normalize_midi_sync(getattr(self.app.project, "midi_sync", {}))
            if (sync["clock_out"] or sync["transport_messages"]) and sync["clock_port"] != "*":
                wanted.add(sync["clock_port"])
            for name in list(self.outputs):
                if name not in wanted or name not in available:
                    port = self.outputs.pop(name)
                    self._reset_expression_port(port)
                    self._release_port_notes(port)
                    for route in [route for route in self._pitch_bend_ranges if route[0] == id(port)]:
                        self._pitch_bend_ranges.pop(route, None)
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
        self._stop_midi_clock()
        self._reset_expression()
        for port in list(self.outputs.values()):
            self._release_port_notes(port)
            try:
                port.close()
            except Exception:
                pass
        self.outputs.clear()
        self._pitch_bend_ranges.clear()

    @_transport_locked
    def start(self, position_beats=None, *, mode="blocks"):
        self._drain_gui_commands()
        """Start one scheduler in an explicit Blocks/Composition/Perform mode.

        The header always requests Blocks, so saved form/phrase settings cannot
        silently take over an initial sound check. Mode switches release notes
        and rebuild source material under the new effective controls.
        """
        if mode not in ("blocks", "composition", "perform"):
            raise ValueError(f"Unknown playback mode: {mode}")
        if self.running:
            if self.playback_mode == mode:
                if position_beats is not None:
                    self.seek(position_beats)
                return
            self.stop()
        self.playback_mode = mode
        self.app.engine.section_automation.reset()
        self.app.engine.composition_runtime.playback_active = mode == "composition"
        position = self._seek_position(0. if position_beats is None else position_beats)
        if mode == "composition":
            self.composition_position = position
        self.refresh_ports()
        self.app.engine.reset_live()
        self.app.engine.harmonic_runtime.reset()
        self.app.engine.dialogue_runtime.reset()
        self.app.engine.motif_development.reset_playback()
        self.app.engine.clock.position_beats = position
        self.app.engine.section_performance.reset(clear_layers=False)
        if mode == "composition":
            self.app.engine.section_performance.advance(position, force=True)
            self.app.engine.section_automation.advance(position, force=True, regenerate=False)
        self.app.engine.generate()
        now = time.monotonic()
        self.app.engine.clock.start(now, self.app.project.tempo)
        self.app.engine.clock.seek(position, now)
        self.app.engine.performance._last_time = now
        self._prime_schedules(now, position)
        self.running = True
        self._start_midi_clock(position, now)
        self.app.set_message(f"PLAY · {mode.upper()}")

    @staticmethod
    def _seek_position(position):
        try:
            position = float(position)
        except (ValueError, TypeError, OverflowError):
            position = 0.
        return max(0., position) if math.isfinite(position) else 0.

    def _prime_schedules(self, now, position):
        """Re-anchor every scheduler to one musical position, without catch-up."""
        engine = self.app.engine
        self._cancel_articulations()
        self._motif_schedule.clear()
        self._kit_schedule.clear()
        self._drum_mod_slots.clear()
        self.drum_output_history.clear()
        self._record_piano(action="reset")
        for owner in self._playable_blocks():
            owner._parameter_feedback_event = None
        self._composition_section_key = None
        self._composition_context = None
        self.expression_runtime.reset()
        self._expression_routes.clear()
        self._expression_owner_state.clear()
        self.next_due.clear(); self.grid_due.clear(); self.step_count.clear(); self.seq_index.clear()
        self.next_live = {b.id: now for b in self._playable_blocks() if b.mode == "LIVE"}
        master_grid = MusicalGrid(0.25)
        self._master_step = max(0, master_grid.slot_at(position, "ceil"))
        self._master_due = now + engine.clock.seconds_for_beats(master_grid.beat_at(self._master_step) - position)
        for block in self._playable_blocks():
            if self.app.engine.coordinated_drum(block) is not None:
                slot = max(0, MusicalGrid(STEP_BEATS).slot_at(position, "ceil"))
                self._kit_schedule[block.id] = {
                    "slot": slot, "due": self._motif_due_beat(block, slot, STEP_BEATS), "mode": None,
                }
            motif = self.app.engine.active_motif(block)
            if motif is not None or block.algorithm == "Euclidean":
                step = self.app.engine.sequence_step_beats(block, live=block.mode == "LIVE")
                slot = max(0, MusicalGrid(step).slot_at(position, "ceil"))
                # The worker's first tick arrives after PLAY, not at exactly
                # beat zero. Preserve the opening slot instead of treating
                # every starting block as a late joiner.
                self._motif_schedule[block.id] = {
                    "key": (motif.id if motif is not None else "euclidean", step), "slot": slot,
                    "due": self._motif_due_beat(block, slot, step), "mode": None,
                }
            if block.mode == "SEQ":
                step_beats = engine.sequence_step_beats(block)
                slot = max(0, MusicalGrid(step_beats).slot_at(position, "ceil"))
                interval = self._block_seq_interval(block)
                offset = _clamp(_as_float(block.parameters.get("timing_offset", 0.), 0.), -.5, .5)
                grid_beat = MusicalGrid(step_beats).beat_at(slot)
                grid = now + engine.clock.seconds_for_beats(grid_beat - position, self.app.project.tempo) + offset * interval
                self.grid_due[block.id] = grid
                self.step_count[block.id] = self.seq_index[block.id] = slot
                self.next_due[block.id] = self._swung_time(block, grid, slot, interval)
                material = block.outputs.get("rhythm", ())
                if material:
                    engine.source_positions[block.id] = slot % len(material)

    @_transport_locked
    def seek(self, position_beats):
        self._drain_gui_commands()
        """Move stopped or playing transport; preserve Perform gestures.

        SEQ/Kit/motif positions follow the destination grid. Free LIVE restarts
        its generator state there, without simulating every skipped event.
        """
        position = self._seek_position(position_beats)
        engine = self.app.engine
        self._reset_expression()
        self.all_notes_off()
        engine.section_automation.reset()
        engine.reset_live(reset_performance=False)
        engine.harmonic_runtime.reset()
        engine.dialogue_runtime.reset()
        engine.motif_development.reset_playback()
        engine.clock.position_beats = position
        if self.running and self.playback_mode == "composition":
            engine.section_performance.advance(position, force=True)
            engine.section_automation.advance(position, force=True, regenerate=False)
        engine.generate()
        now = time.monotonic()
        engine.clock.seek(position, now)
        engine.performance._last_time = now
        engine.update_harmonic_context(position)
        self._prime_schedules(now, position)
        self._sync_composition_section(position)
        sync = normalize_midi_sync(getattr(self.app.project, "midi_sync", {}))
        if not self.running and (sync["clock_out"] or sync["transport_messages"]):
            self.refresh_ports()
        self._seek_midi_clock(position, now, running=self.running)
        self.app.set_message(f"SEEK · beat {position:g}")
        return position

    @_transport_locked
    def stop(self, *, advance=True):
        # Do not drain here: stop() can also be called from inside tick() when
        # Composition ends. The next idle scheduler tick drains pending edits.
        now = time.monotonic()
        if self.running and advance:
            self._advance_musical_clock(now)
        if advance:
            self.app.engine.clock.stop(now)
        else:
            self.app.engine.clock.running = False
            self.app.engine.clock.seek(self.app.engine.clock.position_beats, now)
        was_performing = bool(self.app.engine.performance.active
                              or self.app.engine.performance.active_phrase_releases
                              or self.app.engine.director.phrase.running)
        if self.playback_mode == "composition":
            self.composition_position = self.app.engine.clock.position_beats
        self._stop_midi_clock()
        self._reset_expression()
        self.running = False
        self.all_notes_off()
        self.app.engine.performance.reset()
        self.app.engine.section_performance.reset(clear_layers=False)
        was_performing = self.app.engine.section_automation.reset() or was_performing
        self.app.engine.composition_runtime.playback_active = None
        if was_performing:
            self.app.engine.generate()
        self.next_due.clear()
        self.next_live.clear()
        self.seq_index.clear()
        self.grid_due.clear()
        self.step_count.clear()
        self._motif_schedule.clear()
        self._kit_schedule.clear()
        self._drum_mod_slots.clear()
        self._composition_section_key = None
        self._composition_context = None
        self.app.set_message("STOP")

    @_transport_locked
    def all_notes_off(self):
        """Release notes owned by Auricle without affecting other MIDI clients."""
        # Do not broadcast CC123 here: an output port may be shared with a DAW,
        # another sequencer, or hardware.  STOP must only release Auricle's
        # own notes.  A separate explicit panic action can use CC123 if needed.
        self._cancel_articulations()
        self._release_notes(lambda _due, _port, _note, _channel, _owner_id: True)
        self._record_piano(action="cut")

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
        for item in removed:
            self._articulation_note_beats.pop(id(item), None)
        released_keys = set()
        for _due, port, note, channel, owner_id in removed:
            self.expression_runtime.note_released(owner_id, note)
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
                self._monitor(None, "", message, port=port)
            except Exception:
                pass

    def _release_port_notes(self, port: Any):
        """Release all Auricle claims on a port before that port is closed."""
        self._cancel_articulations(port=port)
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
        return self.app.engine.clock.seconds_for_beats(
            self.app.engine.sequence_step_beats(block), self.app.project.tempo
        )

    def _note_duration(self, block: Block, interval: float, event: dict[str, float]) -> float:
        # Gate is a musical duration multiplier, not a scheduler tick.
        # 0.05 = very short staccato, 1.0 = full interval, >1 = legato/overlap.
        duration_beats = event.get("duration_beats")
        if duration_beats is not None:
            return max(.001 if event.get("_articulation") else .025, self.app.engine.clock.seconds_for_beats(
                max(0.0, float(duration_beats)), self.app.project.tempo
            ))
        gate = float(event.get("duration", block.parameters.get("gate", 0.78)))
        return max(0.025, interval * _clamp(gate, 0.05, 1.5))

    def _record_piano(self, **packet):
        """Capture worker time before Qt queues; diagnostics never affect MIDI."""
        callback = getattr(self.app, "record_piano_event", None)
        if callback is None:
            return
        try:
            packet.setdefault("timestamp", time.monotonic())
            packet.setdefault("beat", clock_beat_at(self.app.engine.clock, packet["timestamp"], self.app.project.tempo))
            packet["project_token"] = id(self.app.project)
            callback(packet)
        except Exception:
            pass

    def _monitor(self, block: Optional[Block], port_name: str, message: Any, *, port=None, event=None):
        """Observe successful wire messages independently of the Monitor toggle."""
        if message.type in ("note_on", "note_off"):
            event = event or {}
            self._record_piano(action="on" if message.type == "note_on" and message.velocity > 0 else "off",
                owner_id=getattr(block, "id", None), port=port_name, port_key=id(port) if port is not None else port_name,
                note=message.note, velocity=message.velocity / 127., channel=message.channel,
                kind=event.get("_articulation", "note"),
                source_beat=event.get("_source_beat", event.get("beat", self.app.engine.clock.position_beats)),
                scheduled_beat=event.get("beat", self.app.engine.clock.position_beats))
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
            self._cancel_articulations(owners=hats - {block.id})
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

    def _observe_parameter_event(self, block, before, after, beat):
        """Bounded, non-persistent feedback for the event actually dispatched."""
        engine = self.app.engine
        context_at = getattr(engine.composition_runtime, "context_at", None)
        context = context_at(beat) if context_at is not None else None
        index = 0 if block.mode == "LIVE" else int(getattr(engine, "source_positions", {}).get(block.id, 0))
        pitch = getattr(block, "outputs", {}).get("pitch", ())
        block._parameter_feedback_event = {
            "beat": float(beat),
            "section": (context["section_id"], context["cycle"]) if context is not None else None,
            "input": {key: float(before.get(key, default)) for key, default in
                      (("velocity", .8), ("duration", 1.), ("pitch", 0.))},
            "output": None if after is None else {key: float(after.get(key, default)) for key, default in
                      (("velocity", .8), ("duration", 1.), ("pitch", 0.))},
            "reference_pitch": float(pitch[index % len(pitch)]) if pitch else float(before.get("pitch", 0.)),
        }

    def _dispatch_event(self, block, event, port, interval, beat=None):
        """One accepted-event path for SEQ, LIVE, motifs and Drum Voices."""
        engine = self.app.engine
        parent = engine.drum_parent_for(block)
        if block.muted or (parent is not None and parent.muted):
            return None
        beat = engine.clock.position_beats if beat is None else float(beat)
        before = dict(event)
        event = engine.drum_bus_event(block, event)
        if event is None:
            self._observe_parameter_event(block, before, None, beat)
            return None
        event = dict(event)
        event_class, importance = engine.event_class_info(
            block, beat, event.get("_composition_slot"), event
        )
        event.setdefault("event_class", event_class)
        event.setdefault("importance", importance)
        # Evaluate section gates before Dialogue can capture this event, then
        # apply the remaining section transforms after Dialogue's pitch shaping.
        if (engine.composition_runtime.enabled()
                and not engine.composition_event_allowed(block, beat, event.get("_composition_slot"), event)):
            self._observe_parameter_event(block, before, None, beat)
            return None
        event = engine.place_register_event(block, event, beat)
        if event is not None and "pitch" in event:
            # Register placement belongs to Center feedback. A later Dialogue
            # pitch delta must not make the manual Transpose needle mirror it.
            before["pitch"] = event["pitch"]
        event = engine.dialogue_event(block, event, beat)
        event = engine.apply_composition_event(block, event, beat, gate_checked=True)
        self._observe_parameter_event(block, before, event, beat)
        if event is None:
            return None
        if float(event.get("velocity", .8)) <= 0 or float(event.get("duration", 1)) <= 0:
            return None
        if event is None:
            return None
        interval_beats = self.app.engine.clock.beats_for_seconds(interval, self.app.project.tempo)
        musical_event = MusicalEvent.from_mapping(
            event,
            beat=beat,
            interval_beats=interval_beats,
            source_id=block.id,
            role=block.block_type,
            channel=getattr(block, "midi_channel", None),
            port=self._resolved_port_name(block),
            recompute_duration=True,
        )
        event = musical_event.to_mapping()
        if self._articulation_queue:
            self._cancel_articulations(owners={block.id})
        if supports_strum(block) and block.parameters.get("strum_probability", 0):
            source_grid = MusicalGrid(engine.sequence_step_beats(block, live=block.mode == "LIVE"))
            hits = strum_hits(musical_event, block.parameters, self.app.project.seed,
                              lambda pitch: midi_note_for(self.app.project, block, pitch),
                              source_step=source_grid.slot_at(beat, "floor"))
            if hits is not None:
                self._schedule_strum(block, event, hits, port, interval)
                return event if hits else None
        if supports_articulation(block) and (block.parameters.get("drum_ratchet_probability", 0)
                                             or block.parameters.get("drum_flam_probability", 0)):
            hits = articulate(musical_event, block.parameters, self.app.project.seed)
            if len(hits) > 1 or (hits and hits[0].offset > 0):
                self._schedule_articulation(block, event, hits, port, interval)
                return event
        self._emit_accepted_event(block, event, port, interval)
        return event

    def _emit_accepted_event(self, block, event, port, interval):
        try:
            self.app.record_generated_event(block, event)
        except Exception:
            pass
        if port is not None:
            self._send_event(block, event, port, interval)
        elif getattr(self.app, "record_piano_event", None) is not None:
            # No physical output: retain accepted generated sub-hits, explicitly
            # labelled as generated rather than mixed into the MIDI wire log.
            stamp = time.monotonic()
            beat = clock_beat_at(self.app.engine.clock, stamp, self.app.project.tempo)
            duration = self._event_duration(block, interval, event)
            if event.get("_articulation") == "strum":
                duration = min(duration, self.app.engine.clock.seconds_for_beats(
                    max(0., event["_articulation_end_beat"] - beat), self.app.project.tempo))
            pitches = event.get("pitches") or [event.get("pitch", 0.)]
            try:
                channel = int(_clamp(int(block.midi_channel) - 1, 0, 15))
            except (TypeError, ValueError):
                channel = 0
            for pitch in pitches:
                self._record_piano(action="on", timestamp=stamp, beat=beat, owner_id=block.id,
                    port="", port_key=("generated", block.id), channel=channel,
                    note=midi_note_for(self.app.project, block, pitch),
                    velocity=int(_clamp(int(127 * event.get("velocity", .8)), 1, 127)) / 127.,
                    kind=event.get("_articulation", "note"), stream="generated",
                    source_beat=event.get("_source_beat", event.get("beat", beat)),
                    scheduled_beat=event.get("beat", beat), end=stamp + duration,
                    end_beat=beat + self.app.engine.clock.beats_for_seconds(duration, self.app.project.tempo))

    def _articulation_context(self, beat):
        context = self.app.engine.composition_runtime.context_at(beat)
        return (context["cycle"], context["section_id"]) if context is not None else None

    def _schedule_articulation(self, block, event, hits, port, interval):
        origin = self.app.engine.clock.position_beats
        expires = origin + event["interval_beats"]
        context = self._articulation_context(event["beat"])
        route = (self._resolved_port_name(block), self._midi_channel(block),
                 midi_note_for(self.app.project, block, event.get("pitch", 0.)))
        for hit in hits:
            part = dict(event, beat=event["beat"] + hit.offset,
                        duration_beats=hit.duration, velocity=hit.velocity,
                        _articulation=hit.kind, _source_beat=event["beat"])
            if hit.offset <= 0:
                self._emit_accepted_event(block, part, port, interval)
                continue
            if len(self._articulation_queue) >= 4096:
                break
            self._articulation_serial += 1
            pending = _PendingArticulation(block, part, port, expires, context, route, block.mode, block.block_type)
            heapq.heappush(self._articulation_queue,
                           (origin + hit.offset, self._articulation_serial, pending))

    def _schedule_strum(self, block, event, hits, port, interval):
        origin = self.app.engine.clock.position_beats
        expires = origin + min(event["interval_beats"], event["duration_beats"])
        context = self._articulation_context(event["beat"])
        for hit in hits:
            part = dict(event, pitch=hit.pitch, beat=event["beat"] + hit.offset,
                        duration_beats=hit.duration, velocity=hit.velocity,
                        _articulation="strum", _source_beat=event["beat"],
                        _articulation_end_beat=origin + hit.offset + hit.duration)
            part.pop("pitches", None)  # Each scheduled event owns exactly one note.
            for key in ("harmony_remaining_beats", "dialogue_remaining_beats"):
                if key in part:
                    try:
                        remaining = float(part[key]) - hit.offset
                    except (TypeError, ValueError, OverflowError):
                        part.pop(key)
                    else:
                        if math.isfinite(remaining):
                            part[key] = max(0., remaining)
                        else:
                            part.pop(key)
            if hit.offset <= 0:
                self._emit_accepted_event(block, part, port, interval)
                continue
            if len(self._articulation_queue) >= 4096:
                break
            route = (self._resolved_port_name(block), self._midi_channel(block),
                     midi_note_for(self.app.project, block, hit.pitch))
            pending = _PendingArticulation(block, part, port, expires, context, route, block.mode, block.block_type)
            self._articulation_serial += 1
            heapq.heappush(self._articulation_queue,
                           (origin + hit.offset, self._articulation_serial, pending))

    def _cancel_articulations(self, owners=None, port=None):
        if not self._articulation_queue:
            return
        if owners is None and port is None:
            self._articulation_queue.clear()
            return
        self._articulation_queue[:] = [item for item in self._articulation_queue
                                      if not ((owners is not None and item[2].owner.id in owners)
                                              or (port is not None and item[2].port is port))]
        heapq.heapify(self._articulation_queue)

    def _flush_articulations(self):
        if not self._articulation_queue:
            return
        engine = self.app.engine
        beat = engine.clock.position_beats
        present = {id(block) for block in self._playable_blocks()}
        current_context = self._articulation_context(beat)
        # At most one overdue sub-hit per voice after a worker stall.
        due = {}
        strums = []
        while self._articulation_queue and self._articulation_queue[0][0] <= beat + 1e-8:
            item = heapq.heappop(self._articulation_queue)
            if item[2].event["_articulation"] == "strum":
                # Distinct chord tones are not repeated drum triggers. Keep
                # still-valid tones together if one worker tick covers several.
                strums.append(item)
                continue
            previous = due.get(item[2].owner.id)
            # Keep the principal after a grace, even when a very tight repeat
            # grid puts several sub-hits inside one worker tick.
            if previous is None or previous[2].event["_articulation"] != "main":
                due[item[2].owner.id] = item
        for _due, _serial, pending in sorted([*due.values(), *strums]):
            block, event, port = pending.owner, pending.event, pending.port
            parent = engine.drum_parent_for(block)
            if (id(block) not in present or not (supports_articulation(block) or supports_strum(block))
                    or block.muted or (parent is not None and parent.muted)
                    or pending.mode != block.mode or beat >= pending.expires - 1e-8
                    or pending.context != current_context or pending.block_type != block.block_type):
                continue
            current_route = (self._resolved_port_name(block), self._midi_channel(block),
                             midi_note_for(self.app.project, block, event.get("pitch", 0.)))
            if pending.route != current_route or self.outputs.get(pending.route[0]) is not port:
                continue
            if not engine.dialogue_runtime.can_play(block, beat):
                continue
            if pending.context is not None:
                runtime = engine.composition_runtime
                section = runtime.context_at(beat)["section"]
                if not all(runtime.block_settings(section, owner.id)["enabled"]
                           for owner in (block, parent) if owner is not None):
                    continue
            if event["_articulation"] == "ratchet" and articulation_values(block.parameters)["drum_ratchet_probability"] <= 0:
                continue
            if event["_articulation"] == "strum":
                remaining = event["_articulation_end_beat"] - beat
                if remaining <= 1e-8:
                    continue
                event = dict(event, duration_beats=remaining)
            try:
                self._emit_accepted_event(block, event, port,
                                          engine.clock.seconds_for_beats(event["interval_beats"], self.app.project.tempo))
            except Exception as exc:
                self._cancel_articulations(owners={block.id})
                self._log_error(f"articulation voice={block.id}", exc)

    def _event_duration(self, block, interval, event):
        duration = self._note_duration(block, interval, event)
        runtime = getattr(self.app.engine, "composition_runtime", None)
        if runtime is not None and runtime.enabled() and runtime.ending() == "stop":
            remaining = max(0., runtime.total_beats() - self.app.engine.clock.position_beats)
            duration = min(duration, self.app.engine.clock.seconds_for_beats(
                remaining, self.app.project.tempo))
        if "harmony_remaining_beats" in event:
            duration = min(duration, max(.005, self.app.engine.clock.seconds_for_beats(
                float(event["harmony_remaining_beats"]), self.app.project.tempo)))
        if "dialogue_remaining_beats" in event:
            duration = min(duration, max(.005, self.app.engine.clock.seconds_for_beats(
                float(event["dialogue_remaining_beats"]), self.app.project.tempo)))
        return duration

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
                        self._monitor(block, self._resolved_port_name(block), old_message, port=old_port)
                    except Exception:
                        pass
        self.active_notes = remaining
        for item in replaced:
            self._articulation_note_beats.pop(id(item), None)

        try:
            port.send(message)
            resolved_port = self._resolved_port_name(block)
            self._monitor(block, resolved_port, message, port=port, event=event)
        except Exception as exc:
            self._log_error(f"note_on block={block.id} channel={channel + 1} note={note}", exc)
            resolved_port = self._resolved_port_name(block)
            reopened = self._reopen_port(resolved_port) if resolved_port else None
            if reopened is None:
                raise
            reopened.send(message)
            self._monitor(block, resolved_port, message, port=reopened, event=event)
            port = reopened

        duration = self._event_duration(block, interval, event)
        due = time.monotonic() + duration
        end_beat = None
        if event.get("_articulation"):
            clock = self.app.engine.clock
            end_beat = clock.position_beats + clock.beats_for_seconds(duration, self.app.project.tempo)
            if event["_articulation"] == "strum":
                # Anchor the release to the clock snapshot, not the completion
                # of each MIDI send; a slower port cannot stagger a shared end.
                end_beat = min(end_beat, event["_articulation_end_beat"])
                anchor = getattr(clock, "_last_time", None)
                if clock.running and anchor is not None:
                    due = min(due, anchor + clock.seconds_for_beats(
                        end_beat - clock.position_beats, self.app.project.tempo))
        item = (due, port, note, channel, block.id)
        self.active_notes.append(item)
        if end_beat is not None:
            self._articulation_note_beats[id(item)] = end_beat

    def _release_due(self, now: float):
        due_items = [item for item in self.active_notes if now >= item[0]]
        if not due_items:
            return
        due_ids = {id(item) for item in due_items}
        remaining = [item for item in self.active_notes if id(item) not in due_ids]
        self.active_notes = remaining
        for item in due_items:
            self._articulation_note_beats.pop(id(item), None)
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
                self._monitor(None, "", message, port=port)
            except Exception:
                pass

    def _release_block_notes(self, block_id: int):
        """Immediately release all notes currently owned by one block."""
        owned = {int(block_id)}
        parent = next((block for block in self.app.project.blocks if block.id == int(block_id)), None)
        if parent is not None and getattr(parent, "drum_voices", None):
            owned.update(int(voice.id) for voice in parent.drum_voices)
        self._cancel_articulations(owners=owned)
        self._release_notes(lambda _due, _port, _note, _channel, owner_id: owner_id in owned)
        self._record_piano(action="cut", owners=tuple(owned))

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
        """Schedule relation sources before destinations; cache until topology changes."""
        engine = self.app.engine
        blocks = list(self._playable_blocks())
        routes = engine.relation_runtime.routes()
        # Modes and selected built-in sources affect scheduling order. Numeric
        # stream values and ordinary performance parameters do not.
        block_signature = tuple(
            (int(block.id), id(block), str(block.mode), str(block.block_type).upper(),
             int(engine.drum_parent_for(block).id) if engine.drum_parent_for(block) is not None else None,
             block.parameters.get("relation_drum_source"), block.parameters.get("relation_chord_source"))
            for block in blocks
        )
        route_signature = tuple(
            (int(getattr(route, "id", 0)), relation_endpoint_id(route, "source"),
             relation_endpoint_id(route, "destination"), int(getattr(route, "delay", 0)))
            for route in routes
        )
        signature = (block_signature, route_signature)
        if signature == self._ordered_tick_signature and self._ordered_tick_signature is not None:
            return list(self._ordered_tick_cache)

        by_id = {block.id: block for block in blocks}
        dependencies = {block.id: set() for block in blocks}

        def source_owners(source):
            voices = getattr(source, "drum_voices", None)
            return [voice.id for voice in voices] if voices else [source.id]

        for destination in blocks:
            parent = engine.drum_parent_for(destination)
            targets = {destination.id} | ({parent.id} if parent is not None else set())
            built_in = engine.role_relation_source(destination)
            if built_in is not None:
                dependencies[destination.id].update(source_owners(built_in))
            for route in routes:
                if relation_endpoint_id(route, "destination") not in targets or int(getattr(route, "delay", 0)) > 0:
                    continue
                source_id = relation_endpoint_id(route, "source")
                if source_id in by_id:
                    dependencies[destination.id].add(source_id)
                    continue
                source = engine.find_block(route.source_block)
                if source is not None:
                    dependencies[destination.id].update(source_owners(source))

        ordered, visiting, visited = [], set(), set()
        def visit(bid):
            if bid in visited or bid in visiting:
                return
            visiting.add(bid)
            for source in sorted(dependencies[bid]):
                if source in by_id:
                    visit(source)
            visiting.remove(bid)
            visited.add(bid)
            ordered.append(by_id[bid])

        for block in sorted(blocks, key=lambda item: (item.mode != "SEQ", item.id)):
            visit(block.id)
        self._ordered_tick_signature = signature
        self._ordered_tick_cache = tuple(ordered)
        return list(ordered)

    def _seq_event(self, block: Block, now: float, port: Any, absolute_slot=None):
        # Mute is an output gate. Keep the sequencer clock advancing, but
        # never allow direct calls to this low-level sender to bypass mute.
        # This protects both the transport loop and tests/tools that invoke
        # the event generator directly.
        engine = self.app.engine
        engine.relation_runtime.advance_parent(block)
        step_beats = engine.sequence_step_beats(block)
        event_slot = (int(absolute_slot) if absolute_slot is not None else
                      int(self.step_count.get(block.id, self.seq_index.get(block.id, 0))))
        event_grid = MusicalGrid(step_beats)
        event_beat = event_grid.beat_at(event_slot)
        # A cached SEQ loop belongs to a particular musical-time window.
        # Rebuild it once on entering the next cycle while Director is active;
        # otherwise LIVE advances its decisions but SEQ repeats window zero.
        if engine.director.phrase.running and block.outputs.get("rhythm"):
            origin = engine.sequence_origin(block, len(block.outputs["rhythm"]), event_beat)
            if engine._seq_director_origins.get(block.id) != origin:
                engine.regenerate(block, motif_beat=event_beat)
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
            if engine.event_gate_allowed(block, event_beat, slot=slot):
                event_beat = event_grid.beat_at(event_slot)
                kit_plan = engine.kit_plan(block, event_beat)
                composition_slot = int((kit_plan.start_slot if kit_plan is not None else 0) + i)
                event_class, importance = engine.event_class_info(block, event_beat, slot)
                musical_event = MusicalEvent.from_outputs(
                    block.outputs, i,
                    beat=event_beat,
                    interval_beats=step_beats,
                    source_id=block.id,
                    role=block.block_type,
                    channel=getattr(block, "midi_channel", None),
                    port=self._resolved_port_name(block),
                    composition_slot=composition_slot,
                    event_class=event_class,
                    importance=importance,
                )
                if musical_event is not None:
                    event = musical_event.to_mapping()
                    root_pitch = event["pitch"]
                    if block.block_type in ("CHORD", "PAD"):
                        event["pitches"] = engine._chord_pitches(block, root_pitch)
                    event = engine.harmonize_event(block, event, event_beat)
                    event = self._dispatch_event(block, event, port, self._block_seq_interval(block), event_beat)
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
        beat = MusicalGrid(step).beat_at(slot)
        return self._swung_time(block, beat, slot, step) + offset * step

    def _tick_kit_voice(self, block, now, port):
        """One shared sixteenth grid, including rests and mode changes."""
        engine = self.app.engine
        beat = engine.clock.position_beats
        schedule = self._kit_schedule.get(block.id)
        grid = MusicalGrid(STEP_BEATS)
        if schedule is None:
            slot = max(0, grid.slot_at(beat, "ceil"))
            schedule = {"slot": slot, "due": self._motif_due_beat(block, slot, STEP_BEATS), "mode": None}
            self._kit_schedule[block.id] = schedule
        slot = schedule["slot"]
        if beat >= grid.beat_at(slot + 1) - 1e-8:
            slot = max(slot, grid.slot_at(beat, "floor"))
            schedule["slot"] = slot
            schedule["due"] = self._motif_due_beat(block, slot, STEP_BEATS)
        if beat + 1e-8 < schedule["due"]:
            return
        scheduled_beat = grid.beat_at(slot)
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
            if event is not None and engine.event_gate_allowed(block, scheduled_beat, slot=slot, event=event):
                accepted_event = self._dispatch_event(block, event, port, self._block_seq_interval(block), scheduled_beat)
        self._observe_kit_output(block, slot, accepted_event)
        parent = engine.drum_parent_for(block)
        engine._aggregate_drum_outputs(parent)
        engine.apply_relations()

    def _tick_motif(self, block, motif, now, port):
        """Schedule motifs and Euclidean slots on the absolute beat clock.

        Rests and muted events consume slots too. Late ticks skip old slots
        instead of playing a burst, and parameter regeneration owns no phase.
        """
        engine = self.app.engine
        beat = engine.clock.position_beats
        step = engine.sequence_step_beats(block, live=block.mode == "LIVE")
        key = (motif.id if motif is not None else "euclidean", step)
        schedule = self._motif_schedule.get(block.id)
        grid = MusicalGrid(step)
        if schedule is None or schedule["key"] != key:
            slot = max(0, grid.slot_at(beat, "ceil"))
            schedule = {"key": key, "slot": slot, "due": self._motif_due_beat(block, slot, step), "mode": None}
            self._motif_schedule[block.id] = schedule
        slot = schedule["slot"]
        if beat >= grid.beat_at(slot + 1) - 1e-8:
            slot = max(slot, grid.slot_at(beat, "floor"))
            schedule["slot"] = slot
            schedule["due"] = self._motif_due_beat(block, slot, step)
        if beat + 1e-8 < schedule["due"]:
            return
        # Resolve at the scheduled slot, including early humanized onsets.
        # SEQ must rebuild on a new variant just as LIVE reads the new material.
        scheduled_beat = grid.beat_at(slot)
        variant = engine.motif_variant(block, beat=scheduled_beat) if motif is not None else None
        token = variant.token if variant is not None else None
        if block.mode == "SEQ" and (schedule["mode"] != "SEQ" or
                engine._seq_motifs.get(block.id) is not motif or
                engine._seq_motif_tokens.get(block.id) != token):
            engine.regenerate(block, motif_beat=scheduled_beat)
        schedule["mode"] = block.mode
        schedule["slot"] = slot + 1
        schedule["due"] = self._motif_due_beat(block, slot + 1, step)
        interval = engine.clock.seconds_for_beats(step, self.app.project.tempo)
        if block.mode == "SEQ":
            self.seq_index[block.id] = slot % (motif.steps if motif is not None else max(1, int(self.app.project.length)))
            self._seq_event(block, now, port, absolute_slot=slot)
        else:
            event = engine.live_event(block, beat=scheduled_beat)
            if event is not None and engine.event_gate_allowed(block, scheduled_beat, slot=slot, event=event):
                self._dispatch_event(block, event, port, interval, scheduled_beat)
        parent = engine.drum_parent_for(block)
        if parent is not None:
            engine._aggregate_drum_outputs(parent)
            engine.apply_relations()

    def _clock_port_items(self):
        """Return unique physical ports selected for global MIDI Clock."""
        sync = normalize_midi_sync(getattr(self.app.project, "midi_sync", {}))
        if sync["clock_port"] == "*":
            items = list(self.outputs.items())
        else:
            port = self.outputs.get(sync["clock_port"])
            items = [(sync["clock_port"], port)] if port is not None else []
        unique = {}
        for name, port in items:
            if port is not None:
                unique.setdefault(id(port), (name, port))
        return list(unique.values())

    def _send_clock_message(self, port_name, port, message, block=None):
        try:
            port.send(message)
            self._monitor(block, port_name, message)
            return True
        except Exception as exc:
            self._log_error(f"MIDI sync {message.type} port={port_name}", exc)
            return False

    def _send_song_position(self, position, ports=None):
        sync = normalize_midi_sync(getattr(self.app.project, "midi_sync", {}))
        if not sync["song_position_pointer"]:
            return
        midi_position = int(max(0, min(16383, round(float(position) * 4.0))))
        for name, port in (ports if ports is not None else self._clock_port_items()):
            self._send_clock_message(name, port, mido.Message("songpos", pos=midi_position))

    def _start_midi_clock(self, position, now=None):
        sync = normalize_midi_sync(getattr(self.app.project, "midi_sync", {}))
        ports = self._clock_port_items()
        self._clock_active_ports = {id(port): (name, port) for name, port in ports}
        now = time.monotonic() if now is None else float(now)
        if sync["transport_messages"]:
            if float(position) > 1e-9:
                self._send_song_position(position, ports)
                message = mido.Message("continue")
            else:
                message = mido.Message("start")
            for name, port in ports:
                self._send_clock_message(name, port, message)
        elif (sync["clock_out"] or sync["transport_messages"]) and sync["song_position_pointer"] and float(position) > 1e-9:
            self._send_song_position(position, ports)
        if sync["clock_out"]:
            self._clock_interval = 60.0 / max(1.0, float(self.app.project.tempo)) / 24.0
            self._clock_next_due = now + self._clock_interval
        else:
            self._clock_next_due = None
            self._clock_interval = None

    def _stop_midi_clock(self):
        sync = normalize_midi_sync(getattr(self.app.project, "midi_sync", {}))
        if sync["transport_messages"]:
            for name, port in list(self._clock_active_ports.values()):
                self._send_clock_message(name, port, mido.Message("stop"))
        self._clock_next_due = None
        self._clock_interval = None
        self._clock_active_ports.clear()

    def _seek_midi_clock(self, position, now=None, *, running=False):
        sync = normalize_midi_sync(getattr(self.app.project, "midi_sync", {}))
        ports = self._clock_port_items()
        if (sync["clock_out"] or sync["transport_messages"]) and sync["song_position_pointer"]:
            self._send_song_position(position, ports)
        if running and sync["transport_messages"]:
            for name, port in ports:
                self._send_clock_message(name, port, mido.Message("continue"))
        if running and sync["clock_out"]:
            now = time.monotonic() if now is None else float(now)
            self._clock_interval = 60.0 / max(1.0, float(self.app.project.tempo)) / 24.0
            self._clock_next_due = now + self._clock_interval
        elif not running:
            self._clock_next_due = None
            self._clock_interval = None

    def _tick_midi_clock(self, now):
        sync = normalize_midi_sync(getattr(self.app.project, "midi_sync", {}))
        if not self.running or not sync["clock_out"]:
            return
        ports = self._clock_port_items()
        if not ports:
            return
        interval = 60.0 / max(1.0, float(self.app.project.tempo)) / 24.0
        if self._clock_next_due is None or self._clock_interval is None:
            self._clock_interval = interval
            self._clock_next_due = float(now) + interval
            return
        if abs(interval - self._clock_interval) > 1e-9:
            # Re-anchor the next pulse immediately when project BPM changes;
            # do not let one pulse retain the old tempo interval.
            self._clock_interval = interval
            self._clock_next_due = float(now) + interval
            return
        if now + 1e-6 < self._clock_next_due:
            return
        message = mido.Message("clock")
        for name, port in ports:
            self._send_clock_message(name, port, message)
        lateness = max(0.0, float(now) - self._clock_next_due)
        # Do not burst stale clocks after a scheduler stall. Resume on the next
        # pulse interval; slaves remain locked without receiving a clock burst.
        self._clock_next_due = (float(now) + interval if lateness > interval * 0.75
                                else self._clock_next_due + interval)

    def set_midi_sync_config(self, config):
        """Apply global MIDI sync settings safely while stopped or playing."""
        with self._transport_lock:
            was_running = bool(self.running)
            position = float(self.app.engine.clock.position_beats)
            if was_running:
                self._stop_midi_clock()
            self.app.project.midi_sync = normalize_midi_sync(config)
            self.refresh_ports()
            if was_running:
                self._start_midi_clock(position)

    def _expression_config(self, block, context):
        parent = self.app.engine.drum_parent_for(block)
        section = context.get("section") if context is not None else None
        return entity_expression_config(block, parent=parent, section=section)

    def _send_expression_command(self, block, port_name, port, command):
        channel = self._midi_channel(block)
        kind = command.get("type")
        if kind == "control_change":
            message = mido.Message("control_change", channel=channel,
                                   control=int(command["control"]), value=int(command["value"]))
        elif kind == "pitchwheel":
            semitones = int(command.get("range_semitones", 2))
            route = (id(port), channel)
            if self._pitch_bend_ranges.get(route) != semitones:
                # RPN 0,0 sets Pitch Bend Sensitivity on the receiving channel.
                for control, value in ((101, 0), (100, 0), (6, semitones), (38, 0), (101, 127), (100, 127)):
                    rpn = mido.Message("control_change", channel=channel, control=control, value=value)
                    if not self._send_clock_message(port_name, port, rpn, block=block):
                        return
                self._pitch_bend_ranges[route] = semitones
            message = mido.Message("pitchwheel", channel=channel,
                                   pitch=int(max(-8192, min(8191, command["pitch"]))))
        elif kind == "aftertouch":
            message = mido.Message("aftertouch", channel=channel,
                                   value=int(max(0, min(127, command["value"]))))
        elif kind == "polytouch":
            message = mido.Message("polytouch", channel=channel,
                                   note=int(max(0, min(127, command["note"]))),
                                   value=int(max(0, min(127, command["value"]))))
        else:
            return
        if self._send_clock_message(port_name, port, message, block=block):
            route = (id(port), channel)
            state = self._expression_routes.setdefault(route, {"port": port, "name": port_name, "types": set()})
            state["types"].add(kind)

    @staticmethod
    def _expression_types(config):
        types = set()
        controllers = {}
        for lane in config.get("cc_lanes", ()):
            if lane.get("enabled"):
                controllers[int(lane.get("controller", 0))] = int(lane.get("min", 0))
        if controllers:
            types.add("control_change")
        if config.get("pitch_bend", {}).get("enabled"):
            types.add("pitchwheel")
        pressure = config.get("aftertouch", {})
        if pressure.get("enabled"):
            types.add("polytouch" if pressure.get("mode") == "polyphonic" else "aftertouch")
        return types, controllers

    def _release_expression_types(self, owner_id, previous, removed_types, removed_controllers=()):
        route = previous["route"]
        others = [item for bid, item in self._expression_owner_state.items()
                  if bid != int(owner_id) and item["route"] == route]
        still_types = set().union(*(item["types"] for item in others)) if others else set()
        port, name, channel = previous["port"], previous["name"], previous["channel"]
        state = self._expression_routes.get(route)
        still_controllers = set().union(*(set(item.get("controllers", {})) for item in others)) if others else set()
        for controller in set(removed_controllers):
            if controller not in still_controllers:
                reset_value = int(previous.get("controllers", {}).get(controller, 0))
                self._send_clock_message(name, port, mido.Message("control_change", channel=channel,
                                                                   control=int(controller), value=max(0, min(127, reset_value))))
        for kind in set(removed_types):
            if kind in still_types:
                continue
            if kind == "pitchwheel":
                self._send_clock_message(name, port, mido.Message("pitchwheel", channel=channel, pitch=0))
            elif kind == "aftertouch":
                self._send_clock_message(name, port, mido.Message("aftertouch", channel=channel, value=0))
            elif kind == "polytouch":
                notes = sorted({note for _due, active_port, note, active_channel, owner in self.active_notes
                                if active_port is port and active_channel == channel and owner == int(owner_id)})
                for note in notes:
                    self._send_clock_message(name, port, mido.Message("polytouch", channel=channel, note=note, value=0))
            if state is not None:
                state["types"].discard(kind)
        remaining_types = set(previous["types"]) - set(removed_types)
        if remaining_types:
            previous["types"] = remaining_types
            self._expression_owner_state[int(owner_id)] = previous
        else:
            self._expression_owner_state.pop(int(owner_id), None)
        if state is not None and not state["types"]:
            self._expression_routes.pop(route, None)

    def _release_expression_owner(self, owner_id):
        previous = self._expression_owner_state.get(int(owner_id))
        if previous:
            self._release_expression_types(owner_id, previous, set(previous["types"]),
                                           set(previous.get("controllers", {})))

    def _tick_midi_expression(self, now):
        engine = self.app.engine
        beat = float(engine.clock.position_beats)
        runtime = engine.composition_runtime
        context = runtime.context_at(beat)
        section = context.get("section") if context is not None else None
        playable_blocks = list(self._playable_blocks())
        seen_owners = set()
        active_notes_by_owner = {}
        for _due, active_port, note, _channel, owner in self.active_notes:
            active_notes_by_owner.setdefault((id(active_port), int(owner)), []).append(int(note))
        for block in playable_blocks:
            owner_id = int(block.id)
            seen_owners.add(owner_id)
            parent = engine.drum_parent_for(block)
            section_block_settings = section.get("blocks", {}).get(str(owner_id), {}) if section is not None else {}
            if (block.muted or (parent is not None and parent.muted)
                    or (section is not None and not bool(section_block_settings.get("enabled", True)))):
                self._release_expression_owner(owner_id)
                continue
            port_name = self._resolved_port_name(block)
            port = self.outputs.get(port_name) if port_name else None
            if port is None:
                self._release_expression_owner(owner_id)
                continue
            config = self._expression_config(block, context)
            types, controllers = self._expression_types(config)
            if not types:
                self._release_expression_owner(owner_id)
                continue
            channel = self._midi_channel(block)
            route = (id(port), channel)
            previous = self._expression_owner_state.get(owner_id)
            if previous is not None:
                route_changed = previous["route"] != route
                removed_types = (set(previous["types"]) if route_changed
                                 else set(previous["types"]) - set(types))
                removed_controllers = (set(previous.get("controllers", {})) if route_changed
                                       else set(previous.get("controllers", {})) - set(controllers))
                if removed_types or removed_controllers:
                    self._release_expression_types(owner_id, previous, removed_types, removed_controllers)
            self._expression_owner_state[owner_id] = {
                "route": route, "port": port, "name": port_name,
                "channel": channel, "types": set(types), "controllers": dict(controllers),
            }
            active_notes = active_notes_by_owner.get((id(port), owner_id), ())
            commands = self.expression_runtime.sample(owner_id, config, beat, context, active_notes, normalized=True)
            for command in commands:
                try:
                    self._send_expression_command(block, port_name, port, command)
                except Exception as exc:
                    self._log_error(f"MIDI expression block={block.id} {command.get('type')}", exc)
        # Removed blocks/voices can leave a non-neutral wheel or pressure value.
        for owner_id in list(self._expression_owner_state):
            if owner_id not in seen_owners:
                self._release_expression_owner(owner_id)

    def _reset_expression_port(self, port):
        """Neutralise expression on a port before its native handle is closed."""
        active = list(self.active_notes)
        for route, state in list(self._expression_routes.items()):
            if state.get("port") is not port:
                continue
            channel = route[1]
            name = state.get("name", "")
            kinds = state.get("types", set())
            if "pitchwheel" in kinds:
                self._send_clock_message(name, port, mido.Message("pitchwheel", channel=channel, pitch=0))
            if "aftertouch" in kinds:
                self._send_clock_message(name, port, mido.Message("aftertouch", channel=channel, value=0))
            if "polytouch" in kinds:
                notes = sorted({note for _due, active_port, note, active_channel, _owner in active
                                if active_port is port and active_channel == channel})
                for note in notes:
                    self._send_clock_message(name, port, mido.Message("polytouch", channel=channel, note=note, value=0))
            controllers = {}
            for owner_id, owner_state in self._expression_owner_state.items():
                if owner_state.get("route") == route:
                    controllers.update(owner_state.get("controllers", {}))
            for controller, reset_value in sorted(controllers.items()):
                self._send_clock_message(name, port, mido.Message("control_change", channel=channel,
                                                                   control=int(controller), value=int(reset_value)))
            self._expression_routes.pop(route, None)
            for owner_id, owner_state in list(self._expression_owner_state.items()):
                if owner_state.get("route") == route:
                    self._expression_owner_state.pop(owner_id, None)
        self.expression_runtime.reset()

    def _reset_expression(self):
        """Return channel pressure and pitch wheels to neutral on STOP."""
        active = list(self.active_notes)
        for (_port_id, channel), state in list(self._expression_routes.items()):
            port = state.get("port")
            name = state.get("name", "")
            kinds = state.get("types", set())
            if port is None:
                continue
            if "pitchwheel" in kinds:
                self._send_clock_message(name, port, mido.Message("pitchwheel", channel=channel, pitch=0))
            if "aftertouch" in kinds:
                self._send_clock_message(name, port, mido.Message("aftertouch", channel=channel, value=0))
            if "polytouch" in kinds:
                notes = sorted({note for _due, active_port, note, active_channel, _owner in active
                                if active_port is port and active_channel == channel})
                for note in notes:
                    self._send_clock_message(name, port, mido.Message("polytouch", channel=channel, note=note, value=0))
        self._expression_routes.clear()
        self._expression_owner_state.clear()
        self.expression_runtime.reset()

    def _sync_composition_section(self, beat):
        """Release sustained notes when a block becomes inactive in a new section."""
        runtime = getattr(self.app.engine, "composition_runtime", None)
        context = runtime.context_at(beat) if runtime is not None else None
        key = (context["cycle"], context["section_id"]) if context is not None else None
        if key == self._composition_section_key:
            return
        previous = self._composition_context
        if previous is not None:
            self._cancel_articulations()
            owners = {item[4] for item in self.active_notes if id(item) in self._articulation_note_beats}
            if owners:
                self._release_notes(lambda _due, _port, _note, _channel, owner: owner in owners)
        if context is not None:
            for block in self._playable_blocks():
                was_enabled = True
                if previous is not None:
                    was_enabled = runtime.block_settings(previous["section"], block.id)["enabled"]
                now_enabled = runtime.block_settings(context["section"], block.id)["enabled"]
                if was_enabled and not now_enabled:
                    self._release_block_notes(block.id)
        self._composition_section_key = key
        self._composition_context = context

    @_transport_locked
    def tick(self):
        self._drain_gui_commands()
        if not self.running:
            return
        now = time.monotonic()
        engine = self.app.engine
        self._advance_musical_clock(now)
        self._tick_midi_clock(now)
        if engine.composition_runtime.finished(engine.clock.position_beats):
            self.stop(advance=False)
            self.app.set_message("COMPOSITION · finished")
            return
        self._sync_composition_section(engine.clock.position_beats)
        # Send continuous controller and pitch-bend values before Note On at
        # this scheduler instant. Polyphonic Aftertouch is deferred until the
        # end of the tick, when newly-started notes are present in active_notes.
        self._tick_midi_expression(now)
        engine.relation_runtime.begin_tick()
        # Apply only values queued during previous ticks. Any modulation
        # generated below is therefore guaranteed at least one tick late.
        engine.apply_pending_parameter_modulations()
        self._release_due(now)
        self._flush_articulations()
        interval = self.seq_interval
        master_grid = MusicalGrid(0.25)
        self._master_step = master_grid.slot_at(engine.clock.position_beats, "floor") + 1
        self._master_due = now + engine.clock.seconds_for_beats(
            master_grid.beat_at(self._master_step) - engine.clock.position_beats,
            self.app.project.tempo,
        )

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
                if motif is not None or block.algorithm == "Euclidean":
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
                        self._seq_event(block, now, port, absolute_slot=self.step_count.get(block.id, 0))
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
                            accepted = engine.event_gate_allowed(
                                block, engine.clock.position_beats,
                                slot=engine.source_positions.get(block.id), event=event,
                            )
                            live_interval = float(event.get("interval", 0.25))
                            if accepted:
                                self._dispatch_event(block, event, port, live_interval, engine.clock.position_beats)
                        else:
                            live_interval = engine._live_interval(block, engine._rng_for(block))
                        parent = engine.drum_parent_for(block)
                        if parent is not None:
                            engine._aggregate_drum_outputs(parent)
                            engine.apply_relations()
                        # Normal worker lateness must not accumulate as tempo
                        # drift. After a real stall, resume without a burst.
                        next_due = due + max(0.01, live_interval)
                        self.next_live[block.id] = next_due if next_due > now else now + max(0.01, live_interval)
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
        engine.relation_runtime.end_tick()
        self._tick_midi_expression(now)
