"""`ref` backend — the forgekernel exact reference kernel behind the seam.

ADR-0018: forgekernel (github.com/gitcad-xyz/forge) is the from-scratch
kernel's executable specification — exact rational arithmetic, no
epsilons in any decision. This shim adapts it to the gitcad Kernel
protocol for the operator classes each stage has earned; everything
else refuses honestly, naming the stage that brings it. The scorecard
(gitcad.bench) measures the growing coverage against OCCT.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from gitcad.errors import FailureSignature, KernelError, ValidationReport

_K2 = "arrives at K2 (quadrics)"
_K3 = "arrives at K3 (NURBS/SSI)"
_K5 = "arrives at K5 (blends)"


def _nope(op: str, stage: str):
    raise KernelError(
        f"ref kernel does not implement {op} yet — {stage}",
        FailureSignature(op=op, diagnostic="NotYetImplemented", kernel="ref"))


class RefKernel:
    """K1: exact planar solids (box, line-profile extrude, quarter-turn
    rigid transforms, mirror, scale, booleans, exact mass properties)."""

    name = "ref-k2-exact"

    def __init__(self) -> None:
        from forgekernel import kernel as fk

        self._fk = fk

    # -- primitives -----------------------------------------------------------

    def box(self, dx: float, dy: float, dz: float):
        return self._fk.box(dx, dy, dz)

    def cylinder(self, radius: float, height: float):
        from forgekernel.quadric import Cyl

        return Cyl.make(radius, height)

    def sphere(self, radius: float):
        from forgekernel.quadric import Sphere

        return Sphere.make(radius)

    def cone(self, r1: float, r2: float, height: float):
        from forgekernel.quadric import Cone

        return Cone.make(r1, r2, height)

    def extrude(self, profile: dict, height: float):
        segs = profile.get("segments", [])
        if any(s.get("kind") != "line" for s in segs):
            _nope("extrude(arc profile)", _K2)
        loop = [tuple(profile["start"])] + [tuple(s["to"]) for s in segs]
        if loop[0] == loop[-1]:
            loop = loop[:-1]
        return self._fk.prism(loop, height)

    # -- transforms -----------------------------------------------------------

    def transform(self, shape, *, translate=(0, 0, 0),
                  rotate_axis=(0, 0, 1), rotate_deg: float = 0.0):
        from forgekernel.quadric import AxisStack, Cone, Cyl, Sphere
        from forgekernel.curve import TubeSolid

        if isinstance(shape, TubeSolid):
            if rotate_deg:
                _nope("transform(rotate a certified tube)", "K3.1")
            return shape.translated(*translate)
        if isinstance(shape, (Cyl, Cone, Sphere)):
            if rotate_deg and (tuple(rotate_axis) != (0, 0, 1)):
                _nope("transform(tilt a quadric)", "K2.2 (general axes)")
            return shape.translated(*translate)
        if isinstance(shape, AxisStack):
            _nope("transform(AxisStack)", "K2.2")
        out = shape
        if rotate_deg:
            axis = {(1, 0, 0): "x", (0, 1, 0): "y", (0, 0, 1): "z"}.get(
                tuple(rotate_axis))
            if axis is None or rotate_deg % 90 != 0:
                _nope(f"transform(rotate {rotate_deg} about {rotate_axis})", _K2)
            out = self._fk.rotate_quarter(out, axis, int(rotate_deg // 90))
        if any(translate):
            out = self._fk.translate(out, *translate)
        return out

    def scale(self, shape, fx: float, fy=None, fz=None):
        return self._fk.scale(shape, fx, fy, fz)

    def mirror(self, shape, plane: str):
        axis = {"yz": "x", "xz": "y", "xy": "z"}.get(plane)
        if axis is None:
            raise KernelError(
                f"mirror plane must be xy|xz|yz, got {plane!r}",
                FailureSignature(op="mirror", diagnostic="BadInput",
                                 kernel="ref"))
        return self._fk.mirror(shape, axis)

    def boolean(self, op: str, a, b):
        from forgekernel.brep import Solid
        from forgekernel.quadric import (AxisStack, Cone, Cyl, DrilledSolid,
                                         Sphere)

        from forgekernel.quadric import DisjointUnion, SphereOverlap

        # two overlapping spheres: exact ℚ[π] cap/lens booleans (K2.2)
        if isinstance(a, Sphere) and isinstance(b, Sphere) and op in ("union", "cut", "intersect"):
            try:
                return SphereOverlap(a, b, op)
            except ValueError:
                pass  # not overlapping / nested / irrational → fall through
        axis_prims = (Cyl, Cone, Sphere)
        curved = (Cyl, Cone, Sphere, AxisStack, DisjointUnion)
        if op == "union" and (isinstance(a, curved) or isinstance(b, curved)):
            # planar Solid+Solid never reaches here — it stays on the exact
            # BSP engine below. Curved operands: coaxial quadrics fuse into
            # an AxisStack; anything meeting only tangentially unions exactly
            # by measure-zero (DisjointUnion). Genuine overlap refuses (K2.3).
            if isinstance(b, axis_prims) and isinstance(a, (axis_prims, AxisStack)):
                try:
                    stack = a if isinstance(a, AxisStack) else AxisStack(a.cx, a.cy, [a])
                    return stack.fuse(b)
                except ValueError:
                    pass                       # non-coaxial: try DisjointUnion
            try:
                members = a.members if isinstance(a, DisjointUnion) else [a]
                other = b.members if isinstance(b, DisjointUnion) else [b]
                return DisjointUnion(members + other)
            except ValueError as exc:
                raise KernelError(str(exc), FailureSignature(
                    op="boolean.union", diagnostic="NotYetImplemented",
                    kernel="ref"))
        if isinstance(b, Cyl) and op == "cut":
            base = (DrilledSolid(a, []) if isinstance(a, Solid)
                    else a if isinstance(a, DrilledSolid) else None)
            if base is not None:
                try:
                    return base.cut(b)
                except ValueError as exc:
                    raise KernelError(str(exc), FailureSignature(
                        op="boolean.cut", diagnostic="NotYetImplemented",
                        kernel="ref"))
        if isinstance(a, (AxisStack, *axis_prims, DrilledSolid)) or                 isinstance(b, (AxisStack, *axis_prims, DrilledSolid)):
            _nope(f"boolean.{op} on quadric operands", "K2.2")
        try:
            return self._fk.boolean(op, a, b)
        except ArithmeticError as exc:
            raise KernelError(
                f"boolean {op} failed closure: {exc}",
                FailureSignature(op=f"boolean.{op}",
                                 diagnostic="ClosureViolation", kernel="ref"))

    def compound(self, shapes: list):
        from forgekernel.brep import Solid

        return Solid([p for s in shapes for p in s.polys])

    # -- metrics --------------------------------------------------------------

    def mass_props(self, shape) -> dict[str, float]:
        from forgekernel.quadric import Cyl, DrilledSolid
        from forgekernel.curve import TubeSolid

        from forgekernel.quadric import (AxisStack, Cone, DisjointUnion,
                                         MiteredSweep, RevolveSolid, RoundedBox, Sphere, SphereOverlap)

        if isinstance(shape, TubeSolid):
            # certified provenance (ADR-0019): volume is an interval; report
            # the midpoint plus the proven half-width bracketing the truth.
            v = shape.volume()
            cx, cy, cz = shape.centroid_f()
            return {"volume": v.to_float(), "cx": cx, "cy": cy, "cz": cz,
                    "volume_halfwidth": float(v.width) / 2}
        if isinstance(shape, (Cone, Sphere)):
            shape = AxisStack(shape.cx, shape.cy, [shape])
        from forgekernel.quadric import FilletedBox
        if isinstance(shape, (Cyl, DrilledSolid, AxisStack, RevolveSolid, DisjointUnion, RoundedBox, MiteredSweep, SphereOverlap, FilletedBox)):
            cx, cy, cz = shape.centroid_f()
            return {"volume": float(shape.volume()),
                    "cx": cx, "cy": cy, "cz": cz}
        c = shape.centroid()
        return {"volume": float(shape.volume()),
                "cx": float(c[0]), "cy": float(c[1]), "cz": float(c[2])}

    def measure(self, shape) -> dict[str, float]:
        (x0, y0, z0), (x1, y1, z1) = shape.bbox()
        return {"volume": float(shape.volume()),
                "dx": float(x1 - x0), "dy": float(y1 - y0),
                "dz": float(z1 - z0)}

    def bbox(self, shape):
        from forgekernel.quadric import AxisStack, Cone, Sphere
        from forgekernel.curve import TubeSolid

        from forgekernel.quadric import RoundedBox
        if isinstance(shape, TubeSolid):
            return shape.bbox_f()
        if isinstance(shape, (Cone, Sphere)):
            shape = AxisStack(shape.cx, shape.cy, [shape])
        lo, hi = shape.bbox()
        return (tuple(float(v) for v in lo), tuple(float(v) for v in hi))

    def _bbox_unused(self, shape):
        lo, hi = shape.bbox()
        return (tuple(float(v) for v in lo), tuple(float(v) for v in hi))

    def _is_composite(self, shape) -> bool:
        from forgekernel.quadric import Cyl, DrilledSolid

        return isinstance(shape, (Cyl, DrilledSolid))

    def entities(self, shape, kind: str) -> list[dict[str, Any]]:
        from forgekernel.quadric import Cyl, DrilledSolid

        from forgekernel.quadric import (AxisStack, Cone, DisjointUnion,
                                         RevolveSolid, Sphere)

        from forgekernel.brep import Solid as _Solid
        if kind == "edge" and isinstance(shape, _Solid):
            # K5.0: deterministic straight-edge enumeration for planar
            # solids (fillet/chamfer selection targets)
            return [{"curve": "line",
                     "dir": [float(v) for v in e["dir"]],
                     "point": [float(v) for v in e["point"]]}
                    for e in self._sorted_edges(shape)]
        if kind != "face":
            raise NotImplementedError("ref enumerates faces and edges only")
        from forgekernel.quadric import MiteredSweep, RoundedBox, SphereOverlap
        from forgekernel.curve import TubeSolid
        if isinstance(shape, TubeSolid):
            # swept lateral surface + two round end caps
            return [{"surface": "swept-tube"}, {"surface": "plane"},
                    {"surface": "plane"}]
        if isinstance(shape, SphereOverlap):
            return [{"surface": "sphere-lens"}]
        if isinstance(shape, RoundedBox):
            return [{"surface": "rounded-box"}]
        if isinstance(shape, MiteredSweep):
            return [{"surface": "swept"}]
        if isinstance(shape, DisjointUnion):
            out = []
            for m in shape.members:
                out += self.entities(m, "face")
            return out
        if isinstance(shape, (Cone, Sphere, AxisStack, RevolveSolid)):
            prims = getattr(shape, "prims", [shape])
            return [{"surface": type(p).__name__.lower()} for p in prims]
        if isinstance(shape, Cyl):
            return [{"surface": "cylinder", "radius": float(shape.r),
                     "axis_dir": [0.0, 0.0, 1.0],
                     "axis_origin": [float(shape.cx), float(shape.cy),
                                     float(shape.z0)]}]
        if isinstance(shape, DrilledSolid):
            base = self.entities(shape.base, "face")
            return base + shape.cylinder_faces()
        out = []
        for (plane_key, source), frags in sorted(
                shape.logical_faces().items(),
                key=lambda kv: (kv[0][1], kv[0][0])):
            out.append({"surface": "plane", "lineage": source,
                        "plane": [float(v) for v in plane_key[:3]],
                        "fragments": len(frags)})
        return out

    def validate(self, shape) -> ValidationReport:
        from forgekernel.quadric import Cyl, DrilledSolid

        from forgekernel.quadric import (AxisStack, Cone, DisjointUnion,
                                         MiteredSweep, RevolveSolid, RoundedBox, Sphere, SphereOverlap)
        from forgekernel.curve import TubeSolid

        if isinstance(shape, TubeSolid):
            # watertight by construction (closed section, non-self-overlapping
            # sweep — both preconditions checked at build); volume certified >0
            return ValidationReport(
                ok=True,
                checks={"method": "certified-tube",
                        "provenance": shape.provenance},
                violations=[])
        from forgekernel.quadric import FilletedBox as _FB
        if isinstance(shape, (Cyl, Cone, Sphere, AxisStack, RevolveSolid, DisjointUnion, RoundedBox, MiteredSweep, SphereOverlap, _FB)):
            return ValidationReport(ok=True, checks={"method": "analytic"},
                                    violations=[])
        if isinstance(shape, DrilledSolid):
            bad = shape.watertight_violations()
            return ValidationReport(
                ok=not bad and float(shape.volume()) > 0,
                checks={"method": "exact-composite",
                        "bores": len(shape.bores)},
                violations=list(bad))
        bad = shape.watertight_violations()
        if shape.volume() <= 0:
            bad = list(bad) + ["nonpositive-volume"]
        return ValidationReport(ok=not bad,
                                checks={"method": "exact-line-coverage",
                                        "polygons": len(shape.polys)},
                                violations=list(bad))

    def tessellate(self, shape, *, deflection: float = 0.2) -> dict[str, list]:
        # planar solids mesh exactly; analytic composites mesh to a
        # bounded-error view (deflection = max chord error)
        if hasattr(shape, "tessellate"):
            try:
                return shape.tessellate(deflection)
            except TypeError:
                return shape.tessellate()
        raise NotImplementedError(
            f"tessellate not implemented for {type(shape).__name__} (K2.x)")

    # -- honest refusals (each names its stage) -------------------------------

    def revolve(self, profile, angle_deg=360.0):
        from forgekernel.quadric import RevolveSolid

        if angle_deg != 360.0:
            _nope("revolve(partial angle)", "K2.2")
        segs = profile.get("segments", [])
        if any(s.get("kind") != "line" for s in segs):
            _nope("revolve(arc profile)", "K2.2")
        loop = [tuple(profile["start"])] + [tuple(s["to"]) for s in segs]
        if loop[0] == loop[-1]:
            loop = loop[:-1]
        return RevolveSolid(loop)

    def loft(self, sections, *, ruled=False):
        # K3.6: RULED multi-section lofts graduate — a ruled loft through
        # N line-profile sections is exactly the stack of pairwise
        # prismatoids (each adjacent pair rules linearly), fused with the
        # exact boolean engine. SMOOTH (spline-fit) multi-section lofts
        # remain K3.7 — OCCT fits a B-spline through the sections there,
        # which is different geometry, not a stack.
        from forgekernel.brep import prismatoid

        if len(sections) > 2 and not ruled:
            _nope("loft(>2 sections, smooth spline fit)", "K3.7")
        if len(sections) < 2:
            _nope("loft(<2 sections)", "K3")
        for prof, _ in sections:
            if any(s.get("kind") != "line" for s in prof.get("segments", [])):
                _nope("loft(arc profile)", "K3")

        def loop(prof):
            pts = [tuple(prof["start"])] + [tuple(s["to"]) for s in prof["segments"]]
            return pts[:-1] if pts[0] == pts[-1] else pts

        loops = [(loop(p), z) for p, z in sections]
        counts = {len(lp) for lp, _ in loops}
        if len(counts) != 1:
            _nope("loft(unequal section vertex counts)", "K3.7")
        try:
            out = None
            for (la, za), (lb, zb) in zip(loops, loops[1:]):
                piece = prismatoid(la, za, lb, zb)
                out = piece if out is None else self._fk.boolean(
                    "union", out, piece)
            return out
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="loft", diagnostic="NotYetImplemented", kernel="ref"))

    def sweep(self, profile, path):
        # mitered sweep of a convex profile — exact volume in Q[sqrt d].
        # (the model OCCT fails on: 45-degree cornered path.)
        from forgekernel.kernel import sweep as fk_sweep

        segs = profile.get("segments", [])
        if any(s.get("kind") != "line" for s in segs):
            _nope("sweep(arc profile)", "K3.1")
        pts = [tuple(profile["start"])] + [tuple(s["to"]) for s in segs]
        loop = pts[:-1] if pts[0] == pts[-1] else pts
        # shoelace area (exact)
        from fractions import Fraction as _Fr
        area = _Fr(0)
        n = len(loop)
        for i in range(n):
            x1, y1 = loop[i]
            x2, y2 = loop[(i + 1) % n]
            area += _Fr(x1) * _Fr(y2) - _Fr(x2) * _Fr(y1)
        area = abs(area) / 2
        try:
            return fk_sweep(area, path)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="sweep", diagnostic="NotYetImplemented", kernel="ref"))

    def _prism_shell(self, shape, t: Fraction):
        """K4.1: closed hollow of a convex right prism. The inner void's
        profile is the exact inward inset: each edge line moved ``t``
        along its inward unit normal (rational only for Pythagorean
        edge directions), adjacent inset lines intersected exactly."""
        from math import isqrt

        lo, hi = shape.bbox()
        z0, z1 = lo[2], hi[2]
        if 2 * t >= z1 - z0 or t <= 0:
            raise ValueError("shell too thick for the prism height")
        # the bottom cap is ear-clipped into triangles — reconstruct the
        # boundary loop: interior diagonals appear in two triangles with
        # opposite directions and cancel; boundary edges survive once.
        from collections import Counter

        directed: Counter = Counter()
        found_cap = False
        for p in shape.polys:
            if all(v[2] == z0 for v in p.verts):
                found_cap = True
                m = len(p.verts)
                for i in range(m):
                    a = (p.verts[i][0], p.verts[i][1])
                    b = (p.verts[(i + 1) % m][0], p.verts[(i + 1) % m][1])
                    directed[(a, b)] += 1
            elif not all(v[2] in (z0, z1) for v in p.verts):
                raise ValueError("shell(non-prism base) — K4.2")
        if not found_cap:
            raise ValueError("shell: no planar bottom cap found — K4.2")
        boundary = {a: b for (a, b), cnt in directed.items()
                    if cnt == 1 and directed.get((b, a), 0) == 0}
        if not boundary:
            raise ValueError("shell: cap boundary reconstruction failed")
        start = next(iter(boundary))
        bottom = [start]
        cur = boundary[start]
        while cur != start:
            bottom.append(cur)
            cur = boundary.get(cur)
            if cur is None or len(bottom) > len(boundary) + 1:
                raise ValueError("shell: cap boundary is not a single loop")
        # drop collinear midpoints so each remaining edge is a true side
        cleaned = []
        m = len(bottom)
        for i in range(m):
            (x0_, y0_), (x1_, y1_), (x2_, y2_) = (
                bottom[i - 1], bottom[i], bottom[(i + 1) % m])
            if (x1_ - x0_) * (y2_ - y1_) != (y1_ - y0_) * (x2_ - x1_):
                cleaned.append(bottom[i])
        bottom = cleaned
        if len(bottom) < 3:
            raise ValueError("shell: degenerate cap boundary")
        # enforce CCW (positive shoelace)
        area2 = sum(bottom[i][0] * bottom[(i + 1) % len(bottom)][1]
                    - bottom[(i + 1) % len(bottom)][0] * bottom[i][1]
                    for i in range(len(bottom)))
        if area2 < 0:
            bottom = list(reversed(bottom))
            area2 = -area2
        n = len(bottom)
        lines = []                          # (a, b, c): ax + by = c inset line
        for i in range(n):
            (x1, y1), (x2, y2) = bottom[i], bottom[(i + 1) % n]
            dx, dy = x2 - x1, y2 - y1
            # convexity: next turn must be left
            (x3, y3) = bottom[(i + 2) % n]
            cross = dx * (y3 - y2) - dy * (x3 - x2)
            if cross <= 0:
                raise ValueError("shell(non-convex prism profile) — K4.2")
            # |d| must be rational (Pythagorean edge)
            l2 = dx * dx + dy * dy
            num, den = l2.numerator, l2.denominator
            rn, rd = isqrt(num), isqrt(den)
            if rn * rn != num or rd * rd != den:
                raise ValueError(
                    "shell(irrational edge normal) — K4.2 (certified insets)")
            length = Fraction(rn, rd)
            # inward (left) unit normal = (-dy, dx)/|d|
            a, b = -dy, dx
            c = a * x1 + b * y1 + t * length   # shift by t along unit normal
            lines.append((a, b, c))
        inset = []
        for i in range(n):
            a1, b1, c1 = lines[i - 1]
            a2, b2, c2 = lines[i]
            det = a1 * b2 - a2 * b1
            if det == 0:
                raise ValueError("shell: degenerate inset corner")
            inset.append(((c1 * b2 - c2 * b1) / det,
                          (a1 * c2 - a2 * c1) / det))
        # validity: the inset must still be a CCW convex polygon
        in_area2 = sum(inset[i][0] * inset[(i + 1) % n][1]
                       - inset[(i + 1) % n][0] * inset[i][1] for i in range(n))
        if in_area2 <= 0:
            raise ValueError("shell too thick: inset profile collapses")
        void = self._fk.prism(inset, z1 - z0 - 2 * t)
        void = self._fk.translate(void, 0, 0, z0 + t)
        return self._fk.boolean("cut", shape, void)

    def _box_check(self, shape):
        lo, hi = shape.bbox()
        corners = {(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])}
        for pp in shape.polys:
            for vx, vy, vz in pp.verts:
                if (vx, vy) not in corners or vz not in (lo[2], hi[2]):
                    return None
        return lo, hi

    def _sorted_edges(self, shape):
        from forgekernel.brep import logical_edges

        return sorted(logical_edges(shape), key=lambda e: (
            tuple(e["dir"]), tuple(e["point"]), e["tmin"]))

    def fillet(self, shape, edges, radius):
        from forgekernel.brep import Solid
        from forgekernel.kernel import fillet_box
        from forgekernel.quadric import FilletedBox

        if not isinstance(shape, Solid):
            _nope("fillet(non-planar base)", "K5 (general blends)")
        box = self._box_check(shape)
        if box is None:
            _nope("fillet(non-box)", "K5.2 (general blends)")
        lo, hi = box
        if not edges:
            # all edges rounded: the rounded-box Steiner form (K2-era)
            try:
                return fillet_box(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2],
                                  radius, (lo[0], lo[1], lo[2]))
            except ValueError as exc:
                raise KernelError(str(exc), FailureSignature(
                    op="fillet", diagnostic="NotYetImplemented", kernel="ref"))
        # K5.0: constant-radius rolling-ball fillet on SELECTED straight
        # edges — exact in ℚ[π]. Adjacent selections (shared vertex →
        # spherical corner patch) refuse inside FilletedBox with K5.1.
        all_edges = self._sorted_edges(shape)
        axis_name = {0: "x", 1: "y", 2: "z"}
        specs = []
        for idx in edges:
            if idx >= len(all_edges):
                raise KernelError(
                    f"fillet: edge index {idx} out of range",
                    FailureSignature(op="fillet",
                                     diagnostic="EdgeIndexOutOfRange",
                                     kernel="ref"))
            e = all_edges[idx]
            d = e["dir"]
            nz = [c for c in range(3) if d[c] != 0]
            if len(nz) != 1:
                _nope("fillet(diagonal edge)", "K5.2")
            a = nz[0]
            o1, o2 = [c for c in range(3) if c != a]
            p = e["point"]
            side = []
            for o in (o1, o2):
                if p[o] == lo[o]:
                    side.append("min")
                elif p[o] == hi[o]:
                    side.append("max")
                else:
                    _nope("fillet(interior edge)", "K5.2")
            specs.append((axis_name[a], side[0], side[1]))
        try:
            return FilletedBox(lo, hi, specs, radius)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="fillet", diagnostic="NotYetImplemented", kernel="ref"))

    def chamfer(self, shape, edges, distance):
        if edges:
            _nope("chamfer(selected edges)", "K1.2 (edge enumeration ids)")
        from forgekernel.kernel import chamfer as fk_chamfer

        try:
            return fk_chamfer(shape, distance)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="chamfer", diagnostic="NotYetImplemented", kernel="ref"))

    def shell(self, shape, remove_faces, thickness):
        from forgekernel.brep import Solid
        from forgekernel.kernel import shell as fk_shell

        if not isinstance(shape, Solid):
            _nope("shell(non-planar base)", "K4.2 (offset surfaces)")
        if not remove_faces:
            try:
                return fk_shell(shape, thickness)
            except ValueError:
                pass                       # not a box → try the prism path
            # K4.1: closed shell of a right PRISM — the void is the prism
            # of the exact inward polygon inset (half-plane intersection),
            # from z0+t to z1−t, cut with the exact boolean engine.
            # Convex Pythagorean-edge profiles only (the inward unit
            # normal must be rational); everything else → K4.2.
            try:
                return self._prism_shell(shape, Fraction(thickness))
            except ValueError as exc:
                raise KernelError(str(exc), FailureSignature(
                    op="shell", diagnostic="NotYetImplemented", kernel="ref"))
        # K4: OPEN shell on a box — the void is the inward-inset box
        # EXTENDED through each removed face to the outer surface, then
        # one exact boolean cut. Face indices are indices into THIS
        # kernel's entities(shape, "face") enumeration (the Document
        # layer maps stable ids to them — never ordinal at doc level).
        t = Fraction(thickness)
        lo, hi = shape.bbox()
        dims = [hi[c] - lo[c] for c in range(3)]
        if t <= 0 or any(2 * t >= d for d in dims):
            raise KernelError(
                f"shell t={thickness} too thick for the base",
                FailureSignature(op="shell", diagnostic="BadInput",
                                 kernel="ref"))
        # walk the SAME sorted logical-face ordering entities() uses, but
        # decide each face's side from its fragments' actual coordinates —
        # the canonical plane key's sign convention makes opposite faces
        # share a normal, so the normal alone cannot tell min from max.
        ordered = sorted(shape.logical_faces().items(),
                         key=lambda kv: (kv[0][1], kv[0][0]))
        void_lo = [lo[c] + t for c in range(3)]
        void_hi = [hi[c] - t for c in range(3)]
        for idx in remove_faces:
            if idx >= len(ordered):
                raise KernelError(
                    f"shell: face index {idx} out of range",
                    FailureSignature(op="shell",
                                     diagnostic="FaceIndexOutOfRange",
                                     kernel="ref"))
            (plane_key, _), frags = ordered[idx]
            n = plane_key[:3]
            axis = max(range(3), key=lambda c: abs(n[c]))
            if any(n[c] != 0 for c in range(3) if c != axis):
                _nope("shell(open non-axis-aligned face)", "K4.1")
            coord = frags[0].verts[0][axis]     # all verts share it (planar)
            if coord == hi[axis]:
                void_hi[axis] = hi[axis]        # extend through max side
            elif coord == lo[axis]:
                void_lo[axis] = lo[axis]        # extend through min side
            else:
                _nope("shell(open interior face)", "K4.1")
        void = Solid.box(void_hi[0] - void_lo[0], void_hi[1] - void_lo[1],
                         void_hi[2] - void_lo[2], "shellvoid").translated(
            (void_lo[0], void_lo[1], void_lo[2]))
        return self._fk.boolean("cut", shape, void)

    def draft(self, shape, faces, angle_deg, pull=(0, 0, 1), neutral_z=0.0):
        from forgekernel.brep import Solid
        from forgekernel.kernel import draft as fk_draft

        if not isinstance(shape, Solid) or tuple(pull) != (0, 0, 1):
            _nope("draft(non-planar or tilted pull)", "K2.3")
        try:
            return fk_draft(shape, angle_deg, neutral_z)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="draft", diagnostic="NotYetImplemented", kernel="ref"))

    def helix(self, radius, pitch, turns, ccw=True):
        # K3.0: the first transcendental curve — carried as certified
        # geometry (ADR-0019), not an exact field element.
        from forgekernel.curve import Helix

        try:
            return Helix(radius, pitch, turns, ccw)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="helix", diagnostic="BadInput", kernel="ref"))

    def pipe(self, spine, profile_diameter):
        # K3.0: round section swept along a helix → coil spring. Volume is
        # exact (π ρ² L) evaluated as a certified interval.
        from forgekernel.curve import Helix, TubeSolid

        if not isinstance(spine, Helix):
            _nope("pipe(non-helix spine)", "K3.1 (general path pipe)")
        try:
            return TubeSolid(spine, Fraction(profile_diameter) / 2)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="pipe", diagnostic="NotYetImplemented", kernel="ref"))

    def hlr_project(self, shape, direction, up=None):
        _nope("hlr_project", _K2)

    def export_step(self, shape, path):
        # K7.0c: native AP214 export of a planar-faced solid — OCCT-free
        # CAD exchange. Curved solids arrive at K3.7 (freeform topology).
        from forgekernel.brep import Solid
        from forgekernel.stepio import write_step_planar_solid

        if not isinstance(shape, Solid):
            _nope("export_step(curved solid)", "K3.7")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(write_step_planar_solid(shape))

    def export_stl(self, shape, path, *, deflection=0.1):
        from forgekernel import io

        with open(path, "w", newline=chr(10)) as f:
            f.write(io.to_stl(shape))

    def export_brep(self, shape, path):
        from forgekernel import io

        with open(path, "w", newline=chr(10)) as f:
            f.write(io.dumps(shape))

    def import_step(self, path):
        # K3.6: planar-faced STEP solids import as EXACT Solids — STEP
        # reals are decimal text, decimal→Fraction is lossless, and face
        # loops orient by exact Newell-vs-plane-normal comparison.
        # Freeform faces / holes refuse with their stage (K3.7).
        from forgekernel.stepio import read_step_planar_solid

        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        try:
            return read_step_planar_solid(text)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="import_step", diagnostic="NotYetImplemented",
                kernel="ref"))

    def import_brep(self, path):
        from forgekernel import io

        with open(path, encoding="utf-8") as f:
            return io.loads(f.read())
