"""fillet(all) on rectilinear planar solids: an L/T prism and a shelled box.

Both closed forms were verified against INDEPENDENT measurements before being
written down here (the numbers a test asserts must never come from the
implementation — backlog §1.2):

* **L-prism** (30×10 + 10×20 arms, h=8, r=1). Every edge is axis-aligned and
  right-angled; the one REENTRANT vertical edge takes an INSIDE fillet (a
  quarter-cylinder of ADDED material on the void side, axis r inside the void
  diagonal), which meets the top/bottom edge blends in a quarter-swept torus
  (major 2r, minor r, axis the blend axis). Volume, by slab integration and
  independently by the boolean decomposition below:

      V = 3752 + 178π/3 + π²/2 = 3943.335966…

  Monte-Carlo membership (40M samples, written from the rolling-ball
  definition, no forge code): 3942.57 ± 0.57 (z = −1.4). Decomposed and
  measured tighter: union-of-rounded-boxes part 3941.19 ± 0.46 against
  11210/3 + 391π/6 (z = −0.4); intersection A∩B 778.871 ± 0.009 against
  2134/3 + 43π/2 (z = −0.7); reentrant blend 1.9425 ± 0.0010 against
  (1−π/4)(46/3 − 2π) (z = +0.3). The two membership implementations agreed
  pointwise on 20M samples.

* **T-prism** (bar 30×10, stem 10×10 on top, h=8, r=1) — TWO reentrant edges:

      V = 3000 + 136π/3 + π² = 3152.288537…       MC: 3152.58 ± 0.36 (z = +0.8)

* **Shelled box** (20³ shelled t=2, so cavity 16³). The cavity's edges are
  concave: filleting them ADDS material, and the cavity becomes exactly the
  rounded box 16³ (r=1) while the outside becomes the rounded box 20³ (r=1).
  The cavity's rounded form lies STRICTLY inside the outer one for any wall
  t > 0 (per-axis deficits shrink by t), so the B-rep is the outer faces plus
  the cavity faces sense-flipped, and

      V = steiner(20³,1) − steiner(16³,1) = 3856 + 12π = 3893.699082…

  MC membership (40M samples, core-distance test): 3893.63 ± 0.63 (z = −0.1).
"""

from __future__ import annotations

import math
from collections import defaultdict
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


def _profile(pts):
    return {"start": list(pts[0]),
            "segments": [{"kind": "line", "to": list(p)}
                         for p in list(pts[1:]) + [pts[0]]]}


L_PTS = [(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)]
T_PTS = [(0, 0), (30, 0), (30, 10), (20, 10), (20, 20), (10, 20),
         (10, 10), (0, 10)]


def _steiner(a, b, c, r):
    p, q, s = a - 2 * r, b - 2 * r, c - 2 * r
    return (p * q * s + 2 * r * (p * q + q * s + s * p)
            + math.pi * r * r * (p + q + s) + 4 * math.pi * r ** 3 / 3)


def _sound(body):
    """Every edge paired, the mesh watertight, and the STEP writer's audit."""
    from forgekernel import body as B
    from forgekernel.stepbody import write_step_body

    assert B.manifold_violations(body) == []
    ec = defaultdict(int)
    for a, b, c in B.tessellate(body, 0.03)["triangles"]:
        for e in ((a, b), (b, c), (c, a)):
            ec[tuple(sorted(e))] += 1
    assert all(n == 2 for n in ec.values()), "the mesh is not watertight"
    write_step_body(body)
    return len(body.faces)


# --- L-prism: one reentrant edge ---------------------------------------------

def test_l_prism_fillet_exact_volume(k):
    from forgekernel.polypi import PiPoly

    out = k.fillet(k.extrude(_profile(L_PTS), 8), [], 1)
    assert out.volume() == PiPoly([F(3752), F(178, 3), F(1, 2)])


def test_l_prism_fillet_against_boolean_decomposition(k):
    """The item's oracle: the same solid as box-unions minus cylinder wedges.

    F = A ∪ B ∪ W, disjointly (A ∪ B) ⊔ W, with A, B the two rounded boxes
    (Minkowski cores [1,29]×[1,9]×[1,7] and [1,9]×[1,29]×[1,7] ⊕ ball 1) and
    W the reentrant blend. V(A∩B) by slabs: the middle 6·(100 − 3(1−π/4)),
    plus two cap slabs ∫(10−2δ)² − 3(1−π/4)(1−δ)², δ = 1−√(1−t²), giving
    2134/3 + 43π/2 (MC-verified to ±0.009). W = (1−π/4)(46/3 − 2π): a
    (1−π/4) wedge along the 6mm straight run plus two torus-swept ends
    ∫(1+δ)² = 14/3 − π each.
    """
    v = float(k.fillet(k.extrude(_profile(L_PTS), 8), [], 1).volume())
    v_a = _steiner(30, 10, 8, 1)
    v_b = _steiner(10, 30, 8, 1)
    v_ab = 2134 / 3 + 43 * math.pi / 2
    v_w = (1 - math.pi / 4) * (46 / 3 - 2 * math.pi)
    assert v == pytest.approx(v_a + v_b - v_ab + v_w, abs=1e-9)


