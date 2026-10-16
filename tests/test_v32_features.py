import tempfile
from auricle_core import Project, Block, MusicEngine, save_project, load_project


def test_density_and_probability_are_distinct_parameters():
    p=Project(length=16, blocks=[Block(1,'x','MELODY','Euclidean',parameters={'fill_density':.5,'event_probability':.25})])
    e=MusicEngine(p); b=p.blocks[0]
    assert e._fill_density_value(b)==.5
    assert e.event_probability(b)==.25


def test_randomize_respects_catalog_bounds():
    p=Project(blocks=[Block(1,'x','MELODY','Markov')]); e=MusicEngine(p); b=p.blocks[0]
    e.randomize_block(b, {'Generator','Density','Pitch'}, amount=1.0)
    for k,(d,lo,hi) in e.parameter_catalog(b).items():
        if k in b.parameters and isinstance(b.parameters[k],(int,float)):
            assert lo-1e-9 <= float(b.parameters[k]) <= hi+1e-9


def test_macro_route_and_serialization():
    b=Block(1,'x','MELODY','Euclidean'); p=Project(blocks=[b], macros=[{'name':'D','value':1.0,'routes':[{'block_id':1,'parameter':'fill_density','min':0.2,'max':0.8,'amount':1.0,'curve':1.0}]}])
    e=MusicEngine(p); e.apply_macros(); assert abs(b.parameters['fill_density']-.8)<1e-6
    with tempfile.NamedTemporaryFile(suffix='.json') as f:
        save_project(p,f.name); q=load_project(f.name)
    assert q.macros[0]['routes'][0]['parameter']=='fill_density'

