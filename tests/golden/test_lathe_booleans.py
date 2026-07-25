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
from gitcad.errors import KernelError
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
    r"""(A u B) \ C distributes, and cutting only SHRINKS a member, so
    disjointness survives without re-checking it."""
    from forgekernel.brep import Solid
    from forgekernel.quadric import DisjointUnion

    boss = DisjointUnion([Solid.box(30, 30, 3), Cyl(15, 15, 4, 3, 9)])
    # a tool that reaches only the plate: the boss member is provably missed
    # and must come back UNTOUCHED rather than be asked to cut itself against
    # something it never meets
    tool = k.transform(k.box(2, 2, 3), translate=(1, 1, 0))
    out = k.boolean("cut", boss, tool)
    assert isinstance(out, DisjointUnion) and len(out.members) == 2
    assert k.mass_props(out)["volume"] == pytest.approx(
        k.mass_props(boss)["volume"] - 4 * 3)


def test_a_rounded_box_has_no_sharp_edge_to_blend(k) -> None:
    """Its edges are already tangent-continuous blends, so "round every sharp
    edge" has nothing to act on — the same answer a sphere gets."""
    from forgekernel.quadric import RoundedBox

    rb = RoundedBox(20, 20, 20, 3)
    assert k.fillet(rb, [], 1) is rb
    assert k.chamfer(rb, [], 1) is rb


@pytest.mark.parametrize("depth", [1, 3, 4, 6, 11])
def test_a_blind_bore_from_the_BOTTOM_removes_its_own_depth(k, depth) -> None:
    """RevolveSolid normalises the loop, so the axis always descends and the
    traversal direction is CONSTANT — it cannot say which way to step. Crossing
    the tool's near end and its far end need OPPOSITE orders, and getting it
    wrong emitted a shark fin that removed pi r^2 H/3 whatever depth was asked
    for. It was right at depth 4 by coincidence (H/3 = 4), which is exactly the
    depth a casual test would pick."""
    s = Cyl(0, 0, 5, 0, 12)
    out = k.boolean("cut", s, Cyl(0, 0, 1, -50, depth))
    removed = k.mass_props(s)["volume"] - k.mass_props(out)["volume"]
    assert removed == pytest.approx(math.pi * depth)


def test_a_bore_through_a_cone_apex_cannot_ADD_material(k) -> None:
    """The wall guard skipped an apex because it tested r != 0, so boring a
    cone's tip moved the wall OUTWARD: 293.2 against an uncut 261.8, a solid
    made larger by cutting it."""
    with pytest.raises(Exception, match="wider than the lathe"):
        k.boolean("cut", Cone(0, 0, 5, 0, 0, 10), Cyl(0, 0, 1, -5, 15))


def test_a_pocket_inside_a_coaxial_bore_removes_no_air(k) -> None:
    """The wall minimum runs over BOTH walls, so on a tube it is the BORE
    radius and any footprint fitting inside the bore passed — 'removing'
    20 mm^3 of air and leaving the shell open."""
    tube = RevolveSolid([(2, 0), (5, 0), (5, 10), (2, 10)], 0, 0)
    tool = k.transform(k.box(2, 2, 25), translate=(-1, -1, -20))
    with pytest.raises(Exception, match="not solid to the axis"):
        k.boolean("cut", tube, tool)


def test_a_pocket_spanning_a_cone_apex_refuses(k) -> None:
    """No planar face exists at the apex, so the mouth was never punched and
    the four wall tops dangled: an OPEN shell returned as a solid."""
    tool = k.transform(k.box(2, 2, 20), translate=(-1, -1, 5))
    with pytest.raises(Exception):
        k.boolean("cut", Cone(0, 0, 5, 0, 0, 10), tool)


