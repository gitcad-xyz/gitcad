"""GOLDEN: importers — onboarding existing work with verified fidelity."""

from __future__ import annotations

import textwrap
import zipfile

import pytest

from gitcad.errors import GitcadError

# ---------------------------------------------------------------------------
# KiCad (pure Python)
# ---------------------------------------------------------------------------

KICAD_FIXTURE = textwrap.dedent("""
(kicad_pcb (version 20240108) (generator "pcbnew")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "") (net 1 "VCC") (net 2 "GND")
  (gr_rect (start 100 100) (end 130 120) (layer "Edge.Cuts") (width 0.1))
  (footprint "Resistor_SMD:R_0603"
    (layer "F.Cu")
    (at 113 108 90)
    (property "Reference" "R1" (at 0 0)) (property "Value" "330R" (at 0 0))
    (pad "1" smd roundrect (at -0.75 0) (size 0.9 0.95) (layers "F.Cu") (net 1 "VCC"))
    (pad "2" smd roundrect (at 0.75 0) (size 0.9 0.95) (layers "F.Cu") (net 2 "GND")))
  (footprint "MountingHole:M3"
    (layer "F.Cu") (at 103 117)
    (property "Reference" "H1" (at 0 0))
    (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu")))
  (footprint "Connector:Pin"
    (layer "F.Cu") (at 104 110)
    (fp_text reference "J1" (at 0 0)) (fp_text value "PWR" (at 0 0))
    (pad "1" thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu") (net 1 "VCC")))
  (segment (start 104 110) (end 112.25 108) (width 0.4) (layer "F.Cu") (net 1))
  (via (at 126 110) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 2))
  (zone (net 2) (layer "B.Cu") (polygon (pts (xy 100 100) (xy 130 100) (xy 130 120))))
)
""")


@pytest.fixture
def kicad_file(tmp_path):
    p = tmp_path / "test.kicad_pcb"
    p.write_text(KICAD_FIXTURE, newline="\n")
    return str(p)


def test_kicad_import_maps_the_board(kicad_file) -> None:
    from gitcad.importers.kicad import import_kicad_pcb

    board, report = import_kicad_pcb(kicad_file)
    # Outline: 30x20 normalized to origin.
    assert board.bbox() == (0, 0, 30, 20)
    refs = {c.ref: c for c in board.components}
    assert set(refs) == {"R1", "J1"}
    # R1 at kicad (113,108) -> gitcad (13, 12); rotation negated: -90 -> 270.
    assert (refs["R1"].x, refs["R1"].y, refs["R1"].rot) == (13, 12, 270)
    assert refs["R1"].nets == {"1": "VCC", "2": "GND"}
    assert refs["R1"].value == "330R"
    # v5-style fp_text reference also works; drill preserved.
    assert refs["J1"].footprint.pads[0].drill == 1.0
    # NPTH became a mounting hole at (3, 3).
    assert len(board.mounting_holes) == 1
    mh = board.mounting_holes[0]
    assert (mh.x, mh.y, mh.drill) == (3, 3, 3.2)
    # Track + via with nets.
    assert len(board.tracks) == 1 and board.tracks[0].net == "VCC"
    assert len(board.vias) == 1 and board.vias[0].net == "GND"
    # Zones import as first-class pours now (the real Altair board's routing).
    assert report.imported.get("zones") == 1
    assert board.zones[0].net == "GND" and board.zones[0].layer == "bottom"
    # Imported board passes fab validation and regenerates gerbers.
    board.name = "imported-test"
    assert board.validate().ok, board.validate().violations


