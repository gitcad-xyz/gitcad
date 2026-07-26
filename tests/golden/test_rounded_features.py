"""Features on a rounded box (K5.1 trimmed quadrics, the expressible half).

A rounded box is a Minkowski sum, ``core ⊕ ball(r)``, and its flats are
ordinary planes. Both facts buy exact answers where the general K4.2 offset and
K5.2 blend do not exist yet:

  * hollowing it is erosion by a ball, which just takes the ball back off;
  * a hole through it is the pocket construction, whose cap guard is exactly
    the check that the hole has not been swallowed by a rounded edge.

Every case here is checked against an analytic oracle — Steiner's formula for
the rounded box, πr²h for the bores — and then against the topology: every edge
paired, the mesh watertight, and the STEP writer's own closing audit run.
"""

from __future__ import annotations

import math
from collections import defaultdict

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from forgekernel.quadric import Cyl, RoundedBox
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _steiner(a, b, c, r):
    """V = pqs + 2r(pq+qs+sp) + πr²(p+q+s) + (4/3)πr³, with p = a−2r …"""
    p, q, s = a - 2 * r, b - 2 * r, c - 2 * r
    return (p * q * s + 2 * r * (p * q + q * s + s * p)
            + math.pi * r * r * (p + q + s) + 4 * math.pi * r ** 3 / 3)


def _sound(body):
    """Every edge paired, and the mesh watertight. Returns the face count."""
    from forgekernel import body as B
    from forgekernel.stepbody import write_step_body

    assert B.manifold_violations(body) == []
    ec = defaultdict(int)
    for a, b, c in B.tessellate(body, 0.03)["triangles"]:
        for e in ((a, b), (b, c), (c, a)):
            ec[tuple(sorted(e))] += 1
    assert all(n == 2 for n in ec.values()), "the mesh is not watertight"
    write_step_body(body)              # the writer's own closing audit
    return len(body.faces)


# --- hollowing: erosion by a ball --------------------------------------------

ROUNDED_SHELLS = [
    ("cube r3 t1", (20, 20, 20, 3), 1),
    ("cube r3 t3 — the ball is used up", (20, 20, 20, 3), 3),
    ("slab r2 t1", (30, 20, 10, 2), 1),
    ("plate r5 t2", (40, 25, 15, 5), 2),
    ("half-integer radius", (21, 13, 9, 2.5), 1),
]


@pytest.mark.parametrize("label,dims,t", ROUNDED_SHELLS,
                         ids=[r[0] for r in ROUNDED_SHELLS])
def test_hollowing_a_rounded_box_is_exact_by_minkowski_erosion(
        k, label, dims, t) -> None:
    """Eroding a convex Minkowski sum by ball(t) just takes the ball back off:

        (core ⊕ B_r) ⊖ B_t  =  core ⊕ B_{r−t}    for t ≤ r
                            =  core ⊖ B_{t−r}    for t >  r

    Both collapse to overall dimensions (a−2t, b−2t, c−2t) with ball radius
    max(r−t, 0) — the SAME core either way. Nothing is offset numerically,
    which is why this is expressible where the general K4.2 offset is not; past
    t = r the corners simply go sharp.
    """
    a, b, c, r = dims
    out = k.shell(RoundedBox(a, b, c, r), [], t)
    truth = _steiner(a, b, c, r) - _steiner(a - 2 * t, b - 2 * t, c - 2 * t,
                                            max(r - t, 0))
    assert k.mass_props(out)["volume"] == pytest.approx(truth)


def test_a_rounded_shell_pairs_every_edge_and_meshes_watertight(k) -> None:
    from forgekernel import body as B

    out = k.shell(RoundedBox(20, 20, 20, 3), [], 1)
    _sound(out if isinstance(out, B.Body) else B.to_body(out))


def test_a_thickness_that_leaves_no_cavity_refuses(k) -> None:
    with pytest.raises(KernelError, match="no cavity"):
        k.shell(RoundedBox(20, 20, 10, 2), [], 5)


# --- a hole is not a split ----------------------------------------------------

THROUGH = [
    ("circular", lambda k: Cyl(10, 10, 2, -5, 15), math.pi * 4 * 10),
    ("rectangular", lambda k: k.transform(k.box(4, 4, 20),
                                          translate=(8, 8, -5)), 4 * 4 * 10),
]


