"""Model-drawing BOM: union-tree derivation, table + balloons on the sheet.

Derivation oracle (null backend): a union tree of patterned rails, repeated
treads, and a cut hole must yield grouped BOM lines whose quantities count
pattern copies and repeats, and the cut tool must NOT appear as a part.
Rendering oracle (occt): the SVG carries the table header and circled
balloons; the PDF content stream carries the table too — notes used to be
silently dropped on the PDF path.
"""

import pytest

from gitcad.document import Document, Feature


def _ladder_doc() -> Document:
    """Two patterned rails + three identical treads + one pin, one hole cut."""
    doc = Document()
    rail = doc.add(Feature(op="box", params={"dx": 25, "dy": 20, "dz": 1150}))
    rails = doc.add(Feature(op="pattern_linear",
                            params={"count": 2, "step": [325, 0, 0]},
                            inputs=[rail]))
    group = rails
    for z in (250.0, 500.0, 750.0):
        tread = doc.add(Feature(op="box", params={"dx": 300, "dy": 60, "dz": 15}))
        moved = doc.add(Feature(op="move", params={"translate": [25, -60, z]},
                                inputs=[tread]))
        group = doc.add(Feature(op="boolean", params={"kind": "union"},
                                inputs=[group, moved]))
    pin = doc.add(Feature(op="cylinder", params={"radius": 4, "height": 350,
                                                 "axis": "x"}))
    group = doc.add(Feature(op="boolean", params={"kind": "union"},
                            inputs=[group, pin]))
    # a cut is a modification of the base body, never a BOM line
    tool = doc.add(Feature(op="cylinder", params={"radius": 2, "height": 100}))
    doc.add(Feature(op="boolean", params={"kind": "cut"}, inputs=[group, tool]))
    return doc


def test_model_bom_groups_and_counts_null_backend():
    from gitcad.drawing.bom import model_bom
    from gitcad.kernel.null import NullKernel

    kern = NullKernel()
    doc = _ladder_doc()
    lines = model_bom(doc, doc.build(kern), kern)

    by_label = {ln["label"]: ln for ln in lines}
    assert by_label["BOX 25×20×1150"]["qty"] == 2      # pattern counted
    assert by_label["BOX 300×60×15"]["qty"] == 3       # repeats grouped
    assert by_label["CYL Ø8×350"]["qty"] == 1
    # the cut tool must not be a part line
    assert "CYL Ø4×100" not in by_label
    assert len(lines) == 3
    # item numbers are 1..n in table order
    assert [ln["item"] for ln in lines] == [1, 2, 3]


def test_model_bom_parameters_resolve_null_backend():
    from gitcad.drawing.bom import model_bom
    from gitcad.kernel.null import NullKernel

    doc = Document()
    doc.set_parameter("L", 100)
    doc.set_parameter("W", 20)
    doc.add(Feature(op="box", params={"dx": "=W", "dy": "=W/2", "dz": "=L"}))
    kern = NullKernel()
    lines = model_bom(doc, doc.build(kern), kern)
    assert lines == [{"item": 1, "qty": 1, "label": "BOX 20×10×100",
                      "anchors": lines[0]["anchors"]}]


@pytest.mark.occt
def test_drawing_carries_bom_table_and_balloons():
    from gitcad.drawing import make_drawing
    from gitcad.drawing.bom import model_bom
    from gitcad.kernel.occt import OcctKernel

    kern = OcctKernel()
    doc = _ladder_doc()
    result = doc.build(kern)
    bom = model_bom(doc, result, kern)
    d = make_drawing(result.final(doc), kern, title="bom-demo", bom=bom)

    svg = d.to_svg()
    assert "ITEM QTY  PART" in svg
    assert "BOX 25×20×1150" in svg
    balloons = [c for c in d.callouts if getattr(c, "balloon", False)]
    assert balloons, "expected balloon callouts on the front view"
    # balloons carry the same item numbers as the table rows
    assert {c.text for c in balloons} <= {str(ln["item"]) for ln in bom}
    assert svg.count("<circle") >= len(balloons)

    # the PDF path must carry the table as well (notes were silently
    # dropped by render_pdf before the BOM landed)
    pdf = d.to_pdf()
    assert b"ITEM QTY  PART" in pdf
