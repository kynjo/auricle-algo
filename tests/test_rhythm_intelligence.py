from types import SimpleNamespace

import pytest

from auricle_core import Block, DrumVoice, MusicEngine, Project
from auricle_model import MusicalRepresentation
from coordinated_kit import KitStep
from rhythm_intelligence import (
    ANCHOR, SUPPORT, ORNAMENT, classify_event, class_probability,
    density_probability,
)


def block(role, **parameters):
    return SimpleNamespace(
        block_type=role,
        name=role,
        midi_note=60,
        is_drum_voice=False,
        parameters=parameters,
    )


def test_metric_classification_distinguishes_anchor_support_and_ornament():
    kick = block("DRUM", kit_role="kick")
    snare = block("DRUM", kit_role="snare")
    hat = block("DRUM", kit_role="closed_hat")
    bass = block("BASS")
    melody = block("MELODY")

    assert classify_event(kick, 0.0)[0] == ANCHOR
    assert classify_event(kick, 2.0)[0] == ANCHOR
    assert classify_event(kick, 1.0)[0] == SUPPORT
    assert classify_event(kick, 1.25)[0] == ORNAMENT
    assert classify_event(snare, 1.0)[0] == ANCHOR
    assert classify_event(hat, 0.0)[0] == ANCHOR
    assert classify_event(hat, 0.5)[0] == SUPPORT
    assert classify_event(hat, 0.25)[0] == ORNAMENT
    assert classify_event(bass, 2.0)[0] == ANCHOR
    assert classify_event(melody, 0.0)[0] == ANCHOR
    assert classify_event(melody, 4.0)[0] == SUPPORT
    assert classify_event(melody, 0.0, phrase_awareness=False)[0] == SUPPORT


def test_compound_and_uneven_meters_have_meter_aware_anchor_positions():
    kick = block("DRUM", kit_role="kick")
    snare = block("DRUM", kit_role="snare")
    assert classify_event(kick, 1.5, meter=(6, 8))[0] == ANCHOR
    assert classify_event(snare, 1.5, meter=(6, 8))[0] == ANCHOR
    assert classify_event(kick, 2.0, meter=(7, 8))[0] == ANCHOR
    assert classify_event(snare, 1.0, meter=(7, 8))[0] == ANCHOR


def test_coordinated_kit_metadata_separates_hat_quarters_eighths_and_sixteenths():
    hat = block("DRUM", kit_role="closed_hat")
    assert classify_event(hat, 0, kit_step=KitStep(True, True, .9, False, True, 1))[0] == ANCHOR
    # The kit editor protects its eighth-note hat pulse in the Keep-beat mask,
    # but the probability engine treats non-downbeat hats as Support.
    assert classify_event(hat, .5, kit_step=KitStep(True, True, .7, False, True, .7))[0] == SUPPORT
    assert classify_event(hat, .25, kit_step=KitStep(True, False, .4, False, False, .25))[0] == ORNAMENT
    assert classify_event(hat, .75, kit_step=KitStep(True, True, .8, True, False, .8))[0] == ORNAMENT


def test_class_probability_and_density_semantics_are_bounded_and_anchor_aware():
    assert class_probability({"anchor_strength": 0.4}, ANCHOR) == pytest.approx(.4)
    assert class_probability({"support_probability": 3}, SUPPORT) == 1
    assert class_probability({"ornament_probability": -1}, ORNAMENT) == 0
    assert density_probability(ANCHOR, .01, 0) == 1
    assert density_probability(ANCHOR, 0, 1) == 0
    assert density_probability(SUPPORT, .4, .1) == pytest.approx(.4)
    assert density_probability(ORNAMENT, .4, .25) == pytest.approx(.2)
    assert density_probability(ORNAMENT, .4, 1) == pytest.approx(.4)


def test_engine_event_gate_uses_class_probability_and_is_deterministic():
    lead = Block(
        1, "Lead", "MELODY", "Pattern", "SEQ", mutators=[],
        parameters={"pattern": "1", "event_probability": 1.0,
                    "anchor_strength": .35, "support_probability": 0.0,
                    "ornament_probability": 0.0},
    )
    project = Project(seed=917, length=16, blocks=[lead])
    engine = MusicEngine(project)
    first = engine.event_gate_allowed(lead, 0.0)
    second = MusicEngine(Project(seed=917, length=16, blocks=[lead])).event_gate_allowed(lead, 0.0)
    assert first is second
    assert not engine.event_gate_allowed(lead, 1.0)  # support probability is zero
    assert not engine.event_gate_allowed(lead, .25)  # ornament probability is zero


