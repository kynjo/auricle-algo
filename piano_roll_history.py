"""Bounded, Qt-free history of emitted notes and deterministic buffer previews."""
from collections import OrderedDict, deque
from dataclasses import dataclass, replace
import math

from auricle_model import midi_note_for
from musical_events import MusicalEvent
from drum_articulation import articulate, supports_articulation
from strum import strum_hits, supports_strum


def clock_beat_at(clock, timestamp, tempo):
    """Read the send instant, including time spent inside a slow MIDI port."""
    beat = float(clock.position_beats)
    anchor = getattr(clock, '_last_time', None)
    if clock.running and anchor is not None:
        beat += max(0., float(timestamp) - float(anchor)) * float(tempo) / 60.
    return beat


@dataclass(frozen=True)
class PianoNote:
    timestamp: float
    note: int
    velocity: float
    owner_id: int
    port: str = ''
    channel: int = 0
    kind: str = 'note'
    beat: float = 0.
    source_beat: float = 0.
    scheduled_beat: float = 0.
    end: float | None = None
    end_beat: float | None = None
    stream: str = 'midi'


class PianoRollHistory:
    """The GUI owns this store. Worker packets contain immutable scalar data."""
    def __init__(self, per_owner=8192, total=32768):
        self.per_owner, self.total = max(1, per_owner), max(1, total)
        self.clear()

    def clear(self):
        self.notes = OrderedDict()
        self.owners = {}
        self.opened = {}
        self.open_keys = {}
        self.serial = 0
        self.has_run = False
        self.revision = 0
        self._snapshot_revision = -1
        self._snapshots = {}

    def _discard(self, identity):
        self.notes.pop(identity, None)
        key = self.open_keys.pop(identity, None)
        if key in self.opened:
            self.opened[key].discard(identity)
            if not self.opened[key]: del self.opened[key]

    def record(self, packet):
        action = packet.get('action')
        if action == 'reset':
            self.clear(); self.has_run = True
            return
        stamp, beat = float(packet['timestamp']), float(packet['beat'])
        if not math.isfinite(stamp) or not math.isfinite(beat): return
        if action == 'cut':
            owners = packet.get('owners')
            for identity, note in tuple(self.notes.items()):
                if note.stream == 'generated' and (owners is None or note.owner_id in owners) and (note.end is None or note.end > stamp):
                    self.notes[identity] = replace(note, end=max(note.timestamp, stamp), end_beat=max(note.beat, beat))
            self.revision += 1
            return
        key = (packet.get('port_key', packet.get('port', '')), int(packet.get('channel', 0)), int(packet['note']))
        if action == 'off':
            for identity in self.opened.pop(key, ()):
                self.open_keys.pop(identity, None)
                note = self.notes.get(identity)
                if note is not None:
                    self.notes[identity] = replace(note, end=max(note.timestamp, stamp), end_beat=max(note.beat, beat))
            self.revision += 1
            return
        if action != 'on' or packet.get('owner_id') is None: return
        owner = int(packet['owner_id'])
        note = PianoNote(stamp, max(0, min(127, int(packet['note']))),
                         max(0., min(1., float(packet['velocity']))), owner,
                         str(packet.get('port', '')), key[1], str(packet.get('kind', 'note')),
                         beat, float(packet.get('source_beat', beat)), float(packet.get('scheduled_beat', beat)),
                         packet.get('end'), packet.get('end_beat'), str(packet.get('stream', 'midi')))
        bucket = self.owners.setdefault(owner, deque())
        while len(bucket) >= self.per_owner:
            self._discard(bucket.popleft())
        while len(self.notes) >= self.total:
            identity = next(iter(self.notes)); old = self.notes[identity]
            self._discard(identity)
            old_bucket = self.owners[old.owner_id]
            while old_bucket and old_bucket[0] not in self.notes: old_bucket.popleft()
        self.serial += 1
        self.notes[self.serial] = note; bucket.append(self.serial)
        if note.end is None:
            self.opened.setdefault(key, set()).add(self.serial)
            self.open_keys[self.serial] = key
        self.has_run = True; self.revision += 1

    def snapshot(self, owner_ids):
        if self._snapshot_revision != self.revision:
            self._snapshots.clear(); self._snapshot_revision = self.revision
        key = tuple(dict.fromkeys(owner_ids))
        if key not in self._snapshots:
            notes = [self.notes[identity] for owner in key
                     for identity in self.owners.get(owner, ()) if identity in self.notes]
            if len(key) > 1: notes.sort(key=lambda note: note.timestamp)
            self._snapshots[key] = tuple(notes)
        return self._snapshots[key]


