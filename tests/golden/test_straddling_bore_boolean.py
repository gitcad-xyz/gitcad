"""#123 — a prism whose footprint STRADDLES a bore.

The last boolean family the capability matrix refused, and the one where the
obvious implementation ships a silent wrong number. The removed cross-section
is NOT the tool's rectangle: for the counterbore probe the tool's corner sits
exactly on the bore axis, so two of its four sides lie entirely inside the bore
and contribute no face at all. The notch floor has THREE edges. Emit the fourth
and you get a self-intersecting shell with a plausible, exact, wrong volume.

Every number here is derived by hand from the geometry, not read off the
implementation:

  counterbore  bore r=2 over z 0..10, counterbore r=4 over z 7..10, tool
               [15,17]² × z≥5. Over z 5..7 the removed section is square minus
               quarter disc = 4 − π; over z 7..10 the whole square already lies
               inside the r=4 bore, so nothing is removed.
                   removed = 2(4 − π),  result = 9000 − 76π − 8 + 2π = 8992 − 74π
  bored boss   plate 30×30×3 + boss r=4 z 3..9, bore r=1 z 4..9, tool
               [15,17]² × z≥4.5. Here the bore is SMALLER than the tool, so the
               corners (16,15) and (15,16) sit on it and the tool's inner sides
               survive in part — FIVE edges, not three, out of the same code.
                   removed = 4.5(4 − π/4) = 18 − 9π/8
                   result  = 2700 + 91π − 18 + 9π/8 = 2682 + 737π/8
"""

from __future__ import annotations

import math

import pytest

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _counterbore(k):
    return k.boolean(
        "cut", k.boolean("cut", k.box(30, 30, 10),
                         k.transform(k.cylinder(2, 10), translate=(15, 15, 0))),
        k.transform(k.cylinder(4, 3), translate=(15, 15, 7)))


def _bored_boss(k):
    return k.boolean(
        "cut", k.boolean("union", k.box(30, 30, 3),
                         k.transform(k.cylinder(4, 6), translate=(15, 15, 3))),
        k.transform(k.cylinder(1, 5), translate=(15, 15, 4)))


def _straddle(k, s):
    """Exactly the capability probe's own 'cut box' cell."""
    lo, hi = k.bbox(s)
    mid = tuple((float(lo[i]) + float(hi[i])) / 2 for i in range(3))
    return k.boolean("cut", s, k.transform(k.box(2, 2, 100), translate=mid))


CASES = [
    ("counterbore", _counterbore, 8992 - 74 * math.pi, 2 * (4 - math.pi)),
    ("bored boss", _bored_boss, 2682 + 737 * math.pi / 8, 18 - 9 * math.pi / 8),
]


@pytest.mark.parametrize("name,make,volume,removed", CASES,
                         ids=[c[0] for c in CASES])
def test_the_straddling_cut_removes_exactly_the_right_material(
        k, name, make, volume, removed) -> None:
    src = make(k)
    out = _straddle(k, src)
    before = k.mass_props(src)["volume"]
    after = k.mass_props(out)["volume"]
    assert after == pytest.approx(volume, rel=0, abs=1e-9)
    assert before - after == pytest.approx(removed, rel=0, abs=1e-9)


@pytest.mark.parametrize("name,make,volume,removed", CASES,
                         ids=[c[0] for c in CASES])
def test_the_result_is_exact_not_merely_close(
        k, name, make, volume, removed) -> None:
    """A float that lands on the right value can still have come from the wrong
    field. The answer is in ℚ[π] with no surd, so demand it exactly."""
    from fractions import Fraction as F

    from forgekernel import body as B
    from forgekernel.quadric import PiVal

    out = B.to_body(_straddle(k, make(k)))
    want = (PiVal(8992, -74) if name == "counterbore"
            else PiVal(2682, F(737, 8)))
    assert B.volume(out) == want


@pytest.mark.parametrize("name,make,volume,removed", CASES,
                         ids=[c[0] for c in CASES])
def test_the_result_is_a_closed_shell(k, name, make, volume, removed) -> None:
    """Two independent oracles the four-sided-prism mistake fails: every edge
    used by exactly two faces, and the closed-shell vector-area identity
    Σ Aᵢ·n̂ᵢ = 0, which edge pairing structurally cannot see."""
    from forgekernel import body as B

    out = B.to_body(_straddle(k, make(k)))
    assert B.manifold_violations(out) == []
    total = _vector_area(out)
    assert all(t.sign() == 0 for t in total), [float(t) for t in total]


