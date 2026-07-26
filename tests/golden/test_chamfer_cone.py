"""Chamfering a CONE — a bevel whose setback lands in ℚ[√d].

Why this refused. ``_chamfer_lathe`` sets each corner back by ``d`` ALONG each
adjacent profile edge, so the new vertex is ``p ± d·(dr, dz)/L`` with
``L = √(dr²+dz²)``. The rectilinear profiles it shipped for have axis-aligned
edges, where ``L`` is rational and every new vertex stays in ℚ. A cone's slant
does not: ``cone(6, 2, 10)`` has ``L = √116 = 2√29``, ``_rational_sqrt``
returned ``None``, and the op refused with
"chamfer(profile edge with irrational length)".

That refusal was one step too strong, and the reason is worth stating because
the brief this closes warned about it in the opposite direction. The setback
is ``d/L``, a rational over a surd — but ℚ[√e] is a FIELD, so ``1/√e = √e/e``
is always back inside it. A single slant therefore costs exactly one radical
and no more. What genuinely does NOT fit is TWO slants with different
square-free parts: the profile then needs ℚ[√d₁, √d₂], which is biquadratic
and which ``SurdVal`` does not hold. That is the gate this adds, and it is the
same gate ``_gate_slanted_profile`` already applies to the shell path.

INDEPENDENT ORACLE — the numbers below were derived three ways, and the
kernel's own Green-contour sum is none of them:

  1. PAPPUS, per removed ring. Each chamfer removes a ring of triangular
     section, V = 2π·r̄·A. For ``cone(6, 2, 10), d=1``:
       base ring: verts (6,0), (5,0), (6−2/√29, 5/√29)
                  A = 5/(2√29),  r̄ = (17 − 2/√29)/3
                  V = 85π/(3√29) − 10π/87
       top  ring: verts (2,10), (2+2/√29, 10−5/√29), (1,10)
                  A = 5/(2√29),  r̄ = (5 + 2/√29)/3
                  V = 25π/(3√29) + 10π/87
     The two ℚ-parts CANCEL and the total removed is 110π/(3√29) exactly,
     so V = 520π/3 − 110π/(3√29) = π(520/3 − 110√29/87) ≈ 523.152159247.
  2. QUADRATURE of π∫r(z)²dz over the three straight spans of the chamfered
     profile (composite Simpson, n=2000 per span): 523.152159247391.
  3. MONTE CARLO, 4M samples in the 12×12×10 box, seed 20260726:
     522.909 ± 0.346 (0.70σ from the closed form).

Derivation 1 is the one that matters: it never forms the contour integral at
all, and its ℚ-part cancellation is a structural check the kernel's sum cannot
fake.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from forgekernel import body as B
from forgekernel.quadric import Cone, RevolveSolid
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _pi_coeff(vol):
    """The π coefficient of an exact volume, whatever ring it landed in."""
    from forgekernel.polypi import PiPoly

    if isinstance(vol, PiPoly):
        assert vol.degree <= 1, f"volume carries π² : {vol!r}"
        assert vol[0] == 0, f"volume carries a non-π part : {vol!r}"
        return vol[1]
    assert vol.a == 0, f"volume carries a non-π part : {vol!r}"
    return vol.b


# --------------------------------------------------------------- exact volume

def test_chamfering_a_tapering_cone_is_exact_in_the_surd_field(k) -> None:
    """cone(r1=6 @ z=0, r2=2 @ z=10), d=1.

    Chamfered profile, exactly:
        (0,0) — (5,0) — (6−2√29/29, 5√29/29)
              — (2+2√29/29, 10−5√29/29) — (1,10) — (0,10)
    """
    from forgekernel.surd import SurdVal

    cone = Cone(0, 0, 6, 2, 0, 10)
    out = k.chamfer(cone, (), 1)
    assert isinstance(out, RevolveSolid)

    s29 = SurdVal(0, 1, 29)
    expect = [(Fraction(0), Fraction(0)),
              (Fraction(5), Fraction(0)),
              (6 - s29 * Fraction(2, 29), s29 * Fraction(5, 29)),
              (2 + s29 * Fraction(2, 29), 10 - s29 * Fraction(5, 29)),
              (Fraction(1), Fraction(10)),
              (Fraction(0), Fraction(10))]
    got = list(out.loop)
    assert len(got) == len(expect)
    # the loop may be rotated/reversed by RevolveSolid's normalisation; compare
    # as a cyclic sequence of exact points
    assert any(all(got[(s + i) % len(got)][0] == expect[i][0]
                   and got[(s + i) % len(got)][1] == expect[i][1]
                   for i in range(len(expect)))
               for s in range(len(got))), got

    # 520π/3 − 110π/(3√29) = π(520/3 − 110√29/87), by Pappus (see module doc)
    coeff = _pi_coeff(B.volume(B.to_body(out)))
    assert coeff == Fraction(520, 3) - s29 * Fraction(110, 87)
    assert float(coeff) * math.pi == pytest.approx(523.152159247391, abs=1e-9)


def test_the_removed_rings_match_pappus_exactly(k) -> None:
    """The kernel's answer against 2π·r̄·A summed over the two rings —
    an independent derivation that never forms the contour integral."""
    from forgekernel.surd import SurdVal

    cone = Cone(0, 0, 6, 2, 0, 10)
    s29 = SurdVal(0, 1, 29)
    removed = (_pi_coeff(B.volume(B.to_body(cone)))
               - _pi_coeff(B.volume(B.to_body(k.chamfer(cone, (), 1)))))
    # 110/(3√29) = 110√29/87
    assert removed == s29 * Fraction(110, 87)


def test_a_widening_cone_chamfers_to_its_own_exact_number(k) -> None:
    """cone(r1=2 @ z=0, r2=5 @ z=10), d=1. Slant (3,10), L=√109.

    Pappus again, per ring:
      base ring (2,0), (1,0), (2+3/√109, 10/√109):
        A = 5/√109, r̄ = (5 + 3/√109)/3 → V = 10π(5 + 3/√109)/(3√109)
      top ring (5,10), (5−3/√109, 10−10/√109), (4,10):
        A = 5/√109, r̄ = (14 − 3/√109)/3 → V = 10π(14 − 3/√109)/(3√109)
      total removed = 190π/(3√109) + 0  (the ℚ parts cancel: +30/327 − 30/327)
    """
    from forgekernel.surd import SurdVal

    cone = Cone(0, 0, 2, 5, 0, 10)
    s109 = SurdVal(0, 1, 109)
    removed = (_pi_coeff(B.volume(B.to_body(cone)))
               - _pi_coeff(B.volume(B.to_body(k.chamfer(cone, (), 1)))))
    # 190/(3√109) = 190√109/327
    assert removed == s109 * Fraction(190, 327)
    assert float(removed) * math.pi == pytest.approx(
        190 * math.pi / (3 * math.sqrt(109)))


def test_a_pythagorean_slant_costs_no_radical_at_all(k) -> None:
    """cone(r1=8, r2=4, h=3): the slant is (-4,3), L=5, so the chamfered
    profile stays in ℚ and no surd appears anywhere. This one already worked
    and must keep its exact answer — widening a field has to be invisible to
    everything that did not need it.

    Pappus: base ring (8,0),(7,0),(36/5,3/5) → A=3/10, r̄=37/5 → 111π/25;
            top  ring (4,3),(24/5,12/5),(3,3) → A=3/10, r̄=59/15 → 59π/25.
    """
    cone = Cone(0, 0, 8, 4, 0, 3)
    out = k.chamfer(cone, (), 1)
    assert all(isinstance(r, Fraction) and isinstance(z, Fraction)
               for r, z in out.loop), out.loop
    removed = (_pi_coeff(B.volume(B.to_body(cone)))
               - _pi_coeff(B.volume(B.to_body(out))))
    assert removed == Fraction(111, 25) + Fraction(59, 25)


# ------------------------------------------------------------ the field gate

def test_two_different_slant_radicals_refuse_rather_than_crash(k) -> None:
    """A profile whose two slants are √116 = 2√29 and √20 = 2√5 needs
    ℚ[√29, √5], a biquadratic field SurdVal does not hold. It must REFUSE by
    name — a raw ValueError out of SurdVal would be a crash through the seam."""
    prof = RevolveSolid([(0, 0), (6, 0), (2, 10), (0, 14)], 0, 0)
    with pytest.raises(KernelError) as ei:
        k.chamfer(prof, (), 1)
    assert "radical" in str(ei.value)
    assert ei.value.signature.diagnostic == "NotYetImplemented"


def test_a_chamfered_cone_survives_the_metrics_seam(k) -> None:
    """Every metric the seam offers, on a surd-coordinate lathe."""
    out = k.chamfer(Cone(0, 0, 6, 2, 0, 10), (), 1)
    assert k.measure(out)["volume"] == pytest.approx(523.152159247391)
    assert 0 < float(k.mass_props(out)["cz"]) < 10
    (lo, hi) = k.bbox(out)
    assert float(hi[0]) == pytest.approx(6 - 2 / math.sqrt(29))
    assert k.validate(out).ok
    tri = k.tessellate(out)
    assert len(tri["triangles"]) > 0


def test_the_chamfered_cone_passes_the_differential_oracle(k) -> None:
    """The exact answer against the MESH it produces, and the mesh against a
    Monte-Carlo measurement of itself. Nothing here shares arithmetic with
    ``contour_r2_dz`` — this is the check that would have caught the 2d³/3
    chamfer bug the day it shipped."""
    from gitcad.bench.oracle import sweep

    shapes = {"chamfered cone": k.chamfer(Cone(0, 0, 6, 2, 0, 10), (), 1),
              "chamfered widening cone":
                  k.chamfer(Cone(0, 0, 2, 5, 0, 10), (), 1)}
    rows = sweep(k, n=40000, seed=7, shapes=shapes)
    assert len(rows) == 2
    for row in rows:
        assert row.converges, (row.shape, row.errors)
        assert row.ok, (row.shape, row.exact, row.meshes, row.mc, row.sigma)


# --------------------------------------------------- fillet: the hard boundary

def test_filleting_a_non_right_lathe_corner_names_the_angle_it_needs(k)  -> None:
    """A fillet arc at a corner of interior angle φ turns through π−φ, and the
    revolved volume carries that ANGLE linearly (the arc's centre is off the
    axis, so the ∫cos²t term survives). For cone(6,2,10) the base corner has
    tan φ = 5/2, and arctan(5/2) is transcendental — no ℚ[√d][π] holds it.
    The refusal must say so rather than pointing at a generic blend gap."""
    with pytest.raises(KernelError) as ei:
        k.fillet(Cone(0, 0, 6, 2, 0, 10), (), 1)
    msg = str(ei.value)
    assert "arctan" in msg and "5/2" in msg, msg
    assert ei.value.signature.diagnostic == "NotYetImplemented"


def test_filleting_an_ALREADY_surd_lathe_refuses_rather_than_crashing(k) -> None:
    """Naming the angle needs ``tan φ`` as an exact ℚ ratio, and a profile
    that already carries ℚ[√d] coordinates (a chamfered cone) has no such
    ratio to name. It must still REFUSE: a raw TypeError out of the seam is a
    defect however honest the refusal it replaced would have been."""
    surd_lathe = k.chamfer(Cone(0, 0, 6, 2, 0, 10), (), 1)
    with pytest.raises(KernelError) as ei:
        k.fillet(surd_lathe, (), Fraction(1, 4))
    assert ei.value.signature.diagnostic == "NotYetImplemented"
