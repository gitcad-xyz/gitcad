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


def test_a_blind_coaxial_bore_is_still_a_solid_of_revolution(k) -> None:
    """Through and blind are the SAME operation on the profile — a blind bore
    just leaves a floor where the tool stopped, and the axis below it stays
    solid. A d=10 x 12 cylinder bored r=1 from z=6 up loses exactly 6 pi."""
    tool = k.transform(k.cylinder(1, 100), translate=(0, 0, 6))
    out = k.boolean("cut", Cyl(0, 0, 5, 0, 12), tool)
    assert isinstance(out, RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(math.pi * (300 - 6))


def test_a_bore_open_at_neither_end_refuses(k) -> None:
    """That is an internal cavity, not a hole: the profile would need a second
    loop, and the result is no longer one closed (r, z) boundary."""
    short = k.transform(k.cylinder(1, 4), translate=(0, 0, 2))
    with pytest.raises(Exception, match="neither end"):
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


POCKETS = [
    ("cylinder", lambda: Cyl(0, 0, 5, 0, 12)),
    ("cone", lambda: Cone(0, 0, 2, 5, 0, 10)),
    ("stepped shaft",
     lambda: RevolveSolid([(0, 0), (4, 0), (4, 5), (7, 5), (7, 9), (0, 9)], 0, 0)),
]


@pytest.mark.parametrize("label,build", POCKETS, ids=[p[0] for p in POCKETS])
def test_a_prism_pocket_removes_exactly_its_own_volume(label, build) -> None:
    """A plane PARALLEL to a lathe's axis meets its cylindrical faces in
    straight LINES and its disks in chords — no conic sections and no new
    surface type. Only the topology has to be built: the open end's cap gains
    an inner loop, the prism contributes four walls, and a blind pocket a
    floor."""
    k = RefKernel()
    s = build()
    lo, hi = k.bbox(s)
    mid = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    out = k.boolean("cut", s, k.transform(k.box(2, 2, 100), translate=mid))
    removed = k.mass_props(s)["volume"] - k.mass_props(out)["volume"]
    assert removed == pytest.approx(4 * (hi[2] - mid[2]))


@pytest.mark.parametrize("label,build", POCKETS, ids=[p[0] for p in POCKETS])
def test_a_pocketed_lathe_meshes_watertight(label, build) -> None:
    from collections import defaultdict

    from forgekernel import body as B

    k = RefKernel()
    s = build()
    lo, hi = k.bbox(s)
    mid = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    out = k.boolean("cut", s, k.transform(k.box(2, 2, 100), translate=mid))
    ec = defaultdict(int)
    for a, b, c in B.tessellate(out, 0.05)["triangles"]:
        for e in ((a, b), (b, c), (c, a)):
            ec[tuple(sorted(e))] += 1
    assert all(n == 2 for n in ec.values())


def test_a_prism_reaching_the_wall_refuses(k) -> None:
    """Then it breaks OUT through the cylindrical face, the outer wall is no
    longer whole, and these are not the right faces at all."""
    tool = k.transform(k.box(2, 2, 100), translate=(4, 0, 6))
    with pytest.raises(Exception, match="reaches the lathe"):
        k.boolean("cut", Cyl(0, 0, 5, 0, 12), tool)


def test_a_prism_open_at_both_ends_refuses(k) -> None:
    """It would split the lathe into two solids, not pocket one."""
    tool = k.transform(k.box(2, 2, 100), translate=(0, 0, -40))
    with pytest.raises(Exception, match="both ends"):
        k.boolean("cut", Cyl(0, 0, 5, 0, 12), tool)


def test_the_wall_guard_walks_edges_not_just_vertices(k) -> None:
    """The material radius over [za, zb] is NOT the profile's VERTEX radii
    there: on a cone the wall shrinks between vertices, and a vertex outside
    the range still bounds the material inside it. Using vertices alone was
    wrong in BOTH directions — it refused a cone pocket that fits, and would
    have accepted one that breaks straight out."""
    fits = Cone(0, 0, 2, 5, 0, 10)          # wall is 3.5 at the pocket's floor
    breaks = Cone(0, 0, 1, 3, 0, 10)        # wall is 2.0 there, corner is 2.83
    for s, ok in ((fits, True), (breaks, False)):
        lo, hi = k.bbox(s)
        mid = tuple((lo[i] + hi[i]) / 2 for i in range(3))
        tool = k.transform(k.box(2, 2, 100), translate=mid)
        if ok:
            out = k.boolean("cut", s, tool)
            assert k.mass_props(s)["volume"] - k.mass_props(out)["volume"] \
                == pytest.approx(4 * (hi[2] - mid[2]))
        else:
            with pytest.raises(Exception, match="reaches the lathe"):
                k.boolean("cut", s, tool)


def test_cutting_a_drilled_solid_keeps_its_bores(k) -> None:
    """The base is planar, so the exact BSP engine cuts it; the bores are then
    re-applied with the full-height-column precondition still in force."""
    from forgekernel.brep import Solid
    from forgekernel.quadric import DrilledSolid

    plate = DrilledSolid(Solid.box(40, 20, 5), [Cyl(20, 10, 4, 0, 5)])
    tool = k.transform(k.box(2, 2, 100), translate=(4, 4, -50))
    out = k.boolean("cut", plate, tool)
    assert isinstance(out, DrilledSolid) and len(out.bores) == 1
    assert k.mass_props(out)["volume"] == pytest.approx(
        k.mass_props(plate)["volume"] - 4 * 5)


def test_cutting_a_disjoint_union_distributes_over_its_members(k) -> None:
    """(A u B) \ C distributes, and cutting only SHRINKS a member, so
    disjointness survives without re-checking it."""
    from forgekernel.brep import Solid
    from forgekernel.quadric import DisjointUnion

    boss = DisjointUnion([Solid.box(30, 30, 3), Cyl(15, 15, 4, 3, 9)])
    tool = k.transform(k.box(2, 2, 100), translate=(1, 1, -50))
    out = k.boolean("cut", boss, tool)
    assert isinstance(out, DisjointUnion)
    assert k.mass_props(out)["volume"] < k.mass_props(boss)["volume"]


def test_a_rounded_box_has_no_sharp_edge_to_blend(k) -> None:
    """Its edges are already tangent-continuous blends, so "round every sharp
    edge" has nothing to act on — the same answer a sphere gets."""
    from forgekernel.quadric import RoundedBox

    rb = RoundedBox(20, 20, 20, 3)
    assert k.fillet(rb, [], 1) is rb
    assert k.chamfer(rb, [], 1) is rb
