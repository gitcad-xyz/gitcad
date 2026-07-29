"""A refusal must name the thing that would actually fix it.

ADR-0019 makes refusing the preferred failure and #114 makes a refusal DATA —
stage, predicate, measured values, remedy — because an agent that hits one has
to decide what to do next. That only works if the stage named is the stage that
would deliver it.

This one was not. ``boolean.cut`` on a transformed quadric said "a transformed
solid landed in the canonical B-rep (Body)" and pointed at K3.7, which reads as
a plumbing gap: convert the Body back to a Solid and use the exact planar
boolean that already exists. That is a plan, it is obvious, and it is dead —
instrumenting all 25 such refusals across the composed grid found **zero**
all-planar Body operands. Every one carries Cylinder, Cone or SphereS faces
(177 planes, 110 cylinders, 56 sphere zones, 1 cone; 16 with holed faces), so
what is missing is the INTERSECTION of those surfaces with the tool's. No
re-plumbing produces it, and faceting them is what ADR-0019 forbids.

A refusal that sends a reader after a fix that cannot exist costs more than a
blunt one. So it now names the curved surfaces actually present, and says the
blocker is the general curved-surface boolean (K2.x).
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _tilted_cylinder(k):
    """A cylinder laid onto the x axis. `Cyl` is +z by construction, so this
    genuinely cannot stay in the family and lands in the canonical form —
    unlike a z-rotation or a uniform scale, which now both preserve it."""
    return k.transform(k.cylinder(5, 12), rotate_axis=(1, 0, 0),
                       rotate_deg=90)


def test_it_names_the_curved_surfaces_not_the_container(k):
    with pytest.raises(KernelError) as exc:
        k.boolean("cut", _tilted_cylinder(k), k.box(2, 2, 100))
    err = exc.value
    assert "Cylinder" in str(err), str(err)
    assert err.measured["curved_surfaces"] == ["Cylinder"]


def test_it_names_the_stage_that_would_deliver_it(k):
    """K2.x is the general quadric boolean. K3.7 was the canonical-B-rep
    stage, and pointing there implied a converter would fix this."""
    with pytest.raises(KernelError) as exc:
        k.boolean("cut", _tilted_cylinder(k), k.box(2, 2, 100))
    assert exc.value.stage.startswith("K2")
    assert exc.value.predicate == "curved_surface_intersection_unbuilt"


def test_the_remedy_says_what_still_works(k):
    """A remedy has to be actionable. The three transforms that preserve the
    representation are the actionable part, and they are all true as of the
    mirror/rotation/scale work — so the message names them."""
    with pytest.raises(KernelError) as exc:
        k.boolean("cut", _tilted_cylinder(k), k.box(2, 2, 100))
    r = exc.value.remedy
    assert r and "NATIVE" in r
    for word in ("mirror", "rotation", "scale"):
        assert word in r, f"remedy should name {word}: {r}"


def test_the_remedy_is_true_mirror_rotation_and_scale_do_preserve_it(k):
    """The remedy makes a factual claim about the kernel. Check it, or the
    refusal is giving advice that does not work."""
    cyl = k.cylinder(5, 12)
    assert type(k.mirror(cyl, "xy")) is type(cyl)
    assert type(k.transform(cyl, rotate_axis=(0, 0, 1),
                            rotate_deg=45)) is type(cyl)
    assert type(k.scale(cyl, 2)) is type(cyl)
    # and each keeps the shape usable as a boolean operand
    for made in (k.mirror(cyl, "xy"),
                 k.transform(cyl, rotate_axis=(0, 0, 1), rotate_deg=45),
                 k.scale(cyl, 2)):
        out = k.boolean("cut", made, k.transform(
            k.box(2, 2, 500), translate=(0, 0, -250)))
        assert k.mass_props(out)["volume"] > 0


def test_the_other_route_in_the_remedy_also_works(k):
    """'apply the transform to the boolean's RESULT instead of its operand' —
    check that, too."""
    cyl = k.cylinder(5, 12)
    cut = k.boolean("cut", cyl, k.transform(k.box(2, 2, 500),
                                            translate=(0, 0, -250)))
    out = k.transform(cut, rotate_axis=(1, 0, 0), rotate_deg=90)
    assert k.mass_props(out)["volume"] == k.mass_props(cut)["volume"]
