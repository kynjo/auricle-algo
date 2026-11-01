"""Bounded, deterministic macro curves in normalized section coordinates."""
from __future__ import annotations

import math

CURVE_SHAPES = ("smooth", "linear", "step")
MACRO_COLORS = {"energy": "#ed8b62", "tension": "#bd83f4",
                "density": "#6eafea", "variation": "#55c57e"}


def unit(value, default=0.0):
    try:
        value = float(value)
        return max(0.0, min(1.0, value)) if math.isfinite(value) else default
    except (TypeError, ValueError, OverflowError):
        return default


def normalize_curve(raw, default=.5):
    if not isinstance(raw, dict):
        return None
    points = {}
    source = raw.get("points", [])
    if not isinstance(source, (list, tuple)):
        source = []
    for point in source[:64]:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        try:
            x, y = map(float, point)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            # Preserve exact beat positions even in long sections. Six decimal
            # places shifted snapped steps enough to delay stepped curves.
            points[round(unit(x), 12)] = unit(y)
    if not points:
        points = {0.0: unit(default), 1.0: unit(default)}
    ordered = sorted(points.items())
    points.setdefault(0.0, ordered[0][1])
    points.setdefault(1.0, ordered[-1][1])
    shape = str(raw.get("shape", "smooth"))
    return {"enabled": bool(raw.get("enabled", True)),
            "shape": shape if shape in CURVE_SHAPES else "smooth",
            "points": [[x, y] for x, y in sorted(points.items())]}


def curve_value(curve, progress, fallback=.5):
    """Monotone segments, exact endpoints and no interpolation overshoot."""
    if not curve or not curve.get("enabled", False):
        return unit(fallback)
    points = curve["points"]
    x = unit(progress)
    if x >= points[-1][0]:
        return float(points[-1][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x < x1:
            t = unit((x - x0) / max(1e-9, x1 - x0))
            shape = curve.get("shape", "smooth")
            t = 0.0 if shape == "step" else t * t * (3.0 - 2.0 * t) if shape == "smooth" else t
            return y0 + (y1 - y0) * t
    return float(points[0][1])


def macro_override(section, key):
    return section.get("macros", {}).get(key) is not None


def section_macro(section, key, global_values, progress=0.0):
    value = section.get("macros", {}).get(key)
    if value is None:
        return unit(global_values.get(key, .5), .5)
    return curve_value(section.get("macro_curves", {}).get(key), progress, unit(value))
