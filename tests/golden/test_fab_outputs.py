"""GOLDEN: fab output contracts — the files a manufacturer actually parses."""

from __future__ import annotations

import pytest

from gitcad.ecad import Board, Component, Footprint, Pad, Track, Via, export_fab
from gitcad.ecad import excellon, gerber
from gitcad.ecad.fab import pick_and_place
from gitcad.errors import GitcadError


def _board() -> Board:
    smd = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                                   Pad("2", 0.75, 0, 0.9, 0.95)], courtyard=(2.4, 1.4))
    tht = Footprint("HDR", pads=[Pad("1", 0, 0, 1.7, 1.7, shape="circle", drill=1.0)])
    b = Board(name="t", outline=[(0, 0), (20, 0), (20, 10), (0, 10)])
    b.components += [
        Component("R1", smd, value="1k", x=10, y=5, nets={"1": "A", "2": "B"}),
        Component("J1", tht, value="pin", x=3, y=5, nets={"1": "A"}),
    ]
    b.tracks.append(Track(3, 5, 9.25, 5, 0.4, "top", "A"))
    b.vias.append(Via(18, 5, drill=0.4, diameter=0.8, net="B"))
    return b


def test_gerber_structure() -> None:
    g = gerber.copper(_board(), "top")
    assert g.startswith("%TF.GenerationSoftware,gitcad")
    assert "%TF.FileFunction,Copper,L1,Top*%" in g
    assert "%FSLAX46Y46*%" in g and "%MOMM*%" in g
    assert g.rstrip().endswith("M02*")
    # R1 pad 1 at x = 10 - 0.75 = 9.25mm → 9250000 in 4.6
    assert "X9250000Y5000000D03*" in g
    # via flash present on copper
    assert "X18000000Y5000000D03*" in g


def test_through_hole_pads_appear_on_both_copper_layers() -> None:
    b = _board()
    top, bottom = gerber.copper(b, "top"), gerber.copper(b, "bottom")
    assert "X3000000Y5000000D03*" in top
    assert "X3000000Y5000000D03*" in bottom
    # SMD pad must NOT appear on the far side
    assert "X9250000Y5000000D03*" not in bottom


def test_mask_openings_are_expanded() -> None:
    g = gerber.mask(_board(), "top")
    assert "%TF.FilePolarity,Negative*%" in g
    # 0.9 + 2*0.05 = 1.0 wide opening
    assert "R,1.000000X1.050000" in g


def test_drill_file_contains_all_plated_holes() -> None:
    d = excellon.drills(_board())
    assert d.startswith("M48")
    assert "METRIC,TZ" in d
    assert "T01C0.400" in d and "T02C1.000" in d
    assert "X3.000Y5.000" in d      # J1 pad
    assert "X18.000Y5.000" in d     # via
    assert d.rstrip().endswith("M30")


def test_pick_and_place_lists_components_sorted() -> None:
    csv_text = pick_and_place(_board())
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("Designator,")
    assert [l.split(",")[0] for l in lines[1:]] == ["J1", "R1"]


def test_export_fab_refuses_invalid_board(tmp_path) -> None:
    b = _board()
    b.components[0].x = 100  # pad outside outline
    assert not b.validate().ok
    with pytest.raises(GitcadError):
        export_fab(b, str(tmp_path))


def test_export_fab_writes_complete_package(tmp_path) -> None:
    files = export_fab(_board(), str(tmp_path))
    assert set(files) == {"copper_top", "copper_bottom", "mask_top", "mask_bottom",
                          "silk_top", "profile", "drill", "pick_and_place", "manifest"}
    for path in files.values():
        assert (tmp_path / path.split("\\")[-1].split("/")[-1]).exists()
