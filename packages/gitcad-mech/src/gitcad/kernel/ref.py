"""`ref` backend — the forgekernel exact reference kernel behind the seam.

ADR-0018: forgekernel (github.com/gitcad-xyz/forge) is the from-scratch
kernel's executable specification — exact rational arithmetic, no
epsilons in any decision. This shim adapts it to the gitcad Kernel
protocol for the operator classes each stage has earned; everything
else refuses honestly, naming the stage that brings it. The scorecard
(gitcad.bench) measures the growing coverage against OCCT.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

from gitcad.errors import FailureSignature, KernelError, ValidationReport

_K2 = "arrives at K2 (quadrics)"
_K3 = "arrives at K3 (NURBS/SSI)"
_K5 = "arrives at K5 (blends)"
_K7 = "K7 (booleans over freeform solids)"


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


def _audited(body, op: str, *, require_body: bool = False):
    """Check the ANSWER before returning it. The whole burn-down in one rule.

    Every silent wrong number this kernel has produced came from validating the
    INPUT by sampling instead of validating the OUTPUT: a guard probed four
    points of a footprint, or asked whether a tool's volume matched its bbox,
    and a shape that satisfied the probe but not the property sailed through.
    A property test can always be satisfied by something that is not the thing;
    the constructed body cannot lie about what it is.

    Three exact checks and one coarse one, all cheap enough to run on every
    construction:

      * every edge shared by exactly two faces — the closed-shell oracle, which
        catches a rim minted twice, a T-junction left unsplit, a face dropped;
      * positive volume, by the EXACT sign, so an inside-out body cannot pass
        by rounding to zero;
      * the closed-shell vector area, Σ Areaᵢ·n̂ᵢ = 0. This one sees a class the
        other two structurally cannot. Edge pairing audits COUNTS, so a face
        whose loop runs backwards still pairs; the volume is one number, so a
        sign error that leaves it positive still passes. Both are live risks in
        #123, where the same arc bounds the notch floor and the shoulder with
        opposite senses: the correct body sums to (0,0,0), emitting the tool's
        fourth wall gives (4, 4, π), and flipping one segment term gives
        (0, 0, 2π).

    ``require_body`` closes the last way out. A z-slab ``DisjointUnion`` can
    report exactly the right volume while being a pile of solids rather than
    one, and a non-``Body`` result is handed back here untouched — so a caller
    that has genuinely built a solid says so, and a pile then refuses instead
    of sailing past the net wearing a correct number.

    The coarse check is the MESH (see `_mesh_tears` below): the exact checks
    all reason about the b-rep, and none of them looks at what gets
    tessellated. (#130 landed: torus faces carry their rims as loops now, so
    the pairing check runs on every body — the old blanket exemption for
    torus-carrying bodies is gone.)
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
        if require_body:
            raise GeometryInvalidError(
                f"{op} was asked for one solid and produced a "
                f"{type(body).__name__} — a pile of pieces can report the right "
                "volume while not being the shape at all",
                FailureSignature(op=op, diagnostic="AnswerAudit", kernel="ref"),
                stage="audit", predicate="answer_is_a_closed_solid",
                measured={"kind": type(body).__name__},
                remedy="this is a kernel defect, not a bad request — please report it")
        try:
            subject = B.to_body(body)
        except Exception:                       # noqa: BLE001 - see above
            return body
    bad = []
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
    elif defect is None:
        # The boundary-integral form skips any body carrying an arc. The
        # SURFACE form (Σ Areaᵢ·n̂ᵢ over faces, exact in ℚ[√3][π] via the
        # twelfth span) covers plane-and-cylinder bodies with arcs — every
        # quarter-crossing #123 result, where the same 90° arc bounds the
        # notch floor and the mouth with opposite senses and a flipped sense
        # moves the sum by 2π while leaving pairing and volume untouched.
        # None still means NOT CHECKED, never passed: a sphere or torus in
        # the shell, or an odd-twelfth #123 wall whose normal has irrational
        # length (2−√3 for a crossing at 60°).
        va = B.vector_area(subject)
        if va is not None and any(c.sign() != 0 for c in va):
            bad.append("the shell is not closed: sum of Area*n is "
                       f"({', '.join(f'{float(c):.6g}' for c in va)}), "
                       "not zero")
    # The MESH, coarsely. The three checks above are all exact and all reason
    # about the b-rep; none of them looks at what gets tessellated, and a body
    # can satisfy every one of them while producing a torn STL — the first #123
    # prototype did exactly that (exact volume, clean pairing, 87 non-manifold
    # directed edges) because the trimmed-band mesher meshed the (theta,z)
    # BOUNDING RECTANGLE rather than the real domain. The landed #123 splits
    # the bore wall into plain bands and meshes rim arcs on the shared axis
    # grid, so its bodies now measure 0 unpaired directed edges at deflections
    # 0.8 through 0.05 — but the failure SHAPE is permanent: a right number
    # behind a wrong artifact is still a wrong answer to whoever prints the
    # part, which is why this check stays.
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


# A mesh tolerance below this is a request no mesher here can honour without
# unbounded subdivision — the refusal names the floor instead of exhausting
# memory trying (docket R7).
_DEFLECTION_FLOOR = 1e-9


def _check_deflection(op: str, deflection) -> float:
    """Refuse a degenerate mesh tolerance BEFORE it reaches a mesher.

    Docket R7: nothing between the seam and the meshers validated
    ``deflection``, so 0.0 escaped as a raw MemoryError, -0.5 as a raw
    OverflowError, and NaN sailed through every comparison (each is False) to
    SILENTLY return the default-quality mesh — the caller asked for an
    impossible tolerance and got 124 triangles with no signal. Deflection is a
    display property (its VALUE never decides topology, ADR-0019), but a
    refusal is still owed where no honest mesh exists.
    """
    if isinstance(deflection, bool) or not isinstance(
            deflection, (int, float, Fraction)):
        # `float("0.1")` would coerce, but a string is not a number and the
        # seam should not guess — same strictness `loads_body` applies to
        # `sense` (truthy is not True).
        raise KernelError(
            f"{op}: deflection must be a number, got "
            f"{type(deflection).__name__} {deflection!r}",
            FailureSignature(op=op, diagnostic="BadInput", kernel="ref"))
    d = float(deflection)
    if not (math.isfinite(d) and d >= _DEFLECTION_FLOOR):
        raise KernelError(
            f"{op}: deflection must be a finite number >= {_DEFLECTION_FLOOR}"
            f" (a linear mesh tolerance in model units), got {deflection!r}",
            FailureSignature(op=op, diagnostic="BadInput", kernel="ref"))
    return d


_SEAM_OPS = (
    "box", "cylinder", "sphere", "cone", "extrude", "revolve", "loft", "sweep",
    "transform", "scale", "mirror", "boolean", "compound", "mass_props",
    "measure", "bbox", "entities", "validate", "tessellate", "fillet",
    "chamfer", "shell", "draft", "helix", "pipe", "hlr_project",
    "section_polys", "export_step", "export_stl", "export_brep",
    "import_step", "import_brep",
    "move_face", "offset_face", "delete_face",
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
                # Issue #9: `exc` itself ('Body' object has no attribute
                # 'polys') is an internal of the implementation, not a fact
                # about the model — it never reaches the caller. Name the
                # MISMATCH instead: which representation, which op, which
                # stage brings it. CPython fills `exc.obj` for real attribute
                # lookups, which is exactly the operand whose representation
                # fell short.
                culprit = type(exc.obj).__name__ \
                    if getattr(exc, "obj", None) is not None else None
                shapes = {type(a).__name__ for a in args if hasattr(a, "volume")}
                if culprit:
                    shapes.add(culprit)
                kinds = ", ".join(sorted(shapes)) or "shape"
                if culprit == "Body":
                    # the canonical B-rep — where every exactly-transformed
                    # quadric/lathe lands (ADR-0021). Booleans over general
                    # B-rep solids are the K7 program; everything else on a
                    # Body is the canonical-form stage.
                    stage = _K7 if name == "boolean" \
                        else "K3.7 (canonical B-rep)"
                    what = (f"a transformed solid lands in the canonical "
                            f"B-rep (Body), and {name} has no path over "
                            f"that representation")
                    remedy = (f"re-order the recipe so {name} runs while the "
                              "operand is still in its native representation "
                              "(e.g. transform the result instead of the "
                              "operand), or wait for the named stage")
                elif culprit:
                    stage = "unsupported representation"
                    what = (f"the {culprit} representation has no {name} "
                            "path for this combination of operands")
                    remedy = ("rebuild the shape in a representation that "
                              f"supports {name}")
                else:
                    stage = "unsupported representation"
                    what = "no path exists for this combination of operands"
                    remedy = None
                raise KernelError(
                    f"ref kernel does not implement {name} on {kinds} yet "
                    f"— {what} — {stage}",
                    FailureSignature(op=name, diagnostic="NotYetImplemented",
                                     kernel="ref"),
                    stage=stage, predicate="representation_supports_op",
                    remedy=remedy)
        return inner

    for name in _SEAM_OPS:
        fn = getattr(cls, name, None)
        if callable(fn):
            setattr(cls, name, wrap(name, fn))
    return cls


def _mp(volume: float, cx: float, cy: float, cz: float, *,
        provenance: str = "exact", **extra) -> dict[str, Any]:
    """A mass-properties dict with the centroid available both as split
    ``cx/cy/cz`` scalars and as a ``centroid`` tuple (forge does not compute
    an inertia tensor — that stays out of the seam contract).

    ``provenance`` is the ADR-0019 label: ``"exact"`` when the numbers are
    float renderings of exact field elements (ℚ, ℚ[√d], ℚ[π] — the default,
    because every ref path is exact unless it says otherwise), and
    ``"certified"`` when the underlying value is a proven interval bracket
    (CInterval), in which case the midpoint is reported here and the
    half-width rides alongside (e.g. ``volume_halfwidth``). The field exists
    so K7's certified results can flow through the seam without ever being
    mistaken for exact — a certified value is "certified ± e", never a bare
    float."""
    return {"volume": volume, "cx": cx, "cy": cy, "cz": cz,
            "centroid": (cx, cy, cz), "provenance": provenance, **extra}


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


# -- direct edits (#132): shared exact helpers --------------------------------
#
# A direct edit (move_face / offset_face / delete_face) is a
# RE-PARAMETERIZATION of the owning representation, never a boolean
# (ADR-0022). The topology law every editor below enforces: the edit must be
# a homeomorphism of the boundary graph — an edge collapsing, two faces
# merging coplanar, a neighbour flipping its material side, or the target
# face vanishing from the result is a REFUSAL carrying the measured distance
# to the event, never a silently different solid.

_K6 = "K6.1 (direct edits)"


def _exact_in(op: str, v, what: str = "value") -> Fraction:
    """An op input as an exact rational — same coercion the rest of the seam
    uses (``Fraction(str(x))`` so 0.1 means 1/10, not the binary float)."""
    if isinstance(v, Fraction):
        return v
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise KernelError(
            f"{op}: {what} must be a number, got {type(v).__name__} {v!r}",
            FailureSignature(op=op, diagnostic="BadInput", kernel="ref"))
    if isinstance(v, float) and not math.isfinite(v):
        raise KernelError(
            f"{op}: {what} must be finite, got {v!r}",
            FailureSignature(op=op, diagnostic="BadInput", kernel="ref"))
    return Fraction(v) if isinstance(v, int) else Fraction(str(v))


def _det3(a, b, c):
    from forgekernel.exact import cross, dot

    return dot(a, cross(b, c))


def _meet_three_planes(p1, p2, p3):
    """Exact meet point of three planes, or None when their normals are
    linearly dependent (Cramer over ℚ — ADR-0019: topology never floats)."""
    from forgekernel.exact import add, cross, smul

    d = _det3(p1.n, p2.n, p3.n)
    if d == 0:
        return None
    v = add(add(smul(p1.d, cross(p2.n, p3.n)),
                smul(p2.d, cross(p3.n, p1.n))),
            smul(p3.d, cross(p1.n, p2.n)))
    return (v[0] / d, v[1] / d, v[2] / d)


def _newell(verts):
    """Twice the area vector of a closed polygon — exact, orientation-aware."""
    from forgekernel.exact import add, cross

    acc = (Fraction(0), Fraction(0), Fraction(0))
    n = len(verts)
    for i in range(n):
        acc = add(acc, cross(verts[i], verts[(i + 1) % n]))
    return acc


def _sign(x) -> int:
    """Exact sign of any exact scalar (Fraction / SurdVal rich comparisons)."""
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _cross2(ax, ay, bx, by):
    return ax * by - ay * bx


def _segs_cross(a, b, c, d) -> bool:
    """Exact: do 2D segments ab and cd share a point? (Endpoint touches
    count — a loop that TOUCHES itself is already a topology event.)"""
    o1 = _sign(_cross2(b[0] - a[0], b[1] - a[1], c[0] - a[0], c[1] - a[1]))
    o2 = _sign(_cross2(b[0] - a[0], b[1] - a[1], d[0] - a[0], d[1] - a[1]))
    o3 = _sign(_cross2(d[0] - c[0], d[1] - c[1], a[0] - c[0], a[1] - c[1]))
    o4 = _sign(_cross2(d[0] - c[0], d[1] - c[1], b[0] - c[0], b[1] - c[1]))
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True

    def on(p, q, r):                    # r collinear with pq and inside its box
        if _sign(_cross2(q[0] - p[0], q[1] - p[1],
                         r[0] - p[0], r[1] - p[1])) != 0:
            return False
        return (min(p[0], q[0]) <= r[0] <= max(p[0], q[0])
                and min(p[1], q[1]) <= r[1] <= max(p[1], q[1]))

    return on(a, b, c) or on(a, b, d) or on(c, d, a) or on(c, d, b)


def _loop_is_simple(pts) -> bool:
    """Exact simplicity of a closed 2D loop: no two non-adjacent segments
    meet, adjacent ones meet only at their shared vertex."""
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c, d = pts[j], pts[(j + 1) % n]
            if _segs_cross(a, b, c, d):
                return False
    return True


def _meet_lines2(p1, d1, p2, d2):
    """Exact meet of two 2D lines (point+dir), or None when parallel. Works
    over ℚ and over ℚ[√d] (SurdVal has full field arithmetic)."""
    den = _cross2(d1[0], d1[1], d2[0], d2[1])
    if den == 0:
        return None
    t = _cross2(p2[0] - p1[0], p2[1] - p1[1], d2[0], d2[1]) / den
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])


def _bore_bands(cyls):
    """Exact z-band decomposition of a coaxial bore stack: contiguous-equal
    bands merged, each (lo, hi, r) with r the largest active radius."""
    cuts = sorted({t for c in cyls for t in (c.z0, c.z1)})
    bands = []
    for lo, hi in zip(cuts, cuts[1:]):
        rs = [c.r for c in cyls if c.z0 <= lo and hi <= c.z1]
        if rs:
            bands.append([lo, hi, max(rs)])
    merged = []
    for b in bands:
        if merged and merged[-1][1] == b[0] and merged[-1][2] == b[2]:
            merged[-1][1] = b[1]
        else:
            merged.append(b)
    return [tuple(b) for b in merged]


def _drilled_ring_meta(shape):
    """The annular faces a bore stack carries besides its walls — exact.

    One tuple per ring: ``(kind, (cx, cy), z, r_below, r_above)`` with kind in
    {"shoulder", "floor", "ceiling"} and r_below/r_above the void radii on
    each side of z (0 = solid material on that side). These are real faces of
    the solid (the counterbore shoulder, the blind hole's floor) that
    ``cylinder_faces`` never enumerated, so no direct edit could name them.

    Multi-slab columns (a bore through a shelled base) are SKIPPED: their ring
    faces border internal voids and a descriptor computed from the outer
    z-extent would lie.
    """
    from collections import defaultdict

    from forgekernel.quadric import _column_slabs

    (_, _, bz0), (_, _, bz1) = shape.base.bbox()
    groups: dict = defaultdict(list)
    for c in shape.bores:
        groups[(c.cx, c.cy)].append(c)
    out = []
    for key in sorted(groups):
        cyls = groups[key]
        if len(_column_slabs(shape.base, cyls[0])) != 1:
            continue
        bands = _bore_bands(cyls)
        for i, (lo, hi, r) in enumerate(bands):
            below = bands[i - 1] if i > 0 else None
            if lo > bz0 and (below is None or below[1] < lo):
                out.append(("floor", key, lo, Fraction(0), r))
            if below is not None and below[1] < lo:
                out.append(("ceiling", key, below[1], below[2], Fraction(0)))
            if below is not None and below[1] == lo and below[2] != r:
                out.append(("shoulder", key, lo, below[2], r))
        if bands and bands[-1][1] < bz1:
            out.append(("ceiling", key, bands[-1][1], bands[-1][2],
                        Fraction(0)))
    return out


def _drilled_ring_faces(shape) -> list[dict]:
    """Descriptor form of :func:`_drilled_ring_meta` for ``entities``."""
    out = []
    for kind, (cx, cy), z, r_below, r_above in _drilled_ring_meta(shape):
        d = {"surface": "plane",
             "lineage": "bore.shoulder" if kind == "shoulder" else "bore.floor",
             "plane": [0.0, 0.0, 1.0], "z": float(z),
             "centroid": [float(cx), float(cy), float(z)]}
        if kind == "shoulder":
            d["r_inner"] = float(min(r_below, r_above))
            d["r_outer"] = float(max(r_below, r_above))
        else:
            d["radius"] = float(max(r_below, r_above))
        out.append(d)
    return out


def _lathe_face_segments(loop) -> list[int]:
    """Indices of the profile segments that are FACES of the revolved solid
    (everything except the axis segments r==0 → r==0), in loop order."""
    n = len(loop)
    return [i for i in range(n)
            if not (loop[i][0] == 0 and loop[(i + 1) % n][0] == 0)]


def _lathe_seg_faces(shape) -> list[dict]:
    """Per-segment face descriptors for a RevolveSolid — caps are planes,
    vertical segments cylinders, slanted ones cones. This is what makes a
    lathe's faces individually addressable (before, the whole solid was one
    opaque descriptor no selector could distinguish)."""
    cx, cy = float(shape.cx), float(shape.cy)
    loop = shape.loop
    n = len(loop)
    out = []
    for i in _lathe_face_segments(loop):
        (r1, z1), (r2, z2) = loop[i], loop[(i + 1) % n]
        mid_z = float(z1 + z2) / 2
        if z1 == z2:
            out.append({"surface": "plane", "lineage": f"lathe.seg{i}",
                        "plane": [0.0, 0.0, 1.0], "z": float(z1),
                        "r_lo": float(min(r1, r2)), "r_hi": float(max(r1, r2)),
                        "centroid": [cx, cy, float(z1)]})
        elif r1 == r2:
            out.append({"surface": "cylinder", "lineage": f"lathe.seg{i}",
                        "radius": float(r1), "axis_dir": [0.0, 0.0, 1.0],
                        "axis_origin": [cx, cy, float(min(z1, z2))],
                        "centroid": [cx, cy, mid_z]})
        else:
            out.append({"surface": "cone", "lineage": f"lathe.seg{i}",
                        "r1": float(r1), "r2": float(r2),
                        "z1": float(z1), "z2": float(z2),
                        "axis_dir": [0.0, 0.0, 1.0],
                        "axis_origin": [cx, cy, float(min(z1, z2))],
                        "centroid": [cx, cy, mid_z]})
    return out


_ROUNDED_FLATS = (("bottom", 2, "min"), ("top", 2, "max"),
                  ("front", 1, "min"), ("back", 1, "max"),
                  ("right", 0, "max"), ("left", 0, "min"))


def _rounded_face_meta(shape):
    """(kind, *spec) per face of a RoundedBox, aligned 1:1 with
    :func:`_rounded_faces`: 6 flats, 12 edge blends, 8 corner octants."""
    out = [("flat", name, axis, side) for name, axis, side in _ROUNDED_FLATS]
    for axis in range(3):
        b, c = [o for o in range(3) if o != axis]
        for sb in ("min", "max"):
            for sc in ("min", "max"):
                out.append(("edge", axis, (b, sb), (c, sc)))
    for sx in ("min", "max"):
        for sy in ("min", "max"):
            for sz in ("min", "max"):
                out.append(("corner", sx, sy, sz))
    return out


def _rounded_faces(shape) -> list[dict]:
    """Full face enumeration of a RoundedBox (was one opaque descriptor —
    nothing on it was addressable, so nothing on it was editable)."""
    import math as _m

    dims = (float(shape.a), float(shape.b), float(shape.c))
    org = tuple(float(v) for v in shape.origin)
    r = float(shape.r)
    flats = tuple(d - 2 * r for d in dims)

    def coord(axis, side, inset):
        lo, hi = org[axis], org[axis] + dims[axis]
        return lo + inset if side == "min" else hi - inset

    out: list[dict] = []
    for kind, *spec in _rounded_face_meta(shape):
        if kind == "flat":
            name, axis, side = spec
            b, c = [o for o in range(3) if o != axis]
            centroid = [0.0, 0.0, 0.0]
            centroid[axis] = coord(axis, side, 0.0)
            centroid[b] = org[b] + dims[b] / 2
            centroid[c] = org[c] + dims[c] / 2
            normal = [0.0, 0.0, 0.0]
            normal[axis] = 1.0
            out.append({"surface": "plane", "lineage": f"rounded.{name}",
                        "plane": normal, "centroid": centroid,
                        "area": flats[b] * flats[c]})
        elif kind == "edge":
            axis, (b, sb), (c, sc) = spec
            origin = [0.0, 0.0, 0.0]
            origin[axis] = coord(axis, "min", r)
            origin[b] = coord(b, sb, r)
            origin[c] = coord(c, sc, r)
            axis_dir = [0.0, 0.0, 0.0]
            axis_dir[axis] = 1.0
            k = r / _m.sqrt(2)
            centroid = list(origin)
            centroid[axis] = org[axis] + dims[axis] / 2
            centroid[b] += k if sb == "max" else -k
            centroid[c] += k if sc == "max" else -k
            names = "xyz"
            out.append({"surface": "blend-cylinder",
                        "lineage": f"rounded.edge.{names[axis]}.{sb}.{sc}",
                        "radius": r, "axis_dir": axis_dir,
                        "axis_origin": origin, "centroid": centroid})
        else:
            sides = spec
            centre = [coord(axis, sides[axis], r) for axis in range(3)]
            k = r / _m.sqrt(3)
            centroid = [centre[axis] + (k if sides[axis] == "max" else -k)
                        for axis in range(3)]
            out.append({"surface": "blend-sphere",
                        "lineage": f"rounded.corner.{'.'.join(sides)}",
                        "radius": r, "center": centre, "centroid": centroid})
    return out


