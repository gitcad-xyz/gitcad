"""Closed shell on curved and composite solids (ADR-0021 / K4.1 extension).

Hollowing a solid of revolution is a PROFILE operation: the void is the (r, z)
profile inset by the wall thickness, lathed, and turned inside out. Its faces
are the inner solid's with every sense FLIPPED — a cavity's boundary points
away from the material, which is INTO the cavity — so the divergence sum
subtracts the void and the volume comes out exact with no boolean at all.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from forgekernel.brep import Solid
from forgekernel.quadric import Cone, Cyl, DrilledSolid, RevolveSolid
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def test_a_shelled_cylinder_matches_the_analytic_annulus(k) -> None:
    out = k.shell(Cyl(0, 0, 5, 0, 12), [], 1.0)
    assert k.mass_props(out)["volume"] == pytest.approx(
        math.pi * (25 * 12 - 16 * 10))


def test_a_shelled_tube_hollows_the_wall_not_the_bore(k) -> None:
    """The bore is already empty; the void belongs between the two walls.
    Profile [(3,0),(6,0),(6,10),(3,10)] insets to [(4,1),(5,1),(5,9),(4,9)]."""
    tube = RevolveSolid([(3, 0), (6, 0), (6, 10), (3, 10)], 0, 0)
    out = k.shell(tube, [], 1.0)
    assert k.mass_props(out)["volume"] == pytest.approx(
        math.pi * ((36 - 9) * 10 - (25 - 16) * 8))


@pytest.mark.parametrize("t", [1, Fraction(3, 2), 2])
def test_shelling_a_drilled_plate_builds_the_bore_a_collar(k, t) -> None:
    """Shell offsets EVERY boundary face inward by t, and a bore's cylindrical
    wall is a boundary face — so the void stops r+t from the axis and a tube of
    metal is left around the hole.

    "Shell the base, then re-drill" built no such tube, and was not refusing: a
    30x30x10 plate with a blind Ø4 bore in its top wall, shelled t=2, reported
    4918.867 against a true 5088.81 +- 6.69 (4M-sample Monte Carlo) — 170 mm3
    of collar simply absent, in a shape the kernel called good.

    With every bore going straight through, the void is the inset base MINUS
    the enlarged cylinders: an intersection of two eroded sets, so its corners
    stay sharp and no new surface type appears."""
    plate = DrilledSolid(Solid.box(40, 20, 5), [Cyl(20, 10, 4, 0, 5)])
    out = k.shell(plate, [], t)
    truth = ((40 * 20 * 5 - math.pi * 16 * 5)
             - ((40 - 2 * t) * (20 - 2 * t) * (5 - 2 * t)
                - math.pi * (4 + t) ** 2 * (5 - 2 * t)))
    assert k.mass_props(out)["volume"] == pytest.approx(float(truth))


def test_a_blind_bore_refuses_because_its_floor_erodes_to_a_torus(k) -> None:
    """A blind bore is different IN KIND, not just in difficulty: eroding
    around the reentrant rim where its floor meets its wall sweeps a torus, and
    that is a K4.2 offset surface rather than the sharp intersection the
    through case is."""
    blind = DrilledSolid(Solid.box(30, 30, 10), [Cyl(15, 15, 3, 4, 10)])
    with pytest.raises(Exception, match="torus"):
        k.shell(blind, [], 2)
    # a DrilledSolid carrying NO bores is just its base, and still shells
    assert k.mass_props(k.shell(DrilledSolid(Solid.box(20, 20, 20), []),
                                [], 2.0))["volume"] == 20 ** 3 - 16 ** 3


def test_a_shelled_body_still_meshes_watertight(k) -> None:
    from forgekernel import body as B
    from collections import defaultdict

    out = k.shell(Cyl(0, 0, 5, 0, 12), [], 1.0)
    mesh = B.tessellate(out, 0.05)
    ec = defaultdict(int)
    for a, b, c in mesh["triangles"]:
        for e in ((a, b), (b, c), (c, a)):
            ec[tuple(sorted(e))] += 1
    assert all(n == 2 for n in ec.values())


def test_a_slanted_profile_edge_refuses_rather_than_thin_the_wall(k) -> None:
    """A slanted edge's inward normal carries 1/sqrt(dr^2+dz^2), which leaves
    Q. A shell wall must be EXACTLY the requested thickness or the part is
    not the part — so refuse rather than round it."""
    with pytest.raises(Exception, match="slanted lathe profile edge"):
        k.shell(Cone(0, 0, 2, 5, 0, 10), [], 1.0)


def test_a_thickness_that_eats_the_solid_refuses(k) -> None:
    with pytest.raises(Exception, match="thickness exceeds"):
        k.shell(Cyl(0, 0, 5, 0, 12), [], 9.0)


def test_a_sphere_has_no_edges_to_blend(k) -> None:
    """fillet and chamfer of a sphere are the sphere. Returning it unchanged
    is the correct answer, not a refusal — there is no edge to act on."""
    from forgekernel.quadric import Sphere

    s = Sphere(0, 0, 0, 6)
    assert k.fillet(s, [], 1) is s
    assert k.chamfer(s, [], 1) is s


def test_a_hollow_ball_is_the_difference_of_two_spheres(k) -> None:
    from forgekernel.quadric import Sphere

    out = k.shell(Sphere(0, 0, 0, 6), [], 1.0)
    assert k.mass_props(out)["volume"] == pytest.approx(
        4 / 3 * math.pi * (6 ** 3 - 5 ** 3))


def test_hollowing_a_sphere_thinner_than_itself_refuses(k) -> None:
    from forgekernel.quadric import Sphere

    with pytest.raises(Exception, match="exceeds the sphere"):
        k.shell(Sphere(0, 0, 0, 6), [], 9.0)


NONCONVEX = [
    # outer 64 mm2 x 6; inset by 1 is 28 mm2 x 4 -> 384 - 112
    ("L-prism t=1", [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)],
     6, 1, 272),
    # inset by 1/2 is 45 mm2 x 5 -> 384 - 225
    ("L-prism t=0.5", [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)],
     6, 0.5, 159),
    # a U: the SLOT FLOOR insets DOWNWARD, because the material is below it.
    # outer 78 x 5; inset 24 x 3 -> 390 - 72
    ("U-channel", [(0, 0), (12, 0), (12, 10), (9, 10), (9, 3), (3, 3),
                   (3, 10), (0, 10)], 5, 1, 318),
]


@pytest.mark.parametrize("label,profile,h,t,want", NONCONVEX,
                         ids=[n[0] for n in NONCONVEX])
def test_a_non_convex_prism_can_be_hollowed(label, profile, h, t, want) -> None:
    """A reflex corner's inset is perfectly well defined — two inset lines
    still meet at a point — so refusing every L-bracket was too strong. What
    can actually go wrong is the inset SELF-INTERSECTING or escaping the
    profile where a notch is narrower than 2t, and that is now checked on the
    finished polygon, where it is a property of the ANSWER rather than a guess
    about the input."""
    from forgekernel.kernel import prism

    k = RefKernel()
    out = k.shell(prism(profile, h), [], t)
    assert k.mass_props(out)["volume"] == pytest.approx(want)


def test_a_notch_narrower_than_the_wall_refuses(k) -> None:
    """Where the slot is thinner than 2t the inset inverts, and a bow tie has
    a NEGATIVE Green's integral — the void would add material."""
    from forgekernel.kernel import prism

    narrow = [(0, 0), (12, 0), (12, 10), (7, 10), (7, 3), (5, 3), (5, 10),
              (0, 10)]
    with pytest.raises(Exception):
        k.shell(prism(narrow, 5), [], 2.0)
