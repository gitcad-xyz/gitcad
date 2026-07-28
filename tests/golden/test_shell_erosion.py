"""#120: shell of a drilled solid whose bore does not go straight through.

Eroding around a blind bore's floor rim (or a counterbore's shoulder rim)
sweeps a quarter TORUS: the void's fillet is the set of points within t of
the reentrant rim circle. The volume therefore carries a pi^2 term — the
result is PiPoly degree 2, not PiVal.

THE TRAP, verified by construction before this landed: the void's floor disk
has radius r, NOT r+t — the naive body (floor at z_f-t with radius r+t, no
torus) PASSES all four answer-audit checks while being 3.744 mm^3 heavy on
the banked oracle. Closed-form comparison is therefore MANDATORY here; the
audit cannot catch a well-formed wrong solid.

Every expected volume below was derived by hand from the erosion geometry
and verified against an independent Monte-Carlo membership test
(dist(p, complement) >= t, 16M samples, seed 987654321):

  blind probe   2728 + (107/3)pi + (3/2)pi^2 = 2854.8545   (mc z = -0.19)
  banked oracle 2728 + (92/3)pi  +      pi^2 = 2834.2118   (mc z = +0.09)
  counterbore   2728 + (107/3)pi +    2 pi^2 = 2859.7893   (mc z = -0.61)
"""
from __future__ import annotations

from fractions import Fraction as F

import pytest

pytest.importorskip("forgekernel")

from forgekernel import body as B
from forgekernel.brep import Solid
from forgekernel.polypi import PiPoly
from forgekernel.quadric import Cyl, DrilledSolid
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _plate(bores):
    out = DrilledSolid(Solid.box(30, 30, 10), [])
    for b in bores:
        out = out.cut(b)
    return out


def _exact_volume(body):
    v = B.volume(body)
    return v if isinstance(v, PiPoly) else PiPoly.from_pival(v)


def test_blind_bore_shell_matches_the_closed_form(k) -> None:
    """Bench probe: 30x30x10 plate, blind r=3 bore with floor at z=4, t=1."""
    shape = _plate([Cyl(15, 15, 3, 4, 10)])
    shell = k.shell(shape, [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    assert _exact_volume(body) == PiPoly([F(2728), F(107, 3), F(3, 2)])
    assert float(B.volume(body)) == pytest.approx(2854.854545, abs=1e-5)
    assert B.manifold_violations(body) == []
    assert any(isinstance(f.surface, B.Torus) for f in body.faces)


def test_the_banked_worked_oracle(k) -> None:
    """30x30x10 plate, blind r=2 floor z=3, t=1 -> 2728 + (92/3)pi + pi^2 =
    2834.211779111. The naive floor-disk-at-r+t body reports 2837.956 and
    passes the audit — only this comparison stands between it and a caller."""
    shape = _plate([Cyl(15, 15, 2, 3, 10)])
    shell = k.shell(shape, [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    assert _exact_volume(body) == PiPoly([F(2728), F(92, 3), F(1)])
    assert float(B.volume(body)) == pytest.approx(2834.211779111, abs=1e-6)


def test_counterbore_shell_matches_the_closed_form(k) -> None:
    """Bench probe: through r=2 plus counterbore r=4 over z 7..10, t=1. The
    shoulder's outer rim erodes to the same k0=3 span=1 quarter torus as a
    blind floor — centred on the rim (R, Z), not on the bore axis wall."""
    shape = _plate([Cyl(15, 15, 2, 0, 10), Cyl(15, 15, 4, 7, 10)])
    shell = k.shell(shape, [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    assert _exact_volume(body) == PiPoly([F(2728), F(107, 3), F(2)])
    assert float(B.volume(body)) == pytest.approx(2859.789347, abs=1e-5)
    assert B.manifold_violations(body) == []


def test_a_shallow_floor_needs_no_torus_at_all(k) -> None:
    """z_f - bz0 <= t: the void sits entirely ABOVE the floor, so the
    through-bore collar formula is exact and refusing it was simply wrong.
    Floor at z=1/2, t=1: shell = 2728 + 34 pi. (This regime is not in the
    bench matrix — the fix moves correctness, not the cell count.)"""
    shape = _plate([Cyl(15, 15, 2, F(1, 2), 10)])
    shell = k.shell(shape, [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    v = B.volume(body)
    assert float(v) == pytest.approx(2728 + 34 * 3.141592653589793, abs=1e-9)
    assert B.manifold_violations(body) == []


def test_the_clipped_floor_regime_refuses_by_name(k) -> None:
    """t < z_f - bz0 < 2t: the quarter torus is clipped by the void's floor
    plane and the volume picks up an arcsin — transcendental (Niven/
    Lindemann), outside every exact field. The refusal is the answer."""
    shape = _plate([Cyl(15, 15, 2, F(3, 2), 10)])
    with pytest.raises(KernelError, match="clip"):
        k.shell(shape, [], 1)


def test_a_narrow_shoulder_refuses_by_name(k) -> None:
    """A counterbore step of r_hi - r_lo <= t clips the shoulder torus
    against the inner collar — same transcendental wall."""
    shape = _plate([Cyl(15, 15, 2, 0, 10), Cyl(15, 15, F(5, 2), 7, 10)])
    with pytest.raises(KernelError, match="clip"):
        k.shell(shape, [], 1)


def test_a_bottom_entry_blind_bore_is_the_mirror_not_a_top_entry_answer(k):
    """Entering from below is the same mathematics mirrored — and now it is
    BUILT, by conjugating the upward construction with a reflection through
    the plate's own mid-z plane (shelling commutes with isometries).

    This asserted a refusal, whose stated worry was that the bottom case must
    "not become a wrong top-entry answer". That worry is kept, and sharpened
    into the check that would actually catch it: the bore here is 6 deep in a
    10 plate, so it is NOT symmetric in z, and a bottom-entry answer that
    quietly reused the top-entry construction would differ. The two must be
    EQUAL — because they are congruent — and exact arithmetic lets that be
    tested as equality rather than as a tolerance.
    """
    bottom = k.shell(_plate([Cyl(15, 15, 3, 0, 6)]), [], 1)
    top = k.shell(_plate([Cyl(15, 15, 3, 4, 10)]), [], 1)

    vb = k.mass_props(bottom)["volume"]
    vt = k.mass_props(top)["volume"]
    assert vb == vt, f"mirror pair disagree: {vb} vs {vt}"
    assert k.validate(bottom).ok and k.validate(top).ok

    # and it is a real hollowing, not a pass-through of the solid
    assert vb < k.mass_props(_plate([Cyl(15, 15, 3, 0, 6)]))["volume"]
