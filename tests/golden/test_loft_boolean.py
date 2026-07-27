"""K7 flagship through the seam: LoftSolid × LoftSolid → certified shell.

Two smooth lofts convert to their EXACT patch skins at the boolean
dispatch (``LoftSolid.to_patches`` — walls degree (1,3) from the
natural-spline coefficients, caps planar, seam topology proven by
control-point equality) and run forge's open-branch boolean assembly:
per face-pair SSI, canonicalized seam crossings, chains glued across
the other operand's seams, full border loops, the three-oracle audit.
The result crosses the seam as a ``TrimmedShell`` whose volume is
midpoint + ``volume_halfwidth`` with provenance ``"certified"``
("certified ± e", ADR-0019) — never a bare float.

The acceptance geometry is hand-derivable: the barrel (square sections
3/2, 5/2, 3/2 at z = 0, 2, 4; volume 2582/35) against a slab loft
([1,4]×[−1,1] at z = 1, 3; volume 12) meet in A∩B = {z∈[1,3],
y∈[−1,1], x∈[1, w(z)]} with V = ∫₁³ 2(w−1) dz = 89/16 exactly.
"""

from __future__ import annotations

from fractions import Fraction as F

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md); everything
# here needs real geometry.
pytest.importorskip("forgekernel")

from forgekernel.loft import LoftSolid
from forgekernel.trimshell import TrimmedShell

from gitcad.kernel.ref import RefKernel


def _sq(half):
    return [(-half, -half), (half, -half), (half, half), (-half, half)]


BARREL = LoftSolid([(_sq(F(3, 2)), 0), (_sq(F(5, 2)), 2), (_sq(F(3, 2)), 4)])
SLAB = LoftSolid([([(1, -1), (4, -1), (4, 1), (1, 1)], 1),
                  ([(1, -1), (4, -1), (4, 1), (1, 1)], 3)])

VOL_A = F(2582, 35)          # barrel: 16·∫w², w = 3/2 + (3/2)s − s³/2
VOL_B = F(12)
VOL_AB = F(89, 16)           # ∫₁³ 2(w−1) dz, hand-derived


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def cap(k):
    return k.boolean("intersect", BARREL, SLAB)


def test_loft_by_loft_boolean_returns_an_audited_certified_shell(cap) -> None:
    assert isinstance(cap, TrimmedShell)
    assert cap.provenance == "certified"


def test_mass_props_bracket_contains_the_closed_form(k, cap) -> None:
    mp = k.mass_props(cap)
    assert mp["provenance"] == "certified"
    assert mp["volume_halfwidth"] > 0.0
    assert abs(mp["volume"] - float(VOL_AB)) <= mp["volume_halfwidth"]


def test_validate_runs_the_shell_audit(k, cap) -> None:
    report = k.validate(cap)
    assert report.ok
    assert report.checks["provenance"] == "certified"


def test_conservation_identity_holds_in_seam_brackets(k, cap) -> None:
    cup = k.boolean("union", BARREL, SLAB)
    mp_u, mp_i = k.mass_props(cup), k.mass_props(cap)
    truth = float(VOL_A + VOL_B)
    assert abs((mp_u["volume"] + mp_i["volume"]) - truth) \
        <= mp_u["volume_halfwidth"] + mp_i["volume_halfwidth"]


def test_cut_bracket_contains_the_closed_form(k) -> None:
    cut = k.boolean("cut", BARREL, SLAB)
    mp = k.mass_props(cut)
    assert abs(mp["volume"] - float(VOL_A - VOL_AB)) \
        <= mp["volume_halfwidth"]


def test_tessellate_returns_the_certified_safe_view(k, cap) -> None:
    mesh = k.tessellate(cap)
    assert mesh["provenance"] == "render"
    assert mesh["triangles"]
    assert mesh["gaps"], "a trimmed shell's uncertainty band must show"
    nv = len(mesh["vertices"])
    assert all(0 <= i < nv for t in mesh["triangles"] for i in t)
