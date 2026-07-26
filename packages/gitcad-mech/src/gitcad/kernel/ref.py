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


def _exact_volume(shape) -> float:
    """The volume, from the CANONICAL form, rendered once at the boundary.

    ``AxisStack.volume()`` integrates its z-slabs in float and wraps the result
    in a ``PiVal`` — a float laundered into an exact-looking type, which is the
    worst arrangement available: it reads as exact and is not. It is also
    POSITION-DEPENDENT, so the same sphere reports a different volume after a
    translation:

        Sphere(1.5, 1.5, 4.5, 6.5).volume()  ->  6441672123263659/17592186044416 · π
        the truth                            ->                        2197/6 · π

    That last-digit wobble matters more here than the size of it suggests: this
    product's premise is that designs diff, and a part that reports a different
    volume merely for having moved shows up as a change that is not one.

    The whole corpus hides it, because every shape in it has integer dimensions
    and the float arithmetic lands exactly. A fractional radius does not.

    ADR-0021's answer applies: the canonical B-rep computes this exactly for
    every representation, so ask it, and keep the per-representation formula
    only for shapes that have no canonical form yet.
    """
    from forgekernel import body as B

    try:
        return float(B.volume(B.to_body(shape)))
    except (ValueError, AttributeError, TypeError):
        v = shape.volume()
        return v.to_float() if hasattr(v, "to_float") else float(v)


def _mesh_tears(canon) -> int:
    """Count unpaired directed edges in a coarse mesh of ``canon``.

    Floats are legal here — this is meshing (ADR-0019). The count decides only
    whether to refuse; no geometry is derived from it.

    A closed, correctly-wound triangle mesh uses every directed edge (a, b)
    exactly as often as its reverse (b, a). Anything else is a hole, a doubled
    face, or a seam that did not close. Returns 0 when the shape cannot be
    meshed at all — that is a different failure, reported by whoever asks for
    the mesh, and not something to convert into a bogus tear count here.
    """
    from collections import Counter

    from forgekernel import body as B

    try:
        mesh = B.tessellate(canon, 0.8)
    except Exception:                           # noqa: BLE001 - see docstring
        return 0
    seen: Counter = Counter()
    for tri in mesh.get("triangles", ()):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            seen[(a, b)] += 1
    return sum(1 for (a, b), n in seen.items() if seen.get((b, a), 0) != n)


def _audited(body, op: str):
    """Check the ANSWER before returning it. The whole burn-down in one rule.

    Every silent wrong number this kernel has produced came from validating the
    INPUT by sampling instead of validating the OUTPUT: a guard probed four
    points of a footprint, or asked whether a tool's volume matched its bbox,
    and a shape that satisfied the probe but not the property sailed through.
    A property test can always be satisfied by something that is not the thing;
    the constructed body cannot lie about what it is.

    Two exact checks, both cheap enough to run on every construction:

      * every edge shared by exactly two faces — the closed-shell oracle, which
        catches a rim minted twice, a T-junction left unsplit, a face dropped;
      * positive volume, by the EXACT sign, so an inside-out body cannot pass
        by rounding to zero.

    Mesh watertightness is deliberately NOT here: it needs a tessellation per
    call, and it belongs in the differential harness that already samples
    deflections. Torus faces carry no boundary loops yet (#130), so a body with
    one is exempted from pairing rather than failing on a known gap — the
    volume check still applies.
    """
    from forgekernel import body as B
    from gitcad.errors import GeometryInvalidError

    # AUDIT THE CANONICAL FORM, NOT THE RETURNED TYPE. This used to read
    # `if not isinstance(body, B.Body): return body`, which meant the audit
    # only ever fired on hand-built Bodies — and most results are NOT Bodies
    # (Cyl, DrilledSolid, AxisStack, DisjointUnion, RoundedBox, RevolveSolid,
    # …), so the majority of this kernel's answers were never checked at all.
    # That is the ADR-0021 problem wearing a different hat: the check knew
    # about the canonical form, the ops returned representations, and the gap
    # between them was the hole.
    #
    # Converting first closes it. Measured before changing anything: all 15
    # corpus representations convert and all 15 pass, so this buys coverage
    # without changing a single existing answer.
    #
    # A representation with no canonical form is NOT a failure — there is
    # simply nothing to audit against, and refusing there would turn a working
    # op into a refusal on the strength of a missing converter.
    subject = body
    if not isinstance(body, B.Body):
        try:
            subject = B.to_body(body)
        except Exception:                       # noqa: BLE001 - see above
            return body
    bad = []
    if not any(isinstance(f.surface, B.Torus) for f in subject.faces):
        bad += B.manifold_violations(subject)
    # Ask the value for its SIGN; do not order it against a bare 0. Every exact
    # type here decides its own sign exactly (ADR-0019), but their rich
    # comparisons route through helpers that SWALLOW TypeError and ValueError
    # and hand back NotImplemented — so a coercion failure inside the number
    # field surfaced as "'<=' not supported between instances of 'PiVal' and
    # 'int'", a message about Python's operator protocol rather than about the
    # arithmetic, three modules from the cause. A safety net must not be
    # disarmable by a swallowed exception; `.sign()` lets the real failure out.
    vol = B.volume(subject)
    if (vol.sign() if hasattr(vol, "sign") else (vol > 0) - (vol < 0)) <= 0:
        bad.append(f"volume is not positive ({float(vol):.6g})")
    # Orientation, which edge pairing cannot see: it counts how many faces use
    # each edge, never which DIRECTION. Reversing one face of a box leaves
    # every edge used exactly twice and passes the pairing check outright.
    # Gauss' identity closes that gap — the face vector areas of a closed shell
    # sum to zero — and it is a boundary integral, so it needs no per-surface
    # area formula. None means NOT CHECKED (a body carrying arcs), never passed.
    defect = B.vector_area_defect(subject)
    if defect is not None and any(d != 0 for d in defect):
        bad.append("faces are not consistently oriented — the shell's vector "
                   f"areas sum to {tuple(float(d) for d in defect)}, not zero")
    # The MESH, coarsely. The three checks above are all exact and all reason
    # about the b-rep; none of them looks at what gets tessellated, and a body
    # can satisfy every one of them while producing a torn STL — the #123
    # prototype does exactly that (exact volume, clean pairing, 87 non-manifold
    # directed edges) because the trimmed-band mesher meshes the (theta,z)
    # BOUNDING RECTANGLE rather than the real domain. A right number behind a
    # wrong artifact is still a wrong answer to whoever prints the part.
    #
    # Deliberately COARSE (deflection 0.8): this is a topology question, not an
    # accuracy one, and a torn mesh is torn at any resolution. Measured across
    # the corpus: 15/15 clean, 1.9 ms average — cheap enough for every op.
    #
    # Floats are legal here — this is meshing (ADR-0019). No exact predicate
    # depends on the result; it only decides whether to REFUSE.
    torn = _mesh_tears(subject)
    if torn:
        bad.append(f"the mesh is not watertight — {torn} directed edges are "
                   "unpaired at a coarse deflection")
    if bad:
        raise GeometryInvalidError(
            f"{op} built an invalid body — refusing to return it: "
            + "; ".join(bad[:4]),
            FailureSignature(op=op, diagnostic="AnswerAudit", kernel="ref"),
            stage="audit", predicate="answer_is_a_closed_solid",
            measured={"violations": len(bad), "faces": len(subject.faces)},
            remedy="this is a kernel defect, not a bad request — please report it")
    # the ORIGINAL object goes back to the caller: the conversion is a check,
    # never a change of representation
    return body


def _nope(op: str, stage: str, *, predicate: str | None = None,
          measured: dict | None = None, remedy: str | None = None):
    """Refuse, and say enough that the caller can do something about it.

    ``predicate`` names the guard, ``measured`` carries the numbers it actually
    saw, and ``remedy`` says in one sentence what would make it work. An agent
    that hits a bare string has to read this file to know whether to shrink the
    hole, move it, or give up; with these it can just act. The measured values
    are LOCAL ONLY — they are user coordinates and never enter the signature
    (ADR-0006/0007).

    Every refusal also lands on the live rail, so a person watching sees WHY
    the agent stopped rather than only that it did.
    """
    from gitcad import activity

    activity.note("problem", text=f"{op} — {stage}", predicate=predicate,
                  remedy=remedy)
    raise KernelError(
        f"ref kernel does not implement {op} yet — {stage}",
        FailureSignature(op=op, diagnostic="NotYetImplemented", kernel="ref"),
        stage=stage, predicate=predicate, measured=measured, remedy=remedy)


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


