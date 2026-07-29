"""Capping a sphere with a half-space must not care WHICH axis.

The three principal axes are the same problem relabelled: a permutation is an
isometry, so `op(sigma S) == sigma op(S)` exactly (ADR-0019 equivariance), and
a kernel that answers on z but refuses on x is not stating a mathematical
limit — it is reporting where someone happened to write the code.

This pins the axis-independence of BOTH halves at once: the exact volume and
centroid (the measurement side, #143) and the tessellation (the display side,
#144). The mesh assertions are deliberately structural — watertightness and
triangle count — not numeric: a mesh is a float artefact and the exact answer
is what carries the claim.
"""

from fractions import Fraction as F

import pytest

from gitcad.kernel import get_kernel


R = F(5)
CUT = F(5, 2)


def _sphere_capped(k, axis, keep_low=True):
    """A ball of radius 5 at the origin, cut by the plane x_axis = 5/2."""
    ball = k.sphere(R)                     # centred at the origin
    lo = [F(-10)] * 3
    hi = [F(10)] * 3
    if keep_low:
        lo[axis] = CUT                     # the tool removes the HIGH side
    else:
        hi[axis] = CUT
    # `box` is corner-at-origin, so the half-space slab is built at the size
    # it needs and then moved to its corner
    tool = k.transform(k.box(*(hi[j] - lo[j] for j in range(3))),
                       translate=tuple(lo))
    return k.boolean("cut", ball, tool)


@pytest.mark.parametrize("keep_low", [True, False])
def test_the_volume_is_the_same_on_every_axis(keep_low):
    k = get_kernel()
    vols = [k.mass_props(_sphere_capped(k, ax, keep_low))["volume"]
            for ax in range(3)]
    # EXACT equality, not a tolerance. These are the same rational multiple of
    # pi; if the axes disagree by so much as a float ulp, one of them went
    # through a numeric path it should not have.
    assert vols[0] == vols[1] == vols[2], vols


def test_the_centroid_follows_the_axis_it_was_cut_on():
    """The moment term is the part #143 added; this is what it is for."""
    k = get_kernel()
    for ax in range(3):
        c = k.mass_props(_sphere_capped(k, ax))["centroid"]
        # cut at +5/2 keeping the low side: the centroid shifts NEGATIVE along
        # the cut axis and stays on the sphere's centre in the other two
        assert c[ax] < -1e-9, (ax, c)
        for other in range(3):
            if other != ax:
                assert abs(c[other]) < 1e-9, (ax, other, c)


def test_the_mesh_is_watertight_on_every_axis():
    """#144: the sphere band used to stitch along z whatever the pole was."""
    k = get_kernel()
    counts = []
    for ax in range(3):
        mesh = k.tessellate(_sphere_capped(k, ax), deflection=0.5)
        tris = mesh["triangles"] if isinstance(mesh, dict) else mesh.triangles
        seen = {}
        for t in tris:
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                seen[(a, b)] = seen.get((a, b), 0) + 1
        unpaired = [e for e, n in seen.items()
                    if seen.get((e[1], e[0]), 0) != n]
        assert not unpaired, f"axis {ax}: {len(unpaired)} unpaired edges"
        counts.append(len(tris))
    # and the same SIZE, because it is the same solid relabelled — a mesher
    # that only accidentally closes on x would have no reason to agree here
    assert counts[0] == counts[1] == counts[2], counts
