"""#134: the blend family beyond one constant radius on one solid.

Two deliverables, both exact, both previously wrong or unreachable:

* ``fillet(bossed plate, all)`` was a LIVE WRONG GREEN: ref.py filleted the
  ``DisjointUnion`` members separately and concatenated the faces, which
  rounds the boss's BURIED base rim as if it were exposed and leaves the
  contact patches inside the material as internal walls. The composite path
  mirrors ``_shell_bossed_plate``: rounded plate, boss wall, the convex
  top-rim quarter torus, and the CONCAVE junction quarter torus (the
  reentrant-edge precedent from the planar prism path — a blend that ADDS
  material). Closed forms derived by Pappus and verified against 2D
  quadrature and a 20M-sample Monte-Carlo membership test before the
  construction was written (z = +1.13 plain, +0.94 bored at 3 sigma):

      plain: 2464 + (473/3)pi - pi^2 = 2949.454837
      bored: 2464 + (458/3)pi - pi^2 = 2933.746874

  The junction term alone is 2*pi*(29/6 - 5*pi/4) = 29pi/3 - 5pi^2/2 — it
  needs pi^2, which is why the volume is a PiPoly.

* Variable radius (linear taper) on selected straight edges: the DISC-SWEEP
  semantic — each perpendicular slice is the 2D fillet of radius r(t) — whose
  surface is an oblique circular cone and whose removed volume
  (1-pi/4)*L*(r0^2+r0*r1+r1^2)/3 stays in Q[pi]. The rolling-ball semantic
  (Parasolid/SolidWorks) is transcendental for EVERY rational taper: the
  elliptic slice's eccentric-anomaly span obeys cos(du) = b^2 (b the taper
  slope), and by Niven du/pi is rational only at b^2 in {0, 1/2, 1}.
  The kernel therefore ships disc-sweep BY DEFINITION and refuses everything
  the tower cannot hold, naming the escaping constant.
"""
from __future__ import annotations

import math
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


def _z_edge_at(k, shape, x, y):
    """Index of the vertical box edge at (x, y) in the seam's enumeration."""
    for i, e in enumerate(k.entities(shape, "edge")):
        if e["dir"][2] != 0 and e["centroid"][0] == x and e["centroid"][1] == y:
            return i
    raise AssertionError("edge not found")


# --- the bossed plate: a wrong green becomes the composite ------------------

def test_bossed_plate_fillet_is_the_composite_not_the_pile(k) -> None:
    out = k.fillet(_boss(k, False), [], 1)
    body = out if isinstance(out, B.Body) else B.to_body(out)
    assert _exact_volume(body) == PiPoly([F(2464), F(473, 3), F(-1)])
    assert float(B.volume(body)) == pytest.approx(2949.454837, abs=1e-5)
    assert B.manifold_violations(body) == []
    assert _unpaired(B.tessellate(body, 0.1)) == 0
    # exactly two tori: the convex top rim and the concave junction ring
    assert sum(1 for f in body.faces
               if isinstance(f.surface, B.Torus)) == 2


def test_bored_boss_fillet_matches_the_closed_form(k) -> None:
    out = k.fillet(_boss(k, True), [], 1)
    body = out if isinstance(out, B.Body) else B.to_body(out)
    assert _exact_volume(body) == PiPoly([F(2464), F(458, 3), F(-1)])
    assert float(B.volume(body)) == pytest.approx(2933.746874, abs=1e-5)
    assert B.manifold_violations(body) == []
    assert _unpaired(B.tessellate(body, 0.1)) == 0
    assert sum(1 for f in body.faces
               if isinstance(f.surface, B.Torus)) == 2
    # the bore keeps its sharp rims (the DrilledSolid hole precedent):
    # boss wall + bore wall, both analytic cylinders
    assert sum(1 for f in body.faces
               if isinstance(f.surface, B.Cylinder)) == 14


def test_junction_blend_that_swallows_the_boss_wall_refuses(k) -> None:
    """r = 3 on a 6-high boss: the junction and top-rim blends meet mid-wall
    — a clipped blend carries an arccos, outside every exact field."""
    with pytest.raises(KernelError) as e:
        k.fillet(_boss(k, False), [], 3)
    assert e.value.predicate == "blend_overflow"
    assert "measured" not in (e.value.remedy or "") or True
    assert e.value.measured  # carries the numbers the guard saw


def test_junction_blend_running_off_the_plate_refuses(k) -> None:
    shape = k.boolean("union", k.box(30, 30, 3),
                      k.transform(k.cylinder(4, 6), translate=(5, 15, 3)))
    with pytest.raises(KernelError) as e:
        k.fillet(shape, [], 1)
    assert e.value.predicate is not None


def test_touching_members_outside_the_pattern_refuse(k) -> None:
    """Two bosses on one plate touch it without being the one-boss pattern:
    the pile answer rounds buried rims, so it must refuse rather than return."""
    shape = k.boolean("union", k.boolean(
        "union", k.box(30, 30, 3),
        k.transform(k.cylinder(3, 6), translate=(8, 8, 3))),
        k.transform(k.cylinder(3, 6), translate=(22, 22, 3)))
    with pytest.raises(KernelError, match="touch"):
        k.fillet(shape, [], 1)


