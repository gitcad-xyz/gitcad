"""A sphere with a coaxial BLIND bore — the probe's actual `sphere x cut
cylinder` cell, exact in ℚ[√d][π].

The capability probe's tool is ``cylinder(1, 100)`` translated to the bbox
midpoint of ``sphere(6)`` — the origin. ``cylinder(r, h)`` spans z = 0..h, so
the cut is coaxial but BLIND: it enters the top, exits nowhere, and stops at
z = 0 with its own flat bottom cap. Three faces survive:

  * the sphere minus ONE polar cap (a single rim at z = +√35; the south pole
    survives as a singular point on no edge, like a pointed cone's apex);
  * the bore wall, floor to rim;
  * the FLAT DISK floor at z = 0 — the tool's own bottom cap, a PLANE. An
    earlier backlog note guessed a spherical-cap floor; it is not one, because
    the sphere's surface at any admissible floor depth lies outside the bore.

Volume, from the removed set (bore cylinder πr²·(√d − f) plus the sphere's cap
above √d, d = R² − r², f the floor height relative to the centre):

    V = π · ( 2R³/3 + (2/3)·d·√d + r²·f )

For the probe's R=6, r=1, f=0 that is π(144 + 70√35/3) = 886.0606404251…,
banked with an independent Monte-Carlo membership check of 885.969 ± 1.296
(3σ, 4M samples) and re-verified fresh at seed 987654321 (16M samples,
analytic membership — no kernel code in the loop).

WHAT THIS DELIBERATELY DOES NOT DO. Only the CENTRED bore entering from the
TOP and stopping strictly inside the band is exact here. Off-axis leaves every
algebraic extension (elliptic integrals); a floor at or beyond ±√d is a
different topology (no wall left / a through ring / an untouched cap); a tool
stopping entirely inside the material would carve a closed internal void this
solid cannot hold. All of those refuse, and the refusal is the finished
answer, not a near-miss.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel

SQ35 = math.sqrt(35)


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _blind(k, dz=0.0):
    """The probe's own tool: cylinder(1, 100) with its floor at z = dz."""
    return k.transform(k.cylinder(1, 100), translate=(0, 0, dz))


def _closed_form(R, r, f) -> float:
    d = R * R - r * r
    return math.pi * (2 * R ** 3 / 3 + 2 * d * math.sqrt(d) / 3 + r * r * f)


def test_the_probes_own_cell_volume_matches_the_banked_closed_form(k) -> None:
    """Exactly the capability matrix's construction, against the backlog's
    banked number π(144 + 70√35/3) — never against the kernel's own output."""
    got = k.boolean("cut", k.sphere(6), _blind(k))
    assert float(k.mass_props(got)["volume"]) == pytest.approx(
        math.pi * (144 + 70 * SQ35 / 3), rel=1e-12)
    assert float(k.mass_props(got)["volume"]) == pytest.approx(
        886.0606404251233, rel=1e-12)


FLOORS = [0.0, 2.0, -3.0, 5.0]


@pytest.mark.parametrize("f", FLOORS, ids=[f"floor{f}" for f in FLOORS])
def test_the_volume_tracks_the_floor_depth_linearly(k, f) -> None:
    """dV/df = πr² exactly — the closed form is linear in the floor height,
    which is a property no wrong face list satisfies by accident (a
    spherical-cap floor would add a cubic term in f)."""
    got = k.boolean("cut", k.sphere(6), _blind(k, f))
    assert float(k.mass_props(got)["volume"]) == pytest.approx(
        _closed_form(6, 1, f), rel=1e-12)


def test_the_blind_bore_agrees_with_hemisphere_plus_half_a_napkin_ring(k) -> None:
    """A cross-check that never touches the implementation's formula: cutting
    at f=0 leaves the full south hemisphere plus the top half of the through
    ring, so V = (2/3)πR³ + (1/2)·(4/3)π·d^(3/2) — both terms written from
    independent textbook closed forms."""
    got = float(k.mass_props(k.boolean("cut", k.sphere(6), _blind(k)))["volume"])
    want = (2 / 3) * math.pi * 216 + 0.5 * (4 / 3) * math.pi * 35 ** 1.5
    assert got == pytest.approx(want, rel=1e-12)


def test_the_centroid_sits_below_centre_by_the_closed_form(k) -> None:
    """z̄ = m_z/(V/π), m_z = R²d/2 − d²/4 − R⁴/4 − r²(d − f²)/2 by hand:
    for (6, 1, 0), m_z = 630 − 306.25 − 324 − 17.5 = −17.75. Material left
    the TOP, so the centroid must drop."""
    mp = k.mass_props(k.boolean("cut", k.sphere(6), _blind(k)))
    assert mp["cx"] == pytest.approx(0.0, abs=1e-15)
    assert mp["cy"] == pytest.approx(0.0, abs=1e-15)
    assert mp["cz"] == pytest.approx(-17.75 / (144 + 70 * SQ35 / 3), rel=1e-12)
    assert mp["cz"] < 0


