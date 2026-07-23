"""SW-map P8: detail views (circle-clipped scaled crops) + engrave
(sketch text via the shared stroke font, now in gitcad-core)."""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.errors import GitcadError
from gitcad.kernel.null import NullKernel


def test_shared_strokefont_one_source() -> None:
    from gitcad.ecad.strokefont import text_strokes as via_ecad
    from gitcad.strokefont import text_strokes as via_core

    assert via_ecad is via_core            # the shim re-exports, no fork


def test_clip_poly_to_circle() -> None:
    from gitcad.drawing.sheet import _clip_poly_to_circle

    # horizontal line through a unit circle at origin: clipped to the chord
    runs = _clip_poly_to_circle([(-5, 0), (5, 0)], 0, 0, 1)
    assert len(runs) == 1
    (a, b), = [(runs[0][0], runs[0][-1])]
    assert a[0] == pytest.approx(-1) and b[0] == pytest.approx(1)
    # line missing the circle: nothing survives
    assert _clip_poly_to_circle([(-5, 3), (5, 3)], 0, 0, 1) == []


def test_engrave_builds_and_rejects_empty_text() -> None:
    d = Document()
    base = d.add(Feature(op="box", params={"dx": 40, "dy": 12, "dz": 3}))
    d.add(Feature(op="engrave", params={"text": "GITCAD", "x": 3, "y": 3,
                                        "height": 5, "top_z": 3, "depth": 0.5},
                  inputs=[base]))
    result = d.build(NullKernel())
    assert d.features[-1].id in result.shapes
    d2 = Document()
    b2 = d2.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 3}))
    d2.add(Feature(op="engrave", params={"text": "", "x": 1, "y": 1,
                                         "height": 5, "top_z": 3},
                   inputs=[b2]))
    with pytest.raises(GitcadError, match="empty"):
        d2.build(NullKernel())


@pytest.mark.occt
def test_engrave_removes_material() -> None:
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    d = Document()
    base = d.add(Feature(op="box", params={"dx": 40, "dy": 12, "dz": 3}))
    d.add(Feature(op="engrave", params={"text": "GITCAD", "x": 3, "y": 3,
                                        "height": 5, "top_z": 3, "depth": 0.5},
                  inputs=[base]))
    vol = k.mass_props(d.build(k).final(d))["volume"]
    assert vol < 40 * 12 * 3
    assert vol > 40 * 12 * 3 * 0.95        # grooves, not craters


@pytest.mark.occt
def test_detail_view_lands_on_sheet(tmp_path) -> None:
    from gitcad.mcp.server import REGISTRY

    d = Document()
    base = d.add(Feature(op="box", params={"dx": 40, "dy": 30, "dz": 5}))
    d.add(Feature(op="hole", params={"x": 5, "y": 5, "top_z": 5,
                                     "depth": 5, "diameter": 2},
                  inputs=[base]))
    out = tmp_path / "p8.svg"
    REGISTRY["model_drawing"](model=d.dumps(), path=str(out),
                              details=[{"cx": 5, "cy": 5, "r": 6}])
    svg = out.read_text(encoding="utf-8")
    assert "DETAIL A  (2:1)" in svg
