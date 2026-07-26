"""fillet(all) on a chamfered box — the last #121 cell, exact in ℚ(√2,√3)[π].

The closed form asserted here was derived and verified INDEPENDENTLY of the
implementation, before it existed (backlog §1.2 / the derivation record in the
2026-07-26 workflow):

* **Probe cell** (box 20³, chamfer d=2, fillet r=1). The solid is convex, so
  fillet(all, r) is the opening P₋ᵣ ⊕ B_r; P₋₁ is the chamfered box of dims
  18³ with setback t' = d − (2−√2)r = √2, and Steiner over it gives

      V(P₋₁) = 5616 + 12√2          S(P₋₁) = 2424 − 468√2
      edges  = (54 − 6√2)π + 2√6·π  corners = 4π/3

      V = 8040 − 456√2 + (166/3 − 6√2 + 2√6)π = 7557.6867093895…

  Verified: pieces against qhull to ≤1e-12; volume by Monte-Carlo membership
  dist(q, P₋₁) ≤ 1 (exact polytope distance, facet + 48-segment decomposition)
  at THREE seeds — 20260726 40M: 7557.99 ± 0.29 (z +1.05); 987654321 60M:
  7557.74 ± 0.24 (z +0.23); fresh 1357911 40M: 7557.57 ± 0.29 (z −0.41), the
  last run before the seam was wired.

* **Non-cube** (30×20×10, d=2, r=1): same assembly, V = 5557.6867093895…
  (the t'-dependent terms coincide with the cube's because the eroded dims
  sum to 54 in both). MC seed 24681357 40M: 5557.88 ± 0.25 (z +0.80).

* **The trap, banked:** the 32 spherical corner patches are individually
  transcendental over every ℚ[√d][π] (arccos(1/3), arccos(1/√3)); they cancel
  only in aggregate to 4π/3·r³. Any per-corner accumulation is wrong by
  construction — the exact coefficients asserted below cannot come out of one.

* **√2 and √3 provenance:** √2 rides in on the eroded setback t' (offsetting
  a √2-normal plane by r moves its constant by r√2); √3 enters as the
  chamfer–chamfer edge length (√3/2)t' times its π/3 sweep (cos dihedral =
  −1/2 exactly, so 2π/3 by Niven) — surfacing as the 2√6·π term.
"""

from __future__ import annotations

import math
from fractions import Fraction as F

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _fcb(k, dims=(20, 20, 20), d=2, r=1):
    return k.fillet(k.chamfer(k.box(*dims), [], d), [], r)


def test_probe_cell_exact_closed_form(k):
    from forgekernel.bisurd import BiSurd
    from forgekernel.polypi import PiPoly

    v = _fcb(k).volume()
    assert v == PiPoly([BiSurd(8040, -456, 0, 0, 2, 3),
                        BiSurd(F(166, 3), -6, 0, 2, 2, 3)])
    assert math.isclose(float(v), 7557.6867093895, rel_tol=1e-12)


def test_probe_cell_through_the_seam(k):
    out = _fcb(k)
    m = k.measure(out)
    assert math.isclose(m["volume"], 7557.6867093895, rel_tol=1e-12)
    assert (m["dx"], m["dy"], m["dz"]) == (20.0, 20.0, 20.0)
    mp = k.mass_props(out)
    assert math.isclose(mp["volume"], 7557.6867093895, rel_tol=1e-12)
    # centrally symmetric: centroid at the box centre, exactly
    assert (mp["cx"], mp["cy"], mp["cz"]) == (10.0, 10.0, 10.0)
    assert k.validate(out).ok
    lo, hi = k.bbox(out)
    assert tuple(lo) == (0.0, 0.0, 0.0) and tuple(hi) == (20.0, 20.0, 20.0)


def test_non_cube_box(k):
    v = _fcb(k, dims=(30, 20, 10)).volume()
    assert math.isclose(float(v), 5557.6867093895, rel_tol=1e-12)


def test_fillet_result_is_smaller_than_the_chamfered_box(k):
    # exact-order sanity: blending a convex solid only removes material
    cb = k.chamfer(k.box(20, 20, 20), [], 2)
    v = _fcb(k).volume()
    assert v < 7568                    # chamfered box volume, exact
    assert v > 0
    assert float(k.measure(cb)["volume"]) == 7568.0


def test_translated_chamfered_box_still_detected(k):
    moved = k.transform(k.chamfer(k.box(20, 20, 20), [], 2),
                        translate=(5, 6, 7))
    out = k.fillet(moved, [], 1)
    mp = k.mass_props(out)
    assert math.isclose(mp["volume"], 7557.6867093895, rel_tol=1e-12)
    assert (mp["cx"], mp["cy"], mp["cz"]) == (15.0, 16.0, 17.0)


def test_bridging_regime_refuses_by_name(k):
    # d ≤ (2−√2)r: the ball bridges the chamfer facet — honest refusal,
    # never the pile of colliding blends and never a silent rounded box
    cb = k.chamfer(k.box(20, 20, 20), [], F(1, 2))
    with pytest.raises(KernelError, match="bridges the chamfer"):
        k.fillet(cb, [], 1)


def test_thin_face_regime_refuses_by_name(k):
    # C − 2d − (2√2−2)r ≤ 0: blends meet across the face
    cb = k.chamfer(k.box(20, 20, F(9, 2)), [], 2)
    with pytest.raises(KernelError, match="across the"):
        k.fillet(cb, [], 1)


def test_octagon_prism_is_not_mistaken_for_a_chamfered_box(k):
    # an extruded octagon has the chamfered box's bbox and even its top-face
    # inset, but is NOT chamfer(box) — the sound detector (rebuild + exact
    # symmetric difference) must not claim it; the diagonal side faces make
    # the honest answer a refusal
    prof = {"start": [2, 0],
            "segments": [{"kind": "line", "to": [18, 0]},
                         {"kind": "line", "to": [20, 2]},
                         {"kind": "line", "to": [20, 18]},
                         {"kind": "line", "to": [18, 20]},
                         {"kind": "line", "to": [2, 20]},
                         {"kind": "line", "to": [0, 18]},
                         {"kind": "line", "to": [0, 2]},
                         {"kind": "line", "to": [2, 0]}]}
    oct_prism = k.extrude(prof, 20)
    with pytest.raises(KernelError):
        k.fillet(oct_prism, [], 1)


def test_tessellate_and_step_refuse_honestly(k):
    # a REPRESENTATION, not a canonical Body (the FilletedPrism precedent):
    # mesh and STEP go through to_body, which refuses with the K3.7 stage
    out = _fcb(k)
    with pytest.raises(KernelError):
        k.tessellate(out)
    with pytest.raises(KernelError):
        k.export_step(out, "unused.step")
