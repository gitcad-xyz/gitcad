"""Shelling a prism that has been BORED through (K4.2 multi-loop caps).

``shell`` refused every bored prism with "cap boundary is not a single loop".
Two distinct things were hiding behind that message:

1. **T-junctions.** Boundary reconstruction cancels directed edges, which
   assumes the polygons either side of an interior edge name the SAME segment.
   After a boolean they often do not: cutting a 4×4 bore through a 20×20 cap
   leaves one side of the line y=8 as a single edge (0,8)→(20,8) while the
   other side is split at x=8 and x=12 by the hole. Those never cancel, so an
   interior line survived as "boundary" and the loop walk failed. Splitting
   every edge at each vertex lying strictly inside it restores the pairing —
   collinearity and betweenness are exact predicates over ℚ, so no tolerance
   enters (ADR-0019).

2. **A genuine multi-loop cap.** Once the loops reconstruct, a cap with a hole
   is one outer boundary plus one inner one. The offset needs no new
   mathematics: the reconstruction hands back each loop with material on its
   left, so shifting every edge along its LEFT normal erodes the outer
   boundary and DILATES the hole, with no sign analysis.

The refusal was added for a real silent-wrong — chaining one loop and stopping
hollowed a single component and returned 1488 for a pair of 10³ boxes whose
true member-wise shell is 976. That case still refuses; it is two solids, and
their shells do not compose.
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


def _bored(k, *, w=20, d=20, h=10, hw=4, at=(8, 8)):
    """A w×d×h prism with an hw×hw square bore straight through."""
    tool = k.transform(k.box(hw, hw, h * 10), translate=(at[0], at[1], -h * 5))
    return k.boolean("cut", k.box(w, d, h), tool)


def test_a_bored_prism_shells_to_its_closed_form(k):
    """Every number here is derived from the geometry, not read off the code.

    solid   = 20·20·10 − 4·4·10                     = 3840
    cavity  = (outer inset 2 → 16×16) − (hole dilated 2 → 8×8)
            = 256 − 64 = 192, over height 10 − 2·2 = 6   = 1152
    shell   = 3840 − 1152                            = 2688
    """
    out = k.shell(_bored(k), [], 2)
    assert k.mass_props(out)["volume"] == 2688
    assert k.validate(out).ok


def test_two_bores_compose(k):
    """solid 30·20·10 − 2·(4·4·10) = 5680; cavity (26·16 − 2·64)·6 = 1728."""
    box = k.box(30, 20, 10)
    t1 = k.transform(k.box(4, 4, 100), translate=(5, 8, -50))
    t2 = k.transform(k.box(4, 4, 100), translate=(21, 8, -50))
    out = k.shell(k.boolean("cut", k.boolean("cut", box, t1), t2), [], 2)
    assert k.mass_props(out)["volume"] == 5680 - 1728
    assert k.validate(out).ok


def test_the_hole_grows_and_the_rim_shrinks(k):
    """The direction check, as a number. If the hole were ERODED instead of
    dilated the cavity would be 256 − 0 (the 4×4 hole would close at t=2) and
    the shell would read 2304 — a plausible wrong answer, not a crash."""
    out = k.shell(_bored(k), [], 2)
    assert k.mass_props(out)["volume"] != 3840 - 256 * 6
    assert k.mass_props(out)["volume"] == 2688


def test_an_unbored_prism_is_unchanged(k):
    """Control: the single-loop path must not move. 4000 − 16·16·6 = 2464."""
    out = k.shell(k.box(20, 20, 10), [], 2)
    assert k.mass_props(out)["volume"] == 2464


def test_two_separate_solids_still_refuse(k):
    """The silent-wrong this guard was added for: hollowing one component of a
    disconnected cap returned 1488 where the true member-wise shell is 976."""
    pair = k.boolean("union", k.box(10, 10, 10),
                     k.transform(k.box(10, 10, 10), translate=(30, 0, 0)))
    with pytest.raises(KernelError) as exc:
        k.shell(pair, [], 1)
    assert "two solids" in str(exc.value)


def test_a_wall_thinner_than_twice_t_refuses(k):
    """A bore 1 mm from the rim cannot carry a 2 mm wall on both sides: the
    cavity would break into the bore. That must refuse, not return a number
    for a solid that cannot exist."""
    with pytest.raises(KernelError) as exc:
        k.shell(_bored(k, at=(1, 8)), [], 2)
    assert "thinner than 2t" in str(exc.value)


def test_an_off_centre_bore_is_still_exact(k):
    """Nothing here depends on symmetry — the cavity area is the same wherever
    a through bore sits, as long as the walls hold.

    (5,10) not (4,12): at x=4 the dilated hole's edge lands on x=2, exactly
    where the inset outer wall is, leaving zero material between cavity and
    bore. The guard refuses that, correctly — it is the boundary case, not an
    off-centre one.
    """
    out = k.shell(_bored(k, at=(5, 10)), [], 2)
    assert k.mass_props(out)["volume"] == 2688
    assert k.validate(out).ok