def test_the_bbox_keeps_the_south_pole_and_stops_at_the_rim(k) -> None:
    """The north cap is gone (top at +√35); the south pole survives (bottom
    at −6). Reporting ±6 would be loose at the top; reporting ±√35 would be
    UNSOUND at the bottom, and part.interference uses this as a skip-filter."""
    lo, hi = k.bbox(k.boolean("cut", k.sphere(6), _blind(k)))
    assert float(hi[2]) == pytest.approx(SQ35, rel=1e-12)
    assert float(lo[2]) == pytest.approx(-6.0, rel=1e-12)
    assert float(hi[0]) - float(lo[0]) == pytest.approx(12.0, rel=1e-12)


def test_it_meshes_watertight_through_the_seam_and_refines(k) -> None:
    from collections import Counter

    got = k.boolean("cut", k.sphere(6), _blind(k))
    coarse = k.tessellate(got, deflection=0.5)
    fine = k.tessellate(got, deflection=0.01)
    assert len(fine["triangles"]) > len(coarse["triangles"]) > 0
    for mesh in (coarse, fine):
        seen: Counter = Counter()
        for tri in mesh["triangles"]:
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                seen[(a, b)] += 1
        assert [e for e, n in seen.items()
                if seen.get((e[1], e[0]), 0) != n] == []


def _mesh_volume(mesh) -> float:
    """Divergence-theorem volume of a triangle soup. Floats are legal here —
    this measures a MESH, which is a display artifact (ADR-0019)."""
    verts, total = mesh["vertices"], 0.0
    for a, b, c in mesh["triangles"]:
        p, q, r = verts[a], verts[b], verts[c]
        total += (p[0] * (q[1] * r[2] - q[2] * r[1])
                  - p[1] * (q[0] * r[2] - q[2] * r[0])
                  + p[2] * (q[0] * r[1] - q[1] * r[0])) / 6.0
    return abs(total)


def test_the_seams_mesh_converges_on_the_exact_volume(k) -> None:
    """Compared against the closed form, never the mesher's own output.
    CONVERGENCE, not a single tolerance: 5x refinement must cut the error by
    roughly 5x, because an inscribed mesh's deficit is first-order in the
    deflection — a mesh of the wrong latitude band would be watertight and
    refining while sitting at a constant offset."""
    exact = math.pi * (144 + 70 * SQ35 / 3)
    got = k.boolean("cut", k.sphere(6), _blind(k))
    coarse = abs(_mesh_volume(k.tessellate(got, deflection=0.05)) - exact)
    fine = abs(_mesh_volume(k.tessellate(got, deflection=0.01)) - exact)
    finer = abs(_mesh_volume(k.tessellate(got, deflection=0.002)) - exact)
    assert coarse / fine > 3, f"5x refinement barely helped: {coarse} -> {fine}"
    assert fine / finer > 3, f"5x refinement barely helped: {fine} -> {finer}"
    assert finer / exact < 1e-3


def test_the_mesh_ray_cast_measurement_agrees(k) -> None:
    """The differential oracle's own independent instrument, pointed at this
    one solid: Monte-Carlo membership by ray-casting the tessellated mesh —
    different traversal, different arithmetic, floats throughout — must land
    within its stated error bar of the exact volume."""
    from gitcad.bench.oracle import mc_volume

    got = k.boolean("cut", k.sphere(6), _blind(k))
    est, sigma, _disc = mc_volume(got, k, n=200000, seed=20260726,
                                  deflection=0.01)
    exact = math.pi * (144 + 70 * SQ35 / 3)
    assert sigma > 0
    assert abs(est - exact) <= 5 * sigma, (
        f"MC {est} vs exact {exact} is {abs(est - exact) / sigma:.1f} sigma")


REFUSED = [
    ("off-axis blind bore", lambda k: k.transform(k.cylinder(1, 100),
                                                  translate=(2, 0, 0))),
    ("floor below the band", lambda k: k.transform(k.cylinder(1, 100),
                                                   translate=(0, 0, -5.95))),
    ("floor above the band", lambda k: k.transform(k.cylinder(1, 100),
                                                   translate=(0, 0, 5.95))),
    ("tool stops inside the material (closed internal void)",
     lambda k: k.transform(k.cylinder(1, 3), translate=(0, 0, 0))),
    ("tool top strands a cap floating above it",           # √35 < 5.95 < 6
     lambda k: k.transform(k.cylinder(1, 5.95), translate=(0, 0, 0))),
]


@pytest.mark.parametrize("label,tool", REFUSED, ids=[r[0] for r in REFUSED])
def test_the_cases_that_are_not_exact_still_refuse(k, label, tool) -> None:
    """Each of these is a DIFFERENT topology or leaves every algebraic
    extension; answering the nearest expressible solid instead would be a
    plausible wrong number. The refusal is the finished answer."""
    with pytest.raises(KernelError):
        k.boolean("cut", k.sphere(6), tool(k))


def test_a_floor_exactly_on_the_band_edge_refuses(k) -> None:
    """R=5, r=3 has a RATIONAL band edge (√16 = 4), so a floor AT the edge is
    exactly constructible — and there the bore wall has zero height and the
    result is a plane-capped sphere this solid does not describe. Strictness
    of the inequality is load-bearing."""
    with pytest.raises(KernelError):
        k.boolean("cut", k.sphere(5),
                  k.transform(k.cylinder(3, 100), translate=(0, 0, 4)))
