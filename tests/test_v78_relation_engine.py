from auricle_core import Project, Block, Relation, MusicEngine

def blocks():
    a=Block(1,"A","MELODY",parameters={}); b=Block(2,"B","MELODY",parameters={})
    return a,b

def test_relation_curve_and_delay():
    # Curve/delay math is checked on a non-pitch dimension (v102.2: pitch
    # relation results are additionally quantized to the destination scale).
    a,b=blocks(); p=Project(blocks=[a,b],relations=[Relation(1,"velocity",2,"velocity","Copy",.5,"Exponential",1,1.0,True,1)])
    e=MusicEngine(p); a.outputs={"velocity":[0,1,2]}; b.outputs={"velocity":[10,10,10]}; e._base_outputs={1:{"velocity":[0,1,2]},2:{"velocity":[10,10,10]}}
    e.apply_relations(); assert b.outputs["velocity"] == [8.0,7.5,7.75]


def test_pitch_relation_result_is_quantized_to_scale():
    a,b=blocks(); p=Project(blocks=[a,b],relations=[Relation(1,"pitch",2,"pitch","Copy",.5,"Exponential",1,1.0,True,1)])
    e=MusicEngine(p); a.outputs={"pitch":[0,1,2]}; b.outputs={"pitch":[10,10,10]}; e._base_outputs={1:{"pitch":[0,1,2]},2:{"pitch":[10,10,10]}}
    e.apply_relations()
    assert all(v == int(v) and int(v) % 12 in (0, 2, 4, 5, 7, 9, 11) for v in b.outputs["pitch"])

def test_disabled_relation_is_noop():
    a,b=blocks(); p=Project(blocks=[a,b],relations=[Relation(1,"pitch",2,"pitch","Copy",1,"Linear",0,1,False,1)])
    e=MusicEngine(p); e._base_outputs={1:{"pitch":[1]},2:{"pitch":[9]}}; a.outputs={"pitch":[1]}; b.outputs={"pitch":[9]}; e.apply_relations(); assert b.outputs["pitch"]==[9]

def test_relation_cycles_are_diagnostic():
    a,b=blocks(); p=Project(blocks=[a,b],relations=[Relation(1,"pitch",2,"pitch","Copy"),Relation(2,"pitch",1,"pitch","Copy")])
    cycles=MusicEngine(p).relation_cycles(); assert cycles
