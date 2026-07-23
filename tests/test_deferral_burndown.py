"""The deferral-list burndown: ODB++, GenCAD, schematic PDF, teardrops,
autoroute v1, Altium ASCII import. Each was a documented deferral in the
KiCad feature map; each now ships with the project's verification style —
oracle-shaped output where an oracle exists, check-chain gating where the
result is copper."""

from __future__ import annotations

import pytest

from gitcad.ecad import Board, Component, Footprint, Pad, Track, Via, check_connectivity
from gitcad.ecad.autoroute import autoroute
from gitcad.ecad.drc import run_drc
from gitcad.ecad.gencad import to_gencad
from gitcad.ecad.odb import to_odb
from gitcad.ecad.schpdf import sheet_to_pdf
from gitcad.ecad.teardrop import generate_teardrops
from gitcad.errors import GitcadError


def _board() -> Board:
    fp = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                                  Pad("2", 0.75, 0, 0.9, 0.95)])
    b = Board(name="t", outline=[(0, 0), (30, 0), (30, 20), (0, 20)])
    b.components += [Component("R1", fp, x=6, y=10, nets={"1": "A", "2": "B"}),
                     Component("R2", fp, x=24, y=10, nets={"1": "A", "2": "B"})]
    return b


# -- ODB++ ---------------------------------------------------------------------

def test_odb_tree_structure_and_determinism() -> None:
    b = _board()
    b.tracks.append(Track(6.75, 10, 23.25, 10, 0.3, "top", "B"))
    b.vias.append(Via(15, 5, net="B"))
    tree = to_odb(b)
    for required in ("misc/info", "matrix/matrix", "steps/pcb/profile",
                     "steps/pcb/stephdr", "steps/pcb/layers/top/features",
                     "steps/pcb/layers/bottom/features",
                     "steps/pcb/layers/drill_plated_top-bottom/tools",
                     "steps/pcb/netlists/cadnet/netlist"):
        assert required in tree, required
    assert tree == to_odb(b)                               # deterministic
    feats = tree["steps/pcb/layers/top/features"]
    assert "F 6" in feats            # 4 SMD pads + 1 via pad + 1 track line
    assert "L " in feats and "P " in feats
    cadnet = tree["steps/pcb/netlists/cadnet/netlist"]
    assert "$1 A" in cadnet and "$2 B" in cadnet


def test_odb_span_drills_get_their_own_layers() -> None:
    b = _board()
    b.layers = 4
    b.vias.append(Via(15, 5, drill=0.3, diameter=0.6,
                      layer_from="top", layer_to="in1"))
    tree = to_odb(b)
    assert "steps/pcb/layers/drill_plated_top-in1/features" in tree
    assert "steps/pcb/layers/drill_plated_top-in1/tools" in tree


# -- GenCAD --------------------------------------------------------------------

def test_gencad_sections_and_signals() -> None:
    b = _board()
    b.tracks.append(Track(6.75, 10, 23.25, 10, 0.3, "top", "B"))
    b.vias.append(Via(15, 5, net="B"))
    g = to_gencad(b)
    for section in ("$HEADER", "$BOARD", "$PADS", "$PADSTACKS", "$SHAPES",
                    "$COMPONENTS", "$DEVICES", "$SIGNALS", "$TRACKS", "$ROUTES"):
        assert section in g, section
    assert 'SIGNAL "A"' in g and 'NODE "R1" "1"' in g and 'NODE "R2" "1"' in g
    assert 'ROUTE "B"' in g and "VIA PS" in g
    assert "UNITS INCH" in g
    assert g == to_gencad(b)                               # deterministic


# -- schematic PDF -------------------------------------------------------------

def test_schematic_pdf_from_authored_sheet() -> None:
    from gitcad.ecad.sheetedit import SheetEditor

    e = SheetEditor("pdf-test")
    e.place("R1", "resistor", 50, 50, value="10k")
    e.wire((50, 46.19), (50, 40))
    e.label("SIG", 50, 40)
    pdf = sheet_to_pdf(e.finish())
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"(SIG)" in pdf and b"(R1)" in pdf and b"(10k)" in pdf
    assert pdf == sheet_to_pdf(e.finish())                 # deterministic


def test_schematic_pdf_requires_graphics() -> None:
    from gitcad.ecad import Schematic

    with pytest.raises(GitcadError, match="graphics"):
        sheet_to_pdf(Schematic(name="bare"))


# -- teardrops -----------------------------------------------------------------

