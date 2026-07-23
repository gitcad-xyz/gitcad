"""SW-map P4: scale, draft, split, rib — the everyday molded/machined-part
verbs. Null-kernel builds run in the base suite; geometry truth is
volume-asserted under OCCT."""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.errors import GitcadError
from gitcad.kernel.null import NullKernel


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


@pytest.mark.occt
def test_scale_volumes() -> None:
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    d = _doc_with("scale", {"factor": 2})
    assert k.mass_props(d.build(k).final(d))["volume"] == pytest.approx(8000)
    d = _doc_with("scale", {"fx": 2, "fy": 1, "fz": 1})
    assert k.mass_props(d.build(k).final(d))["volume"] == pytest.approx(2000)


@pytest.mark.occt
def test_split_keeps_the_named_side() -> None:
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    d = _doc_with("split", {"normal": "z", "offset": 4, "keep": "below"})
    assert k.mass_props(d.build(k).final(d))["volume"] == pytest.approx(400)
    d = _doc_with("split", {"normal": "z", "offset": 4, "keep": "above"})
    assert k.mass_props(d.build(k).final(d))["volume"] == pytest.approx(600)


@pytest.mark.occt
def test_rib_adds_exact_wall_volume() -> None:
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    d = Document()
    base = d.add(Feature(op="box", params={"dx": 20, "dy": 20, "dz": 2}))
    d.add(Feature(op="rib", params={"x1": 2, "y1": 10, "x2": 18, "y2": 10,
                                    "base_z": 2, "height": 8, "thickness": 2},
                  inputs=[base]))
    vol = k.mass_props(d.build(k).final(d))["volume"]
    assert vol == pytest.approx(20 * 20 * 2 + 16 * 2 * 8)


@pytest.mark.occt
def test_draft_tilts_exactly_the_draftable_faces() -> None:
    """Pull +z on a cube: the 4 side faces accept draft, top/bottom refuse —
    asserted across every face index without assuming enumeration order."""
    from gitcad.errors import KernelError
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
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
