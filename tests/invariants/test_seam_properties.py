"""Properties every op must satisfy, over randomised shapes.

The ~1080 unit tests found NONE of the ~40 silent wrong numbers this kernel has
had. They could not: a unit test asserts the number the implementation produced,
so it re-states the bug. These assert only things that must hold whatever the
answer is —

    cut never adds material          union never removes it
    cut and intersect partition      a rigid motion preserves volume EXACTLY
    a returned solid is a solid      an op is deterministic

— which is a much weaker claim per test and a far stronger one in aggregate,
because it holds over inputs nobody wrote down.

Randomised, not exhaustive, and SEEDED: a property test that cannot be
reproduced is a rumour. The seed is in the id of every generated case.
"""

from __future__ import annotations

import random

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from forgekernel import body as B
from forgekernel.brep import Solid
from forgekernel.quadric import Cone, Cyl, DrilledSolid, RoundedBox, Sphere
from gitcad.errors import GitcadError
from gitcad.kernel.ref import RefKernel

SEED = 20260726
CASES = 60


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _shapes(rng):
    """One random shape from each family the seam supports."""
    q = lambda lo, hi: rng.randrange(lo * 2, hi * 2) / 2      # halves stay exact
    return [
        Solid.box(q(4, 20), q(4, 20), q(4, 20)),
        Cyl(q(0, 6), q(0, 6), q(2, 8), 0, q(4, 16)),
        Sphere(q(0, 6), q(0, 6), q(0, 6), q(2, 9)),
        Cone(q(0, 4), q(0, 4), q(1, 4), q(5, 9), 0, q(4, 14)),
        RoundedBox(q(10, 24), q(10, 24), q(8, 20), q(1, 3)),
        DrilledSolid(Solid.box(q(20, 40), q(20, 40), q(4, 10)), []),
    ]


def _vol(k, s) -> float:
    return float(k.mass_props(s)["volume"])


def _cases():
    rng = random.Random(SEED)
    out = []
    for i in range(CASES):
        r = random.Random(rng.random())
        out.append(pytest.param(r, id=f"seed{SEED}-{i}"))
    return out


@pytest.mark.parametrize("rng", _cases())
def test_cut_never_adds_material_and_union_never_removes_it(k, rng) -> None:
    """The single cheapest invariant, and it would have caught the wedge tool
    that removed 64 mm3 where 48 exists — that cut REPORTED less volume than
    the truth, but the direction check alone catches the whole family of
    over-removal only when the tool is bigger than the solid. Both directions
    are asserted because a boolean that silently no-ops is equally wrong."""
    shapes = _shapes(rng)
    a, b = rng.choice(shapes), rng.choice(shapes)
    try:
        va = _vol(k, a)
    except GitcadError:
        return
    for op, cmp_ in (("cut", "le"), ("union", "ge")):
        try:
            out = k.boolean(op, a, b)
            # measuring can refuse on its own terms — `cut(a, a)` annihilates
            # its operand and the centroid of nothing is genuinely undefined
            vo = _vol(k, out)
        except GitcadError:
            continue                       # an honest refusal proves nothing
        if cmp_ == "le":
            assert vo <= va + 1e-9, f"cut ADDED material: {vo} > {va}"
        else:
            assert vo >= va - 1e-9, f"union REMOVED material: {vo} < {va}"
        assert vo >= -1e-9, "no op may produce negative volume"


@pytest.mark.parametrize("rng", _cases())
def test_a_rigid_motion_preserves_volume_exactly(k, rng) -> None:
    """Not approximately — EXACTLY. A translation is rational and an exact
    rotation is in Q[sqrt d], so any drift here is the arithmetic leaking, not
    a tolerance. The rotated-rounded-box mesh bug lived next door to this."""
    s = rng.choice(_shapes(rng))
    try:
        v0 = k.mass_props(s)["volume"]
    except GitcadError:
        return
    moved = k.transform(s, translate=(rng.randrange(-30, 30),
                                      rng.randrange(-30, 30),
                                      rng.randrange(-30, 30)))
    assert k.mass_props(moved)["volume"] == v0, "translation drifted"
    for deg in (30, 45, 90, 180):
        try:
            turned = k.transform(s, rotate_axis=(0, 0, 1), rotate_deg=deg)
            vt = k.mass_props(turned)["volume"]
        except GitcadError:
            continue
        assert vt == v0, f"rotation {deg} drifted"