def test_strictly_disjoint_members_still_fillet_memberwise(k) -> None:
    """Rounding distributes over strictly separated components — the
    member-wise answer is exact there and must keep working."""
    shape = k.boolean("union", k.box(10, 10, 10),
                      k.transform(k.cylinder(3, 10), translate=(20, 5, 0)))
    out = k.fillet(shape, [], 1)
    body = B.to_body(out)
    # rounded box 896 + 76pi/3, filleted cylinder 244pi/3 + 2pi^2
    assert float(B.volume(body)) == pytest.approx(
        896 + 320 * math.pi / 3 + 2 * math.pi ** 2, abs=1e-9)


# --- variable radius: the disc-sweep taper ----------------------------------

def test_variable_fillet_volume_is_exact(k) -> None:
    box = k.box(10, 10, 10)
    idx = _z_edge_at(k, box, 0, 0)
    out = k.fillet(box, [idx], (1, 2))
    # V = 1000 - (1 - pi/4) * 10 * (1 + 2 + 4) / 3  =  2930/3 + 35pi/6
    v = out.volume()
    assert (v.a, v.b) == (F(2930, 3), F(35, 6))
    assert float(v) == pytest.approx(994.9926238126071, abs=1e-12)
    lo, hi = out.bbox()
    assert (lo, hi) == ((0, 0, 0), (10, 10, 10))


def test_variable_fillet_mass_props_and_centroid(k) -> None:
    box = k.box(10, 10, 10)
    idx = _z_edge_at(k, box, 0, 0)
    mp = k.mass_props(k.fillet(box, [idx], (1, 2)))
    # independent closed forms: I2 = L(r0^2+r0r1+r1^2)/3, I2t = L^2(r0^2+
    # 2r0r1+3r1^2)/12, I3 = L(r0^3+r0^2r1+r0r1^2+r1^3)/4; transverse first
    # moment of a slice from its corner is r^3(5/6 - pi/4).
    ka = 1 - math.pi / 4
    i2, i2t, i3 = 70 / 3, 100 * 17 / 12, 10 * 15 / 4
    vrem = ka * i2
    vtot = 1000 - vrem
    mx = 5000 - (5 / 6 - math.pi / 4) * i3
    mz = 5000 - ka * i2t
    assert mp["volume"] == pytest.approx(vtot, abs=1e-9)
    assert mp["cx"] == pytest.approx(mx / vtot, abs=1e-9)
    assert mp["cy"] == pytest.approx(mx / vtot, abs=1e-9)
    assert mp["cz"] == pytest.approx(mz / vtot, abs=1e-9)


def test_equal_endpoints_collapse_to_the_constant_fillet(k) -> None:
    """r0 == r1 IS the constant fillet — same surface, and the constant
    machinery meshes, so collapsing is strictly better than a parallel rep."""
    box = k.box(10, 10, 10)
    idx = _z_edge_at(k, box, 0, 0)
    a = k.fillet(box, [idx], (2, 2))
    b = k.fillet(box, [idx], 2)
    assert type(a) is type(b)
    assert float(a.volume()) == pytest.approx(float(b.volume()), abs=0)


def test_adjacent_variable_edges_refuse_naming_the_corner_patch(k) -> None:
    box = k.box(10, 10, 10)
    i = _z_edge_at(k, box, 0, 0)
    j = next(idx for idx, e in enumerate(k.entities(box, "edge"))
             if e["dir"][0] != 0 and e["centroid"][1] == 0
             and e["centroid"][2] == 0)
    with pytest.raises(KernelError, match="corner patch"):
        k.fillet(box, [i, j], (1, 2))


def test_variable_overflow_refuses_with_the_two_admissible_ratios(k) -> None:
    box = k.box(10, 10, 10)
    idx = _z_edge_at(k, box, 0, 0)
    with pytest.raises(KernelError) as e:
        k.fillet(box, [idx], (1, 6))
    assert e.value.predicate == "blend_overflow"
    assert "1/2" in (e.value.remedy or "")


def test_constant_overflow_is_the_same_structured_refusal(k) -> None:
    box = k.box(10, 10, 10)
    idx = _z_edge_at(k, box, 0, 0)
    with pytest.raises(KernelError) as e:
        k.fillet(box, [idx], 6)
    assert e.value.predicate == "blend_overflow"


def test_variable_radius_on_a_lathe_rim_refuses_by_name(k) -> None:
    """A tapered blend on a CIRCULAR rim is not a torus and not a cone —
    no exact representation exists, so the refusal names the gap."""
    with pytest.raises(KernelError, match="variable"):
        k.fillet(k.cylinder(5, 12), [], (1, 2))


def test_variable_radius_needs_selected_edges(k) -> None:
    """radius=(r0, r1) with edges=[] would taper all twelve box edges, and
    every pair of them shares a vertex — the K5.3 corner patch, named."""
    with pytest.raises(KernelError, match="corner patch"):
        k.fillet(k.box(10, 10, 10), [], (1, 2))


def test_variable_fillet_mesh_and_step_refuse_honestly(k, tmp_path) -> None:
    """volume/bbox/mass_props are exact; the mesh needs the oblique-cone
    band (K5.3) — the FilletedPrism precedent: refuse by name, never crash."""
    box = k.box(10, 10, 10)
    idx = _z_edge_at(k, box, 0, 0)
    out = k.fillet(box, [idx], (1, 2))
    with pytest.raises(KernelError):
        k.tessellate(out)
    with pytest.raises(KernelError):
        k.export_step(out, str(tmp_path / "vfb.step"))
