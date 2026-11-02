"""Continuous harmonic influence and register-safe chord placement."""
import pytest

from auricle_core import Block, Project, MusicEngine, midi_note_for
from harmonic_plan import HarmonicRuntime, METERS, QUALITIES, metric_weight
from voice_leading import VoiceLeading


def plan(meter='4/4'):
    return {'enabled':True,'meter':meter,'loop':True,
            'chords':[{'root':0,'quality':'major','bars':1}]}


@pytest.mark.parametrize('role',['BASS','MELODY'])
def test_harmonic_strength_is_monotonic_with_no_jump_near_zero(role):
    block=Block(1,role,role,parameters={'harmonic_strength':0})
    runtime=HarmonicRuntime(Project(seed=752,blocks=[block],harmonic_plan=plan()))
    selections=[]
    for strength in (0,.01,.25,.5,.75,1):
        block.parameters['harmonic_strength']=strength
        chosen={i for i in range(2048) if runtime.apply(block,{'pitch':2,'velocity':.8},i*.25)['pitch'] != 2}
        selections.append(chosen)
    assert not selections[0]
    assert 0 < len(selections[1]) < 2048*.04
    assert len(selections[-1]) == 2048
    assert all(a < b for a,b in zip(selections,selections[1:]))
    block.parameters['harmonic_strength']=.5
    again={i for i in range(2048) if runtime.apply(block,{'pitch':2},i*.25)['pitch'] != 2}
    assert again == selections[3]


@pytest.mark.parametrize('meter', METERS)
def test_downbeats_and_cadences_do_not_bypass_low_strength(meter):
    block=Block(7,'Lead','MELODY',parameters={'harmonic_strength':.01})
    runtime=HarmonicRuntime(Project(seed=11,blocks=[block],harmonic_plan=plan(meter)))
    numerator,denominator=map(int,meter.split('/'))
    bar=numerator*4/denominator
    for phase in (0,bar-.25):
        anchored=sum(runtime.apply(block,{'pitch':2},i*bar+phase)['pitch'] != 2 for i in range(512))
        assert anchored < 512*.05


def test_meter_accents_distinguish_simple_compound_and_odd_meters():
    assert metric_weight('4/4',0) > metric_weight('4/4',2) > metric_weight('4/4',1)
    assert metric_weight('3/4',0) > 0 and metric_weight('3/4',1) == 0
    assert metric_weight('6/8',1.5) > 0 and metric_weight('6/8',1) == 0
    assert metric_weight('7/8',2) > 0 and metric_weight('7/8',1.5) == 0


@pytest.mark.parametrize('role',['CHORD','PAD'])
@pytest.mark.parametrize('base',[0,60,127])
@pytest.mark.parametrize('scale',['Major','Dorian','Whole Tone'])
def test_standalone_wide_chords_preserve_distinct_scale_tones_at_midi_edges(role,base,scale):
    block=Block(1,role,role,midi_note=base,parameters={
        'role_center':-12,'role_width':12,'harmony_size':4,'harmony_spread':48})
    e=MusicEngine(Project(blocks=[block],scale=scale,root_note=62))
    for inversion in (-3,-1,0,1,3):
        block.parameters['harmony_inversion']=inversion
        offsets=e._chord_pitches(block,0)
        notes=[midi_note_for(e.project,block,p) for p in offsets]
        assert len(notes) == len(set(notes)) == 4
        assert 0 <= min(notes) <= max(notes) <= 127
        expected={round(p)%12 for p in e._chord_pitches(block,0)}
        block.parameters['harmony_spread']=0
        compact=e._chord_pitches(block,0)
        assert {round(p)%12 for p in compact} == expected
        block.parameters['harmony_spread']=48


def test_standalone_spread_folds_into_register_instead_of_clipping():
    block=Block(1,'Chord','CHORD',parameters={
        'role_center':-12,'role_width':24,'harmony_size':4,'harmony_spread':48})
    e=MusicEngine(Project(blocks=[block]))
    notes=e._chord_pitches(block,0)
    assert len(set(notes)) == 4
    assert min(notes) >= -24 and max(notes) <= 0
    assert {round(p)%12 for p in notes} == {0,4,7,11}
    block.parameters['role_center']=0
    assert e._chord_pitches(block,0) == [note+12 for note in notes]


@pytest.mark.parametrize('quality',QUALITIES)
def test_tight_voicings_keep_pitch_classes_even_when_exact_width_is_impossible(quality):
    intervals=QUALITIES[quality][1]
    notes=[60+x+12*i for i,x in enumerate(intervals)]
    result=VoiceLeading.resolve_chord(notes,register=(45,51))
    assert len(result) == len(set(result)) == len(notes)
    assert [n%12 for n in result] == [n%12 for n in notes]
    assert max(result)-min(result) <= 12
    assert max(0,45-result[0],result[-1]-51) < 12


def test_builtin_chord_anchor_is_gradual_and_accounts_for_different_base_notes():
    chord=Block(1,'Harmony','CHORD',midi_note=65,mutators=[])
    melody=Block(2,'Lead','MELODY',midi_note=60,mutators=[],parameters={'harmony_anchor':.01})
    project=Project(length=512,seed=71,blocks=[chord,melody])
    e=MusicEngine(project)
    chord.outputs={'rhythm':[1]*512,'pitch':[0]*512}
    melody.outputs={'rhythm':[1]*512,'pitch':[2]*512}
    e._apply_chord_to_melody(chord,melody)
    assert sum(v != 2 for v in melody.outputs['pitch']) < 512*.04
    melody.parameters['harmony_anchor']=1
    e._apply_chord_to_melody(chord,melody)
    pcs={(65+tone)%12 for tone in e._chord_pitches(chord,0)}
    assert all((60+v)%12 in pcs for v in melody.outputs['pitch'])