@pytest.mark.parametrize("rng", _cases())
def test_everything_the_seam_returns_is_a_solid(k, rng) -> None:
    """validate() must agree that what an op handed back is a closed solid with
    positive volume. Two ops used to return bodies that no metric could even
    read, and one returned an OPEN shell that meshed watertight."""
    shapes = _shapes(rng)
    a, b = rng.choice(shapes), rng.choice(shapes)
    for make in (lambda: k.boolean("cut", a, b),
                 lambda: k.boolean("union", a, b),
                 lambda: k.shell(a, [], 1),
                 lambda: k.fillet(a, [], 1),
                 lambda: k.chamfer(a, [], 1)):
        try:
            out = make()
            # measuring may refuse on its own terms (a torus term that leaves
            # ℚ[π], say). That is a gap, not a broken answer.
            v = _vol(k, out)
            rep = k.validate(out)
        except GitcadError:
            continue
        # a cut CAN legitimately annihilate its operand; what it must not do is
        # return something that is neither empty nor a solid
        if v == 0:
            continue
        assert v > 0, "an op returned negative volume"
        assert rep.ok, f"{type(out).__name__}: {rep.violations}"


@pytest.mark.parametrize("rng", _cases())
def test_an_op_gives_the_same_answer_twice(k, rng) -> None:
    """Determinism is not free: dict ordering, set iteration and float
    accumulation all leak it, and a kernel that answers differently on a
    re-run cannot be diffed in git — which is the whole product."""
    shapes = _shapes(rng)
    a, b = rng.choice(shapes), rng.choice(shapes)
    try:
        first = k.mass_props(k.boolean("cut", a, b))["volume"]
        second = k.mass_props(k.boolean("cut", a, b))["volume"]
    except GitcadError:
        return
    assert first == second


@pytest.mark.parametrize("rng", _cases())
def test_a_cut_and_an_intersect_partition_the_original(k, rng) -> None:
    """vol(a - b) + vol(a & b) == vol(a). The strongest of the five: it pins
    the ACTUAL NUMBER without anyone writing it down, so an op that is
    self-consistently wrong still fails."""
    shapes = _shapes(rng)
    a, b = rng.choice(shapes), rng.choice(shapes)
    try:
        cut = _vol(k, k.boolean("cut", a, b))
        both = _vol(k, k.boolean("intersect", a, b))
    except GitcadError:
        return
    assert cut + both == pytest.approx(_vol(k, a), rel=1e-9), (
        f"cut {cut} + intersect {both} != {_vol(k, a)}")


def test_the_generator_actually_exercises_the_ops(k) -> None:
    """A property suite where every case refuses proves nothing, so pin how
    much real work the sweep does — as a RATCHET, at the measured number.

    That number is currently 6 of 40, and it is worth stating plainly: over
    ARBITRARY pairs of shapes the kernel refuses roughly 85% of cuts. The
    curated capability matrix reads 327/345 because it pairs each shape with a
    tool chosen to suit it; this is the same kernel measured without that help,
    and the two numbers answer different questions. Raise the floor when
    coverage genuinely improves — never lower it to make a red suite green.
    """
    rng = random.Random(SEED)
    built = 0
    for _ in range(40):
        shapes = _shapes(rng)
        a, b = rng.choice(shapes), rng.choice(shapes)
        try:
            k.boolean("cut", a, b)
            built += 1
        except GitcadError:
            pass
    assert built >= 6, f"only {built}/40 cuts succeeded — coverage regressed"
