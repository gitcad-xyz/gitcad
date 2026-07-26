"""Round-9 survivors W7/W8/W11/W12: representation metrics through the seam.

Two representation classes, four silent wrong numbers (all tier A):

- W8  MiteredSweep.bbox padded the centreline by sqrt(profile area) — for a
      20x1 plate that box CUT 5.5 mm INSIDE real material on both x sides
      (and `requirements.bbox_max_mm` passes/fails parts from this box).
- W11 MiteredSweep.centroid_f returned the centroid of the WIRE (length-
      weighted centreline midpoints), not the solid.
- W7  SphereOverlap.centroid_f returned the midpoint of the two centres for
      every op — the cut centroid came back +3.0 where the truth is -26/33,
      the wrong side of the origin.
- W12 SphereOverlap.bbox ignored the radical plane (cut) and the lens waist
      (intersect).

Every expected number below is a closed form re-derived independently of the
kernel (direct integration; cross-checked by Monte Carlo membership sampling
in the fixing session). Violated invariant: a reported metric is either the
metric of the solid or a structured refusal — never a plausible stand-in.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from gitcad.kernel import get_kernel


@pytest.fixture(scope="module")
def k():
    return get_kernel()


def _rect(w, h):
    return {"start": (-w / 2, -h / 2), "segments": [
        {"kind": "line", "to": (w / 2, -h / 2)},
        {"kind": "line", "to": (w / 2, h / 2)},
        {"kind": "line", "to": (-w / 2, h / 2)},
        {"kind": "line", "to": (-w / 2, -h / 2)}]}


def test_w8_straight_sweep_bbox_is_the_prism_box(k):
    """A 20x1 rectangle swept 30 up is a prism (the kernel's own exact
    volume 600 = 20*1*30 proves the shape): bbox (-10,-.5,0)..(10,.5,30)."""
    sw = k.sweep(_rect(20, 1), [[0, 0, 0], [0, 0, 30]])
    lo, hi = k.bbox(sw)
    assert lo == pytest.approx((-10.0, -0.5, 0.0), rel=0, abs=1e-9)
    assert hi == pytest.approx((10.0, 0.5, 30.0), rel=0, abs=1e-9)
    m = k.measure(sw)
    assert m["volume"] == pytest.approx(600.0)
    assert m["dx"] == pytest.approx(20.0)
    assert m["dy"] == pytest.approx(1.0)
    assert m["dz"] == pytest.approx(30.0)


def test_w11_l_sweep_centroid_is_the_solid_not_the_wire(k):
    """10x10 square swept z-up then x-along: closed form (1.875, 0, 8.125)
    on the kernel's own miter model (leg 1 = {|x|,|y|<=5, 0<=z, x+z<=10},
    leg 2 its mirror through the 45-degree miter plane); the wire answer
    was (2.5, 0, 7.5)."""
    sw = k.sweep(_rect(10, 10), [[0, 0, 0], [0, 0, 10], [10, 0, 10]])
    mp = k.mass_props(sw)
    assert mp["volume"] == pytest.approx(2000.0)
    assert mp["centroid"] == pytest.approx((1.875, 0.0, 8.125),
                                           rel=0, abs=1e-9)


def test_w7_sphere_cut_centroid_is_on_the_negative_side(k):
    """r=5 spheres 6 apart, cut: lens x-moment 104*pi by direct integration,
    so cx = -104/132 = -26/33 = -0.78788 — NEGATIVE (reported +3.0)."""
    so = k.boolean("cut", k.sphere(5),
                   k.transform(k.sphere(5), translate=(6, 0, 0)))
    mp = k.mass_props(so)
    assert mp["volume"] == pytest.approx(132 * math.pi)
    assert mp["cx"] == pytest.approx(float(Fraction(-26, 33)), rel=0, abs=1e-12)
    assert mp["cy"] == 0.0 and mp["cz"] == 0.0


def test_w12_sphere_overlap_bbox_stops_at_plane_and_waist(k):
    """Cut ends at the radical plane x = d1 = 3; the lens's transverse
    extent is the waist radius sqrt(r1^2 - d1^2) = 4."""
    a = k.sphere(5)
    b = k.transform(k.sphere(5), translate=(6, 0, 0))
    assert k.bbox(k.boolean("cut", a, b)) == ((-5.0, -5.0, -5.0),
                                              (3.0, 5.0, 5.0))
    assert k.bbox(k.boolean("intersect", a, b)) == ((1.0, -4.0, -4.0),
                                                    (5.0, 4.0, 4.0))
    # union keeps the two-sphere box it always had
    assert k.bbox(k.boolean("union", a, b)) == ((-5.0, -5.0, -5.0),
                                                (11.0, 5.0, 5.0))
