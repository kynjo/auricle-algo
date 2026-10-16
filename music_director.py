"""Musical Director: multidimensional phrase form over PhraseState.

Phrase techniques still provide local musical gestures.  The Director adds a
separate, transient form layer; it never writes Director values into Block
parameters, so STOP can restore phrase techniques without cumulative drift.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from motif_engine import PhraseState, MotifEngine, TensionCurve

def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(v)))

def _lerp(a, b, x):
    return float(a) + (float(b)-float(a))*float(x)

# Normalized phrase trajectories. Values are deliberately not a shared
# amplitude envelope: each phrase has a different path through several musical
# dimensions. density/probability stay above useful floors to avoid turning a
# phrase into a generic fade-out.
PHRASE_PROFILES = {
    "opening_bloom": (
        (0.00, .18, .48, .62, -2.0, .78, 1.15, .18),
        (0.35, .34, .62, .74,  0.0, .84, 1.02, .28),
        (0.70, .58, .76, .88,  2.5, .91, .92, .42),
        (1.00, .72, .84, .96,  4.0, .96, .88, .52),
    ),
    "tension_rise": (
        (0.00, .24, .58, .72,  0.0, .82, 1.00, .28),
        (0.40, .52, .70, .82,  1.5, .88, .88, .48),
        (0.75, .80, .86, .93,  3.5, .95, .76, .70),
        (1.00, 1.00, .98, 1.00,  5.0, 1.00, .68, .86),
    ),
    "climax_release": (
        (0.00, .58, .74, .82,  2.0, .90, .88, .55),
        (0.30, .86, .91, .96,  4.5, .98, .72, .78),
        (0.42, 1.00, 1.00, 1.00,  6.0, 1.00, .64, .92),
        (0.70, .62, .72, .76,  2.0, .86, 1.05, .48),
        (1.00, .28, .52, .64, -1.0, .76, 1.28, .24),
    ),
    "breath": (
        (0.00, .34, .64, .78,  0.0, .88, 1.00, .28),
        (0.28, .46, .70, .86,  1.0, .92, 1.12, .34),
        (0.52, .38, .66, .82,  0.0, .90, 1.32, .42),
        (0.76, .44, .69, .80,  0.5, .88, 1.18, .38),
        (1.00, .26, .58, .72, -0.5, .82, 1.38, .20),
    ),
    "accelerando_release": (
        (0.00, .30, .60, .72,  0.0, .82, 1.08, .30),
        (0.35, .56, .72, .84,  1.0, .90, .82, .48),
        (0.62, .88, .90, .98,  2.5, .98, .58, .72),
        (0.78, .72, .82, .90,  1.5, .92, .78, .56),
        (1.00, .32, .58, .70,  0.0, .80, 1.30, .26),
    ),
}
DEFAULT_PROFILE = PHRASE_PROFILES["opening_bloom"]

# Role semantics are intentionally musical rather than simple scalar multipliers.
# Each role interprets the common phrase state as a different ensemble function.
ROLE_CHARACTER = {
    "DRUM":       dict(energy=1.10, density=1.12, register=0.00, probability=1.08, duration=.70, variation=1.15),
    "PERCUSSION": dict(energy=.98, density=1.18, register=0.00, probability=1.12, duration=.66, variation=1.22),
    "BASS":       dict(energy=1.04, density=.76, register=.42, probability=.92, duration=1.04, variation=.62),
    "MELODY":     dict(energy=1.00, density=.92, register=1.00, probability=.98, duration=.96, variation=1.18),
    "CHORD":      dict(energy=.92, density=.62, register=.68, probability=.94, duration=1.18, variation=.52),
    "PAD":        dict(energy=.84, density=.48, register=.52, probability=.90, duration=1.38, variation=.36),
}

# Phrase-specific emphasis layered over the stable role identity.
PHRASE_ROLE_EMPHASIS = {
    "opening_bloom": {
        "DRUM": (.95,1.08,1.00), "PERCUSSION":(.92,1.16,1.08),
        "BASS": (1.00,.88,.82), "MELODY":(1.04,1.00,1.10),
        "CHORD":(.96,.92,.78), "PAD":(.92,.86,.68),
    },
    "tension_rise": {
        "DRUM": (1.10,1.16,1.12), "PERCUSSION":(1.05,1.20,1.18),
        "BASS": (1.06,.92,.88), "MELODY":(1.08,1.04,1.20),
        "CHORD":(1.00,.90,.74), "PAD":(.94,.80,.62),
    },
    "climax_release": {
        "DRUM": (1.14,1.14,1.12), "PERCUSSION":(1.08,1.18,1.16),
        "BASS": (1.10,.88,.82), "MELODY":(1.10,1.00,1.18),
        "CHORD":(1.06,.88,.72), "PAD":(1.00,.78,.60),
    },
    "breath": {
        "DRUM": (.82,.72,.68), "PERCUSSION":(.78,.68,.64),
        "BASS": (.94,.72,.54), "MELODY":(.92,.76,.62),
        "CHORD":(.90,.78,.46), "PAD":(.88,.82,.38),
    },
    "accelerando_release": {
        "DRUM": (1.10,1.20,1.12), "PERCUSSION":(1.04,1.24,1.18),
        "BASS": (1.04,.90,.72), "MELODY":(1.04,1.04,1.08),
        "CHORD":(.98,.86,.60), "PAD":(.90,.72,.46),
    },
}


@dataclass
class PerformanceState:
    energy: float = .65
    tension: float = .35
    density: float = .82
    register_shift: float = 0.0
    probability: float = .90
    duration_factor: float = 1.0
    variation: float = .30
    progress: float = 0.0

@dataclass
class RolePerformanceState:
    energy: float
    density: float
    register_shift: float
    probability: float
    duration_factor: float
    variation: float
    activity_mode: str = "notes"

# Backwards-compatible name used by existing tests/imports.
DirectorSnapshot = PerformanceState

class MusicDirector:
    def __init__(self, project=None):
        self.motifs=MotifEngine()
        if project is not None:
            self.motifs.load(getattr(project,"motifs",{}))
        self.phrase=PhraseState.from_dict(getattr(project,"phrase_state",{})) if project is not None else PhraseState()
        self.motifs.phrase_state=self.phrase

        # Manual Director controls. These are influence/depth controls, not
        # duplicate Global Musical Macros.
        self.smoothing=.60
        self.energy_influence=.60
        self.density_influence=.60
        self.register_influence=.60
        self.probability_influence=.60
        self.variation_influence=.50
        self.voice_smooth=.60
        self.tension_amount=1.0
        self.global_macro_values={"energy": .5, "tension": .5, "density": .5, "variation": .5}
        self.voice_leading=True
        self._last_state=PerformanceState()
        self._energy_override=None
        self._density_override=None
        self.project_seed=int(getattr(project,"seed",12345)) if project is not None else 12345
        self.decision_window_beats=1.0
        # Project macros are persisted as values and restored as Director
        # controls. The GUI keeps the four canonical controls in a shared
        # header strip, while custom block routes remain supported separately.
        for index, macro in enumerate(getattr(project, "macros", []) or []):
            control = str(macro.get("control", ("energy", "tension", "density", "variation")[index] if index < 4 else ""))
            if control:
                self.set_global_macro(control, float(macro.get("value", .5)))

    @property
    def energy(self):
        return self._last_state.energy

    @energy.setter
    def energy(self, value):
        # Compatibility for projects/tests that used the old live scalar.
        self._energy_override=_clamp(value)

    @property
    def density(self):
        return self._last_state.density

    @density.setter
    def density(self, value):
        self._density_override=_clamp(value)

    def _profile_value(self, progress: float):
        profile=PHRASE_PROFILES.get(self.phrase.phrase_id, DEFAULT_PROFILE)
        x=_clamp(progress)
        if x <= profile[0][0]: return profile[0][1:]
        if x >= profile[-1][0]: return profile[-1][1:]
        for a,b in zip(profile,profile[1:]):
            if a[0] <= x <= b[0]:
                local=(x-a[0])/max(1e-9,b[0]-a[0])
                smooth=local*local*(3.0-2.0*local)
                local=_lerp(local,smooth,self.smoothing)
                return tuple(_lerp(av,bv,local) for av,bv in zip(a[1:],b[1:]))
        return profile[-1][1:]

    def snapshot(self, beat: float|None=None):
        pos=self.phrase.position_beats if beat is None else float(beat)
        total=float(self.phrase.memory.get("total_beats",0.0) or 0.0)
        if total <= 0.0:
            pts=getattr(self.phrase.tension,"points",[])
            total=max([float(p.beat) for p in pts], default=16.0)
        progress=_clamp(pos/max(.25,total))
        energy,tension,density,register,probability,duration,variation=self._profile_value(progress)
        intensity=_clamp(self.phrase.intensity)

        # Influence sliders blend each dimension toward a neutral pass-through
        # state. Phrase Amount scales the overall distance from neutral.
        depth=intensity
        energy=_lerp(.72,energy,self.energy_influence*depth)
        density=_lerp(1.0,density,self.density_influence*depth)
        if self._energy_override is not None: energy=self._energy_override
        if self._density_override is not None: density=self._density_override
        register=_lerp(0.0,register,self.register_influence*depth)
        probability=_lerp(1.0,probability,self.probability_influence*depth)
        duration=_lerp(1.0,duration,depth)
        variation=_lerp(.20,variation,self.variation_influence*depth)

        # Curve is a tension contour, not a master volume envelope.
        curve_tension=_clamp(self.phrase.tension.value_at(pos)*self.tension_amount)
        tension=_clamp(_lerp(tension,curve_tension,.35))
        self._last_state=PerformanceState(
            _clamp(energy), tension, _clamp(density), register,
            _clamp(probability), max(.35,min(1.8,duration)),
            _clamp(variation), progress,
        )
        return self._last_state

    def role_state(self, role: str, state: PerformanceState|None=None):
        """Interpret a common phrase state for one ensemble role.

        PAD/CHORD density is deliberately mapped to harmonic-change activity,
        not wholesale note deletion; DRUM/PERCUSSION density is the strongest
        event-activity control; melodic roles sit between those extremes.
        """
        state=state or self.snapshot()
        role=str(role or "MELODY").upper()
        c=ROLE_CHARACTER.get(role, ROLE_CHARACTER["MELODY"])
        emphasis=PHRASE_ROLE_EMPHASIS.get(self.phrase.phrase_id, {}).get(role,(1.0,1.0,1.0))
        e_mul,d_mul,v_mul=emphasis

        energy=_clamp(.5 + (state.energy-.5)*c["energy"]*e_mul)
        # Density is centered around unity so low-density ensemble roles do not
        # become silent merely because they are pads/chords.
        density=_clamp(1.0 - (1.0-state.density)*c["density"]*d_mul)
        probability=_clamp(1.0 - (1.0-state.probability)*c["probability"])
        register=state.register_shift*c["register"]
        duration=1.0 + (state.duration_factor-1.0)*c["duration"]
        variation=_clamp(state.variation*c["variation"]*v_mul)

        activity_mode="harmonic" if role in ("PAD","CHORD") else ("pulse" if role in ("DRUM","PERCUSSION") else "notes")
        return RolePerformanceState(energy,density,register,probability,max(.30,min(2.2,duration)),variation,activity_mode)

    def decision_value(self, block_id: int, lane: str="density", beat: float|None=None, slot: int=0) -> float:
        """Stable pseudo-random value for a musical decision window.

        It is deterministic for Project seed + Phrase + block + beat window.
        Regenerating the same phrase therefore cannot reshuffle density gates
        every few milliseconds.
        """
        import hashlib
        pos=self.phrase.position_beats if beat is None else float(beat)
        window=max(.25,float(self.decision_window_beats))
        window_index=int(max(0.0,pos)//window)
        token=f"{self.project_seed}|{self.phrase.phrase_id}|{int(block_id)}|{lane}|{window_index}|{int(slot)}"
        raw=hashlib.blake2b(token.encode("utf-8"),digest_size=8).digest()
        return int.from_bytes(raw,"big") / float((1<<64)-1)

    @staticmethod
    def bounded_combine(base: float, performance: float, floor: float=.12) -> float:
        """Combine independent activity controls without multiplicative collapse."""
        base=_clamp(base); performance=_clamp(performance)
        # Weighted minimum: respects a deliberately low user setting while
        # preventing several performance layers from repeatedly multiplying
        # the same dimension toward zero.
        combined=min(base, .35*base + .65*performance)
        return _clamp(max(float(floor),combined))

    def set_curve_preset(self,name:str,total_beats:float=16):
        self.phrase.tension=TensionCurve.preset(name,total_beats)

    def set_control(self, name: str, value: float):
        value=_clamp(value)
        mapping={
            "Smoothing":"smoothing",
            "Energy Influence":"energy_influence",
            "Density Influence":"density_influence",
            "Register Influence":"register_influence",
            "Probability Influence":"probability_influence",
            "Voice Smooth":"voice_smooth",
        }
        attr=mapping.get(str(name))
        if attr:
            setattr(self,attr,value)

    def set_global_macro(self, control: str, value: float):
        """Set one of the four always-active global musical controls."""
        value = _clamp(value)
        control = str(control or "").strip().lower().replace(" ", "_")
        if control in self.global_macro_values:
            self.global_macro_values[control] = value
        if control == "energy":
            self.energy_influence = .60 + (value - .50) * .80
        elif control == "density":
            self.density_influence = .60 + (value - .50) * .80
        elif control == "variation":
            self.variation_influence = .50 + (value - .50)
        elif control == "tension":
            # Keep the midpoint at the historical neutral value of 1.0 while
            # still giving the full slider a useful, audible range.
            self.tension_amount = 1.0 + 1.5 * (value - .50)

    def sync_project(self, project):
        project.motifs={k:asdict(v) for k,v in self.motifs.motifs.items()}
        state=asdict(self.phrase)
        missing=state.get("memory",{}).get("snapshot_missing",{})
        if missing:
            state["memory"]["snapshot_missing"]={str(k): sorted(v) for k,v in missing.items()}
        snap=state.get("memory",{}).get("snapshot",{})
        if snap:
            state["memory"]["snapshot"]={str(k): v for k,v in snap.items()}
        project.phrase_state=state
