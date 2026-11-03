"""Section-addressed parameter automation; musical sampling, no Qt or timers."""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import math
import uuid

from auricle_catalogs import (COMMON_MOD_PARAMETERS, GENERATOR_MOD_PARAMETERS,
                             FLOAT_MOD_KEYS, GENERATORS, SCALES, ROLE_PROFILES)
from composition_automation import normalize_curve, curve_value
from metric_kit import METRIC_PARAMETERS
from drum_articulation import ARTICULATION_PARAMETERS, supports_articulation
from strum import STRUM_PARAMETERS, STRUM_CHOICES, supports_strum

PREFIX = 'composition-auto:'
TIMINGS = ('auto', 'continuous', 'step', 'beat', 'bar', 'cycle', 'section')
OPERATIONS = ('set', 'add', 'multiply')
MAX_TRACKS = 128
MACRO_SOURCES = ('energy', 'tension')
ARTICULATION_NUMERIC_KEYS = frozenset((*ARTICULATION_PARAMETERS, *STRUM_PARAMETERS))
ARTICULATION_KEYS = ARTICULATION_NUMERIC_KEYS | frozenset(STRUM_CHOICES)


def articulation_family(key):
    if key.startswith('drum_ratchet_'): return 'ratchet'
    if key.startswith('drum_flam_'): return 'flam'
    return 'strum' if key in (*STRUM_PARAMETERS, *STRUM_CHOICES) else None


def articulation_keys(block):
    if supports_articulation(block): return frozenset(ARTICULATION_PARAMETERS)
    if supports_strum(block): return frozenset((*STRUM_PARAMETERS, *STRUM_CHOICES))
    return frozenset()


def curve_field(track):
    return 'macro_curve' if track.get('mode') == 'macro' else 'curve'


LENGTH_KEYS = {'structure_length', 'euclidean_steps', 'bres_steps', 'poly_a', 'poly_b',
               'timing_rate', 'variation_seed', 'ca_rule', 'ca_generations', 'ls_iterations'}
ROTATION_KEYS = {'structure_rotation', 'euclidean_rotation', 'bres_rotation', 'tm_rotation',
                 'debruijn_rotation', 'pattern_rotation', 'orbit_rotation', 'fib_offset'}
INTEGER_CONTROLS = {'scale_root', 'transpose', 'octave', 'pitch_range', 'role_center', 'role_width',
                    'harmony_size', 'harmony_spread', 'harmony_inversion', 'groove_offset',
                    'kit_metric_fragment', 'drum_ratchet_count'}
UNITS = {
    **dict.fromkeys(('structure_length', 'euclidean_steps', 'bres_steps', 'groove_offset', *ROTATION_KEYS), 'steps'),
    **dict.fromkeys(('pulses', 'bres_pulses'), 'hits'),
    **dict.fromkeys(('transpose', 'pitch_range', 'role_center', 'role_width', 'harmony_spread'), 'st'),
    **dict.fromkeys(('octave', 'markov_octaves', 'scale_octaves', 'arp_octaves', 'chaos_octaves', 'probability_octaves'), 'oct'),
    **dict.fromkeys(('live_min_beats', 'live_max_beats'), 'beats'),
    **dict.fromkeys(('timing_swing', 'timing_humanize', 'timing_offset'), 'step'),
    **dict.fromkeys(('timing_rate', 'role_duration', 'pattern_scale', 'pad_sustain'), '×'),
    **dict.fromkeys(('poly_a', 'poly_b', 'poly_phase_a', 'poly_phase_b',
                     'orbit_cycle_a', 'orbit_cycle_b', 'orbit_phase_a', 'orbit_phase_b'), 'steps'),
    **dict.fromkeys(('sequence_mod', 'sequence_offset', 'scale_step', 'markov_jump', 'markov_transpose'), 'degrees'),
    **dict.fromkeys(('interval_step', 'interval_range'), 'st'),
    'geometry_speed': '×',
    'scale_root': 'MIDI', 'harmony_size': 'voices',
    'kit_metric_fragment': '16ths',
    'drum_ratchet_count': 'hits', 'drum_flam_spacing': 'beats',
    'drum_ratchet_decay': '×',
    'strum_spacing': 'beats',
}


