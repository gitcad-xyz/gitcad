"""Golden: semantic 3-way merge (ADR-0016) — the file-lock era ends here.

Kernel-free. Behavioral oracles: two branches editing DIFFERENT features
of the same model merge cleanly into a document that loads and contains
both edits; the same feature edited differently is a structured conflict
naming the feature id; a schematic net rename merges (all pins move
together) while the same pin moved to two nets conflicts.
"""

import pytest

from gitcad.document import Document, Feature
from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.merge3 import merge_documents


def _base_model() -> Document:
    doc = Document()
    bid = doc.add(Feature(op="box", params={"dx": 30, "dy": 20, "dz": 10}))
    doc.add(Feature(op="hole", params={"x": 10, "y": 10, "top_z": 10,
                                       "depth": 10, "diameter": 4}, inputs=[bid]))
    return doc


def _texts(mutate_ours, mutate_theirs):
    base = _base_model()
    ours = Document.loads(base.dumps())
    theirs = Document.loads(base.dumps())
    mutate_ours(ours)
    mutate_theirs(theirs)
    return base.dumps(), ours.dumps(), theirs.dumps()


def test_parallel_edits_to_different_features_merge_clean():
    def ours(doc):   # ours: enlarge the hole
        doc.features[1].params["diameter"] = 5
    def theirs(doc):  # theirs: add a fillet on the box
        doc.add(Feature(op="fillet", params={"radius": 1},
                        inputs=[doc.features[0].id]))
    b, o, t = _texts(ours, theirs)
    r = merge_documents(b, o, t)
    assert r["ok"], r["conflicts"]
    merged = Document.loads(r["merged"])          # loads = build-order valid
    ops = [f.op for f in merged.features]
    assert ops.count("fillet") == 1
    hole = next(f for f in merged.features if f.op == "hole")
    assert hole.params["diameter"] == 5           # both edits survived


def test_same_feature_edited_differently_conflicts_by_id():
    def ours(doc):
        doc.features[1].params["diameter"] = 5
    def theirs(doc):
        doc.features[1].params["diameter"] = 6
    b, o, t = _texts(ours, theirs)
    r = merge_documents(b, o, t)
    assert not r["ok"]
    (c,) = r["conflicts"]
    assert c["unit"] == "feature" and c["op"] == "hole"
    assert c["ours"]["params"]["diameter"] == 5
    assert c["theirs"]["params"]["diameter"] == 6


def test_modify_vs_delete_conflicts():
    def ours(doc):
        doc.features[1].params["depth"] = 8
    def theirs(doc):
        doc._features.pop(1)                       # delete the hole
    b, o, t = _texts(ours, theirs)
    r = merge_documents(b, o, t)
    assert not r["ok"]
    assert r["conflicts"][0]["theirs"] is None     # deletion side is explicit


def test_identical_edits_on_both_sides_merge_clean():
    def same(doc):
        doc.features[1].params["diameter"] = 5
    b, o, t = _texts(same, same)
    r = merge_documents(b, o, t)
    assert r["ok"] and r["conflicts"] == []


def test_feature_added_after_deleted_input_conflicts():
    base = _base_model()
    ours = Document.loads(base.dumps())
    theirs = Document.loads(base.dumps())
    # ours: fillet referencing the hole feature; theirs: delete that feature
    ours.add(Feature(op="fillet", params={"radius": 1},
                     inputs=[ours.features[1].id]))
    theirs._features.pop(1)
    r = merge_documents(base.dumps(), ours.dumps(), theirs.dumps())
    assert not r["ok"]                             # dependency cannot resolve


# -- schematics ---------------------------------------------------------------

def _base_sch() -> Schematic:
    sch = Schematic(name="s")
    sch.components = [
        SchComponent(ref="R1", value="10k", pins=[Pin("1", "1"), Pin("2", "2")]),
        SchComponent(ref="C1", value="100nF", pins=[Pin("1", "1"), Pin("2", "2")]),
    ]
    sch.connect("VCC", "R1.1", "C1.1")
    sch.connect("OUT", "R1.2")
    sch.connect("GND", "C1.2")
    return sch


def test_net_rename_merges_while_value_edit_lands():
    base = _base_sch()
    ours = Schematic.loads(base.dumps())
    theirs = Schematic.loads(base.dumps())
    ours.nets["+3V3"] = ours.nets.pop("VCC")       # rename: pins move together
    theirs.components[1].value = "1uF"             # independent edit
    r = merge_documents(base.dumps(), ours.dumps(), theirs.dumps())
    assert r["ok"], r["conflicts"]
    merged = Schematic.loads(r["merged"])
    assert sorted(merged.nets["+3V3"]) == ["C1.1", "R1.1"]
    assert next(c for c in merged.components if c.ref == "C1").value == "1uF"


