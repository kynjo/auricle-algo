"""Experimental deterministic generators for Auricle.

The functions in this module are pure sequence builders. They return the same
legacy material contract as :mod:`generators`: rhythm algorithms use 1.0/0.0,
pitch algorithms use semitone offsets and ``None`` for rests. Randomized initial
conditions always come from an explicit ``random.Random`` instance.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from generators import degree_to_note, scale_intervals


def _bounded_int(value, low, high, default):
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(low, min(high, value))


def _bits(seed: str, length: int) -> list[int]:
    raw = [1 if char == "1" else 0 for char in str(seed) if char in "01"]
    if not raw:
        raw = [0, 0, 0, 1, 0, 0, 0, 0]
    return (raw * (max(1, length) // len(raw) + 1))[:max(1, length)]


def turing_machine(
    length: int,
    *,
    preset: str = "Busy Beaver",
    tape: str = "00010000",
    mode: str = "Rhythm",
    root: int = 60,
    scale_name: str = "Major",
    density: float = 1.0,
    wrap: bool = True,
    rng: Optional[random.Random] = None,
) -> list[float | None]:
    """Run a small binary Turing machine or a deterministic marble rotor.

    ``Busy Beaver``, ``Alternator`` and ``Growth`` are two-state machines.
    ``Marbles`` is a multi-particle ring: particles move in opposite directions,
    and a collision reverses the participating particles. A collision is the
    generated event. The finite tape/head prevents unbounded execution.
    """
    n = max(1, int(length))
    preset = str(preset)
    mode = str(mode)
    density = max(0.0, min(1.0, float(density)))
    cells = _bits(tape, n)
    rng = rng or random.Random(0)
    raw: list[tuple[int, int]] = []  # (symbol/sector, event flag)

    if preset == "Marbles":
        count = 2
        positions = [0, n // 2]
        directions = [1, -1]
        for _ in range(n):
            old = list(positions)
            positions = [(pos + direction) % n for pos, direction in zip(positions, directions)]
            collided: set[int] = set()
            for i in range(count):
                for j in range(i + 1, count):
                    same_cell = positions[i] == positions[j]
                    crossed = positions[i] == old[j] and positions[j] == old[i]
                    if same_cell or crossed:
                        collided.update((i, j))
            if collided:
                for index in collided:
                    directions[index] *= -1
                sector = sum(positions[index] for index in sorted(collided)) // len(collided)
                raw.append((sector, 1))
            else:
                raw.append((0, 0))
    else:
        # Transition tuple: (symbol to write, movement, next state).
        tables = {
            "Busy Beaver": {
                (0, 0): (1, 1, 1), (0, 1): (1, -1, 1),
                (1, 0): (1, -1, 0), (1, 1): (1, 1, 2),
            },
            "Alternator": {
                (0, 0): (1, 1, 1), (0, 1): (0, 1, 1),
                (1, 0): (0, -1, 0), (1, 1): (1, -1, 0),
            },
            "Growth": {
                (0, 0): (1, 1, 0), (0, 1): (1, 1, 1),
                (1, 0): (0, -1, 0), (1, 1): (1, -1, 1),
            },
        }
        table = tables.get(preset, tables["Busy Beaver"])
        head = n // 2
        state = 0
        for _ in range(n):
            symbol = cells[head]
            write, movement, next_state = table[(state, symbol)]
            cells[head] = write
            # A transition is musically active when it changes the tape.
            # This keeps the Busy Beaver preset from degenerating into a
            # constant stream after the machine has filled the tape with 1s.
            raw.append((head + state * 2 + write, int(write != symbol)))
            state = next_state
            candidate = head + movement
            if wrap:
                head = candidate % n
            else:
                if candidate < 0 or candidate >= n:
                    movement *= -1
                    candidate = head + movement
                head = max(0, min(n - 1, candidate))
            if state == 2:  # halting transition: restart the machine on its current tape
                state = 0
                head = n // 2

    count = len(scale_intervals(scale_name))
    out: list[float | None] = []
    for index, (value, active) in enumerate(raw[:n]):
        if not active or (density < 1.0 and rng.random() >= density):
            out.append(0.0 if mode == "Rhythm" else None)
        elif mode == "Rhythm":
            out.append(1.0)
        else:
            degree = (int(value) + index) % count
            out.append(float(degree_to_note(degree, root, scale_name) - root))
    return out


def orbital_sequence(
    length: int,
    *,
    cycle_a: int = 8,
    cycle_b: int = 5,
    phase_a: int = 0,
    phase_b: int = 0,
    combine: str = "OR",
    output: str = "Rhythm",
    rotation: int = 0,
    root: int = 60,
    scale_name: str = "Major",
) -> list[float | None]:
    """Create interlocking periodic orbits on one shared discrete grid."""
    n = max(0, int(length))
    a = _bounded_int(cycle_a, 1, 256, 8)
    b = _bounded_int(cycle_b, 1, 256, 5)
    pa, pb = int(phase_a), int(phase_b)
    combine = str(combine).upper()
    output = str(output)
    scale_count = len(scale_intervals(scale_name))
    result: list[float | None] = []
    for i in range(n):
        hit_a = (i + pa) % a == 0
        hit_b = (i + pb) % b == 0
        if combine == "A":
            hit = hit_a
        elif combine == "B":
            hit = hit_b
        elif combine == "AND":
            hit = hit_a and hit_b
        elif combine == "XOR":
            hit = hit_a != hit_b
        elif combine == "INTERLOCK":
            # Both clocks may coincide, but only alternating coincidences
            # survive; this creates a slower, phase-sensitive interlock.
            coincident = hit_a and hit_b
            hit = (hit_a != hit_b) or (coincident and ((i // a + i // b) % 2 == 0))
        else:
            hit = hit_a or hit_b
        if not hit:
            result.append(0.0 if output == "Rhythm" else None)
        elif output == "Rhythm":
            result.append(1.0)
        else:
            source_degree = (i // a + 2 * (i // b) + (0 if hit_a else 1)) % scale_count
            result.append(float(degree_to_note(source_degree, root, scale_name) - root))
    if result:
        r = int(rotation) % len(result)
        if r:
            result = result[r:] + result[:r]
    return result


def geometry_collision(
    length: int,
    *,
    shape: str = "Box",
    particles: int = 2,
    speed: float = 1.0,
    substeps: int = 24,
    mode: str = "Rhythm",
    root: int = 60,
    scale_name: str = "Major",
    rng: Optional[random.Random] = None,
) -> list[float | None]:
    """Generate events from deterministic billiard collisions in a box/circle.

    Every output slot advances each particle through a bounded number of
    microsteps. Collisions are quantized to that slot. In pitch mode the side
    (box) or angular sector (circle) selects a scale degree; slots without a
    collision are explicit rests.
    """
    n = max(0, int(length))
    if not n:
        return []
    rng = rng or random.Random(0)
    shape = str(shape).title()
    mode = str(mode)
    count = _bounded_int(particles, 1, 8, 2)
    microsteps = _bounded_int(substeps, 4, 96, 24)
    speed = max(0.1, min(4.0, float(speed)))
    # Positions are kept away from the walls to avoid an immediate corner burst.
    objects = []
    for _ in range(count):
        x, y = rng.uniform(.18, .82), rng.uniform(.18, .82)
        angle = rng.uniform(0.0, math.tau)
        objects.append([x, y, math.cos(angle), math.sin(angle)])
    scale_count = len(scale_intervals(scale_name))
    step_size = 0.12 * speed / microsteps
    result: list[float | None] = []

    for slot in range(n):
        collision_degrees: list[int] = []
        for _ in range(microsteps):
            for particle in objects:
                x, y, vx, vy = particle
                x += vx * step_size
                y += vy * step_size
                if shape == "Circle":
                    dx, dy = x - .5, y - .5
                    radius = math.hypot(dx, dy)
                    limit = .46
                    if radius >= limit:
                        if radius <= 1e-12:
                            nx, ny = 1.0, 0.0
                        else:
                            nx, ny = dx / radius, dy / radius
                        dot = vx * nx + vy * ny
                        if dot > 0:
                            vx -= 2.0 * dot * nx
                            vy -= 2.0 * dot * ny
                        x, y = .5 + nx * (limit - 1e-6), .5 + ny * (limit - 1e-6)
                        angle = (math.atan2(ny, nx) + math.pi) / math.tau
                        collision_degrees.append(int(angle * 8) % 8)
                elif shape in ("Triangle", "Hexagon"):
                    sides = 3 if shape == "Triangle" else 6
                    apothem = .46 * math.cos(math.pi / sides)
                    dx, dy = x - .5, y - .5
                    for side in range(sides):
                        angle = math.tau * side / sides - math.pi / 2.0
                        nx, ny = math.cos(angle), math.sin(angle)
                        distance = dx * nx + dy * ny
                        if distance > apothem:
                            dot = vx * nx + vy * ny
                            if dot > 0:
                                vx -= 2.0 * dot * nx
                                vy -= 2.0 * dot * ny
                            correction = distance - apothem + 1e-6
                            x -= nx * correction
                            y -= ny * correction
                            collision_degrees.append(int(round(side * 8 / sides)) % 8)
                            break
                else:
                    if x < 0.0:
                        x, vx = -x, abs(vx)
                        collision_degrees.append(0)
                    elif x > 1.0:
                        x, vx = 2.0 - x, -abs(vx)
                        collision_degrees.append(2)
                    if y < 0.0:
                        y, vy = -y, abs(vy)
                        collision_degrees.append(4)
                    elif y > 1.0:
                        y, vy = 2.0 - y, -abs(vy)
                        collision_degrees.append(6)
                    x = max(0.0, min(1.0, x))
                    y = max(0.0, min(1.0, y))
                particle[:] = [x, y, vx, vy]
        if not collision_degrees:
            result.append(0.0 if mode == "Rhythm" else None)
        elif mode == "Rhythm":
            result.append(1.0)
        else:
            degree = int(round(sum(collision_degrees) / len(collision_degrees))) % scale_count
            result.append(float(degree_to_note(degree, root, scale_name) - root))
    return result


def cellular_automaton_evolved(
    length: int,
    *,
    rule: int = 30,
    seed: str = "00100000",
    generations: int = 8,
    mode: str = "Rhythm",
    root: int = 60,
    scale_name: str = "Major",
    density: float = 1.0,
    boundary: str = "Wrap",
    evolution: str = "Evolution Trail",
    rng: Optional[random.Random] = None,
) -> list[float | None]:
    """One-dimensional elementary CA with selectable boundary and time output."""
    n = max(0, int(length))
    if not n:
        return []
    seed_width = max(1, min(256, len([char for char in str(seed) if char in "01"])))
    row = _bits(seed, seed_width)
    rule = _bounded_int(rule, 0, 255, 30)
    generations = _bounded_int(generations, 0, 64, 8)
    boundary = str(boundary).title()
    evolution = str(evolution)
    rows = [row[:]]

    def cell_at(index: int) -> int:
        if 0 <= index < len(row):
            return row[index]
        if boundary == "Fixed":
            return 0
        if boundary == "Mirror":
            return row[0 if index < 0 else -1]
        return row[index % len(row)]

    for _ in range(generations):
        nxt = []
        for i in range(len(row)):
            neighborhood = (cell_at(i - 1) << 2) | (row[i] << 1) | cell_at(i + 1)
            nxt.append((rule >> neighborhood) & 1)
        row = nxt
        rows.append(row[:])

    if evolution == "Final Row":
        selected = [(bit, generations, i) for i, bit in enumerate(rows[-1])]
    elif evolution == "XOR Trail":
        selected = []
        for i in range(len(rows[0])):
            bit = 0
            for generation, values in enumerate(rows):
                bit ^= values[i]
            selected.append((bit, generations, i))
    else:  # Evolution Trail
        selected = [(bit, generation, i) for generation, values in enumerate(rows[1:], 1)
                    for i, bit in enumerate(values)] or [(bit, 0, i) for i, bit in enumerate(rows[0])]
    if not selected:
        selected = [(0, 0, i) for i in range(n)]
    selected = (selected * (n // len(selected) + 1))[:n]
    density = max(0.0, min(1.0, float(density)))
    rng = rng or random.Random(0)
    count = len(scale_intervals(scale_name))
    out: list[float | None] = []
    for index, (bit, generation, column) in enumerate(selected):
        active = bool(bit) and (density >= 1.0 or rng.random() < density)
        if not active:
            out.append(0.0 if mode == "Rhythm" else None)
        elif mode == "Rhythm":
            out.append(1.0)
        else:
            if evolution in ("Final Row", "XOR Trail"):
                degree = column % count
            else:
                degree = (column + generation + index // max(1, len(rows[0]))) % count
            out.append(float(degree_to_note(degree, root, scale_name) - root))
    return out


def lsystem_sequence_extended(
    length: int,
    *,
    axiom: str = "A",
    rule_a: str = "AB",
    rule_b: str = "A",
    iterations: int = 3,
    mode: str = "Pitch",
    mapping: str = "0,1,2,3,4,5,6",
    root: int = 60,
    scale_name: str = "Major",
) -> list[float | None]:
    """L-system with an optional turtle stack for branching phrases."""
    from generators import parse_number_list

    n = max(0, int(length))
    text = str(axiom)
    for _ in range(max(0, min(10, int(iterations)))):
        text = "".join(rule_a if char == "A" else rule_b if char == "B" else char for char in text)
        if len(text) > 16384:
            text = text[:16384]
            break
    if not n:
        return []
    stream = (list(text) * (n // max(1, len(text)) + 1))[:n]
    mode = str(mode)
    if mode == "Rhythm":
        return [1.0 if char in "A1X+F" else 0.0 for char in stream]
    raw = parse_number_list(mapping, int, range(len(scale_intervals(scale_name))))
    symbols = {chr(ord("A") + i): raw[i % len(raw)] for i in range(26)}
    if not mode.startswith("Turtle"):
        return [float(degree_to_note(symbols.get(char, 0), root, scale_name) - root) for char in stream]

    current = 0
    stack: list[int] = []
    out: list[float | None] = []
    draw_symbols = set("ABFGXY1")
    for char in stream:
        if char == "+":
            current += 1
            out.append(None if mode == "Turtle Pitch" else 0.0)
        elif char == "-":
            current -= 1
            out.append(None if mode == "Turtle Pitch" else 0.0)
        elif char == "[":
            stack.append(current)
            out.append(None if mode == "Turtle Pitch" else 0.0)
        elif char == "]":
            if stack:
                current = stack.pop()
            out.append(None if mode == "Turtle Pitch" else 0.0)
        elif char in draw_symbols:
            if mode == "Turtle Rhythm":
                out.append(1.0)
            else:
                degree = int(symbols.get(char, symbols.get("A", 0))) + current
                out.append(float(degree_to_note(degree, root, scale_name) - root))
        else:
            out.append(None if mode == "Turtle Pitch" else 0.0)
    return out