def finite(value, default=0.):
    try:
        value = float(value)
        return value if math.isfinite(value) else float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def entities(project):
    return [owner for block in project.blocks for owner in (block, *(block.drum_voices or []))]


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    default: object
    low: float = 0.
    high: float = 1.
    integer: bool = False
    boolean: bool = False
    choices: tuple = ()
    text: bool = False
    generators: tuple = ()
    timing: str = 'continuous'

    @property
    def unit(self):
        return UNITS.get(self.key, '')

    def decimals(self, operation='set'):
        return 0 if (self.integer or self.boolean) and operation != 'multiply' else 5

    def step(self, operation='set'):
        return 1. if self.decimals(operation) == 0 else .01

    def operand_unit(self, operation='set'):
        return '×' if operation == 'multiply' else self.unit

    @property
    def discrete(self):
        return bool(self.choices or self.text)

    @property
    def label(self):
        if self.key == '@algorithm':
            return 'Generator algorithm'
        from help_catalog import entry
        help_entry = entry('block', self.key)
        return help_entry.label if help_entry else self.key.replace('_', ' ').title()

    def supported(self, block):
        return not self.generators or block.algorithm in self.generators

    def coerce(self, value):
        if self.choices:
            return value if value in self.choices else self.default
        if self.text:
            return str(value)[:4096]
        value = max(self.low, min(self.high, finite(value, self.default)))
        return bool(value >= .5) if self.boolean else int(round(value)) if self.integer else value


