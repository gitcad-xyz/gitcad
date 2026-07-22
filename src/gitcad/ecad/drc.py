"""The DRC engine — scoped design rules, geometrically checked (feature-map B4).

Architecture follows the industry's best idea (Altium's rule system): rules
are *data* — typed, scoped, prioritized — and checking is a pure function of
(board, rules). A :class:`RulePack` serializes canonically, so fab capability
profiles become versionable, shareable artifacts (registry parts, ADR-0010).

v1 rule types (all computable on the v0.1 board model):

- ``clearance``       min copper-to-copper distance between different nets
- ``track_width``     min/max track width
- ``annular_ring``    min (via diameter - drill) / 2
- ``drill_size``      min/max drill (vias + through pads + NPTH)
- ``hole_to_hole``    min drill-center spacing
- ``edge_clearance``  min copper distance to board outline bbox edge

Geometry honesty: pads are checked as axis-aligned boxes (exact for the 0/90/
180/270 rotations the fab gate enforces), circles as their bounding box —
conservative, may over-flag by ~0.2·r in diagonal cases, never under-flags.
``checks`` metadata records the method so a clean report can't overstate.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError, ValidationReport
from gitcad.ecad.board import Board

RULE_TYPES = {"clearance", "track_width", "annular_ring", "drill_size",
              "hole_to_hole", "edge_clearance"}


@dataclass
class Rule:
    name: str
    type: str
    params: dict = field(default_factory=dict)   # e.g. {"min": 0.15}
    scope: str = "*"                             # "*" or a net name (v1)

    def __post_init__(self) -> None:
        if self.type not in RULE_TYPES:
            raise GitcadError(f"unknown rule type {self.type!r} (want one of {sorted(RULE_TYPES)})")

    def applies_to(self, net: str) -> bool:
        return self.scope == "*" or self.scope == net


@dataclass
class RulePack:
    """A named, versionable set of rules — a fab's capability profile."""

    name: str
    rules: list[Rule] = field(default_factory=list)

    SCHEMA = "gitcad/rulepack@1"

    def dumps(self) -> str:
        doc = {"schema": self.SCHEMA, "name": self.name,
               "rules": [asdict(r) for r in self.rules]}
        return canonical_json(doc, indent=2) + "\n"

    @classmethod
    def loads(cls, text: str) -> "RulePack":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported rulepack schema {doc.get('schema')!r}")
        return cls(name=doc["name"], rules=[Rule(**r) for r in doc["rules"]])


def default_rules() -> RulePack:
    """A conservative 2-layer prototype-fab profile (0.15mm/6mil class)."""
    return RulePack(name="default-2layer-proto", rules=[
        Rule("clearance", "clearance", {"min": 0.15}),
        Rule("track-width", "track_width", {"min": 0.15}),
        Rule("annular-ring", "annular_ring", {"min": 0.13}),
        Rule("drill-size", "drill_size", {"min": 0.3, "max": 6.5}),
        Rule("hole-to-hole", "hole_to_hole", {"min": 0.5}),
        Rule("edge-clearance", "edge_clearance", {"min": 0.3}),
    ])


# -- geometry helpers (2D, exact for AABBs and segments) ----------------------