@pytest.mark.parametrize("label,tool,removed", THROUGH,
                         ids=[t[0] for t in THROUGH])
def test_a_hole_straight_through_a_rounded_box_is_not_a_split(
        k, label, tool, removed) -> None:
    """"Open at both ends" was read as "splits the solid" and refused. That is
    true of a SLOT reaching the boundary; it is not true of a footprint
    strictly inside both flats, which leaves the part every bit as connected as
    a drilled plate. Same faces as a pocket, two mouths and no floor."""
    from forgekernel import body as B

    base = RoundedBox(20, 20, 10, 2)
    before = float(k.mass_props(base)["volume"])
    out = k.boolean("cut", base, tool(k))
    assert before - float(k.mass_props(out)["volume"]) == pytest.approx(removed)
    _sound(B.to_body(out))


def test_a_through_hole_reaching_the_fillet_band_still_refuses(k) -> None:
    """The cap guard is what makes the through case expressible at all: past
    the flat there is a quarter-cylinder in the way, and these are not the
    faces to build."""
    with pytest.raises(KernelError, match="strictly inside"):
        k.boolean("cut", RoundedBox(20, 20, 10, 2), Cyl(10, 1, 2, -5, 15))


def test_an_internal_cavity_is_still_refused(k) -> None:
    """Open at NEITHER end genuinely cannot be one closed boundary — it was the
    other half of the same over-broad refusal, and it stays refused."""
    with pytest.raises(KernelError, match="internal cavity"):
        k.boolean("cut", RoundedBox(20, 20, 10, 2), Cyl(10, 10, 2, 3, 7))


# --- rounding every edge of a drilled plate -----------------------------------

FILLETED_DRILLED = [
    ("a through bore", lambda k: k.boolean(
        "cut", k.box(40, 20, 5),
        k.transform(k.cylinder(4, 5), translate=(20, 10, 0))),
     1, (40, 20, 5), math.pi * 16 * 5),
    ("a blind bore", lambda k: k.boolean(
        "cut", k.box(30, 30, 10),
        k.transform(k.cylinder(3, 6), translate=(15, 15, 4))),
     1, (30, 30, 10), math.pi * 9 * 6),
]


@pytest.mark.parametrize("label,build,r,dims,bore", FILLETED_DRILLED,
                         ids=[f[0] for f in FILLETED_DRILLED])
def test_filleting_a_drilled_plate_keeps_its_bores(k, label, build, r, dims,
                                                   bore) -> None:
    """It used to refuse — "the rounded base cannot be re-drilled" — but the
    rounded base needs no re-drilling: each bore is the pocket construction
    with a circular footprint, and the mouth guard is precisely the check that
    the bore has not been swallowed by a rounded edge."""
    from forgekernel import body as B

    out = k.fillet(build(k), [], r)
    assert k.mass_props(out)["volume"] == pytest.approx(
        _steiner(*dims, r) - bore)
    _sound(B.to_body(out))


def test_filleting_a_counterbore_builds_the_shoulder(k) -> None:
    """Coaxial bores are ONE stepped void, not two independent ones. Cut
    separately, the wider mouth is punched into a cap that already carries the
    narrower one and the shoulder ring where the radius steps is never built —
    so they are grouped and banded exactly as ``from_drilled`` does it.

    Ø4 x 7 deep under a Ø8 x 3 counterbore removes 28π + 48π."""
    from forgekernel import body as B

    cb = k.boolean("cut", k.boolean(
        "cut", k.box(30, 30, 10),
        k.transform(k.cylinder(2, 10), translate=(15, 15, 0))),
        k.transform(k.cylinder(4, 3), translate=(15, 15, 7)))
    out = k.fillet(cb, [], 1)
    assert k.mass_props(out)["volume"] == pytest.approx(
        _steiner(30, 30, 10, 1) - math.pi * (4 * 7 + 16 * 3))
    _sound(B.to_body(out))


def test_a_coaxial_stack_with_a_gap_refuses(k) -> None:
    """Two bores from opposite ends that do not meet are two voids. Banding
    them as one stack would invent a wall through the material between them."""
    d = k.boolean("cut", k.boolean(
        "cut", k.box(30, 30, 20),
        k.transform(k.cylinder(2, 4), translate=(15, 15, 0))),
        k.transform(k.cylinder(2, 4), translate=(15, 15, 16)))
    with pytest.raises(KernelError, match="gap"):
        k.fillet(d, [], 1)