def parameter_specs(engine, block):
    """Known destinations, including inactive-generator lanes for section changes."""
    catalog = dict(engine.parameter_catalog(block))
    owners = {}
    known = dict(COMMON_MOD_PARAMETERS)
    known.update(METRIC_PARAMETERS)
    known.update(ARTICULATION_PARAMETERS)
    known.update(STRUM_PARAMETERS)
    for algorithm, values in GENERATOR_MOD_PARAMETERS.items():
        for key, limits in values.items():
            # A stored inactive-generator value is not its definition. Replace
            # the engine's conservative legacy fallback with the known limits.
            catalog[key] = limits
            known[key] = limits
            if key not in COMMON_MOD_PARAMETERS:
                owners.setdefault(key, []).append(algorithm)
    length = max(1, int(engine.project.length))
    for key in ('structure_length', 'euclidean_steps', 'bres_steps'):
        catalog[key] = (length, 1, length)
    for key in ('pulses', 'bres_pulses'):
        catalog[key] = (5, 1, length)
    for key in ROTATION_KEYS:
        catalog[key] = (0, 0, length - 1)
    catalog['ls_iterations'] = (3, 0, 10)
    profile = ROLE_PROFILES.get(block.block_type, {})
    for key, fallback in (('role_density', profile.get('fill_density', 1.)),
                          ('role_duration', profile.get('role_duration', 1.)),
                          ('role_root_bias', profile.get('root_bias', 0.))):
        _, low, high = catalog[key]
        catalog[key] = (fallback, low, high)
    if 'fill_density' not in block.parameters:
        catalog['fill_density'] = (finite(block.parameters.get('event_density', 1.), 1.), 0., 1.)
    result = {}
    for key, (default, low, high) in catalog.items():
        if key in ('relation_drum_source', 'relation_chord_source'):
            continue  # Entity ids are choices, never interpolated numbers.
        if key in ('structure_length', 'euclidean_steps', 'bres_steps'):
            default = engine.project.length
        elif key == 'scale_root':
            default = engine.project.root_note
        base = engine.parameter_influence.base_value(block, key, default)
        # Known types do not change because an old JSON wrote 4.0 instead of 4,
        # or 1 instead of 1.0. Match the actual Inspector controls.
        integer = (key in INTEGER_CONTROLS or
                   (isinstance(default, int) and not isinstance(default, bool) and key not in FLOAT_MOD_KEYS))
        if key not in known and key not in INTEGER_CONTROLS and key not in ROTATION_KEYS and key not in ('role_center', 'role_width'):
            integer = isinstance(base, int) and not isinstance(base, bool) and key not in FLOAT_MOD_KEYS
            if not key.startswith('kit_') and key not in ('harmonic_strength', 'velocity_random'):
                default = finite(base, finite(default))
                span = max(1., abs(finite(base)))
                low, high = -4. * span, 4. * span
        result[key] = ParameterSpec(key, default, float(low), float(high), integer=integer,
                                    boolean=isinstance(base, bool), generators=tuple(owners.get(key, ())),
                                    timing='cycle' if key in LENGTH_KEYS else 'step' if integer else 'continuous')
    if not getattr(block, 'drum_voices', None):
        result['@algorithm'] = ParameterSpec('@algorithm', block.algorithm, choices=tuple(GENERATORS), timing='bar')
        result['pattern'] = ParameterSpec('pattern', '1,0,0.7,0,1,0,0.5,0', text=True,
                                         generators=('Pattern',), timing='cycle')
        result['variation_seed'] = ParameterSpec('variation_seed', 0, -9999, 9999, integer=True, timing='cycle')
        for key, default, generators in (
            ('tm_invert', False, ('Thue-Morse',)),
            ('sequence_reverse', False, ('Fibonacci', 'Recaman')),
            ('pattern_reverse', False, ('Pattern',)),
            ('turing_wrap', True, ('Turing Machine',)),
            ('interval_quantize', True, ('Interval Walker',)),
            ('chaos_quantize', True, ('Logistic Chaos',)),
        ):
            result[key] = ParameterSpec(key, default, boolean=True, generators=generators, timing='cycle')
        for key, default, generators in (
            ('scale_weights', '1,1,1,1,1,1,1', ('Weighted Scale',)),
            ('arp_pattern', '0,2,4,6', ('Arpeggiator',)),
            ('ca_seed', '00100000', ('Cellular Automaton',)),
            ('ls_axiom', 'A', ('L-System',)), ('ls_rule_a', 'AB', ('L-System',)),
            ('ls_rule_b', 'A', ('L-System',)), ('ls_mapping', '0,1,2,3,4,5,6', ('L-System',)),
            ('turing_tape', '00010000', ('Turing Machine',)),
        ):
            result[key] = ParameterSpec(key, default, text=True, generators=generators, timing='cycle')
        for key, choices, generator in (
            ('poly_mode', ('OR', 'AND', 'XOR'), 'Polyrhythm'),
            ('debruijn_mode', ('Rhythm', 'Pitch'), 'De Bruijn'),
            ('arp_direction', ('Up', 'Down', 'Up/Down'), 'Arpeggiator'),
            ('arp_octave_mode', ('Cycle', 'Random'), 'Arpeggiator'),
            ('ca_mode', ('Rhythm', 'Pitch'), 'Cellular Automaton'),
            ('ca_boundary', ('Wrap', 'Fixed', 'Mirror'), 'Cellular Automaton'),
            ('ca_evolution', ('Final Row', 'Evolution Trail', 'XOR Trail'), 'Cellular Automaton'),
            ('ls_mode', ('Pitch', 'Rhythm', 'Turtle Pitch', 'Turtle Rhythm'), 'L-System'),
            ('turing_preset', ('Busy Beaver', 'Alternator', 'Growth', 'Marbles'), 'Turing Machine'),
            ('turing_mode', ('Rhythm', 'Pitch'), 'Turing Machine'),
            ('orbit_mode', ('OR', 'A', 'B', 'AND', 'XOR', 'Interlock'), 'Orbital Sequence'),
            ('orbit_output', ('Rhythm', 'Pitch'), 'Orbital Sequence'),
            ('geometry_shape', ('Box', 'Triangle', 'Hexagon', 'Circle'), 'Geometry Collision'),
            ('geometry_mode', ('Rhythm', 'Pitch'), 'Geometry Collision'),
        ):
            result[key] = ParameterSpec(key, choices[0], choices=choices, generators=(generator,), timing='cycle')
    if supports_strum(block):
        for key, (default, choices) in STRUM_CHOICES.items():
            result[key] = ParameterSpec(key, default, choices=choices, timing='step')
    if block.block_type in ('BASS', 'MELODY', 'PAD', 'CHORD'):
        result['scale_name'] = ParameterSpec('scale_name', engine.project.scale, choices=tuple(SCALES), timing='bar')
        result['harmonic_follow'] = ParameterSpec('harmonic_follow', True, boolean=True, timing='bar')
    if getattr(block, 'drum_voices', None):
        result['kit_protect_anchors'] = ParameterSpec('kit_protect_anchors', True, boolean=True, timing='bar')
    source_type = 'DRUM' if block.block_type == 'BASS' else 'CHORD' if block.block_type == 'MELODY' else None
    if source_type:
        key = 'relation_drum_source' if source_type == 'DRUM' else 'relation_chord_source'
        choices = (-1, *(owner.id for owner in engine.project.blocks if owner.block_type == source_type))
        result[key] = ParameterSpec(key, -1, choices=choices, timing='bar')
    if block.block_type == 'BASS':
        result['groove_mode'] = ParameterSpec('groove_mode', 'Union', choices=('Union', 'Replace'), timing='bar')
    return result


