"""Shelling a CONE — the first offset of a slanted surface (K4.2, partial).

Why this needed a number field rather than an algorithm. Shelling offsets every
boundary face inward by ``t``. For a rectilinear lathe profile each face normal
is an axis direction, so the offset vertices stay in ℚ and the old
``_inset_profile`` could just add the two unit normals. A cone's slant has
normal ``(-dz, dr)/√(dr²+dz²)``, and that ``√`` is the whole obstruction: the
offset profile's vertices land at IRRATIONAL radii, so the void was not
EXPRESSIBLE — not merely hard to compute. It refused with
"shell(slanted lathe profile edge) — K4.2".

Two things closed it, both already in the tree:

  * ``exact.F()`` was widened so a value already exact in ℚ[√d] passes through
    untouched, which lets a surd radius sit in the canonical B-rep at all;
  * ``surdrev.contour_r2_dz`` gives the exact Green term ``∮r² dz`` over a
    profile whose coordinates live in ℚ[√d].

What remains here is the OFFSET ITSELF, and the correction it forced: summing
the two adjacent unit normals is only the mitre when they are PERPENDICULAR.
``s·n₁ = s·n₂ = t`` is the actual condition, a 2×2 solve that reduces to the
old sum for a rectilinear corner and is simply a different point for any other.

INDEPENDENT ORACLE. Every number below was derived twice: once symbolically
(mitred offset profile → ``contour_r2_dz`` → ×π) and once by Monte Carlo over
the DEFINITION of a shell — the points of a convex solid within ``t`` of its
boundary, with distance-to-boundary written longhand as the minimum over the
three bounding surfaces. 8M samples, two seeds each:

    cone(r1=6, r2=2, h=10), t=1  exact 308.3686  MC 308.5526 ± 0.60, 308.4031 ± 0.60
    cone(r1=2, r2=5, h=10), t=1  exact 244.7480  MC 244.6645 ± 0.44, 244.7072 ± 0.44

The mitred offset equals the true erosion only where the profile is CONVEX (at
a reflex corner the erosion carries an arc of radius t about the vertex, which
is a genuine K4.2 surface). That is exactly the gate the kernel applies before
it will offset a slanted edge, so the two derivations above describe the same
solid rather than two different ones that happen to agree.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from forgekernel.quadric import Cone, RevolveSolid
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _pi_coeff(vol):
    """The π coefficient of an exact volume, whatever ring it landed in."""
    from forgekernel.polypi import PiPoly

    if isinstance(vol, PiPoly):
        assert vol.degree <= 1, f"volume carries π² : {vol!r}"
        assert vol[0] == 0, f"volume carries a non-π part : {vol!r}"
        return vol[1]
    assert vol.a == 0, f"volume carries a non-π part : {vol!r}"
    return vol.b


# --------------------------------------------------------------- exact volume

def test_a_tapering_cone_shells_to_an_exact_surd_volume(k) -> None:
    """cone r1=6 @ z=0, r2=2 @ z=10, t=1.

    The slant runs (6,0)→(2,10), so its inward normal is (-10,-4)/√116 and the
    offset profile is

        (0,1) — ((28-√29)/5, 1) — ((12-√29)/5, 9) — (0,9)

    a frustum again, because an offset of a straight profile edge is parallel
    to it. Green then gives

        V_void = 8π/3 · (a² + ab + b²) = π(10808/75 − (64/5)√29)
        V      = 520π/3 − V_void       = π(2192/75 + (64/5)√29)

    ≈ 308.36861, against a Monte-Carlo erosion estimate of 308.55 ± 0.60.
    """
    from forgekernel import body as B
    from forgekernel.surd import SurdVal

    out = k.shell(Cone(0, 0, 6, 2, 0, 10), [], 1)
    want = SurdVal(Fraction(2192, 75), Fraction(64, 5), 29)
    assert _pi_coeff(B.volume(out)) == want
    assert k.mass_props(out)["volume"] == pytest.approx(308.36860700365753)


def test_a_widening_cone_shells_to_an_exact_surd_volume(k) -> None:
    """cone r1=2 @ z=0, r2=5 @ z=10, t=1 — the taper the other way, so the
    void's radii are (23-√109)/10 and (47-√109)/10 and

        V = 130π − π(8292 − 420√109)/75 = π(1458/75 + (420/75)√109)

    ≈ 244.74803, against Monte Carlo 244.66 ± 0.44 and 244.71 ± 0.44.
    """
    from forgekernel import body as B
    from forgekernel.surd import SurdVal

    out = k.shell(Cone(0, 0, 2, 5, 0, 10), [], 1)
    want = SurdVal(Fraction(1458, 75), Fraction(420, 75), 109)
    assert _pi_coeff(B.volume(out)) == want
    assert k.mass_props(out)["volume"] == pytest.approx(244.74802647165245)


def test_the_wall_is_exactly_t_thick_measured_perpendicular(k) -> None:
    """The point of the mitre. Summing the two adjacent unit normals — what
    the rectilinear inset did — puts the offset vertex at ``t(n₁+n₂)``, whose
    distance to the slant is ``t(1 + n₁·n₂)``: correct only when the corner is
    a right angle. On this cone n₁·n₂ = -4/√116, so the old rule would have
    left the wall 0.6285 mm thick where 1 mm was asked for.

    Floats here are a MEASUREMENT of an exactly-constructed profile, never a
    decision — ADR-0019.
    """
    from gitcad.kernel.ref import _inset_profile_exact

    prof = [(Fraction(0), Fraction(0)), (Fraction(6), Fraction(0)),
            (Fraction(2), Fraction(10)), (Fraction(0), Fraction(10))]
    inset = _inset_profile_exact(prof, Fraction(1))
    # perpendicular distance from each offset vertex to the slant's LINE
    ax, az, bx, bz = 6.0, 0.0, 2.0, 10.0
    dr, dz = bx - ax, bz - az
    ln = math.hypot(dr, dz)
    for (r, z) in inset[1:3]:                     # the two mitred corners
        d = abs(-dz * (float(r) - ax) + dr * (float(z) - az)) / ln
        assert d == pytest.approx(1.0)


def test_the_shelled_cone_meshes_watertight(k) -> None:
    from collections import defaultdict

    from forgekernel import body as B

    out = k.shell(Cone(0, 0, 6, 2, 0, 10), [], 1)
    mesh = B.tessellate(out, 0.05)
    ec: dict = defaultdict(int)
    for a, b, c in mesh["triangles"]:
        for e in ((a, b), (b, c), (c, a)):
            ec[tuple(sorted(e))] += 1
    assert all(n == 2 for n in ec.values())


@pytest.mark.parametrize("r1,r2", [(6, 2), (2, 5)])
def test_the_shelled_cone_agrees_with_the_differential_oracle(k, r1, r2) -> None:
    """The permanent version of the check that made these numbers trustworthy.

    ``bench.oracle`` reaches the volume through completely different code:
    tessellate, then ray-cast a Monte-Carlo membership test against the MESH,
    then extrapolate the mesh error to deflection zero. Nothing about the
    divergence-theorem sum or the ℚ[√d] offset is reused. A unit test that
    asserts the number the implementation produced only restates the bug —
    this is the one that would catch a wrong mitre.
    """
    from gitcad.bench.oracle import sweep

    shape = k.shell(Cone(0, 0, r1, r2, 0, 10), [], 1)
    (row,) = sweep(kernel=k, n=20000, seed=1, shapes={"shelled cone": shape})
    assert row.ok, (f"residual {float(row.residual) * 100:.4f}% "
                    f"z={float(row.z):.2f} exact={float(row.exact):.4f} "
                    f"mc={float(row.mc):.4f}")


def test_a_shelled_cone_still_reports_its_bbox_and_centroid(k) -> None:
    """The seam has to survive surd coordinates, not just the volume call."""
    out = k.shell(Cone(0, 0, 6, 2, 0, 10), [], 1)
    lo, hi = k.bbox(out)
    assert (float(lo[0]), float(lo[2])) == pytest.approx((-6.0, 0.0))
    assert (float(hi[0]), float(hi[2])) == pytest.approx((6.0, 10.0))
    cz = k.mass_props(out)["centroid"][2]
    assert 0.0 < float(cz) < 10.0


# ------------------------------------------------------------------ refusals

def test_a_thickness_that_outruns_the_taper_refuses_with_a_measurement(k) -> None:
    """Not a kernel gap: a shell thicker than the part is a bad part. The
    offset of the small end crosses the axis, so the void has negative radius
    long before anything else goes wrong."""
    with pytest.raises(Exception, match="exceeds the lathe's radius"):
        k.shell(Cone(0, 0, 6, 2, 0, 10), [], 3)


def test_two_different_slants_need_a_bigger_field_and_refuse(k) -> None:
    """One slant puts the profile in ℚ[√d]. TWO, with different d, put it in
    ℚ[√d₁, √d₂] — a biquadratic field ``SurdVal`` does not hold. Refuse by
    name rather than float one of the two roots."""
    prof = RevolveSolid([(0, 0), (4, 0), (6, 5), (3, 10), (0, 10)], 0, 0)
    with pytest.raises(Exception, match="two different slant"):
        k.shell(prof, [], 1)


def test_a_reflex_corner_beside_a_slant_refuses(k) -> None:
    """Where the profile turns back on itself the true offset carries an ARC
    of radius t about the reflex vertex; the mitred corner is a different
    solid. The rectilinear path has always shipped the mitre (that IS the CAD
    shell), but a slanted reflex corner is new capability, so it is only
    allowed where mitre and erosion provably coincide — a convex profile."""
    prof = RevolveSolid([(0, 0), (8, 0), (8, 4), (3, 6), (3, 10), (0, 10)],
                        0, 0)
    with pytest.raises(Exception, match="reflex corner"):
        k.shell(prof, [], 1)