@_guard_seam
class RefKernel:
    """K1: exact planar solids (box, line-profile extrude, quarter-turn
    rigid transforms, mirror, scale, booleans, exact mass properties)."""

    name = "ref-k2-exact"

    # Evidence channel for the last import (#135): what was dropped, what was
    # healed and its certificate. The importer's ImportReport reads this after
    # a build — intent lives in the feature params (ADR-0022), evidence here.
    last_import_report: dict | None = None

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

    @staticmethod
    def _quarter_turns(rotate_axis, rotate_deg):
        """``(axis_name, k)`` for an exact quarter-turn about a principal
        axis through the origin (k counter-clockwise quarter-turns about the
        POSITIVE axis, in {0, 1, 2, 3}), else None."""
        signed = {(1, 0, 0): ("x", 1), (0, 1, 0): ("y", 1),
                  (0, 0, 1): ("z", 1), (-1, 0, 0): ("x", -1),
                  (0, -1, 0): ("y", -1), (0, 0, -1): ("z", -1)}
        named = signed.get(tuple(rotate_axis))
        if named is None or rotate_deg % 90 != 0:
            return None
        name, sign = named
        return name, int(sign * (rotate_deg // 90)) % 4

    @staticmethod
    def _rot_q(x, y, k):
        """Rotate (x, y) by k counter-clockwise quarter-turns, exactly."""
        for _ in range(k % 4):
            x, y = -y, x
        return x, y

    @classmethod
    def _rot_q3(cls, p, axis, k):
        """Rotate a 3d point by k quarter-turns about a principal axis."""
        x, y, z = p
        if axis == "z":
            x, y = cls._rot_q(x, y, k)
        elif axis == "x":
            y, z = cls._rot_q(y, z, k)
        else:
            z, x = cls._rot_q(z, x, k)
        return x, y, z

    def _rotate_native(self, shape, rotate_axis, rotate_deg):
        """Rotate WITHOUT leaving the representation, where symmetry allows
        (issue #8: rotate must not be a one-way door where it needn't be).

        The exact facts this encodes, nothing more:

          * any rotation about a z-axisymmetric solid's OWN axis is the
            identity (a lathe spun about its axis is the same lathe);
          * a quarter-turn about z maps the z-axisymmetric family (Cyl,
            Cone, RevolveSolid, AxisStack, DrilledSolid, DisjointUnion of
            such) to itself with centres rotated exactly;
          * a sphere is a sphere about any centre: principal-axis
            quarter-turns rotate its centre, and any rotation about an
            axis through its centre is the identity.

        Returns None where the rotation genuinely breaks the
        representation — the caller then converts through the canonical
        B-rep (ADR-0021), which is lossy for booleans and says so
        downstream. Never widens what is exactly representable.
        """
        from forgekernel.brep import Solid
        from forgekernel.quadric import (AxisStack, Cone, Cyl, DisjointUnion,
                                         DrilledSolid, RevolveSolid, Sphere)

        q = self._quarter_turns(rotate_axis, rotate_deg)
        if isinstance(shape, Sphere):
            c, ax = (shape.cx, shape.cy, shape.cz), tuple(rotate_axis)
            if c == (0, 0, 0):
                return shape                # any axis through the centre
            if (ax in ((0, 0, 1), (0, 0, -1)) and c[:2] == (0, 0)) \
                    or (ax in ((1, 0, 0), (-1, 0, 0)) and c[1:] == (0, 0)) \
                    or (ax in ((0, 1, 0), (0, -1, 0))
                        and (c[0], c[2]) == (0, 0)):
                return shape                # the axis passes through it
            if q is None:
                return None
            axis, k = q
            if k == 0:
                return shape
            cx, cy, cz = self._rot_q3((shape.cx, shape.cy, shape.cz), axis, k)
            return Sphere(cx, cy, cz, shape.r)
        if tuple(rotate_axis) not in ((0, 0, 1), (0, 0, -1)):
            return None
        if isinstance(shape, (Cyl, Cone, RevolveSolid)) \
                and (shape.cx, shape.cy) == (0, 0):
            return shape                    # its own axis: the identity
        if q is None:
            return None
        _axis, k = q
        if k == 0:
            return shape
        if isinstance(shape, (Cyl, Cone, RevolveSolid)):
            cx, cy = self._rot_q(shape.cx, shape.cy, k)
            return shape.translated(cx - shape.cx, cy - shape.cy, 0)
        if isinstance(shape, DrilledSolid):
            base = self._fk.rotate_quarter(shape.base, "z", k)
            bores = [Cyl(*self._rot_q(b.cx, b.cy, k), b.r, b.z0, b.z1)
                     for b in shape.bores]
            return DrilledSolid(base, bores)
        if isinstance(shape, AxisStack):
            cx, cy = self._rot_q(shape.cx, shape.cy, k)
            return AxisStack(cx, cy,
                             [p.translated(cx - p.cx, cy - p.cy, 0)
                              for p in shape.prims])
        if isinstance(shape, DisjointUnion):
            members = []
            for m in shape.members:
                if isinstance(m, Solid):
                    members.append(self._fk.rotate_quarter(m, "z", k))
                    continue
                rm = self._rotate_native(m, rotate_axis, rotate_deg)
                if rm is None:
                    return None
                members.append(rm)
            # a rigid motion of the whole preserves pairwise disjointness
            return DisjointUnion._unchecked(members)
        return None

    def transform(self, shape, *, translate=(0, 0, 0),
                  rotate_axis=(0, 0, 1), rotate_deg: float = 0.0):
        from forgekernel.brep import Solid
        from forgekernel.quadric import (AxisStack, Cone, Cyl, DisjointUnion,
                                         DrilledSolid, RevolveSolid, Sphere)
        from forgekernel.curve import TubeSolid

        if rotate_deg and not isinstance(shape, Solid):
            native = self._rotate_native(shape, rotate_axis, rotate_deg)
            if native is not None:
                shape = native
                rotate_deg = 0.0            # only the translation remains
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
            if rotate_deg:
                # a rotation the family cannot absorb (a tilt, or a
                # non-quarter turn of an off-axis solid) genuinely leaves
                # the representation — through the canonical form, honestly
                return self._transform_via_body(
                    "tilt a quadric", shape, rotate_axis, rotate_deg, translate)
            return shape.translated(*translate)
        if isinstance(shape, AxisStack):
            if rotate_deg:
                return self._transform_via_body(
                    "transform an AxisStack", shape,
                    rotate_axis, rotate_deg, translate)
            if any(translate):
                # rigid translation: every member carries its own centre.
                # F() first — Fraction + float would round through the float
                from forgekernel.exact import F as _F

                return AxisStack(shape.cx + _F(translate[0]),
                                 shape.cy + _F(translate[1]),
                                 [p.translated(*translate)
                                  for p in shape.prims])
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

        rep = type(shape).__name__
        # Issue #9: the raw exception ("argument should be a string or a
        # Rational instance…") reads as a type bug in the caller's arguments.
        # The fact about the model is which HALF of the canonical route fell
        # short: no converter, or an op the canonical form cannot take yet.
        try:
            body = B.to_body(shape)
        except (ValueError, AttributeError, TypeError):
            _nope(f"{op} on {rep}", "K3.7 (canonical B-rep)",
                  predicate="representation_has_canonical_brep",
                  remedy=f"a {rep} has no converter to the canonical B-rep "
                         f"yet; rebuild the shape in a representation that "
                         f"converts, or run {op} on the inputs that made it")
        try:
            return make(body)
        except (ValueError, AttributeError, TypeError):
            _nope(f"{op} on {rep}", "K3.7 (canonical B-rep)",
                  predicate="canonical_brep_supports_op",
                  remedy=f"{op} cannot complete exactly on the canonical "
                         f"B-rep this {rep} converts to — a transformed "
                         f"solid's exact coordinates can lie outside what "
                         f"{op} encodes; run {op} before the transform and "
                         "apply the placement downstream")

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

        # FREEFORM operands. A smooth loft now HAS its exact patch-skin
        # converter — LoftSolid.to_patches (K7 flagship): walls degree (1,3)
        # straight from the natural-spline coefficients, caps planar, seam
        # topology proven by exact control-point equality — so LoftSolid
        # operands convert here and take the PatchSolid assembly below,
        # open branches included (loft × loft is the case that forced the
        # seam-edge pairing to exist). SplinePrism and TubeSolid still have
        # no converter and keep the K7-staged refusal: a spline prism cut
        # by a box must never leak "'SplinePrism' object has no attribute
        # 'polys'" with stage=None (#96 gap 11 / item 10).
        from forgekernel.curve import TubeSolid
        from forgekernel.loft import LoftSolid
        from forgekernel.profile2d import SplinePrism

        if isinstance(a, LoftSolid) or isinstance(b, LoftSolid):
            try:
                a = a.to_patches() if isinstance(a, LoftSolid) else a
                b = b.to_patches() if isinstance(b, LoftSolid) else b
            except ValueError as exc:
                _nope(f"boolean.{op} (loft skin: {exc})", _K7,
                      predicate="loft_skin_unbuildable",
                      remedy="the loft's sections refuse an outward patch "
                             "skin (mixed orientation or a zero-area "
                             "section); fix the section loops and re-loft")

        ff = [type(s).__name__ for s in (a, b)
              if isinstance(s, (SplinePrism, TubeSolid))]
        if ff:
            _nope(f"boolean.{op} on freeform operands ({', '.join(ff)})",
                  _K7,
                  predicate="freeform_boolean_unbuilt",
                  remedy="K7's boolean assembly works over PatchSolid "
                         "operands today (SSI chains, certified "
                         "point-membership classification, an audited "
                         "trimmed-patch shell whose volume is certified ± e, "
                         "ADR-0019), and smooth lofts convert via "
                         "LoftSolid.to_patches; these representations still "
                         "need their patch-skin converters — until those "
                         "land, model the boolean against a planar, quadric, "
                         "or PatchSolid representation instead")

        # K7 gap 5 through the seam: PatchSolid × PatchSolid dispatches to
        # forge's boolean_trimmed — per face-pair SSI, certified trim loops,
        # certified fragment membership, principled orientation, full shell
        # audit. Every forge refusal crosses the seam as a K7-staged
        # KernelError carrying the guard's own predicate name; the only
        # thing that never crosses is a wrong shell.
        from forgekernel.bsolid import BooleanUnsupported, PatchSolid
        from forgekernel.trimshell import (ShellAuditError,
                                           ShellAuditUncertified,
                                           TrimmedShell)

        if isinstance(a, TrimmedShell) or isinstance(b, TrimmedShell):
            _nope(f"boolean.{op} on a TrimmedShell operand", _K7,
                  predicate="trimmed_shell_reboolean_unbuilt",
                  remedy="a boolean RESULT cannot be an operand yet — "
                         "re-trimming already-trimmed faces is the K7 "
                         "follow-on; boolean the original patch solids "
                         "instead")
        if isinstance(a, PatchSolid) or isinstance(b, PatchSolid):
            if not (isinstance(a, PatchSolid) and isinstance(b, PatchSolid)):
                other = type(b if isinstance(a, PatchSolid) else a).__name__
                _nope(f"boolean.{op} on PatchSolid × {other}", _K7,
                      predicate="mixed_patchsolid_boolean_unbuilt",
                      remedy="only PatchSolid × PatchSolid is assembled "
                             "today; represent the other operand as an "
                             "outward-oriented PatchSolid (e.g. "
                             "forgekernel.bsolid.box_patches) first")
            from forgekernel.bsolid import boolean_trimmed
            from forgekernel.raycast import PointClassifyUncertified
            from forgekernel.ssi import (SsiCellUncertified,
                                         TrimLoopUnstitchable)
            try:
                return boolean_trimmed(op, a, b, depth=5)
            except SsiCellUncertified as exc:
                _nope(f"boolean.{op} (tangential or near-tangential "
                      f"contact)", _K7,
                      predicate="ssi_cell_uncertified",
                      measured={"unresolved_cells": len(exc.cells),
                                "depth": exc.depth},
                      remedy="tangential contact has no transversal "
                             "certificate; separate the surfaces or raise "
                             "the depth only if the contact is believed "
                             "transversal")
            except TrimLoopUnstitchable as exc:
                _nope(f"boolean.{op} ({exc})", _K7,
                      predicate=f"trim_loop_unstitchable_{exc.reason}",
                      remedy="the intersection curve could not be closed "
                             "into a certified trim loop; raise the depth "
                             "or reshape the overlap so curves close "
                             "inside the faces")
            except BooleanUnsupported as exc:
                _nope(f"boolean.{op} ({exc})", _K7,
                      predicate=exc.predicate,
                      remedy="this operand/curve configuration is outside "
                             "what the K7 assembly can certify today; see "
                             "the predicate for which guard refused")
            except PointClassifyUncertified as exc:
                _nope(f"boolean.{op} (fragment membership uncertified)",
                      _K7,
                      predicate="point_classify_uncertified",
                      measured={"rays_refused": len(exc.reasons)},
                      remedy="no witness ray certified a fragment's "
                             "membership — geometry may graze the other "
                             "solid's boundary; raise the depth")
            except ShellAuditUncertified as exc:
                _nope(f"boolean.{op} (shell audit uncertified: {exc})",
                      _K7,
                      predicate="shell_audit_uncertified",
                      remedy="the certified brackets are too wide to prove "
                             "the shell at this depth; raise the depth")
            except ShellAuditError as exc:
                # a PROVEN-wrong shell is a kernel defect, not a modeling
                # error — but a raw ValueError through the seam is a
                # crash-class defect, so it crosses structured
                raise KernelError(
                    f"K7 boolean produced a shell that failed its own "
                    f"audit — a kernel defect, not a modeling error: {exc}",
                    FailureSignature(op=f"boolean.{op}",
                                     diagnostic="ShellAuditFailed",
                                     kernel="ref"),
                    stage=_K7, predicate="shell_audit_failed",
                    remedy="file this as a bug: the assembly and its own "
                           "audit disagree") from exc

        # a sphere with a COAXIAL bore: exact in ℚ[√d][π] — the arc term lives
        # in forgekernel.surdrev and is proven there against closed forms.
        #
        #   * drilled clean THROUGH → a napkin ring (two faces, no caps),
        #     V = (4/3)π(R²−r²)^(3/2);
        #   * entering from the TOP and STOPPING inside the band → a BLIND
        #     bore (three faces: one-rim zone, wall, and the tool's own FLAT
        #     disk floor — a plane, not the spherical cap an earlier note
        #     guessed), V = π(2R³/3 + (2/3)(R²−r²)^(3/2) + r²·(z_floor−c_z)).
        #
        # Only the CENTRED cases. Off-axis, the volume acquires elliptic
        # integrals and leaves every algebraic extension, so there is nothing
        # to be exact about; a tool stopping ON the band edge, below it, or
        # entirely inside the material is a different topology (no wall left /
        # a through ring / a closed internal void). Those keep refusing, and
        # that is the honest answer rather than a near-miss.
        if op == "cut" and isinstance(a, Sphere) and isinstance(b, Cyl):
            from forgekernel.surdrev import NapkinRing, SphereBlindBore

            ax, ay, az = a.c if hasattr(a, "c") else (a.cx, a.cy, a.cz)
            if b.cx == ax and b.cy == ay and 0 <= b.r < a.r \
                    and b.z0 <= az - a.r and b.z1 >= az + a.r:
                return _audited(NapkinRing(a.r, b.r, ax, ay, az), "boolean.cut")
            # blind from the top: the tool clears the north pole entirely
            # (z1 ≥ c+R, else a cap would survive DISCONNECTED above the tool)
            # and its floor sits strictly inside the band (exact, in ℚ:
            # (z0−c)² < R²−r²). Entering from the BOTTOM instead still
            # refuses — same mathematics, but nothing constructs it yet.
            if b.cx == ax and b.cy == ay and 0 < b.r < a.r \
                    and b.z1 >= az + a.r \
                    and (b.z0 - az) * (b.z0 - az) < a.r * a.r - b.r * b.r:
                return _audited(
                    SphereBlindBore(a.r, b.r, b.z0 - az, ax, ay, az),
                    "boolean.cut")

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
            except ValueError:
                # genuinely overlapping (or unprovably separated). Coaxial
                # solids of revolution union EXACTLY — the union of their
                # (r, z) profiles (issue #14: the overlapping hose-nozzle
                # collar). Everything else keeps refusing, without the old
                # text that called an OVERLAPPING pair "disjoint-union".
                fused = self._fuse_lathe(a, b)
                if fused is not None:
                    return fused
                _nope(f"boolean.union of {type(a).__name__}+"
                      f"{type(b).__name__} whose members overlap or cannot "
                      "be proven separate",
                      "K2.3 (general quadric union)",
                      predicate="union_members_provably_disjoint",
                      remedy="coaxial overlapping solids of revolution fuse "
                             "exactly through their shared profile; move the "
                             "parts apart, make them coaxial, or wait for "
                             "the general union")
        if op == "cut":
            # #123 — a box tool whose FOOTPRINT STRADDLES a bore. It has to be
            # tried before the representation-specific paths below, because
            # every one of them is right to refuse it: a DrilledSolid cannot
            # hold a bore that meets a lateral wall, and its guard saying so is
            # correct and must never be loosened. This dispatches AHEAD of that
            # guard rather than around it, and only for the family it can
            # actually build — anything else falls through untouched.
            straddled = self._straddle_cut(a, b)
            if straddled is not None:
                return straddled
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
                    # audited like every other constructive path: W6's phantom
                    # shoulder (a gapped counterbore stack whose canonical form
                    # grew an annulus hanging in solid material) reached
                    # mass_props off by an exact pi multiple BECAUSE this
                    # return skipped the answer audit — validate said ok while
                    # manifold_violations could see the tear all along.
                    return _audited(base.cut(b), "boolean.cut(drill)")
                except ValueError as exc:
                    raise KernelError(str(exc), FailureSignature(
                        op="boolean.cut", diagnostic="NotYetImplemented",
                        kernel="ref"))
        if op == "intersect":
            # a z-band clip of a solid of revolution (the split op's
            # half-space boolean) truncates its PROFILE — exact (#14)
            clipped = self._clip_lathe_zband(a, b)
            if clipped is None:
                clipped = self._clip_lathe_zband(b, a)
            if clipped is not None:
                return clipped
        # A rotated solid that left its representation lands in the canonical
        # B-rep (Body), which no boolean path accepts yet — name THAT, rather
        # than blaming whichever quadric shares the call (issue #8: the
        # boundary an agent needs is which rotations preserve representation).
        from forgekernel.body import Body as _CanonBody

        if isinstance(a, _CanonBody) or isinstance(b, _CanonBody):
            _nope(f"boolean.{op} on {type(a).__name__} × {type(b).__name__} "
                  "— a transformed solid landed in the canonical B-rep "
                  "(Body)", _K7,
                  predicate="canonical_brep_boolean_unbuilt",
                  remedy="quarter-turns about z, principal quarter-turns of "
                         "a sphere, and any rotation about a z-axisymmetric "
                         "solid's own axis all PRESERVE the native "
                         "representation — re-order the recipe to keep "
                         "boolean operands native (e.g. rotate the boolean's "
                         "result instead of its operand)")
        # RoundedBox, RevolveSolid and DisjointUnion belong on this list too:
        # they have no `.polys`, so falling through to the planar BSP engine
        # surfaced raw CPython text ("'RoundedBox' object has no attribute
        # 'polys'") as the kernel's diagnostic instead of naming the stage.
        if isinstance(a, curved) or isinstance(b, curved):
            _nope(f"boolean.{op} on quadric operands "
                  f"({type(a).__name__} × {type(b).__name__})", "K2.2")
        try:
            # cost signal on the live rail (#11): exact BSP arithmetic grows
            # with facet count, and a dense operand (a lofted hull) can take
            # minutes — say so BEFORE starting, so the watcher and the agent
            # both know what the elapsed seconds are being spent on.
            npa = len(getattr(a, "polys", ()))
            npb = len(getattr(b, "polys", ()))
            if npa + npb >= 200:
                from gitcad import activity
                activity.note(text=f"boolean.{op}: {npa} × {npb} facets — "
                                   "exact BSP arithmetic; cost grows "
                                   "quadratically with facet count")
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
        from forgekernel.brep import Solid as _Solid

        if isinstance(shape, _Solid) and not shape.polys:
            # The EMPTY solid — cut(a, a), cut by a superset, a disjoint
            # intersect — is an ANSWER, not a failure (#136). Volume 0 is the
            # truth and gets reported; the centroid of the empty set does not
            # exist, so those fields are NaN rather than a fabricated
            # location, and `empty` says so in data.
            nan = float("nan")
            return _mp(0.0, nan, nan, nan, empty=True)
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
            # the midpoint plus the proven half-width bracketing the truth,
            # LABELLED as certified so no consumer reads midpoint as exact.
            v = shape.volume()
            cx, cy, cz = shape.centroid_f()
            return _mp(v.to_float(), cx, cy, cz,
                       provenance=shape.provenance,
                       volume_halfwidth=float(v.width) / 2)
        from forgekernel.trimshell import TrimmedShell
        if isinstance(shape, TrimmedShell):
            # a K7 boolean result: volume is a certified bracket through the
            # SSI strips (depth 5 matches the boolean's default detection
            # depth). No certified centroid machinery exists for trimmed
            # shells yet, so the centroid is a FLAGGED non-answer (NaN, the
            # empty-solid precedent) — never a fabricated location.
            v = shape.volume(depth=5)
            nan = float("nan")
            return _mp(v.to_float(), nan, nan, nan,
                       provenance=shape.provenance,
                       volume_halfwidth=float(v.width) / 2,
                       centroid_unavailable=True)
        # Measure the volume on the ORIGINAL shape, before the AxisStack wrap
        # below: a Sphere has a canonical body and an AxisStack does not, so
        # wrapping first would send it down the float-integrating path that
        # _exact_volume exists to avoid.
        vol = _exact_volume(shape)
        if isinstance(shape, (Cone, Sphere)):
            shape = AxisStack(shape.cx, shape.cy, [shape])
        from forgekernel.quadric import (FilletedBox, FilletedChamferedBox,
                                         FilletedPrism, VariableFilletedBox)
        if isinstance(shape, (Cyl, DrilledSolid, AxisStack, RevolveSolid, DisjointUnion, RoundedBox, MiteredSweep, SphereOverlap, FilletedBox, FilletedPrism, FilletedChamferedBox, VariableFilletedBox)):
            cx, cy, cz = shape.centroid_f()
            return _mp(vol, cx, cy, cz)
        c = shape.centroid()
        return _mp(vol, float(c[0]), float(c[1]), float(c[2]))

    def measure(self, shape) -> dict[str, float]:
        from forgekernel.quadric import AxisStack, Cone, Sphere
        from forgekernel import body as B
        from forgekernel.brep import Solid as _Solid

        if isinstance(shape, _Solid) and not shape.polys:
            # the empty solid (#136): zero volume, zero extent in every axis —
            # asking self.bbox() would refuse (it has no location), and letting
            # min() raise over no vertices was a raw crash through the seam
            return {"volume": 0.0, "dx": 0.0, "dy": 0.0, "dz": 0.0}
        if isinstance(shape, B.Body):                 # ADR-0021 canonical form
            try:
                (x0, y0, z0), (x1, y1, z1) = B.bbox(shape)
                return {"volume": float(B.volume(shape)),
                        "dx": x1 - x0, "dy": y1 - y0, "dz": z1 - z0}
            except ValueError as exc:
                # forge refuses honestly when the value leaves the exact field
                # (a ring rotated off-axis, say). A raw ValueError through the
                # seam is a CRASH-class defect — wrap it like mass_props does.
                _nope(f"measure({exc})", _K2)

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
        from forgekernel.brep import Solid as _Solid

        if isinstance(shape, _Solid) and not shape.polys:
            # The empty solid contains no points, so it has no bounding box —
            # inventing one would be a wrong number wearing coordinates, and
            # the old behaviour (min() over no vertices) was a raw ValueError
            # through the seam. Refuse structurally instead (#136).
            raise KernelError(
                "the empty solid has no bounding box — it contains no points",
                FailureSignature(op="bbox", diagnostic="EmptySolid",
                                 kernel="ref"),
                stage="bbox", predicate="solid_is_nonempty",
                measured={"polygons": 0},
                remedy="check mass_props()['volume'] (or its 'empty' flag) "
                       "before asking where a solid is")
        if isinstance(shape, B.Body):
            return B.bbox(shape)
        from forgekernel.quadric import AxisStack, Cone, Sphere
        from forgekernel.curve import TubeSolid

        from forgekernel.quadric import RoundedBox
        from forgekernel.loft import LoftSolid
        from forgekernel.profile2d import SplinePrism
        from forgekernel.trimshell import TrimmedShell as _TShell
        if isinstance(shape, _TShell):
            # the control-net box of an UNTRIMMED face over-reports a
            # trimmed one — a wrong number wearing coordinates. A
            # strip-aware certified extent has not landed; refuse by name.
            _nope("bbox on a TrimmedShell", _K7,
                  predicate="trimmed_shell_extent_unbuilt",
                  remedy="a certified extent must exclude the trimmed-away "
                         "control net; until that lands, derive extents "
                         "from the operands")
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
        from forgekernel.trimshell import TrimmedShell as _TShl
        if isinstance(shape, _TShl):
            # a freeform shell's faces ARE enumerable (the audit names
            # them); descriptors carry the trim topology so a K3.7 import
            # can be indexed by the document (edges stay unenumerated —
            # trim edges live in parameter space, and inventing 3D edge
            # descriptors for them would be a wrong number wearing
            # coordinates)
            return [{"surface": "trimmed-bspline", "sense": f.sense,
                     "loops": len(f.loops)} for f in shape.faces]
        if isinstance(shape, TubeSolid):
            # swept lateral surface + two round end caps
            return [{"surface": "swept-tube"}, {"surface": "plane"},
                    {"surface": "plane"}]
        if isinstance(shape, SphereOverlap):
            return [{"surface": "sphere-lens"}]
        if isinstance(shape, RoundedBox):
            # every face individually addressable (6 flats + 12 edge blends +
            # 8 corner octants) — the precondition for direct edits (#132)
            return _rounded_faces(shape)
        if isinstance(shape, RevolveSolid):
            # per-profile-segment faces (caps / cylinders / cones), not the
            # single opaque descriptor the prims fallback used to emit
            return _lathe_seg_faces(shape)
        from forgekernel.quadric import FilletedPrism as _FPr
        if isinstance(shape, _FPr):
            return [{"surface": "filleted-prism"}]
        from forgekernel.quadric import VariableFilletedBox as _VFBx
        if isinstance(shape, _VFBx):
            return [{"surface": "variable-filleted-box"}]
        from forgekernel.quadric import FilletedChamferedBox as _FCB
        if isinstance(shape, _FCB):
            return [{"surface": "filleted-chamfered-box"}]
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
            import math as _m

            cx, cy = float(shape.cx), float(shape.cy)
            cap_area = _m.pi * float(shape.r) ** 2
            return [{"surface": "cylinder", "radius": float(shape.r),
                     "axis_dir": [0.0, 0.0, 1.0],
                     "axis_origin": [cx, cy, float(shape.z0)]},
                    {"surface": "plane", "lineage": "cyl.top",
                     "plane": [0.0, 0.0, 1.0], "z": float(shape.z1),
                     "radius": float(shape.r), "area": cap_area,
                     "centroid": [cx, cy, float(shape.z1)]},
                    {"surface": "plane", "lineage": "cyl.bottom",
                     "plane": [0.0, 0.0, 1.0], "z": float(shape.z0),
                     "radius": float(shape.r), "area": cap_area,
                     "centroid": [cx, cy, float(shape.z0)]}]
        if isinstance(shape, DrilledSolid):
            base = self.entities(shape.base, "face")
            # walls, then the ring faces (counterbore shoulders, blind-hole
            # floors) that were never enumerated — appended so existing
            # indices stay stable
            return base + shape.cylinder_faces() + _drilled_ring_faces(shape)
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
                                    checks={"method": "exact-green-area",
                                            "provenance": shape.provenance},
                                    violations=[])
        if isinstance(shape, TubeSolid):
            # watertight by construction (closed section, non-self-overlapping
            # sweep — both preconditions checked at build); volume certified >0
            return ValidationReport(
                ok=True,
                checks={"method": "certified-tube",
                        "provenance": shape.provenance},
                violations=[])
        from forgekernel.trimshell import (ShellAuditError,
                                           ShellAuditUncertified)
        from forgekernel.trimshell import TrimmedShell as _TShell
        if isinstance(shape, _TShell):
            # a K7 boolean result: re-run the full three-oracle audit (exact
            # trim-edge pairing, Σ-flux orientation, certified volume sign).
            # "uncertified" is reported as not-ok WITH the reason — the shell
            # is unproven at this depth, which must never read as fine.
            try:
                report = shape.audit(depth=5)
            except ShellAuditError as exc:
                return ValidationReport(
                    ok=False,
                    checks={"method": "certified-shell-audit",
                            "provenance": shape.provenance},
                    violations=[str(exc)])
            except ShellAuditUncertified as exc:
                return ValidationReport(
                    ok=False,
                    checks={"method": "certified-shell-audit",
                            "provenance": shape.provenance,
                            "uncertified": True},
                    violations=[str(exc)])
            return ValidationReport(
                ok=True,
                checks={"method": "certified-shell-audit",
                        "provenance": shape.provenance,
                        "faces": report["faces"],
                        "edges": report["edges"]},
                violations=[])
        from forgekernel.quadric import FilletedBox as _FB
        from forgekernel.quadric import FilletedChamferedBox as _FCB
        from forgekernel.quadric import FilletedPrism as _FP
        from forgekernel.quadric import VariableFilletedBox as _VFB
        if isinstance(shape, (Cyl, Cone, Sphere, AxisStack, RevolveSolid, DisjointUnion, RoundedBox, MiteredSweep, SphereOverlap, _FB, _FP, _FCB, _VFB)):
            return ValidationReport(ok=True, checks={"method": "analytic",
                                                     "provenance": "exact"},
                                    violations=[])
        from forgekernel import body as _B
        if isinstance(shape, _B.Body):
            # A Body has no `watertight_violations` — it is a different
            # representation — so every pocketed or curved-shelled solid came
            # back "unsupported representation", i.e. unvalidatable, which
            # reads far too much like fine. The canonical B-rep's own oracle is
            # edge pairing: in a closed shell every edge is shared by exactly
            # two faces.
            try:
                bad = _B.manifold_violations(shape)
                # the exact sign, not float(...) <= 0: a solid whose true
                # volume is a hair above zero must not validate as inside-out
                # because the double rounded to 0.0
                if _B.volume(shape) <= 0:
                    bad = list(bad) + ["nonpositive-volume"]
            except ValueError as exc:
                # the kernel cannot DECIDE — the volume leaves the exact field
                # (a ring rotated off-axis). Neither ok nor a violation is an
                # honest answer, so refuse structurally rather than leak the
                # raw ValueError through the seam (a CRASH-class defect).
                _nope(f"validate({exc})", _K2)
            return ValidationReport(
                ok=not bad,
                checks={"method": "exact-edge-pairing",
                        "provenance": "exact",
                        "faces": len(shape.faces)},
                violations=list(bad))
        if isinstance(shape, DrilledSolid):
            bad = shape.watertight_violations()
            return ValidationReport(
                ok=not bad and shape.volume() > 0,
                checks={"method": "exact-composite",
                        "provenance": "exact",
                        "bores": len(shape.bores)},
                violations=list(bad))
        if not shape.polys:
            # the EMPTY solid is exactly what an annihilating boolean claims
            # to produce (#136) — reporting its emptiness as a violation was a
            # refusal standing in for an answer. The pardon is for the empty
            # solid ONLY: a degenerate solid still carrying polygons but no
            # volume falls through and keeps failing below.
            return ValidationReport(ok=True,
                                    checks={"method": "exact-line-coverage",
                                            "provenance": "exact",
                                            "polygons": 0, "empty": True},
                                    violations=[])
        bad = shape.watertight_violations()
        if shape.volume() <= 0:
            bad = list(bad) + ["nonpositive-volume"]
        return ValidationReport(ok=not bad,
                                checks={"method": "exact-line-coverage",
                                        "provenance": "exact",
                                        "polygons": len(shape.polys)},
                                violations=list(bad))

    def tessellate(self, shape, *, deflection: float = 0.2) -> dict[str, list]:
        from forgekernel import body as B

        deflection = _check_deflection("tessellate", deflection)
        from forgekernel.trimshell import TrimmedShell as _TShell
        if isinstance(shape, _TShell):
            # the trim boundary is only known as a certified cell enclosure,
            # so a watertight mesh would lie — but a CERTIFIED-SAFE view
            # exists: triangulate exactly the dyadic cells whose membership
            # is certain and show the SSI strip as explicit gap quads
            # (forgekernel.tess.trimmed_shell_mesh). The viewer gets an
            # honest picture of a freeform boolean; measures stay with
            # mass_props/validate. ``deflection`` is not honoured — the
            # grid is fixed by the boolean's own strip depth (5, matching
            # the dispatch above) so gaps align with strip cells 1:1.
            from forgekernel.tess import trimmed_shell_mesh
            return trimmed_shell_mesh(shape, depth=5)
        if isinstance(shape, B.Body):
            try:
                return B.tessellate(shape, deflection)
            except ValueError as exc:
                # an honest mesher refusal (30° trims are exact but not yet
                # meshable, a rotated spherical patch outside ℚ[π], …) must
                # cross the seam structured, not as a raw ValueError a caller
                # cannot tell from a bug (#137's side finding).
                _nope(f"tessellate({exc})", "K3.7 (canonical B-rep)")
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
        from gitcad import activity
        try:
            if len(loops) > 2:
                # Fast path (#11): a ruled stack's interface caps cancel
                # exactly, so the shell is buildable directly — same point
                # set as the BSP fold (tests/test_ruled_stack.py proves
                # exact volume/centroid equality against the fold), at
                # O(sections) instead of O(n²) splits. The watertight audit
                # is the same one kernel.boolean applies to the fold's
                # result; any violation falls back to the fold (the spec).
                from forgekernel.brep import ruled_stack
                try:
                    fast = ruled_stack(loops)
                    if not fast.watertight_violations():
                        return fast
                except ValueError:
                    pass  # non-monotonic z / mixed orientation → the fold
            out = None
            n_pieces = len(loops) - 1
            for i, ((la, za), (lb, zb)) in enumerate(zip(loops, loops[1:])):
                if n_pieces > 1:
                    # narrate long fused lofts on the live rail (#11): the
                    # watcher sees progress, not just an elapsed counter
                    activity.note(text=f"loft: fusing section {i + 1}/"
                                       f"{n_pieces} (exact BSP union)")
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
            # pass the polygon itself, not just its area: bbox/centroid are
            # exact closed forms over the profile's vertices and moments, and
            # forge refuses metrics on an area-only sweep (W8/W11 — the old
            # sqrt-area pad and wire centroid were silent wrong numbers)
            return fk_sweep(area, path, profile=loop)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="sweep", diagnostic="NotYetImplemented", kernel="ref"))

    def _shell_chamfered_box(self, shape, t):
        """Shell a box chamfered on all 12 edges, or return None (#120).

        A chamfered box is CONVEX, so its erosion is the intersection of its
        own half-spaces offset inward by t. The six face planes move t
        (rational); the twelve chamfer planes have normals of length √2, so
        each constant moves t·√2 — relative to the inset box the void is
        exactly the chamfered box of that inset with depth

            d' = d − (2 − √2)·t

        irrational but inside ℚ[√2], which F() already carries end to end
        (the napkin-ring widening). d' ≤ 0 means the offset chamfer plane
        never reaches the inset box and the void is the plain inset box —
        exact, not a refusal.

        Detection is SOUND, not structural: d is read off one chamfer plane,
        then the candidate is rebuilt with fk_chamfer and compared by exact
        symmetric difference — the box-predicate lesson.
        """
        from forgekernel import body as B
        from forgekernel import csg
        from forgekernel.brep import Solid
        from forgekernel.kernel import chamfer as fk_chamfer
        from forgekernel.kernel import translate
        from forgekernel.surd import SurdVal

        lo, hi = shape.bbox()
        d = None
        for p in shape.polys:
            n = tuple(Fraction(x) for x in p.plane.n)
            nz = [c for c in range(3) if n[c] != 0]
            if len(nz) == 2 and abs(n[nz[0]]) == abs(n[nz[1]]):
                scale = abs(n[nz[0]])
                corner = sum((Fraction(hi[c]) if n[c] > 0 else
                              -Fraction(lo[c])) * abs(n[c]) / scale
                             for c in nz)
                d = corner - Fraction(p.plane.d) / scale
                break
        if d is None or d <= 0:
            return None
        try:
            candidate = fk_chamfer(
                translate(Solid.box(hi[0] - lo[0], hi[1] - lo[1],
                                    hi[2] - lo[2]), lo[0], lo[1], lo[2]), d)
            if (csg.cut(shape, candidate).volume() != 0
                    or csg.cut(candidate, shape).volume() != 0):
                return None
        except (ArithmeticError, ValueError, TypeError, IndexError):
            return None
        dims = [Fraction(hi[c]) - Fraction(lo[c]) - 2 * t for c in range(3)]
        if min(dims) <= 0:
            _nope("shell(thickness leaves no cavity)", "K4.2",
                  predicate="cavity_is_positive",
                  measured={"smallest_dimension": float(min(dims) + 2 * t),
                            "thickness": float(t)})
        inset = translate(Solid.box(dims[0], dims[1], dims[2]),
                          lo[0] + t, lo[1] + t, lo[2] + t)
        dp = SurdVal(d - 2 * t, t, 2)             # d − 2t + t√2
        # SurdVal's rich comparisons are EXACT (sign of a ± b√d, no floats)
        if dp <= 0:
            void = inset
        else:
            # the void's flats shrink FASTER than the solid's (per unit t a
            # flat loses 2(√2 − 1) beyond its own inset): a flat that
            # vanishes changes the combinatorics, and the wedge construction
            # then no longer equals the half-space intersection — refuse
            # rather than guess. Exact: width = dim − 2d' as a SurdVal sign.
            for dim in dims:
                if SurdVal(dim - 2 * (d - 2 * t), -2 * t, 2) <= 0:
                    _nope("shell(chamfered box: the void's flat face "
                          "vanishes at this thickness — the offset chamfer "
                          "planes cross and the wedge construction stops "
                          "being the erosion)", "K4.2 (offset surfaces)",
                          predicate="void_flats_survive",
                          measured={"dim": float(dim), "d": float(d),
                                    "t": float(t)})
            try:
                void = fk_chamfer(inset, dp)
            except (ArithmeticError, ValueError) as exc:
                _nope(f"shell(chamfered box: {exc})",
                      "K4.2 (offset surfaces)")
        return _audited(B.Body(B.to_body(shape).faces
                      + tuple(B.Face(f.surface, f.loops, not f.sense)
                              for f in B.to_body(void).faces)),
                      "shell(chamfered box)")

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
        if len(bottom) != len(boundary):
            # The walk CLOSED without CONSUMING every boundary edge: the cap
            # has more than one loop (a disconnected solid, or a cap with a
            # hole). Chaining one loop successfully proved nothing — hollowing
            # just that component returned 1488 for a pair of 10³ boxes whose
            # true member-wise shell is 976, a silent wrong number.
            raise ValueError("shell: cap boundary is not a single loop — "
                             "K4.2 for multi-loop caps")
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
        # The vertex screen alone is SATISFIABLE by a non-box: a triangular
        # prism's vertices are a subset of the box corners, and fillet(all)
        # on one sailed through here and returned a RoundedBox holding twice
        # the prism's material — a silent wrong answer (found by the
        # rectilinear-prism failing test; chamfer only escaped because the
        # diagonal face's irrational normal happens to refuse downstream).
        # Ask the point-set question directly, like _is_axis_box does.
        if not _is_axis_box(self, shape, (lo, hi)):
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

        if isinstance(radius, (tuple, list)):
            # radius=(r0, r1): the variable-radius (linear taper) fillet —
            # the DISC-SWEEP semantic, the one member of the family the
            # tower holds (#134)
            return self._fillet_variable(shape, edges, radius)
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
                from forgekernel.quadric import _exact_bbox

                bossy = self._fillet_bossed_plate(shape, r)
                if bossy is not None:
                    return bossy
                # Rounding distributes over STRICTLY SEPARATED components
                # and over nothing else: members that touch are one
                # connected solid, and the member-wise answer rounds their
                # BURIED contact rims as if exposed while keeping the
                # contact patches as internal walls — a silent wrong number
                # (measured: 2938.67 pile vs 2949.45 composite on the
                # matrix's boss shape). Shell got this witness in #120;
                # fillet ran without it until #134. Closed bboxes are the
                # same conservative separation witness shell uses.
                boxes = [_exact_bbox(m) for m in shape.members]
                if any(b is None for b in boxes):
                    # _exact_bbox's None is a documented, legitimate answer
                    # ("cannot give bounds without leaving ℚ") — but the
                    # separation argument NEEDS the witness, so without it
                    # the honest answer is a refusal, not the TypeError this
                    # unpack used to raise (#10 composed census).
                    _nope("fillet(disjoint union: a member has no exact "
                          "bbox witness, so separation cannot be certified)",
                          "K5.4 (face blends)")
                for i in range(len(boxes)):
                    for j in range(i + 1, len(boxes)):
                        (alo, ahi), (blo, bhi) = boxes[i], boxes[j]
                        if all(alo[c] <= bhi[c] and blo[c] <= ahi[c]
                               for c in range(3)):
                            _nope("fillet(disjoint union: members touch — "
                                  "rounding the parts separately rounds "
                                  "their buried contact rims and misses "
                                  "the junction blend, so the pile answer "
                                  "is a different solid)",
                                  "K5.4 (face blends)",
                                  predicate="members_strictly_separated",
                                  measured={"member_pair": [i, j]},
                                  remedy="one boss standing on a boxy "
                                         "plate has the exact composite "
                                         "path; separate the members or "
                                         "reshape to that pattern")
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
            if not edges:
                r = (radius if isinstance(radius, Fraction)
                     else Fraction(str(radius)))
                out = self._fillet_hollow_box(shape, r)
                if out is None:
                    out = self._fillet_rect_prism(shape, r)
                if out is None:
                    out = self._fillet_chamfered_box(shape, r)
                if out is not None:
                    return out
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
        specs = self._box_edge_specs(shape, (lo, hi), edges)
        try:
            return FilletedBox(lo, hi, specs, radius)
        except ValueError as exc:
            if "exceeds" in str(exc):
                r = (radius if isinstance(radius, Fraction)
                     else Fraction(str(radius)))
                self._nope_blend_overflow(
                    f"fillet({exc})", r,
                    min(hi[c] - lo[c] for c in range(3)) / 2)
            raise KernelError(str(exc), FailureSignature(
                op="fillet", diagnostic="NotYetImplemented", kernel="ref"))

    def _box_edge_specs(self, shape, box, edges):
        """Map seam edge indices (the ``entities(shape, "edge")`` order) to
        FilletedBox ``(axis, side, side)`` specs — shared by the constant
        and variable selected-edge fillets."""
        lo, hi = box
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
        return specs

    def _fillet_variable(self, shape, edges, radius):
        """Variable-radius (LINEAR TAPER) fillet on selected straight box
        edges — the DISC-SWEEP semantic, the one member of the family the
        tower holds (#134).

        Two G1-valid surfaces answer to "linear variable fillet" and they
        sit on opposite sides of the exact-field boundary. The disc-sweep
        (each perpendicular slice is the 2D fillet of radius r(t)) is an
        oblique circular cone; its removed volume is polynomial and the
        result stays in ℚ[π]. The rolling ball (Parasolid/SolidWorks —
        envelope of spheres) slices to an ELLIPSE whose segment area
        carries the eccentric-anomaly span Δu linearly with cos Δu = b²
        (b the taper slope): by Niven, in-field only for b² ∈ {0, ½, 1},
        i.e. NEVER for a rational nonzero taper — the same Lindemann class
        as the cone fillet. So this kernel ships disc-sweep BY DEFINITION;
        the divergence table lives on ``VariableFilletedBox``'s docstring
        (0.33% of removed volume at b=0.1 up to 16.1% at b=0.8).

        volume/bbox/mass_props are exact; mesh and STEP refuse by name
        until the oblique-cone band lands (the FilletedPrism precedent).
        """
        from forgekernel.brep import Solid
        from forgekernel.quadric import VariableFilletedBox

        if len(radius) != 2:
            raise KernelError(
                f"fillet: a variable radius is (r0, r1), got {len(radius)} "
                "values",
                FailureSignature(op="fillet", diagnostic="BadInput",
                                 kernel="ref"))
        r0, r1 = (v if isinstance(v, Fraction) else Fraction(str(v))
                  for v in radius)
        if r0 == r1:
            # r0 == r1 IS the constant fillet — the same surface exactly,
            # and the constant machinery also meshes, so collapsing is
            # strictly better than a parallel representation
            return self.fillet(shape, edges, r0)
        if not isinstance(shape, Solid):
            _nope("fillet(variable radius on a curved representation: a "
                  "tapered blend along a circular rim is neither a torus "
                  "nor a cone, and the rolling-ball reading is "
                  "transcendental for every rational taper — cos Δu = b², "
                  "Niven)", "K5.3 (variable blends beyond straight edges)",
                  predicate="variable_radius_needs_a_straight_edge",
                  measured={"representation": type(shape).__name__},
                  remedy="taper only straight box edges, or use a constant "
                         "radius")
        box = self._box_check(shape)
        if box is None:
            _nope("fillet(variable radius on a non-box planar solid)",
                  "K5.3 (variable blends beyond straight edges)",
                  predicate="variable_radius_needs_a_straight_edge",
                  remedy="taper straight edges of an axis-aligned box, or "
                         "use a constant radius")
        if not edges:
            _nope("fillet(variable radius on ALL edges: every pair of box "
                  "edges shares a vertex, and the blend between two taper "
                  "cones needs the variable corner patch — a sphere octant "
                  "at matched vertex radii would be C0-watertight but not "
                  "G1 against the cones)", "K5.3 (variable corner patch)",
                  predicate="variable_edges_share_a_vertex",
                  remedy="select pairwise non-adjacent edges")
        lo, hi = box
        specs = self._box_edge_specs(shape, box, edges)
        try:
            return VariableFilletedBox(
                lo, hi, [(ax, sa, sb, r0, r1) for ax, sa, sb in specs])
        except ValueError as exc:
            if "exceeds" in str(exc):
                self._nope_blend_overflow(
                    f"fillet({exc})", max(r0, r1),
                    min(hi[c] - lo[c] for c in range(3)) / 2)
            if "corner patch" in str(exc):
                _nope(f"fillet({exc})", "K5.3 (variable corner patch)",
                      predicate="variable_edges_share_a_vertex",
                      remedy="select pairwise non-adjacent edges")
            raise KernelError(str(exc), FailureSignature(
                op="fillet", diagnostic="NotYetImplemented", kernel="ref"))

    def _hollow_box_spec(self, shape):
        """(lo, hi, ilo, ihi) of a closed hollow box — a box with one fully
        enclosed box cavity, what ``shell(box)`` builds — or None.

        Detection is SOUND, not structural: the candidate outer-minus-inner
        is rebuilt from the two vertex boxes and compared by exact symmetric
        difference (both boolean cuts must have volume exactly zero) — the
        lesson of the box predicate that was satisfiable by non-boxes.
        """
        from forgekernel import csg
        from forgekernel.brep import Solid

        lo, hi = shape.bbox()
        inner = [v for p in shape.polys for v in p.verts
                 if all(lo[c] < v[c] < hi[c] for c in range(3))]
        if not inner:
            return None
        ilo = tuple(min(v[c] for v in inner) for c in range(3))
        ihi = tuple(max(v[c] for v in inner) for c in range(3))
        if any(ihi[c] <= ilo[c] for c in range(3)):
            return None
        try:
            outer_box = Solid.box(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2],
                                  "fhb.outer").translated(lo)
            inner_box = Solid.box(ihi[0] - ilo[0], ihi[1] - ilo[1],
                                  ihi[2] - ilo[2], "fhb.inner").translated(ilo)
            candidate = csg.cut(outer_box, inner_box)
            if (csg.cut(shape, candidate).volume() != 0
                    or csg.cut(candidate, shape).volume() != 0):
                return None
        except (ArithmeticError, ValueError, TypeError, IndexError):
            return None            # not a shape the exact engine can settle
        return lo, hi, ilo, ihi

    def _shell_hollow_box(self, shape, t):
        """Shell a CLOSED HOLLOW BOX, or return None (#120).

        Erosion of the wall by t: the complement of the material is (outside
        the outer box) ∪ (the cavity), so the void is the inset outer box
        minus the cavity DILATED by a ball of t — and a box dilated by a ball
        is exactly a ROUNDED BOX (Minkowski sum), which the kernel already
        has. No torus appears: the cavity's edges are convex from the
        complement's side, so the dilation rounds them with quarter cylinders
        and corner octants.

        Regimes, decided exactly per face gap g = wall − 2t:

        * every g > 0: the rounded box sits strictly inside the inset box —
          the void is the six full inset flats plus the rounded box flipped.
        * every g == 0 (the bench probe: wall 2, t 1): the flat void regions
          vanish. The void degenerates to the corner-and-edge LATTICE: its
          outer faces are square FRAMES (inset flats with the rounded box's
          core rectangle as an inner ring — the tangency lines), and the
          rounded box contributes only its 12 quarter cylinders and 8
          octants, flipped. The frame's inner-ring segments are exactly the
          cylinders' straight tangency edges, so pairing closes.
        * any g < 0: the rounded box is clipped by an inset plane — the
          clipped quarter cylinder's cross-section is a circular segment
          whose area carries an arcsin, outside every exact field. Refusing
          is the finished answer. Mixed 0/positive gaps are a buildable but
          unbuilt hybrid (frame on some faces only) — an honest gap.
        """
        from forgekernel import body as B
        from forgekernel.brep import Solid
        from forgekernel.quadric import RoundedBox

        spec = self._hollow_box_spec(shape)
        if spec is None:
            return None
        lo, hi, ilo, ihi = spec
        gaps = [(ilo[c] - t) - (lo[c] + t) for c in range(3)] \
            + [(hi[c] - t) - (ihi[c] + t) for c in range(3)]
        if any(g < 0 for g in gaps):
            _nope("shell(hollow box: a wall thinner than 2t clips the "
                  "dilated cavity against the inset wall — the clipped "
                  "quarter cylinder's volume carries an arcsin, outside "
                  "every exact field)", "K4.2 (offset surfaces)",
                  predicate="wall_at_least_two_t",
                  measured={"min_wall": float(2 * t + min(gaps)),
                            "t": float(t)},
                  remedy=f"use t at most {float((2 * t + min(gaps)) / 2):.4g}")
        if any(g == 0 for g in gaps) and any(g > 0 for g in gaps):
            _nope("shell(hollow box: walls of exactly 2t mixed with thicker "
                  "ones need frame faces on some sides only — not built yet)",
                  "K4.2 (offset surfaces)")
        rb = RoundedBox(ihi[0] - ilo[0] + 2 * t, ihi[1] - ilo[1] + 2 * t,
                        ihi[2] - ilo[2] + 2 * t, t,
                        (ilo[0] - t, ilo[1] - t, ilo[2] - t))
        rb_faces = B.from_rounded_box(rb).faces
        inset = Solid.box(hi[0] - lo[0] - 2 * t, hi[1] - lo[1] - 2 * t,
                          hi[2] - lo[2] - 2 * t, "shb.inset").translated(
                              (lo[0] + t, lo[1] + t, lo[2] + t))
        box_faces = B.from_solid(inset).faces
        if all(g > 0 for g in gaps):
            void_faces = box_faces + tuple(
                B.Face(f.surface, f.loops, not f.sense) for f in rb_faces)
        else:
            # the lattice: frames outside, tangent quadrics inside
            void_faces = tuple(
                _frame_face(f, ilo, ihi) for f in box_faces) + tuple(
                B.Face(f.surface, f.loops, not f.sense) for f in rb_faces
                if not isinstance(f.surface, B.Plane))
        return _audited(B.Body(B.to_body(shape).faces
                      + tuple(B.Face(f.surface, f.loops, not f.sense)
                              for f in void_faces)), "shell(hollow box)")

    def _fillet_hollow_box(self, shape, r):
        """fillet(all) on a CLOSED HOLLOW BOX — a box with a fully-enclosed
        box cavity (what ``shell(box)`` builds) — or None if ``shape`` is not
        one.

        The outer edges round into the rounded box; the cavity's edges are
        CONCAVE, so their blends ADD material and the cavity becomes exactly
        the rounded box of its own dimensions. Containment is strict for any
        wall thickness t > 0: a point within r of the cavity core has every
        per-axis deficit to the OUTER core smaller by t, so the cavity's
        rounded form lies strictly inside the outer one and the two face sets
        never meet. The B-rep is therefore the outer rounded box's 26 faces
        plus the cavity's 26 sense-flipped, and the volume is the difference
        of the two Steiner forms (for the probe's 20³/t=2/r=1: 3856 + 12π,
        Monte-Carlo membership 3893.63 ± 0.63 against 3893.699).

        Detection is SOUND, not structural: a candidate outer-minus-inner is
        rebuilt from the two vertex boxes and compared by exact symmetric
        difference (both boolean cuts must have volume exactly zero) — the
        lesson of the box predicate that was satisfiable by non-boxes.
        """
        from forgekernel import body as B
        from forgekernel.quadric import RoundedBox

        spec = self._hollow_box_spec(shape)
        if spec is None:
            return None
        lo, hi, ilo, ihi = spec
        if 2 * r > min(ihi[c] - ilo[c] for c in range(3)):
            _nope("fillet(shelled box: 2r exceeds the cavity's smallest "
                  "dimension, so the cavity blends would collide)", "K5.2")
        try:
            outer_rb = RoundedBox(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2],
                                  r, lo)
            cavity_rb = RoundedBox(ihi[0] - ilo[0], ihi[1] - ilo[1],
                                   ihi[2] - ilo[2], r, ilo)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="fillet", diagnostic="NotYetImplemented", kernel="ref"))
        faces = (B.from_rounded_box(outer_rb).faces
                 + tuple(B.Face(f.surface, f.loops, not f.sense)
                         for f in B.from_rounded_box(cavity_rb).faces))
        return _audited(B.Body(faces), "fillet(shelled box)")

    def _fillet_rect_prism(self, shape, r):
        """fillet(all) on a rectilinear right prism, or None if ``shape`` is
        not one. The profile is recovered from the bottom cap's boundary
        edges, then the identification is made SOUND by rebuilding the prism
        and requiring the exact symmetric difference to vanish — only then is
        the profile handed to ``FilletedPrism``, whose own guards decide
        expressibility (its docstring carries the mathematics and the
        Monte-Carlo verification record)."""
        from forgekernel import csg
        from forgekernel.brep import Solid
        from forgekernel.quadric import FilletedPrism

        lo, hi = shape.bbox()
        z0, z1 = lo[2], hi[2]
        if z1 <= z0:
            return None
        if any(v[2] not in (z0, z1) for p in shape.polys for v in p.verts):
            return None
        bottom = [p for p in shape.polys
                  if all(v[2] == z0 for v in p.verts)]
        if not bottom:
            return None
        # boundary = directed edges whose reverse never appears
        counts: dict = {}
        for p in bottom:
            vs = [(v[0], v[1]) for v in p.verts]
            for a, b in zip(vs, vs[1:] + vs[:1]):
                counts[(a, b)] = counts.get((a, b), 0) + 1
        nxt: dict = {}
        for (a, b), n in counts.items():
            if counts.get((b, a), 0) == 0:
                if a in nxt:
                    return None            # pinched vertex: not a simple loop
                nxt[a] = b
        if not nxt:
            return None
        start = next(iter(nxt))
        loop = [start]
        cur = nxt[start]
        while cur != start:
            loop.append(cur)
            cur = nxt.get(cur)
            if cur is None or len(loop) > len(nxt):
                return None
        if len(loop) != len(nxt):
            return None                    # more than one boundary loop
        # merge vertices the triangulation left on straight runs
        merged = []
        m = len(loop)
        for i in range(m):
            pv, v, nx = loop[(i - 1) % m], loop[i], loop[(i + 1) % m]
            e0 = (v[0] - pv[0], v[1] - pv[1])
            e1 = (nx[0] - v[0], nx[1] - v[1])
            if e0[0] * e1[1] - e0[1] * e1[0] == 0 \
                    and e0[0] * e1[0] + e0[1] * e1[1] > 0:
                continue
            merged.append(v)
        if len(merged) < 3:
            return None
        try:
            candidate = Solid.prism(merged, z1 - z0, "frp").translated(
                (Fraction(0), Fraction(0), z0))
            if (csg.cut(shape, candidate).volume() != 0
                    or csg.cut(candidate, shape).volume() != 0):
                return None
        except (ArithmeticError, ValueError, TypeError, IndexError):
            return None            # not a shape the exact engine can settle
        try:
            return FilletedPrism(merged, z0, z1 - z0, r)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="fillet", diagnostic="NotYetImplemented", kernel="ref"))

    def _chamfered_box_spec(self, shape):
        """``(lo, dims, d)`` when ``shape`` IS ``chamfer(box(dims), d)`` at
        ``lo``, else None. The setback is INFERRED (top-face inset) and the
        identification made SOUND the only way that has survived review:
        rebuild the claimed solid and require the exact symmetric difference
        to vanish both ways (the ``_is_axis_box`` lesson — a property test can
        always be satisfied by something that is not the thing)."""
        from forgekernel import csg
        from forgekernel.brep import Solid
        from forgekernel.kernel import chamfer as _fk_chamfer

        lo, hi = shape.bbox()
        dims = tuple(hi[c] - lo[c] for c in range(3))
        top = [v for p in shape.polys for v in p.verts if v[2] == hi[2]]
        if not top:
            return None
        d = hi[0] - max(v[0] for v in top)
        if d <= 0 or any(2 * d >= dims[c] for c in range(3)):
            return None
        # cheap exact screen (additive over polys, so NOT sufficient alone)
        if shape.volume() != (dims[0] * dims[1] * dims[2]
                              - 2 * d * d * (dims[0] + dims[1] + dims[2])
                              + 6 * d ** 3):
            return None
        try:
            cand = _fk_chamfer(
                Solid.box(dims[0], dims[1], dims[2], "cbx").translated(lo), d)
            if (csg.cut(shape, cand).volume() != 0
                    or csg.cut(cand, shape).volume() != 0):
                return None
        except (ArithmeticError, ValueError, TypeError, IndexError):
            return None            # not a shape the exact engine can settle
        return lo, dims, d

    def _fillet_chamfered_box(self, shape, r):
        """fillet(all) on a chamfered box, or None if ``shape`` is not one —
        exact in ℚ(√2,√3)[π] (the last #121 cell; biquadratic, one surd wider
        than the single-d tower). The mathematics, the Steiner/opening
        decomposition, the per-corner-patch trap and the Monte-Carlo record
        all live on ``FilletedChamferedBox`` (forge quadric.py), whose guards
        decide expressibility; a guard failure on a DETECTED chamfered box is
        an honest named refusal, not a fall-through to "fillet(non-box)"."""
        from forgekernel.quadric import FilletedChamferedBox

        spec = self._chamfered_box_spec(shape)
        if spec is None:
            return None
        lo, dims, d = spec
        try:
            return FilletedChamferedBox(lo, dims, d, r)
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

    def _straddle_cut(self, a, tool):
        """#123 — an axis-aligned box tool whose footprint STRADDLES a bore.

        Returns the result, or ``None`` when this is not that family, in which
        case ``boolean`` carries on to the paths that are right for whatever it
        actually is. Written against the canonical ``Body`` (ADR-0021), so it
        serves the counterbore (a ``DrilledSolid``) and the bored boss (a
        ``DisjointUnion`` around a lathe) out of one implementation rather than
        one per representation.

        Two refusals, deliberately different. ``NotchOutsideField`` means the
        tool genuinely straddles a bore and the answer is not in any exact
        field this kernel has — a permanent boundary, reported by name with the
        offsets that DO work. Plain ``NotchRefused`` means "not this family",
        and is silent, because the guards downstream are correct for the shapes
        it does not cover and must keep their say.
        """
        from forgekernel import body as B
        from forgekernel.brep import Solid
        from forgekernel.notch import NotchOutsideField, NotchRefused, notch_cut
        from forgekernel.quadric import _exact_bbox

        if not isinstance(tool, Solid):
            return None
        tb = _exact_bbox(tool)
        if tb is None:
            return None
        (x0, y0, z0), (x1, y1, z1) = tb
        # the tool must BE its bounding box: a prism that only fills part of it
        # would remove less than the notch this builds
        if tool.volume() != (x1 - x0) * (y1 - y0) * (z1 - z0):
            return None
        try:
            src = B.to_body(a)
        except (ValueError, AttributeError, TypeError):
            return None
        try:
            out = notch_cut(src, (x0, x1, y0, y1), z0, z1)
        except NotchOutsideField as exc:
            _nope("boolean.cut(prism straddling a bore)", "K3.7",
                  predicate="crossing_is_at_a_twelfth",
                  measured={"faces": len(src.faces)},
                  remedy=str(exc))
        except NotchRefused:
            return None
        return _audited(out, "boolean.cut", require_body=True)

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
        of revolution — exactly, with no surface-surface intersection.

        Issue #14: the specialised reconstruction demands the bore stay
        strictly inside EVERY wall — including the INNER wall of a tube — so
        widening an existing bore, stepping a counterbore, or truncating a
        cone past its apex radius all refused despite being exactly
        representable. Where it refuses, the general profile subtraction
        (``_profile_boolean``) runs: subtracting the tool's rectangle from
        the profile polygon. ONE loop out is a lathe again; anything else
        (a genuine internal cavity, a severed part) re-raises the
        specialised path's refusal, which names the reason.
        """
        from forgekernel.quadric import RevolveSolid

        prof, cx, cy = self._lathe_profile(a)
        if prof is None or (tool.cx, tool.cy) != (cx, cy):
            return None                      # not a lathe, or not coaxial
        try:
            out = _bore_lathe_profile(prof, Fraction(tool.r),
                                      Fraction(tool.z0), Fraction(tool.z1))
        except KernelError as refusal:
            rect = [(Fraction(0), Fraction(tool.z0)),
                    (Fraction(tool.r), Fraction(tool.z0)),
                    (Fraction(tool.r), Fraction(tool.z1)),
                    (Fraction(0), Fraction(tool.z1))]
            loops = _profile_boolean(prof, rect, "cut")
            if loops is not None and len(loops) == 1 \
                    and _axis_runs(loops[0]) <= 1:
                # >1 axis runs = the removed band is walled off from the
                # outside by material above AND below — an internal cavity
                # wearing a single loop (the slit down the axis), which is
                # exactly what the specialised path's refusal is about
                return _audited(RevolveSolid(loops[0], cx, cy),
                                "boolean.cut(lathe rebore)")
            raise refusal
        return RevolveSolid(out, cx, cy)

    def _fuse_lathe(self, a, b):
        """Union of two OVERLAPPING coaxial solids of revolution: the union
        of their (r, z) profiles, exactly, when it stays one loop (#14).

        Only consulted after ``DisjointUnion`` has refused, so tangent and
        separated pairs keep their existing representation; returns None
        for anything that is not a coaxial pair of lathe profiles, or whose
        profile union is not a single loop.
        """
        from forgekernel.quadric import RevolveSolid

        pa, cxa, cya = self._lathe_profile(a)
        pb, cxb, cyb = self._lathe_profile(b)
        if pa is None or pb is None or (cxa, cya) != (cxb, cyb):
            return None
        loops = _profile_boolean(pa, pb, "union")
        if loops is None or len(loops) != 1:
            return None
        return _audited(RevolveSolid(loops[0], cxa, cya),
                        "boolean.union(coaxial lathe profiles)")

    def _clip_lathe_zband(self, body, tool):
        """Intersect a solid of revolution with an axis-aligned box that
        contains its whole xy footprint: a z-band clip of the PROFILE — the
        split op's half-space boolean, exactly (#14).

        Returns None when this is not that family (the caller falls through
        to its generic refusals). A box that clips in x or y refuses HERE,
        naming the real boundary: keeping part of a lathe's cross-section
        breaks its axial symmetry, and no (r, z) profile can say that.
        """
        from forgekernel.brep import Solid
        from forgekernel.quadric import RevolveSolid, _exact_bbox

        prof, cx, cy = self._lathe_profile(body)
        if prof is None or not isinstance(tool, Solid):
            return None
        bb = _exact_bbox(tool)
        if bb is None or not _is_axis_box(self, tool, bb):
            return None
        try:
            rmax = max(Fraction(r) for r, _ in prof)
            zvals = [Fraction(z) for _r, z in prof]
            cx, cy = Fraction(cx), Fraction(cy)
        except (TypeError, ValueError):
            return None                      # surd-valued profile: not here
        (tx0, ty0, tz0), (tx1, ty1, tz1) = bb
        if not (tx0 <= cx - rmax and tx1 >= cx + rmax
                and ty0 <= cy - rmax and ty1 >= cy + rmax):
            _nope("boolean.intersect(the tool clips a lathe in x/y, which "
                  "would break its axial symmetry)", "K2.2",
                  predicate="split_plane_is_z_normal",
                  measured={"tool_xy": [float(tx0), float(ty0),
                                        float(tx1), float(ty1)],
                            "lathe_reach": float(rmax)},
                  remedy="only a z-normal split keeps a solid of revolution "
                         "a solid of revolution; split with normal 'z', or "
                         "rebuild the body in a planar representation before "
                         "an x/y split")
        zmin, zmax = min(zvals), max(zvals)
        if tz0 <= zmin and tz1 >= zmax:
            return body                      # the box contains it whole
        if tz1 <= zmin or tz0 >= zmax:
            _nope("boolean.intersect(the z band keeps nothing of the lathe)",
                  "K2.2", predicate="split_keeps_material",
                  measured={"band": [float(tz0), float(tz1)],
                            "lathe_z": [float(zmin), float(zmax)]},
                  remedy="move the split plane inside the body's z range")
        rect = [(Fraction(0), tz0), (rmax + 1, tz0),
                (rmax + 1, tz1), (Fraction(0), tz1)]
        loops = _profile_boolean(prof, rect, "intersect")
        if loops is None:
            return None
        if len(loops) != 1:
            _nope(f"boolean.intersect(the z band leaves {len(loops)} "
                  "separate profile loops, not one solid)", "K2.2",
                  predicate="clip_is_one_loop",
                  remedy="split where the body's profile is connected")
        return _audited(RevolveSolid(loops[0], cx, cy),
                        "boolean.intersect(lathe z-band)")

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

        A bore going STRAIGHT THROUGH keeps every void corner sharp. A BLIND
        floor or a counterbore SHOULDER adds a reentrant rim, and the erosion
        around that rim is the quarter TORUS of points within t of the rim
        circle (#120): tube radius t, k0=3 span=1, carried (ρ, Z−t)→(ρ+t, Z).
        The construction: scaffold the void as a stepped DrilledSolid whose
        flat parts are already correct, then replace each scaffold step with
        the fillet (``_erode_rim_to_torus``). The regimes that CLIP the torus
        (a floor within (t, 2t] of the base, a shoulder narrower than t) have
        an arcsin in their volume — transcendental, so those refusals are
        final answers, not gaps. A floor within t of the base needs no torus
        at all: the void sits entirely above it and the through-bore collar
        formula is exact.
        """
        from collections import defaultdict

        from forgekernel import body as B
        from forgekernel.brep import Solid
        from forgekernel.kernel import translate
        from forgekernel.quadric import Cyl, DrilledSolid

        box = self._box_check(shape.base)
        if box is None:
            return None                 # a general prism base: K4.1's inset
        (bx0, by0, bz0), (bx1, by1, bz1) = box
        smallest = min(bx1 - bx0, by1 - by0, bz1 - bz0)
        if smallest <= 2 * t:
            _nope("shell(thickness leaves no cavity)", "K4.2",
                  predicate="cavity_is_positive",
                  measured={"smallest_dimension": float(smallest),
                            "thickness": float(t)},
                  remedy=(f"t must be under {float(smallest) / 2:.4g} mm — half "
                          "the smallest dimension"))

        # -- coaxial stacks → z-bands with the outermost radius per band ------
        groups = defaultdict(list)
        for c in shape.bores:
            z0, z1 = max(Fraction(c.z0), bz0), min(Fraction(c.z1), bz1)
            if z1 > z0:
                groups[(Fraction(c.cx), Fraction(c.cy))].append(
                    (z0, z1, Fraction(c.r)))
        scaffold: list = []        # cylinders to cut into the inset box
        sites: list = []           # (cx, cy, Z, ρ): reentrant rims → tori
        for (cx, cy), cyls in groups.items():
            zs = sorted({z for c in cyls for z in (c[0], c[1])})
            bands = []
            for za, zb in zip(zs, zs[1:]):
                mid = (za + zb) / 2
                rs = [r for (z0, z1, r) in cyls if z0 <= mid <= z1]
                if rs:
                    bands.append((za, zb, max(rs)))
            if not bands:
                continue
            if any(bands[i][1] != bands[i + 1][0]
                   for i in range(len(bands) - 1)):
                _nope("shell(drilled solid: a coaxial stack with a z-gap is "
                      "two voids, not one)", "K4.2 (offset surfaces)")
            open_bot = bands[0][0] == bz0
            open_top = bands[-1][1] == bz1
            if not open_top and not open_bot:
                _nope("shell(drilled solid: a bore sealed inside the material "
                      "erodes to a floating internal void)",
                      "K4.2 (offset surfaces)")
            if not open_top:
                _nope("shell(drilled solid: a bore entering from the BOTTOM "
                      "is the mirrored construction, not built yet)",
                      "K4.2 (offset surfaces)",
                      predicate="stack_opens_upward",
                      measured={"stack_z": [float(bands[0][0]),
                                            float(bands[-1][1])],
                                "solid_z": [float(bz0), float(bz1)]})
            for (_a, zb0, r0), (_a2, _b2, r1) in zip(bands, bands[1:]):
                if r1 <= r0:
                    _nope("shell(drilled solid: a stack that narrows upward "
                          "is the mirrored construction, not built yet)",
                          "K4.2 (offset surfaces)")
                if r1 - r0 <= t:
                    _nope("shell(drilled solid: a shoulder narrower than t "
                          "clips the fillet torus against the inner collar — "
                          "the clipped sector's volume carries an arcsin, "
                          "outside every exact field)",
                          "K4.2 (offset surfaces)",
                          predicate="shoulder_wider_than_t",
                          measured={"stack_xy": [float(cx), float(cy)],
                                    "step": float(r1 - r0), "t": float(t)},
                          remedy=f"widen the counterbore step past {float(t):.4g}")
            start0 = bz0
            if not open_bot:
                zf, rf = bands[0][0], bands[0][2]
                h = zf - bz0
                if h <= t:
                    # the void's floor (bz0+t) is at or above the bore's: the
                    # erosion never sees the floor rim and the THROUGH collar
                    # is exact. Refusing this regime was simply a wrong answer.
                    start0 = bz0
                elif h <= 2 * t:
                    _nope("shell(drilled solid: a floor between t and 2t "
                          "above the base clips the fillet torus against the "
                          "void's floor — the clipped sector's volume carries "
                          "an arcsin, outside every exact field)",
                          "K4.2 (offset surfaces)",
                          predicate="floor_clears_two_t",
                          measured={"stack_xy": [float(cx), float(cy)],
                                    "floor_height": float(h), "t": float(t)},
                          remedy=(f"make the floor sit below {float(bz0 + t):.4g} "
                                  f"or above {float(bz0 + 2 * t):.4g} in z"))
                else:
                    scaffold.append(Cyl(cx, cy, rf, zf - t, zf))
                    sites.append((cx, cy, zf, rf))
                    start0 = zf
            for j, (za, zb, r) in enumerate(bands):
                start = start0 if j == 0 else bands[j - 1][1]
                end = zb - t if j < len(bands) - 1 else bz1
                # the void clamps a cap-reaching band by t at that cap
                eff_s = start + t if start == bz0 else start
                eff_e = end - t if end == bz1 else end
                if eff_e <= eff_s:
                    _nope("shell(drilled solid: features closer than t along "
                          "the bore axis clip each other's fillets)",
                          "K4.2 (offset surfaces)")
                scaffold.append(Cyl(cx, cy, r + t, start, end))
                if j < len(bands) - 1:
                    Z, rho = zb, bands[j + 1][2]
                    scaffold.append(Cyl(cx, cy, rho, Z - t, Z))
                    sites.append((cx, cy, Z, rho))

        inner = translate(Solid.box(bx1 - bx0 - 2 * t, by1 - by0 - 2 * t,
                                    bz1 - bz0 - 2 * t),
                          bx0 + t, by0 + t, bz0 + t)
        void = DrilledSolid(inner, [])
        try:
            for c in scaffold:
                # DrilledSolid.cut is what checks each collar still fits
                # inside the cavity and clears its neighbours, so a collar
                # that would break out refuses there rather than here. The
                # scaffold's widest cylinder per stack (r_max + t) bounds
                # every fillet bulge, so its clearance covers the tori too.
                void = void.cut(c)
        except ValueError as exc:
            _nope(f"shell(drilled solid: the collar does not fit — {exc})",
                  "K4.2")
        faces = list(B.from_drilled(void).faces)
        for (cx, cy, Z, rho) in sites:
            faces = _erode_rim_to_torus(faces, cx, cy, Z, rho, t)
        return _audited(B.Body(B.to_body(shape).faces
                      + tuple(B.Face(f.surface, f.loops, not f.sense)
                              for f in faces)), "shell(drilled solid)")

    def _bossed_plate_spec(self, shape):
        """Classify a two-member ``DisjointUnion`` as ONE boss standing on a
        boxy plate, or return None.

        Returns ``(plate, box, cx, cy, R, zb, bt, bore)`` with ``bore`` either
        ``None`` or ``(r, floor_z)`` for a coaxial blind bore open at the boss
        top. Shared by the shell (#120) and fillet (#134) composite paths so
        the two cannot drift apart on what "the bossed-plate pattern" means.
        The plate gate is ``_box_check`` — the sound rebuild-and-compare
        predicate, not a corner probe."""
        from forgekernel.brep import Solid
        from forgekernel.quadric import Cyl, RevolveSolid

        if len(shape.members) != 2:
            return None
        plate = boss = None
        for a, b in ((shape.members[0], shape.members[1]),
                     (shape.members[1], shape.members[0])):
            if isinstance(a, Solid) and isinstance(b, (Cyl, RevolveSolid)):
                plate, boss = a, b
                break
        if plate is None:
            return None
        box = self._box_check(plate)
        if box is None:
            return None
        bore = None
        if isinstance(boss, Cyl):
            cx, cy, R = Fraction(boss.cx), Fraction(boss.cy), Fraction(boss.r)
            zb, bt = Fraction(boss.z0), Fraction(boss.z1)
        else:
            loop = [(Fraction(r), Fraction(z)) for r, z in boss.loop]
            cx, cy = Fraction(boss.cx), Fraction(boss.cy)
            if (len(loop) == 4 and loop[0][0] == 0 and loop[3][0] == 0
                    and loop[1][0] == loop[2][0] > 0
                    and loop[0][1] == loop[1][1] < loop[2][1] == loop[3][1]):
                R, zb, bt = loop[1][0], loop[0][1], loop[2][1]
            elif (len(loop) == 6 and loop[0][0] == 0 and loop[5][0] == 0
                    and loop[1][0] == loop[2][0] > 0
                    and loop[3][0] == loop[4][0] > 0
                    and loop[3][0] < loop[1][0]
                    and loop[0][1] == loop[1][1] < loop[2][1] == loop[3][1]
                    and loop[0][1] < loop[4][1] == loop[5][1] < loop[2][1]):
                R, zb, bt = loop[1][0], loop[0][1], loop[2][1]
                bore = (loop[3][0], loop[4][1])       # (r, floor z)
            else:
                return None
        if zb != box[1][2]:
            return None                # the boss does not stand on the plate
        return plate, box, cx, cy, R, zb, bt, bore

    def _shell_bossed_plate(self, shape, t):
        """Shell a plate with ONE boss standing on it (bored or not), or None.

        A DisjointUnion whose members TOUCH is one connected solid, and
        shelling the members separately is NOT the shell of the composite:
        the void connects through the plate under the boss, and the exposed
        plate-top rim around the boss base erodes to a quarter torus swept
        INSIDE the plate (centre circle (R, plate_top), k0=2 span=1). Before
        #120 the boss probe returned the pile answer — 60.9 mm³ heavy.

        The void, bottom to top: the inset plate slab, its top punched with
        the circle (R, plate_top − t); the boss-base rim arc; the boss
        column's wall at R−t; and if the boss carries a coaxial blind bore
        open at its top, the bore collar at r+t, the bore-floor quarter torus
        (k0=3 span=1) and the floor disk of radius r — THE TRAP again: r,
        not r+t.

        Closed forms pinned in tests/golden/test_shell_bossed_plate.py, both
        verified against an independent Monte-Carlo membership test before
        this was built.
        """
        from forgekernel import body as B
        from forgekernel.brep import Solid

        spec = self._bossed_plate_spec(shape)
        if spec is None:
            return None
        plate, box, cx, cy, R, zb, bt, bore = spec
        (px0, py0, pz0), (px1, py1, pz1) = box
        margin = min(cx - px0, px1 - cx, cy - py0, py1 - cy)
        if margin - t <= R:
            _nope("shell(bossed plate: the boss-base fillet needs the void's "
                  "slab to clear the boss by more than t laterally)",
                  "K4.2 (offset surfaces)",
                  predicate="boss_clears_inset_walls",
                  measured={"margin": float(margin), "R": float(R),
                            "t": float(t)})
        if pz1 - pz0 <= 2 * t:
            _nope("shell(bossed plate: a plate no thicker than 2t clips the "
                  "boss-base fillet against the slab floor — arcsin, outside "
                  "every exact field)", "K4.2 (offset surfaces)",
                  predicate="plate_thicker_than_two_t",
                  measured={"plate": float(pz1 - pz0), "t": float(t)})
        if R <= t or bt - pz1 <= t:
            _nope("shell(bossed plate: the boss is too small to hollow at "
                  "this t)", "K4.2 (offset surfaces)",
                  predicate="boss_exceeds_t",
                  measured={"R": float(R), "boss_height": float(bt - pz1),
                            "t": float(t)})
        if bore is not None:
            rb, zf = bore
            if rb + t >= R - t:
                _nope("shell(bossed plate: the bore collar meets the boss "
                      "void's wall — the clipped fillet carries an arcsin, "
                      "outside every exact field)", "K4.2 (offset surfaces)",
                      predicate="collar_clears_boss_wall",
                      measured={"r": float(rb), "R": float(R), "t": float(t)})
            if zf - t < pz1 or zf >= bt - t:
                _nope("shell(bossed plate: the bore floor must clear the "
                      "boss base by t and the boss top by more than t)",
                      "K4.2 (offset surfaces)",
                      predicate="floor_within_boss",
                      measured={"floor_z": float(zf),
                                "boss_z": [float(pz1), float(bt)],
                                "t": float(t)})

        one, zero = Fraction(1), Fraction(0)
        naxis = (zero, zero, one)
        slab = Solid.box(px1 - px0 - 2 * t, py1 - py0 - 2 * t,
                         pz1 - pz0 - 2 * t, "sbp.slab").translated(
                             (px0 + t, py0 + t, pz0 + t))
        vfaces = []
        for f in B.from_solid(slab).faces:
            # the slab's planes are UNNORMALIZED (n=(0,0,784), d=1568), so
            # match the top cap by direction sign and vertex height, the way
            # from_drilled matches caps
            if (isinstance(f.surface, B.Plane)
                    and f.surface.n[0] == 0 and f.surface.n[1] == 0
                    and f.surface.n[2] > 0
                    and Fraction(f.loops[0].edges[0].v0[2]) == pz1 - t):
                f = B.Face(f.surface,
                           f.loops + (B.Loop((_rim_edge(cx, cy, pz1 - t, R),)),),
                           f.sense)
            vfaces.append(f)
        vfaces.append(B.Face(B.Torus((cx, cy, pz1), naxis, R, t, 2, 1),
                             (B.Loop((_rim_edge(cx, cy, pz1 - t, R),
                                      _rim_edge(cx, cy, pz1, R - t))),),
                             False))
        vfaces.append(B.Face(B.Cylinder((cx, cy, pz1), naxis, R - t),
                             (B.Loop((_rim_edge(cx, cy, pz1, R - t),
                                      _rim_edge(cx, cy, bt - t, R - t))),),
                             True))
        top_loops = [B.Loop((_rim_edge(cx, cy, bt - t, R - t),))]
        if bore is not None:
            rb, zf = bore
            top_loops.append(B.Loop((_rim_edge(cx, cy, bt - t, rb + t),)))
            vfaces.append(B.Face(B.Cylinder((cx, cy, zf), naxis, rb + t),
                                 (B.Loop((_rim_edge(cx, cy, zf, rb + t),
                                          _rim_edge(cx, cy, bt - t, rb + t))),),
                                 False))
            vfaces.append(B.Face(B.Torus((cx, cy, zf), naxis, rb, t, 3, 1),
                                 (B.Loop((_rim_edge(cx, cy, zf - t, rb),
                                          _rim_edge(cx, cy, zf, rb + t))),),
                                 False))
            vfaces.append(B.Face(B.Plane(naxis, zf - t),
                                 (B.Loop((_rim_edge(cx, cy, zf - t, rb),)),),
                                 True))
        vfaces.append(B.Face(B.Plane(naxis, bt - t), tuple(top_loops), True))
        return _audited(B.Body(B.to_body(shape).faces
                      + tuple(B.Face(f.surface, f.loops, not f.sense)
                              for f in vfaces)), "shell(bossed plate)")

    def _fillet_bossed_plate(self, shape, r):
        """fillet(all) of a plate with ONE boss standing on it, or None (#134).

        A ``DisjointUnion`` whose members TOUCH is one connected solid, and
        filleting the members separately is NOT the fillet of the composite:
        the boss's base rim is BURIED, so rounding it removes material that is
        genuinely there, and the concatenated faces keep the contact patches
        as internal walls. Measured on the matrix's boss shape (30×30×3 plate,
        r=4 h=6 boss, r=1): the pile answer is 2464 + 425π/3 + 3π² ≈ 2938.67
        where the composite is 2464 + 473π/3 − π² ≈ 2949.45.

        The composite, bottom to top: the ROUNDED plate (every plate edge is
        exposed), its top flat punched at R+r; the CONCAVE junction quarter
        torus — the reentrant-edge precedent from the planar-prism path, a
        blend that ADDS material, k0=2 span=1 about the tube circle
        (R+r, pz1+r), sense False because the material lies outside the tube;
        the boss wall from pz1+r to bt−r; the convex top-rim quarter torus
        (k0=0, tube circle (R−r, bt−r)); and the top cap at radius R−r. A
        coaxial blind bore open at the top keeps its SHARP rims — the
        DrilledSolid precedent: a hole is a hole, fillet(all) does not chase
        rims into it (the lathe path's concave-corner rule, uniformly).

        Junction term by exact Pappus: V_add = πr(2Rr+r²) − π²r²(R+r)/2 +
        2πr³/3 — it needs π², which is why the closed forms are PiPolys. Both
        golden cells were verified against 2D quadrature and a 20M-sample
        Monte-Carlo membership test BEFORE this construction was written
        (z = +1.13 plain, +0.94 bored at 3σ; tests/golden/test_blend_family).
        """
        from forgekernel import body as B
        from forgekernel.kernel import fillet_box

        spec = self._bossed_plate_spec(shape)
        if spec is None:
            return None
        plate, box, cx, cy, R, zb, bt, bore = spec
        (px0, py0, pz0), (px1, py1, pz1) = box
        margin = min(cx - px0, px1 - cx, cy - py0, py1 - cy)
        if r <= 0:
            # fillet_box accepts r=0 and the degenerate RoundedBox then
            # divides by r in from_rounded_box — a raw ZeroDivisionError
            # through the seam (found by probing, not by luck)
            raise KernelError(
                f"fillet radius must be positive, got {float(r)}",
                FailureSignature(op="fillet", diagnostic="BadInput",
                                 kernel="ref"))
        if r >= R:
            self._nope_blend_overflow(
                "fillet(bossed plate: the top-rim blend consumes the whole "
                "cap)", r, R, extra={"R": float(R)})
        if zb + r >= bt - r:
            self._nope_blend_overflow(
                "fillet(bossed plate: the junction and top-rim blends meet "
                "on the boss wall — the clipped blend carries an arccos, "
                "outside every exact field)", r, (bt - zb) / 2,
                extra={"boss_height": float(bt - zb)})
        if R + r >= margin - r:
            self._nope_blend_overflow(
                "fillet(bossed plate: the junction ring must clear the "
                "plate's own edge blends)", r, margin - R - r,
                extra={"margin": float(margin), "R": float(R)})
        if bore is not None and bore[0] >= R - r:
            self._nope_blend_overflow(
                "fillet(bossed plate: the bore mouth meets the top-rim "
                "blend's tangency circle)", r, R - bore[0],
                extra={"bore_r": float(bore[0]), "R": float(R)})
        try:
            rounded = fillet_box(px1 - px0, py1 - py0, pz1 - pz0, r,
                                 (px0, py0, pz0))
        except ValueError as exc:
            if "exceeds" in str(exc):
                self._nope_blend_overflow(
                    f"fillet(bossed plate: {exc})", r,
                    min(px1 - px0, py1 - py0, pz1 - pz0) / 2)
            raise KernelError(str(exc), FailureSignature(
                op="fillet", diagnostic="NotYetImplemented", kernel="ref"))
        one, zero = Fraction(1), Fraction(0)
        naxis = (zero, zero, one)
        faces = []
        for f in B.to_body(rounded).faces:
            # the plate's top flat carries the junction ring as an inner
            # loop — matched by direction sign and vertex height, the way
            # the shell composite matches its slab cap
            if (isinstance(f.surface, B.Plane)
                    and f.surface.n[0] == 0 and f.surface.n[1] == 0
                    and f.surface.n[2] > 0
                    and Fraction(f.loops[0].edges[0].v0[2]) == pz1):
                f = B.Face(f.surface,
                           f.loops + (B.Loop((_rim_edge(cx, cy, pz1,
                                                        R + r),)),),
                           f.sense)
            faces.append(f)
        faces.append(B.Face(B.Torus((cx, cy, pz1 + r), naxis, R + r, r, 2, 1),
                            (B.Loop((_rim_edge(cx, cy, pz1, R + r),
                                     _rim_edge(cx, cy, pz1 + r, R))),),
                            False))
        faces.append(B.Face(B.Cylinder((cx, cy, pz1 + r), naxis, R),
                            (B.Loop((_rim_edge(cx, cy, pz1 + r, R),
                                     _rim_edge(cx, cy, bt - r, R))),),
                            True))
        faces.append(B.Face(B.Torus((cx, cy, bt - r), naxis, R - r, r, 0, 1),
                            (B.Loop((_rim_edge(cx, cy, bt - r, R),
                                     _rim_edge(cx, cy, bt, R - r))),),
                            True))
        cap_loops = [B.Loop((_rim_edge(cx, cy, bt, R - r),))]
        if bore is not None:
            rb, zf = bore
            cap_loops.append(B.Loop((_rim_edge(cx, cy, bt, rb),)))
            faces.append(B.Face(B.Cylinder((cx, cy, zf), naxis, rb),
                                (B.Loop((_rim_edge(cx, cy, zf, rb),
                                         _rim_edge(cx, cy, bt, rb))),),
                                False))
            faces.append(B.Face(B.Plane(naxis, zf),
                                (B.Loop((_rim_edge(cx, cy, zf, rb),)),),
                                True))
        faces.append(B.Face(B.Plane(naxis, bt), tuple(cap_loops), True))
        return _audited(B.Body(tuple(faces)), "fillet(bossed plate)",
                        require_body=True)

    def _nope_blend_overflow(self, op, r, room, *, extra=None):
        """The blend-overflow refusal, structured (#134).

        A blend radius exceeding the room its face offers clips the quarter
        arc to a circular segment either way the overflow is resolved
        (keep-edge trims it, roll-over rides over it), and a segment's area
        is r²·arccos(d/r) − d√(r²−d²) — the arccos of an algebraic number,
        transcendental by Lindemann except at the two Niven ratios. So the
        honest answer is this refusal, never a silently clamped radius, and
        never widening ``Torus(k0, span)`` to general angles (that is the
        edit that lets the transcendental in — §12's warning)."""
        measured = {"radius": float(r), "room": float(room)}
        if room > 0:
            measured["ratio"] = float(Fraction(room) / Fraction(r))
        measured.update(extra or {})
        _nope(op, "K5.4 (blend overflow)", predicate="blend_overflow",
              measured=measured,
              remedy="reduce the radius to fit the adjacent face, or use "
                     "d/r = 1/2 or √3/2 — the two Niven ratios whose "
                     "clipped segment stays in ℚ[√3][π] (meshing gated on "
                     "K3.7 twelfths)")

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
                    # SHELLING A DRILLED SOLID NEEDS A COLLAR (the void must
                    # stop r+t from the bore's wall — "shell the base, then
                    # re-drill" was silently 170 mm³ light), and the collar
                    # construction needs a box base to erode exactly. A
                    # general prism base is K4.1's certified inset.
                    _nope("shell(drilled solid: only a box base can be "
                          "eroded around its bores yet)",
                          "K4.2 (offset surfaces)")
                return DrilledSolid(self.shell(shape.base, (), thickness), [])
            if isinstance(shape, DisjointUnion):
                from forgekernel import body as B
                from forgekernel.quadric import _exact_bbox

                bossy = self._shell_bossed_plate(shape, t)
                if bossy is not None:
                    return bossy
                # Erosion distributes over STRICTLY SEPARATED components and
                # over nothing else: members that touch are one connected
                # solid whose void runs through the contact, and the pile
                # answer is a silent wrong number (the boss probe was 60.9 mm³
                # heavy before the composite path above). Closed bboxes are a
                # conservative witness for separation.
                boxes = [_exact_bbox(m) for m in shape.members]
                if any(b is None for b in boxes):
                    # same contract as fillet's separation witness above:
                    # None is _exact_bbox's honest "no bounds in ℚ" answer,
                    # and without the witness the refusal is the answer —
                    # never the TypeError this unpack used to raise (#10).
                    _nope("shell(disjoint union: a member has no exact bbox "
                          "witness, so separation cannot be certified)",
                          "K4.2 (offset surfaces)")
                for i in range(len(boxes)):
                    for j in range(i + 1, len(boxes)):
                        (alo, ahi), (blo, bhi) = boxes[i], boxes[j]
                        if all(alo[c] <= bhi[c] and blo[c] <= ahi[c]
                               for c in range(3)):
                            _nope("shell(disjoint union: members touch — "
                                  "the composite's erosion connects through "
                                  "the contact, so shelling the parts "
                                  "separately is a different solid)",
                                  "K4.2 (offset surfaces)")
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
            t_exact = (thickness if isinstance(thickness, Fraction)
                       else Fraction(str(thickness)))
            hollow = self._shell_hollow_box(shape, t_exact)
            if hollow is not None:
                return hollow
            chamf = self._shell_chamfered_box(shape, t_exact)
            if chamf is not None:
                return chamf
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
        # The box void below is only the right void when the base IS its
        # bounding box: every logical face axis-aligned AND lying on the
        # bbox itself. Anything else (a loft, a stepped union, a cut
        # result) would have its sloped or interior walls carved away by
        # the box — dogfood #20 measured a frustum "shell" at 1480 mm³,
        # geometry_verified, where the true 2 mm shell is ~3900 mm³.
        # Refuse exactly like the closed-shell paths do, instead of
        # answering with a different solid.
        # The remedy is the route the #24 reporter reached by hand: build the
        # inner surface as its own solid and cut it, which is exact today.
        _open_remedy = (
            "an open shell of this base needs a true offset surface (K4.2). "
            "Build the inner solid explicitly and cut it: for a loft, re-loft "
            "the section polygons inset by the wall thickness (dropping the "
            "inner sections below the open face so the crown keeps thickness) "
            "and boolean-cut it from the body. For a rectilinear base, shell "
            "the box-shaped sub-solids separately and union them.")
        for (plane_key, _), frags in ordered:
            n = plane_key[:3]
            axis = max(range(3), key=lambda c: abs(n[c]))
            if any(n[c] != 0 for c in range(3) if c != axis):
                _nope("shell(open shell of a non-box base: face normals "
                      "are not axis-aligned — the box void would cut the "
                      "walls away)", "K4.2 (offset surfaces)",
                      predicate="open_shell_base_is_its_bounding_box",
                      measured={"face_normal": [float(c) for c in n]},
                      remedy=_open_remedy)
            coord = frags[0].verts[0][axis]
            if coord != lo[axis] and coord != hi[axis]:
                _nope("shell(open shell of a non-box base: a face lies "
                      "inside the bounding box — the box void would cut "
                      "the walls away)", "K4.2 (offset surfaces)",
                      predicate="open_shell_base_is_its_bounding_box",
                      measured={"axis": "xyz"[axis], "face_at": float(coord),
                                "bbox_span": [float(lo[axis]),
                                              float(hi[axis])]},
                      remedy=_open_remedy)
        void_lo = [lo[c] + t for c in range(3)]
        void_hi = [hi[c] - t for c in range(3)]
        for idx in remove_faces:
            if isinstance(idx, bool) or not isinstance(idx, int):
                # Docket R7: a string like 'top' used to reach the comparison
                # below and leak a raw TypeError through the seam. Face NAMES
                # are not a form this kernel speaks — indices into
                # entities(shape, "face") are (the Document layer maps stable
                # ids to them; ADR-0003 keeps names/ids out of the kernel).
                raise KernelError(
                    f"shell: remove_faces must be integer face indices into "
                    f"entities(shape, 'face'), got {idx!r} — named faces are "
                    "not supported at the kernel seam",
                    FailureSignature(op="shell", diagnostic="BadInput",
                                     kernel="ref"))
            if idx < 0 or idx >= len(ordered):
                # A negative index would silently wrap to the END of the
                # enumeration (Python list semantics) — an ordinal accident,
                # not an answer.
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

    def draft(self, shape, faces, angle_deg=None, pull=(0, 0, 1),
              neutral_z=0.0, tan=None, parting_z=None):
        """Molding draft (#133): tilt the selected walls about the neutral
        plane — or split them at a parting plane into two half-drafts — by
        an exact rational tangent.

        ``tan`` is the SPEC (an exact Fraction; 0.1 means 1/10);
        ``angle_deg`` is sugar that snaps to the exact binary Fraction of a
        float tangent. ``faces``: indices into entities(shape, "face");
        empty/None drafts every wall. A cap whose normal is parallel to the
        pull cannot be drafted — that is BadInput, not a missing capability.
        Exact cells: rectilinear prisms stay in ℚ; a cylinder wall drafts
        to a Cone (ℚ[π]), with a parting line to a two-cone AxisStack.
        Named walls: sphere/torus (the drafted surface leaves every exact
        field); lathe/cone tan-addition and non-axis-aligned prism edges
        arrive at K2.3.
        """
        from forgekernel.brep import Solid, draft_prism
        from forgekernel.quadric import (AxisStack, Cone, Cyl, RevolveSolid,
                                         Sphere)

        if (angle_deg is None) == (tan is None):
            raise KernelError(
                "draft wants exactly one of angle_deg (float sugar) or tan "
                "(the exact rational tangent of the draft angle)",
                FailureSignature(op="draft", diagnostic="BadInput",
                                 kernel="ref"))
        t = _exact_in("draft", tan, "tangent") if tan is not None else \
            Fraction(math.tan(math.radians(angle_deg)))
        if tuple(pull) != (0, 0, 1):
            _nope("draft(tilted pull)", "K2.3")
        pz = None if parting_z is None else \
            _exact_in("draft", parting_z, "parting_z")
        nz = _exact_in("draft", neutral_z, "neutral_z")
        if pz is not None and nz != 0 and nz != pz:
            raise KernelError(
                "a parting-line draft's neutral plane IS the parting plane "
                f"— got neutral_z={neutral_z} with parting_z={parting_z}; "
                "drop neutral_z",
                FailureSignature(op="draft", diagnostic="BadInput",
                                 kernel="ref"))
        if isinstance(shape, Cyl):
            return self._draft_cyl(shape, faces, t, nz, pz)
        if isinstance(shape, Solid):
            walls = self._draft_wall_pairs(shape, faces)
            try:
                return draft_prism(shape, t, neutral_z=nz, parting_z=pz,
                                   drafted_walls=walls)
            except ValueError as exc:
                msg = str(exc)
                diag = ("NotYetImplemented" if "K2.3" in msg or "K2" in msg
                        else "BadInput")
                raise KernelError(msg, FailureSignature(
                    op="draft", diagnostic=diag, kernel="ref"))
        if isinstance(shape, Sphere):
            # not a backlog item: tilting a sphere wall about a pull line
            # yields a surface that is no quadric, and its volume needs the
            # arcsin class — outside every ℚ[√d][π] (ADR-0019). The refusal
            # IS the finished answer.
            _nope("draft(sphere wall — the drafted surface is no quadric; "
                  "no exact field holds it)", "exact-field boundary",
                  predicate="draft_of_curved_quadric_wall",
                  remedy="draft the mating planar walls instead, or accept "
                         "the undrafted sphere")
        if isinstance(shape, (Cone, RevolveSolid)):
            _nope("draft(lathe/cone wall — straight profile segments stay "
                  "cones by tan-addition tan(α+δ)=(tanα+t)/(1−tanα·t))",
                  "K2.3",
                  predicate="draft_of_slanted_lathe_segment",
                  remedy="rational-in-rational-out; arrives with the "
                         "profile-segment editor")
        _nope(f"draft({type(shape).__name__})", "K2.3")

    def _draft_cyl(self, shape, faces, t, nz, pz):
        """Cylinder wall → Cone frustum (single pull) or a two-cone
        AxisStack (parting line): r(z) = r − t·(z−nz) or r − t·|z−zp|."""
        from forgekernel.quadric import AxisStack, Cone

        for idx in faces or []:
            if isinstance(idx, bool) or not isinstance(idx, int) or \
                    not 0 <= idx <= 2:
                raise KernelError(
                    f"draft: face index {idx!r} out of range for a cylinder "
                    "(0=wall, 1=top cap, 2=bottom cap)",
                    FailureSignature(op="draft", diagnostic="BadInput",
                                     kernel="ref"))
            if idx != 0:
                raise KernelError(
                    "draft: a cylinder cap's normal is parallel to the pull "
                    "direction — only the wall (face 0) drafts",
                    FailureSignature(op="draft", diagnostic="BadInput",
                                     kernel="ref"))
        r, cx, cy, z0, z1 = shape.r, shape.cx, shape.cy, shape.z0, shape.z1

        def wall_radius(z, about):
            rz = r - t * abs(z - about) if pz is not None else \
                r - t * (z - about)
            if rz <= 0:
                raise KernelError(
                    f"draft consumes the cylinder wall: r(z={float(z):g}) = "
                    f"{float(rz):g} ≤ 0 — reduce the tangent or the band "
                    "height",
                    FailureSignature(op="draft", diagnostic="BadInput",
                                     kernel="ref"))
            return rz

        if pz is None:
            return Cone(cx, cy, wall_radius(z0, nz), wall_radius(z1, nz),
                        z0, z1)
        if not z0 < pz < z1:
            raise KernelError(
                f"draft: parting plane z={float(pz):g} must lie strictly "
                f"inside the cylinder z∈({float(z0):g},{float(z1):g})",
                FailureSignature(op="draft", diagnostic="BadInput",
                                 kernel="ref"))
        return AxisStack(cx, cy, [
            Cone(cx, cy, wall_radius(z0, pz), r, z0, pz),
            Cone(cx, cy, r, wall_radius(z1, pz), pz, z1)])

    def _draft_wall_pairs(self, shape, faces):
        """Map face indices (entities enumeration) to the xy endpoint pairs
        of the walls they name; None/empty = all walls. A cap — normal
        parallel to the pull — is BadInput, not a capability gap."""
        if not faces:
            return None
        ordered = sorted(shape.logical_faces().items(),
                         key=lambda kv: (kv[0][1], kv[0][0]))
        pairs = []
        for idx in faces:
            if isinstance(idx, bool) or not isinstance(idx, int):
                raise KernelError(
                    f"draft: faces must be integer indices into "
                    f"entities(shape, 'face'), got {idx!r}",
                    FailureSignature(op="draft", diagnostic="BadInput",
                                     kernel="ref"))
            if idx < 0 or idx >= len(ordered):
                raise KernelError(
                    f"draft: face index {idx} out of range",
                    FailureSignature(op="draft",
                                     diagnostic="FaceIndexOutOfRange",
                                     kernel="ref"))
            (_key, _src), frags = ordered[idx]
            xy = {(v[0], v[1]) for p in frags for v in p.verts}
            if len(xy) != 2:
                raise KernelError(
                    f"draft: face {idx} is not a vertical wall — its normal "
                    "is parallel to the pull direction (a cap cannot be "
                    "drafted about its own normal)",
                    FailureSignature(op="draft", diagnostic="BadInput",
                                     kernel="ref"))
            pairs.append(frozenset(xy))
        return pairs

    # -- direct edits (#132): move_face / offset_face / delete_face -----------
    #
    # SolidWorks-parity direct editing, feature-level per ADR-0022: the
    # DOCUMENT records which face (lineage-stable id) and by how much; the
    # kernel receives concrete indices into entities(shape, "face") and
    # implements the edit by RE-PARAMETERIZING the owning representation.
    # Sign convention shared by all editors: a positive offset moves the face
    # along its OUTWARD material normal, i.e. adds material (so a bore wall
    # offset by -1 ENLARGES the bore: its outward normal points at the axis).

    def move_face(self, shape, faces, translate):
        """Translate the named faces; every neighbour re-solves exactly.

        For a planar face only the normal component of ``translate`` changes
        the carrier plane (the in-plane part is the identity on it — that is
        the mathematics, not a clamp); for a bore wall an in-plane translate
        moves the hole and a z component refuses (move the cap or shoulder
        instead)."""
        t = tuple(_exact_in("move_face", v, "translate component")
                  for v in translate)
        if len(t) != 3:
            raise KernelError(
                "move_face: translate must be a 3-vector",
                FailureSignature(op="move_face", diagnostic="BadInput",
                                 kernel="ref"))
        return self._direct_edit("move_face", shape, faces, ("move", t))

    def offset_face(self, shape, faces, distance):
        """Offset the named faces along their outward normals (+ adds
        material); neighbours re-solve exactly, blends refuse by name."""
        d = _exact_in("offset_face", distance, "distance")
        return self._direct_edit("offset_face", shape, faces, ("offset", d))

    def delete_face(self, shape, faces, absorb=None):
        """Delete the named faces and HEAL the boundary. Two heal classes
        exist (the derivation's taxonomy): generator-removal (un-drill,
        sharpen, un-chamfer — exact, returns to the pre-feature field) and
        neighbour-extension (re-solve the neighbours to their new meet).
        Where TWO heals are valid (a counterbore shoulder) the op refuses
        listing both and requires ``absorb=<face index>`` naming the
        neighbour that grows."""
        if absorb is not None and (isinstance(absorb, bool)
                                   or not isinstance(absorb, int)):
            raise KernelError(
                f"delete_face: absorb must be a face index, got {absorb!r}",
                FailureSignature(op="delete_face", diagnostic="BadInput",
                                 kernel="ref"))
        return self._direct_edit("delete_face", shape, faces,
                                 ("delete", absorb))

    def _face_indices(self, op, shape, faces) -> list[int]:
        ents = self.entities(shape, "face")
        try:
            items = list(faces)
        except TypeError:
            items = None
        if not items:
            raise KernelError(
                f"{op}: name at least one face index into "
                "entities(shape, 'face')",
                FailureSignature(op=op, diagnostic="BadInput", kernel="ref"))
        idxs: list[int] = []
        for idx in items:
            if isinstance(idx, bool) or not isinstance(idx, int):
                raise KernelError(
                    f"{op}: faces must be integer indices into "
                    f"entities(shape, 'face'), got {idx!r}",
                    FailureSignature(op=op, diagnostic="BadInput",
                                     kernel="ref"))
            if idx < 0 or idx >= len(ents):
                raise KernelError(
                    f"{op}: face index {idx} out of range "
                    f"(shape has {len(ents)} faces)",
                    FailureSignature(op=op, diagnostic="FaceIndexOutOfRange",
                                     kernel="ref"))
            idxs.append(idx)
        if len(set(idxs)) != len(idxs):
            raise KernelError(
                f"{op}: duplicate face index in {idxs}",
                FailureSignature(op=op, diagnostic="BadInput", kernel="ref"))
        return idxs

    def _direct_edit(self, op, shape, faces, action):
        from forgekernel.brep import Solid
        from forgekernel.quadric import (Cyl, DisjointUnion, DrilledSolid,
                                         RevolveSolid, RoundedBox)

        idxs = self._face_indices(op, shape, faces)
        if isinstance(shape, DisjointUnion):
            return self._edit_disjoint(op, shape, idxs, action)
        if isinstance(shape, DrilledSolid):
            return self._edit_drilled(op, shape, idxs, action)
        if isinstance(shape, Solid):
            return self._edit_planar(op, shape, idxs, action)
        if isinstance(shape, Cyl):
            return self._edit_cyl(op, shape, idxs, action)
        if isinstance(shape, RevolveSolid):
            return self._edit_lathe(op, shape, idxs, action)
        if isinstance(shape, RoundedBox):
            return self._edit_rounded(op, shape, idxs, action)
        _nope(f"{op}({type(shape).__name__})", _K6,
              remedy="direct edits cover planar solids, drilled solids, "
                     "cylinders, lathes and rounded boxes so far")

    # -- planar solids: vertex re-solve under the topology law ---------------

    def _edit_planar(self, op, shape, idxs, action):
        ordered = sorted(shape.logical_faces().items(),
                         key=lambda kv: (kv[0][1], kv[0][0]))
        if action[0] == "delete":
            return self._heal_prism(op, shape, ordered, idxs, action[1])
        return self._planar_move(op, shape, ordered, idxs, action)

    def _planar_move(self, op, shape, ordered, idxs, action):
        """Move/offset selected planar faces by re-solving every incident
        vertex from its (updated) incident planes — exact Cramer, with the
        boundary graph REQUIRED unchanged (any edge collapse, face merge or
        orientation flip refuses with the measured fraction to the event)."""
        from forgekernel.brep import Polygon, Solid
        from forgekernel.exact import Plane, dot, sub
        from forgekernel.surd import exact_sqrt

        kind, payload = action

        def face_delta(pl):
            """The exact d-shift for THIS polygon's plane object (scales with
            its |n|, so fragments of one logical face stay coplanar)."""
            if kind == "move":
                return dot(pl.n, payload)
            nn = dot(pl.n, pl.n)
            ln = exact_sqrt(nn)
            if not isinstance(ln, Fraction):
                _nope(f"{op}(a face with a non-Pythagorean normal has no "
                      "rational unit normal to offset along)", _K6,
                      remedy="use move_face with a rational translate along "
                             "the normal — that is exact for any plane")
            return payload * ln

        selected = {}                    # canonical -> set of sources
        for idx in idxs:
            (ckey, source), frags = ordered[idx]
            selected.setdefault(ckey, set()).add(source)
        # a coplanar sibling that is NOT selected would be torn off its plane
        for (ckey, source), _f in ordered:
            if ckey in selected and source not in selected[ckey]:
                _nope(f"{op}(face shares its plane with unselected face "
                      f"{source!r} — coplanar faces move together)", _K6,
                      predicate="topology_event",
                      remedy="select every face on the plane")

        # representative plane + delta per selected canonical (orientation
        # comes from an actual fragment, which is CCW around OUTWARD)
        rep = {}
        for (ckey, source), frags in ordered:
            if ckey in selected and ckey not in rep:
                pl = frags[0].plane
                rep[ckey] = (pl, face_delta(pl))
        if all(d == 0 for _pl, d in rep.values()):
            return shape                 # exact identity (in-plane move)

        # EVENT 1 — parallel-plane merge, caught BEFORE any construction
        # (the exact-coplanar rebuild crashes 'collinear points'; past it a
        # valid WRONG solid builds with a silently flipped face)
        def canon_shift(ckey):
            """How far the canonical d of this face travels (0 if unmoved)."""
            if ckey not in rep:
                return Fraction(0)
            pl, delta = rep[ckey]
            return Plane(pl.n, pl.d + delta).canonical()[3] - ckey[3]

        for ckey in rep:
            dc = canon_shift(ckey)
            if dc == 0:
                continue
            for (okey, osrc), _frags in ordered:
                if okey == ckey or okey[:3] != ckey[:3]:
                    continue             # not parallel: can never merge
                den = dc - canon_shift(okey)
                if den == 0:
                    continue             # moving in lockstep: gap constant
                s = (okey[3] - ckey[3]) / den
                if 0 <= s <= 1:
                    _nope(f"{op}(face would merge with the parallel face "
                          f"{osrc!r} — a topology event, not a bigger move)",
                          _K6, predicate="topology_event",
                          measured={"event": "faces_coplanar",
                                    "fraction_to_event": float(s)},
                          remedy=f"stop short of {float(s):.4g} of the "
                                 "requested move, or model the merge "
                                 "explicitly")

        # vertex re-solve: every vertex on a selected plane moves to the
        # meet of its incident planes with the selected ones shifted
        incident: dict = {}
        for p in shape.polys:
            ck = p.plane.canonical()
            for v in p.verts:
                incident.setdefault(v, {}).setdefault(ck, p.plane)
        moved: dict = {}
        for v, planes in incident.items():
            if not (set(planes) & set(selected)):
                continue
            if len(planes) < 3:
                _nope(f"{op}(a boundary vertex lies on only {len(planes)} "
                      "planes — a fragmented (T-junction) boundary cannot "
                      "be re-solved)", "K6.2 (direct edits on booleans)",
                      remedy="rebuild the feature instead of editing the "
                             "boolean output directly")
            plist = [Plane(pl.n, pl.d + face_delta(pl)) if ck in selected
                     else pl for ck, pl in planes.items()]
            from itertools import combinations

            newv = None
            for trio in combinations(plist, 3):
                newv = _meet_three_planes(*trio)
                if newv is not None:
                    break
            if newv is None:
                _nope(f"{op}(a vertex's incident planes are degenerate "
                      "after the edit)", _K6, predicate="topology_event")
            if any(dot(pl.n, newv) != pl.d for pl in plist):
                _nope(f"{op}(a vertex on more than three faces would SPLIT "
                      "— its planes no longer meet in one point)", _K6,
                      predicate="topology_event",
                      measured={"event": "vertex_split",
                                "planes": len(plist)},
                      remedy="edit the generating feature instead; this "
                             "vertex's faces are tied by construction")
            moved[v] = newv

        # EVENT 2 — edge collapse or reversal (exact, with the fraction of
        # the requested move at which the edge dies: positions are affine in
        # the move, so f(s) = e0·e(s) is linear)
        newpolys = []
        for p in shape.polys:
            nv = [moved.get(v, v) for v in p.verts]
            if nv == p.verts:
                newpolys.append(p)
                continue
            n_ = len(nv)
            for i in range(n_):
                a0, b0 = p.verts[i], p.verts[(i + 1) % n_]
                e0 = sub(b0, a0)
                f0 = dot(e0, e0)
                if f0 == 0:
                    continue
                e1 = sub(nv[(i + 1) % n_], nv[i])
                f1 = dot(e0, e1)
                if f1 <= 0:
                    s = f0 / (f0 - f1) if f0 != f1 else Fraction(1)
                    _nope(f"{op}(an edge of face {p.source!r} "
                          f"{'collapses' if f1 == 0 else 'reverses'} — the "
                          "face beyond it would flip its material side)",
                          _K6, predicate="topology_event",
                          measured={"event": "edge_collapse",
                                    "fraction_to_event": float(s)},
                          remedy=f"stop short of {float(s):.4g} of the "
                                 "requested move")
            nrm = _newell(nv)
            if dot(nrm, p.plane.n) <= 0:
                _nope(f"{op}(face {p.source!r} flips its material side)",
                      _K6, predicate="topology_event",
                      measured={"event": "face_flip"})
            for i in range(n_):
                ea = sub(nv[(i + 1) % n_], nv[i])
                eb = sub(nv[(i + 2) % n_], nv[(i + 1) % n_])
                from forgekernel.exact import cross

                if dot(cross(ea, eb), nrm) < 0:
                    _nope(f"{op}(face {p.source!r} would go non-convex — "
                          "its re-solved loop self-intersects)", _K6,
                          predicate="topology_event",
                          measured={"event": "face_split"})
            try:
                newpolys.append(Polygon(nv, p.source))
            except ValueError:
                _nope(f"{op}(face {p.source!r} degenerates)", _K6,
                      predicate="topology_event")
        out = Solid(newpolys)

        # POST-CHECKS: the edited faces still exist, the boundary is closed,
        # the volume stayed positive — the silent-clamp trap, refused
        new_faces = out.logical_faces()
        for ckey, (pl, delta) in rep.items():
            nk = Plane(pl.n, pl.d + delta).canonical()
            for source in selected[ckey]:
                frags = new_faces.get((nk, source))
                if not frags or all(f.area2() == 0 for f in frags):
                    _nope(f"{op}(face {source!r} is absent from the result "
                          "— consumed by the edit)", _K6,
                          predicate="face_absent_after_edit")
        bad = out.watertight_violations()
        if bad:
            _nope(f"{op}(the re-solved boundary is not closed: {bad[0]})",
                  _K6, predicate="topology_event",
                  measured={"violations": len(bad)})
        if out.volume() <= 0:
            _nope(f"{op}(the edit turns the solid inside out)", _K6,
                  predicate="topology_event",
                  measured={"volume": float(out.volume())})
        return out

    def _heal_prism(self, op, shape, ordered, idxs, absorb):
        """delete_face on a planar solid — the neighbour-extension heal,
        implemented where it is exact: a right z-prism's side wall (its two
        neighbour walls extend to their sharp meet — the un-chamfer). Caps
        refuse with a boundedness PROOF (the walls are parallel to the cap
        normal and never close)."""
        from forgekernel.brep import Polygon, Solid, _ear_clip, _loop_area2
        from forgekernel.exact import vec

        if absorb is not None:
            raise KernelError(
                f"{op}: absorb applies to drilled-solid heals, not planar "
                "walls (the neighbour-extension heal is unique)",
                FailureSignature(op=op, diagnostic="BadInput", kernel="ref"))
        if len(idxs) != 1:
            _nope(f"{op}(several planar faces at once)", _K6,
                  remedy="delete one wall per edit")
        horiz = [(key, frags) for key, frags in ordered
                 if key[0][0] == 0 and key[0][1] == 0]
        sides = [(key, frags) for key, frags in ordered
                 if key[0][2] == 0]
        if len(horiz) != 2 or len(horiz) + len(sides) != len(ordered):
            _nope(f"{op}(planar solid that is not a right z-prism)",
                  "K6.2 (direct edits on booleans)",
                  remedy="direct heals cover prisms; rebuild the feature "
                         "otherwise")
        (k_lo, f_lo), (k_hi, f_hi) = sorted(horiz, key=lambda kf: kf[0][0][3])
        z0, z1 = k_lo[0][3], k_hi[0][3]
        src_lo, src_hi = k_lo[1], k_hi[1]
        target_key = ordered[idxs[0]][0]
        if target_key in (k_lo, k_hi):
            _nope(f"{op}(a prism cap has no bounded heal: every wall is "
                  "parallel to its normal, so the extensions never close)",
                  _K6, predicate="heal_unbounded",
                  remedy="delete a side wall, or remove the feature that "
                         "made the cap")
        # side walls -> footprint segments, oriented so outward is right
        segs = []
        for (ck, src), frags in sides:
            if len(frags) != 1 or len(frags[0].verts) != 4:
                _nope(f"{op}(fragmented side wall {src!r})",
                      "K6.2 (direct edits on booleans)",
                      remedy="rebuild the feature instead of editing the "
                             "boolean output directly")
            quad = frags[0]
            foot = sorted({(v[0], v[1]) for v in quad.verts
                           if v[2] == z0})
            if len(foot) != 2:
                _nope(f"{op}(side wall {src!r} is not a prism wall)",
                      "K6.2 (direct edits on booleans)")
            a, b = foot
            nx, ny = quad.plane.n[0], quad.plane.n[1]
            # CCW loop: outward normal of edge a->b is (dy, -dx)
            if _sign((b[1] - a[1]) * nx - (b[0] - a[0]) * ny) < 0:
                a, b = b, a
            segs.append((a, b, (ck, src)))
        # chain into the footprint loop
        by_start = {a: (b, key) for a, b, key in segs}
        if len(by_start) != len(segs):
            _nope(f"{op}(footprint does not chain into one loop)",
                  "K6.2 (direct edits on booleans)")
        start = segs[0][0]
        loop = []
        cur = start
        for _ in range(len(segs)):
            nxt, key = by_start[cur]
            loop.append((cur, nxt, key))
            cur = nxt
        if cur != start or len(loop) != len(segs):
            _nope(f"{op}(footprint does not chain into one loop)",
                  "K6.2 (direct edits on booleans)")
        pos = next(i for i, (_a, _b, key) in enumerate(loop)
                   if key == target_key)
        n = len(loop)
        pa, pb, pkey = loop[(pos - 1) % n]
        na, nb, nkey = loop[(pos + 1) % n]
        dprev = (pb[0] - pa[0], pb[1] - pa[1])
        dnext = (nb[0] - na[0], nb[1] - na[1])
        meet = _meet_lines2(pa, dprev, na, dnext)
        if meet is None:
            _nope(f"{op}(the neighbour walls are parallel — their "
                  "extensions never meet, so no bounded heal exists)", _K6,
                  predicate="heal_unbounded",
                  measured={"neighbours": [pkey[1], nkey[1]]},
                  remedy="delete a wall whose neighbours converge, or "
                         "remove the generating feature")
        # extensions must EXTEND (same direction), not fold back
        if (_sign((meet[0] - pa[0]) * dprev[0]
                  + (meet[1] - pa[1]) * dprev[1]) <= 0
                or _sign((nb[0] - meet[0]) * dnext[0]
                         + (nb[1] - meet[1]) * dnext[1]) <= 0):
            _nope(f"{op}(the neighbour walls meet BEHIND themselves — the "
                  "heal would fold the boundary)", _K6,
                  predicate="topology_event",
                  measured={"event": "heal_folds"})
        newloop = []
        for i, (a, b, key) in enumerate(loop):
            if i == pos:
                continue
            aa = meet if key == nkey else a
            bb = meet if key == pkey else b
            newloop.append((aa, bb, key))
        pts = [a for a, _b, _k in newloop]
        if len(pts) < 3 or not _loop_is_simple(pts):
            _nope(f"{op}(the healed footprint self-intersects)", _K6,
                  predicate="topology_event",
                  measured={"event": "loop_self_intersection"})
        area2 = _loop_area2(pts)
        if area2 <= 0:
            _nope(f"{op}(the healed footprint has no interior)", _K6,
                  predicate="topology_event")
        # rebuild with the surviving faces keeping their lineage sources
        polys = []
        for a, b, (_ck, src) in newloop:
            polys.append(Polygon(
                [vec(a[0], a[1], z0), vec(b[0], b[1], z0),
                 vec(b[0], b[1], z1), vec(a[0], a[1], z1)], src))
        for t0, t1, t2 in _ear_clip(pts):
            polys.append(Polygon([vec(*t0, z0), vec(*t2, z0), vec(*t1, z0)],
                                 src_lo))
            polys.append(Polygon([vec(*t0, z1), vec(*t1, z1), vec(*t2, z1)],
                                 src_hi))
        out = Solid(polys)
        bad = out.watertight_violations()
        if bad:
            _nope(f"{op}(the healed boundary is not closed: {bad[0]})", _K6,
                  predicate="topology_event")
        return out

    # -- drilled solids: bores, shoulders, floors -----------------------------

    def _redrill(self, op, base, pieces):
        """Rebuild a DrilledSolid from an edited piece list, REPLAYING every
        clearance guard, then verify each requested piece survived VERBATIM.

        The post-check is the whole point (the derivation's silent-clamp
        trap): ``cut`` clamps tools to the base z-extent, so a shoulder
        pushed past the bottom face would come back as a wider through bore
        with no error — a valid, wrong solid."""
        from forgekernel.quadric import DrilledSolid

        if not pieces:
            return base
        dr = DrilledSolid(base, [])
        for c in pieces:
            try:
                dr = dr.cut(c)
            except ValueError as exc:
                raise KernelError(str(exc), FailureSignature(
                    op=op, diagnostic="NotYetImplemented", kernel="ref"))
        got = sorted((c.cx, c.cy, c.r, c.z0, c.z1) for c in dr.bores)
        want = sorted((c.cx, c.cy, c.r, c.z0, c.z1) for c in pieces)
        if got != want:
            _nope(f"{op}(an edited bore does not survive the rebuild "
                  "verbatim — an endpoint was clamped or a face consumed)",
                  _K6, predicate="face_absent_after_edit",
                  measured={"requested_bores": len(want),
                            "rebuilt_bores": len(got)})
        return dr

    def _drilled_group(self, shape, cx, cy):
        return [c for c in shape.bores if c.cx == cx and c.cy == cy]

    def _drilled_boundary_guard(self, op, shape, group_key, old_z, new_z,
                                skip=()):
        """Moving a z-boundary of a bore stack must not cross or touch any
        OTHER boundary of the stack or the base caps — crossing is a
        topology event, touching is a merge (tangency counts too)."""
        (_, _, bz0), (_, _, bz1) = shape.base.bbox()
        cx, cy = group_key
        bounds = {bz0, bz1}
        for c in self._drilled_group(shape, cx, cy):
            bounds.update((c.z0, c.z1))
        for b in bounds:
            if b == old_z or b in skip:
                continue
            if (b - old_z) * (b - new_z) < 0 or b == new_z:
                s = ((b - old_z) / (new_z - old_z)) if new_z != old_z else 1
                _nope(f"{op}(the face would "
                      f"{'meet' if b == new_z else 'cross'} another "
                      f"boundary of the stack at z={float(b):g} — a "
                      "topology event, not a deeper cut)", _K6,
                      predicate="topology_event",
                      measured={"event": "boundary_crossing",
                                "at_z": float(b),
                                "fraction_to_event": float(s)},
                      remedy="stop short of that boundary, or delete the "
                             "face and name the heal")

    def _edit_drilled(self, op, shape, idxs, action):
        kind = action[0]
        nb = len(self.entities(shape.base, "face"))
        nw = len(shape.bores)
        rings = _drilled_ring_meta(shape)
        base_idx = [i for i in idxs if i < nb]
        wall_idx = [i - nb for i in idxs if nb <= i < nb + nw]
        ring_idx = [i - nb - nw for i in idxs if i >= nb + nw]
        if sum(1 for g in (base_idx, wall_idx, ring_idx) if g) != 1:
            _nope(f"{op}(mixing base faces, bore walls and ring faces in "
                  "one edit)", _K6,
                  remedy="edit each face family in its own step")
        if base_idx:
            return self._edit_drilled_base(op, shape, base_idx, action)
        if wall_idx:
            if kind == "delete":
                return self._delete_bore_walls(op, shape, wall_idx,
                                               action[1])
            return self._edit_bore_walls(op, shape, wall_idx, action)
        if len(ring_idx) != 1:
            _nope(f"{op}(several ring faces at once)", _K6,
                  remedy="edit one shoulder or floor per step")
        return self._edit_bore_ring(op, shape, rings[ring_idx[0]], action)

    def _edit_drilled_base(self, op, shape, idxs, action):
        from forgekernel.quadric import Cyl

        if action[0] == "delete":
            _nope(f"{op}(a drilled solid's base face: healing it must "
                  "re-solve the bores too)",
                  "K6.2 (direct edits on booleans)",
                  remedy="un-drill first (delete the bore walls), then "
                         "delete the base face")
        base = shape.base
        ordered = sorted(base.logical_faces().items(),
                         key=lambda kv: (kv[0][1], kv[0][0]))
        obz0, obz1 = base.bbox()[0][2], base.bbox()[1][2]
        new_base = self._planar_move(op, base, ordered, idxs, action)
        nbz0, nbz1 = new_base.bbox()[0][2], new_base.bbox()[1][2]
        pieces = []
        for c in shape.bores:
            z0 = nbz0 if c.z0 == obz0 else c.z0
            z1 = nbz1 if c.z1 == obz1 else c.z1
            if (z0, z1) != (c.z0, c.z1):
                # adjacency extension: a bore ending ON the moved cap rides
                # it (a through hole STAYS through — the executed A3 cell),
                # but must not cross an interior boundary of its own stack
                if z1 != c.z1:
                    self._drilled_boundary_guard(
                        op, shape, (c.cx, c.cy), c.z1, z1,
                        skip={obz0, obz1, nbz0, nbz1})
                if z0 != c.z0:
                    self._drilled_boundary_guard(
                        op, shape, (c.cx, c.cy), c.z0, z0,
                        skip={obz0, obz1, nbz0, nbz1})
                if z1 <= z0:
                    _nope(f"{op}(the cap move consumes a bore)", _K6,
                          predicate="face_absent_after_edit",
                          measured={"bore_span": [float(z0), float(z1)]})
            pieces.append(Cyl(c.cx, c.cy, c.r, z0, z1))
        return self._redrill(op, new_base, pieces)

    def _edit_bore_walls(self, op, shape, wall_idx, action):
        from forgekernel.quadric import Cyl

        kind, payload = action
        pieces = list(shape.bores)
        sel = set(wall_idx)
        if kind == "offset":
            new = []
            for i, c in enumerate(pieces):
                if i not in sel:
                    new.append(c)
                    continue
                # the wall's outward material normal points AT the axis, so
                # +d (add material) SHRINKS the bore
                r = c.r - payload
                if r <= 0:
                    _nope(f"{op}(the bore's wall would cross its own "
                          "axis)", _K6, predicate="topology_event",
                          measured={"radius_after": float(r),
                                    "fraction_to_event": float(c.r / payload)
                                    if payload > c.r else 1.0},
                          remedy=f"offset by less than {float(c.r):g}")
                new.append(Cyl(c.cx, c.cy, r, c.z0, c.z1))
            self._guard_stack_order(op, pieces, new)
            return self._redrill(op, shape.base, new)
        # move: in-plane translates the hole; z refuses (the wall's carrier
        # is invariant along its own axis — the honest edit is on the caps)
        dx, dy, dz = payload
        if dz != 0:
            _nope(f"{op}(a bore wall along its own axis)", _K6,
                  remedy="move the shoulder, floor or cap instead — the "
                         "wall slides in its own carrier")
        if dx == 0 and dy == 0:
            return shape
        groups = {(c.cx, c.cy) for i, c in enumerate(pieces) if i in sel}
        for gx, gy in groups:
            members = [i for i, c in enumerate(pieces)
                       if (c.cx, c.cy) == (gx, gy)]
            if not set(members) <= sel:
                _nope(f"{op}(moving one wall of a coaxial stack breaks "
                      "the stack's shared axis)", _K6,
                      predicate="topology_event",
                      measured={"stack_walls": len(members)},
                      remedy="select every wall of the stack — the hole "
                             "moves as one feature")
        new = [Cyl(c.cx + dx, c.cy + dy, c.r, c.z0, c.z1) if i in sel else c
               for i, c in enumerate(pieces)]
        # a moved hole landing on ANOTHER hole's axis would silently fuse
        # the two stacks into one (coaxial cuts are legal, so no guard
        # downstream would fire) — a topology event, refused here
        for i, c in enumerate(new):
            for j, o in enumerate(new):
                if j <= i or (pieces[i].cx, pieces[i].cy) == \
                        (pieces[j].cx, pieces[j].cy):
                    continue
                if (c.cx, c.cy) == (o.cx, o.cy):
                    _nope(f"{op}(the moved hole lands on another hole's "
                          "axis — two stacks would fuse into one)", _K6,
                          predicate="topology_event",
                          measured={"axis": [float(c.cx), float(c.cy)]},
                          remedy="move somewhere else, or delete one hole "
                                 "first")
        return self._redrill(op, shape.base, new)

    def _guard_stack_order(self, op, old, new):
        """Within a coaxial stack the strict radius ordering of overlapping
        pieces IS the face topology (which wall is exposed where): a radius
        edit that reorders or ties it inverts or merges a shoulder."""
        for i in range(len(old)):
            for j in range(i + 1, len(old)):
                a, b = old[i], old[j]
                if (a.cx, a.cy) != (b.cx, b.cy):
                    continue
                if min(a.z1, b.z1) < max(a.z0, b.z0):
                    continue                  # no shared z: independent
                s0 = _sign(a.r - b.r)
                s1 = _sign(new[i].r - new[j].r)
                if s1 != s0 or s1 == 0:
                    _nope(f"{op}(the stack's shoulder would "
                          f"{'vanish' if s1 == 0 else 'invert'})", _K6,
                          predicate="topology_event",
                          measured={"radii": [float(new[i].r),
                                              float(new[j].r)]},
                          remedy="keep the counterbore wider than its "
                                 "pilot, or delete the shoulder naming "
                                 "the heal")

    def _delete_bore_walls(self, op, shape, wall_idx, absorb):
        if absorb is not None:
            raise KernelError(
                f"{op}: absorb names a shoulder's surviving wall — "
                "deleting a wall IS the un-drill heal and is unique",
                FailureSignature(op=op, diagnostic="BadInput", kernel="ref"))
        keep = [c for i, c in enumerate(shape.bores)
                if i not in set(wall_idx)]
        if not keep:
            return shape.base
        return self._redrill(op, shape.base, keep)

    def _edit_bore_ring(self, op, shape, ring, action):
        from forgekernel.quadric import Cyl

        kind, payload = action
        rkind, key, z, r_below, r_above = ring
        if kind == "delete":
            return self._delete_bore_ring(op, shape, ring, payload)
        if kind == "move":
            dz = payload[2]              # the in-plane part is the identity
        else:
            # outward material normal: +z when the void sits above the ring
            dz = payload if r_above > r_below else -payload
        if dz == 0:
            return shape
        new_z = z + dz
        self._drilled_boundary_guard(op, shape, key, z, new_z)
        pieces = []
        for c in shape.bores:
            if (c.cx, c.cy) == key and (c.z0 == z or c.z1 == z):
                pieces.append(Cyl(c.cx, c.cy, c.r,
                                  new_z if c.z0 == z else c.z0,
                                  new_z if c.z1 == z else c.z1))
            else:
                pieces.append(c)
        out = self._redrill(op, shape.base, pieces)
        if (rkind, key, new_z, r_below, r_above) not in _drilled_ring_meta(out):
            _nope(f"{op}(the {rkind} is absent from the result)", _K6,
                  predicate="face_absent_after_edit")
        return out

    def _delete_bore_ring(self, op, shape, ring, absorb):
        from forgekernel.quadric import Cyl

        rkind, key, z, r_below, r_above = ring
        cx, cy = key
        (_, _, bz0), (_, _, bz1) = shape.base.bbox()
        nb = len(self.entities(shape.base, "face"))
        group = self._drilled_group(shape, cx, cy)

        def wall_face(piece):
            return nb + shape.bores.index(piece)

        def rebuilt_volume(pieces):
            try:
                return float(self._redrill(op, shape.base, pieces).volume())
            except KernelError:
                return None

        if rkind == "shoulder":
            def heal(radius):
                """Both bands adjacent to z take ``radius``; the rest of the
                stack is untouched. Exact by construction."""
                bands = _bore_bands(group)
                i = next(i for i in range(len(bands) - 1)
                         if bands[i][1] == z)
                pieces = [Cyl(cx, cy, radius, bands[i][0], bands[i + 1][1])]
                for j, (blo, bhi, br) in enumerate(bands):
                    if j not in (i, i + 1):
                        pieces.append(Cyl(cx, cy, br, blo, bhi))
                others = [c for c in shape.bores if (c.cx, c.cy) != key]
                return others + pieces

            if absorb is None:
                cands = []
                for r in (r_below, r_above):
                    v = rebuilt_volume(heal(r))
                    cands.append({"radius": float(r),
                                  "volume": v if v is not None
                                  else "refused"})
                _nope(f"{op}(the shoulder has TWO valid heals — the wide "
                      "wall extends or the narrow one does — and picking "
                      "one silently is a wrong answer)", _K6,
                      predicate="heal_ambiguous",
                      measured={"candidates": cands},
                      remedy="pass absorb=<face index of the wall to "
                             "extend> to name the heal")
            adjacent = {}
            for c in group:
                if (c.z1 == z and c.r == r_below) \
                        or (c.z0 == z and c.r == r_above) \
                        or (c.z0 < z < c.z1 and c.r in (r_below, r_above)):
                    adjacent[wall_face(c)] = c.r
            if absorb not in adjacent:
                raise KernelError(
                    f"{op}: absorb={absorb} is not a wall adjacent to "
                    f"this shoulder (adjacent walls: {sorted(adjacent)})",
                    FailureSignature(op=op, diagnostic="BadInput",
                                     kernel="ref"))
            return self._redrill(op, shape.base, heal(adjacent[absorb]))

        # floor / ceiling: absorb=wall deepens the bore through to the cap;
        # the OTHER heal (un-drill) is delete_face on the wall itself
        r = max(r_below, r_above)
        piece = next(c for c in group
                     if (c.z0 == z if rkind == "floor" else c.z1 == z)
                     and c.r == r)
        cap = bz0 if rkind == "floor" else bz1
        through = [c for c in shape.bores if c is not piece] + [
            Cyl(cx, cy, r,
                cap if rkind == "floor" else piece.z0,
                piece.z1 if rkind == "floor" else cap)]
        if absorb is None:
            undrill = [c for c in shape.bores if c is not piece]
            v_th = rebuilt_volume(through)
            v_un = (rebuilt_volume(undrill) if undrill
                    else float(shape.base.volume()))
            _nope(f"{op}(the {rkind} has two heals: drill THROUGH "
                  "(absorb= the wall) or UN-drill (delete the wall face "
                  "instead))", _K6, predicate="heal_ambiguous",
                  measured={"candidates": [
                      {"action": "absorb the wall, drill through",
                       "volume": v_th if v_th is not None else "refused"},
                      {"action": "delete the wall face to un-drill",
                       "volume": v_un if v_un is not None else "refused"}]},
                  remedy="pass absorb=<the wall's face index> to drill "
                         "through, or delete the wall face to un-drill")
        if absorb != wall_face(piece):
            raise KernelError(
                f"{op}: absorb={absorb} is not the wall of this {rkind} "
                f"(that is face {wall_face(piece)})",
                FailureSignature(op=op, diagnostic="BadInput", kernel="ref"))
        self._drilled_boundary_guard(op, shape, key, z, cap, skip={cap})
        return self._redrill(op, shape.base, through)

    # -- cylinders, lathes, rounded boxes, composites -------------------------

    def _edit_cyl(self, op, shape, idxs, action):
        from forgekernel.quadric import Cyl

        kind, payload = action
        if len(idxs) != 1:
            _nope(f"{op}(several cylinder faces at once)", _K6,
                  remedy="one face per edit on a cylinder")
        idx = idxs[0]
        height = shape.z1 - shape.z0
        if idx == 0:                                   # the lateral wall
            if kind == "delete":
                _nope(f"{op}(the cylinder's only lateral face — nothing "
                      "bounded remains)", _K6, predicate="heal_unbounded")
            if kind == "offset":
                r = shape.r + payload          # outward = away from the axis
                if r <= 0:
                    _nope(f"{op}(the wall would cross its own axis)", _K6,
                          predicate="topology_event",
                          measured={"radius_after": float(r)},
                          remedy=f"offset by more than {float(-shape.r):g}")
                return Cyl(shape.cx, shape.cy, r, shape.z0, shape.z1)
            dx, dy, dz = payload
            if dz != 0:
                _nope(f"{op}(a cylinder wall along its own axis)", _K6,
                      remedy="move a cap instead — the wall slides in its "
                             "own carrier")
            return Cyl(shape.cx + dx, shape.cy + dy, shape.r,
                       shape.z0, shape.z1)
        top = idx == 1
        if kind == "delete":
            _nope(f"{op}(a cylinder cap: the wall is parallel to the axis "
                  "and never closes)", _K6, predicate="heal_unbounded")
        if kind == "move":
            dz = payload[2]                            # in-plane = identity
        else:
            dz = payload if top else -payload          # outward is +z / -z
        z0 = shape.z0 if top else shape.z0 + dz
        z1 = shape.z1 + dz if top else shape.z1
        if z1 <= z0:
            _nope(f"{op}(the caps would meet — the solid vanishes)", _K6,
                  predicate="topology_event",
                  measured={"height_after": float(z1 - z0),
                            "fraction_to_event": float(height / abs(dz))
                            if dz != 0 and abs(dz) > height else 1.0})
        return Cyl(shape.cx, shape.cy, shape.r, z0, z1)

    def _edit_lathe(self, op, shape, idxs, action):
        from forgekernel.quadric import RevolveSolid
        from forgekernel.surd import exact_sqrt

        kind, payload = action
        if len(idxs) != 1:
            _nope(f"{op}(several lathe faces at once)", _K6,
                  remedy="one profile face per edit")
        loop = list(shape.loop)
        n = len(loop)
        seg = _lathe_face_segments(loop)[idxs[0]]
        prv, nxt = (seg - 1) % n, (seg + 1) % n
        a, b = loop[seg], loop[(seg + 1) % n]
        d_seg = (b[0] - a[0], b[1] - a[1])
        area2 = sum(loop[i][0] * loop[(i + 1) % n][1]
                    - loop[(i + 1) % n][0] * loop[i][1] for i in range(n))
        if area2 == 0:
            _nope(f"{op}(degenerate lathe profile)", _K6)

        def carrier(i):
            p, q = loop[i], loop[(i + 1) % n]
            return p, (q[0] - p[0], q[1] - p[1])

        try:
            if kind == "delete":
                if payload is not None:
                    raise KernelError(
                        f"{op}: absorb applies to drilled-solid heals",
                        FailureSignature(op=op, diagnostic="BadInput",
                                         kernel="ref"))
                if n - 1 < 3:
                    _nope(f"{op}(nothing bounded remains)", _K6,
                          predicate="heal_unbounded")
                meet = _meet_lines2(*carrier(prv), *carrier(nxt))
                if meet is None:
                    _nope(f"{op}(the neighbour faces are parallel — their "
                          "extensions never meet, so no bounded heal "
                          "exists)", _K6, predicate="heal_unbounded",
                          remedy="delete a face whose neighbours converge, "
                                 "or remove the generating feature")
                if meet[0] < 0:
                    _nope(f"{op}(the healed profile crosses the axis)",
                          _K6, predicate="topology_event",
                          measured={"r_at_meet": float(meet[0])})
                newloop = [meet if i == (seg + 1) % n else loop[i]
                           for i in range(n) if i != seg]
                changed = [(prv, loop[prv], meet),
                           (nxt, meet, loop[(nxt + 1) % n])]
            else:
                if kind == "move":
                    if (payload[0] != 0 or payload[1] != 0) and a[1] != b[1]:
                        _nope(f"{op}(an off-axis move of a lathe face is "
                              "elliptic — outside every exact field)", _K6,
                              remedy="offset the wall, move a cap along z, "
                                     "or transform the whole body")
                    dz = payload[2]
                    if dz == 0:
                        return shape
                    shift = (Fraction(0), dz)
                else:
                    nn = d_seg[0] * d_seg[0] + d_seg[1] * d_seg[1]
                    ln = exact_sqrt(nn)
                    s = 1 if area2 > 0 else -1
                    # outward normal of a CCW (r,z) loop is (dz, -dr)/|d|
                    shift = (payload * d_seg[1] * s / ln,
                             -payload * d_seg[0] * s / ln)
                na = (a[0] + shift[0], a[1] + shift[1])
                p1 = _meet_lines2(*carrier(prv), na, d_seg)
                p2 = _meet_lines2(na, d_seg, *carrier(nxt))
                if p1 is None or p2 is None:
                    _nope(f"{op}(a neighbour face is parallel to the "
                          "moved face — they merge instead of meeting)",
                          _K6, predicate="topology_event",
                          measured={"event": "faces_merge"})
                newloop = list(loop)
                newloop[seg] = p1
                newloop[(seg + 1) % n] = p2
                changed = [(prv, loop[prv], p1), (seg, p1, p2),
                           (nxt, p2, loop[(nxt + 1) % n])]
                for i, (r, _z) in enumerate(newloop):
                    if r == 0 and loop[i][0] != 0:
                        _nope(f"{op}(the profile touches the axis — "
                              "tangency is a topology event)", _K6,
                              predicate="topology_event")
            for i, pa, pb in changed:
                qa, qb = loop[i], loop[(i + 1) % n]
                od = (qb[0] - qa[0], qb[1] - qa[1])
                nd = (pb[0] - pa[0], pb[1] - pa[1])
                if _sign(od[0] * nd[0] + od[1] * nd[1]) <= 0:
                    _nope(f"{op}(profile segment {i} collapses or "
                          "reverses — a topology event, not a bigger "
                          "edit)", _K6, predicate="topology_event",
                          measured={"event": "segment_collapse",
                                    "segment": i})
            for r, _z in newloop:
                if r < 0:
                    _nope(f"{op}(the profile crosses the revolution "
                          "axis)", _K6, predicate="topology_event",
                          measured={"r": float(r)})
            if not _loop_is_simple(newloop):
                _nope(f"{op}(the edited profile self-intersects)", _K6,
                      predicate="topology_event",
                      measured={"event": "loop_self_intersection"})
            m = len(newloop)
            v3 = sum((newloop[(i + 1) % m][1] - newloop[i][1])
                     * (newloop[i][0] * newloop[i][0]
                        + newloop[i][0] * newloop[(i + 1) % m][0]
                        + newloop[(i + 1) % m][0] * newloop[(i + 1) % m][0])
                     for i in range(m))
            if _sign(v3) <= 0:
                _nope(f"{op}(the edit turns the solid inside out)", _K6,
                      predicate="topology_event")
            return RevolveSolid(newloop, shape.cx, shape.cy)
        except TypeError:
            _nope(f"{op}(the edit needs a second radical — one radical "
                  "per profile)", _K6, predicate="one_radical_per_profile",
                  remedy="keep the profile's slants in one quadratic field")

    def _edit_rounded(self, op, shape, idxs, action):
        from forgekernel.brep import Solid
        from forgekernel.quadric import RoundedBox

        kind, payload = action
        meta = _rounded_face_meta(shape)
        blends = {i for i, m in enumerate(meta) if m[0] != "flat"}
        if kind == "delete":
            if payload is not None:
                raise KernelError(
                    f"{op}: absorb applies to drilled-solid heals",
                    FailureSignature(op=op, diagnostic="BadInput",
                                     kernel="ref"))
            if set(idxs) == blends:
                # generator removal: sharpen back to the exact box
                return Solid.box(shape.a, shape.b, shape.c,
                                 "box").translated(shape.origin)
            if any(i in blends for i in idxs):
                _nope(f"{op}(a subset of the blend family: sharpening one "
                      "edge of a rounded box needs the selected-edge "
                      "fillet family)", "K5.2 (general blends)",
                      remedy="select all blend faces to sharpen, or "
                             "remodel with fillet on selected edges")
            _nope(f"{op}(a rounded box's flat face has no bounded heal — "
                  "its neighbours are tangent blends)", _K6,
                  predicate="heal_unbounded",
                  remedy="move the flat with move_face, or delete all 20 "
                         "blend faces to sharpen first")
        if any(i in blends for i in idxs):
            _nope(f"{op}(a blend face: its offset is tangent to NEITHER "
                  "neighbour, so no exact same-topology answer exists)",
                  _K6, predicate="blend_face_tangency",
                  remedy="re-value the fillet radius on the generating "
                         "feature instead")
        dims = [shape.a, shape.b, shape.c]
        org = list(shape.origin)
        for i in idxs:
            _kind, _name, axis, side = meta[i]
            delta = (payload[axis] * (1 if side == "max" else -1)
                     if kind == "move" else payload)
            dims[axis] += delta
            if side == "min":
                org[axis] -= delta
        r = shape.r
        old_dims = (shape.a, shape.b, shape.c)
        for axis in range(3):
            if dims[axis] <= 2 * r:
                _nope(f"{op}(the {'xyz'[axis]}-axis flats are consumed at "
                      "2r — the cap blends go tangent)", _K6,
                      predicate="topology_event",
                      measured={"flat_width_after":
                                float(dims[axis] - 2 * r),
                                "max_shrink":
                                float(old_dims[axis] - 2 * r)},
                      remedy=f"keep the {'xyz'[axis]} dimension above "
                             f"{float(2 * r):g} (2r)")
        try:
            return RoundedBox(dims[0], dims[1], dims[2], r, tuple(org))
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op=op, diagnostic="NotYetImplemented", kernel="ref"))

    def _edit_disjoint(self, op, shape, idxs, action):
        from forgekernel.quadric import DisjointUnion

        lens = [len(self.entities(m, "face")) for m in shape.members]
        owner = None
        local = []
        for idx in idxs:
            off = 0
            for mi, ln in enumerate(lens):
                if idx < off + ln:
                    if owner is None:
                        owner = mi
                    elif owner != mi:
                        _nope(f"{op}(faces from different members of a "
                              "composite)", _K6,
                              remedy="edit one member per step")
                    local.append(idx - off)
                    break
                off += ln
        edited = self._direct_edit(op, shape.members[owner], local, action)
        members = list(shape.members)
        members[owner] = edited
        try:
            return DisjointUnion(members)
        except (ValueError, TypeError) as exc:
            _nope(f"{op}(the edited member no longer stays clear of its "
                  f"neighbours: {exc})", _K6, predicate="topology_event",
                  remedy="stop the edit before the members touch, or "
                         "model the fused result explicitly")

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

        deflection = _check_deflection("hlr_project", deflection)
        return hidden_line(shape, direction, xdir, deflection=deflection)

    def section_polys(self, shape, direction, xdir, offset, *, deflection=0.05):
        # ADR-0020: native section curves (plane ∩ solid boundary) — same
        # sheet frame as hlr_project, so a section view overlays exactly.
        from forgekernel.hlr import section_polys

        deflection = _check_deflection("section_polys", deflection)
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
        # Round-9 docket W5 + W10: this used to try forge's `io.to_stl(shape)`
        # first, which calls `shape.tessellate()` with NO argument — so every
        # representation carrying a `.tessellate` attribute took a
        # deflection-blind shortcut and the caller's tolerance was silently
        # DISCARDED (a cylinder shipped the same 48 facets at 0.2 and at
        # 0.001: 0.17 mm of wall sag, 170x the request). Worse, the shortcut
        # bypassed the seam's own refusals: an AxisStack whose `tessellate`
        # honestly refuses (K3.7) shipped a chorded lathe enclosing 644.0
        # where the exact volume is 784π/3 = 821.003 — a wrong watertight
        # file on the one path a manufacturer consumes.
        #
        # ADR-0021, ONE mesher: the export path IS `self.tessellate`, at the
        # caller's deflection. Where the mesh would be wrong, this now refuses
        # structurally instead of shipping — the refusal is the answer.
        deflection = _check_deflection("export_stl", deflection)
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

    # The remedy every non-closing import gets: both sanctioned outs, and the
    # bet that rules out a third. Named once so import_step and import_brep
    # cannot drift apart about what the user is allowed to do next.
    _NONCLOSED_REMEDY = (
        "the shell does not close and gitcad will not invent geometry to "
        "close it (the anti-Parasolid bet): repair the part in its source "
        "system, or — if the gaps are small tears — set heal_tolerance=<mm> "
        "on the import feature for an exact, recorded vertex merge (never "
        "face invention); a quarantined sheet-body import (as_sheet) is a "
        "named future option pending the ADR-0022 Body-seam reconciliation")

    def import_step(self, path, heal_tolerance=None):
        # K3.6: planar-faced STEP solids import as EXACT Solids — STEP
        # reals are decimal text, decimal→Fraction is lossless, and face
        # loops orient by exact Newell-vs-plane-normal comparison.
        #
        # K3.7: freeform (B-spline-faced) solids route to the trimmed
        # importer and arrive as an audited TrimmedShell — pcurve chains
        # carry each face's exact parameter-space trim, orientation is
        # decided by certified volume sign, and the volume bracket is
        # width-0 on the exact tier (polynomial faces, degree-1 pcurves).
        # Downstream the K7 contract applies: mass_props certified,
        # validate re-audits, tessellate shows the certified-safe mesh,
        # bbox/boolean keep refusing by name. Analytic surfaces,
        # sign-varying weights, missing pcurves, VERTEX_LOOPs and
        # periodic seams refuse with their names.
        #
        # K3.6b (#135), BOTH paths: the border is audited. A CLOSED_SHELL
        # that lies (missing face, torn seam) used to import silently and
        # hand measure/mass_props an origin-dependent non-number; now
        # closure is established BEFORE any orientation decision and an
        # open shell refuses with a gap report in user millimetres — or
        # heals by exact vertex merge when the import feature records
        # that intent (ADR-0022).
        from forgekernel.brep import NonClosedShellError, SnapClusterError
        from forgekernel.stepio import read_step_solid
        from forgekernel.trimshell import (ShellAuditError,
                                           ShellAuditUncertified)

        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        rep: dict = {}
        self.last_import_report = None
        try:
            s = read_step_solid(text, heal_tolerance=heal_tolerance,
                                report=rep)
        except ShellAuditError as exc:
            # the FILE's shell is proven wrong (mis-oriented face flags,
            # degenerate trim loop) — a modeling/export error, refused
            # with the audit's own finding
            raise KernelError(str(exc), FailureSignature(
                op="import_step", diagnostic="ShellAuditFailed",
                kernel="ref"),
                stage="import", predicate="shell_audit_failed",
                remedy="the freeform shell fails its own certified audit "
                       "— repair the orientation/trim in the source "
                       "system and re-export")
        except ShellAuditUncertified as exc:
            raise KernelError(str(exc), FailureSignature(
                op="import_step", diagnostic="ShellAuditUncertified",
                kernel="ref"),
                stage="import", predicate="shell_audit_uncertified",
                remedy="the certified brackets are too wide to prove the "
                       "shell at this depth; raise the import depth "
                       "(tighten-or-refuse, never a silent pass)")
        except NonClosedShellError as exc:
            measured = dict(exc.report)
            if exc.healed is not None:
                measured["heal_moved"] = exc.healed["moved"]
                measured["heal_max_move_mm"] = exc.healed["max_move_mm"]
            raise KernelError(str(exc), FailureSignature(
                op="import_step", diagnostic="NonClosedShell", kernel="ref"),
                stage="import", predicate="shell_closure",
                measured=measured, remedy=self._NONCLOSED_REMEDY)
        except SnapClusterError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="import_step", diagnostic="HealClusterOverflow",
                kernel="ref"),
                stage="import", predicate="heal_cluster_diameter",
                measured={"cluster": exc.cluster,
                          "diameter_sq": float(exc.diameter_sq),
                          "heal_tolerance": float(exc.tolerance)},
                remedy="lower heal_tolerance below the smallest real vertex "
                       "spacing — a transitive merge would move a vertex "
                       "farther than the promised tolerance")
        except ValueError as exc:
            if "non-planar face loop" in str(exc):
                raise KernelError(str(exc), FailureSignature(
                    op="import_step", diagnostic="NonPlanarFaceLoop",
                    kernel="ref"),
                    stage="import", predicate="face_loop_planar",
                    remedy="the loop's vertices do not lie in one exact "
                           "plane; repair or re-export from the source "
                           "system (freeform faces arrive at K3.7)")
            raise KernelError(str(exc), FailureSignature(
                op="import_step", diagnostic="NotYetImplemented",
                kernel="ref"))
        self.last_import_report = rep
        return s

    def import_brep(self, path):
        from forgekernel import io
        from forgekernel.brep import (Solid, boundary_gap_report,
                                      open_boundary_segments)

        with open(path, encoding="utf-8") as f:
            s = io.loads(f.read())
        # same border, same audit (#135): a polygon-soup file can describe an
        # open shell just as easily as a torn STEP, and the empty solid — an
        # ANSWER (#136), no boundary at all — passes vacuously.
        if isinstance(s, Solid):
            segs = open_boundary_segments(s.polys)
            if segs:
                gr = boundary_gap_report(segs)
                raise KernelError(
                    f"import_brep: the shell does not close — "
                    f"{gr['open_edges']} open boundary edges, "
                    f"{gr['open_perimeter_mm']:.6g} mm open perimeter",
                    FailureSignature(op="import_brep",
                                     diagnostic="NonClosedShell",
                                     kernel="ref"),
                    stage="import", predicate="shell_closure",
                    measured=gr, remedy=self._NONCLOSED_REMEDY)
        return s


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


