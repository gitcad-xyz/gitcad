"""Golden: multi-layer boards. Kernel-free.

Oracles: a 4-layer board names its layers top/in1/in2/bottom; inner
tracks DRC only against copper on their own layer (plus through-vias);
inner Gerbers carry PTH pads and inner tracks but never SMD pads; the
fab package grows .g2/.g3 files; the KiCad importer maps In<k>.Cu.
"""

from gitcad.ecad import Board, Component, Footprint, Pad, Track, Via
from gitcad.ecad.drc import run_drc
from gitcad.ecad.gerber import copper

FP = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                              Pad("2", 0.75, 0, 0.9, 0.95)])
FP_TH = Footprint("HDR", pads=[Pad("1", 0, 0, 1.7, 1.7, "circle", 1.0)])


def _board4():
    b = Board(name="b4", outline=[(0, 0), (30, 0), (30, 20), (0, 20)], layers=4)
    b.components += [Component("R1", FP, x=5, y=5, nets={"1": "A", "2": "B"}),
                     Component("J1", FP_TH, x=25, y=5, nets={"1": "GND"})]
    return b


def test_layer_names():
    assert _board4().copper_layers() == ["top", "in1", "in2", "bottom"]
    assert Board(name="b", outline=[(0, 0), (1, 0), (1, 1)]).copper_layers() == \
        ["top", "bottom"]


def test_validate_accepts_inner_and_rejects_unknown():
    b = _board4()
    b.tracks += [Track(2, 10, 20, 10, 0.2, "in1", "A"),
                 Track(2, 12, 20, 12, 0.2, "in9", "A")]     # no such layer
    v = b.validate().violations
    assert "track-bad-layer:1" in v
    assert "track-bad-layer:0" not in v


def test_inner_layers_clear_each_other_but_not_themselves():
    b = _board4()
    # two overlapping tracks, DIFFERENT nets: same inner layer -> violation
    b.tracks += [Track(2, 10, 20, 10, 0.3, "in1", "A"),
                 Track(2, 10.1, 20, 10.1, 0.3, "in1", "B")]
    assert any(v.startswith("clearance") for v in run_drc(b).violations)
    # same geometry split across in1/in2 -> clean (different planes)
    b2 = _board4()
    b2.tracks += [Track(2, 10, 20, 10, 0.3, "in1", "A"),
                  Track(2, 10.1, 20, 10.1, 0.3, "in2", "B")]
    assert not any(v.startswith("clearance") for v in run_drc(b2).violations)


def test_through_via_touches_all_layers():
    b = _board4()
    b.vias.append(Via(x=10, y=10, drill=0.3, diameter=0.6, net="A"))
    b.tracks.append(Track(10, 10.05, 20, 10.05, 0.3, "in2", "B"))  # near via, diff net
    assert any("via" in v for v in run_drc(b).violations
               if v.startswith("clearance"))


def test_inner_gerber_content():
    b = _board4()
    b.tracks.append(Track(2, 10, 20, 10, 0.3, "in1", "A"))
    g = copper(b, "in1")
    assert "Copper,L2,Inr" in g
    assert g.count("D03*") == 1          # only J1's PTH pad flashes inner
    assert "D01*" in g                   # the inner track draws
    top = copper(b, "top")
    assert top.count("D03*") == 3        # 2 SMD + 1 PTH on the outer layer


def test_fab_package_emits_inner_files(tmp_path):
    from gitcad.ecad.fab import export_fab

    export_fab(_board4(), str(tmp_path))
    names = {p.name for p in tmp_path.iterdir()}
    assert "b4.g2" in names and "b4.g3" in names


def test_kicad_import_maps_inner_layers(tmp_path):
    from gitcad.importers.kicad import import_kicad_pcb

    text = """
(kicad_pcb (version 20240108) (generator "test")
  (layers (0 "F.Cu" signal) (1 "In1.Cu" signal)
          (2 "In2.Cu" signal) (31 "B.Cu" signal))
  (net 0 "") (net 1 "A")
  (gr_line (start 0 0) (end 30 0) (layer "Edge.Cuts"))
  (gr_line (start 30 0) (end 30 20) (layer "Edge.Cuts"))
  (gr_line (start 30 20) (end 0 20) (layer "Edge.Cuts"))
  (gr_line (start 0 20) (end 0 0) (layer "Edge.Cuts"))
  (segment (start 2 10) (end 20 10) (width 0.3) (layer "In1.Cu") (net 1))
)
"""
    p = tmp_path / "ml.kicad_pcb"
    p.write_text(text, encoding="utf-8")
    board, report = import_kicad_pcb(str(p))
    assert board.layers == 4
    assert board.tracks[0].layer == "in1"
    assert report.imported.get("inner_layers") == 2
