"""Golden: hierarchical .kicad_sch import — KiCad subsheet semantics.

A parent wire ending on a sheet pin joins the child net named by the
matching hierarchical label (structural bridge); global labels and power
nets are design-wide; child locals are sheet-scoped. Cycles and missing
files degrade to warnings, never crashes.
"""

import pytest

from gitcad.importers.kicad_sch import import_kicad_sch

CHILD = """
(kicad_sch (version 20250114) (generator "test")
  (lib_symbols
    (symbol "Device:R"
      (symbol "R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27) (name "~") (number "1"))
        (pin passive line (at 0 -3.81 90) (length 1.27) (name "~") (number "2"))))
    (symbol "power:GND"
      (symbol "GND_1_1"
        (pin power_in line (at 0 0 270) (length 0) (name "GND") (number "1")))))
  (symbol (lib_id "Device:R") (at 50 50 0)
    (property "Reference" "R2" (at 0 0 0))
    (property "Value" "1k" (at 0 0 0)))
  (hierarchical_label "IN" (at 50 46.19 0))
  (symbol (lib_id "power:GND") (at 50 53.81 0)
    (property "Reference" "#PWR02" (at 0 0 0))
    (property "Value" "GND" (at 0 0 0)))
  (label "TAP" (at 50 46.19 0))
)
"""

PARENT = """
(kicad_sch (version 20250114) (generator "test")
  (lib_symbols
    (symbol "Device:R"
      (symbol "R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27) (name "~") (number "1"))
        (pin passive line (at 0 -3.81 90) (length 1.27) (name "~") (number "2"))))
    (symbol "power:GND"
      (symbol "GND_1_1"
        (pin power_in line (at 0 0 270) (length 0) (name "GND") (number "1")))))
  (symbol (lib_id "Device:R") (at 100 100 0)
    (property "Reference" "R1" (at 0 0 0))
    (property "Value" "10k" (at 0 0 0)))
  (wire (pts (xy 100 96.19) (xy 120 96.19)))
  (symbol (lib_id "power:GND") (at 100 103.81 0)
    (property "Reference" "#PWR01" (at 0 0 0))
    (property "Value" "GND" (at 0 0 0)))
  (sheet (at 120 90) (size 25 15)
    (property "Sheetname" "amp" (at 120 89 0))
    (property "Sheetfile" "child.kicad_sch" (at 120 106 0))
    (pin "IN" input (at 120 96.19 0)))
)
"""


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "parent.kicad_sch").write_text(PARENT, encoding="utf-8")
    (tmp_path / "child.kicad_sch").write_text(CHILD, encoding="utf-8")
    return tmp_path


def test_sheet_pin_bridges_parent_wire_to_child_net(project):
    sch, report = import_kicad_sch(str(project / "parent.kicad_sch"))
    assert report.imported["subsheets"] == 1
    refs = {c.ref for c in sch.components}
    assert refs == {"R1", "R2"}                       # child flattened in
    bridged = next(prs for prs in sch.nets.values()
                   if "R1.1" in prs and "R2.1" in prs)
    assert sorted(bridged) == ["R1.1", "R2.1"]


def test_power_nets_are_design_wide(project):
    sch, _ = import_kicad_sch(str(project / "parent.kicad_sch"))
    assert sorted(sch.nets["GND"]) == ["R1.2", "R2.2"]


def test_child_locals_are_sheet_scoped(project):
    # the child's local label TAP shares the bridged net here, so scoping
    # shows through the NAME preference: parent has no real label, so the
    # bridge takes the hierarchical name amp/IN (locals would be amp/TAP)
    sch, _ = import_kicad_sch(str(project / "parent.kicad_sch"))
    name = next(n for n, prs in sch.nets.items() if "R2.1" in prs)
    assert name in ("amp/IN", "amp/TAP")
    assert name.startswith("amp/")                    # never bare TAP/IN


def test_missing_child_degrades_to_warning(project):
    (project / "child.kicad_sch").unlink()
    sch, report = import_kicad_sch(str(project / "parent.kicad_sch"))
    assert any("missing" in w for w in report.warnings)
    assert {c.ref for c in sch.components} == {"R1"}  # parent still imports


def test_cycle_degrades_to_warning(project):
    # child that includes the parent -> cycle guard trips, no recursion bomb
    (project / "child.kicad_sch").write_text(
        PARENT.replace('"child.kicad_sch"', '"parent.kicad_sch"')
        .replace('"R1"', '"R9"'), encoding="utf-8")
    sch, report = import_kicad_sch(str(project / "parent.kicad_sch"))
    assert any("cycle" in w for w in report.warnings)


def test_parent_graphics_carry_sheet_boxes(project):
    from gitcad.ecad.schsvg import sheet_to_svg

    sch, _ = import_kicad_sch(str(project / "parent.kicad_sch"))
    assert sch.graphics["sheets"][0]["name"] == "amp"
    svg = sheet_to_svg(sch)
    assert ">amp</text>" in svg                       # the subsheet box glyph
