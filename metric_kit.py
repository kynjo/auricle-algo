"""Barlow metre, density-preserving probabilities and bounded anticipation.

Independent Python implementation of the principles in Sioros & Guedes,
kin.rhythmicator (NIME 2011). Role orchestration, additive 7/8 and bar-boundary
resolution are Auricle adaptations; this is not a port of the Max patch.
No Qt, mutable random generator or playback history is used here.
"""
from dataclasses import dataclass
from functools import lru_cache
from math import prod

from auricle_drum import kit_random
from drum_rhythm import integer, unit


# default, minimum, maximum; integers stay integers in automation and MIDI Learn.
METRIC_PARAMETERS = {
    "kit_metric_density": (.45, 0., 1.),
    "kit_metric_strength": (.85, 0., 1.),
    "kit_metric_fragment": (2, 1, 8),
}
_PRIME_RANKS = {2: (1, 0), 3: (2, 0, 1), 5: (4, 0, 3, 1, 2)}
_ROLES = ("kick", "snare", "closed_hat", "open_hat", "clap", "tom", "perc")


def _factors(number):
    factors = []
    for prime in (5, 3, 2):
        while number > 1 and number % prime == 0:
            factors.append(prime)
            number //= prime
    if number != 1:
        raise ValueError("Unsupported metric grouping")
    return tuple(factors)


