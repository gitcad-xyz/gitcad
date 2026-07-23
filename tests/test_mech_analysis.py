"""Mechanical analysis: exact inertia through the seam + draft (DFM)."""

import pytest

pytest.importorskip("forgekernel")

from gitcad.analysis import draft_analysis, inertia  # noqa: E402
from gitcad.kernel.ref import RefKernel  # noqa: E402


def test_inertia_is_exact_for_forge_solids() -> None:
    k = RefKernel()
    inf = inertia(k, k.box(3, 4, 6))
    assert inf["exact"] is True
    # box 3×4×6: Ixx = V(b²+c²)/12 = 72·52/12 = 312, etc.
    assert inf["inertia"][0][0] == pytest.approx(312.0)
    assert sorted(round(m, 3) for m in inf["principal_moments"]) == [150.0, 270.0, 312.0]


@pytest.mark.occt
def test_inertia_matches_occt_exactly_on_L_prism() -> None:
    from gitcad.kernel.occt import OcctKernel

    prof = {"start": [0, 0], "segments": [
        {"kind": "line", "to": [40, 0]}, {"kind": "line", "to": [40, 10]},
        {"kind": "line", "to": [10, 10]}, {"kind": "line", "to": [10, 30]},
        {"kind": "line", "to": [0, 30]}, {"kind": "line", "to": [0, 0]}]}
    ir = inertia(RefKernel(), RefKernel().extrude(prof, 8))
    io = inertia(OcctKernel(), OcctKernel().extrude(prof, 8))
    assert ir["exact"] and not io["exact"]
    for i in range(3):
        for j in range(3):
            assert abs(ir["inertia"][i][j] - io["inertia"][i][j]) < 1e-6


def test_draft_analysis_flags_vertical_walls() -> None:
    k = RefKernel()
    # a plain box: 4 vertical walls have zero draft under +z pull
    da = draft_analysis(k, k.box(10, 10, 10), pull=(0, 0, 1), min_angle_deg=1.0)
    assert not da["ok"]
    assert len(da["violations"]) == 4
    assert all(v["draft_deg"] < 1e-6 for v in da["violations"])


def test_draft_analysis_passes_a_drafted_block() -> None:
    k = RefKernel()
    drafted = k.draft(k.box(30, 30, 15), [], 3.0, pull=(0, 0, 1), neutral_z=0.0)
    assert draft_analysis(k, drafted, min_angle_deg=1.0)["ok"]      # 3° > 1°
    assert not draft_analysis(k, drafted, min_angle_deg=5.0)["ok"]  # 3° < 5°


def test_thickness_analysis_min_wall() -> None:
    from gitcad.analysis import thickness_analysis

    k = RefKernel()
    # a 20×5×30 slab: the thin dimension is 5
    ta = thickness_analysis(k, k.box(20, 5, 30), min_wall=6.0)
    assert ta["min_thickness"] == 5.0
    assert not ta["ok"] and len(ta["thin_regions"]) == 1
    assert thickness_analysis(k, k.box(20, 5, 30), min_wall=4.0)["ok"]


def test_thickness_analysis_ignores_empty_slots() -> None:
    # REGRESSION (review finding): a U-channel's open slot is empty space,
    # NOT thin material — the sign of di+dj distinguishes wall from pocket.
    from gitcad.analysis import thickness_analysis

    k = RefKernel()
    base = k.box(5, 2, 3)
    left = k.transform(k.box(2, 4, 3), translate=(0, 2, 0))
    right = k.transform(k.box(2.5, 4, 3), translate=(2.5, 2, 0))
    u = k.boolean("union", k.boolean("union", base, left), right)
    ta = thickness_analysis(k, u, min_wall=1.0)
    assert ta["min_thickness"] == 2.0        # the real walls, not the 0.5 slot
    assert ta["ok"]


def test_draft_analysis_rejects_zero_pull() -> None:
    import pytest

    from gitcad.analysis import draft_analysis
    with pytest.raises(ValueError, match="non-zero"):
        draft_analysis(RefKernel(), RefKernel().box(5, 5, 5), pull=(0, 0, 0))


def test_inertia_of_freeform_patchsolid() -> None:
    from forgekernel.bsolid import PatchSolid, box_patches

    from gitcad.analysis import inertia
    inf = inertia(RefKernel(), PatchSolid(box_patches(3, 4, 6)))
    assert inf["exact"] is True
    assert inf["inertia"][0][0] == pytest.approx(312.0)   # V(b²+c²)/12


def test_principal_moments_with_products_of_inertia() -> None:
    # a rotated slab has nonzero off-diagonals; principal moments recover
    # the axis-aligned values regardless of orientation
    from gitcad.analysis import inertia

    k = RefKernel()
    slab = k.transform(k.box(10, 2, 6), rotate_deg=0)     # baseline
    p0 = sorted(inertia(k, slab)["principal_moments"])
    # the eigenvalue solver must return the same set the diagonal gives
    I = inertia(k, k.box(10, 2, 6))["inertia"]
    assert I[0][1] == 0                                    # axis-aligned: no products
    assert p0 == pytest.approx(sorted([I[0][0], I[1][1], I[2][2]]))


def test_thickness_analysis_rejects_non_forge_shape() -> None:
    import pytest

    from gitcad.analysis import thickness_analysis
    with pytest.raises(NotImplementedError):
        thickness_analysis(RefKernel(), object())
