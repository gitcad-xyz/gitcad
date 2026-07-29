"""Issue #8 — rotate must not be a one-way door where symmetry says it isn't.

``move(rotate_deg=...)`` used to convert EVERY rotated curved solid to the
canonical B-rep (``Body``), which no boolean and no STEP export accepts —
and for the axisymmetric family it was worse than lossy: a z-rotation of an
off-axis cylinder was silently DROPPED (the shape came back with its centre
unmoved — wrong geometry, not a refusal).

The symmetry facts these tests pin:

  * any rotation about a solid of revolution's OWN axis is the identity;
  * a quarter-turn about z maps every z-axisymmetric representation to
    itself with the centre rotated exactly (a z-rotated Cyl IS a Cyl);
  * a sphere is a sphere about any centre, so principal quarter-turns
    rotate its centre and keep the representation;
  * everything else (a tilted lathe, a tilted cylinder) genuinely leaves
    the representation, still converts to the canonical B-rep, and the
    DOWNSTREAM refusal names that boundary rather than blaming a quadric.
"""

from __future__ import annotations

import math

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from forgekernel.quadric import (AxisStack, Cyl, DisjointUnion, DrilledSolid,
                                 RevolveSolid, Sphere)
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel

STEPPED = [(0, 0), (4, 0), (4, 5), (7, 5), (7, 9), (0, 9)]


@pytest.fixture()
def k():
    return RefKernel()


# -- the silent drop: z-rotation of an off-axis quadric ------------------------

@pytest.mark.parametrize("deg,want", [
    (90, (0.0, 10.0)), (180, (-10.0, 0.0)), (270, (0.0, -10.0)),
    (-90, (0.0, -10.0)), (360, (10.0, 0.0)),
], ids=["90", "180", "270", "-90", "360"])
def test_a_quarter_turned_cylinder_is_a_cylinder_with_its_centre_moved(
        k, deg, want) -> None:
    """The 0.9.9 wheels returned the cylinder UNROTATED — centroid still at
    (10, 0) after a 90-degree turn about z. Wrong geometry, silently."""
    c = k.transform(k.cylinder(2, 5), translate=(10, 0, 0))
    out = k.transform(c, rotate_axis=(0, 0, 1), rotate_deg=deg)
    assert isinstance(out, Cyl)
    mp = k.mass_props(out)
    assert (mp["cx"], mp["cy"]) == pytest.approx(want)
    assert mp["volume"] == pytest.approx(math.pi * 4 * 5)


def test_a_non_quarter_z_rotation_of_an_off_axis_cylinder_is_not_dropped(
        k) -> None:
    """45 degrees about z moves the centre to (10/sqrt2, 10/sqrt2). Whether
    the kernel answers natively or through the canonical form, the one
    thing it must never do is hand back the unrotated solid."""
    c = k.transform(k.cylinder(2, 5), translate=(10, 0, 0))
    try:
        out = k.transform(c, rotate_axis=(0, 0, 1), rotate_deg=45)
    except KernelError:
        return                               # an honest refusal is also fine
    mp = k.mass_props(out)
    d = 10 / math.sqrt(2)
    assert (mp["cx"], mp["cy"]) == pytest.approx((d, d))


# -- a lathe about its own axis is unchanged -----------------------------------

@pytest.mark.parametrize("deg", [90, 45, 37.5, 180],
                         ids=["90", "45", "37.5", "180"])
def test_rotating_a_lathe_about_its_own_axis_changes_nothing(k, deg) -> None:
    s = RevolveSolid(STEPPED, 0, 0)
    out = k.transform(s, rotate_axis=(0, 0, 1), rotate_deg=deg)
    assert isinstance(out, RevolveSolid)
    assert out.loop == s.loop and (out.cx, out.cy) == (s.cx, s.cy)
    # ...and it is still a boolean operand afterwards (the one-way door)
    bored = k.boolean("cut", out, k.transform(k.cylinder(1, 100),
                                              translate=(0, 0, -50)))
    assert isinstance(bored, RevolveSolid)


def test_a_quarter_turned_off_axis_lathe_keeps_its_representation(k) -> None:
    s = RevolveSolid(STEPPED, 3, 0)
    out = k.transform(s, rotate_axis=(0, 0, 1), rotate_deg=90)
    assert isinstance(out, RevolveSolid)
    assert (out.cx, out.cy) == (0, 3)
    bored = k.boolean("cut", out, k.transform(k.cylinder(1, 100),
                                              translate=(0, 3, -50)))
    assert isinstance(bored, RevolveSolid)


