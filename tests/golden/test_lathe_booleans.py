"""Coaxial booleans on solids of revolution (K2.2, the tractable half).

The probe's "cut cylinder" is a bore straight through the middle and its
"union box" puts the tool FAR away. Neither needs surface-surface intersection:
a cylinder coaxial with a solid of revolution meets the profile plane in a
straight line, and a disjoint union is settled by exact bbox separation. Only
the genuinely oblique cases need conic sections.
"""

from __future__ import annotations

import math

import pytest

from forgekernel.brep import Solid
from forgekernel.quadric import Cone, Cyl, RevolveSolid, RoundedBox
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _bore(k, s, r=1):
    return k.boolean("cut", s, k.transform(k.cylinder(r, 100),
                                           translate=(0, 0, -50)))


BORES = [
    ("cylinder", lambda: Cyl(0, 0, 5, 0, 12), math.pi * (25 - 1) * 12),
    ("cone frustum", lambda: Cone(0, 0, 2, 5, 0, 10),
     math.pi * 10 * (4 + 10 + 25) / 3 - math.pi * 10),
    ("stepped shaft",
     lambda: RevolveSolid([(0, 0), (4, 0), (4, 5), (7, 5), (7, 9), (0, 9)], 0, 0),
     None),
]


@pytest.mark.parametrize("label,build,want", BORES, ids=[b[0] for b in BORES])
def test_a_coaxial_bore_stays_a_solid_of_revolution(label, build, want) -> None:
    s = build()
    out = _bore(k := RefKernel(), s)
    assert isinstance(out, RevolveSolid)
    v = k.mass_props(out)["volume"]
    if want is not None:
        assert v == pytest.approx(want)
    else:
        assert v == pytest.approx(k.mass_props(s)["volume"] - math.pi * 9)


def test_a_bore_that_does_not_pass_through_refuses(k) -> None:
    """A partial bore leaves a blind pocket whose floor is a new face — a
    different solid, not a clamped profile."""
    short = k.transform(k.cylinder(1, 4), translate=(0, 0, 2))
    with pytest.raises(Exception, match="pass through"):
        k.boolean("cut", Cyl(0, 0, 5, 0, 12), short)


def test_a_bore_wider_than_the_part_refuses(k) -> None:
    with pytest.raises(Exception, match="wider than the lathe"):
        _bore(k, Cyl(0, 0, 2, 0, 12), r=3)


def test_an_off_axis_bore_is_not_taken_as_coaxial(k) -> None:
    """Not a lathe operation at all — it must not silently clamp the profile."""
    tool = k.transform(k.cylinder(1, 100), translate=(3, 0, -50))
    with pytest.raises(Exception):
        k.boolean("cut", Cyl(0, 0, 5, 0, 12), tool)


FAR_UNION = [
    ("cylinder", lambda: Cyl(0, 0, 5, 0, 12)),
    ("revolve", lambda: RevolveSolid([(0, 0), (4, 0), (4, 9), (0, 9)], 0, 0)),
    ("rounded box", lambda: RoundedBox(20, 20, 20, 3)),
]


@pytest.mark.parametrize("label,build", FAR_UNION, ids=[f[0] for f in FAR_UNION])
def test_a_union_with_a_far_away_box_is_a_disjoint_union(label, build) -> None:
    """Provably disjoint by exact bbox separation. RevolveSolid and RoundedBox
    were not on the 'curved' list, so this never reached the DisjointUnion
    path and died in the planar BSP engine instead."""
    from forgekernel.quadric import DisjointUnion

    k = RefKernel()
    s = build()
    far = k.transform(k.box(2, 2, 2), translate=(500, 500, 500))
    out = k.boolean("union", s, far)
    assert isinstance(out, DisjointUnion)
    assert k.mass_props(out)["volume"] == pytest.approx(
        k.mass_props(s)["volume"] + 8)
