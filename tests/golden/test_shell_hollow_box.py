"""#120: shell of a hollow box (what shell(box) builds) — no torus at all.

Erosion of the wall by t: the complement is (outside the outer box) UNION
(the cavity), so the void is the inset outer box MINUS the cavity dilated by
a ball of t — and a box dilated by a ball is exactly a ROUNDED BOX (Minkowski
sum). Two exact regimes:

  * wall > 2t everywhere: the rounded box sits strictly inside the inset box
    — the void is a hollow block with a rounded cavity.
  * wall == 2t everywhere (the bench probe): the flat regions vanish and the
    void degenerates to the corner-and-edge LATTICE; the void's outer faces
    are square FRAMES whose inner rings are the rounded box's tangency lines.

Wall < 2t clips the rounded box's flats and quarter cylinders against the
inset planes — circular-segment cross-sections carry an arcsin, outside every
exact field, so that refusal is a finished answer.

Expected volumes derived by hand and verified against an independent
Monte-Carlo membership test (dist(p, complement) >= t):

  20^3 wall 2, t=1: 3704 + (148/3)pi = 3858.9852   (16M samples, z = +0.58)
  20^3 wall 3, t=1: 3344 + (130/3)pi = 3480.1357   (16M samples, z = -0.98)
"""
from __future__ import annotations

from fractions import Fraction as F

import pytest

pytest.importorskip("forgekernel")

from forgekernel import body as B
from forgekernel.polypi import PiPoly
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _exact_volume(body):
    v = B.volume(body)
    return v if isinstance(v, PiPoly) else PiPoly.from_pival(v)


def _unpaired(mesh):
    seen: dict = {}
    for t in mesh["triangles"]:
        for i in range(3):
            a, b = t[i], t[(i + 1) % 3]
            seen[(a, b)] = seen.get((a, b), 0) + 1
    return sum(1 for (a, b), n in seen.items() if seen.get((b, a), 0) != n)


def test_the_degenerate_lattice_case_matches_the_closed_form(k) -> None:
    """The bench probe: 20^3 shelled at 2, shelled again at 1. Wall == 2t,
    so the void is the lattice and every void face is a frame or a tangent
    quarter-cylinder/octant."""
    hollow = k.shell(k.box(20, 20, 20), [], 2)
    shell = k.shell(hollow, [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    assert _exact_volume(body) == PiPoly([F(3704), F(148, 3)])
    assert float(B.volume(body)) == pytest.approx(3858.985238, abs=1e-5)
    assert B.manifold_violations(body) == []
    assert _unpaired(B.tessellate(body, 0.1)) == 0


def test_the_thick_wall_case_matches_the_closed_form(k) -> None:
    """20^3 shelled at 3, shelled again at 1: wall 3 > 2t, the rounded box
    sits strictly inside and the void keeps its six full flats."""
    hollow = k.shell(k.box(20, 20, 20), [], 3)
    shell = k.shell(hollow, [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    assert _exact_volume(body) == PiPoly([F(3344), F(130, 3)])
    assert float(B.volume(body)) == pytest.approx(3480.135682, abs=1e-5)
    assert B.manifold_violations(body) == []
    assert _unpaired(B.tessellate(body, 0.1)) == 0


def test_a_wall_thinner_than_two_t_refuses_by_name(k) -> None:
    hollow = k.shell(k.box(20, 20, 20), [], 1)
    with pytest.raises(KernelError, match="clip|arcsin"):
        k.shell(hollow, [], 1)
