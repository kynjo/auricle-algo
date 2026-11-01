"""Deterministic stream graph for user Relations, independent of editor order.

Built-in role shaping supplies the baseline. Explicit routes then form a
stream graph; rhythm/velocity dependencies are graph edges too. Internal
edges of a strongly connected component read one step of history.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict, deque
from copy import deepcopy

from auricle_catalogs import PARTS, PERCUSSIVE_TYPES, ROLE_PROFILES
from auricle_model import block_root, relation_endpoint_id
from coordinated_kit import coordinated
from harmonic_plan import nearest_tone


RELATION_DESCRIPTIONS = {
    "Copy": "Replace selected events with the source. Amount controls the fraction replaced; 0 bypasses.",
    "Mix": "Blend numeric values; for rhythm, add selected source hits without deleting existing hits.",
    "Follow": "Pitch follows the nearest source pitch class. Other values follow the source envelope; rhythm gates existing hits.",
    "Quantize To": "Snap destination values to the source's values/pitch classes; rhythm snaps existing hits to source onsets.",
    "Modulate": "Add source influence, bounded to the destination range; rhythm adds selected source hits.",
    "Trigger": "Positive source activity supplies a unit trigger. Amount controls its influence; 0 bypasses.",
}


def finite(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError, OverflowError):
        return default


def unit(value):
    return max(0.0, min(1.0, finite(value)))


def identity(route):
    # The fallback excludes Amount/Probability: moving either knob must not
    # reshuffle the selected events. It also survives project row reordering.
    rid = int(getattr(route, "id", 0))
    return (rid, relation_endpoint_id(route, "source"), route.source_part,
            relation_endpoint_id(route, "destination"), route.destination_part, route.algorithm)


def sample(seed, key, slot, lane):
    raw = hashlib.blake2b(repr((int(seed), key, int(slot), lane)).encode(), digest_size=8).digest()
    return int.from_bytes(raw, "big") / float(1 << 64)


def active(route):
    return (getattr(route, "enabled", True) and route.algorithm in RELATION_DESCRIPTIONS
            and finite(route.amount) > 0 and finite(getattr(route, "probability", 1)) > 0
            and route.source_part in PARTS and route.destination_part in PARTS)


def components(graph):
    """Tarjan components in dependency order, with deterministic traversal."""
    indices, low, stack, pending, result = {}, {}, [], set(), []

    def visit(node):
        indices[node] = low[node] = len(indices)
        stack.append(node); pending.add(node)
        for neighbour in sorted(graph[node]):
            if neighbour not in indices:
                visit(neighbour); low[node] = min(low[node], low[neighbour])
            elif neighbour in pending:
                low[node] = min(low[node], indices[neighbour])
        if low[node] == indices[node]:
            group = []
            while True:
                member = stack.pop(); pending.remove(member); group.append(member)
                if member == node: break
            result.append(sorted(group))

    for node in sorted(graph):
        if node not in indices: visit(node)
    return list(reversed(result))


def stream_graph(blocks, routes):
    graph = {(b.id, part): set() for b in blocks.values() for part in PARTS}
    for route in routes:
        graph[(relation_endpoint_id(route, "source"), route.source_part)].add(
            (relation_endpoint_id(route, "destination"), route.destination_part))
    for owner in blocks:
        for part in ("velocity", "duration", "density", "accent"):
            graph[(owner, "rhythm")].add((owner, part))
        graph[(owner, "velocity")].add((owner, "accent"))
    return graph


class RelationRuntime:
    def __init__(self, engine):
        self.engine = engine
        self.history = defaultdict(lambda: deque(maxlen=256))
        self.feedback = {}
        self._in_tick = False
        self._parents_advanced = set()
        self._committed = None
        self._activity = False
        self._published = {}
        # The relation graph depends on project topology, not on the current
        # numeric stream values. Cache it so LIVE events do not rebuild the
        # same owner map, route list, graph and SCC decomposition every time.
        self._plan_signature = None
        self._plan_cache = None

    def reset(self):
        self.history.clear(); self.feedback.clear()
        self._in_tick = False
        self._parents_advanced.clear()
        self._committed = None
        self._activity = False
        self._published.clear()

    def forget(self, owners):
        """Invalidate only edited sources while preserving other LIVE delays."""
        for mapping in (self.history, self.feedback, self._published, self._committed or {}):
            for bid in owners:
                mapping.pop(bid, None)
        self._parents_advanced.difference_update(owners)

    def _owners(self):
        """All relation-capable owners, including Drum Machine voices."""
        owners = {}
        for block in self.engine.project.blocks:
            owners[int(block.id)] = block
            for voice in getattr(block, "drum_voices", None) or []:
                owners[int(voice.id)] = voice
        return owners

    def _execution_plan(self, *, force=False):
        """Return cached structural relation data, rebuilding only after edits.

        The transport holds its state lock for a complete scheduler tick. Once
        begin_tick() has refreshed the plan, all relation operations in that
        tick share it; this avoids re-hashing the same project topology for
        every LIVE event. Calls outside playback still validate edits eagerly.
        """
        if self._in_tick and not force and self._plan_cache is not None:
            return self._plan_cache
        owners = self._owners()
        owner_signature = tuple(
            (int(block.id), id(block), tuple((int(v.id), id(v)) for v in (getattr(block, "drum_voices", None) or [])))
            for block in self.engine.project.blocks
        )
        route_signature = tuple(
            (id(route), int(getattr(route, "id", 0)), relation_endpoint_id(route, "source"),
             str(getattr(route, "source_part", "")), relation_endpoint_id(route, "destination"),
             str(getattr(route, "destination_part", "")), str(getattr(route, "algorithm", "")),
             bool(getattr(route, "enabled", True)), finite(getattr(route, "amount", 0.0)),
             str(getattr(route, "curve", "Linear")), finite(getattr(route, "probability", 1.0)),
             max(0, int(getattr(route, "delay", 0))))
            for route in self.engine.project.relations
        )
        signature = (owner_signature, route_signature)
        if signature == self._plan_signature and self._plan_cache is not None:
            return self._plan_cache

        ids = set(owners)
        routes = sorted((route for route in self.engine.project.relations
                         if active(route)
                         and relation_endpoint_id(route, "source") in ids
                         and relation_endpoint_id(route, "destination") in ids
                         and self.engine._relation_curve(finite(route.amount), getattr(route, "curve", "Linear")) > 0),
                        key=identity)
        incoming = defaultdict(list)
        sources = set()
        rhythm_changed, velocity_changed = set(), set()
        for route in routes:
            source_id = relation_endpoint_id(route, "source")
            destination_id = relation_endpoint_id(route, "destination")
            sources.add(source_id)
            incoming[(destination_id, route.destination_part)].append(route)
            if route.destination_part == "rhythm": rhythm_changed.add(destination_id)
            if route.destination_part == "velocity": velocity_changed.add(destination_id)
        graph = stream_graph(owners, routes)
        plan = {
            "owners": owners, "routes": routes, "sources": sources,
            "incoming": incoming, "graph": graph, "components": components(graph),
            "rhythm_changed": rhythm_changed, "velocity_changed": velocity_changed,
        }
        self._plan_signature = signature
        self._plan_cache = plan
        return plan

    def advance_source(self, block):
        """Keep the previous published LIVE attempt, including rests."""
        if int(block.id) in self._execution_plan()["sources"]:
            self.history[block.id].appendleft(deepcopy(self._published.get(block.id, {})))
            self._activity = True
        self.advance_parent(block)

    def publish_source(self, block):
        # A graph refresh may modify the visible outputs between attempts.
        # Delay must retain the actual published attempt, not that later edit.
        if int(block.id) in self._execution_plan()["sources"]:
            self._published[block.id] = deepcopy(block.outputs)

    def advance_parent(self, voice):
        parent = self.engine.drum_parent_for(voice)
        if parent is None or parent.mode != 'LIVE' or coordinated(parent): return
        if int(parent.id) not in self._execution_plan()["sources"]: return
        if not self._in_tick or parent.id not in self._parents_advanced:
            before = self.feedback.get(parent.id, parent.outputs) if self._in_tick else parent.outputs
            self.history[parent.id].appendleft(deepcopy(before))
            self._parents_advanced.add(parent.id)
            self._activity = True

    def begin_tick(self):
        # One frozen frame for all LIVE owners of a transport tick. Repeated
        # apply()/UI refreshes never advance feedback by themselves.
        plan = self._execution_plan(force=True)
        sources = plan["sources"]
        initial = {b.id: deepcopy(b.outputs) for b in plan["owners"].values()
                   if b.id in sources and b.mode == 'LIVE'} if self._committed is None else self._committed
        # _committed is already an immutable snapshot of the previous tick.
        # It is read-only during relation evaluation, so copying it on every
        # 2-ms scheduler poll only burns CPU and allocates thousands of lists.
        self.feedback = initial
        self._in_tick = True
        self._activity = False
        self._parents_advanced.clear()

    def end_tick(self):
        if self._activity:
            plan = self._execution_plan()
            sources = plan["sources"]
            self._committed = {b.id: deepcopy(b.outputs) for b in plan["owners"].values()
                               if b.id in sources and b.mode == 'LIVE'}
        elif self._committed is None:
            # feedback was copied from live outputs in begin_tick; it is safe
            # to promote that frozen frame directly.
            self._committed = self.feedback
        self._in_tick = False

    def routes(self):
        return list(self._execution_plan()["routes"])

    def cycles(self):
        plan = self._execution_plan()
        graph = plan["graph"]
        found = set()
        for group in plan["components"]:
            members = set(group)
            if len(group) == 1 and group[0] not in graph[group[0]]: continue
            # One concrete cycle witness per component; no rotated duplicates.
            start = group[0]
            def walk(node, path):
                for nxt in sorted(graph[node] & members):
                    if nxt == start: return path + [start]
                    if nxt not in path:
                        answer = walk(nxt, path + [nxt])
                        if answer: return answer
                return None
            path = walk(start, [start])
            ids = []
            for owner, _part in path or []:
                if not ids or owner != ids[-1]: ids.append(owner)
            if len(ids) == 1: ids.append(ids[0])
            if ids:
                if ids[-1] != ids[0]: ids.append(ids[0])
                ring = ids[:-1]
                canonical = min(tuple(ring[i:] + ring[:i]) for i in range(len(ring)))
                found.add(canonical + (canonical[0],))
        return [list(cycle) for cycle in sorted(found)]

    def apply(self, skip_destination=None):
        e = self.engine
        plan = self._execution_plan()
        blocks = plan["owners"]
        all_routes = plan["routes"]
        routes = [r for r in all_routes if relation_endpoint_id(r, "destination") != skip_destination]
        # A built-in role relation may still run in MusicEngine, but the
        # explicit graph has no work. Do not copy every block's streams just
        # to discover that the route list is empty.
        if not routes: return
        # Streams are flat numeric lists. Copy each list once, rather than
        # recursively visiting every immutable number for every MIDI event.
        baseline = {b.id: {part: list(stream) for part, stream in b.outputs.items()} for b in blocks.values()}
        if skip_destination is None:
            incoming = plan["incoming"]
            rhythm_changed = plan["rhythm_changed"]
            velocity_changed = plan["velocity_changed"]
        else:
            incoming = defaultdict(list)
            for r in routes:
                incoming[(relation_endpoint_id(r, "destination"), r.destination_part)].append(r)
            rhythm_changed = {relation_endpoint_id(r, "destination") for r in routes if r.destination_part == "rhythm"}
            velocity_changed = {relation_endpoint_id(r, "destination") for r in routes if r.destination_part == "velocity"}
        graph = plan["graph"]
        values = {(bid, part): list(out.get(part, [])) for bid, out in baseline.items() for part in PARTS}
        lengths = {bid: max((len(v) for v in out.values()), default=0) for bid, out in baseline.items()}
        for r in routes:
            destination_id = relation_endpoint_id(r, "destination")
            source_id = relation_endpoint_id(r, "source")
            if not lengths[destination_id]: lengths[destination_id] = max(1, lengths[source_id])

        def read(stream, index, default=0.0):
            return finite(stream[index % len(stream)], default) if stream else default

        def bounds(block, part):
            if part == "duration": return 0.0, 1.5
            if part != "pitch": return 0.0, 1.0
            base = int(block.midi_note) + block_root(e.project, block) % 12
            return -float(base), 127.0 - base

        def convert(value, source, destination, src_part, dst_part):
            if src_part == dst_part: return value
            if src_part == "pitch":
                center = finite(source.parameters.get("role_center", 0))
                width = max(6, finite(source.parameters.get("role_width", 24), 24))
                normalized = unit((value - center + width / 2) / width)
            else:
                normalized = unit(value / (1.5 if src_part == "duration" else 1.0))
            if dst_part == "pitch":
                center = finite(destination.parameters.get("role_center", 0))
                width = max(6, finite(destination.parameters.get("role_width", 24), 24))
                return center + (normalized - .5) * width
            return normalized * (1.5 if dst_part == "duration" else 1.0)

        def normalize(value, block, part):
            lo, hi = bounds(block, part)
            value = max(lo, min(hi, finite(value)))
            if part == "pitch" and block.block_type not in PERCUSSIVE_TYPES:
                value = e._quantize_pitch(block, value)
                if block.block_type in ROLE_PROFILES:
                    base = int(block.midi_note) + block_root(e.project, block) % 12
                    value = float(nearest_tone(block, base, base+value, {round(base+value) % 12}) - base)
                # Octave placement preserves scale membership at MIDI edges.
                while value < lo: value += 12
                while value > hi: value -= 12
            return value

        for group in plan["components"]:
            if not any(incoming[node] or (node[0] in rhythm_changed and node[1] in ("velocity", "duration", "density", "accent"))
                       or (node[0] in velocity_changed and node[1] == "accent") for node in group):
                continue
            members = set(group)
            cyclic = len(group) > 1 or group[0] in graph[group[0]]
            order = sorted(group, key=lambda node: ({"rhythm": 0, "pitch": 1, "velocity": 2,
                                                   "duration": 3, "density": 4, "accent": 5}[node[1]], node[0]))
            count = max((lengths[node[0]] for node in group), default=0)
            for node in group:
                if incoming[node] or (node[0] in rhythm_changed and node[1] in ("velocity", "duration", "density", "accent")) or (node[0] in velocity_changed and node[1] == "accent"):
                    values[node] = [0.0] * lengths[node[0]]
            for i in range(count):
                for node in order:
                    bid, part = node
                    block = blocks[bid]
                    if i >= lengths[bid]: continue
                    affected = (incoming[node] or (bid in rhythm_changed and part in ("velocity", "duration", "density", "accent"))
                                or (bid in velocity_changed and part == "accent"))
                    if not affected: continue
                    original = read(baseline[bid].get(part, []), i)
                    rhythm = read(values[(bid, "rhythm")], i, 1)
                    if bid in rhythm_changed:
                        if part == "velocity" and rhythm > 0 and original <= 0:
                            original = unit(block.parameters.get("velocity_base", .72))
                        if part == "duration" and rhythm > 0 and original <= 0:
                            original = finite(block.parameters.get("gate", .78), .78)
                        if part == "density": original = float(rhythm > 0)
                    if part == "accent" and (bid in rhythm_changed or bid in velocity_changed):
                        original = float(rhythm > 0 and read(values[(bid, "velocity")], i) >= .85)
                    slot = (int(e.live_state.get(bid, {}).get("events", 1)) - 1) if block.mode == "LIVE" else i
                    blends, additions, envelopes = [], [], []
                    rhythm_add, rhythm_follow = [], []
                    for r in incoming[node]:
                        source_id = relation_endpoint_id(r, "source")
                        source = blocks[source_id]
                        src_node = (source.id, r.source_part)
                        feedback = cyclic and src_node in members
                        delay = max(0, int(getattr(r, "delay", 0)))
                        if feedback: delay = max(1, delay)
                        source_values = values[src_node]
                        index = i
                        source_parent = e.drum_parent_for(source)
                        source_coordinated = coordinated(source_parent, source) if source_parent is not None else False
                        if block.mode == "LIVE" and (source.mode != "LIVE" or source_coordinated):
                            index += e.source_positions.get(source.id, 0)
                        if source.mode == "LIVE" and not source_coordinated and delay:
                            history = self.history[source.id]
                            if feedback and delay == 1:
                                source_values = self.feedback.get(source.id, {}).get(r.source_part, [])
                            else:
                                source_values = history[delay-1].get(r.source_part, []) if len(history) >= delay else []
                            s = read(source_values, 0)
                        elif feedback:
                            s = read(source_values, index-delay) if index >= delay else 0.0
                        else:
                            s = read(source_values, index-delay)
                        if not source_values and not delay: continue
                        if sample(e.project.seed, identity(r), slot, "probability") >= unit(getattr(r, "probability", 1)): continue
                        a = e._relation_curve(finite(r.amount), getattr(r, "curve", "Linear"))
                        target = convert(s, source, block, r.source_part, part)
                        if r.algorithm == "Quantize To":
                            if part == "rhythm" and (feedback or block.mode == "LIVE"):
                                target = float(original > 0 and s > 0)
                            elif part == "rhythm":
                                # Snap existing onsets to the nearest source onset,
                                # preserving a rest if there is no quantization grid.
                                hits = [k for k in range(lengths[bid]) if read(source_values, k-delay) > 0]
                                own = baseline[bid].get("rhythm", [])
                                snapped = {min(hits, key=lambda k: (abs(k-j), k)) for j, hit in enumerate(own) if hit > 0} if hits else set()
                                target = float(i in snapped)
                            elif part == "pitch" and r.source_part == "pitch":
                                pool = [s] if feedback else source_values
                                target = self.nearest_pitch(e, source, block, original, pool or [s])
                            else:
                                pool = [convert(finite(v), source, block, r.source_part, part)
                                        for v in ([s] if feedback else source_values)]
                                target = min(pool, key=lambda v: (abs(v-original), v)) if pool else original
                        elif r.algorithm == "Follow" and part == "pitch" and r.source_part == "pitch":
                            target = self.nearest_pitch(e, source, block, original, [s])
                        elif r.algorithm == "Trigger": target = float(s > 0)

                        if part == "rhythm":
                            target = float(target > 0)
                            if r.algorithm in ("Mix", "Modulate"): rhythm_add.append(a * target)
                            elif r.algorithm == "Follow": rhythm_follow.append(1-a*(1-target))
                            else: blends.append((a, target))
                        elif r.algorithm == "Copy":
                            if sample(e.project.seed, identity(r), slot, "copy") < a: blends.append((1.0, target))
                        elif r.algorithm == "Modulate": additions.append(a * target)
                        elif r.algorithm == "Follow" and part != "pitch":
                            envelope = unit(target / (1.5 if part == "duration" else 1))
                            envelopes.append(1-a*(1-envelope))
                        else: blends.append((a, target))
                    weight = math.fsum(w for w, _ in blends)
                    value = (original * max(0.0, 1-weight) + math.fsum(w*v for w, v in blends)) / max(1.0, weight)
                    if part == "rhythm":
                        value = (1-(1-unit(value))*math.prod(1-x for x in rhythm_add)) * math.prod(rhythm_follow)
                        value = float(sample(e.project.seed, (bid, part), slot, "rhythm") < unit(value))
                    else:
                        value = (value + math.fsum(additions)) * math.prod(envelopes)
                        value = normalize(value, block, part)
                    if part in ("velocity", "duration", "accent", "density") and rhythm <= 0: value = 0.0
                    values[node][i] = value
        for bid, block in blocks.items():
            for part in PARTS:
                if values[(bid, part)]: block.outputs[part] = values[(bid, part)]

    @staticmethod
    def nearest_pitch(engine, source, destination, value, pitches):
        source_base = int(source.midi_note) + block_root(engine.project, source) % 12
        dest_base = int(destination.midi_note) + block_root(engine.project, destination) % 12
        pcs = {int(round(source_base + finite(p))) % 12 for p in pitches}
        candidates = [float(n-dest_base) for n in range(128) if n % 12 in pcs]
        return min(candidates, key=lambda n: (abs(n-value), n)) if candidates else value
