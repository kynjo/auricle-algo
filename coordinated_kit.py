"""A shared 16th-note arrangement for a Drum Kit, independent of voice order."""
from dataclasses import dataclass
import math
import re

from auricle_drum import kit_random, kit_value

ROLES = (("Kick", "kick"), ("Snare", "snare"), ("Closed hat", "closed_hat"),
         ("Open hat", "open_hat"), ("Clap", "clap"), ("Tom", "tom"),
         ("Perc", "perc"), ("Free", "free"))
STYLES = (("Straight", "straight"), ("Half-time", "half_time"), ("Broken", "broken"))
STEP_BEATS = .25
METERS = (("2/4", (4, 4)), ("3/4", (4, 4, 4)), ("4/4", (4, 4, 4, 4)),
          ("5/4", (4, 4, 4, 4, 4)), ("6/8", (6, 6)), ("7/8 · 2+2+3", (4, 4, 6)),
          ("12/8", (6, 6, 6, 6)))
CREATIVE_DEFAULTS = {"kit_complexity": .35, "kit_syncopation": .2,
                     "kit_tom_activity": .35, "kit_variation": .3}


def meter_groups(drum):
    key = str(drum.parameters.get("kit_meter", "4/4"))
    return next((groups for label, groups in METERS if label.split(" · ")[0] == key), (4, 4, 4, 4))


def bar_steps(drum):
    return sum(meter_groups(drum))


def creative_value(drum, key):
    try:
        value = float(drum.parameters.get(key, CREATIVE_DEFAULTS[key]))
        return max(0., min(1., value)) if math.isfinite(value) else CREATIVE_DEFAULTS[key]
    except (TypeError, ValueError):
        return CREATIVE_DEFAULTS[key]


def named_role(name):
    """Voice labels describe the instrument; hardware note maps often aren't GM."""
    words = re.sub(r"[^a-zа-я0-9]+", " ", str(name).casefold()).split()
    tokens = set(words)
    compact = "".join(words)
    if tokens & {"kick", "bd", "бочка"} or compact.startswith("bassdrum"):
        return "kick"
    if tokens & {"snare", "snr", "sd", "снейр"}:
        return "snare"
    if tokens & {"clap", "cp", "хлопок"}:
        return "clap"
    if tokens & {"oh", "ohh"} or compact.startswith(("openhat", "openhihat")):
        return "open_hat"
    if tokens & {"hat", "hihat", "hh", "ch", "chh"} or compact.startswith(("closedhat", "closedhihat")):
        return "closed_hat"
    if tokens & {"tom", "том"}:
        return "tom"
    if tokens & {"perc", "percussion", "перкуссия"}:
        return "perc"
    return None


def infer_role(note, name=""):
    role = named_role(name)
    if role is not None:
        return role
    for role, notes in (("kick", (35, 36)), ("snare", (38, 40)),
                        ("closed_hat", (42, 44)), ("open_hat", (46,)),
                        ("clap", (39,)), ("tom", (41, 43, 45, 47, 48, 50))):
        if int(note) in notes:
            return role
    return "perc"


def voice_role(voice):
    role = str(voice.parameters.get("kit_role", infer_role(voice.midi_note, voice.name)))
    return role if role in {key for _, key in ROLES} else "perc"


def coordinated(drum, voice=None):
    return bool(drum is not None and drum.parameters.get("kit_coordinated", False)
                and (voice is None or voice_role(voice) != "free"))


def phrase_bars(drum):
    try:
        return max(1, min(8, int(drum.parameters.get("kit_phrase_bars", 4))))
    except (TypeError, ValueError, OverflowError):
        return 4


@dataclass(frozen=True)
class KitStep:
    allowed: bool = False
    force: bool = False
    accent: float = 1.0
    fill: bool = False
    anchor: bool = False


