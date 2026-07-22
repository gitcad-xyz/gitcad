"""Golden: board stats, net lengths + matched pairs, back-annotation,
KiCad netlist export (KiCad-map tier 2, part 2). Kernel-free.
"""

import pytest

from gitcad.ecad import Board, Component, Footprint, MountingHole, Pad, Track, Via, Zone
from gitcad.ecad.kicadout import to_kicad_netlist
from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.ecad.stats import board_stats, check_length_match, net_lengths
from gitcad.ecad.sync import back_annotate

FP = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                              Pad("2", 0.75, 0, 0.9, 0.95)])


def _board():
    b = Board(name="s", outline=[(0, 0), (20, 0), (20, 10), (0, 10)])
    b.components += [Component("R1", FP, x=5, y=5, value="10k",
                               nets={"1": "A", "2": "B"}),
                     Component("R2", FP, x=15, y=5, side="bottom")]
    b.tracks += [Track(0, 1, 10, 1, 0.2, "top", "USB_DP"),
                 Track(0, 2, 10, 2, 0.2, "top", "USB_DM"),
                 Track(10, 2, 10, 4, 0.2, "top", "USB_DM")]
    b.vias.append(Via(x=12, y=5, drill=0.3, diameter=0.6))
    b.zones += [Zone(net="GND", layer="top", polygon=[(1, 8), (5, 8), (5, 9)]),
                Zone(net="", layer="top", kind="keepout",
                     polygon=[(15, 8), (18, 8), (18, 9)])]
    b.mounting_holes.append(MountingHole("mh1", 2, 2, 2.2))
    return b


def test_board_stats_counts_everything():
    s = board_stats(_board())
    assert s["area_mm2"] == 200.0
    assert s["components"] == {"total": 2, "top": 1, "bottom": 1}
    assert s["pads"] == {"smd": 4, "through_hole": 0}
    assert s["tracks"] == {"count": 3, "length_mm": 22.0}
    assert s["zones"] == 1 and s["keepouts"] == 1
    assert s["drill_sizes_mm"] == {"0.3": 1, "2.2": 1}


def test_net_lengths_and_matched_pair():
    b = _board()
    lengths = net_lengths(b)
    assert lengths["USB_DP"]["track_mm"] == 10.0
    assert lengths["USB_DM"]["track_mm"] == 12.0
    r = check_length_match(b, [("USB_DP", "USB_DM")], tol_mm=1.0)
    assert not r.ok
    assert r.violations == ["length-mismatch:USB_DP~USB_DM:d=2.000mm>1mm"]
    assert check_length_match(b, [("USB_DP", "USB_DM")], tol_mm=2.5).ok
    r2 = check_length_match(b, [("USB_DP", "GHOST")])
    assert r2.violations == ["length-match-unrouted:GHOST"]


def test_back_annotation_syncs_values_never_invents():
    sch = Schematic(name="s")
    sch.components = [SchComponent(ref="R1", value="4.7k",
                                   pins=[Pin("1", "1"), Pin("2", "2")])]
    report = back_annotate(sch, _board())
    assert report["values_changed"] == {"R1": {"old": "4.7k", "new": "10k"}}
    assert sch.components[0].value == "10k"           # written back
    assert report["board_only_refs"] == ["R2"]        # reported, not invented
    assert not report["ok"]


def test_kicad_netlist_export_round_trips_through_our_parser():
    from gitcad.importers.sexp import find_all, find_one, parse, value_of

    sch = Schematic(name="out")
    sch.components = [
        SchComponent(ref="U1", value="MCU", footprint="QFN-16",
                     pins=[Pin("VDD", "1", "power_in")]),
        SchComponent(ref="R1", value="10k", pins=[Pin("1", "1"), Pin("2", "2")]),
    ]
    sch.connect("+3V3", "U1.1", "R1.1")
    sch.connect("GND", "R1.2")
    text = to_kicad_netlist(sch)
    root = parse(text)
    comps = find_all(find_one(root, "components"), "comp")
    assert [value_of(c, "ref") for c in comps] == ["R1", "U1"]
    assert value_of(comps[1], "footprint") == "QFN-16"
    nets = find_all(find_one(root, "nets"), "net")
    by_name = {value_of(n, "name"): [(value_of(nd, "ref"), value_of(nd, "pin"))
                                     for nd in find_all(n, "node")]
               for n in nets}
    assert by_name["+3V3"] == [("R1", "1"), ("U1", "1")]
    assert by_name["GND"] == [("R1", "2")]
    assert to_kicad_netlist(sch) == text              # deterministic