def test_teardrops_added_at_track_via_junctions_and_idempotent() -> None:
    b = _board()
    b.tracks.append(Track(6.75, 10, 15, 10, 0.3, "top", "B"))
    b.vias.append(Via(15, 10, net="B"))                    # track ends on via
    added = generate_teardrops(b)
    assert added == 1
    z = b.zones[-1]
    assert z.net == "B" and z.layer == "top" and len(z.polygon) == 4
    assert generate_teardrops(b) == 0                      # idempotent
    assert run_drc(b).ok


def test_teardrop_skipped_when_track_as_wide_as_barrel() -> None:
    b = _board()
    b.tracks.append(Track(6.75, 10, 15, 10, 0.9, "top", "B"))
    b.vias.append(Via(15, 10, drill=0.4, diameter=0.8, net="B"))
    assert generate_teardrops(b) == 0


# -- autoroute -----------------------------------------------------------------

def test_autoroute_connects_net_and_passes_checks() -> None:
    b = _board()
    stats = autoroute(b, "A")
    assert stats["tracks"] >= 1
    conn = check_connectivity(b)
    assert not any("net-unrouted:A" in v for v in conn.violations)
    assert run_drc(b).ok, run_drc(b).violations


def test_autoroute_routes_around_obstacles_with_via_if_needed() -> None:
    b = _board()
    # wall of other-net copper between the two pads, gap-free on top
    for y in range(0, 21):
        b.tracks.append(Track(15, y - 0.5, 15, y + 0.5, 1.0, "top", "WALL"))
    stats = autoroute(b, "A")
    assert stats["vias"] >= 2                              # dives to bottom
    conn = check_connectivity(b)
    assert not any("net-unrouted:A" in v for v in conn.violations)


def test_autoroute_refuses_when_walled_on_all_layers() -> None:
    b = _board()
    for layer in ("top", "bottom"):
        for y in range(0, 21):
            b.tracks.append(Track(15, y - 0.5, 15, y + 0.5, 1.0, layer, "WALL"))
    with pytest.raises(GitcadError, match="autoroute-no-path"):
        autoroute(b, "A")


# -- Altium import -------------------------------------------------------------

_ALTIUM_ASCII = """|RECORD=Board|FILENAME=demo.PcbDoc
|RECORD=Net|ID=0|NAME=VCC
|RECORD=Net|ID=1|NAME=GND
|RECORD=Component|ID=0|X=1000mil|Y=1000mil|ROTATION=0|LAYER=TOP|PATTERN=RES0603|SOURCEDESIGNATOR=R1|COMMENT=10k
|RECORD=Pad|COMPONENT=0|NAME=1|X=970mil|Y=1000mil|XSIZE=35mil|YSIZE=37mil|SHAPE=RECTANGLE|LAYER=TOP|NET=0
|RECORD=Pad|COMPONENT=0|NAME=2|X=1030mil|Y=1000mil|XSIZE=35mil|YSIZE=37mil|SHAPE=RECTANGLE|LAYER=TOP|NET=1
|RECORD=Track|X1=970mil|Y1=1000mil|X2=800mil|Y2=1000mil|WIDTH=10mil|LAYER=TOP|NET=0
|RECORD=Via|X=800mil|Y=1000mil|DIAMETER=32mil|HOLESIZE=16mil|NET=0|STARTLAYER=TOP|ENDLAYER=BOTTOM
|RECORD=Pad|NAME=FREE|X=0mil|Y=0mil|XSIZE=10mil|YSIZE=10mil|SHAPE=ROUND
"""


def test_altium_ascii_import(tmp_path) -> None:
    from gitcad.importers.altium import import_altium_pcb

    p = tmp_path / "demo.PcbDoc"
    p.write_text(_ALTIUM_ASCII)
    board, report = import_altium_pcb(str(p))
    assert [c.ref for c in board.components] == ["R1"]
    comp = board.components[0]
    assert comp.nets == {"1": "VCC", "2": "GND"}
    # 30 mil pad offset = 0.762 mm, footprint-relative
    assert comp.footprint.pads[0].x == pytest.approx(-0.762)
    assert len(board.tracks) == 1 and board.tracks[0].net == "VCC"
    assert len(board.vias) == 1
    assert board.vias[0].kind(board.copper_layers()) == "through"
    assert any("free pads" in d for d in report.dropped)
    assert any("bounding box" in w for w in report.warnings)


def test_altium_binary_refused_with_guidance(tmp_path) -> None:
    from gitcad.importers.altium import import_altium_pcb

    p = tmp_path / "bin.PcbDoc"
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
    with pytest.raises(GitcadError, match="Non-KiCad Board"):
        import_altium_pcb(str(p))
