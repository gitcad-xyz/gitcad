"""W17: the seam mesh of a boss-on-plate union hides no faces in material.

The canonical Body of a DisjointUnion used to concatenate the member
bodies' faces verbatim, so the flagship boss-on-plate meshed with the
plate's full top rectangle AND the boss's bottom cap buried inside the
contact disc — 30 triangles with solid on both sides. Volume and edge
pairing stayed right (two individually closed shells), which is exactly
why nothing caught it: the lie was topological, and any slicer or
half-edge consumer saw internal walls.

Since the stitch (forge to_body: the contact circle becomes an inner
loop of the plate's top face, the buried cap disk is dropped), the seam
mesh is ONE closed surface. This contract probes the interior of the
contact disc directly: no z-contact-plane triangle may cover any point
there.
"""
from __future__ import annotations

import pytest

pytest.importorskip("forgekernel")

from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _cover_count(mesh, zc, probes):
    verts = mesh["vertices"]
    flat = [[verts[i] for i in t] for t in mesh["triangles"]
            if all(verts[i][2] == zc for i in t)]
    hits = 0
    for px, py in probes:
        for a, b, c in flat:
            d1 = (b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0])
            d2 = (c[0] - b[0]) * (py - b[1]) - (c[1] - b[1]) * (px - b[0])
            d3 = (a[0] - c[0]) * (py - c[1]) - (a[1] - c[1]) * (px - c[0])
            if (d1 >= 0 and d2 >= 0 and d3 >= 0) or \
               (d1 <= 0 and d2 <= 0 and d3 <= 0):
                hits += 1
    return hits


def test_boss_on_plate_meshes_as_one_shell_with_nothing_buried(k) -> None:
    du = k.boolean("union", k.box(30, 30, 5),
                   k.transform(k.cylinder(6, 10), translate=(15, 15, 5)))
    mesh = k.tessellate(du, deflection=0.05)
    probes = [(15 + dx, 15 + dy) for dx in (-3.7, -1.3, 0.0, 1.9, 3.1)
              for dy in (-3.9, -1.1, 0.7, 2.3, 3.3)]
    # every probe sits well inside the contact disc (r = 6); before the
    # stitch each was covered TWICE (plate top + boss cap), now zero
    assert all((px - 15) ** 2 + (py - 15) ** 2 < 34 for px, py in probes)
    assert _cover_count(mesh, 5.0, probes) == 0

    # the mesh still encloses the exact union volume to inscription bias:
    # sample the same shape's exact volume through the seam
    exact = k.mass_props(du)["volume"]
    from forgekernel.tess import mesh_volume
    assert mesh_volume(mesh) == pytest.approx(exact, rel=0.02)

    # and every edge pairs by POSITION: one watertight surface, not two
    # closed shells hiding a wall
    verts = mesh["vertices"]
    seen: dict = {}
    for a, b, c in mesh["triangles"]:
        for u, v in ((a, b), (b, c), (c, a)):
            key = frozenset((tuple(verts[u]), tuple(verts[v])))
            seen[key] = seen.get(key, 0) + 1
    assert sum(1 for n in seen.values() if n != 2) == 0