def test_a_pocket_meeting_two_caps_at_one_height_refuses(k) -> None:
    """A lathe can have SEVERAL planar faces at one z — here an annular groove
    in the top. Punching the mouth into all of them removed 20 where the truth
    is 12, and the mesh came back watertight, so nothing downstream noticed."""
    grooved = RevolveSolid([(0, 0), (10, 0), (10, 6), (8, 6), (8, 4),
                            (5, 4), (5, 6), (0, 6)], 0, 0)
    tool = k.transform(k.box(2, 2, 17), translate=(-1, -1, 3))
    with pytest.raises(Exception, match="planar faces"):
        k.boolean("cut", grooved, tool)


def test_a_forge_refusal_reaches_the_caller_as_a_kernel_error(k) -> None:
    """An honest refusal from the kernel must not escape the seam as a bare
    ValueError — a caller cannot tell that from a bug."""
    from gitcad.errors import KernelError

    u = k.boolean("union", Cone(0, 0, 2, 5, 0, 10), Cyl(0, 0, 3, -20, 10))
    with pytest.raises(KernelError):
        k.mass_props(u)


def test_a_union_holding_a_cut_member_still_meshes(k) -> None:
    """Distributing a cut can leave a canonical Body as a member, and asking
    one for .cx is a bare AttributeError — the union measured fine but was
    unrenderable."""
    far = k.transform(k.box(2, 2, 2), translate=(500, 500, 500))
    u = k.boolean("union", Cyl(0, 0, 5, 0, 12), far)
    cut = k.boolean("cut", u, k.transform(k.box(2, 2, 20), translate=(-1, -1, 6)))
    assert len(k.tessellate(cut, deflection=0.2)["triangles"]) > 0


def test_a_tool_entirely_inside_a_bore_removes_nothing(k) -> None:
    """The material is already gone. Exactly decidable — a rectangle lies
    inside a disc exactly when its corners do, both being convex — and it is
    the honest answer, because cutting the tool out of the REMAINING shape
    would need a square-minus-circular-segment area and leave Q[pi]."""
    from forgekernel.brep import Solid
    from forgekernel.quadric import DrilledSolid

    plate = DrilledSolid(Solid.box(40, 20, 5), [Cyl(20, 10, 4, 0, 5)])
    tool = k.transform(k.box(2, 2, 100), translate=(20, 10, 2.5))
    out = k.boolean("cut", plate, tool)
    assert k.mass_props(out)["volume"] == pytest.approx(
        k.mass_props(plate)["volume"])


def test_a_tool_outside_the_bore_still_cuts(k) -> None:
    """The no-op must not swallow a real cut."""
    from forgekernel.brep import Solid
    from forgekernel.quadric import DrilledSolid

    plate = DrilledSolid(Solid.box(40, 20, 5), [Cyl(20, 10, 4, 0, 5)])
    tool = k.transform(k.box(2, 2, 100), translate=(2, 2, -50))
    out = k.boolean("cut", plate, tool)
    assert k.mass_props(plate)["volume"] - k.mass_props(out)["volume"] \
        == pytest.approx(2 * 2 * 5)


def test_a_tool_straddling_a_counterbore_step_refuses(k) -> None:
    """Only the wider bore contains the tool's footprint, and only above its
    floor. Below that the tool is outside the narrow bore, so the removed area
    is a square minus a circular segment — an arcsin, outside Q[pi]."""
    from forgekernel.brep import Solid
    from forgekernel.quadric import DrilledSolid

    cb = (DrilledSolid(Solid.box(30, 30, 10), [])
          .cut(Cyl(15, 15, 2, 0, 10)).cut(Cyl(15, 15, 4, 7, 10)))
    tool = k.transform(k.box(2, 2, 100), translate=(15, 15, 5))
    with pytest.raises(Exception):
        k.boolean("cut", cb, tool)


