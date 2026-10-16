from copy import deepcopy
from auricle_core import Block, Project, MusicEngine
from music_director import MusicDirector
from performance_presets import phrase_for

def _director(seed=12345, phrase="opening_bloom"):
    p=Project(seed=seed)
    d=MusicDirector(p)
    d.phrase.phrase_id=phrase; d.phrase.running=True
    d.phrase.memory={"total_beats":12.0}
    return d

def test_phrase_decisions_are_reproducible_for_same_seed():
    a=_director(77); b=_director(77)
    av=[a.decision_value(3,"density",beat,i) for i,beat in enumerate((0,.5,1,2,4))]
    bv=[b.decision_value(3,"density",beat,i) for i,beat in enumerate((0,.5,1,2,4))]
    assert av==bv

def test_phrase_decisions_change_with_seed_but_character_does_not():
    a=_director(77); b=_director(78)
    assert a.decision_value(3,"density",2,1) != b.decision_value(3,"density",2,1)
    sa=a.snapshot(6); sb=b.snapshot(6)
    assert (sa.energy,sa.density,sa.duration_factor)==(sb.energy,sb.density,sb.duration_factor)

def test_decision_is_stable_inside_same_musical_window():
    d=_director()
    assert d.decision_value(1,"live",.05,0)==d.decision_value(1,"live",.95,0)
    assert d.decision_value(1,"live",1.05,0)!=d.decision_value(1,"live",.95,0)

def test_bounded_activity_composition_avoids_multiplicative_collapse():
    d=_director()
    combined=d.bounded_combine(.55,.45,.12)
    assert combined >= .12
    assert combined > .55*.45
    assert d.bounded_combine(.04,.03,.12)==.12

def test_phrase_stage_crossfade_is_enabled_for_phrase_techniques():
    p=Project(length=8,blocks=[Block(1,"M","MELODY","Pattern","SEQ",parameters={"pattern":"1,1,1,1"})])
    e=MusicEngine(p)
    assert e.performance.start_phrase(p,"opening_bloom",[1])
    phrase=phrase_for("opening_bloom")
    e.performance._activate_phrase_stage(p,e.director.phrase,phrase,0)
    state=e.performance.active[1]
    assert state.crossfade_beats > 0
    assert state.crossfade_from

def test_opening_bloom_musical_invariant():
    d=_director(123,"opening_bloom")
    a=d.snapshot(0); z=d.snapshot(12)
    assert z.energy>a.energy and z.density>a.density and z.register_shift>a.register_shift

def test_climax_release_has_peak_and_release_invariant():
    d=_director(123,"climax_release"); d.phrase.memory={"total_beats":15.0}
    a=d.snapshot(0); peak=d.snapshot(6.0); z=d.snapshot(15.0)
    assert peak.energy>a.energy and peak.energy>z.energy
    assert z.duration_factor>peak.duration_factor

def test_breath_keeps_pad_harmonic_and_sustained():
    d=_director(123,"breath"); d.phrase.memory={"total_beats":16.0}
    r=d.role_state("PAD",d.snapshot(9.0))
    assert r.activity_mode=="harmonic"
    assert r.duration_factor>1.15

def test_bass_register_is_more_grounded_than_melody():
    d=_director(123,"tension_rise")
    s=d.snapshot(10)
    assert abs(d.role_state("BASS",s).register_shift) < abs(d.role_state("MELODY",s).register_shift)

def test_seq_generation_same_seed_phrase_position_is_reproducible():
    def render():
        p=Project(seed=991,length=16,blocks=[Block(1,"D","DRUM","Euclidean","SEQ",parameters={"pulses":9})])
        e=MusicEngine(p); e.performance.start_phrase(p,"tension_rise",[1])
        e.director.phrase.position_beats=6.0
        e.generate_block(p.blocks[0])
        return deepcopy(p.blocks[0].outputs)
    assert render()==render()
