"""Sheet metal — the mech Gerber (SW-map P3).

A sheet-metal part is DECLARED as structure — a base wall plus flange
chains with bend angles and radii — so unfolding is analytic and exact,
not B-rep surgery. From one declaration both projections derive:

- the FLAT PATTERN with K-factor bend allowance, emitted as the DXF a
  laser/brake shop consumes (layers CUT / BEND_UP / BEND_DOWN / HOLES,
  plus a machine-readable bend table), and
- the 3D SOLID, emitted as an ordinary feature-tree Document so every
  existing pipeline (viewer, STEP, interference, drawings) just works.

Bend math (industry standard): bend allowance BA = θ·(R + K·t); outside
setback OSSB = (R + t)·tan(θ/2); each leg is measured to the mold-line
apex, so leg_flat = leg − OSSB and the BA strip sits between legs.
The solid uses sharp corners at bends (visualization/interference
grade); the flat pattern carries the exact allowance — the flat is the
manufacturing truth. v1 scope, honestly held: full-width flanges on the
four base edges, chained end flanges, round holes per wall.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError, ValidationReport

_EDGES = ("n", "e", "s", "w")


@dataclass
class SmHole:
    """Round hole. On the base: absolute base coords. On a flange: ``u``
    along the bend edge (from the wall's left end), ``v`` outward from the
    bend mold line along the face."""
    u: float
    v: float
    diameter: float


@dataclass
class Flange:
    """A full-width wall folded off its parent's edge. ``length`` is the
    outer mold-line length (ruler measurement); ``angle`` is the fold
    rotation from flat in degrees (90 = perpendicular); ``direction`` is
    up (+z) or down. ``children`` chain off this flange's free end."""
    edge: str                      # n|e|s|w on the base; "end" when chained
    length: float
    angle: float = 90.0
    radius: float | None = None    # inner bend radius; None = part default
    direction: str = "up"
    holes: list[SmHole] = field(default_factory=list)
    children: list["Flange"] = field(default_factory=list)
    hem: bool = False              # 180° fold-back (closed/open hem)


@dataclass
class SheetMetal:
    name: str
    width: float                   # base extent along x
    height: float                  # base extent along y
    thickness: float = 1.5
    k_factor: float = 0.44
    bend_radius: float = 1.5      # default inner radius
    flanges: list[Flange] = field(default_factory=list)
    base_holes: list[SmHole] = field(default_factory=list)

    SCHEMA = "gitcad/sheetmetal@1"

    # -- canonical text -------------------------------------------------------

    def dumps(self) -> str:
        return canonical_json({"schema": self.SCHEMA, "sheetmetal": asdict(self)},
                              indent=2) + "\n"

    @classmethod
    def loads(cls, text: str) -> "SheetMetal":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported sheetmetal schema {doc.get('schema')!r}")
        d = doc["sheetmetal"]

        def fl(f: dict) -> Flange:
            return Flange(edge=f["edge"], length=f["length"],
                          angle=f.get("angle", 90.0), radius=f.get("radius"),
                          direction=f.get("direction", "up"),
                          holes=[SmHole(**h) for h in f.get("holes", [])],
                          children=[fl(c) for c in f.get("children", [])],
                          hem=f.get("hem", False))

        return cls(name=d["name"], width=d["width"], height=d["height"],
                   thickness=d.get("thickness", 1.5),
                   k_factor=d.get("k_factor", 0.44),
                   bend_radius=d.get("bend_radius", 1.5),
                   flanges=[fl(f) for f in d.get("flanges", [])],
                   base_holes=[SmHole(**h) for h in d.get("base_holes", [])])

    # -- bend math ------------------------------------------------------------

    def _r(self, f: Flange) -> float:
        return self.bend_radius if f.radius is None else f.radius

    def _ba(self, f: Flange) -> float:
        return math.radians(f.angle) * (self._r(f) + self.k_factor * self.thickness)

    def _ossb(self, f: Flange) -> float:
        return (self._r(f) + self.thickness) * math.tan(math.radians(f.angle) / 2)

    # -- validation (real sheet-metal DFM) ------------------------------------

    def validate(self) -> ValidationReport:
        violations: list[str] = []
        if self.thickness <= 0:
            violations.append("thickness-nonpositive")
        if not (0 < self.k_factor < 1):
            violations.append(f"k-factor-out-of-range:{self.k_factor}")
        seen_edges: set[str] = set()

        def walk(f: Flange, path: str, chained: bool) -> None:
            label = f"{path}/{f.edge}"
            if chained:
                if f.edge != "end":
                    violations.append(f"chained-flange-edge-not-end:{label}")
            elif f.edge not in _EDGES:
                violations.append(f"flange-bad-edge:{label}")
            elif f.edge in seen_edges:
                violations.append(f"flange-duplicate-edge:{f.edge}")
            else:
                seen_edges.add(f.edge)
            if f.hem:
                # a hem is a 180° fold-back; OSSB diverges at 180° so the
                # general leg check doesn't apply — just need a real return.
                if f.length <= 0:
                    violations.append(f"hem-return-nonpositive:{label}")
                if self._r(f) < self.thickness:
                    violations.append(f"bend-radius-below-thickness:{label}")
                if f.direction not in ("up", "down"):
                    violations.append(f"flange-bad-direction:{label}")
                for c in f.children:
                    walk(c, label, chained=True)
                return
            if not (0 < f.angle < 180):
                violations.append(f"bend-angle-out-of-range:{label}:{f.angle}")
                return
            if self._r(f) < self.thickness:
                violations.append(f"bend-radius-below-thickness:{label}")
            if f.length <= self._ossb(f):
                violations.append(f"flange-shorter-than-setback:{label}")
            if f.direction not in ("up", "down"):
                violations.append(f"flange-bad-direction:{label}")
            min_edge = self._ossb(f) + 2 * self.thickness
            for h in f.holes:
                if h.v < min_edge:
                    violations.append(f"hole-too-close-to-bend:{label}:v={h.v:g}")
            for c in f.children:
                walk(c, label, chained=True)

        for f in self.flanges:
            walk(f, "base", chained=False)
        for h in self.base_holes:
            for f in self.flanges:
                d = {"n": self.height - h.v, "s": h.v,
                     "e": self.width - h.u, "w": h.u}[f.edge] if f.edge in _EDGES else 1e9
                if d < self._ossb(f) + 2 * self.thickness:
                    violations.append(f"hole-too-close-to-bend:base({f.edge}):u={h.u:g},v={h.v:g}")
        return ValidationReport(ok=not violations,
                                checks={"flanges": _count(self.flanges),
                                        "holes": len(self.base_holes)
                                        + _count_holes(self.flanges)},
                                violations=violations)

    # -- flat pattern ----------------------------------------------------------

    def flat_pattern(self) -> dict:
        """The unfold: outline polygon, per-bend lines (position, direction,
        angle, radius), and hole centers — all in flat coordinates with the
        base at (0,0)..(w,h). Exact K-factor math; fail-loud validation."""
        report = self.validate()
        if not report.ok:
            raise GitcadError(f"sheetmetal failed validation: {report.violations}")

        holes: list[tuple[float, float, float]] = [
            (h.u, h.v, h.diameter) for h in self.base_holes]
        bends: list[dict] = []
        # extents beyond each base edge (flat growth per direction)
        ext = {e: 0.0 for e in _EDGES}

        def unfold(f: Flange, edge: str, apex: float) -> float:
            """Lay a flange chain flat. ``apex`` is the flat position (beyond
            the base boundary) of this bend's mold-line apex; the BA strip
            spans [apex-OSSB, apex-OSSB+BA], so every leg between two bends
            loses OSSB at BOTH ends (classic L1-OSSB+BA+L2-OSSB layout).
            Returns the chain's total flat extent."""
            if f.hem:
                # 180° fold-back: BA = π(R + K·t); no OSSB setback. The bend
                # strip lays [apex, apex+BA], the return leg extends past it.
                ba = math.pi * (self._r(f) + self.k_factor * self.thickness)
                start = apex
                strip_end = start + ba
                bends.append({"edge": edge, "at": start + ba / 2, "angle": 180.0,
                              "radius": self._r(f), "direction": f.direction,
                              "width_span": ba, "hem": True})
                for h in f.holes:
                    holes.append(_edge_xy(edge, self.width, self.height,
                                          h.u, strip_end + h.v) + (h.diameter,))
                next_apex = strip_end + f.length
                extent = next_apex
                for c in f.children:
                    extent = max(extent, unfold(c, edge, next_apex))
                return extent
            ossb, ba = self._ossb(f), self._ba(f)
            start = apex - ossb
            strip_end = start + ba
            bends.append({"edge": edge, "at": start + ba / 2, "angle": f.angle,
                          "radius": self._r(f), "direction": f.direction,
                          "width_span": ba})
            for h in f.holes:
                holes.append(_edge_xy(edge, self.width, self.height,
                                      h.u, strip_end + (h.v - ossb))
                             + (h.diameter,))
            next_apex = strip_end + f.length - ossb
            extent = next_apex
            for c in f.children:
                extent = max(extent, unfold(c, edge, next_apex))
            return extent

        for f in self.flanges:
            ext[f.edge] = unfold(f, f.edge, 0.0)
        minx, miny = -ext["w"], -ext["s"]
        maxx, maxy = self.width + ext["e"], self.height + ext["n"]
        outline = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
        # bend "at" values are offsets past the base edge; convert to xy lines
        bend_lines: list[dict] = []
        for b in bends:
            e = b["edge"]
            if e in ("n", "s"):
                y = self.height + b["at"] if e == "n" else -b["at"]
                p1, p2 = (minx, y), (maxx, y)
            else:
                x = self.width + b["at"] if e == "e" else -b["at"]
                p1, p2 = (x, miny), (x, maxy)
            bend_lines.append({**b, "p1": p1, "p2": p2})
        return {"outline": outline, "bends": bend_lines,
                "holes": holes, "bbox": (minx, miny, maxx, maxy),
                "checks": report.checks}

    def flat_dxf(self) -> str:
        """The shop file: DXF R12, layers CUT / BEND_UP / BEND_DOWN / HOLES."""
        fp = self.flat_pattern()
        lines = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009",
                 "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
        pts = fp["outline"] + [fp["outline"][0]]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            lines += ["0", "LINE", "8", "CUT",
                      "10", f"{x1:.6f}", "20", f"{y1:.6f}",
                      "11", f"{x2:.6f}", "21", f"{y2:.6f}"]
        for b in fp["bends"]:
            layer = "BEND_UP" if b["direction"] == "up" else "BEND_DOWN"
            (x1, y1), (x2, y2) = b["p1"], b["p2"]
            lines += ["0", "LINE", "8", layer,
                      "10", f"{x1:.6f}", "20", f"{y1:.6f}",
                      "11", f"{x2:.6f}", "21", f"{y2:.6f}"]
        for hx, hy, d in fp["holes"]:
            lines += ["0", "CIRCLE", "8", "HOLES",
                      "10", f"{hx:.6f}", "20", f"{hy:.6f}", "40", f"{d / 2:.6f}"]
        lines += ["0", "ENDSEC", "0", "EOF"]
        return "\n".join(lines) + "\n"

    def bend_table(self) -> list[dict]:
        """Machine-readable bend schedule, in unfold order per edge."""
        fp = self.flat_pattern()
        return [{"seq": i + 1, "edge": b["edge"], "angle": b["angle"],
                 "radius": b["radius"], "direction": b["direction"]}
                for i, b in enumerate(fp["bends"])]

    # -- hem / jog convenience constructors ------------------------------------

    def hem(self, edge: str, length: float, *, radius: float | None = None,
            direction: str = "up") -> "SheetMetal":
        """A 180° fold-back on ``edge`` (closed hem). ``length`` is the flat
        return; ``radius`` (default part radius) sets closed vs open —
        r≈thickness is a closed hem, larger leaves a gap. Flat-pattern
        allowance BA = π(R + K·t)."""
        self.flanges.append(Flange(edge=edge, length=length, angle=180.0,
                                   radius=radius, direction=direction,
                                   hem=True))
        return self

    def jog(self, edge: str, offset: float, run: float, *,
            angle: float = 90.0, radius: float | None = None,
            direction: str = "up") -> "SheetMetal":
        """A jog (Z-offset) on ``edge``: bend up by ``angle``, step the wall
        out by ``offset`` (measured ⟂ to the base), bend back, then continue
        ``run``. Built as the two-bend flange chain the unfolder already
        handles; the riser length is offset/sin(angle)."""
        theta = math.radians(angle)
        riser = offset / math.sin(theta) if math.sin(theta) else offset
        opp = "down" if direction == "up" else "up"
        self.flanges.append(Flange(
            edge=edge, length=riser, angle=angle, radius=radius,
            direction=direction,
            children=[Flange(edge="end", length=run, angle=angle,
                             radius=radius, direction=opp)]))
        return self

    # -- 3D solid (via the ordinary Document pipeline) -------------------------

    def to_document(self):
        """Emit the folded solid as a feature-tree Document (sharp-corner
        bends — the flat pattern carries the exact allowance). Every
        existing projection (viewer, STEP, drawings, interference) applies."""
        from gitcad.document import Document, Feature

        report = self.validate()
        if not report.ok:
            raise GitcadError(f"sheetmetal failed validation: {report.violations}")
        doc = Document()
        t = self.thickness
        base = doc.add(Feature(op="box",
                               params={"dx": self.width, "dy": self.height, "dz": t}))
        acc = base
        for f in self.flanges:
            slab = _flange_features(doc, self, f, f.edge, 0.0)
            acc = doc.add(Feature(op="boolean", params={"kind": "union"},
                                  inputs=[acc, slab]))
        for h in self.base_holes:
            acc = doc.add(Feature(op="hole",
                                  params={"x": h.u, "y": h.v, "top_z": t,
                                          "depth": t, "diameter": h.diameter},
                                  inputs=[acc]))
        return doc


def _count(fs: list[Flange]) -> int:
    return sum(1 + _count(f.children) for f in fs)


def _count_holes(fs: list[Flange]) -> int:
    return sum(len(f.holes) + _count_holes(f.children) for f in fs)


def _edge_xy(edge: str, w: float, h: float, u: float, out: float) -> tuple[float, float]:
    """Map (u along edge, `out` beyond the base boundary) to flat xy."""
    if edge == "n":
        return (u, h + out)
    if edge == "s":
        return (u, -out)
    if edge == "e":
        return (w + out, u)
    return (-out, u)


def _flange_features(doc, sm: SheetMetal, f: Flange, edge: str, offset: float) -> str:
    """One flange (and its chain) as box+move features. Physically faithful
    composition: the chain is laid out FLAT beyond the base edge, children
    fold about their own bend lines first (innermost first), then the whole
    subtree folds about this flange's line — exactly how a brake folds the
    real part. Pivot at mid-thickness; sharp corners (documented)."""
    from gitcad.document import Feature

    t = sm.thickness
    # flat slab occupying [offset, offset + length] beyond the base edge
    if edge in ("n", "s"):
        slab = doc.add(Feature(op="box",
                               params={"dx": sm.width, "dy": f.length, "dz": t}))
        flat_pos = ((0.0, sm.height + offset, 0.0) if edge == "n"
                    else (0.0, -offset - f.length, 0.0))
        axis = (1, 0, 0)
        up_sign = 1.0 if edge == "n" else -1.0
        pivot = (0.0, sm.height + offset if edge == "n" else -offset, t / 2)
    else:
        slab = doc.add(Feature(op="box",
                               params={"dx": f.length, "dy": sm.height, "dz": t}))
        flat_pos = ((sm.width + offset, 0.0, 0.0) if edge == "e"
                    else (-offset - f.length, 0.0, 0.0))
        axis = (0, 1, 0)
        up_sign = -1.0 if edge == "e" else 1.0
        pivot = (sm.width + offset if edge == "e" else -offset, 0.0, t / 2)
    subtree = doc.add(Feature(op="move", params={"translate": list(flat_pos)},
                              inputs=[slab]))
    for c in f.children:                      # children fold first, flat-relative
        child = _flange_features(doc, sm, c, edge, offset + f.length)
        subtree = doc.add(Feature(op="boolean", params={"kind": "union"},
                                  inputs=[subtree, child]))
    # fold the whole subtree about this flange's bend line
    rot = up_sign * f.angle * (1.0 if f.direction == "up" else -1.0)
    to_origin = doc.add(Feature(
        op="move", params={"translate": [-pivot[0], -pivot[1], -pivot[2]]},
        inputs=[subtree]))
    turned = doc.add(Feature(
        op="move", params={"rotate_axis": list(axis), "rotate_deg": rot},
        inputs=[to_origin]))
    return doc.add(Feature(
        op="move", params={"translate": list(pivot)}, inputs=[turned]))
