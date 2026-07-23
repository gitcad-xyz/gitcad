"""Golden: IPC-2581C export. Kernel-free.

Conformance was benchmarked against kicad-cli's own IPC-2581 of the real
Altair board (holes 58=58 exact, 19/19 real components identical, nets
0=0 on the netless board, mounting holes represented as drill Holes vs
KiCad's pseudo-components — a modeling choice, not data loss). These
goldens pin the structure on a synthetic 4-layer board.
"""

import xml.etree.ElementTree as ET

from gitcad.ecad import Board, Component, Footprint, MountingHole, Pad, Track, Via, Zone
from gitcad.ecad.ipc2581 import to_ipc2581

NS = "{http://webstds.ipc.org/2581}"

FP = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                              Pad("2", 0.75, 0, 0.9, 0.95)])


def _board():
    b = Board(name="ml", outline=[(0, 0), (30, 0), (30, 20), (0, 20)], layers=4)
    b.components += [Component("R1", FP, x=5, y=5, nets={"1": "VCC", "2": "SIG"})]
    b.tracks += [Track(5, 5, 20, 5, 0.2, "top", "SIG"),
                 Track(5, 10, 20, 10, 0.3, "in1", "VCC")]
    b.vias.append(Via(x=20, y=5, drill=0.3, diameter=0.6, net="SIG"))
    b.zones.append(Zone(net="GND", layer="in2", polygon=[(2, 2), (28, 2), (28, 18)]))
    b.mounting_holes.append(MountingHole("mh1", 2, 18, 2.2))
    return b


def test_wellformed_revision_c_and_namespace():
    root = ET.fromstring(to_ipc2581(_board()))
    assert root.tag == NS + "IPC-2581"
    assert root.get("revision") == "C"


def test_stackup_reflects_four_copper_layers():
    root = ET.fromstring(to_ipc2581(_board()))
    layers = list(root.iter(NS + "StackupLayer"))
    # 4 copper + 3 dielectrics
    assert len(layers) == 7
    copper_refs = [sl.get("layerOrGroupRef") for sl in layers
                   if not sl.get("layerOrGroupRef").startswith("dielectric")]
    assert copper_refs == ["top", "in1", "in2", "bottom"]


def test_features_land_on_their_layers():
    root = ET.fromstring(to_ipc2581(_board()))
    by_layer = {lf.get("layerRef"): lf for lf in root.iter(NS + "LayerFeature")}
    assert set(by_layer) == {"top", "in1", "in2", "bottom", "drill"}
    assert len(list(by_layer["in1"].iter(NS + "Line"))) == 1     # the VCC track
    assert len(list(by_layer["in2"].iter(NS + "Polygon"))) == 1  # the GND zone
    # SMD pads only on top; via pad on every copper layer
    assert len(list(by_layer["top"].iter(NS + "Pad"))) == 3      # 2 SMD + via
    assert len(list(by_layer["in1"].iter(NS + "Pad"))) == 1      # via only


def test_nets_and_bom_and_holes():
    root = ET.fromstring(to_ipc2581(_board()))
    nets = {n.get("name"): [(p.get("componentRef"), p.get("pin"))
                            for p in n.iter(NS + "PinRef")]
            for n in root.iter(NS + "LogicalNet")}
    assert nets == {"VCC": [("R1", "1")], "SIG": [("R1", "2")]}
    holes = list(root.iter(NS + "Hole"))
    assert len(holes) == 2                                        # via + mh1
    statuses = sorted(h.get("platingStatus") for h in holes)
    assert statuses == ["NONPLATED", "VIA"]
    items = list(root.iter(NS + "BomItem"))
    assert len(items) == 1 and items[0].get("quantity") == "1"


def test_deterministic_and_origination_parameter():
    a = to_ipc2581(_board())
    b = to_ipc2581(_board())
    assert a == b
    dated = to_ipc2581(_board(), origination="2026-07-23T00:00:00")
    assert 'origination="2026-07-23T00:00:00"' in dated
    assert 'origination="1970-01-01T00:00:00"' in a               # epoch default
