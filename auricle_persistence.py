"""Persistence for the current v107 project schema."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, fields

from auricle_catalogs import apply_role_defaults
from auricle_model import Block, DrumVoice, Mutator, Process, Project, Relation, ensure_drum_voices

def _from_dict(cls, data: dict):
    """Build a dataclass from JSON, ignoring keys this version does not know."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in dict(data).items() if k in names})


def _json_default(value):
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def save_project(project: Project, filename: str):
    """Write a project atomically.

    The JSON is fully serialized first and written to a temporary file that
    replaces the target only on success; a failure used to leave a truncated,
    unreadable project file.  Runtime owners should call
    director.sync_project() before saving; Project remains pure data.
    """
    data = json.dumps(asdict(project), indent=2, ensure_ascii=False, default=_json_default)
    target = os.path.abspath(filename)
    fd, tmp = tempfile.mkstemp(prefix=".auricle-", suffix=".tmp", dir=os.path.dirname(target) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_project(filename: str) -> Project:
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)
    blocks = []
    for index, b in enumerate(data.get("blocks", []), start=1):
        block_type = str(b.get("block_type", "MELODY")).upper()
        if block_type not in ("DRUM", "BASS", "MELODY", "PAD", "CHORD"):
            raise ValueError(f"Unsupported v107 block type: {block_type}")
        voice_payload = b.get("drum_voices") if block_type == "DRUM" else None
        blocks.append(Block(
            id=int(b.get("id", index)),
            name=str(b.get("name", f"BLOCK {index}")),
            block_type=block_type,
            algorithm=b.get("algorithm", "Euclidean"),
            mode=b.get("mode", "SEQ"),
            midi_channel=b.get("midi_channel", 1),
            midi_port=b.get("midi_port", ""),
            midi_note=b.get("midi_note", 60),
            parameters=dict(b.get("parameters", {})),
            mutators=[_from_dict(Mutator, m) for m in b.get("mutators", [])],
            processes=[_from_dict(Process, x) for x in b.get("processes", [])],
            outputs=dict(b.get("outputs", {})),
            color=b.get("color", ""),
            muted=bool(b.get("muted", False)),
            drum_voices=[_from_dict(DrumVoice, voice) for voice in voice_payload] if voice_payload is not None else None,
        ))
        apply_role_defaults(blocks[-1])
        if blocks[-1].block_type == "DRUM":
            ensure_drum_voices(blocks[-1])
        if blocks[-1].block_type == "CHORD":
            blocks[-1].parameters.setdefault("harmony_size", 3)
            blocks[-1].parameters.setdefault("harmony_spread", 7)
            blocks[-1].parameters.setdefault("harmony_inversion", 0)
    loaded_relations=[_from_dict(Relation, r) for r in data.get("relations", [])]
    used=set()
    next_id=1
    for r in loaded_relations:
        rid=int(getattr(r,"id",0))
        if rid <= 0 or rid in used:
            while next_id in used: next_id += 1
            r.id=next_id
        used.add(int(r.id)); next_id=max(next_id, int(r.id)+1)
    return Project(
        tempo=data.get("tempo", 120),
        length=data.get("length", 16),
        seed=data.get("seed", 12345),
        root_note=data.get("root_note", 60),
        scale=data.get("scale", "Major"),
        blocks=blocks,
        relations=loaded_relations,
        block_colors=data.get("block_colors", {}),
        macros=data.get("macros", []),
        performance=dict(data.get("performance", {})),
        motifs=dict(data.get("motifs", {})),
        phrase_state=dict(data.get("phrase_state", {})),
    )


