"""Bar-based harmony shared by SEQ and LIVE, applied at event time."""
from __future__ import annotations

import math
from copy import deepcopy
from auricle_catalogs import ROLE_PROFILES
from auricle_model import block_root
from voice_leading import VoiceLeading

NOTES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
QUALITIES = {
    'major': ('', (0, 4, 7)), 'minor': ('m', (0, 3, 7)),
    '7': ('7', (0, 4, 7, 10)), 'maj7': ('maj7', (0, 4, 7, 11)),
    'm7': ('m7', (0, 3, 7, 10)), 'dim': ('dim', (0, 3, 6)),
    'aug': ('aug', (0, 4, 8)), 'sus2': ('sus2', (0, 2, 7)),
    'sus4': ('sus4', (0, 5, 7)),
}
METERS = ('2/4', '3/4', '4/4', '5/4', '6/8', '7/8', '12/8')
PRESETS = {
    'Am – F – C – G': [(9, 'minor'), (5, 'major'), (0, 'major'), (7, 'major')],
    'C – Am – F – G': [(0, 'major'), (9, 'minor'), (5, 'major'), (7, 'major')],
    'Dm7 – G7 – Cmaj7': [(2, 'm7'), (7, '7'), (0, 'maj7')],
    'Dm – Bb – F – C': [(2, 'minor'), (10, 'major'), (5, 'major'), (0, 'major')],
}


def preset(name='Am – F – C – G'):
    return {'enabled': True, 'meter': '4/4', 'loop': True,
            'chords': [{'root': root, 'quality': quality, 'bars': 1} for root, quality in PRESETS[name]]}


def normalized(data):
    """Validate loaded data without rewriting the user's model on a timer."""
    if not isinstance(data, dict): data = {}
    meter = data.get('meter', '4/4')
    if meter not in METERS: meter = '4/4'
    chords = []
    items = data.get('chords') or []
    if not isinstance(items, (list, tuple)): items = []
    for item in items[:128]:
        try:
            quality = str(item.get('quality', 'major'))
            if quality not in QUALITIES: continue
            chords.append({'root': int(item.get('root', 0)) % 12, 'quality': quality,
                           'bars': max(1, min(64, int(item.get('bars', 1))))})
        except (TypeError, ValueError, AttributeError, OverflowError):
            continue
    return {'enabled': bool(data.get('enabled', False)), 'meter': meter,
            'loop': bool(data.get('loop', True)), 'chords': chords}


def chord_name(chord):
    return NOTES[chord['root']] + QUALITIES[chord['quality']][0]


