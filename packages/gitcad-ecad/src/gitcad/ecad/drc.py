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
        if self.scope == "*" or self.scope == net:
            return True
        if any(ch in self.scope for ch in "*?[") :
            from fnmatch import fnmatchcase

            return fnmatchcase(net, self.scope)
        return False


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
    kind: str          # track | pad | via | zone
    net: str
    layer: str         # top | bottom | both
    label: str         # for violation detail
    seg: tuple | None = None      # ((x1,y1),(x2,y2), half_width) for tracks
    box: tuple | None = None      # (minx,miny,maxx,maxy) for pads/vias
    poly: list | None = None      # closed polygon for zones
    owner: str = ""               # component ref for pads (intra-footprint skip)

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
            it = _Item("pad", net, layer, f"{comp.ref}.{pad.name}",
                       box=(bx - w / 2, by - h / 2, bx + w / 2, by + h / 2))
            it.owner = comp.ref
            out.append(it)
    for i, v in enumerate(board.vias):
        r = v.diameter / 2
        out.append(_Item("via", v.net, "both", f"via[{i}]",
                         box=(v.x - r, v.y - r, v.x + r, v.y + r)))
    for i, z in enumerate(board.zones):
        if z.kind != "copper":
            continue                     # keepouts are rules, not copper
        pts = list(z.polygon)
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        out.append(_Item("zone", z.net, z.layer, f"zone[{i}]", poly=pts))
    return out


def _pt_in_poly(x: float, y: float, poly) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _poly_dist(item: "_Item", poly) -> float:
    """Copper distance from a seg/box/poly item to a zone polygon (0 = touch/in)."""
    edges = list(zip(poly, poly[1:]))
    if item.poly is not None:
        a = item.poly
        if (any(_pt_in_poly(x, y, poly) for x, y in a)
                or any(_pt_in_poly(x, y, a) for x, y in poly)):
            return 0.0
        return min(_seg_seg_dist(p1, p2, e1, e2)
                   for p1, p2 in zip(a, a[1:]) for e1, e2 in edges)
    if item.seg:
        (a, b, hw) = item.seg
        if _pt_in_poly(a[0], a[1], poly) or _pt_in_poly(b[0], b[1], poly):
            return 0.0
        return max(min(_seg_seg_dist(a, b, e1, e2) for e1, e2 in edges) - hw, 0.0)
    x1, y1, x2, y2 = item.box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    if _pt_in_poly(cx, cy, poly):
        return 0.0
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    return min(_seg_seg_dist(c1, c2, e1, e2)
               for c1, c2 in zip(corners, corners[1:]) for e1, e2 in edges)


def _copper_dist(a: _Item, b: _Item) -> float:
    """Copper-to-copper clearance between two items (0 = touching/overlap)."""
    if a.poly or b.poly:
        if a.poly and b.poly:
            # zone-zone: any vertex of one inside the other, or edge distance
            if any(_pt_in_poly(x, y, b.poly) for x, y in a.poly) or                     any(_pt_in_poly(x, y, a.poly) for x, y in b.poly):
                return 0.0
            return min(_seg_seg_dist(e1, e2, f1, f2)
                       for e1, e2 in zip(a.poly, a.poly[1:])
                       for f1, f2 in zip(b.poly, b.poly[1:]))
        zone, other = (a, b) if a.poly else (b, a)
        return _poly_dist(other, zone.poly)
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

def expand_net_classes(board: Board) -> list[Rule]:
    """Board net classes -> net-scoped rules (KiCad-map P1). Each class's
    net patterns (fnmatch globs allowed) get scoped rules that the tightest-
    bound resolution in ``limit`` naturally lets OVERRIDE pack defaults."""
    rules: list[Rule] = []
    for cname, spec in sorted(board.net_classes.items()):
        for pattern in spec.get("nets", []):
            if "clearance" in spec:
                rules.append(Rule(f"class-{cname}-clearance", "clearance",
                                  {"min": spec["clearance"]}, scope=pattern))
            if "track_width_min" in spec:
                rules.append(Rule(f"class-{cname}-width", "track_width",
                                  {"min": spec["track_width_min"]}, scope=pattern))
    return rules


def run_drc(board: Board, pack: RulePack | None = None) -> ValidationReport:
    """Check ``board`` against ``pack`` (default profile if omitted) plus the
    board's own net classes, expanded into net-scoped rules.
    Violations are ``code:detail``; ``checks`` records rule counts + method."""
    pack = pack or default_rules()
    class_rules = expand_net_classes(board)
    if class_rules:
        pack = RulePack(name=f"{pack.name}+netclasses",
                        rules=list(pack.rules) + class_rules)
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
                if a.net == b.net == "" and a.owner and a.owner == b.owner:
                    continue   # unnetted pads of one footprint: its own geometry
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
                if it.box is not None:
                    bx1, by1, bx2, by2 = it.box
                else:  # zone: bounds of its polygon
                    xs = [p[0] for p in it.poly]
                    ys = [p[1] for p in it.poly]
                    bx1, by1, bx2, by2 = min(xs), min(ys), max(xs), max(ys)
                d = min(bx1 - minx, maxx - bx2, by1 - miny, maxy - by2)
            if d < elo:
                violations.append(f"edge-clearance:{it.label}:d={max(d, 0):.3f}mm<{elo}mm")

    # keepout rule areas (KiCad-map P2): copper intersecting a keepout is a
    # violation — tracks, vias, and copper zones; keepouts never conduct
    keepouts = [(i, z) for i, z in enumerate(board.zones) if z.kind == "keepout"]
    for ki, kz in keepouts:
        pts = list(kz.polygon)
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        for it in items:
            if not it.on(kz.layer):
                continue
            if _poly_dist(it, pts) <= 0.0:
                violations.append(f"keepout:{it.kind}:{it.label}:zone[{ki}]")

    # courtyard overlap (KiCad-map P2): same-side courtyards must not collide
    with_cy = [c for c in board.components if c.footprint.courtyard]
    for i, a in enumerate(with_cy):
        aw, ah = a.footprint.courtyard
        if round(a.rot) % 180 == 90:
            aw, ah = ah, aw
        for b in with_cy[i + 1:]:
            if a.side != b.side:
                continue
            bw, bh = b.footprint.courtyard
            if round(b.rot) % 180 == 90:
                bw, bh = bh, bw
            if (abs(a.x - b.x) < (aw + bw) / 2
                    and abs(a.y - b.y) < (ah + bh) / 2):
                violations.append(f"courtyard-overlap:{a.ref}<->{b.ref}")

    return ValidationReport(
        ok=not violations,
        checks={"rulepack": pack.name, "rules": len(pack.rules),
                "copper_items": len(items), "holes": len(holes),
                "method": "aabb-approximation:outline-bbox"},
        violations=violations,
    )