@pytest.mark.parametrize("name,make,volume,removed", CASES,
                         ids=[c[0] for c in CASES])
def test_the_result_meshes_watertight(k, name, make, volume, removed) -> None:
    """Shipping the exact volume with a torn STL is the same failure shape the
    audit exists to prevent."""
    out = _straddle(k, make(k))
    for deflection in (0.5, 0.05):
        m = k.tessellate(out, deflection=deflection)
        use: dict = {}
        for a, b, c in m["triangles"]:
            for e in ((a, b), (b, c), (c, a)):
                key = tuple(sorted(e))
                use[key] = use.get(key, 0) + 1
        assert [e for e, n in use.items() if n != 2] == []


def test_the_notch_floor_is_three_edges_here_and_five_there(k) -> None:
    """The trap, pinned. The same classification must produce a different face
    count for the two probes — a hand-written counterbore builder is silently
    wrong on the boss, because there the tool's inner sides are only PARTLY
    inside the bore and do contribute walls."""
    from forgekernel import body as B

    def floor_edges(shape, z):
        out = B.to_body(_straddle(k, shape))
        for f in out.faces:
            if (isinstance(f.surface, B.Plane) and f.surface.n[0] == 0
                    and f.surface.n[1] == 0
                    and f.surface.d / f.surface.n[2] == z
                    and B._loop_has_arcs(f.loops[0])):
                return len(f.loops[0].edges)
        raise AssertionError("no notch floor found")

    assert floor_edges(_counterbore(k), 5) == 3
    assert floor_edges(_bored_boss(k), 9 / 2) == 5


def test_an_off_twelfth_wall_still_refuses_and_names_the_field(k) -> None:
    """The measure is new; the exact-or-refuse boundary is not. A wall at
    (a−cx)/r = 3/4 meets the bore at an angle whose sine is not algebraic in
    ℚ[√3] (Niven), so the removed area leaves every field this kernel has. That
    is a permanent boundary, and the refusal must say which offsets do work."""
    src = _counterbore(k)
    # x from 16.5, i.e. (16.5 − 15)/2 = 3/4 of the way out to the bore wall.
    # Kept inside the r=4 counterbore so that ONE bore is straddled and the
    # refusal is about the field, not about the shape being out of family.
    tool = k.transform(k.box(1.5, 1, 100), translate=(16.5, 15, 5))
    with pytest.raises(KernelError) as exc:
        k.boolean("cut", src, tool)
    msg = str(exc.value) + str(getattr(exc.value, "remedy", ""))
    assert "30" in msg
    assert "√3" in msg or "sqrt3" in msg
    assert "r/2" in msg


def test_a_reentrant_outline_refuses_at_the_guard_not_the_audit(k) -> None:
    """Found at revival, by attacking the unreviewed guards. The mouth-face
    containment test was a BBOX check on the outline, so an L-plate whose
    reentrant corner the tool pokes past sailed through classification and the
    notch removed material that does not exist. The mesh audit happened to
    catch the torn artifact — but a guard that is wrong and a net that is
    lucky is not the contract. The straddle path must classify this OUT of its
    family (a guard refusal, never an 'invalid body' audit report), and the
    seam must refuse it by name."""
    from gitcad.errors import GeometryInvalidError

    L = {"start": [0, 0], "segments": [{"kind": "line", "to": [30, 0]},
                                       {"kind": "line", "to": [30, 10]},
                                       {"kind": "line", "to": [10, 10]},
                                       {"kind": "line", "to": [10, 30]},
                                       {"kind": "line", "to": [0, 30]},
                                       {"kind": "line", "to": [0, 0]}]}
    drilled = k.boolean("cut", k.extrude(L, 8),
                        k.transform(k.cylinder(2, 8), translate=(13, 7, 0)))
    # tool corner ON the bore axis; its y 7..11 strip crosses the reentrant
    # edge y=10, beyond which (for x > 10) there is no material at all
    tool = k.transform(k.box(2, 4, 100), translate=(13, 7, 4))
    with pytest.raises(KernelError) as exc:
        k.boolean("cut", drilled, tool)
    assert not isinstance(exc.value, GeometryInvalidError), (
        "the guard let a wrong body be built and the audit had to catch it")