class HarmonicRuntime:
    def __init__(self, project):
        self.project = project
        self._configuration = None
        self.voicings = {}
        self.tokens = {}
        self.register_centers = {}
        self.config = normalized({})

    def _sync(self):
        if self._configuration != self.project.harmonic_plan:
            self._configuration = deepcopy(self.project.harmonic_plan)
            self.config = normalized(self._configuration)
            self.reset()
        return self.config

    def reset(self):
        self.voicings.clear()
        self.tokens.clear()
        self.register_centers.clear()

    def follows(self, block):
        config = self._sync()
        return (block.block_type in ('CHORD', 'PAD', 'BASS', 'MELODY')
                and config['enabled'] and bool(config['chords'])
                and bool(block.parameters.get('harmonic_follow', True)))

    def at(self, beat):
        config = self._sync()
        if not config['enabled'] or not config['chords']: return None
        numerator, denominator = map(int, config['meter'].split('/'))
        bar_beats = numerator * 4.0 / denominator
        total = sum(chord['bars'] for chord in config['chords']) * bar_beats
        beat = max(0.0, float(beat))
        cycle = int(math.floor((beat + 1e-8) / total)) if config['loop'] else 0
        position = (beat - cycle * total) if config['loop'] else min(beat, total)
        cursor = 0.0
        for index, chord in enumerate(config['chords']):
            duration = chord['bars'] * bar_beats
            end = cursor + duration
            last = index == len(config['chords']) - 1
            if position < end - 1e-8 or last:
                held = not config['loop'] and last and beat >= total
                return {**chord, 'name': chord_name(chord), 'index': index, 'cycle': cycle,
                        'pitch_classes': [(chord['root'] + i) % 12 for i in QUALITIES[chord['quality']][1]],
                        'bar': int((beat + 1e-8) // bar_beats) + 1,
                        'bar_beats': bar_beats, 'position': max(0.0, position - cursor),
                        'duration': duration, 'remaining': None if held else max(0.0, end - position),
                        'total_beats': total, 'held': held}
            cursor = end

    def apply(self, block, event, beat):
        if not event or not self.follows(block) or event.get('rhythm', 1) <= 0: return event
        chord = self.at(beat)
        if chord is None: return event
        result = dict(event)
        base = int(block.midi_note) + block_root(self.project, block) % 12
        target = max(0, min(127, round(base + float(event.get('pitch', 0)))))
        role = block.block_type
        if role in ('CHORD', 'PAD'):
            profile = ROLE_PROFILES[role]
            center = base + float(block.parameters.get('role_center', profile['register_anchor']))
            width = max(6.0, float(block.parameters.get('role_width', profile['pitch_range'])))
            token = (chord['cycle'], chord['index'], base,
                     block.parameters.get('harmony_inversion', 0),
                     block.parameters.get('harmony_spread', 7), block.parameters.get('harmony_size', 3),
                     center, width)
            if self.tokens.get(block.id) != token:
                intervals = list(QUALITIES[chord['quality']][1])
                size = max(1, min(4, int(block.parameters.get('harmony_size', 3))))
                if len(intervals) == 4: size = max(size, 4)  # explicit sevenths retain their quality
                if size == 4 and len(intervals) == 3:
                    intervals.append(11 if chord['quality'] == 'major' else 10)
                intervals = intervals[:size]
                root = min(range(chord['root'], 128, 12), key=lambda note: abs(note-target))
                notes = [root+i for i in intervals]
                inversion = int(block.parameters.get('harmony_inversion', 0))
                for _ in range(abs(inversion) % len(notes)):
                    notes = notes[1:] + [notes[0]+12] if inversion > 0 else [notes[-1]-12] + notes[:-1]
                spread = max(0, min(36, int(block.parameters.get('harmony_spread', 7))))
                for i in range(1, len(notes)):
                    while notes[i]-notes[0] < spread*i/max(1, len(notes)-1): notes[i] += 12
                previous = self.voicings.get(block.id)
                if previous:
                    # A deliberate Base Note / Center change moves the target
                    # register immediately, even within the current chord.
                    shift = center - self.register_centers[block.id]
                    previous = [note + shift for note in previous]
                self.voicings[block.id] = VoiceLeading.resolve_chord(
                    notes, previous, register=(center-width/2, center+width/2))
                self.register_centers[block.id] = center
                self.tokens[block.id] = token
            pitches = [float(note-base) for note in self.voicings[block.id]]
            result['pitch'], result['pitches'] = pitches[0], pitches
        else:
            strength = max(0.0, min(1.0, float(block.parameters.get('harmonic_strength', .75))))
            local = max(0.0, chord['position'])
            bar_phase = local % chord['bar_beats']
            strong = abs(bar_phase - round(bar_phase)) < .08
            cadence = not chord['held'] and chord['remaining'] <= min(1.0, chord['bar_beats']/2)
            slot = int(math.floor(float(beat)*4 + 1e-8))
            sample = ((slot*1103515245 + int(block.id)*12345 + int(self.project.seed)) & 0xffff)/65536.0
            anchor = strength > 0 and (strong or cadence or sample < strength)
            if anchor:
                pcs = [chord['root']] if role == 'BASS' and (bar_phase < 1 or cadence) else chord['pitch_classes']
                note = min((note for note in range(128) if note % 12 in pcs), key=lambda n: (abs(n-target), n))
                result['pitch'] = float(note-base)
                result.pop('pitches', None)
        result['harmony'] = chord['name']
        if chord['remaining'] is not None:
            result['harmony_remaining_beats'] = chord['remaining']
        return result