def _edge_midpoint(e):
    """Midpoint of a logical straight edge (``tmin``/``tmax`` are the along-dir
    coordinates), for geometry-based edge selection.

    EXACT. This picks which edges an op acts on, which is a topology decision,
    so it may not round: ``tmin``/``tmax`` and the direction are already exact
    and their mean is a ratio of them (ADR-0019).
    """
    return _edge_point(e, (e["tmin"] + e["tmax"]) / 2)


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

        # a sphere with a COAXIAL bore drilled clean through it: a napkin ring.
        # Exact in ℚ[√d][π] — the arc term lives in forgekernel.surdrev and is
        # proven there against the closed form V = (4/3)π(R²−r²)^(3/2).
        #
        # Only the CENTRED, THROUGH case. Off-axis, the volume acquires
        # elliptic integrals and leaves every algebraic extension, so there is
        # nothing to be exact about; a blind bore leaves a spherical cap floor
        # that this two-face solid cannot hold. Both keep refusing, and that is
        # the honest answer rather than a near-miss.
        if op == "cut" and isinstance(a, Sphere) and isinstance(b, Cyl):
            from forgekernel.surdrev import NapkinRing

            ax, ay, az = a.c if hasattr(a, "c") else (a.cx, a.cy, a.cz)
            if b.cx == ax and b.cy == ay and 0 <= b.r < a.r \
                    and b.z0 <= az - a.r and b.z1 >= az + a.r:
                return _audited(NapkinRing(a.r, b.r, ax, ay, az), "boolean.cut")

        # two overlapping spheres: exact ℚ[π] cap/lens booleans (K2.2)
        if isinstance(a, Sphere) and isinstance(b, Sphere) and op in ("union", "cut", "intersect"):
            try:
                return SphereOverlap(a, b, op)
            except ValueError:
                pass  # not overlapping / nested / irrational → fall through
        from forgekernel.quadric import RevolveSolid, RoundedBox

        if op == "cut":
            # A tool whose bbox is SEPARATED from the solid's removes nothing,
            # whatever either shape is. Exact (bbox separation in any one axis
            # is decisive, and touching is measure zero), and it belongs ahead
            # of every representation-specific path: a drilled solid asked to
            # cut a tool it never meets refused with "bore misses the solid in
            # xy" rather than handing back the solid it already was.
            from forgekernel.quadric import _exact_bbox

            ab, bb_ = _exact_bbox(a), _exact_bbox(b)
            if ab is not None and bb_ is not None and any(
                    bb_[1][k] <= ab[0][k] or ab[1][k] <= bb_[0][k]
                    for k in range(3)):
                return a
            # A bore can also miss inside the bbox — down an L-prism's notch,
            # say, where the two shapes overlap in every axis and the disc
            # still never touches material. That is exactly decidable against
            # the solid's xy shadow, and "the bore misses" is the ANSWER, not
            # a reason to refuse.
            base = (a if isinstance(a, Solid)
                    else a.base if isinstance(a, DrilledSolid) else None)
            if isinstance(b, Cyl) and base is not None and _disc_misses_solid(
                    base, Fraction(b.cx), Fraction(b.cy), Fraction(b.r)):
                return a

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
            # standing on a plate keeps its pilot bore exact. DisjointUnion.cut
            # only knows some member types, so fall through to the seam's own
            # distribution rather than refusing on its behalf — it handles
            # lathes, misses and pockets that the quadric layer does not.
            try:
                return a.cut(b)
            except ValueError:
                pass
        if op == "cut" and isinstance(b, Solid) and isinstance(a, DrilledSolid):
            from forgekernel.quadric import _exact_bbox

            tb = _exact_bbox(b)
            if tb is not None and b.volume() == (tb[1][0] - tb[0][0]) * (
                    tb[1][1] - tb[0][1]) * (tb[1][2] - tb[0][2]):
                # A tool sitting entirely inside a bore removes NOTHING: the
                # material is already gone. Exactly decidable (a rectangle is
                # inside a disc iff its corners are), and it is the honest
                # answer where cutting one out of the OTHER shape would need
                # a square-minus-circular-segment area and leave Q[pi].
                (tx0, ty0, tz0), (tx1, ty1, tz1) = tb
                (_sx0, _sy0, sz0), (_sx1, _sy1, sz1) = _exact_bbox(a.base)
                lo_z, hi_z = max(tz0, sz0), min(tz1, sz1)
                for c in a.bores:
                    corners_in = max((x - c.cx) ** 2 + (y - c.cy) ** 2
                                     for x in (tx0, tx1)
                                     for y in (ty0, ty1)) <= c.r * c.r
                    # a rectangle lies inside a disc exactly when its corners
                    # do (both convex), and the part of the tool that could
                    # remove anything is only what overlaps the solid in z
                    if corners_in and c.z0 <= lo_z and hi_z <= c.z1:
                        return a
            base = self.boolean("cut", a.base, b)
            out = DrilledSolid(base, [])
            try:
                for c in a.bores:
                    out = out.cut(c)
            except ValueError as exc:
                _nope(f"boolean.cut(drilled solid: {exc})", "K2.1")
            return out
        if op == "cut" and isinstance(a, DisjointUnion):
            # (A u B) \ C distributes over disjoint members, and cutting only
            # SHRINKS each one, so disjointness survives without re-checking.
            # A member the tool provably MISSES comes back untouched — asking
            # the member to cut itself against something it never meets is how
            # a boss lost a cell to "the prism splits the lathe".
            from forgekernel.quadric import _exact_bbox

            tb = _exact_bbox(b)
            out = []
            for m in a.members:
                mb = _exact_bbox(m)
                if tb is not None and mb is not None and any(
                        tb[1][k] <= mb[0][k] or mb[1][k] <= tb[0][k]
                        for k in range(3)):
                    out.append(m)
                else:
                    out.append(self.boolean("cut", m, b))
            return DisjointUnion._unchecked(out)
        if op == "cut":
            rb = self._pocket_rounded(a, b)
            if rb is not None:
                return rb
        if op == "cut":
            pocket = self._pocket_lathe(a, b)
            if pocket is not None:
                return pocket
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
        # RoundedBox, RevolveSolid and DisjointUnion belong on this list too:
        # they have no `.polys`, so falling through to the planar BSP engine
        # surfaced raw CPython text ("'RoundedBox' object has no attribute
        # 'polys'") as the kernel's diagnostic instead of naming the stage.
        if isinstance(a, curved) or isinstance(b, curved):
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

    def can(self, op: str, *args, **kwargs) -> dict:
        """Would this operation succeed? Answers WITHOUT raising.

        An agent planning a feature tree otherwise has to commit to each step
        and unwind when the kernel refuses three features later. This lets it
        ask first, and — because a refusal now carries its measurements and a
        remedy (#114) — the answer says what to change, not merely no:

            k.can("boolean", "cut", plate, bore)
            {'ok': False, 'predicate': 'mouth_inside_cap',
             'measured': {'clearance': -3.0, ...},
             'remedy': 'move the feature 3 mm further from the flat's edge…'}

        It really RUNS the op and throws the result away, rather than
        predicting from a table. That costs the work twice, and it is the only
        honest implementation: a table of what the kernel can do is a second
        source of truth that will drift from the kernel itself, and this whole
        burn-down is a catalogue of what happens when two things that should
        agree are allowed not to.
        """
        fn = getattr(self, op, None)
        if not callable(fn):
            return {"ok": False, "op": op, "remedy": f"no seam operation {op!r}"}
        try:
            fn(*args, **kwargs)
        except KernelError as exc:
            return {"ok": False, **exc.as_dict()}
        except Exception as exc:              # noqa: BLE001 - a crash is a defect
            return {"ok": False, "op": op,
                    "message": f"{type(exc).__name__}: {exc}",
                    "remedy": "this is a kernel defect, not a bad request — "
                              "please report it"}
        return {"ok": True, "op": op}

    def compound(self, shapes: list):
        """Several bodies as one. FUSED where they meet, never merely piled up.

        This used to be ``Solid([p for s in shapes for p in s.polys])`` — a poly
        soup. For disjoint bodies that is exactly right and very cheap, and it
        is the multi-body import container the seam documents. For bodies that
        OVERLAP it is a wrong answer that every downstream measurement inherits,
        because volume is a divergence sum over faces and interior faces are
        still faces:

            compound([box[0,2]³, box[1,3]³])   reported 16, truth 15
            cut / intersect against such a tool were wrong ~0.5% of the time
            over random compounds, and two thirds of those returned MATERIAL
            where the answer had to be empty — with validate() saying ok.

        So: keep the soup only while the members are provably separated by an
        exact bbox test, and otherwise fold them with the exact boolean engine,
        which is the operation the caller actually meant. The stacked-plate
        case proves the point — the kernel already knew the right answer, it
        just was not asked: `union` of three touching plates gave 6000 while
        `compound` of the same three gave a body that later measured 5853.39
        against a true 5811.50.
        """
        from forgekernel.brep import Solid
        from forgekernel.quadric import _exact_bbox

        shapes = list(shapes)
        if len(shapes) < 2:
            return shapes[0] if shapes else Solid([])
        boxes = [_exact_bbox(s) for s in shapes]
        disjoint = all(
            boxes[i] is not None and boxes[j] is not None and any(
                boxes[i][1][k] <= boxes[j][0][k] or boxes[j][1][k] <= boxes[i][0][k]
                for k in range(3))
            for i in range(len(shapes)) for j in range(i + 1, len(shapes)))
        if disjoint and all(isinstance(s, Solid) for s in shapes):
            return Solid([p for s in shapes for p in s.polys])
        out = shapes[0]
        for s in shapes[1:]:
            out = self.boolean("union", out, s)
        return out

    # -- metrics --------------------------------------------------------------

    def mass_props(self, shape) -> dict[str, float]:
        try:
            return self._mass_props(shape)
        except ValueError as exc:
            # forge refuses honestly when a value leaves the exact field (an
            # irrational profile crossover, say). Letting that out as a bare
            # ValueError is the defect -- callers cannot tell it from a bug.
            _nope(f"mass_props({exc})", _K2)

    def _mass_props(self, shape) -> dict[str, float]:
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
        # Measure the volume on the ORIGINAL shape, before the AxisStack wrap
        # below: a Sphere has a canonical body and an AxisStack does not, so
        # wrapping first would send it down the float-integrating path that
        # _exact_volume exists to avoid.
        vol = _exact_volume(shape)
        if isinstance(shape, (Cone, Sphere)):
            shape = AxisStack(shape.cx, shape.cy, [shape])
        from forgekernel.quadric import FilletedBox
        if isinstance(shape, (Cyl, DrilledSolid, AxisStack, RevolveSolid, DisjointUnion, RoundedBox, MiteredSweep, SphereOverlap, FilletedBox)):
            cx, cy, cz = shape.centroid_f()
            return _mp(vol, cx, cy, cz)
        c = shape.centroid()
        return _mp(vol, float(c[0]), float(c[1]), float(c[2]))

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
        from forgekernel import body as _B
        if isinstance(shape, _B.Body):
            # A Body has no `watertight_violations` — it is a different
            # representation — so every pocketed or curved-shelled solid came
            # back "unsupported representation", i.e. unvalidatable, which
            # reads far too much like fine. The canonical B-rep's own oracle is
            # edge pairing: in a closed shell every edge is shared by exactly
            # two faces.
            bad = _B.manifold_violations(shape)
            # the exact sign, not float(...) <= 0: a solid whose true volume is
            # a hair above zero must not validate as inside-out because the
            # double rounded to 0.0
            if _B.volume(shape) <= 0:
                bad = list(bad) + ["nonpositive-volume"]
            return ValidationReport(
                ok=not bad,
                checks={"method": "exact-edge-pairing",
                        "faces": len(shape.faces)},
                violations=list(bad))
        if isinstance(shape, DrilledSolid):
            bad = shape.watertight_violations()
            return ValidationReport(
                ok=not bad and shape.volume() > 0,
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
        # ADR-0021: ONE mesher, against the canonical form. Preferring each
        # representation's own `tessellate` was a second implementation of the
        # same question, and measuring the two showed the canonical one is
        # strictly better — not merely equivalent:
        #
        #   cylinder      930.80 -> 931.75      revolve   775.67 -> 776.46
        #   bored boss   2981.21 -> 2982.63     cone      100 tris -> 96
        #
        # every curved shape lands closer to its exact volume, with 0
        # non-manifold edges either way. And several representations' own
        # method does not accept a deflection at all, so the seam fell through
        # to `shape.tessellate()` and the caller's argument was silently
        # DISCARDED — asking a planar solid for a fine mesh got the default.
        return self._via_body("tessellate", shape,
                              lambda b: B.tessellate(b, deflection))

    # -- honest refusals (each names its stage) -------------------------------

    def revolve(self, profile, angle_deg=360.0):
        from forgekernel.quadric import RevolveSolid

        # `!= 360` not `!= 360.0`: whether a revolve is FULL decides whether the
        # result has end caps, so it is topology. Fraction(360) == 360 exactly
        # while the float literal invites a caller passing 359.9999999999999
        if angle_deg != 360:
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
            # NOT a convexity check. A reflex corner's inset is perfectly
            # well defined — two inset lines still meet at a point — so
            # refusing every L-bracket was too strong. What can actually go
            # wrong is the inset SELF-INTERSECTING or escaping the profile
            # where a notch is narrower than 2t, and that is checked on the
            # finished polygon below, where it is a property of the answer
            # rather than a guess about the input.
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
        # validity, checked on the RESULT: same orientation, strictly smaller,
        # simple, and wholly inside the profile it hollows
        in_area2 = _signed_area2(inset)
        if in_area2 <= 0:
            raise ValueError("shell too thick: inset profile collapses")
        if in_area2 >= area2:
            raise ValueError("shell: the inset is not smaller than the profile")
        if not _is_simple(inset):
            raise ValueError(
                "shell(thickness makes the void self-intersect) — K4.2")
        if not all(_point_in_poly(bottom, q) for q in inset):
            raise ValueError("shell(the void escapes the profile) — K4.2")
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
            from forgekernel.quadric import DisjointUnion, DrilledSolid, Sphere

            from forgekernel.quadric import RoundedBox

            if isinstance(shape, (Sphere, RoundedBox)):
                # neither carries a SHARP edge: a sphere has none at all and a
                # rounded box's are already tangent-continuous blends, so
                # "round every sharp edge" has nothing to act on
                return shape

            r = (radius if isinstance(radius, Fraction)
                 else Fraction(str(radius)))
            if isinstance(shape, DrilledSolid):
                # Filleting a planar base yields a RoundedBox, which has no
                # polygon soup left to re-drill against — but it does not need
                # any: each bore is a HOLE through that rounded box, which is
                # the pocket construction with a circular footprint, and its
                # own cap guard is what checks the bore has not been swallowed
                # by a rounded edge. That guard is the reason this is
                # expressible at all; it refuses exactly when the bore's mouth
                # would reach a fillet band, where these are not the faces.
                from forgekernel import body as B
                from forgekernel.quadric import _exact_bbox

                from collections import defaultdict

                out = self.fillet(shape.base, (), radius)
                (_x0, _y0, sz0), (_x1, _y1, sz1) = _exact_bbox(out)
                faces = B.to_body(out).faces
                # Coaxial bores are ONE stepped void, not several independent
                # ones — the same grouping from_drilled does. Cutting them
                # separately would punch the wider mouth into a cap that
                # already carries the narrower one and leave the shoulder
                # unbuilt.
                groups = defaultdict(list)
                for c in shape.bores:
                    groups[(Fraction(c.cx), Fraction(c.cy))].append(c)
                for (cx, cy), cyls in groups.items():
                    zs = sorted({z for c in cyls
                                 for z in (max(Fraction(c.z0), sz0),
                                           min(Fraction(c.z1), sz1))})
                    bands = []
                    for za, zb in zip(zs, zs[1:]):
                        mid = (za + zb) / 2
                        rs = [Fraction(c.r) for c in cyls
                              if Fraction(c.z0) <= mid <= Fraction(c.z1)]
                        if rs:
                            bands.append((za, zb, max(rs)))
                    if not bands:
                        continue                  # this stack misses in z
                    if any(bands[i][1] != bands[i + 1][0]
                           for i in range(len(bands) - 1)):
                        _nope("fillet(drilled solid: a coaxial stack with a "
                              "gap is two voids, not one)", "K2.1")
                    faces = _bore_stack_into_body(faces, cx, cy, bands,
                                                  sz0, sz1).faces
                return _audited(B.Body(faces), "fillet(drilled solid)")
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

    def _pocket_rounded(self, a, tool):
        """Cut an axis-aligned tool into a rounded box, whose flats are
        ordinary planes -- nothing about the fillets participates as long as
        the mouth stays clear of them."""
        from forgekernel import body as B
        from forgekernel.brep import Solid
        from forgekernel.quadric import Cyl, RoundedBox, _exact_bbox

        if not isinstance(a, RoundedBox):
            return None
        tb = _exact_bbox(tool)
        if tb is None:
            return None
        (tx0, ty0, tz0), (tx1, ty1, tz1) = tb
        if isinstance(tool, Cyl):
            foot = ("circle", tool.cx, tool.cy, tool.r)
        elif isinstance(tool, Solid) and _is_axis_box(self, tool, tb):
            foot = ("rect", tx0, ty0, tx1, ty1)
        else:
            return None
        (sx0, sy0, sz0), (sx1, sy1, sz1) = _exact_bbox(a)
        za, zb = max(tz0, sz0), min(tz1, sz1)
        if za >= zb:
            return None
        open_bot, open_top = za == sz0, zb == sz1
        if not (open_bot or open_top):
            _nope("boolean.cut(a pocket open at neither end is an internal "
                  "cavity)", "K2.2")
        # Open at BOTH ends is a HOLE, not a split. That refusal read the two
        # cases as one; a slot reaching the boundary would indeed cut the part
        # in two, but a footprint strictly inside both flats — which the cap
        # guard already insists on — leaves it exactly as connected as a
        # drilled plate. Same faces, two mouths and no floor.
        return _pocket_into_body(B.to_body(a).faces, foot, za, zb, open_top,
                                 through=open_bot and open_top)

    def _pocket_lathe(self, a, tool):
        """Cut an axis-aligned rectangular prism into a solid of revolution."""
        from forgekernel.brep import Solid
        from forgekernel.quadric import _exact_bbox

        if not isinstance(tool, Solid):
            return None
        prof, cx, cy = self._lathe_profile(a)
        if prof is None:
            return None
        bb = _exact_bbox(tool)
        if bb is None:
            return None
        (x0, y0, z0), (x1, y1, z1) = bb
        if not _is_axis_box(self, tool, bb):
            return None                       # not a solid axis-aligned box
        zs = [z for _r, z in prof]
        zmin, zmax = min(zs), max(zs)
        za, zb = max(z0, zmin), min(z1, zmax)
        if za >= zb:
            return None                       # misses in z: not our case
        open_top, open_bot = zb == zmax, za == zmin
        if not (open_top or open_bot):
            _nope("boolean.cut(a pocket open at neither end is an internal "
                  "cavity)", "K2.2")
        if open_top and open_bot:
            _nope("boolean.cut(a prism open at both ends splits the lathe)",
                  "K2.2")
        # the footprint must stay strictly inside the material over [za, zb],
        # or the prism breaks out through a wall and the faces are not these
        far2 = max((x - cx) ** 2 + (y - cy) ** 2
                   for x in (x0, x1) for y in (y0, y1))
        # The material radius over [za, zb] is NOT the same as the profile's
        # VERTEX radii there: on a cone the wall shrinks between vertices, and
        # a vertex outside the range still bounds the material inside it. Walk
        # every profile EDGE, clip it to the range, and take the true minimum
        # over both walls — otherwise the guard over-estimates the material and
        # accepts a prism that breaks straight out through the side.
        walls = []
        n = len(prof)
        for i in range(n):
            (r1, w1), (r2, w2) = prof[i], prof[(i + 1) % n]
            if w1 == w2 or (r1 == 0 and r2 == 0):
                # a disk bounds nothing radially, and the AXIS is not a wall —
                # excluding it by value (r > 0) also dropped a wall tapering to
                # zero, so exclude it by TYPE and keep genuine zeros in
                continue
            lo_, hi_ = (w1, w2) if w1 < w2 else (w2, w1)
            ca, cbz = max(lo_, za), min(hi_, zb)
            if ca > cbz:
                continue
            for zz in (ca, cbz):
                walls.append(r1 + (r2 - r1) * (zz - w1) / (w2 - w1))
        if not walls or far2 >= min(w * w for w in walls):
            # `w > 0` used to drop a wall TAPERING TO ZERO, so a pocket
            # spanning a cone's apex was accepted — and with no cap at that z
            # its mouth was never punched, returning an OPEN shell as a solid
            import math as _m

            thinnest = min(walls) if walls else 0
            corner = _m.sqrt(float(far2))
            # the tool's corner is the binding constraint, so the width that
            # fits is the inscribed square of the thinnest wall
            fits = float(thinnest) * _m.sqrt(2)
            _nope("boolean.cut(the prism reaches the lathe's wall)", "K2.2",
                  predicate="prism_inside_material",
                  measured={"tool_corner_radius": corner,
                            "thinnest_wall_radius": float(thinnest),
                            "z_range": [float(za), float(zb)]},
                  remedy=(f"the tool's corner reaches r={corner:.4g} where the "
                          f"wall is only r={float(thinnest):.4g}; a square tool "
                          f"up to {fits:.4g} mm across fits, or keep it clear "
                          "of this z range"))
        pairs = list(zip(prof, prof[1:] + prof[:1]))
        if not any(r1 == 0 and r2 == 0 and min(w1, w2) <= za
                   and max(w1, w2) >= zb for (r1, w1), (r2, w2) in pairs):
            # the minimum above is over BOTH walls, so on a tube it is the
            # BORE radius and any footprint fitting inside the bore passed —
            # "removing" 20 mm^3 of air, and leaving the shell open
            _nope("boolean.cut(the prism's column is not solid to the axis: a "
                  "coaxial bore runs through it)", "K2.2")
        return _pocket_lathe_body(prof, cx, cy, (x0, y0, x1, y1), za, zb,
                                  open_top)

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
        approximation, and the metrics stay exact. Only CONVEX corners are cut
        (a concave one is an internal step, where a chamfer would add material
        rather than remove it), and never a corner on the axis, which is not an
        edge of the solid at all.

        WHICH FIELD THE ANSWER LIVES IN. The corner is set back by ``d`` ALONG
        each adjacent edge, so the new vertex is ``p ± d·(dr, dz)/L`` with
        ``L = √(dr²+dz²)``. This used to demand a RATIONAL ``L``
        (``_rational_sqrt``), which refused every slanted profile — a cone's
        (−4, 10) slant has ``L = 2√29``. That was one step too strong. The
        setback ``d/L`` is a rational over a surd, and ℚ[√e] is a FIELD:
        ``1/√e = √e/e`` is always back inside it. ONE slant therefore costs
        exactly one radical and the whole chamfered profile stays in ℚ[√e],
        which ``F()`` carries through the B-rep untouched (ADR-0019 — these are
        exact values, not floats).

        What is genuinely out of reach is TWO slants whose lengths have
        different square-free parts: the profile then needs the biquadratic
        ℚ[√d₁, √d₂], which ``SurdVal`` does not hold, and it refuses by name
        rather than letting ``SurdVal`` raise a bare ``ValueError`` through the
        seam. This is the same gate ``_gate_slanted_profile`` applies to the
        shell path, for the same reason.
        """
        from forgekernel.body import _as_fraction
        from forgekernel.quadric import RevolveSolid
        from forgekernel.surd import exact_sqrt

        prof, cx, cy = self._lathe_profile(shape)
        if prof is None:
            return None
        n = len(prof)
        area2 = sum(prof[i][0] * prof[(i + 1) % n][1]
                    - prof[(i + 1) % n][0] * prof[i][1] for i in range(n))
        turn = 1 if area2 > 0 else -1

        # PASS ONE: which corners are cut, and what radicals they cost. The
        # field has to be settled for the WHOLE profile before any vertex is
        # emitted — deciding it corner by corner would build half a profile in
        # ℚ[√29] and then discover the next corner wants ℚ[√5].
        cuts: dict[int, tuple] = {}
        radicals: set[int] = set()
        for i in range(n):
            p0, p1, p2 = prof[i - 1], prof[i], prof[(i + 1) % n]
            a = (p1[0] - p0[0], p1[1] - p0[1])
            b = (p2[0] - p1[0], p2[1] - p1[1])
            cross = a[0] * b[1] - a[1] * b[0]
            # multiplication, never `** 2`: SurdVal has no `__pow__`, and an
            # already-surd profile (a chamfered cone re-chamfered) would die
            # with a bare TypeError out of the seam
            la2 = a[0] * a[0] + a[1] * a[1]
            lb2 = b[0] * b[0] + b[1] * b[1]
            if p1[0] == 0 or cross * turn <= 0 or not la2 or not lb2:
                continue
            if d * d * 4 > la2 or d * d * 4 > lb2:
                _nope("chamfer(distance exceeds half the profile edge)", "K5.2")
            qa, qb = _as_fraction(la2), _as_fraction(lb2)
            if qa is None or qb is None:
                # the profile is ALREADY in ℚ[√e] and this edge's squared
                # length did not come back rational, so its length is a root
                # of a quartic — outside SurdVal either way
                _nope("chamfer(profile edge whose squared length has left ℚ)",
                      "K3.1 (a bigger number field)")
            ka, kb = exact_sqrt(qa), exact_sqrt(qb)
            radicals.update(r for r in (getattr(ka, "d", 1),
                                        getattr(kb, "d", 1)) if r != 1)
            cuts[i] = (a, b, ka, kb)
        if len(radicals) > 1:
            names = ", ".join(f"√{r}" for r in sorted(radicals))
            _nope(f"chamfer(two different slant radicals in one lathe "
                  f"profile: {names})", "K3.1 (a bigger number field)",
                  predicate="one_radical_per_profile",
                  measured={"radicals": sorted(radicals)},
                  remedy=("the chamfered profile would live in ℚ[√d₁, √d₂], "
                          "which is biquadratic; make the slants share a "
                          "taper, or give one a Pythagorean (rational-length) "
                          "slope"))

        out = []
        for i in range(n):
            if i not in cuts:
                out.append(prof[i])
                continue
            p1 = prof[i]
            a, b, ka, kb = cuts[i]
            out.append((p1[0] - a[0] * d / ka, p1[1] - a[1] * d / ka))
            out.append((p1[0] + b[0] * d / kb, p1[1] + b[1] * d / kb))
        return _audited(RevolveSolid(out, cx, cy), "chamfer(lathe profile)")

    def chamfer(self, shape, edges, distance):
        from forgekernel.kernel import chamfer as fk_chamfer

        if not edges:
            from forgekernel.brep import Solid
            from forgekernel.quadric import DisjointUnion, DrilledSolid

            d = (distance if isinstance(distance, Fraction)
                 else Fraction(str(distance)))
            from forgekernel.quadric import Sphere

            from forgekernel.quadric import RoundedBox

            if isinstance(shape, (Sphere, RoundedBox)):
                return shape        # no sharp edge to bevel
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
            # EXACTLY, on both counts: which axis an edge runs along and which
            # bbox face its midpoint lies on together decide WHICH EDGES get
            # chamfered, and that is topology. `> 1e-12` and `< 1e-9` were
            # tolerances standing in for tests that are exact over ℚ and ℚ[√d]
            # alike — the direction and the bounds are exact to begin with.
            axes = [i for i in range(3) if e["dir"][i] != 0]
            if len(axes) != 1:
                _nope("chamfer(non-axis-aligned edge)", "K5.2 (general blends)")
            ea = axes[0]
            eb, ec = (i for i in range(3) if i != ea)
            mid = _edge_midpoint(e)

            def _snap(val, loi, hii):
                if val == loi:
                    return loi, 1
                if val == hii:
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
        """Inset an (r, z) lathe profile inward by t, exactly.

        Edges lying ON the axis are not faces of the solid at all and are never
        offset — insetting them would put a solid core inside the void. Every
        other edge moves t along its own inward normal, and the offset VERTEX
        is where the two moved lines meet (``_inset_profile_exact``).

        Axis-aligned edges keep this in ℚ. A SLANTED edge does not: its inward
        normal carries 1/√(dr²+dz²), so the offset vertices land at irrational
        radii and the void lives in ℚ[√d]. That is now expressible — F() was
        widened to carry an exact ℚ[√d] value through the B-rep untouched — but
        only under two gates, both applied here:

        * ONE radical. Two slants with different dr²+dz² put the profile in
          ℚ[√d₁, √d₂], a biquadratic field ``SurdVal`` does not hold.
        * CONVEX. The mitre is the CAD shell everywhere, and it is also the
          true erosion (offset-by-a-ball) only where the profile is convex; at
          a reflex corner the erosion carries an arc of radius t about the
          vertex, which is a genuine K4.2 offset surface. The rectilinear path
          has always shipped the mitre for reflex corners and keeps doing so —
          this gate applies only where a slant makes it NEW capability, so that
          the answers this closes are ones two independent derivations agree on.
        """
        # A REDUNDANT collinear vertex has two identical edge normals, so
        # summing per-edge moved it 2t instead of t — and a cosmetic extra
        # point in the profile silently changed the reported volume of
        # identical geometry by 20%. Drop them before offsetting.
        prof = _drop_collinear_2d(prof)
        _gate_slanted_profile(prof)
        try:
            out = _inset_profile_exact(prof, t)
        except ValueError as exc:
            # SurdVal raises on mixed radicals; the mitre solve raises on a
            # degenerate (parallel) corner. Both are honest gaps, not crashes.
            _nope(f"shell(lathe profile: {exc})", "K4.2 (offset surfaces)")
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

    def _shell_rounded(self, shape, t):
        """Hollow a rounded box. The inward offset is EXACT, by construction.

        A rounded box is a Minkowski sum: ``core ⊕ ball(r)``, where the core is
        the box of dimensions ``(a−2r, b−2r, c−2r)``. Eroding a convex Minkowski
        sum by ``ball(t)`` just takes it back off the ball —

            (core ⊕ B_r) ⊖ B_t  =  core ⊕ B_{r−t}     for t ≤ r
                                =  core ⊖ B_{t−r}     for t > r

        — so the void is another rounded box on the SAME core, and both cases
        collapse to overall dimensions ``(a−2t, b−2t, c−2t)`` with ball radius
        ``max(r−t, 0)``. Nothing is approximated and no surface is offset
        numerically, which is why this one is expressible where the general
        K4.2 offset is not: past ``t = r`` the corners simply go sharp.

        This is the same shape as the hollow-sphere case above — outer faces,
        plus the void's faces turned inside out.
        """
        from forgekernel import body as B
        from forgekernel.brep import Solid
        from forgekernel.kernel import translate
        from forgekernel.quadric import RoundedBox

        if not isinstance(shape, RoundedBox):
            return None
        a, b, c, r = shape.a, shape.b, shape.c, shape.r
        ox, oy, oz = shape.origin
        ia, ib, ic = a - 2 * t, b - 2 * t, c - 2 * t
        if min(ia, ib, ic) <= 0:
            smallest = min(a, b, c)
            _nope("shell(thickness leaves no cavity in the rounded box)",
                  "K4.2", predicate="cavity_is_positive",
                  measured={"dimensions": [float(a), float(b), float(c)],
                            "thickness": float(t)},
                  remedy=(f"t must be under {float(smallest) / 2:.4g} mm — half "
                          f"the smallest dimension ({float(smallest):.4g}) — or "
                          "the walls meet and there is nothing to hollow"))
        if t < r:
            void = RoundedBox(ia, ib, ic, r - t,
                              origin=(ox + t, oy + t, oz + t))
        else:
            # the ball is used up: the cavity is a sharp-cornered box
            void = translate(Solid.box(ia, ib, ic), ox + t, oy + t, oz + t)
        return _audited(B.Body(B.to_body(shape).faces
                      + tuple(B.Face(f.surface, f.loops, not f.sense)
                              for f in B.to_body(void).faces)), "shell(hollow sphere)")

    def _shell_drilled(self, shape, t):
        """Hollow a drilled solid, COLLAR AND ALL, or return None.

        Shell offsets every boundary face inward by t. A bore's cylindrical
        wall is a boundary face, so the void must stop r+t from the axis and a
        tube of metal is left around the hole. That is the whole difference
        from "shell the base then re-drill", which built no tube and was
        silently 170 mm³ light on a plate with one blind bore.

        Exactly expressible while every bore goes STRAIGHT THROUGH: the void is
        then the inset base minus the enlarged cylinders — an intersection of
        two eroded sets, so its corners stay sharp and no new surface type
        appears. A BLIND bore is different in kind: eroding around its floor's
        reentrant rim sweeps a torus, which is a K4.2 offset and not this.
        """
        from forgekernel import body as B
        from forgekernel.brep import Solid
        from forgekernel.kernel import translate
        from forgekernel.quadric import Cyl, DrilledSolid

        box = self._box_check(shape.base)
        if box is None:
            return None                 # a general prism base: K4.1's inset
        (bx0, by0, bz0), (bx1, by1, bz1) = box
        blind = [c for c in shape.bores
                 if Fraction(c.z0) > bz0 or Fraction(c.z1) < bz1]
        if blind:
            _nope("shell(drilled solid: a BLIND bore's floor erodes to a "
                  "torus, not a cylinder)", "K4.2 (offset surfaces)",
                  predicate="every_bore_is_through",
                  measured={"solid_z": [float(bz0), float(bz1)],
                            "blind_bores": [{"xy": [float(c.cx), float(c.cy)],
                                             "r": float(c.r),
                                             "z": [float(c.z0), float(c.z1)]}
                                            for c in blind]},
                  remedy=(f"{len(blind)} bore(s) stop inside the material; take "
                          f"them through z {float(bz0):.4g}..{float(bz1):.4g} "
                          "and the collar is exact, or shell before drilling"))
        smallest = min(bx1 - bx0, by1 - by0, bz1 - bz0)
        if smallest <= 2 * t:
            _nope("shell(thickness leaves no cavity)", "K4.2",
                  predicate="cavity_is_positive",
                  measured={"smallest_dimension": float(smallest),
                            "thickness": float(t)},
                  remedy=(f"t must be under {float(smallest) / 2:.4g} mm — half "
                          "the smallest dimension"))
        inner = translate(Solid.box(bx1 - bx0 - 2 * t, by1 - by0 - 2 * t,
                                    bz1 - bz0 - 2 * t),
                          bx0 + t, by0 + t, bz0 + t)
        void = DrilledSolid(inner, [])
        try:
            for c in shape.bores:
                # the collar: the void keeps t clear of the bore's wall.
                # DrilledSolid.cut is what checks the enlarged cylinder still
                # fits inside the cavity and clears its neighbours, so a collar
                # that would break out refuses there rather than here.
                void = void.cut(Cyl(c.cx, c.cy, Fraction(c.r) + t,
                                    bz0 + t, bz1 - t))
        except ValueError as exc:
            _nope(f"shell(drilled solid: the collar does not fit — {exc})",
                  "K4.2")
        return _audited(B.Body(B.to_body(shape).faces
                      + tuple(B.Face(f.surface, f.loops, not f.sense)
                              for f in B.to_body(void).faces)), "shell(rounded box)")

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
        return _audited(B.Body(B.to_body(shape).faces
                      + tuple(B.Face(f.surface, f.loops, not f.sense)
                              for f in void.faces)), "shell(drilled solid)")

    def shell(self, shape, remove_faces, thickness):
        from forgekernel.brep import Solid
        from forgekernel.kernel import shell as fk_shell

        if not isinstance(shape, Solid) and not remove_faces:
            from forgekernel.quadric import DisjointUnion, DrilledSolid

            t = (thickness if isinstance(thickness, Fraction)
                 else Fraction(str(thickness)))
            if isinstance(shape, DrilledSolid):
                if shape.bores:
                    coll = self._shell_drilled(shape, t)
                    if coll is not None:
                        return coll
                    # SHELLING A DRILLED SOLID NEEDS A COLLAR. Shell offsets
                    # every boundary face inward by t, and the bore's own
                    # cylindrical wall is a boundary face: the void must stop
                    # r+t from the axis, leaving a tube of metal around the
                    # hole. "Shell the base, then re-drill" builds no such
                    # tube, and it was not refusing — a 30x30x10 plate with a
                    # blind Ø4 bore in its top wall, shelled t=2, reported
                    # 4918.867 where the truth is 5088.81 +- 6.69 (4M-sample
                    # Monte Carlo): 170 mm3 of collar that is simply absent.
                    # The old guard only caught bores that reached the cavity,
                    # and even those it blamed on the barrel arithmetic.
                    _nope("shell(drilled solid: the bore's own wall must be "
                          "offset too, which needs a collar this kernel does "
                          "not build yet)", "K4.2 (offset surfaces)")
                return DrilledSolid(self.shell(shape.base, (), thickness), [])
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
            from forgekernel.quadric import Sphere

            if isinstance(shape, Sphere):
                # a hollow ball: the void is the concentric sphere t smaller,
                # turned inside out. Exact at (4/3)pi(R^3 - (R-t)^3).
                from forgekernel import body as B

                inner = Sphere(shape.cx, shape.cy, shape.cz, shape.r - t)
                if inner.r <= 0:
                    _nope("shell(thickness exceeds the sphere's radius)", "K4.2")
                void = B.to_body(inner)
                return _audited(B.Body(B.to_body(shape).faces
                              + tuple(B.Face(f.surface, f.loops, not f.sense)
                                      for f in void.faces)), "shell(lathe)")
            rounded = self._shell_rounded(shape, t)
            if rounded is not None:
                return rounded
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
        """K7.0c: native AP214 export — OCCT-free CAD exchange.

        EVERY representation goes through the canonical B-rep writer. Planar
        solids and drilled solids used to take a second writer of their own,
        and the two disagreed about the one thing a solid model has to get
        right: ``write_step_body`` folds ``ADVANCED_FACE``'s same_sense flag
        into an edge's traversal, ``write_step_planar_solid`` does not. Under
        either rule one family of files was invalid, and a shelled box went out
        as a MANIFOLD_SOLID_BREP over a shell with 16 of its 56 edges used by
        exactly one face — dangling on both conventions.

        Folding same_sense is the correct reading (the flag is precisely what
        relates the face's orientation to its surface's), and the canonical
        writer audits itself before emitting, so a defect refuses instead of
        shipping a file that opens and then will not boolean or mesh for CAM.
        """
        from forgekernel.stepbody import write_step_body

        text = self._via_body("export_step", shape,
                              lambda b: write_step_body(b))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

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


def _profile_edge_normal(qa, qb):
    """One (r, z) profile edge as (inward normal DIRECTION, its exact length),
    or ``None`` where the edge is not a face of the solid at all.

    For a counter-clockwise profile the interior lies to the left, so an edge
    travelling ``(dr, dz)`` has inward normal ``(-dz, dr)/√(dr²+dz²)``. The
    direction is handed back UNNORMALISED with the length beside it, because
    the mitre solve wants them apart: dividing here would put the root into
    every coefficient of the 2×2 system instead of only its right-hand side,
    and the determinant would leave ℚ for no reason.

    An edge with both ends on r = 0 IS the axis — a symmetry line, not a
    boundary face. Offsetting it would push a solid core into the void.
    """
    from forgekernel.surd import exact_sqrt

    dr, dz = qb[0] - qa[0], qb[1] - qa[1]
    if (qa[0] == 0 and qb[0] == 0) or (dr == 0 and dz == 0):
        return None
    return (-dz, dr), exact_sqrt(dr * dr + dz * dz)


def _inset_profile_exact(prof, t):
    """Move every face of an (r, z) profile t along its own inward normal, and
    put each vertex where its two moved lines cross. Exact throughout.

    The condition at a vertex is ``s·n₁ = s·n₂ = t`` for the two adjacent
    inward UNIT normals. Writing ``nᵢ = uᵢ/Lᵢ`` clears the roots out of the
    matrix and leaves them only on the right:

        u₁·s = t·L₁ ,   u₂·s = t·L₂

    which Cramer solves with a rational determinant. Adding the two unit
    normals — what the rectilinear inset did — satisfies this only when
    ``n₁·n₂ = 0``, since ``(t(n₁+n₂))·n₁ = t(1 + n₁·n₂)``: on a right-angled
    corner the two rules agree exactly, so no rectilinear answer moves, and on
    the slant of cone(6,2,10) the old rule would have left a 0.6285 mm wall
    where 1 mm was asked for.

    A vertex ON the axis has one real neighbour and one axis edge. The axis is
    not a face, so there is no second offset line — the vertex slides ALONG the
    axis instead, which is the constraint ``s·(1,0) = 0``. For a rectilinear
    profile that reproduces ``(0, z ± t)``; for a cone's apex it keeps the
    eroded apex on the axis, where summing the one available normal would have
    thrown it off to the side.
    """
    n = len(prof)
    edges = [_profile_edge_normal(prof[i], prof[(i + 1) % n]) for i in range(n)]
    out = []
    for i in range(n):
        rows = [(e[0], t * e[1]) for e in (edges[i - 1], edges[i])
                if e is not None]
        if not rows:                     # two axis edges meeting: nothing moves
            out.append(prof[i])
            continue
        if len(rows) == 1:
            rows.append(((Fraction(1), Fraction(0)), Fraction(0)))
        (a1, b1), (a2, b2) = rows
        det = a1[0] * a2[1] - a1[1] * a2[0]
        if det == 0:
            raise ValueError(
                "a corner whose two faces are parallel has no mitre point")
        out.append((prof[i][0] + (b1 * a2[1] - b2 * a1[1]) / det,
                    prof[i][1] + (a1[0] * b2 - a2[0] * b1) / det))
    return out


def _gate_slanted_profile(prof) -> None:
    """Refuse, by name, the SLANTED-edge offsets that are not expressible or
    not provably the same solid as the true shell. A rectilinear profile has
    neither problem and returns immediately, so this changes nothing shipped.

    Two gates:

    * ONE RADICAL. A slant of length √d puts the offset profile in ℚ[√d].
      Two slants with different square-free parts need ℚ[√d₁, √d₂] — a
      biquadratic field ``SurdVal`` does not hold, and floating one of the two
      roots to get past it is exactly the trade ADR-0019 forbids. A Pythagorean
      slant (3-4-5) has a RATIONAL length and costs no radical at all.
    * CONVEX. The mitre is what a CAD shell means — offset the faces, extend
      them to meet — and where the profile is convex it is also the erosion
      (offset by a ball) and so agrees with the Monte-Carlo oracle the exact
      answer is checked against. At a REFLEX corner the two part company: the
      erosion carries an arc of radius t about the vertex. The rectilinear path
      has always shipped the mitre there and keeps doing so; a slant makes the
      corner new capability, and new capability only lands where two
      independent derivations agree.
    """
    n = len(prof)
    radicals = set()
    slanted = False
    for i in range(n):
        e = _profile_edge_normal(prof[i], prof[(i + 1) % n])
        if e is None:
            continue
        (ur, uz), ln = e
        if ur != 0 and uz != 0:
            slanted = True
            radicals.add(getattr(ln, "d", 1))
    radicals.discard(1)                       # a rational slant length is free
    if not slanted:
        return
    if len(radicals) > 1:
        names = ", ".join(f"√{d}" for d in sorted(radicals))
        _nope(f"shell(two different slant radicals in one lathe profile: "
              f"{names})", "K3.1 (a bigger number field)",
              predicate="one_radical_per_profile",
              measured={"radicals": sorted(radicals)},
              remedy=("the offset profile would live in ℚ[√d₁, √d₂], which is "
                      "biquadratic; make the slants share a taper, or give one "
                      "a Pythagorean (rational-length) slope"))
    turns = set()
    for i in range(n):
        a, b, c = prof[i - 1], prof[i], prof[(i + 1) % n]
        cross = ((b[0] - a[0]) * (c[1] - b[1])
                 - (b[1] - a[1]) * (c[0] - b[0]))
        if cross != 0:
            turns.add(cross > 0)
    if len(turns) > 1:
        _nope("shell(a reflex corner beside a slanted lathe profile edge)",
              "K4.2 (offset surfaces)", predicate="slanted_profile_is_convex",
              measured={"profile": [(float(r), float(z)) for r, z in prof]},
              remedy=("the true offset rounds a reflex corner with an arc of "
                      "radius t rather than mitring it; split the profile at "
                      "the reflex vertex, or keep the slant on a convex part"))


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


def _point_strictly_in_poly(poly, q) -> bool:
    """Exact, and STRICT: a point on the boundary is not inside.

    ``_point_in_poly`` is a crossing-parity test, which is half-open — it is
    inclusive on the min-x/min-y edges and exclusive on the others. That makes
    it MIRROR-ASYMMETRIC: a pocket tangent to its flat's boundary is accepted on
    two sides and refused on the other two, and the same part rotated 180° about
    z builds or refuses depending on which way it landed. Where the answer means
    "the mouth is clear of every other face", tangency is not clear, so the
    boundary has to be excluded on all four sides and by name.

    Exact throughout: no division and no ``float()``, so ℚ and ℚ[√d] coordinates
    both decide this the same way. The float version silently rounded the cap's
    own corner, which at large magnitudes let a mouth a full millimetre outside
    the flat through (ADR-0019: a float must never decide topology).
    """
    px, py = q
    n = len(poly)
    inside = False
    for i in range(n):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
        # cross > 0 <=> q is left of a->b; == 0 <=> q is on the carrier line
        cr = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
        if cr == 0 and (px - ax) * (px - bx) <= 0 and (py - ay) * (py - by) <= 0:
            return False                       # on the boundary: not strict
        if (ay > py) != (by > py) and (cr > 0) == (by > ay):
            inside = not inside
    return inside


def _disc_misses_solid(solid, cx, cy, r) -> bool:
    """Does the disc (cx, cy, r) miss the solid's xy shadow entirely? EXACT.

    A closed solid's shadow is the shadow of its BOUNDARY — every point over
    the shadow's interior has a face above it — so projecting every poly and
    testing the disc against each covers the whole footprint. A side wall
    projects to a segment, which the edge-distance test handles as written.

    Rational throughout: the closest point on a segment is a clamped ratio and
    the comparison is against r², so nothing is rounded and ℚ[√d] coordinates
    from an exact rotation decide it the same way.
    """
    r2 = r * r
    for pp in solid.polys:
        ring = [(v[0], v[1]) for v in pp.verts]
        if len(ring) >= 3 and _point_in_poly(ring, (cx, cy)):
            return False
        for i in range(len(ring)):
            (ax, ay), (bx, by) = ring[i], ring[(i + 1) % len(ring)]
            dx, dy = bx - ax, by - ay
            den = dx * dx + dy * dy
            if den == 0:
                qx, qy = ax, ay
            else:
                t = ((cx - ax) * dx + (cy - ay) * dy) / den
                t = min(max(t, 0 * t), 1 + 0 * t)      # clamp, type-preserving
                qx, qy = ax + t * dx, ay + t * dy
            # multiplication, never `** 2`: SurdVal has no __pow__, and an
            # exactly-rotated solid raised a raw TypeError straight out of the
            # seam — the capability matrix calls a bare exception a defect
            # however honest the refusal it replaced would have been
            ex, ey = cx - qx, cy - qy
            if ex * ex + ey * ey <= r2:
                return False
    return True


def _is_axis_box(kernel, shape, bb) -> bool:
    """Is ``shape`` exactly the axis-aligned box ``bb``? By its POINT SET.

    Two screens were tried here and both were unsound, in the same way: they
    tested a PROPERTY the box has instead of testing the set.

      * ``volume() == dx*dy*dz`` — ``Solid.volume()`` is additive over polys, so
        a compound whose overlap exactly pays for its gap passes. An L of two
        boxes has area 14 in a 4x4 bbox and volume 4*4*4; cut into a rounded box
        it removed 48 mm³ where the truth is 42.
      * ``_box_check`` (every vertex at a bbox corner) ∧ the volume — that only
        forbids INTERIOR vertices. Two triangular wedges spanning the same
        corners, ``[(4,3),(8,3),(8,7)]`` and ``[(4,3),(8,3),(4,7)]`` extruded
        together, have six vertices all at bbox corners and volume 4*4*4 while
        covering 12 of the 16 mm². The pocket removed 64 where 48 exists — 38σ
        against Monte Carlo, mesh watertight, ``validate()`` ok. It also
        REFUSED an ordinary box whose bottom edge carried a midpoint vertex,
        which every sketch that splits an edge produces.

    So ask the question directly: the symmetric difference against the box must
    be empty, both ways, on the exact planar engine. A property test can always
    be satisfied by something that is not the thing.
    """
    from forgekernel.brep import Solid
    from forgekernel.kernel import translate

    (x0, y0, z0), (x1, y1, z1) = bb
    if shape.volume() != (x1 - x0) * (y1 - y0) * (z1 - z0):
        return False                          # cheap screen before the booleans
    box = translate(Solid.box(x1 - x0, y1 - y0, z1 - z0), x0, y0, z0)
    try:
        return (kernel._fk.boolean("cut", box, shape).volume() == 0
                and kernel._fk.boolean("cut", shape, box).volume() == 0)
    except (ArithmeticError, ValueError, TypeError, IndexError):
        return False                          # not a shape the engine can settle


def _fillet_profile(prof, r):
    """Round every convex RIGHT-ANGLE corner of an (r, z) profile.

    Returns segments: ``("line", p0, p1)`` and ``("arc", centre, p0, p1)``.
    Only right angles between axis-aligned edges — the tangent points and the
    arc centre are then rational, and revolving the arc sweeps exactly a
    QUARTER of a torus tube, which is what keeps the volume in ℚ[π].

    WHY THE RIGHT ANGLE IS NOT A CONVENIENCE. Revolving an arc of radius R
    about the axis contributes, to ∮r²dz,

        ∫(c_r + R cos t)² · R cos t dt
          = R c_r² sin t + c_r R² (t + sin t cos t) + R³(sin t − sin³t/3)

    and that lone ``t`` is the whole story: the volume carries the arc's TURN
    ANGLE linearly, with coefficient ``c_r R²``. A fillet's arc centre sits a
    distance ``R`` inside the material, so ``c_r ≠ 0`` always (the one family
    where it vanishes is an arc centred ON the axis — a sphere's meridian,
    which is why ``contour_r2_dz`` takes those and only those). The turn angle
    is ``π − φ`` for an interior angle ``φ``, so the answer is in ℚ[√d][π] iff
    ``φ`` is a rational multiple of π.

    With rational profile coordinates every edge has rational slope, so
    ``tan φ`` is rational — and by Niven's theorem a rational tangent at a
    rational multiple of π forces ``tan φ ∈ {0, ±1, ∞}``. Right angles and
    45°/135° corners, and nothing else, ever. Every other lathe corner needs
    ``arctan(p/q)``, which is transcendental by Lindemann and which no
    extension of ℚ[√d][π] holds; those refusals are the exact-field boundary,
    not backlog. (ADR-0019: the floats below appear only inside refusal text,
    never in a decision.)
    """
    from forgekernel.body import _as_fraction as _as_fraction_rz

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
        # cos φ and sin φ share the denominator |a||b|, so their NUMERATORS
        # alone decide tan φ — exactly, over ℚ, with no root taken.
        cosnum = -(a[0] * b[0] + a[1] * b[1])
        sinnum = abs(cross)
        diagonal = bool(a[0] and a[1]) or bool(b[0] and b[1])
        # `tan φ ∈ ℚ` is what Niven's theorem needs and what the message
        # quotes. A profile ALREADY in ℚ[√d] — a chamfered cone handed back
        # to fillet — has an algebraic tangent instead, so there is no ratio
        # to name and the ℚ-only argument does not apply. Refuse there too,
        # by a different name: formatting a Fraction from a SurdVal threw a
        # bare TypeError straight through the seam.
        qcos, qsin = _as_fraction_rz(cosnum), _as_fraction_rz(sinnum)
        if qcos is None or qsin is None:
            _nope("fillet(lathe corner whose tangent has left ℚ: the profile "
                  "already carries a radical, so Niven's rational-tangent "
                  "argument does not settle the turn angle)", "K5.2")
        cosnum, sinnum = qcos, qsin
        if cosnum != 0 and sinnum != abs(cosnum):
            import math as _math

            tan_phi = Fraction(sinnum, cosnum)
            _nope(f"fillet(lathe corner with tan φ = {tan_phi}: its arc turns "
                  f"through π−arctan({tan_phi}), and the revolved volume "
                  f"carries that angle linearly, so the answer needs "
                  f"arctan({tan_phi}) — transcendental, outside every "
                  f"ℚ[√d][π])", "K5.2",
                  predicate="lathe_corner_angle_is_a_rational_multiple_of_pi",
                  measured={"corner_rz": [float(p1[0]), float(p1[1])],
                            "tan_phi": [tan_phi.numerator,
                                        tan_phi.denominator],
                            "phi_deg": float(_math.degrees(
                                _math.atan2(float(sinnum), float(cosnum))))},
                  remedy=("only 90° and 45°/135° lathe corners have a turn "
                          "angle in ℚ·π (Niven); chamfer this rim instead — "
                          "a bevel is exact in ℚ[√d] for any slant"))
        if cosnum != 0 or diagonal:
            _nope("fillet(45°/135° lathe corner, or a right angle between two "
                  "diagonal edges: the turn IS a rational multiple of π and "
                  "the blend IS expressible in ℚ[√d][π] — the sweep is simply "
                  "not built yet)", "K5.2")
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
    """Bore a coaxial hole through OR into a lathed profile.

    Through and blind are the same operation on the profile: the region
    [0, r] x [za, zb] is removed from it. A blind bore simply leaves a floor
    where the tool stopped, and the axis below it stays solid — so the result
    is still a closed (r, z) profile and still a solid of revolution. No
    surface-surface intersection either way.
    """
    zs = [z for _r, z in prof]
    zmin, zmax = min(zs), max(zs)
    za, zb = max(zlo, zmin), min(zhi, zmax)
    if za >= zb:
        _nope("boolean.cut(bore misses the lathe in z)", "K2.2")
    n = len(prof)
    for i in range(n):
        (r1, w1), (r2, w2) = prof[i], prof[(i + 1) % n]
        if w1 == w2 or (r1 == 0 and r2 == 0):
            continue                       # a disk / the axis bounds nothing
        lo_, hi_ = (w1, w2) if w1 < w2 else (w2, w1)
        ca, cb = max(lo_, za), min(hi_, zb)
        if ca > cb:
            continue
        for zz in (ca, cb):
            # the wall SHRINKS between vertices, and an APEX (r = 0) is a wall
            # too: excluding it by `r != 0` let a bore through a cone's tip
            # move the wall outward and report MORE volume than the uncut solid
            wall = r1 + (r2 - r1) * (zz - w1) / (w2 - w1)
            if wall < tool_r:
                _nope("boolean.cut(bore is wider than the lathe at some "
                      "height)", "K2.2", predicate="bore_inside_material",
                      measured={"tool_radius": float(tool_r),
                                "wall_radius": float(wall), "at_z": float(zz),
                                "z_range": [float(za), float(zb)]},
                      remedy=(f"at z={float(zz):.4g} the wall is only "
                              f"r={float(wall):.4g}; use a bore of at most that "
                              f"radius, or stop it before that height"))
    if za > zmin and zb < zmax:
        _nope("boolean.cut(a bore open at neither end leaves an internal "
              "cavity)", "K2.2")
    out = []
    n = len(prof)
    for i in range(n):
        r, z = prof[i]
        r2, z2 = prof[(i + 1) % n]
        inside = za <= z <= zb
        out.append((tool_r if (r == 0 and inside) else r, z))
        # where the axis crosses the tool's end, step out to the bore wall and
        # leave the floor behind
        if r == 0 and r2 == 0:
            # RevolveSolid normalises the loop, so the axis always descends and
            # `z > z2` was constant — the direction alone cannot say which way
            # to step. Crossing za (blind from the TOP) and crossing zb (blind
            # from the BOTTOM) need OPPOSITE orders; getting it wrong emitted a
            # "shark fin" that removed pi r^2 H/3 whatever the depth asked for.
            down = z > z2
            for edge in ((zb, za) if down else (za, zb)):
                if min(z, z2) < edge < max(z, z2):
                    step = [(tool_r, edge), (0, edge)]
                    if (edge == za) != down:
                        step.reverse()
                    out.extend(step)
    return out


def _pocket_lathe_body(prof, cx, cy, rect, za, zb, open_top):
    """A solid of revolution with an axis-aligned rectangular POCKET.

    A plane parallel to a lathe's axis meets its cylindrical faces in straight
    LINES and its disks in chords, so a prism pocket needs no conic sections
    and no new surface type — only the topology has to be built: the open
    end's cap gains an inner loop, the prism contributes four planar walls,
    and a blind pocket contributes a floor.
    """
    from fractions import Fraction as Q
    from forgekernel import body as B
    from forgekernel.quadric import RevolveSolid

    x0, y0, x1, y1 = rect
    zc = za if open_top else zb                 # the closed (floor) end
    zo = zb if open_top else za                 # the open end
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def loop_of(pts):
        return B.Loop(tuple(
            B.Edge(B.Line(pts[i], tuple(pts[(i + 1) % len(pts)][k] - pts[i][k]
                                        for k in range(3))),
                   pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))))

    def oriented(pts, n, positive):
        """Wind a polygon so its signed area about n has the wanted sign.

        Guessing this from the corner order is how the first attempt failed:
        an outer loop wound the wrong way reads as NEGATIVE AREA, and the
        exact volume refuses outright rather than quietly halving.
        """
        lp = loop_of(pts)
        a2 = B._planar_loop_area2(lp, n)
        return lp if (a2 > 0) == positive else loop_of(list(reversed(pts)))

    def ring(z, positive, n):
        pts = [(Q(x), Q(y), Q(z)) for x, y in corners]
        return oriented(pts, n, positive)

    faces = []
    src = B.to_body(RevolveSolid(prof, cx, cy)).faces
    caps = [i for i, f in enumerate(src)
            if isinstance(f.surface, B.Plane) and f.surface.n[0] == 0
            and f.surface.n[1] == 0 and B._plane_point(f.surface)[2] == zo]
    if len(caps) != 1:
        # a lathe can have SEVERAL planar faces at one z (an annular groove
        # reaching that end), and punching the mouth into all of them removed
        # 20 where the truth was 12 — with a watertight mesh, so nothing
        # downstream noticed. Zero caps means the open end is an apex.
        _nope(f"boolean.cut(the pocket's open end meets {len(caps)} planar "
              "faces, not exactly one)", "K2.2")
    for i, f in enumerate(src):
        if i == caps[0]:
            # an inner loop winds AGAINST the outer one about the surface
            # normal, whichever way that normal happens to point
            faces.append(B.Face(f.surface,
                                f.loops + (ring(zo, False, f.surface.n),),
                                f.sense))
        else:
            faces.append(f)

    for i in range(4):
        (ax, ay), (bx, by) = corners[i], corners[(i + 1) % 4]
        d = (Q(by - ay), Q(ax - bx), Q(0))       # outward = into the pocket
        pts = [(Q(ax), Q(ay), Q(za)), (Q(bx), Q(by), Q(za)),
               (Q(bx), Q(by), Q(zb)), (Q(ax), Q(ay), Q(zb))]
        n = tuple(-v for v in d)
        faces.append(B.Face(B.Plane(n, sum(n[k] * pts[0][k] for k in range(3))),
                            (oriented(pts, n, True),), True))

    nz = Q(1) if open_top else Q(-1)             # floor faces INTO the pocket
    nvec = (Q(0), Q(0), nz)
    faces.append(B.Face(B.Plane(nvec, Q(zc) * nz),
                        (ring(zc, True, nvec),), True))
    return _audited(B.Body(tuple(faces)), "boolean.cut(lathe pocket)")


def _cap_index_at(src, zo, probe):
    """Index of the one flat face a mouth opens through at ``zo``, guarded.

    The mouth must sit strictly inside that cap, clear of any fillet. The ring
    is taken EXACTLY (no ``float()``) and tested strictly on all four sides —
    see ``_point_strictly_in_poly`` for what each of those was hiding.

    ``probe`` bounds the whole mouth because both footprints are axis-aligned:
    for a rectangle the probes ARE its corners, and for a circle the axis
    extremes do it because a rounded box's flat cap is an axis-aligned
    RECTANGLE. Convexity alone would NOT be enough — a diamond cap
    ``|x| + |y| <= 21/10`` admits a mouth of r = 2 at all four probes while the
    circle escapes at 45° — so the polygon guard here is doing real work, not
    merely excluding arcs.
    """
    from forgekernel import body as B

    hits = [i for i, f in enumerate(src)
            if isinstance(f.surface, B.Plane) and f.surface.n[0] == 0
            and f.surface.n[1] == 0 and B._plane_point(f.surface)[2] == zo]
    if len(hits) != 1:
        _nope(f"boolean.cut(the pocket's open end meets {len(hits)} planar "
              "faces, not exactly one)", "K2.2")
    cap = src[hits[0]]
    if len(cap.loops) != 1 or any(not isinstance(e.curve, B.Line)
                                  for e in cap.loops[0].edges):
        _nope("boolean.cut(the pocket's open end is not a single polygonal "
              "face)", "K2.2")
    ring = [(e.v0[0], e.v0[1]) for e in cap.loops[0].edges]
    outside = [q for q in probe if not _point_strictly_in_poly(ring, q)]
    if outside:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        gap = min(min(q[0] - min(xs), max(xs) - q[0],
                      q[1] - min(ys), max(ys) - q[1]) for q in outside)
        _nope("boolean.cut(the pocket does not sit strictly inside one flat "
              "face)", "K2.2", predicate="mouth_inside_cap",
              measured={"flat": [[float(min(xs)), float(min(ys))],
                                 [float(max(xs)), float(max(ys))]],
                        "outside_probes": [[float(a), float(b)]
                                           for a, b in outside],
                        "clearance": float(gap)},
              # MORE than the clearance, not exactly it: the guard is strict,
              # so moving by precisely this much lands tangent and refuses
              # again. A remedy whose own number does not work is worse than
              # none — it costs the caller a second attempt to discover.
              remedy=(f"move the feature MORE than {float(-gap):.4g} mm further "
                      "from the flat's edge (tangent still refuses), or make "
                      "it smaller by more than twice that — past the flat "
                      "there is a rounded band, not a plane"))
    return hits[0]


def _bore_stack_into_body(src, cx, cy, bands, sz0, sz1):
    """Sink a COAXIAL STACK of circular bores into a body with flat caps.

    ``bands`` is [(za, zb, r), ...] in z order and contiguous — the same form
    ``body.from_drilled`` builds for a counterbore. One cylindrical wall per
    band; a shoulder annulus wherever the radius steps; a mouth in the cap at
    an end that reaches the outside, and a floor disk at one that does not.

    A single band is exactly the circular pocket, so this generalises it rather
    than duplicating it — what it adds is the shoulder, which is why a stepped
    hole needed a construction of its own instead of two independent pockets.
    """
    from fractions import Fraction as Q
    from forgekernel import body as B

    faces = list(src)
    axis = (Q(0), Q(0), Q(1))

    def circ_loop(z, r):
        p = (Q(cx) + Q(r), Q(cy), Q(z))
        return B.Loop((B.Edge(B._circle_at(cx, cy, z, r), p, p),))

    # the stack's two outer ends: each either opens through a cap, or stops
    # inside material and needs a floor of its own (the blind case)
    for z, r, boundary, up in ((bands[0][0], bands[0][2], Q(sz0), True),
                               (bands[-1][1], bands[-1][2], Q(sz1), False)):
        if Q(z) == boundary:
            probe = [(cx + r, cy), (cx - r, cy), (cx, cy + r), (cx, cy - r)]
            i = _cap_index_at(faces, Q(z), probe)
            f = faces[i]
            faces[i] = B.Face(f.surface, f.loops + (circ_loop(z, r),), f.sense)
        else:
            # _disk_face keeps the plane normal at +z and carries the direction
            # in `sense`, which is the convention from_drilled uses and the one
            # the writer's bound orientation is derived against
            faces.append(B._disk_face(cx, cy, z, r, up))

    for za, zb, r in bands:
        rims = tuple(B.Edge(B._circle_at(cx, cy, z, r),
                            (Q(cx) + Q(r), Q(cy), Q(z)),
                            (Q(cx) + Q(r), Q(cy), Q(z))) for z in (Q(za), Q(zb)))
        faces.append(B.Face(B.Cylinder((Q(cx), Q(cy), Q(za)), axis, Q(r)),
                            (B.Loop(rims),), False))      # a bore faces INWARD

    for (_a, zs, r0), (_b, _c, r1) in zip(bands, bands[1:]):
        if r0 == r1:
            continue                                      # no step, no shoulder
        rin, rout = min(r0, r1), max(r0, r1)
        # the exposed ring faces INTO the wider bore
        faces.append(B.Face(B.Plane((Q(0), Q(0), Q(1)), Q(zs)),
                            (circ_loop(zs, rout), circ_loop(zs, rin)),
                            r1 > r0))
    return _audited(B.Body(tuple(faces)), "boolean.cut(bore stack)")


def _pocket_into_body(src, foot, za, zb, open_top, through=False):
    """Sink an axis-aligned pocket into a body that has a FLAT cap at each open
    end. ``foot`` is ("circle", cx, cy, r) or ("rect", x0, y0, x1, y1).

    Exactly the construction a lathe pocket uses, with the source body left
    general: each open end's cap gains the mouth as an inner loop, the tool
    contributes its walls, and a closed end a floor. A rounded box's flats are
    ordinary planes, so nothing about the fillets participates as long as the
    mouth stays clear of them.

    ``through`` opens BOTH ends — a hole rather than a pocket. That was refused
    on the grounds that it "would split the solid", which is only true of a slot
    reaching the boundary: a footprint strictly inside both flats leaves the
    part every bit as connected as a drilled plate is. Same faces, two mouths
    and no floor.
    """
    from fractions import Fraction as Q
    from forgekernel import body as B

    opens = (Q(za), Q(zb)) if through else ((Q(zb),) if open_top else (Q(za),))
    closed = () if through else ((Q(za),) if open_top else (Q(zb),))

    def mouth(z, n, positive):
        if foot[0] == "circle":
            # NO pre-flip. A full-circle loop carries no winding of its own, so
            # its direction is the writer's to decide from the circle's axis
            # against the face's role (outer vs inner) — which is exactly what
            # ``stepbody._oriented_bounds`` does, and what ``from_drilled`` and
            # ``from_revolve`` rely on. Handing it a circle already reversed
            # inverted that decision and emitted the mouth rim running the same
            # way as the bore wall's: 2 non-manifold edges in every circular
            # pocket's STEP file, i.e. a MANIFOLD_SOLID_BREP over an open shell.
            _k, cx, cy, r = foot
            p = (Q(cx) + Q(r), Q(cy), Q(z))
            return B.Loop((B.Edge(B._circle_at(cx, cy, z, r), p, p),))
        _k, x0, y0, x1, y1 = foot
        pts = [(Q(x), Q(y), Q(z)) for x, y in
               ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        lp = B.Loop(tuple(B.Edge(B.Line(pts[i], tuple(
            pts[(i + 1) % 4][k] - pts[i][k] for k in range(3))),
            pts[i], pts[(i + 1) % 4]) for i in range(4)))
        if (B._planar_loop_area2(lp, n) > 0) == positive:
            return lp
        pts.reverse()
        return B.Loop(tuple(B.Edge(B.Line(pts[i], tuple(
            pts[(i + 1) % 4][k] - pts[i][k] for k in range(3))),
            pts[i], pts[(i + 1) % 4]) for i in range(4)))

    probe = ([(foot[1] + foot[3], foot[2]), (foot[1] - foot[3], foot[2]),
              (foot[1], foot[2] + foot[3]), (foot[1], foot[2] - foot[3])]
             if foot[0] == "circle"
             else [(foot[1], foot[2]), (foot[3], foot[2]),
                   (foot[3], foot[4]), (foot[1], foot[4])])

    punched = {_cap_index_at(src, z, probe): z for z in opens}
    faces = []
    for i, f in enumerate(src):
        faces.append(B.Face(f.surface,
                            f.loops + (mouth(punched[i], f.surface.n, False),),
                            f.sense) if i in punched else f)

    for zc in closed:
        nz = Q(1) if open_top else Q(-1)
        fl = (Q(0), Q(0), nz)
        faces.append(B.Face(B.Plane(fl, zc * nz), (mouth(zc, fl, True),), True))

    if foot[0] == "circle":
        _k, cx, cy, r = foot
        axis = (Q(0), Q(0), Q(1))
        rims = tuple(B.Edge(B._circle_at(cx, cy, z, r),
                            (Q(cx) + Q(r), Q(cy), Q(z)), (Q(cx) + Q(r), Q(cy), Q(z)))
                     for z in (Q(za), Q(zb)))
        faces.append(B.Face(B.Cylinder((Q(cx), Q(cy), Q(za)), axis, Q(r)),
                            (B.Loop(rims),), False))   # a bore faces INWARD
    else:
        _k, x0, y0, x1, y1 = foot
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for i in range(4):
            (ax, ay), (bx, by) = corners[i], corners[(i + 1) % 4]
            d = (Q(by - ay), Q(ax - bx), Q(0))
            n = tuple(-v for v in d)
            pts = [(Q(ax), Q(ay), Q(za)), (Q(bx), Q(by), Q(za)),
                   (Q(bx), Q(by), Q(zb)), (Q(ax), Q(ay), Q(zb))]
            lp = B.Loop(tuple(B.Edge(B.Line(pts[j], tuple(
                pts[(j + 1) % 4][k] - pts[j][k] for k in range(3))),
                pts[j], pts[(j + 1) % 4]) for j in range(4)))
            if B._planar_loop_area2(lp, n) < 0:
                rp = list(reversed(pts))
                lp = B.Loop(tuple(B.Edge(B.Line(rp[j], tuple(
                    rp[(j + 1) % 4][k] - rp[j][k] for k in range(3))),
                    rp[j], rp[(j + 1) % 4]) for j in range(4)))
            faces.append(B.Face(B.Plane(n, sum(n[k] * pts[0][k] for k in range(3))),
                                (lp,), True))
    return _audited(B.Body(tuple(faces)), "boolean.cut(pocket)")
