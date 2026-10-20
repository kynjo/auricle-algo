"""User-state snapshots, bounded undo/redo, and atomic crash checkpoints."""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
import uuid
from copy import deepcopy
from dataclasses import asdict, fields
from pathlib import Path


def document_state(project, engine=None):
    # Do not copy the potentially large generated output buffers on each drag.
    data = {f.name: deepcopy(getattr(project, f.name)) for f in fields(project)
            if f.name not in ('blocks', 'relations', 'phrase_state')}
    data['relations'] = [asdict(relation) for relation in project.relations]
    def clean(block):
        payload = {f.name: deepcopy(getattr(block, f.name)) for f in fields(block)
                   if f.name not in ('outputs', 'parameters', 'drum_voices', 'mutators', 'processes')}
        payload['parameters'] = (engine.parameter_influence.document_parameters(block)
                                 if engine is not None else deepcopy(block.parameters))
        payload['mutators'] = [asdict(m) for m in block.mutators]
        payload['processes'] = [asdict(p) for p in block.processes]
        if hasattr(block, 'drum_voices'):
            payload['drum_voices'] = [clean(v) for v in block.drum_voices] if block.drum_voices is not None else None
        return payload
    data['blocks'] = [clean(block) for block in project.blocks]
    # Phrase selections/settings live in performance['_phrase']. A playhead,
    # snapshots captured by PLAY and active gestures are not user edits.
    data['phrase_state'] = {}
    for key, settings in data.get('performance', {}).items():
        if not str(key).startswith('_') and isinstance(settings, dict):
            # ENABLE launches a finite gesture, like PLAY PHRASE. Its automatic
            # completion is not a document edit and must not start it on Undo.
            settings['enabled'] = False
    if engine is not None:
        data['motifs'] = {key: asdict(value) for key, value in engine.director.motifs.motifs.items()}
    return data


def encode(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def parameter_only_changes(before, after):
    """Return numeric parameter edits, or None if the UI structure may change.

    Macro values are also safe: their names, routes and order must stay intact.
    Keep this conservative; menus, patterns, chains and topology use a rebuild.
    """
    def without(data, *keys):
        return {key: value for key, value in data.items() if key not in keys}

    if without(before, 'blocks', 'macros') != without(after, 'blocks', 'macros'):
        return None
    old_macros, new_macros = before.get('macros', []), after.get('macros', [])
    if len(old_macros) != len(new_macros):
        return None
    for old, new in zip(old_macros, new_macros):
        if without(old, 'value') != without(new, 'value'):
            return None
    changes = {}
    missing = object()

    def compare(old_items, new_items):
        if len(old_items) != len(new_items):
            return False
        for old, new in zip(old_items, new_items):
            if without(old, 'parameters', 'drum_voices') != without(new, 'parameters', 'drum_voices'):
                return False
            a, b = old.get('parameters', {}), new.get('parameters', {})
            keys = {key for key in a.keys() | b.keys() if a.get(key, missing) != b.get(key, missing)}
            if any(not isinstance(values[key], (int, float))
                   for key in keys for values in (a, b) if key in values):
                return False
            if keys:
                changes[new['id']] = keys
            if (old.get('drum_voices') is None) != (new.get('drum_voices') is None):
                return False
            if not compare(old.get('drum_voices') or [], new.get('drum_voices') or []):
                return False
        return True

    return changes if compare(before.get('blocks', []), after.get('blocks', [])) else None


class ProjectHistory:
    def __init__(self, state, limit=150):
        self.limit = max(2, int(limit))
        self.reset(state)

    def reset(self, state):
        self.states = [encode(state)]
        self.index = 0
        self.clean = self.states[0]
        self.group = None

    @property
    def can_undo(self): return self.index > 0
    @property
    def can_redo(self): return self.index + 1 < len(self.states)
    @property
    def dirty(self): return self.states[self.index] != self.clean

    def commit(self, state, group=None):
        value = encode(state)
        if self.states[self.index] == value:
            return False
        del self.states[self.index + 1:]
        if group is not None and group == self.group and self.index > 0:
            self.states[self.index] = value
        else:
            self.states.append(value)
            self.index += 1
        self.group = group
        if len(self.states) > self.limit:
            self.states.pop(0)
            self.index -= 1
        return True

    def mark_clean(self):
        self.clean = self.states[self.index]
        self.group = None

    def undo(self):
        if self.can_undo: self.index -= 1
        self.group = None
        return json.loads(self.states[self.index])

    def redo(self):
        if self.can_redo: self.index += 1
        self.group = None
        return json.loads(self.states[self.index])


class RecoveryStore:
    """One file per session; another running instance's file is never replaced."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / ('session-' + uuid.uuid4().hex + '.json')

    def write(self, state, source_path=None):
        payload = encode({'schema': 1, 'time': time.time(), 'pid': os.getpid(),
                          'source_path': str(source_path) if source_path else None, 'project': state})
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.checkpoint-', suffix='.tmp', dir=self.directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            try: os.unlink(name)
            except FileNotFoundError: pass

    def clear(self):
        self.path.unlink(missing_ok=True)

    def candidates(self):
        from auricle_persistence import project_from_dict
        result = []
        for path in self.directory.glob('session-*.json'):
            if path == self.path: continue
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
                if payload.get('schema') != 1 or not isinstance(payload['project'].get('blocks'), list): continue
                timestamp = float(payload.get('time', 0))
                if not math.isfinite(timestamp) or not 0 <= timestamp <= time.time()+86400: continue
                project_from_dict(payload['project'])
                result.append((path, payload))
            except (ValueError, TypeError, KeyError, OSError, AttributeError):
                continue
        return sorted(result, key=lambda item: float(item[1].get('time', 0)), reverse=True)


def process_alive(pid):
    """Probe ownership without sending signals on Windows (kill(pid, 0) is unsafe there)."""
    if not isinstance(pid, int) or pid <= 0: return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle: return ctypes.get_last_error() == 5  # access denied: do not take ownership
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError: return False
    except PermissionError: return True