def test_a_union_falls_through_to_the_seams_own_distribution(k) -> None:
    """DisjointUnion.cut only knows some member types, and refusing on the
    seam's behalf hid the cases the seam handles: lathes, misses and pockets.

    Here the tube member ALREADY has an r=1 bore from z=4 and the tool is an
    r=1 cylinder from z=4.5 up, so the tool coincides with the bore and
    removing nothing is the correct answer — not an accidental no-op. The
    plate member is missed outright (the tool starts above it)."""
    from forgekernel.quadric import DisjointUnion, RevolveSolid
    from forgekernel.brep import Solid

    boss = DisjointUnion([
        Solid.box(30, 30, 3),
        RevolveSolid([(0, 3), (4, 3), (4, 9), (1, 9), (1, 4), (0, 4)], 15, 15)])
    tool = k.transform(k.cylinder(1, 100), translate=(15, 15, 4.5))
    out = k.boolean("cut", boss, tool)
    assert k.mass_props(out)["volume"] == pytest.approx(
        k.mass_props(boss)["volume"])
    # ...and the no-op is not vacuous: a WIDER tool would have to WIDEN the
    # existing bore, which a profile clamp cannot express, and refuses
    wider = k.transform(k.cylinder(2, 100), translate=(15, 15, 4.5))
    with pytest.raises(Exception, match="wider than the lathe"):
        k.boolean("cut", boss, wider)


ROUNDED_POCKETS = [
    ("circular", lambda k, mid: k.transform(k.cylinder(1, 100), translate=mid),
     math.pi * 10),
    ("square", lambda k, mid: k.transform(k.box(2, 2, 100), translate=mid), 40.0),
]


@pytest.mark.parametrize("label,make,want", ROUNDED_POCKETS,
                         ids=[r[0] for r in ROUNDED_POCKETS])
def test_a_pocket_sinks_into_a_rounded_boxs_flat(label, make, want) -> None:
    """A rounded box's flats are ORDINARY PLANES, so nothing about the fillets
    participates as long as the mouth stays clear of them — it is the same
    construction a lathe pocket uses with the source body left general."""
    from forgekernel.quadric import RoundedBox

    k = RefKernel()
    rb = RoundedBox(20, 20, 20, 3)
    out = k.boolean("cut", rb, make(k, (10, 10, 10)))
    assert k.mass_props(rb)["volume"] - k.mass_props(out)["volume"] \
        == pytest.approx(want)


@pytest.mark.parametrize("label,make,want", ROUNDED_POCKETS,
                         ids=[r[0] for r in ROUNDED_POCKETS])
def test_a_pocketed_rounded_box_meshes_watertight(label, make, want) -> None:
    from collections import defaultdict

    from forgekernel import body as B
    from forgekernel.quadric import RoundedBox

    k = RefKernel()
    out = k.boolean("cut", RoundedBox(20, 20, 20, 3), make(k, (10, 10, 10)))
    ec = defaultdict(int)
    for a, b, c in B.tessellate(out, 0.1)["triangles"]:
        for e in ((a, b), (b, c), (c, a)):
            ec[tuple(sorted(e))] += 1
    assert all(n == 2 for n in ec.values())


def test_a_pocket_reaching_a_rounded_boxs_fillet_refuses(k) -> None:
    """Past the flat the mouth would meet a quarter-cylinder band, and the cap
    is no longer the only face it cuts."""
    from forgekernel.quadric import RoundedBox

    tool = k.transform(k.cylinder(1, 100), translate=(2, 10, 10))
    with pytest.raises(Exception, match="strictly inside one flat"):
        k.boolean("cut", RoundedBox(20, 20, 20, 3), tool)


# --- the seventh adversarial review: pocket constructions ---------------------

