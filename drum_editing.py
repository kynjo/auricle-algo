"""Routing-safe, detached copies of Drum Voice sound settings."""
from copy import deepcopy


def sound_snapshot(voice):
    return deepcopy({"algorithm": voice.algorithm,
                     "parameters": {k: v for k, v in voice.parameters.items() if k != "kit_role"},
                     "mutators": voice.mutators, "processes": voice.processes})


def apply_sound(voice, snapshot):
    data = deepcopy(snapshot)
    role = voice.parameters.get("kit_role", "perc")
    voice.algorithm = data["algorithm"]
    voice.parameters = {**data["parameters"], "kit_role": role}
    voice.mutators, voice.processes = data["mutators"], data["processes"]
