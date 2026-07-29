"""Issue #14 — the lathe wall, measured and narrowed.

A coaxial cut or union on a solid of revolution is an operation on its
(r, z) PROFILE: subtracting or adding an axis-centred rectangle from a
closed polygon. That is exact plane geometry — no surface-surface
intersection, no new number field — and whenever the result is again ONE
closed loop, the answer is another ``RevolveSolid``.

The old guards demanded the bore stay strictly inside EVERY wall,
including the inner wall of a tube — so widening an existing bore, the
most ordinary lathe operation there is, refused with "bore is wider than
the lathe at some height". These tests pin the narrowed boundary:

  * exactly representable (one loop out): widen a through-bore, step a
    counterbore, relieve a mid-span band of an existing bore, truncate a
    cone by boring past its apex radius, split at a z plane, union an
    overlapping coaxial collar;
  * genuinely refused (not one loop / not axisymmetric): an internal
    cavity, a bore that severs the part, an x- or y-normal split.
"""

from __future__ import annotations

import math

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md). Everything below
# needs real geometry, so skip the module rather than break collection.
pytest.importorskip("forgekernel")

from forgekernel.quadric import Cone, Cyl, DisjointUnion, RevolveSolid
from gitcad.document import Document, Feature
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel
from gitcad.kernel import source_form  # ADR-0022


@pytest.fixture()
def k():
    return RefKernel()


def _tube(inner=5, outer=15, h=20):
    return RevolveSolid([(inner, 0), (outer, 0), (outer, h), (inner, h)], 0, 0)


# -- coaxial re-bores: profile-minus-rectangle, one loop out -------------------

