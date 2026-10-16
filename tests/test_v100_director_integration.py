from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from auricle_core import Block, MusicEngine, Project
from motif_engine import Motif, TensionCurve

def test_phrase_state_is_single_source_of_truth():
    e=MusicEngine(Project(blocks=[Block(1,"M","MELODY","Pattern")]))
    assert not hasattr(e.performance,"active_phrases")
    assert e.performance.start_phrase(e.project,"tension_rise",[1],.8)
    assert e.director.phrase is e.director.motifs.phrase_state
    assert e.director.phrase.running and e.director.phrase.intensity == .8

def test_tension_curve_presets_have_expected_shapes():
    rise=TensionCurve.preset("crescendo",12)
    peak=TensionCurve.preset("peak_release",12)
    assert rise.value_at(12) > rise.value_at(0)
    assert peak.value_at(6.6) > peak.value_at(0) and peak.value_at(6.6) > peak.value_at(12)

def test_project_motifs_load_and_affect_active_phrase_generation():
    p=Project(length=4, motifs={"m1":{"id":"m1","name":"cell","role":"MELODY","notes":[0,2,4,7],"rhythm":[1,0,1,1],"velocity":[.4,.5,.6,.7]}})
    b=Block(1,"M","MELODY","Pattern","SEQ",parameters={"pattern":"1,1,1,1"}); p.blocks=[b]
    e=MusicEngine(p)
    assert "m1" in e.director.motifs.motifs
    e.performance.start_phrase(p,"opening_bloom",[1])
    e.director.phrase.active_motifs=["m1"]
    e.director.energy=1; e.director.density=1; e.director.tension_amount=0
    e.generate_block(b)
    assert b.outputs["rhythm"][1] == 0

def test_director_does_not_pollute_block_parameters():
    p=Project(blocks=[Block(1,"M","MELODY","Pattern","SEQ",parameters={"pattern":"1,2,3,4"})])
    e=MusicEngine(p); e.performance.start_phrase(p,"opening_bloom",[1]); e.generate_block(p.blocks[0])
    assert not any(k.startswith("director_") for k in p.blocks[0].parameters)

def test_voice_smoothing_is_scale_safe_when_director_inactive():
    p=Project(length=16,scale="Dorian",blocks=[Block(1,"M","MELODY","Fibonacci","SEQ")])
    e=MusicEngine(p); e.generate_block(p.blocks[0]); dorian={0,2,3,5,7,9,10}
    assert all(round(v)%12 in dorian for v in p.blocks[0].outputs["pitch"])

def test_running_phrase_state_and_motifs_roundtrip(tmp_path):
    from auricle_core import save_project, load_project
    p=Project(blocks=[Block(1,"M","MELODY","Pattern")])
    e=MusicEngine(p)
    e.director.motifs.register(Motif("x","X","MELODY",[0,2],[1,1],[.5,.6]))
    e.performance.start_phrase(p,"opening_bloom",[1])
    e.director.phrase.active_motifs=["x"]
    e.director.sync_project(p)
    path=tmp_path/"p.json"; save_project(p,str(path))
    loaded=load_project(str(path)); e2=MusicEngine(loaded)
    assert "x" in e2.director.motifs.motifs
    assert e2.director.phrase.running and e2.director.phrase.phrase_id == "opening_bloom"
    assert e2.director.phrase.stage_index == -1
    assert 1 in e2.director.phrase.memory["snapshot"]

def test_director_energy_density_probability_are_live_values():
    p=Project(length=8,blocks=[Block(1,"M","MELODY","Pattern","SEQ",parameters={"pattern":"1,1,1,1,1,1,1,1","event_probability":1.0})])
    e=MusicEngine(p); e.performance.start_phrase(p,"opening_bloom",[1])
    e.director.energy=1.0; e.director.density=1.0
    snap=e.director.snapshot()
    assert snap.energy > 0 and snap.density > 0 and 0 < e.event_probability(p.blocks[0]) <= 1
    e.generate_block(p.blocks[0])
    assert all(not k.startswith("director_") for k in p.blocks[0].parameters)