def _rim_edge(cx, cy, z, r):
    """A full-circle edge at (cx, cy, z) radius r, built exactly the way
    forge's ``_circle_at`` builds rims, so edge keys pair across faces."""
    from forgekernel import body as B

    one, zero = Fraction(1), Fraction(0)
    c = B.Circle((Fraction(cx), Fraction(cy), Fraction(z)),
                 (zero, zero, one), (one, zero, zero), Fraction(r))
    v = (Fraction(cx) + Fraction(r), Fraction(cy), Fraction(z))
    return B.Edge(c, v, v)


def _frame_face(face, ilo, ihi):
    """Punch the dilated cavity's core rectangle into an inset-box face.

    The lattice void's outer faces are square FRAMES: the inset flat with the
    rounded box's tangency rectangle as an inner ring. The ring's segments
    are exactly the quarter-cylinders' straight tangency edges (same
    endpoints, same lines), so each is used once here and once there — the
    shell closes with no face of zero width anywhere.

    The hole must be wound OPPOSITE to the outer ring about the face's
    outward normal, or the plane term would ADD its area instead of
    subtracting it; the winding is checked by exact signed area, not assumed.
    """
    from forgekernel import body as B

    s = face.surface
    axis = max(range(3), key=lambda c: abs(s.n[c]))
    level = Fraction(face.loops[0].edges[0].v0[axis])
    u, v = (c for c in range(3) if c != axis)

    def to3(a, b):
        p = [None, None, None]
        p[axis], p[u], p[v] = level, Fraction(a), Fraction(b)
        return tuple(p)

    ring = [to3(ilo[u], ilo[v]), to3(ihi[u], ilo[v]),
            to3(ihi[u], ihi[v]), to3(ilo[u], ihi[v])]
    out_n = tuple(Fraction(x) if face.sense else -Fraction(x) for x in s.n)
    twice_area = [Fraction(0)] * 3
    for i in range(4):
        a, b = ring[i], ring[(i + 1) % 4]
        twice_area[0] += a[1] * b[2] - a[2] * b[1]
        twice_area[1] += a[2] * b[0] - a[0] * b[2]
        twice_area[2] += a[0] * b[1] - a[1] * b[0]
    if sum(twice_area[c] * out_n[c] for c in range(3)) > 0:
        ring.reverse()
    hole = B.Loop(tuple(
        B.Edge(B.Line(ring[i], tuple(ring[(i + 1) % 4][c] - ring[i][c]
                                     for c in range(3))),
               ring[i], ring[(i + 1) % 4]) for i in range(4)))
    return B.Face(s, face.loops + (hole,), face.sense)


