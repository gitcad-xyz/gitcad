"""GOLDEN: chamfer, shell, patterns, counterbore holes — volume oracles."""

from __future__ import annotations

import math

import pytest

from gitcad.document import Document, Feature

pytestmark = pytest.mark.occt


@pytest.fixture(scope="module")
def kernel():
    from gitcad.kernel.occt import OcctKernel

    return OcctKernel()


def test_chamfer_one_edge_volume(kernel) -> None:
    box = kernel.box(10, 10, 10)
    edges = kernel.entities(box, "edge")
    # pick a specific edge by geometry: the vertical edge at (0,0) — a line
    # whose centroid is (0, 0, 5)
    idx = next(i for i, e in enumerate(edges)
               if e["curve"] == "line" and e["centroid"] == [0.0, 0.0, 5.0])
    out = kernel.chamfer(box, [idx], 2.0)
    # 45-degree chamfer removes a triangular prism: (2*2/2) * 10 = 20
    assert kernel.measure(out)["volume"] == pytest.approx(1000 - 20, rel=1e-9)


def test_shell_open_top_box(kernel) -> None:
    box = kernel.box(10, 10, 10)
    faces = kernel.entities(box, "face")
    top = next(i for i, f in enumerate(faces)
               if f["surface"] == "plane" and f["centroid"][2] == pytest.approx(10.0))
    out = kernel.shell(box, [top], 1.0)
    # walls 1mm, open top: cavity = 8 x 8 x 9
    assert kernel.measure(out)["volume"] == pytest.approx(1000 - 8 * 8 * 9, rel=1e-6)
    assert kernel.validate(out).ok


def test_linear_pattern(kernel) -> None:
    doc = Document()
    c = doc.add(Feature(op="cylinder", params={"radius": 2, "height": 5}))
    doc.add(Feature(op="pattern_linear", params={"count": 4, "step": [10, 0, 0]}, inputs=[c]))
    v = kernel.measure(doc.build(kernel).final(doc))["volume"]
    assert v == pytest.approx(4 * math.pi * 4 * 5, rel=1e-6)


def test_circular_pattern(kernel) -> None:
    doc = Document()
    b = doc.add(Feature(op="box", params={"dx": 5, "dy": 2, "dz": 3}))
    m = doc.add(Feature(op="move", params={"translate": [10, -1, 0]}, inputs=[b]))
    doc.add(Feature(op="pattern_circular", params={"count": 6}, inputs=[m]))
    v = kernel.measure(doc.build(kernel).final(doc))["volume"]
    assert v == pytest.approx(6 * 5 * 2 * 3, rel=1e-6)   # no overlap at r=10


def test_counterbore_hole(kernel) -> None:
    doc = Document()
    plate = doc.add(Feature(op="box", params={"dx": 30, "dy": 30, "dz": 10}))
    doc.add(Feature(op="hole", params={
        "x": 15, "y": 15, "top_z": 10, "diameter": 5, "depth": 10,
        "cbore_diameter": 9, "cbore_depth": 4}, inputs=[plate]))
    v = kernel.measure(doc.build(kernel).final(doc))["volume"]
    thru = math.pi * 2.5**2 * 10
    cbore_extra = math.pi * (4.5**2 - 2.5**2) * 4
    assert v == pytest.approx(30 * 30 * 10 - thru - cbore_extra, rel=1e-6)
