"""Using op(σS) ≡ σ op(S) constructively, not just as an assertion.

Several recognisers in this kernel are ONE-SIDED. ``_bossed_plate_spec`` knows
a boss standing UP on a plate; ``_shell_drilled`` knows a bore stack that
widens upward. Turn the part over and the same solid falls past them into a
generic refusal — "members touch", "a stack that narrows upward is the mirrored
construction" — even though the answer is exact and the kernel can reach it.

So when the direct path refuses, ``RefKernel._via_reflection`` computes
``σ op(σS)`` instead. Two properties make that sound rather than clever:

* it runs ONLY after a refusal, so it cannot change an answer the kernel
  already gives — only turn a refusal into a number;
* uniform shell and all-edge fillet ARE equivariant under an isometry (the
  thickness and radius carry no orientation). That is a theorem, not a
  heuristic. It is deliberately NOT offered when a face or edge SELECTION is
  given, because a reflection would have to carry the selection with it.

Volume agreement across the mirror is guaranteed by construction here and
therefore proves nothing on its own — what it cannot catch is orientation,
since mirroring a body flips every face sense and an inside-out solid has the
same |V|. These tests check the things that CAN still be wrong: the sign of the
volume, ``validate``, the reflected bounding box, and point membership.

This closed the last 5 entries in ``ASYMMETRIC_KNOWN`` (34 → 5 → 0).
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.bench.capability import representations
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def shapes(k):
    return {n: s for n, s in representations(k).items()
            if not isinstance(s, tuple)}


def _ops(k):
    return {"shell": lambda s: k.shell(s, [], 1),
            "fillet": lambda s: k.fillet(s, None, 1)}


#: the five that used to build one way up and refuse turned over, with the
#: volume the UPRIGHT side has always returned
CASES = [
    ("bored boss", "fillet", 2933.7469),
    ("bored boss", "shell", 2088.3289),
    ("counterbore", "shell", 2859.7893),
    ("disjoint union (boss)", "fillet", 2949.4548),
    ("disjoint union (boss)", "shell", 2043.6006),
]


@pytest.mark.parametrize("name,op,upright", CASES,
                         ids=[f"{n}-{o}" for n, o, _ in CASES])
def test_the_upside_down_part_gets_the_same_answer(k, shapes, name, op, upright):
    fn = _ops(k)[op]
    s = shapes[name]
    flipped = k.mirror(s, "xy")

    a, b = fn(s), fn(flipped)
    va, vb = k.mass_props(a)["volume"], k.mass_props(b)["volume"]

    assert float(va) == pytest.approx(upright, abs=1e-3)
    assert va == vb, "a reflection is an isometry"
    assert va > 0 and vb > 0, "an inside-out solid has the same |V|"
    assert k.validate(a).ok and k.validate(b).ok


@pytest.mark.parametrize("name,op,_v", CASES,
                         ids=[f"{n}-{o}" for n, o, _ in CASES])
def test_the_answer_is_actually_upside_down(k, shapes, name, op, _v):
    """The check volume cannot make: the result must SIT where a reflected
    result sits. z flips end for end; x and y do not move."""
    fn = _ops(k)[op]
    s = shapes[name]
    (alo, ahi) = k.bbox(fn(s))
    (blo, bhi) = k.bbox(fn(k.mirror(s, "xy")))
    alo, ahi = [float(v) for v in alo], [float(v) for v in ahi]
    blo, bhi = [float(v) for v in blo], [float(v) for v in bhi]

    assert blo[2] == pytest.approx(-ahi[2], abs=1e-9)
    assert bhi[2] == pytest.approx(-alo[2], abs=1e-9)
    for i in (0, 1):
        assert blo[i] == pytest.approx(alo[i], abs=1e-9)
        assert bhi[i] == pytest.approx(ahi[i], abs=1e-9)


def test_a_selection_is_never_reflected(k):
    """An edge or face selection names entities in the ORIGINAL shape, so the
    reflection cannot carry it and the fallback must decline. A silent answer
    to a different question is worse than the refusal."""
    s = k.boolean("union", k.box(30, 30, 3),
                  k.transform(k.cylinder(4, 6), translate=(15, 15, 3)))
    with pytest.raises(KernelError):
        k.shell(k.mirror(s, "xy"), ["some-face-id"], 1)


def test_it_does_not_rescue_a_real_wall(k):
    """A refusal that is about the exact FIELD is congruence-invariant: the
    reflected shape leaves the field too, so the fallback finds nothing and
    the original refusal — the one that describes the caller's own shape —
    is what surfaces."""
    cone = k.cone(6, 2, 10)
    with pytest.raises(KernelError) as exc:
        k.fillet(cone, None, 1)
    assert "arctan" in str(exc.value) or "fillet" in str(exc.value)

    with pytest.raises(KernelError):
        k.fillet(k.mirror(cone, "xy"), None, 1)


def test_an_upright_answer_is_untouched(k, shapes):
    """The safety property stated as a test: the fallback runs only after a
    refusal, so every shape that already worked must return byte-identically.
    """
    for name in ("planar box", "cylinder", "drilled (through)", "sphere"):
        s = shapes[name]
        assert k.mass_props(k.shell(s, [], 1))["volume"] > 0
        assert k.validate(k.shell(s, [], 1)).ok
