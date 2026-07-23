"""Blind/buried vias — the span (layer_from/layer_to) honored by every
consumer: model/validate, Gerber, Excellon, fab package, DRC, connectivity,
the KiCad importer, IPC-2581 (structure copied from a kicad-cli oracle
export of a 4-layer blind+buried board), and board stats."""

from __future__ import annotations

import json

from gitcad.ecad import Board, Component, Footprint, Pad, Track, Via, check_connectivity
from gitcad.ecad import excellon, gerber
from gitcad.ecad.drc import run_drc
from gitcad.ecad.fab import export_fab
from gitcad.ecad.ipc2581 import to_ipc2581
from gitcad.ecad.stats import board_stats


def _board4(**kw) -> Board:
    return Board(name="bb", outline=[(0, 0), (20, 0), (20, 10), (0, 10)],
                 layers=4, **kw)


# -- model ---------------------------------------------------------------------

def test_default_via_is_through_and_old_text_still_loads() -> None:
    b = _board4()
    b.vias.append(Via(5, 5))
    assert b.vias[0].kind(b.copper_layers()) == "through"
    # a v0.7.x board text has no layer_from/layer_to on vias — must load
    doc = json.loads(b.dumps())
    for v in doc["board"]["vias"]:
        del v["layer_from"], v["layer_to"]
    old = Board.loads(json.dumps(doc))
    assert old.vias[0].layer_from == "top" and old.vias[0].layer_to == "bottom"


def test_span_and_kind_classification() -> None:
    cl = ["top", "in1", "in2", "bottom"]
    assert Via(0, 0).span(cl) == cl
    assert Via(0, 0, layer_from="top", layer_to="in1").kind(cl) == "blind"
    assert Via(0, 0, layer_from="in2", layer_to="bottom").kind(cl) == "blind"
    assert Via(0, 0, layer_from="in1", layer_to="in2").kind(cl) == "buried"
    assert Via(0, 0, layer_from="in1", layer_to="in2").span(cl) == ["in1", "in2"]


def test_validate_rejects_bad_and_inverted_spans() -> None:
    b = _board4()
    b.vias.append(Via(5, 5, layer_from="top", layer_to="in9"))
    b.vias.append(Via(6, 5, layer_from="bottom", layer_to="top"))
    r = b.validate()
    assert "via-bad-layer:0" in r.violations
    assert "via-span-inverted:1" in r.violations
    # a blind span on a 2-layer board names a layer that doesn't exist
    b2 = Board(name="b2", outline=[(0, 0), (10, 0), (10, 10), (0, 10)])
    b2.vias.append(Via(5, 5, layer_from="top", layer_to="in1"))
    assert "via-bad-layer:0" in b2.validate().violations


# -- gerber + excellon ---------------------------------------------------------

def test_gerber_flashes_via_only_on_spanned_layers() -> None:
    b = _board4()
    b.vias.append(Via(5, 5, diameter=0.777, drill=0.333,
                      layer_from="top", layer_to="in1"))
    assert "C,0.777000" in gerber.copper(b, "top")
    assert "C,0.777000" in gerber.copper(b, "in1")
    assert "C,0.777000" not in gerber.copper(b, "in2")
    assert "C,0.777000" not in gerber.copper(b, "bottom")


def test_excellon_separates_span_drills() -> None:
    b = _board4()
    b.vias.append(Via(5, 5, drill=0.4))                                  # through
    b.vias.append(Via(8, 5, drill=0.333, layer_from="top", layer_to="in1"))
    b.vias.append(Via(11, 5, drill=0.333, layer_from="in1", layer_to="in2"))
    through = excellon.drills(b)
    assert "T01C0.400" in through and "C0.333" not in through
    spans = excellon.span_drills(b)
    assert list(spans) == [("top", "in1"), ("in1", "in2")]
    assert "X8.000Y5.000" in spans[("top", "in1")]
    assert "X11.000Y5.000" in spans[("in1", "in2")]
    # all-through boards emit no span files (2-layer output untouched)
    assert excellon.span_drills(Board(name="t", outline=[(0, 0), (1, 0), (1, 1)])) == {}


def test_fab_package_includes_span_drills_and_true_layer_count(tmp_path) -> None:
    b = _board4()
    b.vias.append(Via(5, 5, drill=0.3, diameter=0.6,
                      layer_from="top", layer_to="in1"))
    files = export_fab(b, str(tmp_path))
    assert files["drill_top_in1"].endswith("bb-top-in1.drl")
    manifest = json.loads((tmp_path / "bb-manifest.json").read_text())
    assert manifest["layers"] == 4


# -- drc + connectivity --------------------------------------------------------

def test_drc_clearance_respects_via_span() -> None:
    b = _board4()
    b.tracks.append(Track(4.9, 5, 9, 5, 0.3, "bottom", "B"))
    # blind top->in1 via overlapping the bottom track in XY: no conflict —
    # the barrel never reaches the bottom layer
    b.vias.append(Via(5, 5, net="A", layer_from="top", layer_to="in1"))
    assert not any("via[0]" in v and "clearance" in v
                   for v in run_drc(b).violations)
    b.vias[0] = Via(5, 5, net="A")   # through: now they collide
    assert any("via[0]" in v and "clearance" in v
               for v in run_drc(b).violations)