def _erode_rim_to_torus(faces, cx, cy, Z, rho, t):
    """Replace a void scaffold's step at a reentrant rim with the true fillet.

    ``from_drilled`` gave the void a helper band of radius ρ over [Z−t, Z]
    and a step annulus (ρ → ρ+t) at Z. The erosion's real boundary there is
    the quarter TORUS swept by the rim circle (ρ, Z): tube radius t, k0=3
    span=1, carried (ρ, Z−t) → (ρ+t, Z) — the winding ``lathe_body`` would
    demand. The helper band's outer rims are exactly the torus's rims, so
    removing the two scaffold faces and adding the torus leaves every edge
    paired (#130 gave torus faces their loops, so the audit can now see it).

    THE TRAP, pinned by the golden closed forms: the face BELOW the site
    (a blind bore's floor disk, a counterbore's kept shoulder annulus) has
    outer radius ρ, NOT ρ+t. The naive ρ+t body passes all four audit checks
    while 3.744 mm³ heavy on the banked oracle — which is why the scaffold
    is built so those flat faces are already correct and only the step is
    replaced here.

    Sense: the void's material lies OUTSIDE the tube (points ≥ t from the
    rim), so the void's outward normal points toward the tube's centre
    circle — the opposite of a convex lathe fillet — hence ``sense=False``.
    """
    from forgekernel import body as B

    one, zero = Fraction(1), Fraction(0)

    def rim_edge(z, r):
        return _rim_edge(cx, cy, z, r)

    wall_i = ann_i = None
    for i, f in enumerate(faces):
        s = f.surface
        if (isinstance(s, B.Cylinder) and s.r == rho
                and s.p == (cx, cy, Z - t)):
            wall_i = i
        elif (isinstance(s, B.Plane) and s.n == (zero, zero, one)
                and s.d == Z and len(f.loops) == 2):
            edges = [e for lp in f.loops for e in lp.edges]
            if (sorted(e.curve.r for e in edges) == [rho, rho + t]
                    and all(e.curve.c[:2] == (cx, cy) for e in edges)):
                ann_i = i
    if wall_i is None or ann_i is None:
        raise KernelError(
            "shell(drilled solid): the scaffold surgery lost its step faces "
            "— a kernel defect, please report it",
            FailureSignature(op="shell", diagnostic="AnswerAudit",
                             kernel="ref"))
    kept = [f for i, f in enumerate(faces) if i not in (wall_i, ann_i)]
    tor = B.Face(B.Torus((cx, cy, Z), (zero, zero, one), rho, t, 3, 1),
                 (B.Loop((rim_edge(Z - t, rho), rim_edge(Z, rho + t))),),
                 False)
    return kept + [tor]


