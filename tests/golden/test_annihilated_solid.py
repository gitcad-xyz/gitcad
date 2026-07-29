"""The empty solid is an ANSWER, not a failure (#136).

``cut(a, a)``, cut by a superset, and a disjoint intersect all legitimately
annihilate every point of the operand. The result used to be treated as a
defect three different ways: ``mass_props`` refused ("centroid of zero-volume
solid"), ``validate`` reported the emptiness as a *violation*
(``nonpositive-volume``), and ``measure``/``bbox`` let a raw
``ValueError: min() iterable argument is empty`` escape the seam — a
crash-class defect, not a refusal.

The contract pinned here:

  * volume is 0 — a real number, reported, because it IS the answer;
  * the centroid of the empty set does not exist, so the centroid fields are
    NaN (not a fabricated location) and the dict says ``empty: True``;
  * extents are 0 — the empty set has zero extent in every axis;
  * ``validate`` is ok: an empty solid produced by an annihilating boolean is
    exactly what it claims to be;
  * ``bbox`` refuses with a structured ``KernelError`` — the empty set has no
    location, and inventing one would be a wrong number wearing coordinates.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel
from gitcad.kernel import source_form  # ADR-0022


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _routes(k):
    a = k.box(10, 10, 10)
    return {
        "cut by itself": k.boolean("cut", a, a),
        "cut by a superset": k.boolean(
            "cut", a, k.transform(k.box(20, 20, 20), translate=(-5, -5, -5))),
        "disjoint intersect": k.boolean(
            "intersect", a, k.transform(k.box(5, 5, 5),
                                        translate=(50, 50, 50))),
    }


@pytest.fixture(scope="module", params=["cut by itself", "cut by a superset",
                                        "disjoint intersect"])
def empty(request, k):
    return _routes(k)[request.param]


def test_mass_props_reports_zero_volume_not_a_refusal(k, empty) -> None:
    mp = k.mass_props(empty)
    assert mp["volume"] == 0.0
    assert mp.get("empty") is True
    # no fabricated location: the empty set has no centroid
    assert all(math.isnan(mp[c]) for c in ("cx", "cy", "cz"))


def test_measure_reports_zero_volume_and_zero_extents(k, empty) -> None:
    m = k.measure(empty)
    assert m["volume"] == 0.0
    assert (m["dx"], m["dy"], m["dz"]) == (0.0, 0.0, 0.0)


def test_validate_accepts_the_legitimately_empty_solid(k, empty) -> None:
    rep = k.validate(empty)
    assert rep.ok
    assert rep.violations == []


def test_bbox_refuses_structurally_never_a_raw_valueerror(k, empty) -> None:
    with pytest.raises(KernelError) as e:
        k.bbox(empty)
    assert "empty" in str(e.value)


def test_a_nonempty_zero_volume_solid_still_fails_validate(k) -> None:
    """The pardon is for the EMPTY solid only. A degenerate solid that still
    carries polygons but no volume is a defect, and must keep failing."""
    from forgekernel.brep import Solid

    box = k.box(4, 4, 4)
    flat = Solid([p for p in source_form(box).polys][:2])   # two faces of a box: not a solid
    rep = k.validate(flat)
    assert not rep.ok
