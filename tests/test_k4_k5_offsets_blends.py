"""K4 (open shell) + K5 (selected-edge fillets) — exact on ref,
differentially checked against OCCT."""

from fractions import Fraction

import pytest

pytest.importorskip("forgekernel")

from gitcad.kernel.ref import RefKernel  # noqa: E402

F = Fraction


def _face_index(kernel, shape, axis, coord):
    ordered = sorted(shape.logical_faces().items(),
                     key=lambda kv: (kv[0][1], kv[0][0]))
    for i, ((pk, _), frags) in enumerate(ordered):
        n = pk[:3]
        ax = max(range(3), key=lambda c: abs(n[c]))
        if ax == axis and frags[0].verts[0][axis] == coord:
            return i
    raise AssertionError("face not found")


def test_open_shell_exact_hand_values() -> None:
    k = RefKernel()
    box = k.box(10, 10, 20)
    zmax = _face_index(k, box, 2, F(20))
    s = k.shell(k.box(10, 10, 20), [zmax], 1)
    assert k.mass_props(s)["volume"] == 2000 - 8 * 8 * 19    # 784, exact
    assert k.validate(s).ok
    # two openings through adjacent sides
    xmax = _face_index(k, box, 0, F(10))
    s2 = k.shell(k.box(10, 10, 20), [zmax, xmax], 1)
    assert k.mass_props(s2)["volume"] == 2000 - 9 * 8 * 19   # 632, exact


def test_open_shell_opens_the_right_side() -> None:
    # the probe test that caught the canonical-normal-sign trap: with
    # zmax removed, the top must be VOID and the floor must be WALL.
    k = RefKernel()
    box = k.box(10, 10, 20)
    zmax = _face_index(k, box, 2, F(20))
    s = k.shell(k.box(10, 10, 20), [zmax], 1)
    top = k.boolean("intersect", s, k.transform(
        k.box(1, 1, 1), translate=(F(9, 2), F(9, 2), 19)))
    assert top.volume() == 0                                  # open above
    floor = k.boolean("intersect", s, k.transform(
        k.box(1, 1, F(1, 2)), translate=(F(9, 2), F(9, 2), 0)))
    assert floor.volume() == F(1, 2)                          # solid below


@pytest.mark.occt
def test_open_shell_matches_occt_family() -> None:
    from gitcad.kernel.occt import OcctKernel

    k, ok_ = RefKernel(), OcctKernel()
    box = k.box(10, 10, 10)
    zmax = _face_index(k, box, 2, F(10))
    vr = k.mass_props(k.shell(k.box(10, 10, 10), [zmax], 1))["volume"]
    assert vr == 424                                          # exact
    # OCCT enumerates faces differently; every single-face opening of a
    # cube gives the same volume — the family must contain ref's value
    occt_vols = set()
    b = ok_.box(10, 10, 10)
    for i in range(6):
        occt_vols.add(round(ok_.mass_props(ok_.shell(
            ok_.box(10, 10, 10), [i], 1.0))["volume"], 6))
    assert occt_vols == {424.0}


# -- K5.0: selected-edge rolling-ball fillets ---------------------------------

def test_selected_edge_fillet_exact_pi_volume() -> None:
    import math

    k = RefKernel()
    box = k.box(10, 20, 30)
    edges = k.entities(box, "edge")
    assert len(edges) == 12
    zi = next(i for i, e in enumerate(edges) if abs(e["dir"][2]) > 0)
    s = k.fillet(k.box(10, 20, 30), [zi], 2)
    # V = 6000 − (4 − π)·30 = 5880 + 30π, exact in ℚ[π]
    from forgekernel.quadric import PiVal
    assert s.volume() == PiVal(5880, 30)
    assert abs(k.mass_props(s)["volume"] - (5880 + 30 * math.pi)) < 1e-9
    assert k.validate(s).ok


def test_adjacent_fillet_edges_refuse_with_stage() -> None:
    from gitcad.errors import KernelError

    k = RefKernel()
    box = k.box(10, 10, 10)
    edges = k.entities(box, "edge")
    # find two edges sharing a vertex: a z-edge and an x-edge at a corner
    zi = next(i for i, e in enumerate(edges) if abs(e["dir"][2]) > 0)
    zpt = edges[zi]["point"]
    xi = next(i for i, e in enumerate(edges)
              if abs(e["dir"][0]) > 0 and e["point"][1] == zpt[1])
    with pytest.raises(KernelError, match="K5.1"):
        k.fillet(k.box(10, 10, 10), [zi, xi], 1)


@pytest.mark.occt
def test_fillet_volume_family_matches_occt() -> None:
    """Differential: every OCCT single-edge fillet volume on a 10x20x30
    box lands exactly in ref's ℚ[π] family {6000−(4−π)L : L ∈ 10,20,30},
    4 edges per length."""
    import math
    from collections import Counter

    from gitcad.kernel.occt import OcctKernel

    ok_ = OcctKernel()
    fam_ref = {round(6000 - (4 - math.pi) * L, 6) for L in (10, 20, 30)}
    vols = []
    n = len(ok_.entities(ok_.box(10, 20, 30), "edge"))
    for i in range(n):
        s = ok_.fillet(ok_.box(10, 20, 30), [i], 2.0)
        vols.append(round(ok_.mass_props(s)["volume"], 6))
    assert set(vols) == fam_ref
    assert sorted(Counter(vols).values()) == [4, 4, 4]
