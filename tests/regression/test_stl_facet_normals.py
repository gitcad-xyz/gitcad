"""REGRESSION (#31): export_stl wrote `facet normal 0 0 0` on every facet.

The STL spec expects each facet to carry the unit outward normal; the writer
hardcoded the zero placeholder, so strict validators flagged every facet of
every export. The normal must be derived from the triangle's winding
(right-hand rule) — the winding is already oriented, so this invents nothing.

Pins the public kernel seam (`RefKernel.export_stl`) only.
"""

from __future__ import annotations

import math

import pytest


def _facets(path):
    """(normal, (v0, v1, v2)) per facet from an ASCII STL."""
    facets, normal, cur = [], None, []
    for line in open(path).read().splitlines():
        line = line.strip()
        if line.startswith("facet normal"):
            normal = tuple(float(x) for x in line.split()[2:])
        elif line.startswith("vertex"):
            cur.append(tuple(float(x) for x in line.split()[1:]))
            if len(cur) == 3:
                facets.append((normal, tuple(cur)))
                cur = []
    return facets


def _winding_normal(tri):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
    ux, uy, uz = bx - ax, by - ay, bz - az
    wx, wy, wz = cx - ax, cy - ay, cz - az
    n = (uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx)
    mag = math.sqrt(sum(c * c for c in n))
    return tuple(c / mag for c in n) if mag else (0.0, 0.0, 0.0)


def test_stl_facet_normals_match_winding(tmp_path) -> None:
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    path = str(tmp_path / "plate.stl")
    k.export_stl(k.box(60, 40, 8), path)
    facets = _facets(path)
    assert facets, "no facets parsed"
    zero = sum(1 for n, _ in facets if n == (0.0, 0.0, 0.0))
    assert zero == 0, f"{zero}/{len(facets)} facets carry the 0 0 0 placeholder"
    for n, tri in facets:
        assert math.sqrt(sum(c * c for c in n)) == pytest.approx(1.0, abs=1e-6)
        expect = _winding_normal(tri)
        assert all(a == pytest.approx(b, abs=1e-6) for a, b in zip(n, expect)), (
            f"normal {n} disagrees with winding {expect}")


def test_stl_box_normals_are_axis_aligned_outward(tmp_path) -> None:
    """On an axis-aligned box every facet normal is a signed unit axis, and
    both orientations of each axis appear — outward, not just consistent."""
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    path = str(tmp_path / "box.stl")
    k.export_stl(k.box(10, 20, 30), path)
    seen = set()
    for n, _ in _facets(path):
        canon = tuple(round(c) for c in n)
        assert canon in {(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                         (0, 0, 1), (0, 0, -1)}, n
        assert all(abs(c - r) < 1e-9 for c, r in zip(n, canon))
        seen.add(canon)
    assert len(seen) == 6, f"missing outward directions: {seen}"