def test_kicad_import_inner_copper_on_2layer_stack_drops_honestly(tmp_path) -> None:
    # multi-layer boards import (In<k>.Cu -> in<k>); but a segment on an
    # inner layer the STACK doesn't declare cannot be mapped — reported as
    # dropped, never silently kept or refused wholesale
    from gitcad.importers.kicad import import_kicad_pcb

    text = KICAD_FIXTURE.replace('(segment (start 104 110) (end 112.25 108) (width 0.4) (layer "F.Cu") (net 1))',
                                 '(segment (start 104 110) (end 112.25 108) (width 0.4) (layer "In1.Cu") (net 1))')
    p = tmp_path / "four_layer.kicad_pcb"
    p.write_text(text, newline="\n")
    board, report = import_kicad_pcb(str(p))
    assert board.layers == 2
    assert any("unmapped layer 'In1.Cu'" in d for d in report.dropped)


def test_sexp_parser_handles_quotes_and_numbers() -> None:
    from gitcad.importers.sexp import parse, value_of

    node = parse('(pad "1 \\" odd" smd (at -0.75 0.5) (size 1 2))')
    assert node[1] == '1 " odd'
    at = value_of(node, "at")
    assert at == -0.75


# ---------------------------------------------------------------------------
# STEP + FCStd (need the OCCT kernel)
# ---------------------------------------------------------------------------

@pytest.mark.occt
def test_step_roundtrip_preserves_geometry(tmp_path) -> None:
    from gitcad.importers.step import import_step_file
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    original = k.boolean("cut", k.box(60, 40, 8),
                         k.transform(k.cylinder(3.2, 8), translate=(15, 20, 0)))
    v_original = k.measure(original)["volume"]
    step_path = str(tmp_path / "part.step")
    k.export_step(original, step_path)

    doc, report = import_step_file(step_path, k)
    imported = doc.build(k).final(doc)
    assert k.measure(imported)["volume"] == pytest.approx(v_original, rel=1e-6)
    assert report.imported["solids_or_bodies"] == 1
    assert any("parametric history" in w for w in report.warnings)


@pytest.mark.occt
def test_import_integrity_pin_detects_file_swap(tmp_path) -> None:
    from gitcad.importers.step import import_step_file
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    step_path = str(tmp_path / "part.step")
    k.export_step(k.box(10, 10, 10), step_path)
    doc, _ = import_step_file(step_path, k)
    # Swap the file for different geometry after import.
    k.export_step(k.box(99, 99, 99), step_path)
    with pytest.raises(GitcadError, match="integrity"):
        doc.build(k)


@pytest.mark.occt
def test_fcstd_import_reads_embedded_breps(tmp_path) -> None:
    from gitcad.importers.fcstd import import_fcstd
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    # Fabricate a minimal .FCStd: Document.xml + two .brep objects.
    brep_a, brep_b = str(tmp_path / "a.brep"), str(tmp_path / "b.brep")
    k.export_brep(k.box(10, 10, 10), brep_a)
    k.export_brep(k.transform(k.box(5, 5, 5), translate=(20, 0, 0)), brep_b)
    fcstd = tmp_path / "legacy.FCStd"
    with zipfile.ZipFile(fcstd, "w") as zf:
        zf.writestr("Document.xml",
                    '<Document><Object name="Box"/><Object name="SmallBox"/></Document>')
        zf.write(brep_a, "BoxShape.brep")
        zf.write(brep_b, "SmallBoxShape.brep")

    doc, report = import_fcstd(str(fcstd), k, str(tmp_path / "assets"))
    shape = doc.build(k).final(doc)
    assert k.measure(shape)["volume"] == pytest.approx(1000 + 125, rel=1e-6)
    assert report.imported["objects"] == 2
    assert any("parametric history" in d for d in report.dropped)
    # The document pins a content-addressed artifact that exists.
    import_feature = doc.features[0]
    from pathlib import Path
    assert Path(import_feature.params["file"]).exists()
    assert len(import_feature.params["sha256"]) == 64


def test_solidworks_files_get_actionable_guidance() -> None:
    """SolidWorks can't be parsed natively — the import must return the
    migration path, not a parse error."""
    from gitcad.mcp.server import REGISTRY

    result = REGISTRY["model_import"](path="widget.sldprt")
    assert result["ok"] is False
    assert "sw-batch-export" in result["error"]["message"]
    assert "STEP" in result["error"]["message"]
