from dataclasses import asdict
from pathlib import Path

from auricle_core import Block, MusicEngine, Project, Relation, ensure_drum_voices, save_project
from auricle_catalogs import apply_role_defaults
from motif_engine import TensionCurve

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "examples" / "auricle_demo_all_blocks.json"


def with_role(block, **values):
    apply_role_defaults(block)
    block.parameters.update(values)
    return block


project = Project(
    tempo=110,
    length=16,
    seed=240114,
    root_note=62,  # D
    scale="Dorian",
    macros=[
        {"name": "Energy", "control": "energy", "value": 0.62, "routes": []},
        {"name": "Tension", "control": "tension", "value": 0.58, "routes": []},
        {"name": "Density", "control": "density", "value": 0.68, "routes": []},
        {"name": "Variation", "control": "variation", "value": 0.55, "routes": []},
    ],
)

# 1. Drum machine: six voices share channel 10 by default.
drum = Block(
    1, "DRUM KIT", "DRUM", "Euclidean", "SEQ", midi_channel=10,
    midi_note=36,
    parameters={
        "euclidean_steps": 16, "pulses": 5, "euclidean_rotation": 0,
        "fill_density": 0.94, "event_probability": 1.0, "gate": 0.78,
        "velocity_base": 0.78, "velocity_range": 0.22, "velocity_accent": 0.24,
        "timing_swing": 0.08, "timing_humanize": 0.015,
    },
)
ensure_drum_voices(drum)
voice_specs = [
    # name, algorithm, note, params
    ("KICK", "Euclidean", 36, {"euclidean_steps": 16, "pulses": 4, "euclidean_rotation": 0, "velocity_base": .88, "gate": .82}),
    ("SNARE", "Euclidean", 38, {"euclidean_steps": 16, "pulses": 2, "euclidean_rotation": 4, "velocity_base": .76, "gate": .62}),
    ("CLOSED HAT", "Euclidean", 42, {"euclidean_steps": 16, "pulses": 8, "euclidean_rotation": 0, "velocity_base": .53, "gate": .38}),
    ("OPEN HAT", "Pattern", 46, {"pattern": "0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0", "velocity_base": .55, "gate": .55}),
    ("CLAP", "Euclidean", 39, {"euclidean_steps": 16, "pulses": 2, "euclidean_rotation": 4, "velocity_base": .68, "gate": .58}),
    ("PERC", "Pattern", 50, {"pattern": "1,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0", "velocity_base": .48, "gate": .45}),
]
for voice, (name, algorithm, note, params) in zip(drum.drum_voices, voice_specs):
    voice.name = name
    voice.algorithm = algorithm
    voice.midi_note = note
    voice.midi_channel = drum.midi_channel
    voice.midi_channel_override = False
    voice.parameters.update(params)
    voice.parameters.update({"fill_density": 1.0, "event_probability": 1.0, "velocity_range": .18, "velocity_accent": .14})

# 2. Bass: a centered, quantized random walk shaped by the drum groove.
bass = with_role(Block(
    2, "BASS FOUNDATION", "BASS", "Random Walk", "SEQ", midi_channel=2, midi_note=36,
    parameters={
        "walk_step": 2, "walk_range": 9, "walk_start": 0,
        "walk_return_bias": .58, "walk_drift": .04, "walk_quantize": 1,
        "fill_density": .82, "event_probability": .96, "gate": .88,
        "velocity_base": .70, "velocity_range": .20, "velocity_accent": .16,
        "groove_follow": .78, "groove_accent": .72, "groove_mode": "Union",
        "relation_drum_source": 1, "role_center": -24, "role_width": 24,
        "role_duration": 1.05,
    },
))