def test_widening_a_tubes_bore_is_still_a_tube(k) -> None:
    """A tube inner r=5 bored r=8 straight through IS the tube inner r=8 —
    the guard used to read the inner wall as material and refuse."""
    out = k.boolean("cut", _tube(), k.transform(k.cylinder(8, 40),
                                                translate=(0, 0, -10)))
    assert isinstance(source_form(out), RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(
        math.pi * (15 * 15 - 8 * 8) * 20)


def test_counterboring_a_tube_steps_its_bore(k) -> None:
    """Blind from the top, stopping mid-height: the bore wall gains a step
    (a shoulder at the tool's floor) and stays one closed profile."""
    out = k.boolean("cut", _tube(), k.transform(k.cylinder(8, 15),
                                                translate=(0, 0, 10)))
    assert isinstance(source_form(out), RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(
        math.pi * ((15 * 15 - 5 * 5) * 20 - (8 * 8 - 5 * 5) * 10))


def test_relieving_the_middle_of_an_existing_bore(k) -> None:
    """Open at neither end — but NOT a cavity, because the relieved band
    meets the bore that is already there. The old guard refused this as
    "open at neither end" without looking for the bore."""
    out = k.boolean("cut", _tube(), k.transform(k.cylinder(8, 10),
                                                translate=(0, 0, 5)))
    assert isinstance(source_form(out), RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(
        math.pi * ((15 * 15 - 5 * 5) * 20 - (8 * 8 - 5 * 5) * 10))


def test_boring_past_a_cone_apex_truncates_it(k) -> None:
    """The wall r(z) = 5 - z/2 crosses the r=1 bore at z=8; above that the
    tool removes the whole disc, so the cone is truncated there and the
    result is a ring z in [0, 8]: V = pi * int_0^8 (r(z)^2 - 1) dz =
    224 pi / 3 — LESS than the uncut 250 pi / 3, as cutting must be."""
    out = k.boolean("cut", Cone(0, 0, 5, 0, 0, 10), Cyl(0, 0, 1, -5, 15))
    assert isinstance(source_form(out), RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(math.pi * 224 / 3)
    assert k.mass_props(out)["volume"] < math.pi * 250 / 3


def test_a_true_internal_cavity_still_refuses(k) -> None:
    """No existing bore to meet: the profile would need a second loop."""
    with pytest.raises(KernelError, match="neither end|one closed"):
        k.boolean("cut", Cyl(0, 0, 5, 0, 12),
                  k.transform(k.cylinder(1, 4), translate=(0, 0, 2)))


def test_a_bore_that_severs_the_part_still_refuses(k) -> None:
    """An hourglass necked to r=1 bored r=2: everything at the neck goes,
    the part falls into two solids, and one loop cannot say that."""
    hourglass = RevolveSolid([(0, 0), (5, 0), (1, 10), (5, 20), (0, 20)], 0, 0)
    with pytest.raises(KernelError, match="wider than the lathe"):
        k.boolean("cut", hourglass, Cyl(0, 0, 2, -5, 25))


# -- split: a z-normal plane keeps the solid of revolution ---------------------

STEPPED = [(0, 0), (4, 0), (4, 5), (7, 5), (7, 9), (0, 9)]


def _split_tool(k, s, offset, keep):
    (x0, y0, z0), (x1, y1, z1) = k.bbox(s)
    pad = 1.0 + max(x1 - x0, y1 - y0, z1 - z0)
    lo, hi = z0 - pad, z1 + pad
    start = offset if keep == "above" else lo
    end = hi if keep == "above" else offset
    return k.transform(
        k.box((x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad, end - start),
        translate=(x0 - pad, y0 - pad, start))


@pytest.mark.parametrize("keep,want", [
    ("below", math.pi * (16 * 5 + 49 * 1)),
    ("above", math.pi * 49 * 3),
], ids=["below", "above"])
def test_a_z_split_of_a_stepped_shaft_truncates_the_profile(k, keep, want) -> None:
    s = RevolveSolid(STEPPED, 0, 0)
    out = k.boolean("intersect", s, _split_tool(k, s, 6, keep))
    assert isinstance(source_form(out), RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(want)


def test_a_z_split_through_a_cone_slant_is_exact(k) -> None:
    """r(z) = 2 + 3z/10; keep below z=4: V = pi * 688/25."""
    s = Cone(0, 0, 2, 5, 0, 10)
    out = k.boolean("intersect", s, _split_tool(k, s, 4, "below"))
    assert isinstance(source_form(out), RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(math.pi * 688 / 25)


def test_the_document_split_op_works_on_a_revolve(k) -> None:
    """The intent-level op end to end: split(normal=z) on a revolve feature
    — the row issue #14 measured as refusing."""
    doc = Document()
    prof = {"start": [0, 0], "segments": [
        {"kind": "line", "to": [4, 0]}, {"kind": "line", "to": [4, 5]},
        {"kind": "line", "to": [7, 5]}, {"kind": "line", "to": [7, 9]},
        {"kind": "line", "to": [0, 9]}]}
    rid = doc.add(Feature(op="revolve", params={"profile": prof}))
    doc.add(Feature(op="split", params={"normal": "z", "offset": 6,
                                        "keep": "below"}, inputs=[rid]))
    out = doc.build(k).final(doc)
    assert isinstance(source_form(out), RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(
        math.pi * (16 * 5 + 49 * 1))


def test_an_x_split_of_a_lathe_refuses_naming_the_symmetry(k) -> None:
    """Keeping half a lathe breaks its axial symmetry — that boundary is
    permanent for this representation and the refusal must say so."""
    s = RevolveSolid(STEPPED, 0, 0)
    (x0, y0, z0), (x1, y1, z1) = k.bbox(s)
    pad = 1.0 + max(x1 - x0, y1 - y0, z1 - z0)
    tool = k.transform(k.box((x1 - 2) + pad, (y1 - y0) + 2 * pad,
                             (z1 - z0) + 2 * pad),
                       translate=(2, y0 - pad, z0 - pad))
    with pytest.raises(KernelError, match="symmetr"):
        k.boolean("intersect", s, tool)


def test_a_split_that_keeps_nothing_refuses(k) -> None:
    s = RevolveSolid(STEPPED, 0, 0)
    tool = k.transform(k.box(30, 30, 5), translate=(-15, -15, 20))
    with pytest.raises(KernelError, match="keeps nothing|nothing of"):
        k.boolean("intersect", s, tool)


# -- union: an overlapping coaxial collar fuses into the profile ---------------

def test_an_overlapping_coaxial_collar_unions_exactly(k) -> None:
    """The hose-nozzle case from the issue thread: collar r16 x 3 over a
    body of outer r15 — OVERLAPPING, so DisjointUnion is the wrong tool,
    and the union is the union of the two profiles: one loop, exact."""
    body = RevolveSolid([(0, 0), (15, 0), (15, 20), (0, 20)], 0, 0)
    collar = k.transform(k.cylinder(16, 3), translate=(0, 0, 18))
    out = k.boolean("union", body, collar)
    assert isinstance(source_form(out), RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(
        math.pi * (225 * 20 + 256 * 1 + (256 - 225) * 2))


def test_a_buried_coaxial_collar_unions_to_the_body_itself(k) -> None:
    """A collar entirely inside the material adds nothing — the profile
    union equals the body's own profile."""
    body = RevolveSolid([(0, 0), (15, 0), (15, 20), (0, 20)], 0, 0)
    collar = k.transform(k.cylinder(10, 4), translate=(0, 0, 8))
    out = k.boolean("union", body, collar)
    assert isinstance(source_form(out), RevolveSolid)
    assert k.mass_props(out)["volume"] == pytest.approx(math.pi * 225 * 20)


def test_a_tangent_coaxial_collar_still_takes_the_disjoint_path(k) -> None:
    """Stacked exactly on top: tangent contact is measure-zero and the
    existing DisjointUnion answer stays — this path only opens where
    DisjointUnion refuses."""
    body = RevolveSolid([(0, 0), (15, 0), (15, 20), (0, 20)], 0, 0)
    collar = k.transform(k.cylinder(16, 3), translate=(0, 0, 20))
    out = k.boolean("union", body, collar)
    assert isinstance(source_form(out), DisjointUnion)


def test_an_overlapping_noncoaxial_union_refuses_without_claiming_disjoint(k) -> None:
    """The old text said "disjoint-union of RevolveSolid+Cyl arrives at
    K2.3" about a pair that OVERLAPS — the message must not misname the
    configuration it refuses."""
    body = RevolveSolid([(0, 0), (15, 0), (15, 20), (0, 20)], 0, 0)
    off = Cyl(3, 0, 4, 5, 15)
    with pytest.raises(KernelError) as ei:
        k.boolean("union", body, off)
    assert "disjoint-union" not in str(ei.value)
    assert "K2.3" in str(ei.value)