def operation_range(spec, operation):
    if operation == 'add':
        extent = max(0., spec.high - spec.low)
        return -extent, extent
    if operation == 'multiply':
        return 0., 4.
    return spec.low, spec.high


def effective_operation(track, spec):
    operation = track.get('operation', 'set')
    return operation if operation in OPERATIONS and not spec.discrete and not spec.boolean else 'set'


def curve_range(track, spec):
    """One operand range for the graph, point editor and playback.

    Legacy lanes may contain the old generic 0..128 limits. Fit their scale,
    retaining normalized point positions instead of saturating the output.
    Valid user-selected subranges remain untouched.
    """
    operation = effective_operation(track, spec)
    minimum, maximum = operation_range(spec, operation)
    low = max(minimum, min(maximum, finite(track.get('low', minimum), minimum)))
    high = max(minimum, min(maximum, finite(track.get('high', maximum), maximum)))
    if spec.decimals(operation) == 0:
        low, high = round(low), round(high)
    if high <= low:
        return minimum, maximum
    return low, high


def parameter_curve(track, spec):
    """Quantize point values in parameter units; time coordinates stay intact."""
    fallback = [[0, 0], [1, 1]] if track.get('mode') == 'macro' else [[0, .5], [1, .5]]
    curve = track.get(curve_field(track)) or normalize_curve({'shape': 'linear', 'points': fallback})
    if spec.decimals(effective_operation(track, spec)) != 0:
        return curve
    low, high = curve_range(track, spec)
    span = high - low
    def quantized(value):
        return int(value >= .5) if spec.boolean else round(value)
    return {**curve, 'points': [[x, (quantized(low + y * span) - low) / span if span else .5]
                                for x, y in curve['points']]}


def make_track(engine, block, key):
    spec = parameter_specs(engine, block)[key]
    value = spec.coerce(engine.parameter_influence.base_value(block, key, spec.default))
    span = spec.high - spec.low
    unit = (finite(value, spec.default) - spec.low) / span if not spec.discrete and span else .5
    return {'id': uuid.uuid4().hex, 'entity_id': int(block.id), 'parameter': key,
            'enabled': True, 'operation': 'set', 'mode': 'value', 'value': value,
            'low': spec.low, 'high': spec.high, 'weight': 1., 'timing': 'auto',
            'macro_source': 'energy', 'reverse': False,
            'macro_curve': normalize_curve({'shape': 'linear', 'points': [[0, 0], [1, 1]]}),
            'curve': normalize_curve({'shape': 'linear', 'points': [[0, unit], [1, unit]]})}


