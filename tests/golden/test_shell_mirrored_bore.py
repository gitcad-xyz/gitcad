"""A bore entering from the BOTTOM shells, by conjugation (K4.2).

The erosion in ``_shell_drilled`` is written for coaxial stacks that open
UPWARD. A stack opening downward refused with "the mirrored construction, not
built yet" — while the SAME INTEGERS reflected returned a Body. That asymmetry
was the sharpest single piece of evidence in the 2026-07-28 exact-vs-
approximate audit that these gaps are unwritten code rather than arithmetic:
no number field can explain one direction working and its mirror image not.

The fix needs no new geometry, because **shelling commutes with isometries**:
for any distance-preserving σ, shell(σS, t) = σ shell(S, t), since the offset
is defined by distance alone. So the mirrored case reflects the input through
the base's own mid-z plane, runs the upward construction, and reflects the
answer back. z ↦ (bz0+bz1) − z is exact in ℚ and maps the box to itself.

The one real risk was orientation: a reflection REVERSES it, so a naive
transform would produce an inside-out shell. ``Affine.mirror`` flips face
senses — verified directly (the reflected body's vector-area defect is exactly
(0,0,0)) and pinned below by ``validate``.
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture()
def k():
    return RefKernel()


def _drilled(k, z0, z1, *, cx=10, cy=10, r=3, box=20):
    base = k.box(box, box, box)
    tool = k.transform(k.cylinder(r, z1 - z0), translate=(cx, cy, z0))
    return k.boolean("cut", base, tool)


def test_a_bottom_entering_bore_shells(k):
    out = k.shell(_drilled(k, 0, 10), [], 2)
    assert k.validate(out).ok


def test_the_mirror_pair_agree_exactly(k):
    """The congruence that proves the conjugation, not merely that it runs.

    A reflection is an isometry, so the two shells are congruent and their
    volumes must be EQUAL — not close. Exact arithmetic makes that testable
    as equality rather than as a tolerance.
    """
    top = k.mass_props(k.shell(_drilled(k, 10, 20), [], 2))["volume"]
    bot = k.mass_props(k.shell(_drilled(k, 0, 10), [], 2))["volume"]
    assert top == bot, f"mirror pair disagree: {top} vs {bot}"


@pytest.mark.parametrize("depth", [4, 6, 10, 12])
def test_the_pair_agree_at_several_depths(k, depth):
    """Not a single lucky configuration — the blind floor moves through the
    regimes the upward path distinguishes (floor within t, within 2t, clear)."""
    top = k.shell(_drilled(k, 20 - depth, 20), [], 2)
    bot = k.shell(_drilled(k, 0, depth), [], 2)
    assert k.mass_props(top)["volume"] == k.mass_props(bot)["volume"]
    assert k.validate(top).ok and k.validate(bot).ok


def test_a_through_bore_is_untouched(k):
    """Control: a bore open at BOTH ends is neither case, and must keep
    taking the original path."""
    out = k.shell(_drilled(k, 0, 20), [], 2)
    assert k.validate(out).ok


def test_bores_entering_from_both_ends_still_refuse(k):
    """One reflection cannot fix stacks that disagree, so this stays a
    refusal — but it now says what is actually wrong instead of blaming the
    'mirrored construction', and offers a route."""
    base = k.box(20, 20, 20)
    up = k.boolean("cut", base, k.transform(k.cylinder(3, 10),
                                            translate=(5, 5, 0)))
    both = k.boolean("cut", up, k.transform(k.cylinder(3, 10),
                                            translate=(15, 15, 10)))
    with pytest.raises(KernelError) as exc:
        k.shell(both, [], 2)
    err = exc.value
    assert "BOTH ends" in str(err)
    assert err.predicate == "stacks_open_the_same_way"
    assert err.remedy


def test_the_shell_is_not_inside_out(k):
    """The orientation risk, pinned by a number rather than by a flag: a
    reflected shell that kept its original senses would enclose negative
    volume."""
    out = k.shell(_drilled(k, 0, 10), [], 2)
    vol = k.mass_props(out)["volume"]
    assert vol > 0
    # and it must be LESS than the solid it hollows
    assert vol < k.mass_props(_drilled(k, 0, 10))["volume"]
