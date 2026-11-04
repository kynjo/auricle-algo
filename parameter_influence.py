"""Deterministic parameter layers with persisted, per-parameter policies."""
from __future__ import annotations

import math
from copy import deepcopy

KINDS = ('Macro', 'Technique', 'Modulation', 'Composition')
DEFAULT_PRIORITY = ('Composition', 'Technique', 'Modulation', 'Macro')  # highest first


def number(value, default=0.):
    try:
        value = float(value)
        return value if math.isfinite(value) else float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def source_kind(source):
    source = str(source)
    if source.startswith('Composition:'): return 'Composition'
    if source.startswith('Macro:'): return 'Macro'
    if source.startswith('Technique:') or source == 'Phrase release': return 'Technique'
    return 'Modulation'


def normalized_policy(data=None):
    data = data if isinstance(data, dict) else {}
    priority = [kind for kind in data.get('priority', []) if kind in KINDS]
    priority = list(dict.fromkeys(priority))
    if 'Composition' not in priority:
        priority.insert(0, 'Composition')
    priority.extend(kind for kind in DEFAULT_PRIORITY if kind not in priority)
    weights = data.get('weights', {})
    weights = weights if isinstance(weights, dict) else {}
    return {'mode': data.get('mode') if data.get('mode') in ('priority', 'blend', 'manual') else 'priority',
            'priority': priority,
            'weights': {kind: max(0., min(1., number(weights.get(kind, 1), 1))) for kind in ('Manual', *KINDS)}}


_DEFAULT_POLICY = normalized_policy()