def _pt_seg_dist(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _segs_intersect(a1, a2, b1, b2) -> bool:
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2 = ccw(b1, b2, a1), ccw(b1, b2, a2)
    d3, d4 = ccw(a1, a2, b1), ccw(a1, a2, b2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return False


def _seg_seg_dist(a1, a2, b1, b2) -> float:
    if _segs_intersect(a1, a2, b1, b2):
        return 0.0
    return min(_pt_seg_dist(*b1, *a1, *a2), _pt_seg_dist(*b2, *a1, *a2),
               _pt_seg_dist(*a1, *b1, *b2), _pt_seg_dist(*a2, *b1, *b2))


def _aabb_aabb_dist(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = max(ax1 - bx2, bx1 - ax2, 0.0)
    dy = max(ay1 - by2, by1 - ay2, 0.0)
    return math.hypot(dx, dy)


def _seg_aabb_dist(s1, s2, box) -> float:
    x1, y1, x2, y2 = box
    if x1 <= s1[0] <= x2 and y1 <= s1[1] <= y2:
        return 0.0
    if x1 <= s2[0] <= x2 and y1 <= s2[1] <= y2:
        return 0.0
    edges = [((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)),
             ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))]
    return min(_seg_seg_dist(s1, s2, e1, e2) for e1, e2 in edges)


# -- copper item collection ---------------------------------------------------

@dataclass
class _Item:
    kind: str          # track | pad | via
    net: str
    layer: str         # top | bottom | both
    label: str         # for violation detail
    seg: tuple | None = None      # ((x1,y1),(x2,y2), half_width) for tracks
    box: tuple | None = None      # (minx,miny,maxx,maxy) for pads/vias

    def on(self, layer: str) -> bool:
        return self.layer in (layer, "both")


def _items(board: Board) -> list[_Item]:
    out: list[_Item] = []
    for i, t in enumerate(board.tracks):
        out.append(_Item("track", t.net, t.layer, f"track[{i}]",
                         seg=((t.x1, t.y1), (t.x2, t.y2), t.width / 2)))
    for comp in board.components:
        for pad, bx, by, rot in comp.placed_pads():
            w, h = (pad.h, pad.w) if round(rot) % 180 == 90 else (pad.w, pad.h)
            layer = "both" if pad.drill is not None else comp.side
            net = comp.nets.get(pad.name, "")
            out.append(_Item("pad", net, layer, f"{comp.ref}.{pad.name}",
                             box=(bx - w / 2, by - h / 2, bx + w / 2, by + h / 2)))
    for i, v in enumerate(board.vias):
        r = v.diameter / 2
        out.append(_Item("via", v.net, "both", f"via[{i}]",
                         box=(v.x - r, v.y - r, v.x + r, v.y + r)))
    return out


def _copper_dist(a: _Item, b: _Item) -> float:
    """Copper-to-copper clearance between two items (0 = touching/overlap)."""
    if a.seg and b.seg:
        d = _seg_seg_dist(a.seg[0], a.seg[1], b.seg[0], b.seg[1]) - a.seg[2] - b.seg[2]
    elif a.seg and b.box:
        d = _seg_aabb_dist(a.seg[0], a.seg[1], b.box) - a.seg[2]
    elif a.box and b.seg:
        d = _seg_aabb_dist(b.seg[0], b.seg[1], a.box) - b.seg[2]
    else:
        d = _aabb_aabb_dist(a.box, b.box)
    return max(d, 0.0)


# -- the checker --------------------------------------------------------------

def run_drc(board: Board, pack: RulePack | None = None) -> ValidationReport:
    """Check ``board`` against ``pack`` (default profile if omitted).
    Violations are ``code:detail``; ``checks`` records rule counts + method."""
    pack = pack or default_rules()
    violations: list[str] = []
    items = _items(board)
    minx, miny, maxx, maxy = board.bbox()

    by_type: dict[str, list[Rule]] = {}
    for r in pack.rules:
        by_type.setdefault(r.type, []).append(r)

    def limit(rtype: str, net: str, key: str):
        """Tightest applicable bound for a net (scoped rules win via max/min)."""
        vals = [r.params[key] for r in by_type.get(rtype, [])
                if r.applies_to(net) and key in r.params]
        if not vals:
            return None
        return max(vals) if key == "min" else min(vals)

    # clearance: cross-net copper pairs, per layer
    if "clearance" in by_type:
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a.net == b.net and (a.net or b.net):
                    continue
                if not any(a.on(layer) and b.on(layer) for layer in ("top", "bottom")):
                    continue
                need = max(filter(None, (limit("clearance", a.net, "min"),
                                         limit("clearance", b.net, "min"))), default=None)
                if need is None:
                    continue
                d = _copper_dist(a, b)
                if d < need:
                    violations.append(f"clearance:{a.label}<->{b.label}:d={d:.3f}mm<{need}mm")

    # track width
    for i, t in enumerate(board.tracks):
        lo = limit("track_width", t.net, "min")
        hi = limit("track_width", t.net, "max")
        if lo is not None and t.width < lo:
            violations.append(f"track-width:track[{i}]:w={t.width}mm<{lo}mm")
        if hi is not None and t.width > hi:
            violations.append(f"track-width:track[{i}]:w={t.width}mm>{hi}mm")

    # annular ring + drill sizes + hole-to-hole
    holes: list[tuple[float, float, float, str]] = []   # (x, y, drill, label)
    for i, v in enumerate(board.vias):
        holes.append((v.x, v.y, v.drill, f"via[{i}]"))
        ring = (v.diameter - v.drill) / 2
        lo = limit("annular_ring", v.net, "min")
        if lo is not None and ring < lo:
            violations.append(f"annular-ring:via[{i}]:ring={ring:.3f}mm<{lo}mm")
    for comp in board.components:
        for pad, bx, by, _ in comp.placed_pads():
            if pad.drill is not None:
                holes.append((bx, by, pad.drill, f"{comp.ref}.{pad.name}"))
                ring = (min(pad.w, pad.h) - pad.drill) / 2
                lo = limit("annular_ring", comp.nets.get(pad.name, ""), "min")
                if lo is not None and ring < lo:
                    violations.append(f"annular-ring:{comp.ref}.{pad.name}:ring={ring:.3f}mm<{lo}mm")
    for m in board.mounting_holes:
        holes.append((m.x, m.y, m.drill, m.name))

    dlo, dhi = limit("drill_size", "", "min"), limit("drill_size", "", "max")
    for x, y, drill, label in holes:
        if dlo is not None and drill < dlo:
            violations.append(f"drill-size:{label}:d={drill}mm<{dlo}mm")
        if dhi is not None and drill > dhi:
            violations.append(f"drill-size:{label}:d={drill}mm>{dhi}mm")

    hlo = limit("hole_to_hole", "", "min")
    if hlo is not None:
        for i, (x1, y1, d1, l1) in enumerate(holes):
            for x2, y2, d2, l2 in holes[i + 1:]:
                gap = math.hypot(x2 - x1, y2 - y1) - (d1 + d2) / 2
                if gap < hlo:
                    violations.append(f"hole-to-hole:{l1}<->{l2}:gap={gap:.3f}mm<{hlo}mm")

    # edge clearance (against outline bbox edges)
    elo = limit("edge_clearance", "", "min")
    if elo is not None:
        for it in items:
            if it.seg:
                (x1, y1), (x2, y2), hw = it.seg
                d = min(x1 - minx, x2 - minx, maxx - x1, maxx - x2,
                        y1 - miny, y2 - miny, maxy - y1, maxy - y2) - hw
            else:
                bx1, by1, bx2, by2 = it.box
                d = min(bx1 - minx, maxx - bx2, by1 - miny, maxy - by2)
            if d < elo:
                violations.append(f"edge-clearance:{it.label}:d={max(d, 0):.3f}mm<{elo}mm")

    return ValidationReport(
        ok=not violations,
        checks={"rulepack": pack.name, "rules": len(pack.rules),
                "copper_items": len(items), "holes": len(holes),
                "method": "aabb-approximation:outline-bbox"},
        violations=violations,
    )