def normalize_tracks(raw):
    if not isinstance(raw, (list, tuple)):
        return []
    tracks, ids = [], set()
    for item in raw[:MAX_TRACKS]:
        if not isinstance(item, dict) or isinstance(item.get('entity_id'), bool):
            continue
        try:
            owner = int(item['entity_id'])
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        key = str(item.get('parameter', ''))[:80]
        if not key or (key.startswith('@') and key != '@algorithm'):
            continue
        identity = str(item.get('id') or uuid.uuid4().hex)[:80]
        if identity in ids:
            identity = uuid.uuid4().hex
        ids.add(identity)
        value = item.get('value', 0.)
        value = value[:4096] if isinstance(value, str) else value if isinstance(value, bool) else finite(value)
        low = max(-1e12, min(1e12, finite(item.get('low', 0.))))
        high = max(low + 1e-9, min(1e12, finite(item.get('high', 1.), 1.)))
        tracks.append({'id': identity, 'entity_id': owner, 'parameter': key,
                       'enabled': bool(item.get('enabled', True)),
                       'operation': item.get('operation') if item.get('operation') in OPERATIONS else 'set',
                       'mode': item.get('mode') if item.get('mode') in ('curve', 'macro') else 'value',
                       'macro_source': item.get('macro_source') if item.get('macro_source') in MACRO_SOURCES else 'energy',
                       'reverse': bool(item.get('reverse', False)),
                       'macro_curve': normalize_curve(item.get('macro_curve')) or normalize_curve({'shape': 'linear', 'points': [[0, 0], [1, 1]]}),
                       'value': value, 'low': low, 'high': high,
                       'weight': max(0., min(1., finite(item.get('weight', 1.), 1.))),
                       'timing': item.get('timing') if item.get('timing') in TIMINGS else 'auto',
                       'curve': normalize_curve(item.get('curve')) or normalize_curve({'points': [[0, .5], [1, .5]]})})
    return tracks


def timing_for(track, spec, block):
    requested = track.get('timing', 'auto')
    default = spec.timing
    if default == 'continuous' and block.mode == 'SEQ' and spec.key not in ARTICULATION_KEYS:
        default = 'step'
    if requested == 'auto':
        return default
    if spec.discrete or spec.boolean or spec.timing == 'cycle':
        return requested if requested in ('section', 'bar', 'cycle') else default
    if spec.integer and requested == 'continuous':
        return 'step'
    return requested if requested in TIMINGS else default


def sample_local(context, timing, cycle_beats):
    duration = max(1e-9, context['end_beat'] - context['start_beat'])
    local = max(0., min(duration, context['local_beat']))
    if timing == 'section':
        return 0., duration
    quantum = {'step': .25, 'beat': 1., 'bar': context['bar_beats'], 'cycle': cycle_beats}.get(timing, 0.)
    if local >= duration - 1e-9:
        return duration, quantum
    return (max(0., math.floor((local + 1e-9) / quantum) * quantum) if quantum else local), quantum