def test_a_quarter_turned_lathe_still_exports_step(k, tmp_path) -> None:
    """The issue's table row: revolve -> rotate 90 -> export_step refused.
    About its own axis nothing changed, so the export must run."""
    s = RevolveSolid(STEPPED, 0, 0)
    out = k.transform(s, rotate_axis=(0, 0, 1), rotate_deg=90)
    path = tmp_path / "lathe.step"
    k.export_step(out, str(path))
    assert path.stat().st_size > 0


# -- other z-axisymmetric representations follow the same rule -----------------

def test_a_quarter_turned_drilled_plate_keeps_its_bores(k) -> None:
    plate = k.boolean("cut", k.box(20, 20, 5), k.transform(
        k.cylinder(2, 5), translate=(10, 10, 0)))
    assert isinstance(plate, DrilledSolid)
    out = k.transform(plate, rotate_axis=(0, 0, 1), rotate_deg=90)
    assert isinstance(out, DrilledSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(
        20 * 20 * 5 - math.pi * 4 * 5)
    (bore,) = out.bores
    assert (float(bore.cx), float(bore.cy)) == pytest.approx((-10.0, 10.0))


def test_a_quarter_turned_disjoint_union_rotates_member_wise(k) -> None:
    boss = k.boolean("union", k.box(30, 30, 3), k.transform(
        k.cylinder(4, 6), translate=(15, 15, 3)))
    assert isinstance(boss, DisjointUnion)
    out = k.transform(boss, rotate_axis=(0, 0, 1), rotate_deg=90)
    assert isinstance(out, DisjointUnion)
    assert k.mass_props(out)["volume"] == pytest.approx(
        30 * 30 * 3 + math.pi * 16 * 6)
    assert k.mass_props(out)["centroid"][0] == pytest.approx(
        -k.mass_props(boss)["centroid"][1])


def test_a_quarter_turned_sphere_moves_its_centre_exactly(k) -> None:
    s = k.transform(k.sphere(3), translate=(5, 0, 0))
    out = k.transform(s, rotate_axis=(0, 1, 0), rotate_deg=90)
    assert isinstance(out, Sphere)
    assert (float(out.cx), float(out.cy), float(out.cz)) == \
        pytest.approx((0.0, 0.0, -5.0))


def test_a_translated_axis_stack_stays_an_axis_stack(k) -> None:
    """Translation is rigid and every member carries its own centre — the
    stack must not fall through the canonical form for a move."""
    stack = k.boolean("union", k.cylinder(5, 4), k.transform(
        k.cylinder(3, 6), translate=(0, 0, 4)))
    assert isinstance(stack, AxisStack)
    out = k.transform(stack, translate=(2, 3, 1))
    assert isinstance(out, AxisStack)
    assert k.mass_props(out)["volume"] == pytest.approx(
        math.pi * (25 * 4 + 9 * 6))
    assert k.mass_props(out)["centroid"][0] == pytest.approx(2.0)


# -- the genuine boundary stays, and names itself ------------------------------

def test_a_tilted_lathe_still_refuses_downstream_naming_the_canonical_form(
        k) -> None:
    """Rotation about x genuinely leaves the axisymmetric family, so the
    conversion to the canonical B-rep stays — and the refusal must name what
    would actually fix it.

    That wording moved on 2026-07-28. It used to stop at "canonical B-rep",
    which is true but reads as a plumbing gap and invites a Body→Solid
    converter; measuring all 25 such refusals found zero all-planar Body
    operands, so no converter can exist without faceting. The refusal now
    names the CURVED SURFACES it found and points at K2.x, the quadric
    boolean. The original intent is unchanged and still asserted: it must
    describe the canonical body, not blame whichever quadric shares the call.
    """
    s = RevolveSolid(STEPPED, 0, 0)
    out = k.transform(s, rotate_axis=(1, 0, 0), rotate_deg=90)
    assert isinstance(out, RevolveSolid) is False
    with pytest.raises(KernelError) as exc:
        k.boolean("cut", out, Cyl(0, 0, 1, -50, 100))
    msg = str(exc.value)
    assert "canonical body" in msg, msg          # still names the container
    assert "Cylinder" in msg, msg                # and now the surface too
    assert exc.value.stage.startswith("K2"), exc.value.stage
