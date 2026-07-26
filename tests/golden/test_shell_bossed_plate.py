"""#120: shell of a plate with a boss standing on it (bored or not).

A DisjointUnion whose members TOUCH is one connected solid, and shelling the
members separately is not the shell of the composite: the void must connect
through the plate under the boss, and the exposed plate-top rim around the
boss base erodes to a quarter torus INSIDE the plate. Before this landed the
un-bored boss cell returned exactly that pile answer — 1916 + 60 pi
(2104.4956), a silent 60.9 mm^3 overweight against the true composite shell.

Closed forms derived by hand from the erosion geometry (comp = exposed
boundary pieces + bore) and verified against an independent Monte-Carlo
membership test before construction (16M samples each):

  boss, no bore: 1916 + (103/3)pi + 2 pi^2  = 2043.6006   (z = -0.09)
  bored boss:    1916 + 47 pi + (5/2) pi^2  = 2088.3289   (z = +0.69)

The pi^2 terms are BOTH tori: the boss-base rim arc (k0=2 span=1, swept
inside the plate) and — bored — the bore-floor arc (k0=3 span=1).
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


def _boss(k, bored: bool):
    shape = k.boolean("union", k.box(30, 30, 3),
                      k.transform(k.cylinder(4, 6), translate=(15, 15, 3)))
    if bored:
        shape = k.boolean("cut", shape,
                          k.transform(k.cylinder(1, 5), translate=(15, 15, 4)))
    return shape


def test_the_unbored_boss_shell_is_the_composite_not_the_pile(k) -> None:
    shell = k.shell(_boss(k, False), [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    assert _exact_volume(body) == PiPoly([F(1916), F(103, 3), F(2)])
    assert float(B.volume(body)) == pytest.approx(2043.600558, abs=1e-5)
    assert B.manifold_violations(body) == []
    assert _unpaired(B.tessellate(body, 0.1)) == 0


def test_the_bored_boss_shell_matches_the_closed_form(k) -> None:
    shell = k.shell(_boss(k, True), [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    assert _exact_volume(body) == PiPoly([F(1916), F(47), F(5, 2)])
    assert float(B.volume(body)) == pytest.approx(2088.328866, abs=1e-5)
    assert B.manifold_violations(body) == []
    assert _unpaired(B.tessellate(body, 0.1)) == 0
    assert sum(1 for f in body.faces
               if isinstance(f.surface, B.Torus)) == 2


def test_touching_members_outside_the_pattern_refuse(k) -> None:
    """Two bosses on one plate touch it without being the one-boss pattern:
    the pile answer would be wrong, so it must refuse rather than return."""
    shape = k.boolean("union", k.boolean(
        "union", k.box(30, 30, 3),
        k.transform(k.cylinder(3, 6), translate=(8, 8, 3))),
        k.transform(k.cylinder(3, 6), translate=(22, 22, 3)))
    with pytest.raises(KernelError, match="touch"):
        k.shell(shape, [], 1)


def test_strictly_disjoint_members_still_shell_memberwise(k) -> None:
    """Erosion distributes over strictly separated components — the
    member-wise answer is exact there and must keep working."""
    shape = k.boolean("union", k.box(10, 10, 10),
                      k.transform(k.cylinder(3, 10), translate=(20, 5, 0)))
    shell = k.shell(shape, [], 1)
    body = B.to_body(shell)
    # hollow box 1000 - 8^3 = 488, plus a capped tube pi(9*10 - 4*8) = 58 pi
    import math
    assert float(B.volume(body)) == pytest.approx(488 + 58 * math.pi, abs=1e-9)


def test_a_disconnected_solid_refuses_rather_than_hollowing_one_part(k):
    """Pre-existing guard hole found while pinning the member-wise contract:
    two separated boxes union into ONE two-component Solid, and
    _prism_shell's cap walk closed the first boundary loop without noticing
    the second — hollowing one component and returning 1488 where the true
    member-wise shell is 976. The walk must check it CONSUMED every boundary
    edge, not merely that it closed."""
    from forgekernel import csg
    from forgekernel.brep import Solid
    from forgekernel.kernel import translate as fk_translate

    u = csg.union(Solid.box(10, 10, 10),
                  fk_translate(Solid.box(10, 10, 10), 15, 0, 0))
    with pytest.raises(KernelError, match="single loop"):
        k.shell(u, [], 1)
