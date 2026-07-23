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