@dataclass(frozen=True)
class PreviewNote:
    step: float
    note: int
    duration: float
    velocity: float
    kind: str = 'note'


def preview_notes(project, block, engine=None, steps=16):
    """Read existing buffers only; never advance RNG, generators or automation.

    This is a buffer/articulation preview, not a prediction of future stochastic
    gates, Dialogue, Composition changes or transport humanization.
    """
    if block is None or project is None: return []
    voices = getattr(block, 'drum_voices', None) or [block]
    result = []
    for voice in voices:
        outputs = voice.outputs
        step = engine.sequence_step_beats(voice) if engine is not None else .25 / max(.25, float(voice.parameters.get('timing_rate', 1.)))
        if engine is not None and engine.coordinated_drum(voice) is not None: step = .25
        swing = float(voice.parameters.get('timing_swing', 0.))
        offset = float(voice.parameters.get('timing_offset', 0.))
        rhythm = outputs.get('rhythm', ())
        for index in range(min(len(rhythm), max(1, math.ceil(steps * .25 / step)))):
            beat = index * step
            event = MusicalEvent.from_outputs(outputs, index, beat=beat, interval_beats=step, source_id=voice.id)
            if event is None or event.velocity <= 0 or event.duration_beats <= 0: continue
            # The source onset is offset, but the shared expansion sees the
            # original source-grid beat, exactly as the transport does.
            onset = beat + (offset + (swing if index % 2 else 0.)) * step
            tones = engine._chord_pitches(voice, event.pitch) if engine is not None and supports_strum(voice) else [event.pitch]
            event = replace(event, pitches=tuple(tones))
            mapper = lambda pitch: midi_note_for(project, voice, pitch)
            strums = strum_hits(event, voice.parameters, project.seed, mapper, source_step=index) if supports_strum(voice) else None
            if strums is not None:
                hits = [(hit.offset, hit.pitch, hit.duration, hit.velocity, 'strum') for hit in strums]
            elif supports_articulation(voice):
                hits = [(hit.offset, event.pitch, hit.duration, hit.velocity, hit.kind) for hit in articulate(event, voice.parameters, project.seed)]
            else:
                hits = [(0., pitch, event.duration_beats, event.velocity, 'note') for pitch in tones]
            for delay, pitch, duration, velocity, kind in hits:
                position = (onset + delay) / .25
                if position < steps and position + duration / .25 > 0:
                    result.append(PreviewNote(position, mapper(pitch), duration / .25, velocity, kind))
    return result


@dataclass(frozen=True)
class VisibleNote:
    step: float
    duration: float
    note: PianoNote


def visible_notes(notes, steps, now, interval, now_beat=None):
    """Clip sounding tails as well as onsets, using beats across tempo edits."""
    span = steps * (.25 if now_beat is not None else interval)
    anchor = now_beat if now_beat is not None else now
    start = anchor - span
    result = []
    for note in notes:
        onset = note.beat if now_beat is not None else note.timestamp
        end = note.end_beat if now_beat is not None else note.end
        end = anchor if end is None else min(anchor, end)
        if note.timestamp > now + 1e-8 or onset > anchor + 1e-8 or end < start or end < onset: continue
        left, right = max(start, onset), max(max(start, onset), end)
        scale = .25 if now_beat is not None else interval
        result.append(VisibleNote((left - start) / scale, (right - left) / scale, note))
    return result