class ParameterInfluence:
    def __init__(self, project=None):
        self.project = project
        self.entries = {}
        self.serial = 0
        self.specs = {}
        self.discrete_specs = {}
        self._policy_cache = {}

    @staticmethod
    def _read(block, key):
        if key == '@algorithm':
            return True, block.algorithm
        return key in block.parameters, block.parameters.get(key)

    @staticmethod
    def _assign(block, key, exists, value):
        if key == '@algorithm':
            block.algorithm = str(value)
        elif exists:
            block.parameters[key] = deepcopy(value)
        else:
            block.parameters.pop(key, None)

    def current_value(self, block, key, default=None):
        exists, value = self._read(block, key)
        return value if exists else default

    def configure_discrete(self, block, key, default, choices=()):
        self.discrete_specs[(block.id, key)] = (default, tuple(choices))

    def policy(self, block, key):
        data = getattr(self.project, 'parameter_policies', {}) or {}
        return normalized_policy(data.get(str(block.id), {}).get(key))

    def _policy_for(self, block, key):
        """Read-only resolver policy; avoid normalizing defaults on every tick."""
        data = (getattr(self.project, 'parameter_policies', {}) or {}).get(str(block.id), {}).get(key)
        if not isinstance(data, dict):
            return _DEFAULT_POLICY
        signature = repr(data)
        target = (block.id, key)
        cached = self._policy_cache.get(target)
        if cached is None or cached[0] != signature:
            cached = (signature, normalized_policy(data))
            self._policy_cache[target] = cached
        return cached[1]

    def set_policy(self, block, key, policy):
        if self.project is None: return
        policies = self.project.parameter_policies
        policies.setdefault(str(block.id), {})[key] = normalized_policy(policy)
        entry = self._reconcile(block, key)
        if entry is not None: self._resolve(block, key, entry)

    def configure(self, block, key, default, low, high, integer=False, boolean=False):
        self.specs[(block.id, key)] = (default, low, high, integer, boolean)

    def _reconcile(self, block, key):
        entry = self.entries.get((block.id, key))
        if entry is not None and self._read(block, key) != entry['last']:
            # Direct external writes are manual edits. Keep their new base;
            # callers using manual() also resolve the automatic layers now.
            entry['base'] = deepcopy(self._read(block, key))
            entry['last'] = deepcopy(self._read(block, key))
        return entry

    def base_value(self, block, key, default=None):
        entry = self._reconcile(block, key)
        if entry is None: return self.current_value(block, key, default)
        return entry['base'][1] if entry['base'][0] else default

    def manual(self, block, key, value):
        entry = self._reconcile(block, key)
        if entry is None:
            self._assign(block, key, True, value)
        else:
            entry['base'] = (True, deepcopy(value))
            self._resolve(block, key, entry)

    def unset_manual(self, block, key):
        """Restore an implicit default while retaining active automatic layers."""
        entry = self._reconcile(block, key)
        if entry is None:
            self._assign(block, key, False, None)
        else:
            entry['base'] = (False, None)
            self._resolve(block, key, entry)

    def write(self, block, key, value, source, *, source_id=None, weight=1.):
        entry = self._reconcile(block, key)
        if entry is None:
            entry = {'base': deepcopy(self._read(block, key)), 'rows': {}}
            self.entries[(block.id, key)] = entry
        before = deepcopy(self.current_value(block, key))
        self.serial += 1
        identity = str(source_id if source_id is not None else source)
        entry['rows'][identity] = {'id': identity, 'source': str(source), 'kind': source_kind(source),
                                  'before': before, 'value': deepcopy(value) if (block.id, key) in self.discrete_specs else number(value), 'weight': max(0., min(1., number(weight))),
                                  'order': self.serial}
        self._resolve(block, key, entry)

    def _resolve(self, block, key, entry):
        discrete = self.discrete_specs.get((block.id, key))
        if discrete is not None:
            result = entry['base'][1] if entry['base'][0] else discrete[0]
            policy = self._policy_for(block, key)
            if policy['mode'] != 'manual':
                for kind in policy['priority']:
                    rows = [row for row in entry['rows'].values() if row['kind'] == kind
                            and row['weight'] > 0 and policy['weights'][kind] > 0]
                    if rows:
                        # Choices/text cannot be averaged. Stable route ids,
                        # rather than arrival order, settle duplicate sources.
                        result = sorted(rows, key=lambda row: row['id'])[0]['value']
                        break
            if discrete[1] and result not in discrete[1]:
                result = discrete[0]
            self._publish(block, key, entry, result)
            return
        spec = self.specs.get((block.id, key))
        default = spec[0] if spec else 0.
        base = number(entry['base'][1] if entry['base'][0] else default)
        policy = self._policy_for(block, key)
        groups = {}
        for kind in KINDS:
            rows = [row for row in entry['rows'].values() if row['kind'] == kind and row['weight'] > 0]
            total = math.fsum(row['weight'] for row in rows)
            if total > 0:
                # A category's weight does not grow with its route count.
                value = math.fsum(row['value'] * row['weight'] for row in rows) / total
                groups[kind] = (value, max(row['weight'] for row in rows) * policy['weights'][kind])
        result = base
        if policy['mode'] == 'priority':
            for kind in reversed(policy['priority']):
                if kind in groups:
                    value, weight = groups[kind]
                    result += (value - result) * weight
        elif policy['mode'] == 'blend':
            total = policy['weights']['Manual'] + math.fsum(weight for _, weight in groups.values())
            if total > 0:
                result = (base * policy['weights']['Manual'] + math.fsum(value * weight for value, weight in groups.values())) / total
        if spec:
            _, low, high, integer, boolean = spec
            result = max(low, min(high, result))
            result = bool(result >= .5) if boolean else int(round(result)) if integer else float(result)
        self._publish(block, key, entry, result)

    def _publish(self, block, key, entry, result):
        if not entry['rows']:
            exists, value = entry['base']
            self._assign(block, key, exists, value)
            self.entries.pop((block.id, key), None)
        else:
            self._assign(block, key, True, result)
            entry['last'] = (True, deepcopy(result))

    def remove(self, block, *, source_id=None, prefix=None, key=None):
        changed = False
        selected_key = key
        for (owner, key), entry in list(self.entries.items()):
            if owner != block.id: continue
            if selected_key is not None and selected_key != key: continue
            self._reconcile(block, key)
            ids = [identity for identity in entry['rows'] if identity == source_id or (prefix is not None and identity.startswith(prefix))]
            if not ids: continue
            before = deepcopy(self._read(block, key))
            for identity in ids: entry['rows'].pop(identity)
            self._resolve(block, key, entry)
            changed |= before != self._read(block, key)
        return changed

    def prune(self, blocks, prefix, active_ids):
        changed = []
        for block in blocks:
            for (owner, key), entry in list(self.entries.items()):
                if owner != block.id: continue
                for identity in list(entry['rows']):
                    if identity.startswith(prefix) and identity not in active_ids:
                        if self.remove(block, source_id=identity) and block not in changed: changed.append(block)
        return changed

    def document_parameters(self, block):
        result = deepcopy(block.parameters)
        for owner, key in list(self.entries):
            if owner != block.id: continue
            if key.startswith('@'): continue
            entry = self._reconcile(block, key)
            exists, value = entry['base']
            if exists: result[key] = deepcopy(value)
            else: result.pop(key, None)
        return result

    def document_attributes(self, block):
        entry = self._reconcile(block, '@algorithm')
        return {'algorithm': deepcopy(entry['base'][1])} if entry else {}

    def contributions(self, block, key):
        policy = self._policy_for(block, key)
        entry = self.entries.get((block.id, key))
        rows = entry['rows'].values() if entry else ()
        weights = {kind: max((row['weight'] for row in rows if row['kind'] == kind), default=0.)
                   * policy['weights'][kind] for kind in KINDS}
        if policy['mode'] == 'manual':
            return dict.fromkeys(KINDS, 0.)
        if (block.id, key) in self.discrete_specs:
            winner = next((kind for kind in policy['priority'] if weights[kind] > 0), None)
            return {kind: float(kind == winner) for kind in KINDS}
        if policy['mode'] == 'blend':
            total = policy['weights']['Manual'] + math.fsum(weights.values())
            return {kind: weight / total if total else 0. for kind, weight in weights.items()}
        remaining, result = 1., {}
        for kind in policy['priority']:
            result[kind] = remaining * weights[kind]
            remaining *= 1. - weights[kind]
        return result

    def describe(self, block, key, default=None):
        entry = self._reconcile(block, key)
        policy = self.policy(block, key)
        rows = deepcopy(list(entry['rows'].values())) if entry else []
        active = [kind for kind in policy['priority'] if any(row['kind'] == kind and row['weight'] > 0 for row in rows)
                  and policy['weights'][kind] > 0]
        discrete = (block.id, key) in self.discrete_specs
        winner = active[0] if (policy['mode'] == 'priority' or discrete) and active and policy['mode'] != 'manual' else None
        contributions = self.contributions(block, key)
        for row in rows:
            weight = policy['weights'][row['kind']] * row['weight']
            row['status'] = 'Disabled' if policy['mode'] == 'manual' or weight <= 0 else 'Blended' if policy['mode'] == 'blend' and not discrete else 'Priority' if row['kind'] == winner else 'Underlying'
            row['effective_weight'] = weight
            row['contribution'] = contributions[row['kind']]
        return {'base': self.base_value(block, key, default), 'current': self.current_value(block, key, default),
                'policy': policy, 'winner': winner, 'discrete': discrete,
                'writes': sorted(rows, key=lambda row: (policy['priority'].index(row['kind']), row['id']))}
