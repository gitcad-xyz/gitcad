"""K3.7 golden: the smooth multi-section loft worked example, through the seam.

``k.loft`` with 3+ sections and ``ruled=False`` is the smooth path: forge's
``LoftSolid`` interpolates every vertex fiber and the shared z(v) with natural
cubic splines solved exactly in Q, so the volume is an exact rational —
provenance ``"exact"``, never a bare float estimate (ADR-0019).

The acceptance geometry is hand-derivable end to end. Squares of half-width
1, 2, 1 at z = 0, 1, 2: the natural spline through (1, 2, 1) has
M0 = M2 = 0 and M1 = 6·(1 − 4 + 1)/4 = −3, so on each (symmetric) segment
the half-width is

    w(s) = 1 + (3/2)s − (1/2)s³ ,   s ∈ [0, 1]

and z(v) is linear (the section heights are evenly spaced), giving

    V = 8·∫₀¹ w(s)² ds = 8 · 383/140 = 766/35 .

Three independent pipelines must agree on that exact rational: the closed-form
∫A(v)z′(v)dv volume, the Bézier patch-skin flux (``to_patches``), and a seeded
Monte-Carlo membership oracle. The K7 boolean then consumes the same solid
against a slab loft whose intersection volume is hand-integrable (267/128),
and a near-miss slab configuration must refuse structurally — never a raw
exception through the seam (the zero-crash rule).
"""

from __future__ import annotations

import random
from fractions import Fraction as F

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md); everything here
# needs real geometry.
pytest.importorskip("forgekernel")

from forgekernel.loft import LoftSolid
from forgekernel.trimshell import TrimmedShell

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel
from gitcad.kernel import source_form  # ADR-0022

V_TRUE = F(766, 35)                      # 8 · ∫₀¹ (1 + 3s/2 − s³/2)² ds


def _sq_profile(half):
    """Closed square dict profile, the seam's section format."""
    h = float(half)
    pts = [(-h, -h), (h, -h), (h, h), (-h, h), (-h, -h)]
    return {"start": list(pts[0]),
            "segments": [{"kind": "line", "to": list(p)} for p in pts[1:]]}


def _w(s):
    """Exact spline half-width on either (symmetric) segment."""
    return 1 + F(3, 2) * s - F(1, 2) * s ** 3


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def barrel(k):
    return k.loft([(_sq_profile(1), 0), (_sq_profile(2), 1), (_sq_profile(1), 2)])


def test_seam_loft_of_three_sections_is_the_smooth_solid(k, barrel) -> None:
    # 3+ sections without ruled=True routes to the natural-cubic LoftSolid —
    # distinct geometry from the ruled prismatoid stack, whose volume would be
    # two frustums 2·(1/3)(4 + 16 + 8) = 56/3 ≠ 766/35.
    assert isinstance(source_form(barrel), LoftSolid)
    assert barrel.volume() == V_TRUE                 # exact Fraction, not approx
    assert barrel.volume() != F(56, 3)               # smooth ≠ ruled
    mp = k.mass_props(barrel)
    assert mp["provenance"] == "exact"
    assert mp["volume"] == float(V_TRUE)
    assert (mp["cx"], mp["cy"], mp["cz"]) == (0.0, 0.0, 1.0)   # symmetry


def test_patch_skin_flux_reproduces_the_identical_rational(barrel) -> None:
    # to_patches is an independent pipeline: degree-(1,3) Bézier walls from the
    # spline coefficients + planar caps; its divergence-theorem flux must equal
    # the closed-form volume AS THE SAME Fraction, not merely approximately.
    skin = barrel.to_patches()
    assert len(skin.patches) == 10                   # 2 segments × 4 walls + 2 caps
    assert skin.seams and len(skin.seams) == 20      # closed skin, seams proven
    assert skin.volume() == V_TRUE


def test_monte_carlo_membership_agrees(barrel) -> None:
    # Seeded MC oracle straight from the definition: z(v) is linear so the
    # section at height z is the square of half-width w(s), s = z (or 2 − z).
    rng = random.Random(20260727)
    n = 200_000
    hits = 0
    for _ in range(n):
        x = rng.uniform(-2.0, 2.0)
        y = rng.uniform(-2.0, 2.0)
        z = rng.uniform(0.0, 2.0)
        s = z if z <= 1.0 else 2.0 - z
        w = 1.0 + 1.5 * s - 0.5 * s ** 3
        if abs(x) <= w and abs(y) <= w:
            hits += 1
    est = hits / n * 32.0
    p = float(V_TRUE) / 32.0
    sigma = 32.0 * (p * (1.0 - p) / n) ** 0.5
    assert abs(est - float(V_TRUE)) < 4.0 * sigma


# ---------------------------------------------------------------------------
# K7 consumption: the worked example is a first-class boolean operand.
# Slab = box [1/2, 3] × [−3/4, 3/4] × [1/2, 3/2] (2-section loft — a wall
# patch border shared with the barrel's z = 1 junction refuses seam_corner).
# Intersection truth, by hand:  ∫_{1/2}^{3/2} w dz = 2·(13/8 − 87/128)
# = 121/64, so  V∩ = (3/2)·(121/64 − 1/2) = 267/128.  All dyadic: exact floats.
# ---------------------------------------------------------------------------

RECT = [(F(1, 2), F(-3, 4)), (3, F(-3, 4)), (3, F(3, 4)), (F(1, 2), F(3, 4))]
V_CAP = F(267, 128)


def test_k7_boolean_consumes_the_worked_example(k, barrel) -> None:
    slab = LoftSolid([(RECT, F(1, 2)), (RECT, F(3, 2))])
    assert slab.volume() == F(15, 4)                 # (5/2)·(3/2)·1, exact box
    cap = k.boolean("intersect", barrel, slab)
    assert isinstance(cap, TrimmedShell)
    mp = k.mass_props(cap)
    assert mp["provenance"] == "certified"
    assert mp["volume_halfwidth"] > 0.0              # a bracket, never bare
    assert abs(mp["volume"] - float(V_CAP)) <= mp["volume_halfwidth"]


def test_out_of_envelope_boolean_refuses_structurally(k, barrel) -> None:
    # A slab whose chain ends sit too near the domain borders (y = ±1/2) is
    # outside the current K7 stitching envelope. That is a finished answer —
    # a structured KernelError refusal, never a raw exception (zero-crash).
    narrow = [(F(1, 2), F(-1, 2)), (3, F(-1, 2)), (3, F(1, 2)), (F(1, 2), F(1, 2))]
    slab = LoftSolid([(narrow, F(1, 4)), (narrow, F(3, 2))])
    with pytest.raises(KernelError, match="K7"):
        k.boolean("intersect", barrel, slab)