def test_parent_and_voice_probabilities_combine_and_global_probability_can_mute_anchor():
    voice = DrumVoice(
        -101, 1, "KICK", midi_note=36,
        parameters={"kit_role": "kick", "anchor_strength": 1.0,
                      "support_probability": 0.0, "ornament_probability": 1.0},
    )
    drum = Block(1, "Kit", "DRUM", mutators=[],
                 parameters={"kit_coordinated": True, "event_probability": 1.0,
                             "anchor_strength": 1.0}, drum_voices=[voice])
    project = Project(seed=21, blocks=[drum])
    engine = MusicEngine(project)
    assert engine.event_gate_allowed(voice, 0.0)  # downbeat anchor
    assert not engine.event_gate_allowed(voice, 1.0)  # support is explicitly disabled
    drum.parameters["event_probability"] = 0.0
    assert not engine.event_gate_allowed(voice, 0.0)  # master Probability overrides anchors


def test_positive_density_preserves_anchor_but_zero_density_is_absolute_silence():
    lead = Block(
        2, "Lead", "MELODY", "Pattern", "SEQ", mutators=[],
        parameters={"pattern": "1,1,1,1", "fill_density": .01,
                    "event_probability": 1.0, "anchor_strength": 1.0},
    )
    engine = MusicEngine(Project(seed=42, length=4, blocks=[lead]))
    engine.generate_block(lead)
    assert lead.outputs["rhythm"][0] == 1.0
    lead.parameters["fill_density"] = 0.0
    engine.generate_block(lead)
    assert not any(lead.outputs["rhythm"])


def test_probability_controls_are_exposed_in_parameter_catalog():
    lead = Block(3, "Lead", "MELODY", "Pattern", mutators=[])
    catalog = MusicEngine(Project(blocks=[lead])).parameter_catalog(lead)
    assert catalog["anchor_strength"] == (1.0, 0.0, 1.0)
    assert catalog["support_probability"] == (1.0, 0.0, 1.0)
    assert catalog["ornament_probability"] == (1.0, 0.0, 1.0)


def test_musical_event_preserves_event_class_metadata():
    from musical_events import MusicalEvent
    event = MusicalEvent.from_mapping(
        {"pitch": 0, "velocity": .8, "duration": .5,
         "event_class": "ornament", "importance": .2},
        beat=.25, interval_beats=.25,
    )
    assert event.to_mapping()["event_class"] == "ornament"
    assert event.to_mapping()["importance"] == pytest.approx(.2)


def test_global_variation_thins_ornaments_without_removing_anchor_or_support():
    def render(variation):
        lead = Block(
            8, "Lead", "MELODY", "Pattern", "SEQ", mutators=[],
            parameters={"pattern": "1,1,1,1,1,1,1,1", "fill_density": 1.0,
                        "event_probability": 1.0},
        )
        engine = MusicEngine(Project(seed=88, length=8, blocks=[lead]))
        engine.director.set_global_macro("variation", variation)
        engine.generate_block(lead)
        return lead.outputs["rhythm"]

    restrained = render(0.0)
    neutral = render(.5)
    assert restrained[0] == 1.0       # phrase anchor
    assert restrained[4] == 1.0       # quarter-note support
    assert all(restrained[index] == 0.0 for index in (1, 2, 3, 5, 6, 7))
    assert sum(neutral) > sum(restrained)


def test_seq_and_live_class_gates_share_the_same_seeded_decision():
    decisions = []
    for mode in ("SEQ", "LIVE"):
        lead = Block(
            9, "Lead", "MELODY", "Pattern", mode, mutators=[],
            parameters={"pattern": "1", "event_probability": 1.0,
                        "support_probability": .43, "phrase_awareness": False},
        )
        engine = MusicEngine(Project(seed=199, length=16, blocks=[lead]))
        decisions.append(engine.event_gate_allowed(lead, .25))
    assert decisions[0] is decisions[1]


def test_live_event_carries_its_anchor_class_for_transport_and_monitoring():
    kick = Block(
        10, "Kick", "DRUM", "Pattern", "LIVE", midi_note=36, mutators=[],
        parameters={"pattern": "1", "fill_density": 1.0, "event_probability": 1.0,
                    "kit_role": "kick"},
    )
    engine = MusicEngine(Project(seed=5, length=16, blocks=[kick]))
    event = engine.live_event(kick, beat=0.0)
    assert event is not None
    assert event["event_class"] == ANCHOR
    assert event["importance"] == pytest.approx(1.0)
