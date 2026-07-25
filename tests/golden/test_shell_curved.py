"""Closed shell on curved and composite solids (ADR-0021 / K4.1 extension).

Hollowing a solid of revolution is a PROFILE operation: the void is the (r, z)
profile inset by the wall thickness, lathed, and turned inside out. Its faces
are the inner solid's with every sense FLIPPED — a cavity's boundary points
away from the material, which is INTO the cavity — so the divergence sum
subtracts the void and the volume comes out exact with no boolean at all.
"""

from __future__ import annotations

import math

import pytest

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


def test_a_shelled_drilled_plate_keeps_its_bores(k) -> None:
    plate = DrilledSolid(Solid.box(40, 20, 5), [Cyl(20, 10, 4, 0, 5)])
    out = k.shell(plate, [], 1.0)
    assert isinstance(out, DrilledSolid) and len(out.bores) == 1
    assert k.mass_props(out)["volume"] < k.mass_props(plate)["volume"]


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
