"""#131: the mesh of a shelled-then-chamfered box must be a real manifold.

The repro: ``shell(box(20,20,20), (), 2)`` then ``chamfer(all, 1)`` — a planar
Solid whose canonical form has faces meeting along exactly-collinear T-junction
seams at the cavity's chamfered corners. The mesher's float 2D projection put
those seam vertices ~1e-15 off the line, and when the noise landed on the
convex side earcut ate the vertex as a near-zero-area SLIVER triangle whose
long edge chords past the seam. Undirected edge counts still paired (the
sliver launders the T-junction), ``validate().ok`` stayed True — and the mesh
carried overlapping degenerate facets that tear the moment anything discards
them: edge-use histogram {2: 1064, 3: 2, 4: 1, 1: 1} at the cavity corners.

Fixed in forge mesh2d (noise-scaled epsilon on the keep_collinear
collinearity decisions); this pins the seam-level contract: no degenerate
triangles, every DIRECTED edge paired with its reverse, at coarse and fine
deflections. The volume assertions are self-consistency (mesh vs exact), not
truth — the exact value is pinned by the kernel's own field arithmetic and
was unaffected by the defect (mesh/STL only, as filed).
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

pytest.importorskip("forgekernel")

from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def chamfered_shell(k):
    return k.chamfer(k.shell(k.box(20, 20, 20), (), 2), [], 1)


def _tri_area(v, t):
    a, b, c = (v[t[0]], v[t[1]], v[t[2]])
    ab = [b[i] - a[i] for i in range(3)]
    ac = [c[i] - a[i] for i in range(3)]
    cr = (ab[1] * ac[2] - ab[2] * ac[1],
          ab[2] * ac[0] - ab[0] * ac[2],
          ab[0] * ac[1] - ab[1] * ac[0])
    return math.sqrt(sum(x * x for x in cr)) / 2


@pytest.mark.parametrize("deflection", [0.8, 0.2, 0.05])
def test_the_mesh_is_manifold_with_no_degenerate_facets(k, chamfered_shell,
                                                        deflection) -> None:
    mesh = k.tessellate(chamfered_shell, deflection=deflection)
    v = mesh["vertices"]
    directed: Counter = Counter()
    for t in mesh["triangles"]:
        assert _tri_area(v, t) > 1e-9, f"degenerate sliver triangle {t}"
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            directed[(a, b)] += 1
    unpaired = sum(1 for (a, b), n in directed.items()
                   if directed.get((b, a), 0) != n)
    assert unpaired == 0


def test_the_mesh_encloses_the_exact_volume(k, chamfered_shell) -> None:
    """All faces are planar, so the mesh volume must match the exact volume to
    float precision — any gap is a hole or an overlap."""
    from forgekernel import body as B

    exact = float(B.volume(B.to_body(chamfered_shell)))
    mesh = k.tessellate(chamfered_shell, deflection=0.2)
    v = mesh["vertices"]
    vol6 = 0.0
    for a, b, c in mesh["triangles"]:
        pa, pb, pc = v[a], v[b], v[c]
        vol6 += (pa[0] * (pb[1] * pc[2] - pb[2] * pc[1])
                 - pa[1] * (pb[0] * pc[2] - pb[2] * pc[0])
                 + pa[2] * (pb[0] * pc[1] - pb[1] * pc[0]))
    assert vol6 / 6 == pytest.approx(exact, rel=1e-9)
    assert k.validate(chamfered_shell).ok