class ParameterAutomationRuntime:
    """Only the transport calls advance. UI reads status without advancing it."""
    def __init__(self, engine):
        self.engine = engine
        self.context_key = None
        self.states = {}
        self.statuses = {}
        self.spec_cache = {}
        self.dirty = set()
        self.generation_slot = None
        self.structure_serial = 0
        self.pruned_generation_targets = set()

    def _prune(self, active_ids):
        layers = self.engine.parameter_influence
        owners = entities(self.engine.project)
        live_ids = {owner.id for owner in owners}
        for target, entry in list(layers.entries.items()):
            if target[0] not in live_ids and any(identity.startswith(PREFIX) for identity in entry['rows']):
                layers.entries.pop(target, None)
                layers.specs.pop(target, None)
                layers.discrete_specs.pop(target, None)
        generation_targets = {owner for (owner, key), entry in layers.entries.items()
                              if key not in ARTICULATION_KEYS and any(
                                  identity.startswith(PREFIX) and identity not in active_ids for identity in entry['rows'])}
        discrete = {owner for (owner, key), entry in layers.entries.items()
                    if key not in ARTICULATION_KEYS and (owner, key) in layers.discrete_specs and any(
                        identity.startswith(PREFIX) and identity not in active_ids for identity in entry['rows'])}
        changed = layers.prune(owners, PREFIX, active_ids)
        self.pruned_generation_targets = {block.id for block in changed if block.id in generation_targets}
        for block in changed:
            if block.id in discrete:
                self.engine.reset_live(block, reset_performance=False)
                self.structure_serial += 1
        return changed

    def reset(self, *, regenerate=False):
        changed = self._prune(set())
        self.context_key = None
        self.states.clear(); self.statuses.clear(); self.spec_cache.clear(); self.dirty.clear()
        self.generation_slot = None
        if changed and regenerate and self.pruned_generation_targets:
            self.engine.generate()
        return bool(changed)

    def advance(self, beat, *, force=False, regenerate=True):
        engine = self.engine
        runtime = engine.composition_runtime
        context = runtime.context_at(beat) if runtime.playback_active is True else None
        if context is None:
            return self.reset(regenerate=regenerate)
        section = context['section']
        context_key = (context['cycle'], context['section_id'])
        output_changed = False
        if context_key != self.context_key:
            restored = self.reset()
            output_changed = restored
            if restored and self.pruned_generation_targets:
                self.dirty.add(-1)
            self.context_key = context_key
            force = True
        owners = {block.id: block for block in entities(engine.project)}
        tracks = section.get('parameter_automation', [])[:MAX_TRACKS]
        active_ids, seen, statuses = set(), set(), {}
        # Resolve algorithm snapshots before lanes for that generator.
        tracks = sorted(tracks, key=lambda item: item.get('parameter') != '@algorithm')
        for track in tracks:
            tid = track['id']; owner = owners.get(track['entity_id']); key = track['parameter']
            status = {'state': 'assigned', 'timing': track.get('timing', 'auto')}
            statuses[tid] = status
            if not track.get('enabled', True) or track.get('weight', 1.) <= 0:
                status['state'] = 'disabled'; continue
            if owner is None:
                status['state'] = 'missing target'; continue
            target = (owner.id, key)
            if target in seen:
                status['state'] = 'duplicate target'; continue
            seen.add(target)
            cache_key = (id(section), id(owner), owner.algorithm, engine.project.length, engine.project.root_note, engine.project.scale)
            if cache_key not in self.spec_cache:
                self.spec_cache[cache_key] = parameter_specs(engine, owner)
            spec = self.spec_cache[cache_key].get(key)
            if spec is None or not spec.supported(owner) or (key in ARTICULATION_KEYS and key not in articulation_keys(owner)):
                status['state'] = 'unavailable for generator'; continue
            if spec.discrete and track.get('mode') == 'macro':
                status['state'] = 'macro requires numeric target'; continue
            source_id = f'{PREFIX}{context["section_id"]}:{tid}'
            active_ids.add(source_id)
            if tid not in self.states:
                cycle = max(1, min(engine.project.length, int(engine.parameter_influence.base_value(owner, 'structure_length', engine.project.length))))
                rate = max(.25, min(4., finite(engine.parameter_influence.base_value(owner, 'timing_rate', 1.), 1.)))
                cycle *= .25 if engine.coordinated_drum(owner) is not None else .25 / rate
                self.states[tid] = {'cycle': cycle}
            state = self.states[tid]
            timing = timing_for(track, spec, owner)
            sampled, quantum = sample_local(context, timing, state['cycle'])
            signature = repr(track)
            if state.get('signature') != signature:
                state['signature'] = signature
                local = context['local_beat']
                state['pending'] = (min(context['end_beat'] - context['start_beat'],
                                        math.ceil((local - 1e-9) / quantum) * quantum)
                                    if quantum and not force and local > 1e-9 else 0.)
            status['timing'] = timing
            status['sample_beat'] = sampled
            if not force and context['local_beat'] + 1e-9 < state.get('pending', 0.):
                status['state'] = 'waiting for boundary'
                status['next_beat'] = state['pending']
                continue
            operation = effective_operation(track, spec)
            if spec.discrete:
                engine.parameter_influence.configure_discrete(owner, key, spec.default, spec.choices)
                value = spec.coerce(track.get('value', spec.default))
            else:
                engine.parameter_influence.configure(owner, key, spec.default, spec.low, spec.high, spec.integer, spec.boolean)
                duration = max(1e-9, context['end_beat'] - context['start_beat'])
                low, high = curve_range(track, spec)
                curve_key = (signature, low, high, spec.decimals(operation))
                if track.get('mode') in ('curve', 'macro') and state.get('curve_key') != curve_key:
                    state['curve_key'] = curve_key
                    state['curve'] = parameter_curve(track, spec)
                if track.get('mode') == 'macro':
                    macro = track.get('macro_source', 'energy')
                    macro = macro if macro in MACRO_SOURCES else 'energy'
                    if (force or not quantum or state.get('macro_sample') != sampled
                            or state.get('macro_signature') != signature):
                        sample_context = {**context, 'local_beat': sampled, 'section_progress': sampled / duration}
                        macros = runtime.effective_macros(section, engine.director.global_macro_values, sample_context)
                        state['macro_value'] = max(0., min(1., finite(macros[macro])))
                        state['macro_sample'], state['macro_signature'] = sampled, signature
                    source = state['macro_value']
                    position = 1. - source if track.get('reverse', False) else source
                    response = curve_value(state['curve'], position)
                    operand = low + (high - low) * response
                    status.update(macro_source=macro, macro_value=source, curve_position=position, response=response)
                else:
                    operand = (low + (high - low) * curve_value(state['curve'], sampled / duration)
                               if track.get('mode') == 'curve' else finite(track.get('value'), spec.default))
                base = finite(engine.parameter_influence.base_value(owner, key, spec.default), spec.default)
                value = spec.coerce(base + operand if operation == 'add' else base * operand if operation == 'multiply' else operand)
            before = deepcopy(engine.parameter_influence.current_value(owner, key, spec.default))
            row = engine.parameter_influence.entries.get(target, {}).get('rows', {}).get(source_id)
            if row is None or row['value'] != value or row['weight'] != track.get('weight', 1.):
                engine.parameter_influence.write(owner, key, value,
                    f'Composition: {section["name"]} / {spec.label}' +
                    (f' ← {status["macro_source"].title()}' if 'macro_source' in status else ''),
                    source_id=source_id, weight=track.get('weight', 1.))
            current = engine.parameter_influence.current_value(owner, key, spec.default)
            state['structural'] = spec.discrete and key not in ARTICULATION_KEYS
            if before != current:
                if key in ARTICULATION_KEYS:
                    output_changed = True
                else:
                    self.dirty.add(owner.id)
                if state['structural']:
                    self.structure_serial += 1
                    engine.reset_live(owner, reset_performance=False)
            coefficient = engine.parameter_influence.contributions(owner, key)['Composition']
            status.update(state='active' if coefficient > 1e-9 else 'bypassed by policy',
                          target=value, current=current, contribution=coefficient)
        restored = self._prune(active_ids)
        self.dirty.update(self.pruned_generation_targets)
        output_changed = output_changed or bool(restored)
        self.states = {key: value for key, value in self.states.items() if key in statuses}
        self.statuses = statuses
        if len(self.spec_cache) > MAX_TRACKS * 2:
            self.spec_cache.clear()
        # One batched generation per sixteenth, not per lane or MIDI-worker tick.
        slot = (context_key, math.floor((context['local_beat'] + 1e-9) / .25))
        changed = bool(self.dirty) or output_changed
        if self.dirty and regenerate and (force or slot != self.generation_slot):
            engine.generate()
            self.dirty.clear()
            self.generation_slot = slot
        elif not regenerate:
            self.dirty.clear()
            self.generation_slot = slot
        return changed
