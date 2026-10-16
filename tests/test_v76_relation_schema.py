from auricle_core import Relation, Project, save_project, load_project

def test_relation_extended_schema_defaults():
    r = Relation(1, "pitch", 2, "pitch", "Modulate", .5)
    assert r.curve == "Linear" and r.delay == 0 and r.probability == 1.0
    assert r.enabled is True and r.id == 0

def test_relation_extended_schema_persists(tmp_path):
    p = Project(relations=[Relation(1,"pitch",2,"pitch","Mix",.4,"Exponential",2,.75,False,42)])
    path = tmp_path / "p.json"
    save_project(p, str(path)); q = load_project(str(path)); r=q.relations[0]
    assert (r.curve,r.delay,r.probability,r.enabled,r.id)==("Exponential",2,.75,False,42)
