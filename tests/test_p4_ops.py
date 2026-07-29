"""SW-map P4: scale, draft, split, rib — the everyday molded/machined-part
verbs. Null-kernel builds run in the base suite; geometry truth is
volume-asserted under OCCT."""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.errors import GitcadError
from gitcad.kernel.null import NullKernel
from gitcad.kernel import source_form  # ADR-0022


def _doc_with(op: str, params: dict) -> Document:
    d = Document()
    base = d.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 10}))
    d.add(Feature(op=op, params=params, inputs=[base]))
    return d


def test_new_ops_build_under_null_kernel() -> None:
    for op, params in [("scale", {"factor": 2}),
                       ("split", {"normal": "z", "offset": 4, "keep": "below"}),
                       ("rib", {"x1": 1, "y1": 5, "x2": 9, "y2": 5,
                                "height": 3, "thickness": 1})]:
        doc = _doc_with(op, params)
        result = doc.build(NullKernel())
        assert doc.features[-1].id in result.shapes, op


def test_split_validates_inputs() -> None:
    with pytest.raises(GitcadError, match="normal"):
        _doc_with("split", {"normal": "q", "offset": 1}).build(NullKernel())
    with pytest.raises(GitcadError, match="zero-length"):
        _doc_with("rib", {"x1": 1, "y1": 1, "x2": 1, "y2": 1,
                          "height": 3, "thickness": 1}).build(NullKernel())


def test_scale_volumes() -> None:
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    d = _doc_with("scale", {"factor": 2})
    assert k.mass_props(d.build(k).final(d))["volume"] == pytest.approx(8000)
    d = _doc_with("scale", {"fx": 2, "fy": 1, "fz": 1})
    assert k.mass_props(d.build(k).final(d))["volume"] == pytest.approx(2000)


def test_split_keeps_the_named_side() -> None:
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    d = _doc_with("split", {"normal": "z", "offset": 4, "keep": "below"})
    assert k.mass_props(d.build(k).final(d))["volume"] == pytest.approx(400)
    d = _doc_with("split", {"normal": "z", "offset": 4, "keep": "above"})
    assert k.mass_props(d.build(k).final(d))["volume"] == pytest.approx(600)


def test_rib_adds_exact_wall_volume() -> None:
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    d = Document()
    base = d.add(Feature(op="box", params={"dx": 20, "dy": 20, "dz": 2}))
    d.add(Feature(op="rib", params={"x1": 2, "y1": 10, "x2": 18, "y2": 10,
                                    "base_z": 2, "height": 8, "thickness": 2},
                  inputs=[base]))
    vol = k.mass_props(d.build(k).final(d))["volume"]
    assert vol == pytest.approx(20 * 20 * 2 + 16 * 2 * 8)


def test_draft_tilts_exactly_the_draftable_faces() -> None:
    """Pull +z on a cube: the 4 side faces accept draft, top/bottom refuse —
    asserted across every face index without assuming enumeration order.

    Was a forge_gap: ref.draft used to DROP the ``faces`` argument on the
    floor, so drafting one selected wall silently drafted all four (#133
    defect 2). Selection now maps face indices to footprint edges."""
    from gitcad.errors import KernelError
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    cube = k.box(10, 10, 10)
    ok, refused = 0, 0
    for idx in range(6):
        try:
            shape = k.draft(cube, [idx], 5.0)
            assert k.mass_props(shape)["volume"] != pytest.approx(1000)
            ok += 1
        except KernelError:
            refused += 1
    assert (ok, refused) == (4, 2)


def test_draft_one_wall_differs_from_all_walls() -> None:
    """The regression pinned exactly: draft(box, [one wall]) must NOT equal
    draft(box, all) — with the exact one-wall closed form as the oracle:
    V = A·H − (L·t/2)·H² (no corner d² term — those need BOTH incident
    edges drafted)."""
    from fractions import Fraction as Q

    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    box = k.box(10, 6, 4)
    walls = [i for i, f in enumerate(k.entities(box, "face"))
             if f.get("fragments") and _face_is_wall(k, box, i)]
    one = k.draft(box, [walls[0]], tan=Q(1, 10)).volume()
    all_ = k.draft(box, [], tan=Q(1, 10)).volume()
    assert one != all_
    # the y=0 (or symmetric) wall of length 10 or 6: both closed forms exact
    assert one in (Q(240) - Q(10, 2) * Q(1, 10) * 16,
                   Q(240) - Q(6, 2) * Q(1, 10) * 16)
    assert all_ == Q(16144, 75)


def _face_is_wall(k, shape, idx) -> bool:
    n = k.entities(shape, "face")[idx].get("plane")
    return n is not None and n[2] == 0