def _lathe_body(segs, cx, cy):
    from forgekernel import body as B

    return B.lathe_body(segs, cx, cy)


def _axis_runs(loop) -> int:
    """How many maximal circular runs of axis (r == 0) edges the profile
    loop has. A valid lathe profile has 0 (a tube) or 1 (a solid); 2+ means
    an axis-touching slit — an internal cavity wearing a single loop."""
    n = len(loop)
    on_axis = [loop[i][0] == 0 and loop[(i + 1) % n][0] == 0
               for i in range(n)]
    if all(on_axis) or not any(on_axis):
        return 1 if on_axis and on_axis[0] else 0
    return sum(1 for i in range(n) if on_axis[i] and not on_axis[i - 1])


def _profile_boolean(loop_a, loop_b, op):
    """Exact boolean of two closed (r, z) profile polygons — a z-band sweep.

    A coaxial boolean on solids of revolution IS a boolean on their
    profiles, and a polygon boolean is exact plane geometry: every event
    (a vertex, or one polygon's edge crossing the other's) happens at a
    RATIONAL z, because the edges are rational lines. Between events the
    cross-section of each region is a fixed list of r-intervals whose
    endpoints move linearly, so the boolean is interval arithmetic per
    band; the boundary is then re-stitched from the band walls plus the
    horizontal symmetric-difference at each event height.

    ``op`` is "cut" (a minus b), "union" or "intersect". Returns the list
    of result loops (Fraction coordinates, collinear runs merged), or
    ``None`` when the inputs leave ℚ (a surd-valued profile) or the
    boundary does not stitch into simple loops (a pinch vertex, where four
    boundary edges meet) — the caller keeps its honest refusal for those.
    """
    from collections import defaultdict

    def rat(v):
        if isinstance(v, Fraction):
            return v
        if isinstance(v, int):
            return Fraction(v)
        return None                          # SurdVal / float: not this path

    def edges_of(loop):
        out = []
        n = len(loop)
        for i in range(n):
            (r1, z1), (r2, z2) = loop[i], loop[(i + 1) % n]
            vals = [rat(r1), rat(z1), rat(r2), rat(z2)]
            if any(v is None for v in vals):
                return None
            r1, z1, r2, z2 = vals
            if z1 != z2:                     # horizontals carry no coverage
                out.append((r1, z1, r2, z2))
        return out

    ea, eb = edges_of(loop_a), edges_of(loop_b)
    if ea is None or eb is None:
        return None
    events = set()
    for loop in (loop_a, loop_b):
        for _r, z in loop:
            zv = rat(z)
            if zv is None:
                return None
            events.add(zv)
    # an A edge crossing a B edge swaps their r-order: that z is an event
    # (edges within ONE simple polygon never cross each other)
    for r1, z1, r2, z2 in ea:
        sa = (r2 - r1) / (z2 - z1)
        alo, ahi = (z1, z2) if z1 < z2 else (z2, z1)
        for p1, w1, p2, w2 in eb:
            sb = (p2 - p1) / (w2 - w1)
            if sa == sb:
                continue
            zx = (p1 - sb * w1 - r1 + sa * z1) / (sa - sb)
            blo, bhi = (w1, w2) if w1 < w2 else (w2, w1)
            if max(alo, blo) < zx < min(ahi, bhi):
                events.add(zx)
    zs = sorted(events)

    def band_pairs(edges, zl, zh):
        """Each edge spanning the band as its (r@zl, r@zh) pair, sorted —
        the order is constant inside a band because crossings are events."""
        out = []
        for r1, z1, r2, z2 in edges:
            if min(z1, z2) <= zl and max(z1, z2) >= zh:
                s = (r2 - r1) / (z2 - z1)
                out.append((r1 + s * (zl - z1), r1 + s * (zh - z1)))
        out.sort()
        return out

    keep = {"cut": lambda in_a, in_b: in_a and not in_b,
            "union": lambda in_a, in_b: in_a or in_b,
            "intersect": lambda in_a, in_b: in_a and in_b}[op]
    bands = []                               # (zl, zh, [(lo, hi), ...])
    for zl, zh in zip(zs, zs[1:]):
        toggles = {}
        for p in band_pairs(ea, zl, zh):
            toggles.setdefault(p, [0, 0])[0] ^= 1
        for p in band_pairs(eb, zl, zh):
            toggles.setdefault(p, [0, 0])[1] ^= 1
        in_a = in_b = cur = False
        open_at = None
        ivs = []
        for p in sorted(toggles):
            ta, tb = toggles[p]
            if ta:
                in_a = not in_a
            if tb:
                in_b = not in_b
            now = keep(in_a, in_b)
            if now and not cur:
                open_at = p
            elif cur and not now and open_at != p:
                ivs.append((open_at, p))
            cur = now
        if cur:
            return None                      # unbalanced parity: degenerate
        if ivs:
            bands.append((zl, zh, ivs))

    # boundary soup: slanted/vertical walls per band, horizontal edges at
    # each event = coverage-below XOR coverage-above
    segs = []
    at_z = {z: ([], []) for z in zs}         # z -> (below-cover, above-cover)
    for zl, zh, ivs in bands:
        for lo, hi in ivs:
            segs.append(((lo[0], zl), (lo[1], zh)))
            segs.append(((hi[0], zl), (hi[1], zh)))
            at_z[zh][0].append((lo[1], hi[1]))
            at_z[zl][1].append((lo[0], hi[0]))
    for z, (below, above) in at_z.items():
        marks = defaultdict(lambda: [0, 0])
        for lo, hi in below:
            marks[lo][0] += 1
            marks[hi][0] -= 1
        for lo, hi in above:
            marks[lo][1] += 1
            marks[hi][1] -= 1
        cb = ca = 0
        start = None
        for r in sorted(marks):
            db, da = marks[r]
            prev = (cb > 0) != (ca > 0)
            cb += db
            ca += da
            now = (cb > 0) != (ca > 0)
            if now and not prev:
                start = r
            elif prev and not now and start != r:
                segs.append(((start, z), (r, z)))

    adj = defaultdict(list)
    for a, b in segs:
        if a == b:
            continue
        adj[a].append(b)
        adj[b].append(a)
    if any(len(nbrs) != 2 for nbrs in adj.values()):
        return None                          # a pinch vertex: not simple loops
    loops = []
    seen = set()
    for begin in adj:
        if begin in seen:
            continue
        loop = [begin]
        seen.add(begin)
        prev, cur = begin, adj[begin][0]
        while cur != begin:
            loop.append(cur)
            seen.add(cur)
            nxt = adj[cur][0] if adj[cur][0] != prev else adj[cur][1]
            prev, cur = cur, nxt
        # merge collinear runs (band events that did not bend the boundary)
        out = []
        n = len(loop)
        for i in range(n):
            p0, p1, p2 = loop[i - 1], loop[i], loop[(i + 1) % n]
            ux, uy = p1[0] - p0[0], p1[1] - p0[1]
            vx, vy = p2[0] - p1[0], p2[1] - p1[1]
            if ux * vy - uy * vx == 0 and ux * vx + uy * vy > 0:
                continue
            out.append(p1)
        loops.append(out)
    return loops


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