def test_a_pocket_overlapping_the_tool_refuses_at_the_guard(k) -> None:
    """Same defect, other direction: a through-pocket appears only as a KEPT
    inner loop of the mouth face, and nothing checked kept loops against the
    tool. The notch then counts the pocket's void as removed material."""
    from gitcad.errors import GeometryInvalidError

    pocketed = k.boolean("cut", k.box(30, 30, 10),
                         k.transform(k.box(2, 2, 100),
                                     translate=(16.5, 16.5, -5)))
    drilled = k.boolean("cut", pocketed,
                        k.transform(k.cylinder(2, 10), translate=(15, 15, 0)))
    tool = k.transform(k.box(2, 2, 100), translate=(15, 15, 5))
    with pytest.raises(KernelError) as exc:
        k.boolean("cut", drilled, tool)
    assert not isinstance(exc.value, GeometryInvalidError), (
        "the guard let a wrong body be built and the audit had to catch it")


def test_a_wall_at_half_the_radius_is_exact_in_sqrt3_pi(k) -> None:
    """The gate's remedy names r/2 as an offset that works, so it must. A wall
    at (16 − 15)/2 = r/2 crosses the bore at 60° — an odd twelfth — and the
    removed area picks up √3 from the segment term: ℚ[√3][π], the tower's
    middle floor.

    Derived by hand, not read off the implementation: the solid is
    9000 − 40π (box minus through-bore r=2), the tool spans x 16..18, y 15..17,
    z 5..105, and per unit z the removed section is
    4 − ∫₁² √(4−u²) du = 4 − 2π/3 + √3/2. Over 5 units:

        result = 9000 − 40π − 20 + 10π/3 − 5√3/2 = 8980 − (5/2)√3 − (110/3)π

    This family could never execute before: `Fraction()` coercion rejected the
    √3 crossing coordinates outright, and the first revival attempt died on
    `SurdVal ** 2` (the ADR-0019 lint's own defect class, backlog 1.4).
    """
    from fractions import Fraction as F

    from forgekernel import body as B
    from forgekernel.quadric import PiVal
    from forgekernel.surd import SurdVal

    src = k.boolean("cut", k.box(30, 30, 10),
                    k.transform(k.cylinder(2, 10), translate=(15, 15, 0)))
    out = k.boolean("cut", src, k.transform(k.box(2, 2, 100),
                                            translate=(16, 15, 5)))
    want = PiVal(SurdVal(8980, F(-5, 2), 3), F(-110, 3))
    assert B.volume(B.to_body(out)) == want
    assert B.manifold_violations(B.to_body(out)) == []
    # the mesh cannot follow an odd twelfth yet; the refusal must say so BY
    # NAME rather than crash or, worse, quietly mesh the bounding rectangle
    with pytest.raises(Exception, match="twelfths of a turn"):
        k.tessellate(out)


def _vector_area(bd):
    """Σ over faces of Area·n̂, exactly in ℚ[π]. Zero for any closed shell."""
    from fractions import Fraction as F

    from forgekernel import body as B
    from forgekernel.polypi import PiPoly

    tot = [PiPoly.rational(0)] * 3
    for f in bd.faces:
        s, sg = f.surface, (1 if f.sense else -1)
        if isinstance(s, B.Plane):
            rat, pi = F(0), F(0)
            for i, lp in enumerate(f.loops):
                circ = B._loop_is_circle(lp)
                if circ is not None:
                    pi += (1 if i == 0 else -1) * circ.r ** 2
                elif B._loop_has_arcs(lp):
                    a = (B._mixed_loop_area(lp, s.n) if i == 0
                         else B._mixed_loop_area_as_hole(lp, s.n))
                    rat, pi = rat + a[0], pi + a[1]
                else:
                    a2 = B._planar_loop_area2(lp, s.n)
                    rat += (a2 if i == 0 else -abs(a2)) / (
                        2 * B._rational_sqrt(B.dot(s.n, s.n)))
            ln = B._rational_sqrt(B.dot(s.n, s.n))
            for i in range(3):
                tot[i] = tot[i] + PiPoly([rat, pi]) * sg * (s.n[i] / ln)
        elif isinstance(s, B.Cylinder):
            h, arcs = B._band_height(f, s), B._band_arc(f)
            vint = ((F(0), F(0), F(0)) if arcs is None
                    else B._band_sweep(arcs, s)[1])
            for i in range(3):
                tot[i] = tot[i] + PiPoly([h * s.r * vint[i] * sg, F(0)])
        else:
            raise AssertionError(f"unhandled surface {type(s).__name__}")
    return tot
