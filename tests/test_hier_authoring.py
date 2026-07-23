"""Hierarchical sheet authoring — SheetEditor.sheet() places subsheet
instances that flatten through the SAME hier_merge engine as the KiCad
importer, so an authored hierarchy and an imported one mean exactly the
same thing. The equivalence test proves it: the same two-channel design
authored here and imported from the KiCad reuse fixture yields an
identical netlist."""

from __future__ import annotations

import pytest

from gitcad.ecad.sheetedit import SheetEditor
from gitcad.errors import GitcadError


def _channel() -> SheetEditor:
    """One resistor: pin 1 wired to hier label IN, pin 2 to local OUT —
    the authored twin of the import fixture's channel.kicad_sch. Sheet
    coordinates are KiCad y-down, so pin 1 (symbol +3.81) is at y-3.81."""
    e = SheetEditor("channel")
    e.place("R1", "resistor", 50, 50)
    e.wire((50, 46.19), (50, 40))
    e.hier_label("IN", 50, 40)
    e.wire((50, 53.81), (50, 58))
    e.label("OUT", 50, 58)
    return e


def _two_channel_system() -> SheetEditor:
    parent = SheetEditor("system")
    ch = _channel().finish()
    parent.sheet("ch_a", ch, 100, 100, 20, 10, pins={"IN": (100, 105)})
    parent.sheet("ch_b", ch, 140, 100, 20, 10, pins={"IN": (140, 105)},
                 ref_map={"R1": "R2"})
    parent.wire((95, 105), (100, 105))
    parent.label("NET_A", 95, 105)
    parent.wire((135, 105), (140, 105))
    parent.label("NET_B", 135, 105)
    return parent


def test_sheet_pin_bridges_parent_wire_to_child_net() -> None:
    parent = _two_channel_system()
    sch = parent.finish()
    assert sorted(c.ref for c in sch.components) == ["R1", "R2"]
    assert sorted(sch.nets["NET_A"]) == ["R1.1"]
    assert sorted(sch.nets["NET_B"]) == ["R2.1"]
    assert sorted(sch.nets["ch_a/OUT"]) == ["R1.2"]
    assert sorted(sch.nets["ch_b/OUT"]) == ["R2.2"]
    assert parent.warnings == []


def test_authored_hierarchy_equals_imported_hierarchy(tmp_path) -> None:
    """The oracle: same design through both paths, identical netlist."""
    from test_sheet_reuse import _write_project

    from gitcad.importers.kicad_sch import import_kicad_sch

    imported, _ = import_kicad_sch(_write_project(tmp_path))
    authored = _two_channel_system().finish()
    assert {n: sorted(refs) for n, refs in authored.nets.items()} == \
           {n: sorted(refs) for n, refs in imported.nets.items()}


def test_reuse_without_ref_map_fails_loud() -> None:
    parent = SheetEditor("system")
    ch = _channel().finish()
    parent.sheet("ch_a", ch, 100, 100, 20, 10, pins={"IN": (100, 105)})
    parent.sheet("ch_b", ch, 140, 100, 20, 10, pins={"IN": (140, 105)})
    with pytest.raises(GitcadError, match="duplicate ref"):
        parent.finish()


def test_global_labels_are_design_wide() -> None:
    child = SheetEditor("psu")
    child.place("C1", "capacitor", 50, 50)
    child.wire((50, 46.19), (50, 40))
    child.hier_label("VIN", 50, 40)
    child.wire((50, 53.81), (50, 58))
    child.global_label("GNDREF", 50, 58)

    parent = SheetEditor("system")
    parent.place("R1", "resistor", 60, 100)
    parent.sheet("psu", child.finish(), 100, 100, 20, 10,
                 pins={"VIN": (100, 105)})
    parent.wire((60, 103.81), (60, 110))
    parent.global_label("GNDREF", 60, 110)
    sch = parent.finish()
    # the child cap's ground pin and the parent resistor pin share one net
    assert sorted(sch.nets["GNDREF"]) == ["C1.2", "R1.2"]


def test_sheet_pin_without_child_hier_label_fails_at_placement() -> None:
    parent = SheetEditor("system")
    with pytest.raises(GitcadError, match="no hierarchical label"):
        parent.sheet("ch", _channel().finish(), 100, 100, 20, 10,
                     pins={"MISSING": (100, 105)})


def test_duplicate_sheet_name_rejected() -> None:
    parent = SheetEditor("system")
    ch = _channel().finish()
    parent.sheet("ch", ch, 100, 100, 20, 10, pins={"IN": (100, 105)})
    with pytest.raises(GitcadError, match="duplicate sheet name"):
        parent.sheet("ch", ch, 140, 100, 20, 10, pins={"IN": (140, 105)})


def test_mcp_schematic_author_sheet_ops() -> None:
    from gitcad.mcp.server import REGISTRY

    channel_ops = [
        ["place", "R1", "resistor", 50, 50],
        ["wire", [[50, 46.19], [50, 40]]],
        ["hier_label", "IN", 50, 40],
        ["wire", [[50, 53.81], [50, 58]]],
        ["label", "OUT", 50, 58],
    ]
    result = REGISTRY["schematic_author"](name="system", ops=[
        ["sheet", "ch_a", 100, 100, 20, 10,
         {"child": "channel", "ops": channel_ops, "pins": {"IN": [100, 105]}}],
        ["sheet", "ch_b", 140, 100, 20, 10,
         {"child": "channel", "ops": channel_ops, "pins": {"IN": [140, 105]},
          "ref_map": {"R1": "R2"}}],
        ["wire", [[95, 105], [100, 105]]],
        ["label", "NET_A", 95, 105],
        ["wire", [[135, 105], [140, 105]]],
        ["label", "NET_B", 135, 105],
    ])
    nets = result["nets"]
    assert sorted(nets["NET_A"]) == ["R1.1"]
    assert sorted(nets["ch_b/OUT"]) == ["R2.2"]
    assert result["parity_ok"] is None                      # per-child by design
    assert "sheet_svg" in result
