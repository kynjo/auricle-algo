"""Musical kit maps, bounded motif grammar and simultaneous voice relations.

The maps below are authored for Auricle; no Grids data or external patches are
embedded. All choices are random-access and use musical slots, never RNG state.
"""
from dataclasses import dataclass
import hashlib
import math

from auricle_drum import kit_random


RHYTHM_ENGINES = (("Role grid", "classic"), ("Rhythm map", "map"),
                  ("Metric / Barlow", "metric"))
MAP_DEFAULTS = {"kit_map_x": .25, "kit_map_y": .25, "kit_motif_change": .45}
LINK_OPERATIONS = (
    ("Support / OR", "support"),
    ("Call → Answer", "answer"),
    ("Avoid source / NOT", "complement"),
    ("Together / AND", "and"),
    ("Either / XOR", "xor"),
    ("Copy pattern", "copy"),
    ("Fill gaps", "gap_fill"),
    ("Interlock / no overlap", "interlock"),
    ("Accent response", "accent"),
)
LINK_DEFAULTS = {"amount": .75, "probability": 1.0, "delay": 0, "phase": 0, "enabled": True}
LINK_DESCRIPTIONS = {
    "support": "OR: keep destination hits and add selected source hits.",
    "answer": "Call / response: answer delayed source hits only when the source is resting and the destination is empty.",
    "complement": "NOT: keep destination hits only where the source is absent.",
    "and": "AND: keep destination hits only where the source is active.",
    "xor": "XOR: toggle destination activity where the source is active.",
    "copy": "Copy: make the destination follow the source pattern.",
    "gap_fill": "Fill gaps: add hits only to empty weak 16th-note slots where the source is silent.",
    "interlock": "Interlock: move coincident destination hits to the nearest free weak slot.",
    "accent": "Accent: strengthen destination hits where the source is active without adding notes.",
}
MAP_PRESETS = (
    ("Pocket", .05, .05),
    ("Straight drive", .05, .95),
    ("Broken pocket", .95, .05),
    ("Broken drive", .95, .95),
    ("Balanced", .5, .5),
)
MOTIF_STATES = ("Theme", "Variation", "Answer", "Fill", "Return")

# Four related 4/4 skeletons. Digits are importance, not velocity. X moves
# towards broken/offbeat placement; Y towards a driving, more active texture.
_MAPS = (
    {"kick": "9000004090000040", "snare": "0000900000029002",
     "closed_hat": "8060806080608060", "open_hat": "0000005000000060",
     "clap": "0000000000008000", "tom": "0000000000000030", "perc": "0003000500030005"},
    {"kick": "9006000700600050", "snare": "0000900200029003",
     "closed_hat": "6060806360608073", "open_hat": "0000007000000060",
     "clap": "0000000000008000", "tom": "0000000000500004", "perc": "0005000506000050"},
    {"kick": "9000900090009000", "snare": "0000900300009003",
     "closed_hat": "8373837383738373", "open_hat": "0070007000700070",
     "clap": "0000000000008000", "tom": "0000003000000050", "perc": "0030005000300050"},
    {"kick": "9000007090600007", "snare": "0030900200609005",
     "closed_hat": "6383638363836383", "open_hat": "0007000000070000",
     "clap": "0000000000008000", "tom": "0000005000000056", "perc": "0050006500500065"},
)


def unit(parameters, key, default=0.):
    try:
        value = float(parameters.get(key, default))
        return max(0., min(1., value)) if math.isfinite(value) else default
    except (TypeError, ValueError, OverflowError):
        return default


