"""Per-step Pattern chances, stored separately from note/velocity values."""
import math

from auricle_catalogs import DEFAULT_PATTERN
from generators import parse_number_list


def step_chances(parameters):
    count = len(parse_number_list(parameters.get("pattern", DEFAULT_PATTERN), float,
                                  parse_number_list(DEFAULT_PATTERN, float)))
    raw = parameters.get("pattern_step_chances", [])
    if isinstance(raw, str):
        raw = raw.replace(";", ",").split(",")
    if not isinstance(raw, (list, tuple)):
        raw = []
    result = []
    for i in range(count):
        try:
            value = float(raw[i])
            result.append(max(0., min(1., value)) if math.isfinite(value) else 1.)
        except (IndexError, TypeError, ValueError):
            result.append(1.)
    return result


def chance_at(parameters, slot, cycle=None):
    values = step_chances(parameters)
    if cycle is not None:
        cycle = max(1, int(cycle))
        values = [values[i % len(values)] for i in range(cycle)]
    if parameters.get("pattern_reverse", False):
        values.reverse()
    rotation = int(parameters.get("pattern_rotation", 0))
    if cycle is not None:
        rotation += int(parameters.get("structure_rotation", 0))
    return values[(int(slot) + rotation) % len(values)]