def indispensability(factors):
    """Ranks 0..N-1, pulse zero strongest. Prime order defines the metre."""
    factors = tuple(factors)
    if not factors or any(p not in _PRIME_RANKS for p in factors):
        raise ValueError("Metric strata must use primes 2, 3 or 5")
    count = prod(factors)
    ranks = []
    for pulse in range(count):
        phase, divisor, rank = (pulse - 1) % count, 1, 0
        for index in range(len(factors) - 1, -1, -1):
            prime = factors[index]
            digit = (phase // divisor + 1) % prime
            rank += prod(factors[:index]) * _PRIME_RANKS[prime][digit]
            divisor *= prime
        ranks.append(rank)
    return tuple(ranks)


@dataclass(frozen=True)
class MetricProfile:
    groups: tuple
    factors: tuple
    ranks: tuple
    levels: tuple


@lru_cache(maxsize=32)
def metric_profile(groups):
    """Compound metres preserve grouping; 7/8 uses the supplied 2+2+3.

    Unequal groups are truncated from an equal-group parent, then remaining
    ranks are compressed. Thus 7/8 has group starts at 0, 4, 8, rather than a
    fictitious undifferentiated prime-7 bar.
    """
    groups = tuple(groups)
    if not groups or any(type(g) is not int or g < 1 for g in groups):
        raise ValueError("Positive integer metric groups are required")
    width = max(groups)
    factors = _factors(len(groups)) + _factors(width)
    ranks = indispensability(factors)
    count = len(ranks)
    levels = tuple(next(i for i in range(1, len(factors) + 1)
                        if rank >= count - prod(factors[:i])) for rank in ranks)
    positions = tuple(group * width + pulse for group, size in enumerate(groups)
                      for pulse in range(size))
    retained = sorted(ranks[pulse] for pulse in positions)
    compressed = {rank: i for i, rank in enumerate(retained)}
    return MetricProfile(groups, factors, tuple(compressed[ranks[p]] for p in positions),
                         tuple(levels[p] for p in positions))


def metric_weights(profile, density):
    """Each stratum i spans [R**i, R**(i-1)], in rank order."""
    density = unit({"value": density}, "value", .45)
    weights = [0.] * len(profile.ranks)
    for level in sorted(set(profile.levels)):
        pulses = sorted((i for i, item in enumerate(profile.levels) if item == level),
                        key=profile.ranks.__getitem__, reverse=True)
        high, low = density ** (level - 1), density ** level
        for index, pulse in enumerate(pulses):
            weights[pulse] = high - (high - low) * index / max(1, len(pulses) - 1)
    return tuple(weights)


def event_probabilities(weights, strength):
    """M changes metrical contrast, preserving the expected event count ΣW."""
    strength = unit({"value": strength}, "value", .85)
    shaped = tuple(weight ** strength if strength else 1. for weight in weights)
    total = sum(shaped)
    normalizer = sum(weights) / total if total else 0.
    return tuple(min(1., normalizer * weight) for weight in shaped)


def metric_accents(profile, strength, seed, lane):
    """Amplitude distribution is independent of R; M shuffles its placement."""
    strength = unit({"value": strength}, "value", .85)
    accents = list(metric_weights(profile, .5))
    for index in range(len(accents) - 1, 0, -1):
        if kit_random(seed, index, lane) >= strength:
            other = min(index, int(kit_random(seed, index, lane + 1) * (index + 1)))
            accents[index], accents[other] = accents[other], accents[index]
    return tuple(.55 + .6 * value for value in accents)


def anticipation_sources(groups, probability, fragment, seed, lane=240):
    """Destination for every source pulse (None means a deliberately muted beat).

    Runs anticipate by one 16th. At the run limit shifting is suspended until
    the next group boundary, which resolves normally. Short runs that stop on
    a stress mute that stress. Pulse zero always resolves at the bar boundary;
    no note leaks into a preceding bar, section or loop.
    """
    probability = unit({"value": probability}, "value", .2)
    limit = integer(fragment, 2, 1, 8)
    boundaries = {sum(groups[:i]) for i in range(len(groups))}
    destinations = list(range(sum(groups)))
    run, waiting = 0, False
    for pulse in range(1, len(destinations)):
        if waiting:
            if pulse in boundaries:
                waiting, run = False, 0
            continue
        if kit_random(seed, pulse, lane) < probability:
            destinations[pulse] = pulse - 1
            run += 1
            if run >= limit:
                waiting = True
        else:
            if run and pulse in boundaries:
                destinations[pulse] = None
            run = 0
    return tuple(destinations)


def metric_settings(drum):
    return (unit(drum.parameters, "kit_metric_density", .45),
            unit(drum.parameters, "kit_metric_strength", .85),
            integer(drum.parameters.get("kit_metric_fragment", 2), 2, 1, 8))


def compose_metric(drum, seed, start, steps, groups, owners, rows, Step, states):
    """Orchestrate one metric model across roles, then let shared links/fills act."""
    profile = metric_profile(tuple(groups))
    density, strength, fragment = metric_settings(drum)
    weights = metric_weights(profile, density)
    complexity = unit(drum.parameters, "kit_complexity", .35)
    syncopation = unit(drum.parameters, "kit_syncopation", .2)
    variation = unit(drum.parameters, "kit_variation", .3)
    toms = unit(drum.parameters, "kit_tom_activity", .35)
    boundaries = tuple(sum(groups[:i]) for i in range(len(groups)))
    backbeat = boundaries[len(groups) // 2] if drum.parameters.get("kit_style") == "half_time" else boundaries[1]
    broken = drum.parameters.get("kit_style") == "broken"
    phases = {"kick": 0, "snare": backbeat, "clap": backbeat,
              "closed_hat": 0, "open_hat": max(0, groups[0] - 2),
              "tom": boundaries[-1], "perc": 2 if broken else 0}
    exponents = {"kick": 2.4 - complexity, "snare": 2.8 - complexity,
                 "clap": 3.2 - complexity, "closed_hat": .75 - .35 * complexity,
                 "open_hat": 3.5 - complexity, "tom": 3. - complexity,
                 "perc": 3.5 - 2. * complexity}
    for row in rows.values():
        row[:] = [Step()] * len(row)
    for bar, state in enumerate(states):
        base, absolute_bar = bar * steps, (start // steps) + bar
        # Theme/Return reuse decisions. Variation/Answer get deterministic
        # development without advancing a mutable RNG or depending on seeking.
        development = absolute_bar if state in ("Variation", "Answer", "Fill") else 0
        for role_index, role in enumerate(_ROLES):
            pool = owners.get(role, ())
            if not pool or (role == "tom" and toms <= 0):
                continue
            lane = 300 + role_index * 10
            role_weights = tuple(w ** exponents[role] for w in weights)
            probabilities = event_probabilities(role_weights, strength)
            accents = metric_accents(profile, strength, seed + development * 97, lane + 2)
            phase = phases[role]
            move = anticipation_sources(groups, syncopation, fragment,
                                        seed + development * 97, lane + 4)
            for source in range(steps):
                evolving = kit_random(seed, source, lane + 7) < variation
                bar_seed = seed + (absolute_bar if evolving else development) * 193
                metric_source = (source - phase) % steps
                probability = probabilities[metric_source]
                if role == "tom":
                    probability *= toms
                if state == "Answer" and role in ("kick", "closed_hat"):
                    probability *= .65
                if kit_random(bar_seed, source, lane) >= probability:
                    continue
                target = move[source]
                if target is None:
                    continue
                importance = weights[metric_source]
                anchor = source == target and source == phase and strength >= .5
                if drum.parameters.get("kit_style") == "half_time" and role in ("snare", "clap"):
                    # Keep a half-time backbeat; other hits remain weak decoration.
                    if source in boundaries and source != backbeat:
                        continue
                owner = pool[min(len(pool) - 1, int(kit_random(seed, absolute_bar, lane + 8) * len(pool)))]
                step = Step(True, True, accents[metric_source], False, anchor, importance)
                previous = rows[owner][base + target]
                # A collision is one hit, never a second Note On or summed velocity.
                if not previous.allowed or (step.anchor, step.importance) > (previous.anchor, previous.importance):
                    rows[owner][base + target] = step