def test_l_prism_fillet_measure_and_centroid(k):
    out = k.fillet(k.extrude(_profile(L_PTS), 8), [], 1)
    m = k.measure(out)
    assert m["dx"] == m["dy"] == 30.0 and m["dz"] == 8.0
    mp = k.mass_props(out)
    # symmetry across the x=y diagonal, and the MC-measured centroid
    # (10.987 ± 0.002, same, 4.000 ± 0.001) from 40M membership samples
    assert mp["cx"] == pytest.approx(mp["cy"], abs=1e-9)
    assert mp["cx"] == pytest.approx(10.987, abs=0.008)
    assert mp["cz"] == pytest.approx(4.0, abs=1e-9)
    assert k.validate(out).ok


# --- T-prism: two reentrant edges --------------------------------------------

def test_t_prism_fillet_exact_volume(k):
    from forgekernel.polypi import PiPoly

    out = k.fillet(k.extrude(_profile(T_PTS), 8), [], 1)
    assert out.volume() == PiPoly([F(3000), F(136, 3), F(1)])
    mp = k.mass_props(out)
    assert mp["cx"] == pytest.approx(15.0, abs=1e-9)     # mirror symmetry
    # MC: c_y = 7.490 ± 0.001, c_z = 4
    assert mp["cy"] == pytest.approx(7.490, abs=0.008)
    assert mp["cz"] == pytest.approx(4.0, abs=1e-9)


# --- honest refusals ---------------------------------------------------------

def test_prism_fillet_refusals(k):
    # a diagonal edge: not rectilinear, so not this construction
    tri = k.extrude(_profile([(0, 0), (20, 0), (0, 20)]), 8)
    with pytest.raises(KernelError):
        k.fillet(tri, [], 1)
    # an edge shorter than 2r: the corner features would overlap along it
    lp = k.extrude(_profile(L_PTS), 8)
    with pytest.raises(KernelError):
        k.fillet(lp, [], 6)
    # radius exceeding half the height
    with pytest.raises(KernelError):
        k.fillet(lp, [], 5)
    # an H whose 3mm crossbar is thinner than 2r = 4: the top-edge blends of
    # its two long sides would collide mid-wall — every edge is ≥ 4 long, so
    # only a local-feature-size guard can catch it
    h_pts = [(0, 0), (10, 0), (10, F(17, 2)), (20, F(17, 2)), (20, 0),
             (30, 0), (30, 20), (20, 20), (20, F(23, 2)), (10, F(23, 2)),
             (10, 20), (0, 20)]
    hp = k.extrude(_profile(h_pts), 8)
    with pytest.raises(KernelError):
        k.fillet(hp, [], 2)


# --- shelled box -------------------------------------------------------------

def test_shelled_box_fillet_exact_volume(k):
    from forgekernel import body as B
    from forgekernel.quadric import PiVal

    out = k.fillet(k.shell(k.box(20, 20, 20), [], 2), [], 1)
    assert isinstance(out, B.Body)
    assert B.volume(out) == PiVal(F(3856), F(12))
    # 26 outer faces (6 flats + 12 quarter-cylinders + 8 octants) + 26 cavity
    assert _sound(out) == 52
    mp = k.mass_props(out)
    assert (mp["cx"], mp["cy"], mp["cz"]) == pytest.approx((10.0, 10.0, 10.0),
                                                           abs=1e-9)
    assert k.validate(out).ok


def test_shelled_box_fillet_differential_oracle(k):
    """The mesh's own volume must converge to the exact one (backlog §1.2),
    and an independent Monte-Carlo ray-cast of the mesh must agree with it."""
    from gitcad.bench.oracle import DEFLECTIONS, Row, mc_volume, mesh_volume

    out = k.fillet(k.shell(k.box(20, 20, 20), [], 2), [], 1)
    exact = 3856 + 12 * math.pi
    row = Row("shelled box fillet", exact,
              tuple(mesh_volume(out, k, d) for d in DEFLECTIONS))
    row.mc, row.sigma, row.discarded = mc_volume(out, k, n=20000,
                                                 deflection=DEFLECTIONS[-1])
    row.samples = 20000
    assert row.ok, (row.exact, row.meshes, row.mc, row.sigma)


def test_shelled_box_fillet_refuses_oversize_radius(k):
    s = k.shell(k.box(20, 20, 20), [], 2)
    # 2r = 18 exceeds the 16mm cavity: the cavity blends would collide
    with pytest.raises(KernelError):
        k.fillet(s, [], 9)
