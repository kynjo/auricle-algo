import random
from auricle_core import Project, Block, MusicEngine, Process, MusicalRepresentation


def rep(values):
    n=len(values)
    return MusicalRepresentation(list(values), list(values), [1.0]*n, [1.0]*n, list(values), [0.0]*n)


def run_process(kind, params, values=(0,1,2,3,4,5,6,7)):
    b=Block(1,'X','MELODY','Pattern','SEQ',1,'',60,{'pattern':'0,1,2,3'})
    b.processes=[Process(kind,'pitch',1.0,params)]
    e=MusicEngine(Project(blocks=[b]))
    r=rep(values)
    e._apply_processes(b,r,random.Random(1))
    return r.pitch


def test_delay_repeats_and_decay():
    out=run_process('Delay', {'delay':2,'repeats':3,'feedback':0.8,'mix':1.0,'decay':0.5,'mode':'Echo'}, (1,0,0,0,0,0,0,0))
    assert out[2] > 0
    assert out[4] > 0
    assert out[6] > 0
    assert out[4] < out[2]


def test_counter_waveforms_are_distinct():
    a=run_process('Counter', {'length':4,'step':1,'offset':0,'center':0,'phase':0,'reset':4,'waveform':'Ramp'})
    b=run_process('Counter', {'length':4,'step':1,'offset':0,'center':0,'phase':0,'reset':4,'waveform':'Triangle'})
    assert a != b


def test_memory_and_feedback_have_extended_controls():
    a=run_process('Memory', {'delay':2,'feedback':1,'mix':1,'initial':9,'mode':'Replace'})
    b=run_process('Feedback', {'feedback':0.7,'iterations':4,'decay':0.8,'mix':1,'bias':0.2,'clamp':2,'initial':0,'mode':'Recursive'})
    assert a[0] == 9
    assert all(abs(x) <= 2 for x in b)
