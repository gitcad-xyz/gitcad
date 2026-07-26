"""A sphere with a coaxial bore through it — exact in ℚ[√d][π].

The first real user of the number field #117 built. It is a good first user
precisely because its answer is known in closed form and is *surprising*:

    V = (4/3)·π·(R² − r²)^(3/2)

depends only on the band height, not on R and r separately. A 6 mm sphere
bored to leave a 2h band has the same volume as a 100 mm sphere bored to leave
the same band. That makes it an unusually strong oracle — an implementation
that quietly used R or r on its own would produce a plausible number that
fails the equal-band test below, and nothing else would catch it.

WHAT THIS DELIBERATELY DOES NOT DO. Only the CENTRED, THROUGH case is exact.
Off-axis, the volume acquires elliptic integrals and leaves every algebraic
extension — there is nothing to be exact about, so it refuses. A blind bore
leaves a spherical-cap floor that this two-face solid cannot hold, so it
refuses too. Both refusals are the finished answer for now, not a near-miss.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _through(k, half=50):
    return k.transform(k.cylinder(1, 2 * half), translate=(0, 0, -half))


RINGS = [(6, 1), (10, 6), (5, 3), (13, 5)]
IDS = [f"R{R}r{r}" for R, r in RINGS]


@pytest.mark.parametrize("R,r0", RINGS, ids=IDS)
def test_the_volume_matches_the_closed_form(k, R, r0) -> None:
    ring = k.boolean("cut", k.sphere(R),
                     k.transform(k.cylinder(r0, 400), translate=(0, 0, -200)))
    assert float(k.mass_props(ring)["volume"]) == pytest.approx(
        (4 / 3) * math.pi * (R * R - r0 * r0) ** 1.5, rel=1e-12)


def test_the_volume_depends_only_on_the_band_height(k) -> None:
    """The claim no naive implementation satisfies by accident.

    V is a function of R² − r² alone. An implementation that used R or r
    separately — easy to do when the profile is derived from the sphere — would
    still produce a plausible positive number, and only this property would
    catch it.

    Checked across the rational (R, r) pairs available: each band height must
    reproduce (4/3)π·band^(3/2), and two different spheres that happen to share
    a band height must agree with each other exactly.
    """
    by_band: dict[int, float] = {}
    for R, r0 in ((6, 1), (10, 6), (5, 3), (13, 5), (7, 2)):
        ring = k.boolean("cut", k.sphere(R),
                         k.transform(k.cylinder(r0, 400),
                                     translate=(0, 0, -200)))
        band = R * R - r0 * r0
        vol = float(k.mass_props(ring)["volume"])
        assert vol == pytest.approx((4 / 3) * math.pi * band ** 1.5, rel=1e-12)
        if band in by_band:
            assert vol == pytest.approx(by_band[band], rel=1e-12), (
                f"same band {band} from a different sphere gave a different "
                "volume — the implementation is using R or r on its own")
        by_band[band] = vol


def test_the_bbox_stops_at_the_band_not_the_sphere(k) -> None:
    """The polar caps are gone, so the solid's z-extent is 2√(R²−r²), not 2R.
    Reporting 2R would be loose; reporting 2r would be UNSOUND, and
    part.interference uses this box as a skip-filter."""
    ring = k.boolean("cut", k.sphere(6), _through(k))
    (lo, hi) = k.bbox(ring)
    assert float(hi[2]) - float(lo[2]) == pytest.approx(2 * math.sqrt(35),
                                                        rel=1e-12)
    assert float(hi[0]) - float(lo[0]) == pytest.approx(12.0, rel=1e-12)


@pytest.mark.xfail(strict=True, reason=(
    "NapkinRing has no canonical-B-rep converter yet, and the seam correctly "
    "refuses rather than falling back to the representation's own mesher — "
    "that fallback was removed in #124 because it silently discarded the "
    "caller's deflection. The converter needs a TRIMMED SPHERICAL ZONE face "
    "(the sphere between the two bore circles) plus the bore wall; the solid "
    "itself already meshes correctly via NapkinRing.tessellate, so this is "
    "plumbing, not geometry. strict=True so it fails loudly once wired up."))
def test_it_meshes_through_the_seam_and_refines(k) -> None:
    ring = k.boolean("cut", k.sphere(6), _through(k))
    coarse = len(k.tessellate(ring, deflection=0.5)["triangles"])
    fine = len(k.tessellate(ring, deflection=0.01)["triangles"])
    assert fine > coarse > 0


def test_the_representation_itself_meshes_inside_its_own_bbox(k) -> None:
    """What DOES work today, pinned so the converter has a target: the solid
    meshes correctly and the mesh fits the reported box."""
    ring = k.boolean("cut", k.sphere(6), _through(k))
    (lo, hi) = k.bbox(ring)
    mesh = ring.tessellate(0.05)
    assert len(mesh["triangles"]) > 0
    for v in mesh["vertices"]:
        for i in range(3):
            assert float(lo[i]) - 1e-6 <= v[i] <= float(hi[i]) + 1e-6
    assert len(ring.tessellate(0.01)["triangles"]) > len(
        ring.tessellate(0.5)["triangles"])


REFUSED = [
    ("off-axis bore", lambda k: k.transform(k.cylinder(1, 100),
                                            translate=(2, 0, -50))),
    ("blind bore", lambda k: k.transform(k.cylinder(1, 100),
                                         translate=(0, 0, 0))),
    ("bore wider than the sphere", lambda k: k.transform(
        k.cylinder(9, 100), translate=(0, 0, -50))),
]


@pytest.mark.parametrize("label,tool", REFUSED, ids=[r[0] for r in REFUSED])
def test_the_cases_that_are_not_exact_still_refuse(k, label, tool) -> None:
    """A near-miss silently answered is worse than a refusal. Each of these
    leaves ℚ[√d][π] or needs a face this solid does not have."""
    with pytest.raises(KernelError):
        k.boolean("cut", k.sphere(6), tool(k))