# 3. Chords: patterned harmonic changes, four-note Dorian voicings.
chord = with_role(Block(
    3, "CHORDS", "CHORD", "Pattern", "SEQ", midi_channel=4, midi_note=48,
    parameters={
        "pattern": "0,0,4,0,5,0,3,0,0,0,4,0,5,0,7,0",
        "pattern_probability": .96, "pattern_scale": 1.0,
        "fill_density": .86, "event_probability": .96, "gate": 1.05,
        "velocity_base": .62, "velocity_range": .18, "velocity_accent": .12,
        "harmony_size": 4, "harmony_spread": 7, "harmony_inversion": 0,
        "chord_degree": 0, "role_center": -12, "role_width": 24,
        "role_duration": 1.15,
    },
))

# 4. Pad: weighted-scale texture with long, wide voicings.
pad = with_role(Block(
    4, "PAD TEXTURE", "PAD", "Weighted Scale", "SEQ", midi_channel=5, midi_note=48,
    parameters={
        "scale_weights": "4,2,3,2,3,1,2", "scale_octave_spread": .08,
        "structure_length": 8, "fill_density": .52, "event_probability": .86,
        "gate": 1.45, "velocity_base": .42, "velocity_range": .12,
        "velocity_accent": .06, "harmony_size": 3, "harmony_spread": 12,
        "harmony_inversion": 1, "role_center": -12, "role_width": 24,
        "role_duration": 1.80,
    },
))

# 5. Melody: live Markov line anchored to the chord authority.
melody = with_role(Block(
    5, "MELODY LEAD", "MELODY", "Markov", "LIVE", midi_channel=3, midi_note=72,
    parameters={
        "markov_jump": 3, "markov_transpose": 0, "markov_octaves": 1,
        "markov_rest": .06, "markov_leap": .14, "markov_stay": .16,
        "markov_scale": 1, "live_min_beats": .22, "live_max_beats": .62,
        "live_gate": .64, "fill_density": .84, "event_probability": .90,
        "velocity_base": .68, "velocity_range": .24, "velocity_accent": .18,
        "harmony_anchor": .78, "relation_chord_source": 3,
        "role_center": 0, "role_width": 36, "role_duration": .82,
    },
))

project.blocks = [drum, bass, chord, pad, melody]
project.relations = [
    Relation(1, "rhythm", 2, "rhythm", "Follow", .78, "Linear", 0, 1.0, True, 1),
    Relation(3, "pitch", 5, "pitch", "Follow", .72, "Linear", 0, 1.0, True, 2),
]

# A ready-to-launch phrase state. Playback is stopped on open; PLAY PHRASE
# starts it from the beginning and uses the selected blocks as targets.
curve = TensionCurve.preset("peak_release", 15.0)
project.phrase_state = {
    "phrase_id": "climax_release",
    "name": "Climax → Release",
    "position_beats": 0.0,
    "stage_index": -1,
    "intensity": .88,
    "tension": asdict(curve),
    "active_motifs": [],
    "block_ids": [b.id for b in project.blocks],
    "running": False,
    "memory": {"total_beats": 15.0},
}

# Individual techniques are prepared but disabled until the user starts them.
project.performance = {
    "1": {"preset_id": "euclidean_fill", "amount": .38, "shape": "in", "beats": 4, "enabled": False},
    "2": {"preset_id": "stringendo", "amount": .34, "shape": "in", "beats": 4, "enabled": False},
    "3": {"preset_id": "tenuto", "amount": .30, "shape": "in", "beats": 2, "enabled": False},
    "4": {"preset_id": "rubato", "amount": .26, "shape": "pulse", "beats": 8, "enabled": False},
    "5": {"preset_id": "markov_unstable", "amount": .32, "shape": "in", "beats": 8, "enabled": False},
}

engine = MusicEngine(project)
engine.generate()
save_project(project, str(OUT))
print(OUT)
print("blocks", [(b.id, b.name, b.block_type, b.algorithm, b.mode, b.midi_channel) for b in project.blocks])
print("drum_channels", sorted({v.midi_channel for v in drum.drum_voices}))
print("outputs", {b.name: len(b.outputs.get("rhythm", [])) for b in project.blocks})