def test_same_pin_moved_to_two_nets_conflicts():
    base = _base_sch()
    ours = Schematic.loads(base.dumps())
    theirs = Schematic.loads(base.dumps())
    ours.nets["OUT"].remove("R1.2")
    ours.connect("FB", "R1.2")
    theirs.nets["OUT"].remove("R1.2")
    theirs.connect("SENSE", "R1.2")
    r = merge_documents(base.dumps(), ours.dumps(), theirs.dumps())
    assert not r["ok"]
    (c,) = [c for c in r["conflicts"] if c["unit"] == "pin"]
    assert c["pin"] == "R1.2"
    assert {c["ours"], c["theirs"]} == {"FB", "SENSE"}


def test_component_added_on_both_sides_identically_is_clean():
    base = _base_sch()
    ours = Schematic.loads(base.dumps())
    theirs = Schematic.loads(base.dumps())
    for sch in (ours, theirs):
        sch.components.append(SchComponent(ref="R2", value="1k",
                                           pins=[Pin("1", "1"), Pin("2", "2")]))
        sch.connect("OUT", "R2.1")
        sch.connect("GND", "R2.2")
    r = merge_documents(base.dumps(), ours.dumps(), theirs.dumps())
    assert r["ok"], r["conflicts"]


def test_board_one_sided_change_takes_that_side():
    from gitcad.ecad import Board

    b = Board(name="b", outline=[(0, 0), (10, 0), (10, 10), (0, 10)])
    base = b.dumps()
    b2 = Board.loads(base)
    b2.outline = [(0, 0), (20, 0), (20, 10), (0, 10)]
    ours = b2.dumps()
    r = merge_documents(base, ours, base)   # theirs unchanged
    assert r["ok"]
    assert Board.loads(r["merged"]).outline == b2.outline


# -- boards: fine-grained (ADR-0016 upgrade) ----------------------------------

def _base_board():
    from gitcad.ecad import Board, Component, Footprint, MountingHole, Pad, Track

    fp = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                                  Pad("2", 0.75, 0, 0.9, 0.95)])
    b = Board(name="m", outline=[(0, 0), (30, 0), (30, 20), (0, 20)])
    b.components += [Component("R1", fp, x=5, y=5),
                     Component("R2", fp, x=15, y=5)]
    b.tracks.append(Track(0, 1, 10, 1, 0.2, "top", "A"))
    b.mounting_holes.append(MountingHole("mh1", 2, 18, 2.2))
    return b


def test_board_parallel_edits_merge_fine_grained():
    from gitcad.ecad import Board, Track, Via

    base = _base_board()
    ours = Board.loads(base.dumps())
    theirs = Board.loads(base.dumps())
    # ours: move R1 and reroute the track (delete + add = clean)
    ours.components[0].x = 7
    ours.tracks[0] = Track(0, 2, 10, 2, 0.2, "top", "A")
    # theirs: add a via and a new track on net B
    theirs.vias.append(Via(x=20, y=10, drill=0.3, diameter=0.6, net="B"))
    theirs.tracks.append(Track(15, 5, 20, 10, 0.2, "top", "B"))
    r = merge_documents(base.dumps(), ours.dumps(), theirs.dumps())
    assert r["ok"], r["conflicts"]
    merged = Board.loads(r["merged"])
    assert next(c for c in merged.components if c.ref == "R1").x == 7
    assert len(merged.tracks) == 2            # rerouted + added, old gone
    assert len(merged.vias) == 1


def test_board_same_component_moved_differently_conflicts():
    from gitcad.ecad import Board

    base = _base_board()
    ours = Board.loads(base.dumps())
    theirs = Board.loads(base.dumps())
    ours.components[0].x = 7
    theirs.components[0].x = 9
    r = merge_documents(base.dumps(), ours.dumps(), theirs.dumps())
    assert not r["ok"]
    (c,) = r["conflicts"]
    assert c["unit"] == "component" and c["key"] == "R1"
    assert c["ours"]["x"] == 7 and c["theirs"]["x"] == 9


def test_board_outline_both_changed_conflicts():
    from gitcad.ecad import Board

    base = _base_board()
    ours = Board.loads(base.dumps())
    theirs = Board.loads(base.dumps())
    ours.outline = [(0, 0), (40, 0), (40, 20), (0, 20)]
    theirs.outline = [(0, 0), (50, 0), (50, 20), (0, 20)]
    r = merge_documents(base.dumps(), ours.dumps(), theirs.dumps())
    assert not r["ok"]
    assert r["conflicts"][0]["unit"] == "outline"


def test_board_net_classes_merge_by_name():
    from gitcad.ecad import Board

    base = _base_board()
    ours = Board.loads(base.dumps())
    theirs = Board.loads(base.dumps())
    ours.net_classes["power"] = {"nets": ["VCC"], "track_width_min": 0.5}
    theirs.net_classes["spi"] = {"nets": ["SPI_*"], "clearance": 0.2}
    r = merge_documents(base.dumps(), ours.dumps(), theirs.dumps())
    assert r["ok"]
    merged = Board.loads(r["merged"])
    assert set(merged.net_classes) == {"power", "spi"}
