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


_SEAM_OPS = (
    "box", "cylinder", "sphere", "cone", "extrude", "revolve", "loft", "sweep",
    "transform", "scale", "mirror", "boolean", "compound", "mass_props",
    "measure", "bbox", "entities", "validate", "tessellate", "fillet",
    "chamfer", "shell", "draft", "helix", "pipe", "hlr_project",
    "section_polys", "export_step", "export_stl", "export_brep",
    "import_step", "import_brep",
)


def _guard_seam(cls):
    """Turn a representation mismatch into an HONEST REFUSAL at the seam.

    Every forge representation (Solid, Cyl, DrilledSolid, RevolveSolid,
    DisjointUnion, …) implements a different slice of the geometry protocol, and
    an op written against the planar ``Solid`` API raises a bare
    ``AttributeError`` when handed a quadric — a raw exception through the seam
    that no caller can handle and that the capability matrix cannot tell apart
    from a genuine gap. This wrapper converts those into a stage-named
    ``NotYetImplemented`` KernelError naming BOTH the op and the representation,
    so an unsupported combination is reported the same way a deliberate
    ``_nope`` is.

    It deliberately does NOT swallow anything else: KernelError, ValueError and
    ArithmeticError keep their existing meanings, so real precondition failures
    and closure violations still surface untouched.
    """
    import functools

    def wrap(name, fn):
        @functools.wraps(fn)
        def inner(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except AttributeError as exc:
                kinds = ", ".join(sorted({type(a).__name__ for a in args
                                          if hasattr(a, "volume")})) or "shape"
                raise KernelError(
                    f"ref kernel does not implement {name} on {kinds} yet "
                    f"— unsupported representation ({exc})",
                    FailureSignature(op=name, diagnostic="NotYetImplemented",
                                     kernel="ref"))
        return inner

    for name in _SEAM_OPS:
        fn = getattr(cls, name, None)
        if callable(fn):
            setattr(cls, name, wrap(name, fn))
    return cls


def _mp(volume: float, cx: float, cy: float, cz: float, **extra) -> dict[str, Any]:
    """A mass-properties dict with the centroid available both as split
    ``cx/cy/cz`` scalars and as a ``centroid`` tuple (forge does not compute
    an inertia tensor — that stays out of the seam contract)."""
    return {"volume": volume, "cx": cx, "cy": cy, "cz": cz,
            "centroid": (cx, cy, cz), **extra}


def _edge_point(e, t) -> list[float]:
    pt = [float(x) for x in e["point"]]
    d = [float(x) for x in e["dir"]]
    dd = sum(x * x for x in d) or 1.0
    s = (float(t) - sum(pt[i] * d[i] for i in range(3))) / dd
    return [pt[i] + s * d[i] for i in range(3)]


def _edge_midpoint(e) -> list[float]:
    """Midpoint of a logical straight edge (``tmin``/``tmax`` are the along-dir
    coordinates), for geometry-based edge selection."""
    return _edge_point(e, (float(e["tmin"]) + float(e["tmax"])) / 2)


def _edge_length(e) -> float:
    a, b = _edge_point(e, e["tmin"]), _edge_point(e, e["tmax"])
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def _poly_area_centroid(verts) -> tuple[list[float], float]:
    """Exact area and area-centroid of a planar polygon via fan triangulation
    from ``verts[0]``. (The vertex mean is the centroid only for triangles and
    parallelograms; forge's ``Polygon.area2()`` is ``4·area²``, so neither is a
    substitute here.)"""
    vs = [[float(c) for c in v] for v in verts]
    if len(vs) < 3:
        n = len(vs) or 1
        return [sum(v[i] for v in vs) / n for i in range(3)], 0.0
    v0 = vs[0]
    acc, area = [0.0, 0.0, 0.0], 0.0
    for i in range(1, len(vs) - 1):
        a = [vs[i][k] - v0[k] for k in range(3)]
        b = [vs[i + 1][k] - v0[k] for k in range(3)]
        cr = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
              a[0] * b[1] - a[1] * b[0])
        ta = 0.5 * (cr[0] ** 2 + cr[1] ** 2 + cr[2] ** 2) ** 0.5
        tc = [(v0[k] + vs[i][k] + vs[i + 1][k]) / 3 for k in range(3)]
        for k in range(3):
            acc[k] += tc[k] * ta
        area += ta
    if area == 0:
        n = len(vs)
        return [sum(v[i] for v in vs) / n for i in range(3)], 0.0
    return [acc[k] / area for k in range(3)], area


def _face_area(frags) -> float:
    return sum(_poly_area_centroid(p.verts)[1] for p in frags)


def _tri_prism_along(ea: int, tri2d, a_lo, a_hi):
    """A triangular prism: the 2D triangle ``tri2d`` (in the two axes other than
    ``ea``) extruded along axis ``ea`` from ``a_lo`` to ``a_hi``. Exact vertices;
    outward-oriented (a chamfer wedge to subtract)."""
    from forgekernel.brep import Polygon, Solid

    eb, ec = (i for i in range(3) if i != ea)

    def pt(a, b, c):
        p = [None, None, None]
        p[ea], p[eb], p[ec] = a, b, c
        return tuple(p)

    bot = [pt(a_lo, b, c) for (b, c) in tri2d]
    top = [pt(a_hi, b, c) for (b, c) in tri2d]
    polys = [Polygon(bot, "chamfer.cap"), Polygon(list(reversed(top)), "chamfer.cap")]
    n = len(tri2d)
    for i in range(n):
        j = (i + 1) % n
        polys.append(Polygon([bot[i], bot[j], top[j], top[i]], "chamfer.side"))
    s = Solid(polys)
    return Solid([p.flipped() for p in s.polys]) if s.volume() < 0 else s


