"""Golden: check waivers (KiCad-map tier 2) — suppression that shows.

Oracles: a reasoned waiver moves matching violations to the visible
waived list (never deletes them); a waiver without a reason refuses to
load; a stale waiver that matches nothing becomes its own violation; the
PCBA gate and the review gate both honor sibling .waivers files.
"""

import pytest

from gitcad.errors import GitcadError
from gitcad.waivers import SCHEMA, load_waivers, waive


def _doc(waivers):
    import json

    return json.dumps({"schema": SCHEMA, "waivers": waivers})


def test_waive_moves_matches_visible_and_keeps_rest():
    kept, waived, unused = waive(
        ["erc:net-single-pin:TP1", "erc:net-single-pin:TP2", "drc:clearance:x"],
        load_waivers(_doc([{"match": "erc:net-single-pin:TP*",
                            "reason": "test points are single-ended"}])))
    assert kept == ["drc:clearance:x"]
    assert [w["violation"] for w in waived] == \
        ["erc:net-single-pin:TP1", "erc:net-single-pin:TP2"]
    assert waived[0]["reason"] == "test points are single-ended"
    assert unused == []


def test_reasonless_waiver_refused():
    with pytest.raises(GitcadError, match="no reason"):
        load_waivers(_doc([{"match": "x", "reason": "  "}]))


def test_stale_waiver_is_reported_unused():
    _kept, _w, unused = waive(["a:b"], load_waivers(
        _doc([{"match": "never:*", "reason": "old fix"}])))
    assert unused == ["never:*"]


def test_pcba_gate_honors_sibling_waivers(tmp_path):
    from gitcad.ecad import Board, Component, Footprint, MountingHole, Pad
    from gitcad.ecad.schematic import Pin, SchComponent, Schematic
    from gitcad.pcba import pcba_verify

    fp = Footprint("R", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                              Pad("2", 0.75, 0, 0.9, 0.95)])
    b = Board(name="w", outline=[(0, 0), (20, 0), (20, 12), (0, 12)])
    b.mounting_holes = [MountingHole("mh1", 2, 2, 2.2)]
    b.components += [Component("R1", fp, x=6, y=6, nets={"1": "VCC", "2": "GND"})]
    (tmp_path / "w.board").write_text(b.dumps(), encoding="utf-8")
    sch = Schematic(name="w")
    sch.components = [SchComponent(ref="R1", pins=[Pin("1", "1"), Pin("2", "2")])]
    sch.connect("VCC", "R1.1")
    sch.connect("GND", "R1.2")
    (tmp_path / "w.sch").write_text(sch.dumps(), encoding="utf-8")
    part = b.to_part("prt_wv_01", schematics=["w.sch"])
    (tmp_path / "w.pcba").write_text(part.dumps(), encoding="utf-8")

    base = pcba_verify((tmp_path / "w.pcba").read_text(encoding="utf-8"),
                       str(tmp_path))
    assert not base["ok"]                             # tiny fixture is red
    (tmp_path / "w.waivers").write_text(_doc(
        [{"match": v, "reason": "fixture noise"} for v in base["violations"]]),
        encoding="utf-8")
    waived = pcba_verify((tmp_path / "w.pcba").read_text(encoding="utf-8"),
                         str(tmp_path))
    assert waived["ok"]                               # green, but...
    assert len(waived["waived"]) == len(base["violations"])   # ...fully visible
