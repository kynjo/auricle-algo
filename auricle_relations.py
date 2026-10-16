"""Model-level user relation operations."""

from __future__ import annotations

from auricle_model import Project, Relation

def validate_relations(project: Project) -> list[tuple[int, str]]:
    """Validate relation references without touching the UI."""
    block_ids={b.id for b in project.blocks}
    issues=[]
    for i,r in enumerate(project.relations):
        if r.source_block not in block_ids: issues.append((i,"missing source block"))
        if r.destination_block not in block_ids: issues.append((i,"missing destination block"))
        if r.source_block == r.destination_block and r.source_part == r.destination_part:
            issues.append((i,"self relation"))
        if not 0.0 <= float(getattr(r,"probability",1.0)) <= 1.0:
            issues.append((i,"probability out of range"))
    return issues

def next_relation_id(project: Project) -> int:
    return max([int(getattr(r,"id",0)) for r in project.relations] + [0]) + 1

def remove_relation(project: Project, index: int) -> bool:
    """Model-first relation deletion; returns whether a row was removed."""
    if 0 <= int(index) < len(project.relations):
        project.relations.pop(int(index))
        return True
    return False

def duplicate_relation(project: Project, index: int) -> Relation | None:
    if not 0 <= int(index) < len(project.relations): return None
    r=project.relations[int(index)]
    copy=Relation(r.source_block,r.source_part,r.destination_block,r.destination_part,r.algorithm,r.amount,
                  getattr(r,"curve","Linear"),int(getattr(r,"delay",0)),float(getattr(r,"probability",1.0)),
                  bool(getattr(r,"enabled",True)),next_relation_id(project))
    project.relations.insert(int(index)+1,copy)
    return copy