def test_a_compound_whose_volume_matches_its_bbox_is_not_a_box(k) -> None:
    """The pocket paths asked ``volume() == dx*dy*dz`` and read a yes as "this
    tool is a box", then cut the tool's BOUNDING BOX. ``Solid.volume()`` is
    additive over polys, so a compound whose overlap exactly pays for its gap
    passes: an L of a 4x3 and a 2x2 sharing a 2x1 corner has area 14 inside a
    4x4 bbox, and 4*4*4 == 64 either way.

    Cut into a rounded box it removed 48 mm3 where the truth is 42 — silently,
    with a watertight mesh. The predicate is the POINT SET, not the measure."""
    tool = k.compound([k.transform(k.box(4, 3, 4), translate=(3, 3, 3)),
                       k.transform(k.box(2, 2, 4), translate=(3, 5, 3))])
    assert tool.volume() == 4 * 4 * 4          # the trap, still baited
    assert k._box_check(tool) is None          # and the predicate that sees it
    base = RoundedBox(12, 10, 6, 2)            # top flat [2,10] x [2,8]
    before = float(k.mass_props(base)["volume"])
    with pytest.raises(KernelError, match="quadric operands"):
        k.boolean("cut", base, tool)           # NOT 48 mm3 removed
    # the honest box still cuts, and removes exactly its own footprint x depth
    box = k.transform(k.box(4, 4, 4), translate=(3, 3, 3))
    got = float(k.mass_props(k.boolean("cut", base, box))["volume"])
    assert before - got == pytest.approx(4 * 4 * 3)


MIRRORS = [
    ("rect low-y", (4, 2)), ("rect high-y", (4, 4)),
    ("rect low-x", (2, 3)), ("rect high-x", (6, 3)),
]


@pytest.mark.parametrize("label,xy", MIRRORS, ids=[m[0] for m in MIRRORS])
def test_a_mouth_tangent_to_its_flat_refuses_from_every_side(k, label, xy) -> None:
    """The containment guard was a crossing-parity test, which is half-open:
    inclusive on the min-x/min-y edges and exclusive on the others. A pocket
    tangent to its flat's boundary was accepted on two sides and refused on the
    other two — so the same part rotated 180 degrees about z built or refused
    depending on which way it landed, and the accepted B-rep had the cap's
    inner loop coincident with its outer along a segment."""
    rb = RoundedBox(10, 8, 6, 2)               # top flat is [2,8] x [2,6]
    tool = k.transform(k.box(2, 2, 4), translate=(xy[0], xy[1], 4))
    with pytest.raises(KernelError, match="strictly inside"):
        k.boolean("cut", rb, tool)


def test_the_guard_is_exact_at_a_magnitude_no_float_can_hold(k) -> None:
    """The ring was taken through ``float()``. At 2**53 the cap's own corner
    rounds DOWN, and a mouth starting a full 1.0 OUTSIDE the flat was accepted
    — it removed 264 where the truth is 264 - (4 - pi), and left a mesh with 18
    non-manifold edges. ADR-0019: a float must never decide topology."""
    big = 2 ** 53
    rb = RoundedBox(20, 16, 12, 1, origin=(big, 0, 0))
    tool = k.transform(k.box(4, 4, 6), translate=(big, 4, 6))
    with pytest.raises(KernelError, match="strictly inside"):
        k.boolean("cut", rb, tool)


# the base is 6 tall and every tool opens at z = 4, so the depth is 2
POCKETS = [("circle", lambda k: Cyl(5, 4, 1, 4, 7), math.pi * 1 * 2),
           ("fractional r", lambda k: Cyl(5, 4, 1.0 / 3, 4, 7),
            math.pi * (1 / 3.0) ** 2 * 2),
           ("rect", lambda k: k.transform(k.box(2, 2, 4), translate=(4, 3, 4)),
            2 * 2 * 2)]


@pytest.mark.parametrize("label,tool,removed", POCKETS,
                         ids=[p[0] for p in POCKETS])
def test_a_pocket_exports_a_closed_shell_and_validates(k, label, tool,
                                                       removed) -> None:
    """Every CIRCULAR pocket shipped a STEP file whose shell was open at the
    mouth rim: the mouth circle was handed to the writer already reversed,
    which inverted the outer/inner decision the writer makes from the circle's
    axis, so the rim ran the same way as the bore wall's. Two non-manifold
    edges in a MANIFOLD_SOLID_BREP — a file that opens, and then will not
    boolean, will not mesh for CAM, and imports as a surface soup."""
    from forgekernel import body as B
    from forgekernel.stepbody import write_step_body

    base = RoundedBox(10, 8, 6, 1)
    before = float(k.mass_props(base)["volume"])
    out = k.boolean("cut", base, tool(k))
    assert before - float(k.mass_props(out)["volume"]) == pytest.approx(removed)
    assert B.manifold_violations(B.to_body(out)) == []
    assert k.validate(out).ok
    write_step_body(B.to_body(out))            # the writer's own audit runs here


