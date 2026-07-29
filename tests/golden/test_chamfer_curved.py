"""Chamfer on curved and composite solids (ADR-0021 fallbacks).

A 45-degree cut on a lathed rim sweeps a cone frustum, so a chamfered solid
of revolution is STILL a solid of revolution — no new surface type and no
approximation. A chamfered drilled solid is its base chamfered and re-drilled,
with the bore validation kept so a bore the chamfer ate into refuses rather
than shipping a part with a broken-out hole.
"""

from __future__ import annotations

import math

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from forgekernel.brep import Solid
from forgekernel.quadric import Cyl, DisjointUnion, DrilledSolid, RevolveSolid
from gitcad.kernel.ref import RefKernel
from gitcad.kernel import source_form  # ADR-0022


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _vol(k, s):
    return k.mass_props(s)["volume"]


def test_chamfering_a_cylinder_removes_the_analytic_ring(k) -> None:
    """Both rims of a d=10 x 12 cylinder, chamfered 1 mm. Each removes a ring
    of triangular section: 2*pi*r_bar*A with r_bar = (4+5+5)/3 and A = 1/2."""
    cyl = Cyl(0, 0, 5, 0, 12)
    out = k.chamfer(cyl, (), 1.0)
    assert isinstance(source_form(out), RevolveSolid)
    removed = _vol(k, cyl) - _vol(k, out)
    assert removed == pytest.approx(2 * (2 * math.pi * (14 / 3) * 0.5))


def test_chamfering_a_tube_chamfers_the_bore_rims_too(k) -> None:
    tube = RevolveSolid([(3, 0), (6, 0), (6, 10), (3, 10)], 0, 0)
    out = k.chamfer(tube, (), 1.0)
    removed = _vol(k, tube) - _vol(k, out)
    outer = 2 * (2 * math.pi * ((5 + 6 + 6) / 3) * 0.5)
    inner = 2 * (2 * math.pi * ((4 + 3 + 3) / 3) * 0.5)
    assert removed == pytest.approx(outer + inner)


def test_chamfering_a_drilled_solid_keeps_its_bores(k) -> None:
    plate = DrilledSolid(Solid.box(40, 20, 5), [Cyl(20, 10, 4, 0, 5)])
    out = k.chamfer(plate, (), 1.0)
    assert isinstance(source_form(out), DrilledSolid)
    assert len(source_form(out).bores) == 1
    assert _vol(k, out) < _vol(k, plate)


def test_a_bore_the_chamfer_would_break_into_refuses(k) -> None:
    """Honest refusal, not a silently broken-out hole: the bore is 1 mm from
    the wall and a 1 mm chamfer reaches it."""
    plate = DrilledSolid(Solid.box(40, 20, 5), [Cyl(4, 4, 3, 0, 5)])
    with pytest.raises(Exception, match="crosses a lateral wall"):
        k.chamfer(plate, (), 1.0)


def test_chamfering_a_disjoint_union_chamfers_every_member(k) -> None:
    """A chamfer only REMOVES material, so disjoint members stay disjoint."""
    boss = DisjointUnion([Solid.box(30, 30, 3), Cyl(15, 15, 4, 3, 9)])
    out = k.chamfer(boss, (), 0.5)
    assert isinstance(source_form(out), DisjointUnion)
    assert len(source_form(out).members) == 2
    assert _vol(k, out) < _vol(k, boss)


def test_a_bore_at_the_centre_of_a_chamfered_plate_is_not_lost(k) -> None:
    """The footprint predicate used parity over LATERAL edges, which is only
    equivalent for a prism: a chamfer's slanted faces project to bands whose
    extra crossings flip the parity back, so a bore at the dead centre read as
    missing the solid entirely."""
    from forgekernel.quadric import _xy_inside_footprint
    from forgekernel.kernel import chamfer as fk_chamfer

    chamfered = fk_chamfer(Solid.box(40, 20, 5), 1.0)
    assert _xy_inside_footprint(chamfered, 20, 10)
    assert not _xy_inside_footprint(chamfered, 60, 10)