@dataclass
class KitPlan:
    start_slot: int
    length: int
    token: tuple
    rows: dict
    steps_per_bar: int = 16
    groups: tuple = (4, 4, 4, 4)
    roles: dict = None

    def at(self, voice_id, slot):
        row = self.rows.get(voice_id)
        return row[int(slot) % self.length] if row else KitStep()

    def can_emit(self, voice_id, slot, protect=True):
        if protect:
            return self.at(voice_id, slot).allowed
        # Unlocked processing may move notes outside the role template;
        # shared fills and hat ownership remain exclusive.
        if any(self.at(vid, slot).fill for vid in self.rows):
            return self.at(voice_id, slot).fill
        role = (self.roles or {}).get(voice_id)
        if role in ("closed_hat", "open_hat"):
            return not any(other != role and other in ("closed_hat", "open_hat")
                           and self.at(vid, slot).allowed for vid, other in self.roles.items())
        return True


class KitCoordinator:
    def __init__(self):
        self.plans = {}

    def plan(self, drum, seed, beat):
        groups = meter_groups(drum)
        steps = sum(groups)
        length = phrase_bars(drum) * steps
        cycle = max(0, int(math.floor(max(0., beat) / (length * STEP_BEATS) + 1e-8)))
        style = str(drum.parameters.get("kit_style", "straight"))
        if style not in {key for _, key in STYLES}:
            style = "straight"
        roster = tuple(sorted((int(v.id), voice_role(v), bool(v.muted)) for v in drum.drum_voices))
        tuning = tuple(creative_value(drum, key) for key in CREATIVE_DEFAULTS)
        complexity, syncopation, toms, variation = tuning
        variant = int(drum.parameters.get("kit_variant", 0))
        token = (int(seed), int(drum.id), cycle, length, groups, style, kit_value(drum, "kit_fill"), roster, tuning, variant)
        previous = self.plans.get(drum.id)
        if previous is not None and previous.token == token:
            return previous
        rows = {vid: [KitStep()] * length for vid, role, muted in roster if role != "free"}
        roles = {vid: role for vid, role, muted in roster if role != "free"}
        owners = {role: [vid for vid, r, muted in roster if r == role and not muted] for _, role in ROLES}
        shared_seed = int(seed) + int(drum.id) * 1009 + variant * 7919
        start = cycle * length
        tail = groups[-1]
        fill_slots = {pos for pos in range(length - tail, length)
                      if kit_random(shared_seed, start + pos, 72) < kit_value(drum, "kit_fill")}
        boundaries = [sum(groups[:i]) for i in range(len(groups))]
        half = boundaries[len(groups) // 2]
        kick = (0, half) if len(groups) > 2 else (0,)
        backbeats = tuple(boundaries[1::2]) or (half,)
        if groups == (4, 4, 4):
            kick, backbeats = (0,), (4, 8)
        if style == "half_time":
            kick, backbeats = (0, min(steps - 1, half + 2)), (half,)
        elif style == "broken":
            kick = tuple(sorted({0, max(1, half - 1), min(steps - 1, half + 2)}))
        kick_extra = tuple(sorted({max(1, half - 2), min(steps - 1, half + 2), steps - 2} - set(kick)))
        if groups == (4, 4, 4, 4) and style == "broken":
            kick_extra = (3, 6, 14)

        def assign(role, pos, force=False, accent=1., fill=False, anchor=False):
            ids = owners[role]
            if ids:
                owner = ids[int(kit_random(shared_seed, pos // steps, 71) * len(ids)) % len(ids)]
                old = rows[owner][pos]
                rows[owner][pos] = KitStep(True, force or old.force, accent, fill or old.fill, anchor or old.anchor)

        for pos in range(length):
            step = pos % steps
            if step in kick or step in kick_extra:
                assign("kick", pos, step in kick, 1.12 if step in kick else .82, anchor=step in kick)
            if step in backbeats:
                assign("snare" if owners["snare"] else "clap", pos, True, 1.08, anchor=True)
            elif step in {max(0, b - 1) for b in backbeats} | {steps - 1}:
                assign("snare", pos, False, .65)
            assign("closed_hat", pos, step % 2 == 0, .92 if step in boundaries else .68,
                   anchor=step % 2 == 0)
            if step in (max(1, half - 2), steps - 2):
                assign("tom", pos, False, .8)
            if step in {b + g - 1 for b, g in zip(boundaries, groups)}:
                assign("perc", pos, False, .72)

        # Compose audible weak-slot material independently of source rests.
        # Variation chooses bounded bar alternatives; zero repeats one pattern.
        for bar in range(phrase_bars(drum)):
            varied = kit_random(shared_seed, cycle * phrase_bars(drum) + bar, 81) < variation
            salt = cycle * phrase_bars(drum) + bar if varied else 0
            base = bar * steps
            weak = [i for i in range(1, steps) if i not in kick and i not in backbeats]

            # Both backbeat instruments need an authored part. An optional
            # clap slot intersected with a sparse source could stay silent
            # forever, regardless of New variant. Share the beat instead of
            # doubling every snare; half-time uses a clap pickup.
            if owners["snare"] and owners["clap"]:
                if len(backbeats) > 1:
                    choice = int(kit_random(shared_seed + salt * 97, 0, 87) * len(backbeats))
                    pos = base + backbeats[choice]
                    for vid in owners["snare"]:
                        rows[vid][pos] = KitStep()
                    assign("clap", pos, True, 1.08, anchor=True)
                else:
                    pool = [i for i in weak if i < backbeats[0] and base + i not in fill_slots]
                    pool = pool or [i for i in weak if base + i not in fill_slots]
                    if pool:
                        pool.sort(key=lambda i: (i % 2, kit_random(shared_seed + salt * 97, i, 87)))
                        assign("clap", base + pool[0], True, .88)

            # Open hats own offbeat slots, excluding the actual fill. Keep a
            # simple ending at Complexity=0; higher values add distinct group
            # offbeats. This also prevents a one-bar fill erasing the whole part.
            if owners["open_hat"]:
                pool = [b + g - 2 for b, g in zip(boundaries, groups)
                        if base + b + g - 2 not in fill_slots]
                pool.sort(key=lambda i: kit_random(shared_seed + salt * 97, i, 88)
                          if complexity > 0 else (i != steps - 2, i))
                count = min(len(pool), 1 + int(math.ceil(complexity * max(1, len(groups) - 2))))
                for i in pool[:count]:
                    for vid in owners["closed_hat"]:
                        rows[vid][base + i] = KitStep()
                    assign("open_hat", base + i, True, .88, anchor=True)

            for role, amount, lane in (("kick", complexity * .7, 82), ("snare", complexity * .6, 83),
                                       ("closed_hat", complexity, 84), ("perc", complexity, 85),
                                       ("tom", toms, 86)):
                pool = [i for i in weak if role != "closed_hat" or (i % 2 and i != steps - 2)]
                # Even subdivisions favour an open groove; Syncopation shifts
                # the preference towards offbeats without moving core anchors.
                pool.sort(key=lambda i: (kit_random(shared_seed + salt * 97, i, lane)
                                        + (0 if i % 2 else syncopation * .7)
                                        + (0 if not i % 2 else (1 - syncopation) * .35)))
                count = min(len(pool), int(math.ceil(amount * (5 if role == "perc" else 4 if role == "tom" else 3)))) if amount > 0 else 0
                for i in pool[:count]:
                    # An open hat still owns its assigned slot.
                    if role == "closed_hat" and any(rows[vid][base + i].allowed for vid in owners["open_hat"]):
                        continue
                    assign(role, base + i, True, .78 if role == "tom" else .58 + .2 * amount)

        for pos in sorted(fill_slots):
            backbeat = [vid for vid in owners["snare"] + owners["clap"] if rows[vid][pos].anchor]
            pool = sorted(owners["snare"] + owners["clap"] + owners["tom"] + owners["perc"])
            pool = pool or sorted(vid for vid, role, muted in roster if role != "free" and not muted)
            for row in rows.values():
                row[pos] = KitStep()
            if pool:
                owner = backbeat[0] if backbeat else pool[(cycle + pos - (length - tail)) % len(pool)]
                rows[owner][pos] = KitStep(True, True, .82 + .3 * (pos - length + tail) / max(1, tail - 1), True, bool(backbeat))
        result = KitPlan(start, length, token, rows, steps, groups, roles)
        self.plans[drum.id] = result
        return result
