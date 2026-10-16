"""Current v107 project model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from auricle_catalogs import DRUM_VOICE_DEFAULTS, PARTS, PERCUSSIVE_TYPES, ROLE_PROFILES, _clamp, apply_role_defaults

@dataclass
class Process:
    type: str
    target: str = "pitch"
    amount: float = 0.5
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Mutator:
    name: str
    amount: float = 0.5
    target: str = "pitch"  # rhythm, pitch, velocity


@dataclass
class DrumVoice:
    """Independent child generator owned by a DRUM block."""
    id: int
    parent_id: int
    name: str
    block_type: str = "DRUM"
    algorithm: str = "Pattern"
    mode: str = "SEQ"
    midi_channel: int = 1
    # False means the voice follows its parent DRUM channel. Editing the
    # voice channel in the kit turns this into an explicit per-voice override.
    midi_channel_override: bool = False
    midi_port: str = ""
    midi_note: int = 36
    parameters: dict[str, Any] = field(default_factory=dict)
    mutators: list[Mutator] = field(default_factory=list)
    processes: list[Process] = field(default_factory=list)
    outputs: dict[str, list[float]] = field(default_factory=dict)
    color: str = ""
    muted: bool = False
    is_drum_voice: bool = True


@dataclass
class MusicalRepresentation:
    """Musical meaning produced by a generator before MIDI output."""
    rhythm: list[float]
    pitch: list[float]
    velocity: list[float]
    duration: list[float]
    density: list[float]
    accent: list[float]

    def as_outputs(self) -> dict[str, list[float]]:
        return {part: list(getattr(self, part)) for part in PARTS}


@dataclass
class Block:
    id: int
    name: str
    block_type: str
    algorithm: str = "Euclidean"
    mode: str = "SEQ"  # SEQ = cached material, LIVE = continuously generated events
    midi_channel: int = 1  # musician-facing 1..16
    midi_port: str = ""
    midi_note: int = 60
    parameters: dict[str, Any] = field(default_factory=dict)
    mutators: list[Mutator] = field(default_factory=list)
    processes: list[Process] = field(default_factory=list)
    outputs: dict[str, list[float]] = field(default_factory=dict)
    # Optional per-block accent color. If empty, the GUI falls back to the
    # legacy block-type color stored in Project.block_colors.
    color: str = ""
    muted: bool = False
    # None means a legacy/simple DRUM block that has not been upgraded to the
    # Drum Machine container yet. The GUI and project loader materialize voices.
    drum_voices: Optional[list[DrumVoice]] = None

    def __post_init__(self):
        # Every block starts with the three basic pitch-shaping stages.
        # Existing custom mutators are preserved and duplicates are not added.
        existing = {m.name for m in self.mutators}
        for name in ("Transpose", "Scale", "Octave"):
            if name not in existing:
                self.mutators.append(Mutator(name, 0.5, "pitch"))


def make_default_drum_voices(parent: Block) -> list[DrumVoice]:
    """Create the six editable voices of a new Drum Machine."""
    voices = []
    for index, (name, algorithm, note, parameters) in enumerate(DRUM_VOICE_DEFAULTS, 1):
        # Negative ids cannot collide with ordinary project block ids and are
        # stable across saves. They are runtime owners, not relation targets.
        voice_id = -(abs(int(parent.id)) * 100 + index)
        voice_params = {
            "gate": 0.78, "live_gate": 0.65, "fill_density": 1.0,
            "event_probability": 1.0, "timing_rate": 1.0,
            "timing_swing": 0.0, "timing_humanize": 0.0,
            "timing_offset": 0.0, "velocity_base": 0.72,
            "velocity_range": 0.25, "velocity_accent": 0.18,
        }
        voice_params.update(parameters)
        voices.append(DrumVoice(
            id=voice_id, parent_id=int(parent.id), name=name,
            algorithm=algorithm, mode=str(parent.mode),
            midi_channel=int(parent.midi_channel), midi_channel_override=False,
            midi_port=str(parent.midi_port or ""), midi_note=note,
            parameters=voice_params,
        ))
    return voices


def ensure_drum_voices(block: Block) -> list[DrumVoice]:
    """Materialize child voices for a DRUM block exactly once."""
    if str(block.block_type).upper() != "DRUM":
        return []
    if not getattr(block, "drum_voices", None):
        block.drum_voices = make_default_drum_voices(block)
    for voice in block.drum_voices:
        voice.parent_id = int(block.id)
        voice.block_type = "DRUM"
        voice.is_drum_voice = True
        if not bool(getattr(voice, "midi_channel_override", False)):
            voice.midi_channel = int(parent_channel := max(1, min(16, int(block.midi_channel))))
        if not voice.midi_port:
            voice.midi_port = str(block.midi_port or "")
    return block.drum_voices


@dataclass
class Relation:
    """A model-only connection between two musical dimensions.

    The UI deliberately treats this as plain data.  New fields are appended
    with defaults so old positional Relation(...) calls and old project JSON
    remain compatible.
    """
    source_block: int
    source_part: str
    destination_block: int
    destination_part: str
    algorithm: str
    amount: float = 0.5
    curve: str = "Linear"
    delay: int = 0
    probability: float = 1.0
    enabled: bool = True
    id: int = 0


@dataclass
class Project:
    tempo: int = 120
    length: int = 16
    seed: int = 12345
    root_note: int = 60
    scale: str = "Major"
    blocks: list[Block] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    block_colors: dict[str, str] = field(default_factory=dict)
    macros: list[dict[str, Any]] = field(default_factory=list)
    performance: dict[str, dict[str, Any]] = field(default_factory=dict)
    motifs: dict[str, dict[str, Any]] = field(default_factory=dict)
    phrase_state: dict[str, Any] = field(default_factory=dict)


def block_root(project: Any, block: Block) -> int:
    """Scale root used by a block (block override, else project root)."""
    try:
        return int(block.parameters.get("scale_root", getattr(project, "root_note", 60)))
    except (TypeError, ValueError):
        return 60


def midi_note_for(project: Any, block: Block, pitch: float) -> int:
    """Translate a generated pitch offset into the MIDI note that is sent.

    Pitched blocks are transposed by the key (pitch class of the scale root),
    so the KEY selector actually changes what is played. DRUM blocks always
    send their fixed base note.
    """
    try:
        base = int(block.midi_note)
    except (TypeError, ValueError):
        base = 60
    if block.block_type in PERCUSSIVE_TYPES:
        return int(_clamp(base, 0, 127))
    key = block_root(project, block) % 12
    return int(_clamp(round(base + key + float(pitch or 0.0)), 0, 127))


