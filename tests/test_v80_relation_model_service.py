from auricle_core import Project, Block, Relation, next_relation_id, remove_relation, duplicate_relation, validate_relations, save_project, load_project

def test_relation_model_mutations_are_stable():
    p=Project(blocks=[Block(1,"A","MELODY"),Block(2,"B","MELODY")],relations=[Relation(1,"pitch",2,"pitch","Mix")])
    assert next_relation_id(p)==1
    c=duplicate_relation(p,0); assert c is not None and c.id==1
    assert remove_relation(p,1)
    assert not remove_relation(p,99)

def test_relation_validation_is_model_level():
    p=Project(blocks=[Block(1,"A","MELODY")],relations=[Relation(1,"pitch",99,"pitch","Copy")])
    assert any("destination" in msg for _,msg in validate_relations(p))

def test_load_normalizes_relation_ids(tmp_path):
    p=Project(blocks=[Block(1,"A","MELODY"),Block(2,"B","MELODY")],relations=[Relation(1,"pitch",2,"pitch","Copy"),Relation(1,"velocity",2,"velocity","Mix")])
    path=tmp_path/"p.json"; save_project(p,str(path)); q=load_project(str(path)); ids=[r.id for r in q.relations]
    assert len(set(ids))==2 and all(x>0 for x in ids)
