"""Portable authored algorithm/block presets; no Qt, MIDI routing or runtime state."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, replace
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import uuid

from auricle_catalogs import GENERATORS, BLOCK_TYPES, GENERATOR_MOD_PARAMETERS, ROLE_PROFILES, PROCESS_TYPES
from auricle_model import Block, Mutator, Process, make_default_drum_voices
from mutators import mutators_for_target
from section_automation import parameter_specs
from coordinated_kit import voice_role
from midi_expression import normalize_expression
from parameter_influence import ParameterInfluence

FORMAT = 'auricle-sound-preset'
VERSION = 1
MAX_BYTES = 2 * 1024 * 1024
# These values identify other objects in a project. Presets never transplant them.
PROTECTED = frozenset(('relation_drum_source', 'relation_chord_source', 'motif_id', 'motif_hold', 'kit_voice_links'))
EXTRAS = {
    'Polyrhythm': {'poly_mode': 'OR'},
    'Thue-Morse': {'tm_invert': False, 'variation_seed': 0},
    'Fibonacci': {'sequence_reverse': False}, 'Recaman': {'sequence_reverse': False},
    'De Bruijn': {'debruijn_mode': 'Rhythm'},
    'Markov': {'variation_seed': 0, 'markov_scale': True},
    'Random Walk': {'variation_seed': 0, 'walk_quantize': True},
    'Interval Walker': {'variation_seed': 0, 'interval_quantize': True},
    'Scale Walker': {'variation_seed': 0},
    'Weighted Scale': {'scale_weights': '1,1,1,1,1,1,1', 'variation_seed': 0},
    'Arpeggiator': {'arp_pattern': '0,2,4,6', 'arp_direction': 'Up', 'arp_octave_mode': 'Cycle', 'variation_seed': 0},
    'Probability': {'variation_seed': 0},
    'Pattern': {'pattern': '1,0,0.7,0,1,0,0.5,0', 'pattern_reverse': False, 'pattern_step_chances': []},
    'Cellular Automaton': {'variation_seed': 0, 'ca_mode': 'Rhythm', 'ca_seed': '00100000', 'ca_boundary': 'Wrap', 'ca_evolution': 'Final Row'},
    'L-System': {'ls_axiom': 'A', 'ls_rule_a': 'AB', 'ls_rule_b': 'A', 'ls_mapping': '0,1,2,3,4,5,6', 'ls_mode': 'Pitch'},
    'Turing Machine': {'turing_preset': 'Busy Beaver', 'turing_mode': 'Rhythm', 'turing_tape': '00010000', 'turing_wrap': True, 'variation_seed': 0},
    'Orbital Sequence': {'orbit_mode': 'OR', 'orbit_output': 'Rhythm'},
    'Geometry Collision': {'geometry_shape': 'Box', 'geometry_mode': 'Rhythm', 'variation_seed': 0},
    'Logistic Chaos': {'chaos_quantize': True},
}


def algorithm_defaults(algorithm, length=16):
    if algorithm not in GENERATORS: raise ValueError('Unknown generator algorithm')
    result = {key: limits[0] for key, limits in GENERATOR_MOD_PARAMETERS.get(algorithm, {}).items()}
    result.update(deepcopy(EXTRAS.get(algorithm, {})))
    if algorithm == 'Euclidean': result['euclidean_steps'] = length
    if algorithm == 'Bresenham': result['bres_steps'] = length
    return result


def _parameters(raw):
    if not isinstance(raw, dict) or len(raw) > 512: raise ValueError('Invalid parameter map')
    result = {}
    for key, value in raw.items():
        if not isinstance(key, str) or len(key) > 128 or key.startswith('@'): raise ValueError('Invalid parameter name')
        if key in PROTECTED: continue
        if key == 'pattern_step_chances':
            if isinstance(value, str): value = value.replace(';', ',').split(',') if value.strip() else []
            if not isinstance(value, (list, tuple)) or len(value) > 4096: raise ValueError('Invalid step chances')
            result[key] = [max(0., min(1., _finite(v))) for v in value]
        elif isinstance(value, str):
            if len(value) > 4096: raise ValueError('Parameter text is too long')
            result[key] = value
        elif isinstance(value, bool): result[key] = value
        elif isinstance(value, (int, float)):
            _finite(value)
            if abs(value) > 1e6: raise ValueError('Parameter is outside a supported range')
            result[key] = value
        else: raise ValueError(f'Unsupported value for {key}')
    return result


def _finite(value):
    try: value = float(value)
    except (TypeError, ValueError, OverflowError): raise ValueError('Expected a finite number') from None
    if not math.isfinite(value): raise ValueError('Expected a finite number')
    return value


def validate(raw):
    if not isinstance(raw, dict) or raw.get('format') != FORMAT or type(raw.get('version')) is not int or raw['version'] != VERSION:
        raise ValueError('This is not a supported Auricle sound preset')
    kind = raw.get('kind')
    if kind not in ('algorithm', 'block'): raise ValueError('Unknown preset scope')
    algorithm = raw.get('algorithm')
    if algorithm not in GENERATORS: raise ValueError('Unknown generator algorithm')
    name = raw.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 120: raise ValueError('Preset name must contain 1–120 characters')
    result = {'format': FORMAT, 'version': VERSION, 'id': str(raw.get('id') or uuid.uuid4().hex)[:80],
              'name': name.strip(), 'description': str(raw.get('description', ''))[:2048],
              'kind': kind, 'algorithm': algorithm, 'parameters': _parameters(raw.get('parameters', {}))}
    if kind == 'algorithm':
        allowed = algorithm_defaults(algorithm)
        if not set(result['parameters']) <= set(allowed): raise ValueError('Algorithm preset contains unrelated parameters')
    else:
        if raw.get('block_type') not in BLOCK_TYPES: raise ValueError('Unknown block type')
        result['block_type'] = raw['block_type']
        result['target'] = 'voice' if raw.get('target') == 'voice' else 'block'
        result['mode'] = 'LIVE' if raw.get('mode') == 'LIVE' else 'SEQ'
        mutations = raw.get('mutators', [])
        processes = raw.get('processes', [])
        if not isinstance(mutations, list) or len(mutations) > 64 or not isinstance(processes, list) or len(processes) > 64:
            raise ValueError('Invalid processing stack')
        result['mutators'] = []
        for item in mutations:
            if not isinstance(item, dict) or item.get('name') not in mutators_for_target(item.get('target', 'pitch')):
                raise ValueError('Invalid mutation')
            result['mutators'].append({'name': item['name'], 'target': item.get('target', 'pitch'),
                                       'amount': max(0., min(1., _finite(item.get('amount', .5))))})
        result['processes'] = []
        for item in processes:
            if not isinstance(item, dict) or item.get('type') not in PROCESS_TYPES or item.get('target') not in ('rhythm','pitch','velocity','duration','density','accent'):
                raise ValueError('Invalid process')
            if item['type'] == 'Parameter Modulation': continue
            result['processes'].append({'type': item['type'], 'target': item['target'],
                'amount': max(0., min(1., _finite(item.get('amount', .5)))), 'parameters': _parameters(item.get('parameters', {}))})
        expression = raw.get('midi_expression', {})
        if not isinstance(expression, dict): raise ValueError('Invalid MIDI expression')
        result['midi_expression'] = normalize_expression(expression)
        voices = raw.get('voices', [])
        if not isinstance(voices, list) or len(voices) > 64: raise ValueError('Invalid kit voices')
        if voices and (result['block_type'] != 'DRUM' or result['target'] == 'voice'):
            raise ValueError('Only a Drum Kit preset can contain voices')
        result['voices'] = []
        for voice in voices:
            child = validate({**voice, 'format': FORMAT, 'version': VERSION, 'kind': 'block', 'target': 'voice',
                              'block_type': 'DRUM', 'voices': [], 'name': 'Drum Voice'})
            result['voices'].append(child)
    return result


def capture(engine, block, kind, name, description=''):
    influence = engine.parameter_influence
    algorithm = influence.document_attributes(block).get('algorithm', block.algorithm)
    parameters = influence.document_parameters(block)
    if kind == 'algorithm':
        if getattr(block, 'drum_voices', None): raise ValueError('Select an individual Drum Voice to save its algorithm')
        defaults = algorithm_defaults(algorithm, engine.project.length)
        parameters = {key: deepcopy(parameters.get(key, default)) for key, default in defaults.items()}
    result = {'format': FORMAT, 'version': VERSION, 'id': uuid.uuid4().hex, 'kind': kind,
              'name': name, 'description': description, 'algorithm': algorithm, 'parameters': parameters}
    if kind == 'block':
        result.update(block_type=block.block_type, target='voice' if getattr(block, 'is_drum_voice', False) else 'block',
                      mode=block.mode, mutators=[asdict(m) for m in block.mutators],
                      processes=[asdict(p) for p in block.processes], midi_expression=deepcopy(block.midi_expression),
                      voices=[capture(engine, v, 'block', 'Drum Voice') for v in block.drum_voices or []] if hasattr(block, 'drum_voices') else [])
    return validate(result)


def compatible(preset, block):
    if preset['kind'] == 'algorithm':
        return not getattr(block, 'drum_voices', None)
    if preset['block_type'] != block.block_type or (preset['target'] == 'voice') != bool(getattr(block, 'is_drum_voice', False)):
        return False
    voices = getattr(block, 'drum_voices', None) or []
    return Counter(v['parameters'].get('kit_role', 'perc') for v in preset['voices']) == Counter(voice_role(v) for v in voices)


def prepared_parameters(engine, block, preset):
    """Resolve types and current-project ranges before changing any live object."""
    candidate = replace(block, algorithm=preset['algorithm'], parameters={})
    # Preview must never reconcile a disposable object's empty parameters
    # against the live object's influence entry with the same entity id.
    reader = SimpleNamespace(project=engine.project, parameter_catalog=engine.parameter_catalog,
                             parameter_influence=ParameterInfluence())
    specs = parameter_specs(reader, candidate)
    raw = deepcopy(preset['parameters'])
    if preset['kind'] == 'algorithm':
        raw = {**algorithm_defaults(preset['algorithm'], engine.project.length), **raw}
    result = {}
    for key, value in raw.items():
        if key in PROTECTED: continue
        spec = specs.get(key)
        if key in ('markov_scale', 'walk_quantize'): value = bool(value)
        elif spec is not None:
            value = spec.coerce(value)
        elif key == 'pattern_step_chances': value = list(value)
        result[key] = value
    for steps, pulses, rotation in (('euclidean_steps','pulses','euclidean_rotation'), ('bres_steps','bres_pulses','bres_rotation')):
        if steps in result:
            if pulses in result: result[pulses] = min(result[pulses], result[steps])
            if rotation in result: result[rotation] = min(result[rotation], result[steps]-1)
    return result


def apply(engine, block, raw):
    """Must run on the transport command queue. Preserve identities and influences."""
    preset = validate(raw)
    if not compatible(preset, block): raise ValueError('Preset requires the same block type and Drum Voice roles')
    pairs = [(block, preset)]
    buckets = defaultdict(list)
    for voice in getattr(block, 'drum_voices', None) or []: buckets[voice_role(voice)].append(voice)
    for voice in preset.get('voices', []): pairs.append((buckets[voice['parameters'].get('kit_role', 'perc')].pop(0), voice))
    plans = [(target, data, prepared_parameters(engine, target, data)) for target, data in pairs]
    influence = engine.parameter_influence
    for target, data, parameters in plans:
        if data['kind'] == 'algorithm':
            keys = set(algorithm_defaults(data['algorithm'], engine.project.length))
        else:
            keys = set(influence.document_parameters(target)) | {key for owner, key in influence.entries if owner == target.id and not key.startswith('@')}
        for key in keys - set(parameters) - PROTECTED - {'kit_role'}:
            influence.unset_manual(target, key)
        influence.manual(target, '@algorithm', data['algorithm'])
        for key, value in parameters.items():
            if key == 'kit_role' and getattr(target, 'is_drum_voice', False): continue
            influence.manual(target, key, value)
        if data['kind'] == 'block':
            target.mode = data['mode']
            target.mutators = [Mutator(**row) for row in data['mutators']]
            links = [p for p in target.processes if p.type == 'Parameter Modulation']
            target.processes = [Process(**deepcopy(row)) for row in data['processes']] + links
            target.midi_expression = deepcopy(data['midi_expression'])
    engine.reset_live(block)
    engine.regenerate(block)


class PresetStore:
    """One atomic, portable JSON file per user preset; damaged files stay intact."""
    def __init__(self, directory): self.directory = Path(directory)

    def list(self):
        result, errors = [], []
        if not self.directory.exists(): return result, errors
        for path in sorted(self.directory.glob('*.json')):
            try: result.append(self.read(path))
            except (OSError, ValueError, RecursionError) as exc: errors.append(f'{path.name}: {exc}')
        return result, errors

    @staticmethod
    def read(path):
        with Path(path).open('rb') as stream: data = stream.read(MAX_BYTES+1)
        if len(data) > MAX_BYTES: raise ValueError('Preset file exceeds 2 MB')
        try: raw = json.loads(data)
        except (UnicodeError, json.JSONDecodeError): raise ValueError('Invalid JSON preset') from None
        return validate(raw)

    @staticmethod
    def write(path, preset):
        data = json.dumps(validate(preset), ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
        if len(data) > MAX_BYTES: raise ValueError('Preset file exceeds 2 MB')
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.preset-', delete=False) as stream:
                temporary = stream.name
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and os.path.exists(temporary): os.unlink(temporary)

    def save(self, preset):
        result = validate(preset)
        result['id'] = uuid.uuid4().hex
        self.write(self.directory / (result['id']+'.json'), result)
        return result

    def delete(self, preset):
        identity = preset['id']
        if len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity): raise ValueError('Not a user preset')
        (self.directory / (identity+'.json')).unlink()