def test_draft_parting_line_exact_volume_and_mc() -> None:
    """#133 core contract: parting line mid-face splits every wall into two
    half-drafts, inset d(z) = t·|z−z_p|, widest at the parting plane.

    Two INDEPENDENT oracles, neither derived from kernel output:
    (1) closed form V = A·H − (P·t/2)(p²+q²) + (4/3)t²(p³+q³) computed here
        from the literal A, P of a 10×6 footprint;
    (2) Monte-Carlo membership sampling of the SPEC (point in the inset
        rectangle at its own z), seeded, 200k samples, 4σ gate."""
    import random

    from fractions import Fraction as Q

    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    d = k.draft(k.box(10, 6, 4), [], tan=Q(1, 10), parting_z=Q(3, 2))
    A, P, t = Q(60), Q(32), Q(1, 10)
    p, q = Q(3, 2), Q(5, 2)
    closed = A * 4 - (P * t / 2) * (p ** 2 + q ** 2) \
        + Q(4, 3) * t ** 2 * (p ** 3 + q ** 3)
    assert d.volume() == closed == Q(16999, 75)
    assert d.watertight_violations() == []

    rng = random.Random(20260726)
    hits, n = 0, 200_000
    for _ in range(n):
        x, y, z = rng.uniform(0, 10), rng.uniform(0, 6), rng.uniform(0, 4)
        dd = 0.1 * abs(z - 1.5)
        if dd <= x <= 10 - dd and dd <= y <= 6 - dd:
            hits += 1
    est = 240.0 * hits / n
    # sigma = 240*sqrt(p(1-p)/n) ~ 0.123; 4 sigma ~ 0.49
    assert abs(est - float(closed)) < 0.5


def test_draft_rejects_prism_masquerading_as_box() -> None:
    """#133 defect 1 regression, through the public seam: a triangular prism
    whose vertices all sit on bbox xy-corners used to pass the corner-subset
    gate and come back as the FULL-BOX frustum (218.26 drafted out of 120.0
    of material, no error). The footprint itself is now the gate."""
    from forgekernel.brep import Solid

    from gitcad.errors import KernelError
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    tri = Solid.prism([(0, 0), (10, 0), (10, 6)], 4)
    with pytest.raises(KernelError):
        k.draft(tri, [], 5.0)


def test_draft_cylinder_wall_is_a_cone() -> None:
    """A drafted cylinder wall IS a cone — already representable, ℚ[π]:
    r(z) = r − t·z gives the frustum π·h·(r0²+r0r1+r1²)/3, asserted
    exactly against the independent closed form."""
    from fractions import Fraction as Q

    from forgekernel.quadric import AxisStack, Cone, PiVal

    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    c = k.draft(k.cylinder(5, 8), [], tan=Q(1, 4))
    assert isinstance(source_form(c), Cone) and (source_form(c).r1, source_form(c).r2) == (5, 3)
    vol = AxisStack(source_form(c).cx, source_form(c).cy, [source_form(c)]).volume()
    assert vol == PiVal(0, Q(8) * (25 + 15 + 9) / 3) == PiVal(0, Q(392, 3))
    # parting line: two frustums meeting (widest) at the parting plane
    s = k.draft(k.cylinder(5, 8), [], tan=Q(1, 4), parting_z=3)
    r0, rp, r1 = Q(17, 4), Q(5), Q(15, 4)
    lower = Q(3) * (r0 ** 2 + r0 * rp + rp ** 2) / 3
    upper = Q(5) * (rp ** 2 + rp * r1 + r1 ** 2) / 3
    assert s.volume() == PiVal(0, lower + upper)
    # a cap's normal is parallel to the pull: BadInput, not a gap
    from gitcad.errors import KernelError
    with pytest.raises(KernelError, match="cap"):
        k.draft(k.cylinder(5, 8), [1], tan=Q(1, 4))


def test_draft_named_refusals() -> None:
    """A refusal with predicate/measured/remedy is a finished answer:
    sphere walls leave every exact field; ambiguous angle specs and a
    neutral plane fighting the parting plane are BadInput."""
    from fractions import Fraction as Q

    from gitcad.errors import KernelError
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    with pytest.raises(KernelError, match="no exact field|sphere"):
        k.draft(k.sphere(6), [], 5.0)
    box = k.box(10, 6, 4)
    with pytest.raises(KernelError, match="exactly one"):
        k.draft(box, [], 5.0, tan=Q(1, 10))
    with pytest.raises(KernelError, match="exactly one"):
        k.draft(box, [])
    with pytest.raises(KernelError, match="parting"):
        k.draft(box, [], tan=Q(1, 10), parting_z=2, neutral_z=1)
    with pytest.raises(KernelError, match="consume"):
        k.draft(box, [], tan=1, neutral_z=0)   # d_max=4 eats the 6-wall
    with pytest.raises(KernelError, match="strictly inside"):
        k.draft(box, [], tan=Q(1, 10), parting_z=9)


def test_draft_document_op_carries_tan_and_parting() -> None:
    """The document layer records the exact intent (tan as the spec, the
    parting plane) and replays it through any kernel — null included."""
    from gitcad.kernel.ref import RefKernel

    d = Document()
    base = d.add(Feature(op="box", params={"dx": 10, "dy": 6, "dz": 4}))
    d.add(Feature(op="draft", params={"faces": [], "tan": 0.1,
                                      "parting_z": 1.5}, inputs=[base]))
    assert d.features[-1].id in d.build(NullKernel()).shapes
    k = RefKernel()
    from fractions import Fraction as Q
    assert d.build(k).final(d).volume() == Q(16999, 75)
