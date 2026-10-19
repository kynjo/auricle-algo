"""Beat-based call/response between block owners; independent of UI and ports.

Record accepted call events, not cached previews. Replies retain their own
rhythm and timbre, optionally echoing/inverting the call's contour and accents.
Only one current call is retained per pair; no recursive relation evaluation.
"""
from __future__ import annotations

import math
import random

from auricle_model import midi_note_for

METERS = ('2/4', '3/4', '4/4', '5/4', '6/8', '7/8', '12/8')
REPLIES = ('Own phrase', 'Echo', 'Contrast')


def number(value, default, low, high):
    try:
        value = float(value)
        return min(high, max(low, value)) if math.isfinite(value) else default
    except (ValueError, TypeError, OverflowError):
        return default


def settings(relation):
    p = relation.parameters if isinstance(relation.parameters, dict) else {}
    return {
        'meter': p.get('meter') if p.get('meter') in METERS else '4/4',
        'call_bars': int(number(p.get('call_bars'), 1, 1, 8)),
        'response_bars': int(number(p.get('response_bars'), 1, 1, 8)),
        'gap_beats': number(p.get('gap_beats'), 0, 0, 4),
        'reply': p.get('reply') if p.get('reply') in REPLIES else 'Echo',
        'follow': number(p.get('follow'), .75, 0, 1),
    }


def phase_at(config, beat):
    numerator, denominator = map(int, config['meter'].split('/'))
    bar = numerator * 4.0 / denominator
    call, response, gap = config['call_bars']*bar, config['response_bars']*bar, config['gap_beats']
    total = call + response + 2*gap
    beat = max(0.0, float(beat))
    cycle = math.floor((beat+1e-8)/total)
    position = max(0., beat-cycle*total)
    if position < call-1e-8:
        phase, local, duration = 'Call', position, call
    elif position < call+gap-1e-8:
        phase, local, duration = 'Pause', position-call, gap
    elif position < call+gap+response-1e-8:
        phase, local, duration = 'Response', position-call-gap, response
    else:
        phase, local, duration = 'Pause', position-call-gap-response, gap
    return dict(phase=phase, local=local, remaining=max(0., duration-local), cycle=cycle,
                position=position, total=total, call=call, response=response, gap=gap)


class DialogueRuntime:
    def __init__(self, project):
        self.project = project
        self._signature = None
        self.routes = {}
        self.owners = {}
        self.memory = {}

    def reset(self):
        self.memory.clear()

    def _sync(self):
        relations = [r for r in self.project.relations if r.algorithm == 'Dialogue']
        signature = (tuple(b.id for b in self.project.blocks), self.project.seed,
                     tuple((id(r), r.id, r.source_block, r.destination_block, r.enabled,
                            r.amount, r.probability, tuple(settings(r).items())) for r in relations))
        if signature == self._signature:
            return
        self._signature = signature
        self.reset()
        self.routes, self.owners = {}, {}
        block_ids = {b.id for b in self.project.blocks}
        for index, relation in enumerate(relations):
            source, destination = relation.source_block, relation.destination_block
            reason = ''
            if not relation.enabled:
                reason = 'Disabled'
            elif number(relation.amount, 1, 0, 1) <= 0:
                reason = 'Separation is 0 — bypass'
            elif number(relation.probability, 1, 0, 1) <= 0:
                reason = 'Cycle chance is 0 — bypass'
            elif source not in block_ids or destination not in block_ids:
                reason = 'Missing block — bypass'
            elif source == destination:
                reason = 'Choose two different blocks — bypass'
            elif source in self.owners or destination in self.owners:
                reason = 'Block already used by an earlier Dialogue — bypass'
            route = dict(relation=relation, config=settings(relation), reason=reason, index=index)
            self.routes[id(relation)] = route
            if not reason:
                self.owners[source] = self.owners[destination] = route

    def status(self, relation, beat):
        self._sync()
        route = self.routes.get(id(relation))
        if route is None:
            return {'active': False, 'reason': 'Not a Dialogue'}
        phase = phase_at(route['config'], beat)
        reason = route['reason']
        if not reason:
            seed = int(self.project.seed) + (int(relation.id) or route['index']+1)*104729 + phase['cycle']*7919
            chance = number(relation.probability, 1, 0, 1)
            if chance < 1 and random.Random(seed).random() >= chance:
                reason = 'This cycle bypassed'
        return {**phase, 'active': not reason, 'reason': reason}

    def route_for(self, block):
        self._sync()
        return self.owners.get(getattr(block, 'parent_id', block.id))

    def can_play(self, block, beat):
        route = self.route_for(block)
        if route is None:
            return True
        relation = route['relation']
        status = self.status(relation, beat)
        if not status['active'] or number(relation.amount, 1, 0, 1) < 1:
            return True
        owner = getattr(block, 'parent_id', block.id)
        return ((status['phase'] == 'Call' and owner == relation.source_block)
                or (status['phase'] == 'Response' and owner == relation.destination_block))

    def apply(self, block, event, beat):
        if event is None:
            return None
        route = self.route_for(block)
        if route is None:
            return event
        relation, config = route['relation'], route['config']
        status = self.status(relation, beat)
        if not status['active']:
            return event
        owner = getattr(block, 'parent_id', block.id)
        calling = status['phase'] == 'Call' and owner == relation.source_block
        answering = status['phase'] == 'Response' and owner == relation.destination_block
        if not calling and not answering and number(relation.amount, 1, 0, 1) >= 1:
            return None
        result = dict(event)
        result['dialogue_remaining_beats'] = status['remaining']
        result['dialogue_phase'] = status['phase']
        if not calling and not answering:
            result['velocity'] = float(result.get('velocity', .8)) * (1-number(relation.amount, 1, 0, 1))
            return result
        key = id(relation)
        memory = self.memory.get(key)
        if memory is None or memory['cycle'] != status['cycle']:
            memory = self.memory[key] = {'cycle': status['cycle'], 'samples': {}, 'anchors': {}}
        if calling:
            # One representative per sixteenth, also for polyphony/Drum Kit.
            # Prefer the loudest voice, then lower pitch; independent of order.
            slot = int(math.floor((status['local']+1e-8)*4))
            sample = (status['local'], midi_note_for(self.project, block, result.get('pitch', 0)),
                      float(result.get('velocity', .8)), block.block_type != 'DRUM')
            previous = memory['samples'].get(slot)
            if previous is None or (sample[2], -sample[1]) > (previous[2], -previous[1]):
                memory['samples'][slot] = sample
        elif config['reply'] != 'Own phrase' and memory['samples'] and config['follow'] > 0:
            samples = [sample for _, sample in sorted(memory['samples'].items())]
            position = status['local'] / status['response'] * status['call']
            sample = min(samples, key=lambda s: abs(s[0]-position))
            direction = -1 if config['reply'] == 'Contrast' else 1
            follow = config['follow']
            mean_velocity = sum(s[2] for s in samples)/len(samples)
            result['velocity'] = number(float(result.get('velocity', .8)) +
                                        direction*follow*(sample[2]-mean_velocity), .8, .01, 1)
            if block.block_type in ('BASS', 'MELODY') and sample[3]:
                pitch = float(result.get('pitch', 0))
                anchor = memory['anchors'].setdefault(block.id, pitch)
                delta = number(sample[1]-samples[0][1], 0, -12, 12)
                result['pitch'] = (1-follow)*pitch + follow*(anchor+direction*delta)
                result['dialogue_pitch_changed'] = True
        return result
