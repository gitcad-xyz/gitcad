"""Entity-selection DSL — the dogfood's face-picking friction, fixed.

Selecting "the back face" previously meant filtering descriptors by centroid
arithmetic. Now a query string does it:

    "plane,zmax"      the planar face(s) with the largest centroid z
    "cylinder"        all cylindrical faces
    "line,zmin"       bottom edges
    "area_max"        the single largest face

Tokens (comma = AND): surface/curve type names (plane, cylinder, line,
circle, ...), extreme selectors ``{x,y,z}{max,min}`` on the centroid, and
``area_max``/``area_min``/``length_max``/``length_min``. Extreme selectors
keep everything within tolerance of the extreme, so four tied bottom edges
all match "zmin".
"""

from __future__ import annotations

from typing import Any

from gitcad.errors import GitcadError

_TOL = 1e-6
_AXES = {"x": 0, "y": 1, "z": 2}


def select_entities(entities: list[dict[str, Any]], query: str) -> list[int]:
    """Indices (enumeration order) of entities matching every token."""
    keep = list(range(len(entities)))
    for token in (t.strip() for t in query.split(",") if t.strip()):
        if token[:-3] in _AXES and token[-3:] in ("max", "min"):
            axis, kind = _AXES[token[:-3]], token[-3:]
            vals = {i: entities[i].get("centroid", [0, 0, 0])[axis] for i in keep}
            if not vals:
                return []
            extreme = max(vals.values()) if kind == "max" else min(vals.values())
            keep = [i for i in keep if abs(vals[i] - extreme) <= _TOL]
        elif token in ("area_max", "area_min", "length_max", "length_min"):
            key, kind = token.rsplit("_", 1)
            vals = {i: entities[i].get(key) for i in keep if entities[i].get(key) is not None}
            if not vals:
                return []
            extreme = max(vals.values()) if kind == "max" else min(vals.values())
            keep = [i for i in keep if vals.get(i) is not None and abs(vals[i] - extreme) <= _TOL]
        elif token.isidentifier():
            keep = [i for i in keep
                    if entities[i].get("surface") == token or entities[i].get("curve") == token]
        else:
            raise GitcadError(f"bad select token {token!r}")
    return keep
