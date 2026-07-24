"""Model BOM derivation: the leaves of a model's union tree are its parts.

A model document is one final body, but its boolean-union structure records
how that body was composed. Each union branch that bottoms out in a
geometry-creating op is a BOM line: patterns multiply quantity, modifiers
(move / fillet / cut / ...) pass through to the creator that names the part,
and identical creators group into one line. A single-creator part gets the
standard one-line BOM.

Stated limitation: a folded sheet-metal solid unions its flanges, so its
blank elements appear as lines — pass ``bom=False`` to ``model_drawing``
when that reading is wrong for the part.
"""

from __future__ import annotations

from typing import Any

from gitcad.expr import resolve_value

# ops that create a body (a BOM-visible part)
_CREATORS = frozenset({
    "box", "cylinder", "sphere", "cone", "extrude", "revolve", "loft",
    "sweep", "import",
})
# ops that transform a body without changing what part it is
_PASSTHROUGH = frozenset({"move", "fillet", "chamfer", "shell", "hole"})


def _fmt(v: Any) -> str:
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


def _label(op: str, p: dict[str, Any]) -> str:
    """A human-readable part designation from the creator op + key dims."""
    if op == "box":
        return f"BOX {_fmt(p.get('dx'))}×{_fmt(p.get('dy'))}×{_fmt(p.get('dz'))}"
    if op == "cylinder":
        try:
            dia = _fmt(2.0 * float(p.get("radius", 0.0)))
        except (TypeError, ValueError):
            dia = "?"
        return f"CYL Ø{dia}×{_fmt(p.get('height'))}"
    if op == "sphere":
        try:
            return f"SPHERE Ø{_fmt(2.0 * float(p.get('radius', 0.0)))}"
        except (TypeError, ValueError):
            return "SPHERE"
    if op == "cone":
        return (f"CONE Ø{_fmt(p.get('r1'))}/Ø{_fmt(p.get('r2'))}"
                f"×{_fmt(p.get('height'))}")
    if op == "extrude":
        return f"EXTRUSION t={_fmt(p.get('height'))}"
    if op == "import":
        return f"IMPORT {p.get('file', '?')}"
    return op.upper()


def model_bom(doc, result, kernel) -> list[dict[str, Any]]:
    """Derive BOM lines from a built document.

    Returns ``[{item, qty, label, anchors: [(x, y, z), ...]}, ...]`` where
    anchors are world-mm bbox centers of the placed branch bodies — one per
    distinct union branch, so drawing balloons point at real geometry.
    """
    by_id = {f.id: f for f in doc.features}
    env = doc.resolved_parameters()
    leaves: list[tuple[Any, int, str]] = []   # (creator feature, qty, anchor fid)

    def _count(f) -> int:
        try:
            n = resolve_value({"n": f.params.get("count", 1)}, env)["n"]
            return max(1, int(float(n)))
        except Exception:
            return 1

    def walk(fid: str, mult: int, anchor_fid: str) -> None:
        f = by_id.get(fid)
        if f is None:
            return
        if f.op == "boolean":
            if f.params.get("kind", "union") == "union":
                # composition: each side is its own placed branch
                walk(f.inputs[0], mult, f.inputs[0])
                walk(f.inputs[1], mult, f.inputs[1])
            else:
                # cut/intersect keep the base body's part identity
                walk(f.inputs[0], mult, anchor_fid)
            return
        if f.op in _PASSTHROUGH or (f.op == "extrude" and f.inputs):
            walk(f.inputs[0], mult, anchor_fid)
            return
        if f.op in ("pattern_linear", "pattern_circular", "pattern_table"):
            # anchor at the seed copy so the balloon points at a real body,
            # not the centroid of the whole (possibly hollow) array
            walk(f.inputs[0], mult * _count(f), f.inputs[0])
            return
        if f.op == "mirror":
            fuse = bool(f.params.get("fuse", False))
            walk(f.inputs[0], mult * (2 if fuse else 1), anchor_fid)
            return
        if f.op in _CREATORS:
            leaves.append((f, mult, anchor_fid))

    final_id = doc.features[-1].id
    walk(final_id, 1, final_id)

    lines: dict[str, dict[str, Any]] = {}
    for f, qty, anchor_fid in leaves:
        try:
            rp = resolve_value(f.params, env)
        except Exception:
            rp = f.params
        label = _label(f.op, rp if isinstance(rp, dict) else f.params)
        line = lines.setdefault(label, {"label": label, "qty": 0, "anchors": []})
        line["qty"] += qty
        shape = result.shapes.get(anchor_fid)
        if shape is not None:
            try:
                lo, hi = kernel.bbox(shape)
                a = tuple(round((lo[i] + hi[i]) / 2.0, 3) for i in range(3))
                if a not in line["anchors"]:
                    line["anchors"].append(a)
            except Exception:
                pass   # a balloon-less line still belongs in the table
    return [{"item": i, "qty": ln["qty"], "label": ln["label"],
             "anchors": ln["anchors"]}
            for i, ln in enumerate(lines.values(), start=1)]