def test_a_tool_that_provably_misses_gives_the_solid_back(k) -> None:
    """Bbox separation in any one axis settles a cut exactly, and it belongs
    ahead of every representation-specific path: a drilled solid asked to cut a
    tool it never meets refused with "bore misses the solid in xy" rather than
    handing back the solid it already was."""
    plate = k.boolean("cut", Solid.box(40, 20, 5),
                      k.transform(k.cylinder(4, 5), translate=(20, 10, 0)))
    far = k.transform(k.box(5, 5, 5), translate=(100, 100, 100))
    assert k.boolean("cut", plate, far) is plate


NOTCH_L = {"start": [0, 0], "segments": [
    {"kind": "line", "to": [30, 0]}, {"kind": "line", "to": [30, 10]},
    {"kind": "line", "to": [10, 10]}, {"kind": "line", "to": [10, 30]},
    {"kind": "line", "to": [0, 30]}, {"kind": "line", "to": [0, 0]}]}


def test_a_bore_down_a_notch_gives_the_solid_back_rather_than_refusing(k) -> None:
    """The two shapes overlap in every axis and the disc still never touches
    material: an L-prism's bbox centre is in the NOTCH. Bbox separation cannot
    see that, so the kernel refused "bore misses the solid in xy (nothing to
    drill)" — a refusal whose own text states the answer. The disc-vs-shadow
    test is exact (a clamped ratio compared against r^2), and it is checked
    against the SHADOW, since a closed solid's shadow is its boundary's."""
    prism = k.extrude(NOTCH_L, 8)
    assert float(k.mass_props(prism)["volume"]) == 30 * 10 * 8 + 10 * 20 * 8
    bore = k.transform(k.cylinder(1, 100), translate=(15, 15, 4))
    assert k.boolean("cut", prism, bore) is prism

    # ...and a bore that DOES meet the material still cuts, to the millimetre:
    # the tool spans z 4..104 and the prism z 0..8, so the depth is 4
    hit = k.boolean("cut", prism, k.transform(k.cylinder(1, 100),
                                              translate=(5, 5, 4)))
    removed = float(k.mass_props(prism)["volume"]) - float(
        k.mass_props(hit)["volume"])
    assert removed == pytest.approx(math.pi * 1 * 4)


# the notch's walls are x = 10 (y >= 10) and y = 10 (x >= 10), meeting at the
# reflex corner (10, 10)
TANGENT = [("well inside the notch", (15, 15), 1, True),
           ("centre on the wall", (10, 20), 1, False),
           ("just short of the wall", (12, 20), 1.9, True),
           ("exactly touching the wall", (12, 20), 2, False),
           ("short of a reflex corner", (11.2, 11.2), 1, True),
           ("reaching a reflex corner", (11.2, 11.2), 1.2, False)]


@pytest.mark.parametrize("label,c,r,misses", TANGENT,
                         ids=[t[0] for t in TANGENT])
def test_the_miss_predicate_is_tight_at_the_wall(k, label, c, r, misses) -> None:
    """Claiming a miss where material exists would be a silent wrong answer —
    the exact failure mode this whole burn-down is about. Tangency counts as a
    hit and falls through to the ordinary path."""
    from fractions import Fraction as Q

    from gitcad.kernel.ref import _disc_misses_solid

    prism = k.extrude(NOTCH_L, 8)
    assert _disc_misses_solid(prism, Q(c[0]), Q(c[1]), Q(str(r))) is misses