def test_buried_via_bridges_only_its_span() -> None:
    fp = Footprint("H", pads=[Pad("1", 0, 0, 1.7, 1.7, "circle", 1.0)])
    b = _board4()
    b.components += [Component("J1", fp, x=4, y=5, nets={"1": "N"}),
                     Component("J2", fp, x=16, y=5, nets={"1": "N"})]
    b.tracks += [Track(4, 5, 10, 5, 0.4, "in1", "N"),
                 Track(10, 5, 16, 5, 0.4, "in2", "N")]
    r = check_connectivity(b)
    assert any(v.startswith("net-unrouted:N") for v in r.violations)
    b.vias.append(Via(10, 5, net="N", layer_from="in1", layer_to="in2"))
    assert check_connectivity(b).ok
    # a span that misses both tracks does NOT connect them
    b.vias[0] = Via(10, 5, net="N", layer_from="in2", layer_to="bottom")
    assert any(v.startswith("net-unrouted:N")
               for v in check_connectivity(b).violations)


# -- ipc-2581 (oracle-shaped) --------------------------------------------------

def test_ipc2581_emits_span_drill_layers() -> None:
    b = _board4()
    b.vias.append(Via(5, 5, drill=0.4, net=""))
    b.vias.append(Via(8, 5, drill=0.3, diameter=0.6,
                      layer_from="top", layer_to="in1"))
    b.vias.append(Via(11, 5, drill=0.3, diameter=0.6,
                      layer_from="in1", layer_to="in2"))
    xml = to_ipc2581(b)
    assert ('<Layer name="drill" layerFunction="DRILL" side="ALL" '
            'polarity="POSITIVE"><Span fromLayer="top" toLayer="bottom"/>') in xml
    assert '<Layer name="drill_top_in1"' in xml
    assert '<Span fromLayer="top" toLayer="in1"/>' in xml
    assert '<Span fromLayer="in1" toLayer="in2"/>' in xml
    # holes land in their span's LayerFeature, not the through-drill one
    drill_main = xml.split('<LayerFeature layerRef="drill">')[1].split("</LayerFeature>")[0]
    assert "via0" in drill_main and "via1" not in drill_main
    span_feature = xml.split('<LayerFeature layerRef="drill_top_in1">')[1].split("</LayerFeature>")[0]
    assert "via1" in span_feature and "via2" not in span_feature


def test_ipc2581_via_pads_only_on_spanned_copper() -> None:
    b = _board4()
    b.vias.append(Via(8, 5, drill=0.3, diameter=0.6,
                      layer_from="in1", layer_to="in2"))
    xml = to_ipc2581(b)

    def copper_feature(layer: str) -> str:
        return xml.split(f'<LayerFeature layerRef="{layer}">')[1].split("</LayerFeature>")[0]

    assert 'padUsage="VIA"' in copper_feature("in1")
    assert 'padUsage="VIA"' in copper_feature("in2")
    assert 'padUsage="VIA"' not in copper_feature("top")
    assert 'padUsage="VIA"' not in copper_feature("bottom")


# -- stats ---------------------------------------------------------------------

def test_stats_count_via_kinds() -> None:
    b = _board4()
    b.vias += [Via(5, 5), Via(8, 5, layer_from="top", layer_to="in1"),
               Via(11, 5, layer_from="in1", layer_to="in2")]
    assert board_stats(b)["via_kinds"] == {"through": 1, "blind": 1, "buried": 1}


# -- kicad import --------------------------------------------------------------

_KICAD_4L = """(kicad_pcb (version 20240108) (generator "pcbnew")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (1 "In1.Cu" signal) (2 "In2.Cu" signal)
          (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "") (net 1 "N1")
  (gr_rect (start 100 100) (end 120 120) (layer "Edge.Cuts"))
  (via (at 104 104) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 1))
  (via blind (at 106 102) (size 0.6) (drill 0.3) (layers "F.Cu" "In1.Cu") (net 1))
  (via blind (at 110 102) (size 0.6) (drill 0.3) (layers "In2.Cu" "In1.Cu") (net 1))
)
"""


def test_kicad_import_reads_via_spans(tmp_path) -> None:
    from gitcad.importers.kicad import import_kicad_pcb

    p = tmp_path / "bb.kicad_pcb"
    p.write_text(_KICAD_4L)
    board, report = import_kicad_pcb(str(p))
    cl = board.copper_layers()
    kinds = sorted(v.kind(cl) for v in board.vias)
    assert kinds == ["blind", "buried", "through"]
    # the In2->In1 span is normalized outside-in
    buried = next(v for v in board.vias if v.kind(cl) == "buried")
    assert (buried.layer_from, buried.layer_to) == ("in1", "in2")
    assert report.imported.get("blind_buried_vias") == 2
    assert board.validate().ok


def test_kicad_import_drops_via_outside_stack(tmp_path) -> None:
    from gitcad.importers.kicad import import_kicad_pcb

    bad = _KICAD_4L.replace('(layers "F.Cu" "In1.Cu")', '(layers "F.Cu" "In7.Cu")')
    p = tmp_path / "bad.kicad_pcb"
    p.write_text(bad)
    board, report = import_kicad_pcb(str(p))
    assert len(board.vias) == 2
    assert any("In7.Cu" in d for d in report.dropped)