def integer(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def rhythm_engine(drum):
    value = drum.parameters.get("kit_engine")
    return value if value in ("map", "metric") else "classic"


def map_scores(role, steps, x, y, groups=None):
    """Bilinearly morph four authored groove skeletons onto any bar length.

    Templates are sampled with circular linear interpolation instead of
    nearest-step/max projection. This avoids duplicated or skipped accents in
    compound and odd meters while keeping the 4/4 templates bit-aligned.
    """
    steps = max(1, int(steps))
    x = max(0.0, min(1.0, float(x)))
    y = max(0.0, min(1.0, float(y)))
    weights = ((1-x)*(1-y), x*(1-y), (1-x)*y, x*y)
    templates = [tuple(int(char) / 9.0 for char in node.get(role, "0" * 16)) for node in _MAPS]
    values = []
    for target in range(steps):
        source_position = ((target + .5) * 16.0 / steps) - .5
        low = math.floor(source_position)
        fraction = source_position - low
        low_index, high_index = low % 16, (low + 1) % 16
        score = 0.0
        for weight, template in zip(weights, templates):
            sample_value = template[low_index] * (1.0 - fraction) + template[high_index] * fraction
            score += weight * sample_value
        values.append(max(0.0, min(1.0, score)))

    # Group boundaries in compound/odd meters receive a small structural
    # preference. The main anchors are still authored and protected by the
    # coordinator; this only shapes optional map material.
    if groups:
        cursor = 0
        boundaries = set()
        for group in groups:
            group = max(1, int(group))
            boundaries.add(cursor)
            # In compound groups, the third eighth is a secondary pulse.
            if group >= 6:
                boundaries.add(cursor + 4)
            cursor += group
        for index in range(min(steps, cursor)):
            if index in boundaries:
                values[index] = min(1.0, values[index] * 1.08)
    return values


@dataclass(frozen=True)
class RhythmContext:
    """Composition boundaries; the common kit clock is never restarted."""
    section_id: str = ""
    origin_slot: int = 0
    end_slot: int | None = None

    @property
    def salt(self):
        if not self.section_id:
            return 0
        return int.from_bytes(hashlib.blake2s(self.section_id.encode("utf-8"), digest_size=4).digest(), "big")


def motif_states(parameters, seed, start_slot, steps, bars, context):
    """Replay at most 16 phrase transitions, so seek/preview has no history.

    Return is a true thematic return; Fill always resolves to Return. Every
    return window starts on Theme, even after hours of playback or a seek.
    """
    if not parameters.get("kit_motif_enabled", False):
        return ("Theme",) * bars
    amount = unit(parameters, "kit_motif_change", MAP_DEFAULTS["kit_motif_change"])
    every = integer(parameters.get("kit_motif_return", 4), 4, 2, 16)
    states = []
    for bar in range(bars):
        position = start_slot + bar * steps
        local = max(0, position - context.origin_slot)
        absolute_bar = local // steps
        window, in_window = divmod(absolute_bar, bars * every)
        state = "Theme"
        # Replay one short return window. Even a seek many hours ahead costs
        # at most 16 * 8 transitions, with no dependence on call order.
        for index in range(1, in_window + 1):
            phrase, phrase_bar = divmod(index, bars)
            if state == "Fill" or phrase == every - 1:
                state = "Return"
                continue
            draw = kit_random(seed + context.salt, window * every * bars + index, 121)
            if draw >= amount or (phrase_bar == 0 and state == "Return"):
                state = "Theme" if state == "Return" or phrase_bar == 0 else state
            else:
                options = ("Variation", "Answer", "Fill") if phrase_bar == bars - 1 else ("Variation", "Answer")
                state = options[int(kit_random(seed + context.salt, window * every * bars + index, 122) * len(options))]
        if amount <= 0:
            state = "Theme"
        if context.end_slot is not None and position < context.end_slot <= position + steps:
            state = "Fill"
        states.append(state)
    return tuple(states)


def normalized_links(drum):
    """Return canonical, validated voice links with backward-compatible defaults.

    Legacy links only stored amount/delay. Missing probability/phase fields
    therefore mean probability=1 and phase=0, preserving their old behaviour.
    """
    voices = {v.id for v in (drum.drum_voices or [])
              if not v.muted and v.parameters.get("kit_role") != "free"}
    operations = {key for _, key in LINK_OPERATIONS}
    raw = drum.parameters.get("kit_voice_links", [])
    result = []
    for item in raw[:64] if isinstance(raw, list) else ():
        if not isinstance(item, dict) or not item.get("enabled", True):
            continue
        source, destination = item.get("source"), item.get("destination")
        operation = item.get("operation")
        if (type(source) is not int or type(destination) is not int or source not in voices
                or destination not in voices or source == destination or not isinstance(operation, str)
                or operation not in operations):
            continue
        amount = unit(item, "amount", LINK_DEFAULTS["amount"])
        probability = unit(item, "probability", LINK_DEFAULTS["probability"])
        delay = integer(item.get("delay", 0), 0, 0, 32)
        phase = integer(item.get("phase", 0), 0, -32, 32)
        if amount <= 0 or probability <= 0:
            continue
        result.append((source, destination, operation, amount, delay, phase, probability))
    # Canonical ordering and deduplication make the graph independent of UI row
    # order, voice iteration order and duplicate serialized rows.
    return tuple(sorted(set(result)))


def suggested_links(drum):
    """Suggest role-aware interlocks; only endpoints present in this kit are used."""
    roles = {}
    for voice in sorted(drum.drum_voices or [], key=lambda v: v.id):
        role = voice.parameters.get("kit_role")
        if not voice.muted and role and role != "free":
            roles.setdefault(role, voice.id)
    suggestions = (
        ("snare", "clap", "answer", .42, 2, 0, .85),
        ("kick", "perc", "gap_fill", .38, 0, 0, .80),
        ("snare", "tom", "answer", .48, 2, 0, .75),
        ("closed_hat", "open_hat", "interlock", .65, 0, 0, 1.0),
    )
    result = []
    for source, destination, operation, amount, delay, phase, probability in suggestions:
        if source in roles and destination in roles and roles[source] != roles[destination]:
            result.append(dict(source=roles[source], destination=roles[destination], operation=operation,
                               amount=amount, delay=delay, phase=phase, probability=probability, enabled=True))
    return result


def enable_musical_kit(drum):
    drum.parameters.update(kit_coordinated=True, kit_engine="map", kit_motif_enabled=True,
                           kit_motif_return=4, kit_links_enabled=True)
    for key, value in MAP_DEFAULTS.items():
        drum.parameters.setdefault(key, value)
    drum.parameters.setdefault("kit_fill", .25)
    drum.parameters.setdefault("kit_voice_links", suggested_links(drum))


def _is_weak_slot(position, groups=()):
    """True for 16th offbeats, excluding explicit metric group starts."""
    if int(position) % 2 == 0:
        return False
    if not groups:
        return True
    cursor = 0
    starts = set()
    for group in groups:
        starts.add(cursor)
        cursor += max(1, int(group))
    return int(position) not in starts


def _copy_step(step_type, previous, *, allowed=None, force=None, accent=None, importance=None):
    resolved_allowed = previous.allowed if allowed is None else bool(allowed)
    resolved_force = previous.force if force is None else bool(force)
    if resolved_allowed and not previous.allowed:
        resolved_force = True
    return step_type(
        resolved_allowed,
        resolved_force,
        previous.accent if accent is None else float(accent),
        previous.fill,
        previous.anchor,
        previous.importance if importance is None else float(importance),
    )


def apply_voice_links(drum, seed, start, rows, step_type, groups=()):
    """Apply intelligent kit Relations simultaneously from an immutable snapshot.

    ``amount`` is the strength/chance of influence, ``probability`` is an
    additional route gate, ``delay`` is causal lag, and ``phase`` is a signed
    cyclic offset. Metric anchors and fill slots are immutable. Additive,
    subtractive, copy, XOR and accent actions are combined in a stable order.
    """
    if not drum.parameters.get("kit_links_enabled", False) or not rows:
        return
    links = normalized_links(drum)
    if not links:
        return
    snapshot = {vid: tuple(row) for vid, row in rows.items()}
    size = len(next(iter(snapshot.values())))
    if size <= 0:
        return

    actions = {}
    for source, destination, operation, amount, delay, phase, probability in links:
        if source not in snapshot or destination not in snapshot:
            continue
        source_row = snapshot[source]
        destination_row = snapshot[destination]
        route_key = (source, destination, operation, delay, phase)
        chance = amount * probability
        for pos, previous in enumerate(destination_row):
            # Keep authored metric anchors and fill events as immutable kit
            # structure. A fill in another voice also owns the whole slot.
            if previous.anchor or previous.fill or any(row[pos].fill for row in snapshot.values()):
                continue
            source_index = (pos - delay - phase) % size
            source_hit = bool(source_row[source_index].allowed)
            source_now = bool(source_row[pos].allowed)
            draw = kit_random(seed + source * 17 + destination * 31 + phase * 7,
                              start + pos, 160 + sum(ord(char) for char in operation))
            if draw >= chance:
                continue
            key = (destination, pos)
            state = actions.setdefault(key, {"adds": [], "gates": [], "sets": [], "xors": 0,
                                              "accents": [], "interlocks": []})
            strength = chance
            if operation == "support":
                if source_hit:
                    state["adds"].append((strength, route_key))
            elif operation == "answer":
                if source_hit and not source_now and not previous.allowed:
                    state["adds"].append((strength, route_key))
            elif operation == "complement":
                # Destination AND NOT source: keep its own events only in the
                # spaces left by the source, rather than generating new hits.
                if source_hit:
                    state["gates"].append((strength, route_key))
            elif operation == "and":
                if not source_hit:
                    state["gates"].append((strength, route_key))
            elif operation == "xor":
                if source_hit:
                    state["xors"] += 1
            elif operation == "copy":
                state["sets"].append((strength, route_key, source_hit))
            elif operation == "gap_fill":
                if not source_hit and not previous.allowed and _is_weak_slot(pos, groups):
                    state["adds"].append((strength, route_key))
            elif operation == "interlock":
                if source_hit and previous.allowed:
                    state["interlocks"].append((strength, route_key))
            elif operation == "accent":
                if source_hit and previous.allowed:
                    state["accents"].append((strength, route_key))

    # Resolve every destination slot once. No operation can read a mutation
    # made by another route, and ties are broken by stable route identity.
    for (destination, pos), state in sorted(actions.items()):
        previous = snapshot[destination][pos]
        desired = bool(previous.allowed)
        if state["sets"]:
            strongest = max(state["sets"], key=lambda item: (item[0], tuple(str(value) for value in item[1])))
            desired = bool(strongest[2])
        if state["xors"] % 2:
            desired = not desired
        if state["adds"]:
            desired = True
        # Gate/anti-lock rules have priority over additive rules at the same
        # slot, so contradictory links cannot create order-dependent hits.
        if state["gates"]:
            desired = False
        if desired != previous.allowed:
            rows[destination][pos] = _copy_step(step_type, previous, allowed=desired,
                                                 accent=max(previous.accent, .78) if desired else previous.accent,
                                                 importance=max(previous.importance, .45) if desired else previous.importance)
        if state["accents"] and rows[destination][pos].allowed:
            amount = min(.5, math.fsum(item[0] for item in state["accents"]) * .35)
            current = rows[destination][pos]
            rows[destination][pos] = _copy_step(step_type, current,
                accent=min(1.5, current.accent * (1.0 + amount)),
                importance=min(1.0, current.importance + amount * .35))

    # Interlock moves coincident destination hits to the nearest free weak
    # slot within one beat. If no safe target exists, the original event stays.
    reserved = set()
    for (destination, origin), state in sorted(actions.items()):
        if not state["interlocks"]:
            continue
        current = rows[destination][origin]
        if not current.allowed or current.anchor or current.fill:
            continue
        candidates = [((origin + offset) % size) for offset in range(1, 5)
                      if _is_weak_slot((origin + offset) % size, groups)]
        target = next((candidate for candidate in candidates
                       if (destination, candidate) not in reserved
                       and not snapshot[destination][candidate].allowed
                       and not rows[destination][candidate].allowed
                       and not snapshot[destination][candidate].anchor
                       and not snapshot[destination][candidate].fill
                       and not any(row[candidate].fill for row in snapshot.values())), None)
        if target is None:
            continue
        reserved.add((destination, target))
        rows[destination][origin] = _copy_step(step_type, current, allowed=False)
        rows[destination][target] = step_type(True, True, min(1.35, current.accent * .92), False, False,
                                              min(.85, max(.25, current.importance * .92)))


def compose_map(drum, seed, start, steps, groups, owners, rows, step_type, states):
    """Author all voices from one map while retaining the meter's anchors."""
    parameters = drum.parameters
    x, y = (unit(parameters, key, default) for key, default in
            (("kit_map_x", .25), ("kit_map_y", .25)))
    complexity = unit(parameters, "kit_complexity", .35)
    sync = unit(parameters, "kit_syncopation", .2)
    toms = unit(parameters, "kit_tom_activity", .35)
    variation = unit(parameters, "kit_variation", .3)
    motifs = bool(parameters.get("kit_motif_enabled", False))
    for role, ids in owners.items():
        if not ids or role == "free":
            continue
        scores = map_scores(role, steps, x, y, groups)
        if parameters.get("kit_style") == "half_time" and role in ("snare", "clap"):
            scores = [min(score, .22) for score in scores]
        for bar, state in enumerate(states):
            base = bar * steps
            salt = (start // steps + bar) if not motifs and variation > 0 else 0
            if motifs and state not in ("Theme", "Return"):
                salt = start // steps + bar + {"Variation": 17, "Answer": 31, "Fill": 47}[state]
            for i in range(steps):
                pos = base + i
                existing = next((rows[vid][pos] for vid in ids if rows[vid][pos].anchor), None)
                if existing is not None:
                    continue
                for vid in ids:
                    rows[vid][pos] = step_type()
                value = scores[i]
                value += (.12 * sync if i % 2 else -.06 * sync)
                if role == "tom":
                    value *= toms * 1.8
                threshold = .66 - .42 * complexity
                noise = kit_random(seed, i + salt * steps, 130 + list(owners).index(role))
                threshold += (noise - .5) * .12 * variation
                if state == "Answer":
                    value += .16 if i >= steps // 2 and role in ("tom", "perc", "snare") else -.08
                elif state == "Variation":
                    value += (noise - .35) * .22
                elif state == "Fill" and i >= steps - groups[-1]:
                    value += .12 * unit(parameters, "kit_fill", 0.)
                if value <= threshold or value <= .05:
                    continue
                owner = ids[int(kit_random(seed, bar if salt else 0, 151) * len(ids)) % len(ids)]
                importance = max(.12, min(.88, value))
                accent = .60 + .35 * importance
                rows[owner][pos] = step_type(True, True, accent, False, False, importance)


def resolve_exclusions(rows, roles, step_type):
    """Final ownership pass shared by map and Relations: no double hats."""
    if not rows:
        return
    for pos in range(len(next(iter(rows.values())))):
        for candidates in (("closed_hat", "open_hat"), ("snare", "clap")):
            active = [vid for vid in rows if roles.get(vid) in candidates and rows[vid][pos].allowed]
            if len(active) < 2:
                continue
            winner = max(active, key=lambda vid: (rows[vid][pos].fill, rows[vid][pos].anchor,
                         roles.get(vid) == candidates[1], rows[vid][pos].importance, -vid))
            for vid in active:
                if vid != winner:
                    rows[vid][pos] = step_type()


def retained(step, amount, sample, musical, variation=.5, event_class=None):
    """Density removes ornaments before support; metric anchors stay intact."""
    if amount <= 0:
        return False
    # The kit's authored Keep-beat mask remains authoritative at the master
    # kit-density stage. The later class gate can still treat protected hat
    # eighths as Support rather than as structural Anchors.
    if event_class == "anchor" or (step is not None and step.anchor):
        return True
    if step is None:
        keep = amount
        if event_class == "ornament":
            keep *= max(0.0, min(1.0, float(variation) * 2.0))
        return sample < keep
    if amount >= 1 and variation >= .5:
        return True
    importance = max(0.0, min(1.0, float(step.importance)))
    keep = amount * (.5 + .5 * importance)
    if event_class == "ornament" or (event_class is None and (step.fill or importance < .60)):
        keep *= max(0.0, min(1.0, float(variation) * 2.0))
    return sample < keep
