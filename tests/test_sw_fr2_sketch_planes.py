"""Golden: SW-manual FR2 — sketch planes and the sketch-on-face workflow.

Axis-mapping oracles: extruding a 2x3 rectangle on each principal plane must
land its bounding box on exactly the documented axes (normal x: sketch x->Y,
y->Z, extrude +X). The sketch-on-face workflow is extrude-with-mode against
an input body, verified by exact volume arithmetic.
"""

import pytest

from gitcad.document import Document, Feature
from gitcad.sketch import Profile

RECT_2x3 = Profile.rectangle(2, 3).to_params()


@pytest.fixture(scope="module")
def kern():
    from gitcad.kernel.occt import OcctKernel

    return OcctKernel()


def _final(kern, doc):
    return doc.build(kern).final(doc)


@pytest.mark.occt
def test_sketch_plane_normal_x_maps_axes(kern):
    doc = Document()
    doc.add(Feature(op="extrude", params={
        "profile": RECT_2x3, "height": 4, "plane": {"normal": "x", "offset": 5}}))
    shape = _final(kern, doc)
    lo, hi = kern.bbox(shape)
    assert lo == pytest.approx((5, 0, 0), abs=1e-6)
    assert hi == pytest.approx((9, 2, 3), abs=1e-6)   # sketch x->Y(2), y->Z(3), +X(4)
    assert kern.measure(shape)["volume"] == pytest.approx(24.0, rel=1e-9)


@pytest.mark.occt
def test_sketch_plane_normal_y_maps_axes(kern):
    doc = Document()
    doc.add(Feature(op="extrude", params={
        "profile": RECT_2x3, "height": 4, "plane": {"normal": "y", "offset": -1}}))
    lo, hi = kern.bbox(_final(kern, doc))
    assert lo == pytest.approx((0, -1, 0), abs=1e-6)
    assert hi == pytest.approx((3, 3, 2), abs=1e-6)   # sketch x->Z(2), y->X(3), +Y(4)


@pytest.mark.occt
def test_sketch_plane_z_offset(kern):
    doc = Document()
    doc.add(Feature(op="extrude", params={
        "profile": RECT_2x3, "height": 1, "plane": {"offset": 7}}))
    lo, hi = kern.bbox(_final(kern, doc))
    assert lo[2] == pytest.approx(7.0, abs=1e-6)
    assert hi[2] == pytest.approx(8.0, abs=1e-6)


@pytest.mark.occt
def test_sketch_on_face_cut_and_boss(kern):
    # The sketch-on-face workflow: find the top face (select DSL in real use),
    # sketch on its plane, extrude mode=cut into the body / mode=add out of it.
    doc = Document()
    base = doc.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 10}))
    pocket = Profile.rectangle(4, 4).to_params()
    doc.add(Feature(op="extrude", params={
        "profile": pocket, "height": 3, "mode": "cut",
        "plane": {"offset": 7}}, inputs=[base]))
    shape = _final(kern, doc)
    assert kern.measure(shape)["volume"] == pytest.approx(1000 - 4 * 4 * 3, rel=1e-9)

    doc2 = Document()
    b2 = doc2.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 10}))
    doc2.add(Feature(op="extrude", params={
        "profile": pocket, "height": 5, "mode": "add",
        "plane": {"offset": 10}}, inputs=[b2]))
    shape2 = _final(kern, doc2)
    assert kern.measure(shape2)["volume"] == pytest.approx(1000 + 4 * 4 * 5, rel=1e-9)


@pytest.mark.occt
def test_bad_plane_and_mode_fail_loud(kern):
    from gitcad.errors import GitcadError

    doc = Document()
    doc.add(Feature(op="extrude", params={
        "profile": RECT_2x3, "height": 1, "plane": {"normal": "w"}}))
    with pytest.raises(GitcadError, match="normal must be"):
        doc.build(kern)

    doc2 = Document()
    b = doc2.add(Feature(op="box", params={"dx": 1, "dy": 1, "dz": 1}))
    doc2.add(Feature(op="extrude", params={
        "profile": RECT_2x3, "height": 1, "mode": "subtract"}, inputs=[b]))
    with pytest.raises(GitcadError, match="mode must be"):
        doc2.build(kern)