def _face_centroid(frags) -> list[float]:
    """Area-weighted centroid of a logical face's fragments (each a true
    polygon centroid weighted by true area), for geometry-based face selection."""
    acc, tot = [0.0, 0.0, 0.0], 0.0
    for p in frags:
        c, a = _poly_area_centroid(p.verts)
        for k in range(3):
            acc[k] += c[k] * a
        tot += a
    return [acc[k] / tot for k in range(3)] if tot else [0.0, 0.0, 0.0]


@_guard_seam
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
        kinds = {s.get("kind") for s in segs}
        if "arc" in kinds:
            _nope("extrude(arc profile)", _K2)
        if "spline" in kinds:
            # K3.8: spline (polynomial-Bézier) profile → exact rational
            # volume via Green's-theorem area (SplinePrism).
            from forgekernel.profile2d import SplinePrism

            try:
                return SplinePrism(profile["start"], segs, height)
            except ValueError as exc:
                raise KernelError(str(exc), FailureSignature(
                    op="extrude", diagnostic="NotYetImplemented", kernel="ref"))
        loop = [tuple(profile["start"])] + [tuple(s["to"]) for s in segs]
        if loop[0] == loop[-1]:
            loop = loop[:-1]
        if len(loop) < 3:
            raise KernelError(
                "extrude: profile has fewer than 3 distinct points",
                FailureSignature(op="extrude", diagnostic="BadInput",
                                 kernel="ref"))
        try:
            return self._fk.prism(loop, height)
        except (ValueError, ArithmeticError, ZeroDivisionError) as exc:
            # a degenerate loop (collinear / zero-area) must surface as a
            # KernelError, not a raw Python exception through the seam
            raise KernelError(
                f"extrude: degenerate profile ({exc})",
                FailureSignature(op="extrude", diagnostic="BadInput",
                                 kernel="ref"))

    # -- transforms -----------------------------------------------------------

    def _translate_any(self, m, t):
        """Translate one solid whatever its representation: the planar Solid
        takes a vector, the quadric/composite types take (x, y, z)."""
        from forgekernel.brep import Solid

        if isinstance(m, Solid):
            return self._fk.translate(m, *t)
        return m.translated(*t)

    def transform(self, shape, *, translate=(0, 0, 0),
                  rotate_axis=(0, 0, 1), rotate_deg: float = 0.0):
        from forgekernel.brep import Solid
        from forgekernel.quadric import (AxisStack, Cone, Cyl, DisjointUnion,
                                         DrilledSolid, RevolveSolid, Sphere)
        from forgekernel.curve import TubeSolid

        if isinstance(shape, (TubeSolid, DrilledSolid, RevolveSolid)):
            # these carry their own (x, y, z) translate; the planar path would
            # hand them a single vector
            if rotate_deg:
                return self._transform_via_body(
                    "rotate a drilled/tube/revolved solid", shape,
                    rotate_axis, rotate_deg, translate)
            return shape.translated(*translate)
        if isinstance(shape, DisjointUnion):
            # rigid translation of every member — disjointness is preserved
            if rotate_deg:
                return self._transform_via_body(
                    "rotate a disjoint union", shape,
                    rotate_axis, rotate_deg, translate)
            return DisjointUnion._unchecked(
                [self._translate_any(m, translate) for m in shape.members])
        if isinstance(shape, (Cyl, Cone, Sphere)):
            if rotate_deg and (tuple(rotate_axis) != (0, 0, 1)):
                return self._transform_via_body(
                    "tilt a quadric", shape, rotate_axis, rotate_deg, translate)
            return shape.translated(*translate)
        if isinstance(shape, AxisStack):
            if rotate_deg or any(translate):
                return self._transform_via_body(
                    "transform an AxisStack", shape,
                    rotate_axis, rotate_deg, translate)
            return shape
        if not isinstance(shape, Solid):
            # any other representation with a converter (a rounded box, say)
            # transforms through the canonical form rather than refusing
            return self._transform_via_body(
                f"transform a {type(shape).__name__}", shape,
                rotate_axis, rotate_deg, translate)
        out = shape
        if rotate_deg:
            axis = {(1, 0, 0): "x", (0, 1, 0): "y", (0, 0, 1): "z"}.get(
                tuple(rotate_axis))
            if axis is not None and rotate_deg % 90 == 0:
                out = self._fk.rotate_quarter(out, axis, int(rotate_deg // 90))
            else:
                # K2.2: exact rotation about any axis by a ℚ[√d] angle (multiples
                # of 30°/45°) — circular patterns and diagonal sketch planes.
                try:
                    out = self._fk.rotate(out, tuple(rotate_axis), rotate_deg)
                except (ValueError, AttributeError):
                    _nope(f"transform(rotate {rotate_deg} about {rotate_axis})", _K2)
        if any(translate):
            out = self._fk.translate(out, *translate)
        return out

    def _transform_via_body(self, what: str, shape, rotate_axis, rotate_deg,
                            translate):
        """Rotate through the canonical B-rep (ADR-0021).

        Every representation that could not rotate itself used to refuse —
        a drilled plate, a boss, a tilted cylinder. The canonical form rotates
        EXACTLY for the ℚ[√d] angles (multiples of 30°/45°/90°), so the
        refusal was about the representation, not about the geometry. Angles
        outside the field still refuse, now from one place.
        """
        from forgekernel import body as B

        def make(b):
            out = b.transformed(B.Affine.rotation(tuple(rotate_axis), rotate_deg))
            return (out.transformed(B.Affine.translation(*translate))
                    if any(translate) else out)

        return self._via_body(f"transform({what})", shape, make)

    def _via_body(self, op: str, shape, make):
        """ADR-0021 fallback: run an operation on the canonical B-rep when the
        representation has no specialised path. Native paths keep priority —
        this only ever turns a refusal into a result, never the reverse."""
        from forgekernel import body as B

        try:
            return make(B.to_body(shape))
        except (ValueError, AttributeError, TypeError) as exc:
            _nope(f"{op} on {type(shape).__name__} ({exc})", "K3.7 (canonical B-rep)")

    def scale(self, shape, fx: float, fy=None, fz=None):
        from forgekernel import body as B
        from forgekernel.brep import Solid

        if isinstance(shape, Solid):
            return self._fk.scale(shape, fx, fy, fz)
        fy = fx if fy is None else fy
        fz = fx if fz is None else fz
        return self._via_body(
            "scale", shape, lambda b: b.transformed(B.Affine.scaling(fx, fy, fz)))

    def mirror(self, shape, plane: str):
        from forgekernel import body as B
        from forgekernel.brep import Solid

        axis = {"yz": "x", "xz": "y", "xy": "z"}.get(plane)
        if axis is None:
            raise KernelError(
                f"mirror plane must be xy|xz|yz, got {plane!r}",
                FailureSignature(op="mirror", diagnostic="BadInput",
                                 kernel="ref"))
        if isinstance(shape, Solid):
            return self._fk.mirror(shape, axis)
        return self._via_body(
            "mirror", shape, lambda b: b.transformed(B.Affine.mirror(axis)))

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
        from forgekernel.quadric import RevolveSolid, RoundedBox

        axis_prims = (Cyl, Cone, Sphere)
        # RevolveSolid, RoundedBox and DrilledSolid belong here too: they are
        # every bit as "curved", and leaving them out meant a union with a box
        # FAR AWAY -- provably disjoint by exact bbox separation -- never even
        # reached the DisjointUnion path and died in the planar BSP engine.
        curved = (Cyl, Cone, Sphere, AxisStack, DisjointUnion, RevolveSolid,
                  RoundedBox, DrilledSolid)
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
        if isinstance(b, Cyl) and op == "cut" and isinstance(a, DisjointUnion):
            # (A ∪ B) ∖ C distributes over disjoint members (K2.3): the boss
            # standing on a plate keeps its pilot bore exact.
            try:
                return a.cut(b)
            except ValueError as exc:
                raise KernelError(str(exc), FailureSignature(
                    op="boolean.cut", diagnostic="NotYetImplemented",
                    kernel="ref"))
        if isinstance(b, Cyl) and op == "cut":
            lathe = self._bore_lathe(a, b)
            if lathe is not None:
                return lathe
        if isinstance(b, Cyl) and op == "cut" and isinstance(a, Cyl):
            from forgekernel.quadric import bore_cyl

            try:
                return bore_cyl(a, b)
            except ValueError as exc:
                raise KernelError(str(exc), FailureSignature(
                    op="boolean.cut", diagnostic="NotYetImplemented",
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
        except ValueError as exc:
            # operands whose exact coordinates live in different quadratic
            # fields (e.g. a 45°-rotated ℚ[√2] body vs a 30°-rotated ℚ[√3] one)
            # need a bigger field — refuse honestly rather than leak (K3.1).
            _nope(f"boolean.{op} across mixed radicals ({exc})", "K3.1")

    def compound(self, shapes: list):
        from forgekernel.brep import Solid

        return Solid([p for s in shapes for p in s.polys])

    # -- metrics --------------------------------------------------------------

    def mass_props(self, shape) -> dict[str, float]:
        from forgekernel import body as B

        if isinstance(shape, B.Body):
            # exact volume, and a real centre of mass from the same per-face
            # cone decomposition. This used to substitute the BBOX CENTRE and
            # flag it with a key no caller read — for an L-bracket that is off
            # by a fifth of the part, reported as fact.
            cx, cy, cz = B.centroid(shape)
            return _mp(float(B.volume(shape)), cx, cy, cz)
        from forgekernel.quadric import Cyl, DrilledSolid
        from forgekernel.curve import TubeSolid

        from forgekernel.quadric import (AxisStack, Cone, DisjointUnion,
                                         MiteredSweep, RevolveSolid, RoundedBox, Sphere, SphereOverlap)

        from forgekernel.loft import LoftSolid
        from forgekernel.profile2d import SplinePrism
        if isinstance(shape, (LoftSolid, SplinePrism)):
            cx, cy, cz = shape.centroid_f()
            return _mp(float(shape.volume()), cx, cy, cz)
        if isinstance(shape, TubeSolid):
            # certified provenance (ADR-0019): volume is an interval; report
            # the midpoint plus the proven half-width bracketing the truth.
            v = shape.volume()
            cx, cy, cz = shape.centroid_f()
            return _mp(v.to_float(), cx, cy, cz,
                       volume_halfwidth=float(v.width) / 2)
        if isinstance(shape, (Cone, Sphere)):
            shape = AxisStack(shape.cx, shape.cy, [shape])
        from forgekernel.quadric import FilletedBox
        if isinstance(shape, (Cyl, DrilledSolid, AxisStack, RevolveSolid, DisjointUnion, RoundedBox, MiteredSweep, SphereOverlap, FilletedBox)):
            cx, cy, cz = shape.centroid_f()
            return _mp(float(shape.volume()), cx, cy, cz)
        c = shape.centroid()
        return _mp(float(shape.volume()), float(c[0]), float(c[1]), float(c[2]))

    def measure(self, shape) -> dict[str, float]:
        from forgekernel.quadric import AxisStack, Cone, Sphere
        from forgekernel import body as B

        if isinstance(shape, B.Body):                 # ADR-0021 canonical form
            (x0, y0, z0), (x1, y1, z1) = B.bbox(shape)
            return {"volume": float(B.volume(shape)),
                    "dx": x1 - x0, "dy": y1 - y0, "dz": z1 - z0}

        (x0, y0, z0), (x1, y1, z1) = self.bbox(shape)
        vshape = (AxisStack(shape.cx, shape.cy, [shape])
                  if isinstance(shape, (Cone, Sphere)) else shape)
        vol = vshape.volume()
        # certified-provenance solids (TubeSolid) report volume as a CInterval;
        # take its midpoint (no __float__, only to_float()).
        vol = vol.to_float() if hasattr(vol, "to_float") else float(vol)
        return {"volume": vol,
                "dx": float(x1 - x0), "dy": float(y1 - y0),
                "dz": float(z1 - z0)}

    def bbox(self, shape):
        from forgekernel import body as B

        if isinstance(shape, B.Body):
            return B.bbox(shape)
        from forgekernel.quadric import AxisStack, Cone, Sphere
        from forgekernel.curve import TubeSolid

        from forgekernel.quadric import RoundedBox
        from forgekernel.loft import LoftSolid
        from forgekernel.profile2d import SplinePrism
        if isinstance(shape, (TubeSolid, LoftSolid, SplinePrism)):
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
        from forgekernel import body as _B

        if isinstance(shape, _B.Body):                # ADR-0021 canonical form
            return _B.edges_info(shape) if kind == "edge" else _B.faces_info(shape)
        if kind == "edge" and not isinstance(shape, _Solid):
            # every representation has edges once it is in canonical form —
            # circular bore rims included, with exact radius and axis. A
            # representation with no converter yet falls through to the legacy
            # behaviour rather than changing the exception type callers see.
            try:
                return _B.edges_info(_B.to_body(shape))
            except (ValueError, AttributeError, TypeError):
                pass
        if kind == "edge" and isinstance(shape, _Solid):
            # K5.0: deterministic straight-edge enumeration for planar
            # solids (fillet/chamfer selection targets)
            return [{"curve": "line",
                     "dir": [float(v) for v in e["dir"]],
                     "point": [float(v) for v in e["point"]],
                     "centroid": _edge_midpoint(e),
                     "length": _edge_length(e)}
                    for e in self._sorted_edges(shape)]
        if kind != "face":
            raise NotImplementedError("ref enumerates faces and edges only")
        from forgekernel.quadric import MiteredSweep, RoundedBox, SphereOverlap
        from forgekernel.curve import TubeSolid
        from forgekernel.loft import LoftSolid
        from forgekernel.profile2d import SplinePrism
        if isinstance(shape, SplinePrism):
            return [{"surface": "spline-swept"}, {"surface": "plane"},
                    {"surface": "plane"}]
        if isinstance(shape, LoftSolid):
            return [{"surface": "spline-loft"}, {"surface": "plane"},
                    {"surface": "plane"}]
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
                        "fragments": len(frags),
                        "centroid": _face_centroid(frags),
                        "area": _face_area(frags)})
        return out

    def validate(self, shape) -> ValidationReport:
        from forgekernel.quadric import Cyl, DrilledSolid

        from forgekernel.quadric import (AxisStack, Cone, DisjointUnion,
                                         MiteredSweep, RevolveSolid, RoundedBox, Sphere, SphereOverlap)
        from forgekernel.curve import TubeSolid

        from forgekernel.loft import LoftSolid
        from forgekernel.profile2d import SplinePrism
        if isinstance(shape, (LoftSolid, SplinePrism)):
            return ValidationReport(ok=shape.volume() > 0,
                                    checks={"method": "exact-green-area"},
                                    violations=[])
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
        from forgekernel import body as B

        if isinstance(shape, B.Body):
            return B.tessellate(shape, deflection)
        # planar solids mesh exactly; analytic composites mesh to a
        # bounded-error view (deflection = max chord error)
        if hasattr(shape, "tessellate"):
            try:
                return shape.tessellate(deflection)
            except TypeError:
                return shape.tessellate()
        # ADR-0021: anything with a converter meshes through the canonical
        # form. A rounded box HAS one now, and was still refusing here.
        return self._via_body("tessellate", shape,
                              lambda b: B.tessellate(b, deflection))

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

        if len(sections) < 2:
            _nope("loft(<2 sections)", "K3")
        for prof, _ in sections:
            if any(s.get("kind") != "line" for s in prof.get("segments", [])):
                _nope("loft(arc profile)", "K3")

        def loop(prof):
            pts = [tuple(prof["start"])] + [tuple(s["to"]) for s in prof["segments"]]
            return pts[:-1] if pts[0] == pts[-1] else pts

        if len(sections) > 2 and not ruled:
            # K3.7: SMOOTH multi-section loft — natural cubic spline through
            # the sections (forge's documented smoothing choice), volume
            # EXACT rational via ∫A(v)z'(v)dv. Distinct geometry from a
            # ruled stack and from OCCT's own B-spline fit.
            from forgekernel.loft import LoftSolid

            try:
                return LoftSolid([(loop(p), z) for p, z in sections])
            except ValueError as exc:
                raise KernelError(str(exc), FailureSignature(
                    op="loft", diagnostic="NotYetImplemented", kernel="ref"))

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

        if not isinstance(shape, Solid) and not edges:
            from forgekernel.quadric import DisjointUnion, DrilledSolid

            r = (radius if isinstance(radius, Fraction)
                 else Fraction(str(radius)))
            if isinstance(shape, DrilledSolid):
                # filleting a planar base yields a RoundedBox, which has no
                # polygon soup left to re-drill against — and a bore breaking
                # out through a rounded edge is exactly the case the
                # full-height-column precondition exists to catch
                _nope("fillet(drilled solid: the rounded base cannot be "
                      "re-drilled)", "K2.1")
            if isinstance(shape, DisjointUnion):
                from forgekernel import body as B

                parts = [self.fillet(m, (), radius) for m in shape.members]
                if any(isinstance(q, B.Body) for q in parts):
                    return B.Body(tuple(f for q in parts
                                        for f in B.to_body(q).faces))
                return DisjointUnion._unchecked(parts)
            prof, cx, cy = self._lathe_profile(shape)
            if prof is not None:
                # a fillet on a lathed rim sweeps a TORUS, so the blend lives
                # on the (r, z) profile just as the chamfer does — and the
                # volume needs pi^2, which is why forge grew Q[pi] as a
                # polynomial ring rather than a + b*pi
                return _lathe_body(_fillet_profile(prof, r), cx, cy)
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

    def _lathe_profile(self, shape):
        """The (r, z) profile of anything that is a solid of revolution."""
        from forgekernel.quadric import Cone as QCone, Cyl, RevolveSolid

        if isinstance(shape, RevolveSolid):
            return list(shape.loop), shape.cx, shape.cy
        if isinstance(shape, Cyl):
            r, z0, z1 = Fraction(shape.r), Fraction(shape.z0), Fraction(shape.z1)
            return [(Fraction(0), z0), (r, z0), (r, z1), (Fraction(0), z1)], \
                shape.cx, shape.cy
        if isinstance(shape, QCone):
            r1, r2 = Fraction(shape.r1), Fraction(shape.r2)
            z0, z1 = Fraction(shape.z0), Fraction(shape.z1)
            pts = [(Fraction(0), z0)] if r1 else []
            pts += [(r1, z0), (r2, z1)]
            pts += [(Fraction(0), z1)] if r2 else []
            return [p for i, p in enumerate(pts) if p not in pts[:i]], \
                shape.cx, shape.cy
        return None, None, None

    def _bore_lathe(self, a, tool):
        """A coaxial cylinder through a solid of revolution is another solid
        of revolution — exactly, with no surface-surface intersection."""
        from forgekernel.quadric import RevolveSolid

        prof, cx, cy = self._lathe_profile(a)
        if prof is None or (tool.cx, tool.cy) != (cx, cy):
            return None                      # not a lathe, or not coaxial
        out = _bore_lathe_profile(prof, Fraction(tool.r),
                                  Fraction(tool.z0), Fraction(tool.z1))
        return RevolveSolid(out, cx, cy)

    def _chamfer_lathe(self, shape, d):
        """Chamfer a solid of revolution by chamfering its PROFILE.

        A 45° cut on a lathed rim sweeps a cone frustum, so the chamfered
        solid is still a solid of revolution — no new surface type, no
        approximation, and the metrics stay exact in ℚ[π]. Only CONVEX
        corners are cut (a concave one is an internal step, where a chamfer
        would add material rather than remove it), and never a corner on the
        axis, which is not an edge of the solid at all.
        """
        from forgekernel.quadric import RevolveSolid

        prof, cx, cy = self._lathe_profile(shape)
        if prof is None:
            return None
        n = len(prof)
        area2 = sum(prof[i][0] * prof[(i + 1) % n][1]
                    - prof[(i + 1) % n][0] * prof[i][1] for i in range(n))
        turn = 1 if area2 > 0 else -1
        out = []
        for i in range(n):
            p0, p1, p2 = prof[i - 1], prof[i], prof[(i + 1) % n]
            a = (p1[0] - p0[0], p1[1] - p0[1])
            b = (p2[0] - p1[0], p2[1] - p1[1])
            cross = a[0] * b[1] - a[1] * b[0]
            la2, lb2 = a[0] ** 2 + a[1] ** 2, b[0] ** 2 + b[1] ** 2
            if p1[0] == 0 or cross * turn <= 0 or not la2 or not lb2:
                out.append(p1)
                continue
            if d * d * 4 > la2 or d * d * 4 > lb2:
                _nope("chamfer(distance exceeds half the profile edge)", "K5.2")
            from forgekernel.body import _rational_sqrt

            ka = _rational_sqrt(la2)
            kb = _rational_sqrt(lb2)
            if ka is None or kb is None:
                _nope("chamfer(profile edge with irrational length)", _K2)
            out.append((p1[0] - a[0] * d / ka, p1[1] - a[1] * d / ka))
            out.append((p1[0] + b[0] * d / kb, p1[1] + b[1] * d / kb))
        return RevolveSolid(out, cx, cy)

    def chamfer(self, shape, edges, distance):
        from forgekernel.kernel import chamfer as fk_chamfer

        if not edges:
            from forgekernel.brep import Solid
            from forgekernel.quadric import DisjointUnion, DrilledSolid

            d = (distance if isinstance(distance, Fraction)
                 else Fraction(str(distance)))
            if isinstance(shape, DrilledSolid):
                # chamfer the BASE and re-drill: DrilledSolid.cut validates
                # that every bore still lands inside the (now smaller) solid,
                # so a bore the chamfer ate into refuses rather than silently
                # producing a part with a broken-out hole
                base = self.chamfer(shape.base, (), distance)
                out = DrilledSolid(base, [])
                try:
                    for b in shape.bores:
                        out = out.cut(b)
                except ValueError as exc:
                    # the reshaped base no longer carries a full-height column
                    # under some bore; an honest gap, not a crash through the
                    # seam (the invariant test pins that distinction)
                    _nope(f"chamfer(drilled solid: {exc})", "K2.1")
                return out
            if isinstance(shape, DisjointUnion):
                # members are disjoint and a chamfer only REMOVES material,
                # so they stay disjoint
                return DisjointUnion._unchecked(
                    [self.chamfer(m, (), distance) for m in shape.members])
            if not isinstance(shape, Solid):
                lathe = self._chamfer_lathe(shape, d)
                if lathe is not None:
                    return lathe
            try:
                return fk_chamfer(shape, distance)
            except (ValueError, AttributeError) as exc:
                raise KernelError(str(exc), FailureSignature(
                    op="chamfer", diagnostic="NotYetImplemented", kernel="ref"))

        # selected edges: exact 45° wedge cut per axis-aligned box edge — a
        # planar, rational operation (the chamfer facet's endpoints are rational).
        from forgekernel.brep import Solid

        box = self._box_check(shape) if isinstance(shape, Solid) else None
        if box is None:
            _nope("chamfer(selected edges of a non-box)", "K5.2 (general blends)")
        lo, hi = box
        all_edges = self._sorted_edges(shape)
        d = distance if isinstance(distance, Fraction) else Fraction(str(distance))
        if d <= 0:
            raise KernelError(
                f"chamfer distance must be positive (got {float(d)})",
                FailureSignature(op="chamfer", diagnostic="BadInput", kernel="ref"))
        out = shape
        for idx in edges:
            e = all_edges[idx]
            dirv = [float(x) for x in e["dir"]]
            axes = [i for i in range(3) if abs(dirv[i]) > 1e-12]
            if len(axes) != 1:
                _nope("chamfer(non-axis-aligned edge)", "K5.2 (general blends)")
            ea = axes[0]
            eb, ec = (i for i in range(3) if i != ea)
            mid = _edge_midpoint(e)

            def _snap(val, loi, hii):
                if abs(val - float(loi)) < 1e-9:
                    return loi, 1
                if abs(val - float(hii)) < 1e-9:
                    return hii, -1
                return None

            sb, sc = _snap(mid[eb], lo[eb], hi[eb]), _snap(mid[ec], lo[ec], hi[ec])
            if sb is None or sc is None:
                _nope("chamfer(interior edge)", "K5.2 (general blends)")
            (pb, db), (pc, dc) = sb, sc
            tri = [(pb, pc), (pb + d * db, pc), (pb, pc + d * dc)]
            wedge = _tri_prism_along(ea, tri, lo[ea], hi[ea])
            try:
                out = self._fk.boolean("cut", out, wedge)
            except (ValueError, ArithmeticError) as exc:
                raise KernelError(
                    f"chamfer: distance {float(d)} too large for the edge ({exc})",
                    FailureSignature(op="chamfer", diagnostic="BadInput", kernel="ref"))
            if not getattr(out, "polys", None) or out.volume() <= 0:
                raise KernelError(
                    f"chamfer: distance {float(d)} removes the whole cross-section",
                    FailureSignature(op="chamfer", diagnostic="BadInput", kernel="ref"))
        return out

    def _inset_profile(self, prof, t):
        """Inset a RECTILINEAR (r, z) profile inward by t, exactly.

        Only axis-aligned edges: a slanted edge's inward normal carries
        1/sqrt(dr^2+dz^2), which leaves ℚ, and a shell wall must be exactly
        t thick or the part is not the part. Edges lying ON the axis are not
        faces of the solid at all and are never offset — insetting them would
        put a solid core inside the void.
        """
        # A REDUNDANT collinear vertex has two identical edge normals, so
        # summing per-edge moved it 2t instead of t — and a cosmetic extra
        # point in the profile silently changed the reported volume of
        # identical geometry by 20%. Drop them before offsetting.
        prof = _drop_collinear_2d(prof)
        n = len(prof)
        out = []
        for i in range(n):
            p0, p1, p2 = prof[i - 1], prof[i], prof[(i + 1) % n]
            shift = [Fraction(0), Fraction(0)]
            for (qa, qb) in ((p0, p1), (p1, p2)):
                dr, dz = qb[0] - qa[0], qb[1] - qa[1]
                if qa[0] == 0 and qb[0] == 0:
                    continue                       # the axis is not a face
                if dr != 0 and dz != 0:
                    _nope("shell(slanted lathe profile edge)",
                          "K4.2 (offset surfaces)")
                if dr == 0 and dz == 0:
                    continue
                ln = abs(dr) if dr else abs(dz)
                shift[0] += -dz / ln * t
                shift[1] += dr / ln * t
            out.append((p1[0] + shift[0], p1[1] + shift[1]))
        if any(r < 0 for r, _ in out):
            _nope("shell(thickness exceeds the lathe's radius)", "K4.2")
        # An offset polygon INVERTS where a step is shorter than 2t: the void
        # becomes a bow tie whose Green's integral is negative, or escapes the
        # solid entirely (one case put the cavity below z=0). The mesh still
        # comes back watertight, so nothing downstream notices — check it here
        # or not at all.
        if _signed_area2(out) * _signed_area2(prof) <= 0:
            _nope("shell(thickness inverts the profile)", "K4.2")
        if abs(_signed_area2(out)) >= abs(_signed_area2(prof)):
            _nope("shell(inset is not smaller than the profile)", "K4.2")
        if not _is_simple(out):
            _nope("shell(thickness makes the void self-intersect)", "K4.2")
        if not all(_point_in_poly(prof, q) for q in out):
            _nope("shell(void escapes the solid)", "K4.2")
        return out

    def _shell_lathe(self, shape, t):
        """Hollow a solid of revolution: the void is the profile inset by t,
        lathed and turned inside out. Its faces are the inner solid's with
        every sense FLIPPED — a cavity's boundary faces point away from the
        material, which is into the cavity — so the divergence sum subtracts
        the void and the shelled volume is exact with no boolean at all."""
        from forgekernel import body as B
        from forgekernel.quadric import RevolveSolid

        prof, cx, cy = self._lathe_profile(shape)
        if prof is None:
            return None
        inner = RevolveSolid(self._inset_profile(prof, t), cx, cy)
        void = B.to_body(inner)
        return B.Body(B.to_body(shape).faces
                      + tuple(B.Face(f.surface, f.loops, not f.sense)
                              for f in void.faces))

    def shell(self, shape, remove_faces, thickness):
        from forgekernel.brep import Solid
        from forgekernel.kernel import shell as fk_shell

        if not isinstance(shape, Solid) and not remove_faces:
            from forgekernel.quadric import DisjointUnion, DrilledSolid

            t = (thickness if isinstance(thickness, Fraction)
                 else Fraction(str(thickness)))
            if isinstance(shape, DrilledSolid):
                base = self.shell(shape.base, (), thickness)
                out = DrilledSolid(base, [])
                try:
                    for b in shape.bores:
                        out = out.cut(b)
                except ValueError as exc:
                    # after hollowing, the bore passes through the CAVITY,
                    # where only the two walls carry material — a full-barrel
                    # removal would take metal that is not there. An honest
                    # gap, and it must not escape the seam as a raw exception.
                    _nope(f"shell(drilled solid: {exc})", "K2.1")
                return out
            if isinstance(shape, DisjointUnion):
                from forgekernel import body as B

                parts = [self.shell(m, (), thickness) for m in shape.members]
                if any(isinstance(q, B.Body) for q in parts):
                    # a DisjointUnion's members must be quadric types: putting
                    # a Body in one turned a working object into a crashing
                    # one (volume/tessellate reach for .cx). The members are
                    # disjoint, so their faces already form ONE valid Body.
                    return B.Body(tuple(f for q in parts
                                        for f in B.to_body(q).faces))
                return DisjointUnion._unchecked(parts)
            lathe = self._shell_lathe(shape, t)
            if lathe is not None:
                return lathe
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

    def hlr_project(self, shape, direction, xdir, *, deflection=0.05):
        # ADR-0020: native forge hidden-line removal — visibility is a display
        # property (floats legal), the geometry drawn is the exact solid.
        from forgekernel.hlr import hidden_line

        return hidden_line(shape, direction, xdir, deflection=deflection)

    def section_polys(self, shape, direction, xdir, offset, *, deflection=0.05):
        # ADR-0020: native section curves (plane ∩ solid boundary) — same
        # sheet frame as hlr_project, so a section view overlays exactly.
        from forgekernel.hlr import section_polys

        return section_polys(shape, direction, xdir, offset, deflection=deflection)

    def export_step(self, shape, path):
        # K7.0c: native AP214 export — OCCT-free CAD exchange. Planar solids and
        # drilled solids (exact CYLINDRICAL_SURFACE bores, not facets) export;
        # freeform topology arrives at K3.7.
        from forgekernel.brep import Solid
        from forgekernel.quadric import Cyl, DrilledSolid
        from forgekernel.stepio import write_step_planar_solid

        if isinstance(shape, Solid):
            base, bores = shape, ()
        elif isinstance(shape, DrilledSolid):
            base, bores = shape.base, shape.bores
        else:
            # ADR-0021: everything else exports from the canonical B-rep, one
            # writer for all representations. A bare cylinder, a boss and a
            # bored boss all used to refuse for want of a planar base to hang
            # the topology on — the canonical form has no such notion.
            from forgekernel.stepbody import write_step_body

            text = self._via_body("export_step", shape,
                                  lambda b: write_step_body(b))
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            return
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(write_step_planar_solid(base, bores=bores))

    def export_stl(self, shape, path, *, deflection=0.1):
        from forgekernel import io

        try:
            text = io.to_stl(shape)
        except AttributeError:
            # io.to_stl expects a planar Solid; everything else meshes through
            # the canonical form, which is the same mesh tessellate() returns
            mesh = self.tessellate(shape, deflection=deflection)
            v = mesh["vertices"]
            out = ["solid forge"]
            for a, b, c in mesh["triangles"]:
                out += ["facet normal 0 0 0", "outer loop"]
                out += [f"vertex {v[i][0]:.9g} {v[i][1]:.9g} {v[i][2]:.9g}"
                        for i in (a, b, c)]
                out += ["endloop", "endfacet"]
            out.append("endsolid forge")
            text = chr(10).join(out) + chr(10)
        with open(path, "w", newline=chr(10)) as f:
            f.write(text)

    def export_brep(self, shape, path):
        from forgekernel import io
        from forgekernel.brep import Solid

        if isinstance(shape, Solid):
            text = io.dumps(shape)
        else:
            # ADR-0021: the native format described planar polygon soup only,
            # so a bore, a boss or a lathe had nothing to serialise. The
            # canonical form is written ANALYTICALLY — a hole is a cylinder
            # with an exact radius, so a git diff reads as a change of
            # geometry rather than a reshuffle of triangles.
            text = self._via_body("export_brep", shape,
                                  lambda b: io.dumps_body(b))
        with open(path, "w", newline=chr(10)) as f:
            f.write(text)

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


def _drop_collinear_2d(poly):
    """Remove vertices that lie mid-edge — they carry no shape, and an offset
    counts their (duplicated) edge normal twice."""
    out = list(poly)
    i = 0
    while len(out) > 3 and i < len(out):
        a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
        if ((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) == 0:
            del out[i]
        else:
            i += 1
    return out


def _signed_area2(poly):
    n = len(poly)
    return sum(poly[i][0] * poly[(i + 1) % n][1]
               - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))


def _orient(a, b, c):
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 0 if v == 0 else (1 if v > 0 else -1)


def _segments_cross(a, b, c, d) -> bool:
    o1, o2 = _orient(a, b, c), _orient(a, b, d)
    o3, o4 = _orient(c, d, a), _orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    def on(p, q, r):
        return (_orient(p, q, r) == 0
                and min(p[0], q[0]) <= r[0] <= max(p[0], q[0])
                and min(p[1], q[1]) <= r[1] <= max(p[1], q[1]))
    return on(a, b, c) or on(a, b, d) or on(c, d, a) or on(c, d, b)


def _is_simple(poly) -> bool:
    """Exact: does the polygon avoid touching itself anywhere but at shared
    vertices of adjacent edges?"""
    n = len(poly)
    for i in range(n):
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            if _segments_cross(poly[i], poly[(i + 1) % n],
                               poly[j], poly[(j + 1) % n]):
                return False
    return True


def _point_in_poly(poly, q) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > q[1]) != (y2 > q[1]):
            if q[0] < x1 + (q[1] - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def _fillet_profile(prof, r):
    """Round every convex RIGHT-ANGLE corner of an (r, z) profile.

    Returns segments: ``("line", p0, p1)`` and ``("arc", centre, p0, p1)``.
    Only right angles between axis-aligned edges — the tangent points and the
    arc centre are then rational, and revolving the arc sweeps exactly a
    QUARTER of a torus tube, which is what keeps the volume in ℚ[π].
    """
    prof = _drop_collinear_2d(prof)
    n = len(prof)
    area2 = _signed_area2(prof)
    turn = 1 if area2 > 0 else -1
    cut = {}
    for i in range(n):
        p0, p1, p2 = prof[i - 1], prof[i], prof[(i + 1) % n]
        a = (p1[0] - p0[0], p1[1] - p0[1])
        b = (p2[0] - p1[0], p2[1] - p1[1])
        cross = a[0] * b[1] - a[1] * b[0]
        if p1[0] == 0 or cross * turn <= 0:
            continue                       # on the axis, or concave
        if (a[0] and a[1]) or (b[0] and b[1]) or a[0] * b[0] + a[1] * b[1] != 0:
            _nope("fillet(non-right-angle lathe corner)", "K5.2")
        la = abs(a[0]) if a[0] else abs(a[1])
        lb = abs(b[0]) if b[0] else abs(b[1])
        if 2 * r > la or 2 * r > lb:
            _nope("fillet(radius exceeds half the profile edge)", "K5.2")
        ua = (a[0] / la, a[1] / la)
        ub = (b[0] / lb, b[1] / lb)
        ta = (p1[0] - r * ua[0], p1[1] - r * ua[1])
        tb = (p1[0] + r * ub[0], p1[1] + r * ub[1])
        # inward normal of the incoming edge is (-dz, dr)/|d| for a positively
        # wound profile; for a right angle the two agree on the centre
        na = (-ua[1] * turn, ua[0] * turn)
        cen = (ta[0] + r * na[0], ta[1] + r * na[1])
        cut[i] = (cen, ta, tb)

    segs, pts = [], []
    for i in range(n):
        pts.append(cut[i][1] if i in cut else prof[i])
        if i in cut:
            pts.append(cut[i][2])
    j = 0
    out = []
    for i in range(n):
        start = pts[j]
        if i in cut:
            out.append(("arc", cut[i][0], cut[i][1], cut[i][2]))
            j += 2
        else:
            j += 1
        nxt = pts[j % len(pts)]
        out.append(("line", pts[(j - 1) % len(pts)], nxt))
    return [sg for sg in out if sg[0] == "arc"
            or (sg[1][0], sg[1][1]) != (sg[2][0], sg[2][1])]


def _lathe_body(segs, cx, cy):
    from forgekernel import body as B

    return B.lathe_body(segs, cx, cy)


def _bore_lathe_profile(prof, tool_r, zlo, zhi):
    """Bore a coaxial hole of radius ``tool_r`` through a lathed profile.

    A cylinder coaxial with a solid of revolution cuts it into another solid
    of revolution — no surface–surface intersection and no conic sections,
    because the tool's wall meets the profile plane in a straight line. The
    profile's points ON THE AXIS become the bore wall.

    Refuses unless the bore passes clean through and stays strictly inside the
    material: a partial bore leaves a blind pocket whose floor is a new face,
    and a bore wider than the part at some height is a different solid
    entirely.
    """
    zs = [z for _r, z in prof]
    if zlo > min(zs) or zhi < max(zs):
        _nope("boolean.cut(bore does not pass through the lathe)", "K2.2")
    on_axis = [i for i, (r, _z) in enumerate(prof) if r == 0]
    if not on_axis:
        _nope("boolean.cut(lathe already has a bore)", "K2.2")
    for i, (r, _z) in enumerate(prof):
        if i not in on_axis and r < tool_r:
            _nope("boolean.cut(bore is wider than the lathe at some height)",
                  "K2.2")
    return [(tool_r if r == 0 else r, z) for r, z in prof]
