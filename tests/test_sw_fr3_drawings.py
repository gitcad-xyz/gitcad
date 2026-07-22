"""Golden: SW-manual FR3 — section views and assembly BOM/balloon drawings.

Section oracle: a box with a through-hole, sectioned on the hole axis, must
produce exactly two closed hatch loops (the material on either side of the
slot), and every hatch segment must stay inside the section bounds. Assembly
oracle: balloons carry the same item numbers as the BOM table rows.
"""

import pytest

from gitcad.document import Document, Feature


@pytest.fixture(scope="module")
def kern():
    from gitcad.kernel.occt import OcctKernel

    return OcctKernel()


@pytest.fixture(scope="module")
def holed_box(kern):
    doc = Document()
    b = doc.add(Feature(op="box", params={"dx": 20, "dy": 10, "dz": 10}))
    doc.add(Feature(op="hole", params={"x": 10, "y": 5, "top_z": 10,
                                       "depth": 10, "diameter": 4}, inputs=[b]))
    return doc.build(kern).final(doc)


@pytest.mark.occt
def test_section_through_hole_yields_two_hatched_loops(kern, holed_box):
    from gitcad.drawing.sections import make_section_drawing

    d = make_section_drawing(holed_box, kern, axis="x", offset=10)
    outline = next(v for v in d.views if v.name == "section-outline")
    hatch = next(v for v in d.views if v.name == "hatch")
    assert len(outline.visible) == 2       # material each side of the slot
    assert len(hatch.visible) > 10
    # every hatch segment stays inside the section outline's bounds
    xs = [x for lp in outline.visible for x, _ in lp]
    ys = [y for lp in outline.visible for _, y in lp]
    for seg in hatch.visible:
        for x, y in seg:
            assert min(xs) - 1e-6 <= x <= max(xs) + 1e-6
            assert min(ys) - 1e-6 <= y <= max(ys) + 1e-6


@pytest.mark.occt
def test_section_svg_renders_and_labels(kern, holed_box):
    from gitcad.drawing.sections import make_section_drawing

    svg = make_section_drawing(holed_box, kern, axis="x", offset=10,
                               title="demo").to_svg()
    assert "SECTION A-A" in svg
    assert svg.count("<polyline") > 20     # view + outline + hatching


@pytest.mark.occt
def test_section_rejects_bad_axis(kern, holed_box):
    from gitcad.drawing.sections import make_section_drawing
    from gitcad.errors import GitcadError

    with pytest.raises(GitcadError, match="axis must be"):
        make_section_drawing(holed_box, kern, axis="q", offset=0)


@pytest.fixture(scope="module")
def demo_assembly(kern):
    from gitcad.derive import model_to_part
    from gitcad.part.assembly import Assembly
    from gitcad.part.bought import bought_part
    from gitcad.part.interface import Interface

    doc = Document()
    doc.add(Feature(op="box", params={"dx": 40, "dy": 30, "dz": 10}))
    plate = model_to_part(doc, kern, part_id="prt_fr3_plate", name="plate")
    iface = Interface()
    iface.envelope = {"dx": 6, "dy": 6, "dz": 12}
    screw = bought_part("91290A115", "McMaster", "prt_fr3_m3", interface=iface)
    asm = Assembly("fr3-asm")
    asm.add("plate", plate)
    asm.add("screw_1", screw, translate=(5, 5, 10))
    asm.add("screw_2", screw, translate=(35, 25, 10))
    return asm, {"plate": doc}


@pytest.mark.occt
def test_assembly_balloons_match_bom_items(kern, demo_assembly):
    from gitcad.drawing.assembly import assembly_drawing

    asm, models = demo_assembly
    d = assembly_drawing(asm, kern, models=models)
    # BOM: item 1 = bought screw (qty 2), item 2 = made plate (qty 1)
    balloon_texts = sorted(c.text for c in d.callouts)
    assert balloon_texts == ["(1)", "(1)", "(2)"]
    table = "\n".join(t for _, _, t in d.notes)
    assert "91290A115 (McMaster)" in table
    assert "plate@0.1.0" in table
    # header + one row per BOM line
    assert len(d.notes) == 3


@pytest.mark.occt
def test_assembly_envelope_fallback_draws_hidden_rects(kern, demo_assembly):
    from gitcad.drawing.assembly import assembly_drawing

    asm, models = demo_assembly
    d = assembly_drawing(asm, kern, models=models)
    top = next(v for v in d.views if v.name == "top")
    # two screw envelopes drawn hidden-style (closed 5-point rectangles)
    rects = [p for p in top.hidden if len(p) == 5 and p[0] == p[-1]]
    assert len(rects) == 2
