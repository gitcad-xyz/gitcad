"""GOLDEN: sketch profiles + extrude/revolve — the 2D->3D workflow."""

from __future__ import annotations

import math

import pytest

from gitcad.document import Document, Feature
from gitcad.drawing.dxf import profile_to_dxf
from gitcad.errors import GitcadError
from gitcad.sketch import Profile


def test_profile_validation() -> None:
    with pytest.raises(GitcadError, match="not closed"):
        Profile((0, 0)).line_to(10, 0).line_to(10, 10).validate()
    p = Profile((0, 0)).line_to(10, 0).line_to(10, 10).close()
    p.validate()
    # Canonical param round-trip.
    assert Profile.from_params(p.to_params()).to_params() == p.to_params()


def test_dxf_export_of_profile() -> None:
    p = (Profile((0, 0)).line_to(40, 0)
         .arc_to(40, 20, via=(50, 10))
         .line_to(0, 20).close())
    dxf = profile_to_dxf(p)
    assert dxf.startswith("0\nSECTION")
    assert dxf.count("\nLINE\n") == 3 and dxf.count("\nARC\n") == 1
    assert dxf.rstrip().endswith("EOF")
    assert profile_to_dxf(p) == dxf   # deterministic


@pytest.mark.occt
class TestOcct:
    @pytest.fixture(scope="class")
    def kernel(self):
        from gitcad.kernel.occt import OcctKernel

        return OcctKernel()

    def test_extruded_rectangle_matches_box(self, kernel) -> None:
        prof = Profile.rectangle(60, 40).to_params()
        shape = kernel.extrude(prof, 8)
        assert kernel.measure(shape)["volume"] == pytest.approx(60 * 40 * 8, rel=1e-9)
        assert kernel.validate(shape).ok

    def test_l_bracket_extrusion(self, kernel) -> None:
        # L-profile: 50x40 with 8mm legs -> area = 50*8 + (40-8)*8
        prof = Profile.l_shape(50, 40, 8).to_params()
        shape = kernel.extrude(prof, 30)
        expected = (50 * 8 + (40 - 8) * 8) * 30
        assert kernel.measure(shape)["volume"] == pytest.approx(expected, rel=1e-9)

    def test_arc_profile_extrudes(self, kernel) -> None:
        # Rectangle with a semicircular bulge on one edge.
        prof = (Profile((0, 0)).line_to(40, 0).line_to(40, 20)
                .arc_to(0, 20, via=(20, 40)).close().to_params())
        shape = kernel.extrude(prof, 5)
        expected = (40 * 20 + math.pi * 20**2 / 2) * 5
        assert kernel.measure(shape)["volume"] == pytest.approx(expected, rel=1e-6)

    def test_revolve_disc(self, kernel) -> None:
        # Rectangle x in [0,10], height 5, revolved about Y -> cylinder r=10 h=5.
        prof = Profile((0, 0)).line_to(10, 0).line_to(10, 5).line_to(0, 5).close()
        shape = kernel.revolve(prof.to_params(), 360)
        assert kernel.measure(shape)["volume"] == pytest.approx(math.pi * 100 * 5, rel=1e-6)

    def test_document_extrude_op_end_to_end(self, kernel) -> None:
        doc = Document()
        doc.add(Feature(op="extrude", params={
            "profile": Profile.rectangle(30, 20).to_params(), "height": 10}))
        v = kernel.measure(doc.build(kernel).final(doc))["volume"]
        assert v == pytest.approx(6000, rel=1e-9)
        # Round-trips through canonical text like any feature.
        assert Document.loads(doc.dumps()).dumps() == doc.dumps()
