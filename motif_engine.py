"""Motif, PhraseState and TensionCurve backend for Auricle v100."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass
class Motif:
    id: str
    name: str
    role: str = "MELODY"
    notes: list[int] = field(default_factory=list)
    rhythm: list[float] = field(default_factory=list)
    velocity: list[float] = field(default_factory=list)
    variations: dict[str, Any] = field(default_factory=dict)

@dataclass
class TensionPoint:
    beat: float
    value: float
    label: str = ""

CURVE_PRESETS = {
    "gentle_rise": ((0.0,.20),(1.0,.62)),
    "crescendo": ((0.0,.12),(.35,.30),(.72,.68),(1.0,1.0)),
    "peak_release": ((0.0,.20),(.55,1.0),(1.0,.18)),
}

@dataclass
class TensionCurve:
    points: list[TensionPoint] = field(default_factory=lambda: [TensionPoint(0,.2), TensionPoint(8,.8), TensionPoint(16,.2)])
    smoothing: float = .35

    @classmethod
    def preset(cls, name: str, beats: float = 16.0, smoothing: float = .35):
        shape = CURVE_PRESETS.get(name, CURVE_PRESETS["peak_release"])
        return cls([TensionPoint(float(beats)*x, y) for x,y in shape], smoothing)

    @classmethod
    def from_dict(cls, data: dict | None):
        data = data or {}
        pts=[]
        for p in data.get("points", []):
            if isinstance(p, dict): pts.append(TensionPoint(float(p.get("beat",0)), float(p.get("value",0)), str(p.get("label",""))))
        return cls(pts or cls().points, float(data.get("smoothing", .35)))

    def value_at(self, beat: float) -> float:
        if not self.points: return 0.0
        pts=sorted(self.points,key=lambda p:p.beat)
        if beat <= pts[0].beat: return max(0.,min(1.,pts[0].value))
        if beat >= pts[-1].beat: return max(0.,min(1.,pts[-1].value))
        for a,b in zip(pts,pts[1:]):
            if a.beat <= beat <= b.beat:
                x=(beat-a.beat)/max(1e-9,b.beat-a.beat)
                # smoothing is an amount, not a fake tension control
                smooth=x*x*(3-2*x)
                x=x*(1-self.smoothing)+smooth*self.smoothing
                return max(0.,min(1.,a.value+(b.value-a.value)*x))
        return 0.0

@dataclass
class PhraseState:
    phrase_id: str = ""
    name: str = ""
    position_beats: float = 0.0
    stage_index: int = -1
    intensity: float = 1.0
    tension: TensionCurve = field(default_factory=TensionCurve)
    active_motifs: list[str] = field(default_factory=list)
    block_ids: list[int] = field(default_factory=list)
    running: bool = False
    memory: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict | None):
        data=data or {}
        memory=dict(data.get("memory",{}))
        if "snapshot" in memory:
            memory["snapshot"]={int(k): {pk: tuple(pv) for pk,pv in vals.items()} for k,vals in memory["snapshot"].items()}
        if "snapshot_missing" in memory:
            memory["snapshot_missing"]={int(k): set(vals) for k,vals in memory["snapshot_missing"].items()}
        running=bool(data.get("running",False))
        return cls(str(data.get("phrase_id","")), str(data.get("name","")), float(data.get("position_beats",0)),
                   -1 if running else int(data.get("stage_index",-1)), float(data.get("intensity",1)), TensionCurve.from_dict(data.get("tension")),
                   list(data.get("active_motifs",[])), [int(x) for x in data.get("block_ids",[])], running, memory)
    def advance(self, beats: float): self.position_beats += float(beats)
    def tension_value(self): return self.tension.value_at(self.position_beats)

class MotifEngine:
    def __init__(self):
        self.motifs: dict[str,Motif]={}
        self.phrase_state=PhraseState()
    def load(self, motifs: dict | None):
        self.motifs={}
        for key,value in (motifs or {}).items():
            if isinstance(value, Motif): self.register(value); continue
            if isinstance(value, dict):
                d=dict(value); d.setdefault("id",str(key)); d.setdefault("name",str(key)); self.register(Motif(**{k:d[k] for k in Motif.__dataclass_fields__ if k in d}))
    def register(self,motif:Motif): self.motifs[motif.id]=motif
    def set_phrase(self, phrase_id:str, name:str="", motifs:list[str]|None=None, curve:TensionCurve|None=None):
        self.phrase_state=PhraseState(phrase_id=phrase_id,name=name,active_motifs=list(motifs or []),tension=curve or TensionCurve(),running=True)
        return self.phrase_state
    def tick(self,beats:float): self.phrase_state.advance(beats); return self.phrase_state
    def snapshot(self): return asdict(self.phrase_state)
