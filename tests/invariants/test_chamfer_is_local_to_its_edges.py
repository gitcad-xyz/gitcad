"""A chamfer removes the union of its per-edge wedges. Nothing else.

Round 10 found `chamfer(box, all edges)` removing 2d³/3 more material than any
edge asked for — a silent wrong number in one of the most-used operations,
shipped and green for months.

The cause was a corner facet added on purpose. At a box corner the three
chamfer planes (x+y=d, y+z=d, z+x=d) already meet at the single point
(d/2, d/2, d/2), so the apex is a VERTEX and there is no corner face to cut.
Cutting one anyway removes the tetrahedron between that apex and the added
plane x+y+z=2d: exactly d³/12 per corner, 2d³/3 per box.

WHY ~1100 TESTS AND THE DIFFERENTIAL ORACLE ALL MISSED IT. The mesh is built
from the same face set as the exact volume, so the two agreed to 0.0000% and
the oracle's convergence check was satisfied by a shape that was simply the
wrong shape. That is the limit of any oracle sharing a face set with what it
checks, and it is why the first test below is a CONTAINMENT claim rather than a
volume claim: it is derived from the definition of a chamfer, not from any
implementation's output.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _edge_halfspaces(a, b, c, d):
    """The twelve half-spaces a chamfer is DEFINED by: for each edge, keep the
    points at combined distance >= d from it along the two adjacent faces."""
    ext = (Fraction(a), Fraction(b), Fraction(c))
    d = Fraction(d)
    out = []
    for i, j in ((0, 1), (1, 2), (0, 2)):
        for si in (-1, 1):
            for sj in (-1, 1):
                n = [0, 0, 0]
                n[i], n[j] = si, sj
                rhs = -d + (ext[i] if si > 0 else 0) + (ext[j] if sj > 0 else 0)
                out.append((tuple(n), rhs))
    return out


BOXES = [(20, 20, 20, 2), (30, 20, 10, 1), (40, 30, 20, 3)]
IDS = [f"{a}x{b}x{c} d={d}" for a, b, c, d in BOXES]


@pytest.mark.parametrize("a,b,c,d", BOXES, ids=IDS)
def test_a_chamfer_removes_nothing_outside_its_own_edge_wedges(k, a, b, c, d):
    """The definitional claim, and the one that actually caught this.

    A point strictly satisfying every edge half-space, and strictly inside the
    original box, is material NO edge chamfered away — so it must survive. The
    corner-facet bug fails here on the near-corner probe while passing every
    volume comparison, because the volume it reports is self-consistent.
    """
    solid = k.chamfer(k.box(a, b, c), [], d)
    planes = _edge_halfspaces(a, b, c, d)

    # a point just inside the corner apex (d/2,d/2,d/2) region: it clears every
    # edge wedge, but the spurious corner plane x+y+z=2d cuts exactly here
    q = (Fraction(131, 100) * d / 2, Fraction(122, 100) * d / 2,
         Fraction(117, 100) * d / 2)
    assert all(n[0] * q[0] + n[1] * q[1] + n[2] * q[2] < rhs
               for n, rhs in planes), "the probe must clear all twelve wedges"

    (lo, hi) = k.bbox(solid)
    assert all(float(lo[i]) <= float(q[i]) <= float(hi[i]) for i in range(3))

    # …so it must still be material. Ask the kernel: cutting a tiny box around
    # q must remove something.
    tiny = Fraction(1, 100)
    probe = k.transform(k.box(tiny, tiny, tiny),
                        translate=(q[0] - tiny / 2, q[1] - tiny / 2,
                                   q[2] - tiny / 2))
    before = k.mass_props(solid)["volume"]
    after = k.mass_props(k.boolean("cut", solid, probe))["volume"]
    assert after < before, (
        f"the point {tuple(float(x) for x in q)} clears every edge wedge but "
        "was already removed — the chamfer cut material no edge asked for")


@pytest.mark.parametrize("a,b,c,d", BOXES, ids=IDS)
def test_the_chamfered_volume_matches_its_closed_form(k, a, b, c, d):
    """V = abc − 2(a+b+c)d² + 6d³.

    Derived, not fitted: subtract one triangular prism of cross-section d²/2
    per edge, then add back the 8 corner over-subtractions of 3d³/4 each. It
    was checked against an independent exact vertex-enumeration of the twelve
    half-spaces before being written down here.
    """
    exact = Fraction(a * b * c) - 2 * (a + b + c) * d ** 2 + 6 * d ** 3
    got = k.mass_props(k.chamfer(k.box(a, b, c), [], d))["volume"]
    assert Fraction(got) == exact, (
        f"chamfer({a}x{b}x{c}, d={d}): got {float(got)}, exact {float(exact)}, "
        f"difference {float(Fraction(got) - exact)}")


def test_a_chamfer_never_removes_more_than_its_wedges_could(k) -> None:
    """A cheap upper bound that needs no closed form, so it keeps working when
    the shape is not a box: the removed volume can never exceed the sum of the
    per-edge wedges, because the wedges are what a chamfer is."""
    for a, b, c, d in BOXES:
        removed = Fraction(a * b * c) - Fraction(
            k.mass_props(k.chamfer(k.box(a, b, c), [], d))["volume"])
        bound = 4 * (a + b + c) * Fraction(d * d, 2)   # 12 edges, d²/2 each
        assert 0 < removed <= bound, (
            f"{a}x{b}x{c} d={d}: removed {float(removed)} exceeds the "
            f"wedge bound {float(bound)}")
