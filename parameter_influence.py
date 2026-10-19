"""Provenance for parameter writes, independent of widgets and transport time."""
from __future__ import annotations

from copy import deepcopy


class ParameterInfluence:
    """Keep manual values separate from automatic writes to the existing model.

    Rows describe writes, not additive routes: the last writer wins. Output
    transforms (e.g. Energy's velocity gain) are reported separately by the UI.
    """
    def __init__(self):
        self.entries = {}
        self.serial = 0

    def _reconcile(self, block, key):
        entry = self.entries.get((block.id, key))
        if entry is not None and (key in block.parameters, block.parameters.get(key)) != entry['last']:
            self.entries.pop((block.id, key), None)
            entry = None
        return entry

    def manual(self, block, key, value):
        self.entries.pop((block.id, key), None)
        block.parameters[key] = value

    def write(self, block, key, value, source):
        entry = self._reconcile(block, key)
        if entry is None:
            entry = {'base': (key in block.parameters, deepcopy(block.parameters.get(key))), 'rows': {}}
            self.entries[(block.id, key)] = entry
        before = deepcopy(block.parameters.get(key))
        block.parameters[key] = value
        self.serial += 1
        entry['last'] = (True, deepcopy(value))
        entry['rows'][str(source)] = {'source': str(source), 'before': before,
                                     'value': deepcopy(value), 'order': self.serial}

    def document_parameters(self, block):
        result = deepcopy(block.parameters)
        for owner, key in list(self.entries):
            if owner != block.id:
                continue
            entry = self._reconcile(block, key)
            if entry is not None:
                exists, value = entry['base']
                if exists:
                    result[key] = deepcopy(value)
                else:
                    result.pop(key, None)
        return result

    def describe(self, block, key, default=None):
        entry = self._reconcile(block, key)
        base = entry['base'][1] if entry and entry['base'][0] else default
        if entry is None:
            base = block.parameters.get(key, default)
        return {'base': base, 'current': block.parameters.get(key, default),
                'writes': sorted(deepcopy(list(entry['rows'].values())), key=lambda r: r['order']) if entry else []}
