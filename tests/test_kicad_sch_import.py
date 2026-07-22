"""Regression: .kicad_sch importer — netlist derived from wire-pin geometry.

The synthetic fixture exercises every transform case the real Altair sheets
proved out (validated pin-group-identical against KiCad's own netlist
exporter): rotation, mirror, chained wires with a T-junction, net labels,
power symbols naming nets, no_connect exclusion, and stacked pins.
"""

import pytest

from gitcad.importers.kicad_sch import import_kicad_sch

FIXTURE = """
(kicad_sch (version 20250114) (generator "test")
  (lib_symbols
    (symbol "Device:R"
      (symbol "R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27)
          (name "~") (number "1"))
        (pin passive line (at 0 -3.81 90) (length 1.27)
          (name "~") (number "2"))))
    (symbol "power:GND"
      (symbol "GND_1_1"
        (pin power_in line (at 0 0 270) (length 0)
          (name "GND") (number "1"))))
    (symbol "Custom:STACK"
      (symbol "STACK_1_1"
        (pin power_in line (at 0 2.54 270) (length 1.27)
          (name "VIN") (number "1"))
        (pin passive line (at 0 2.54 270) (length 1.27)
          (name "VIN") (number "2")))))
  (symbol (lib_id "Device:R") (at 100 100 0)
    (property "Reference" "R1" (at 0 0 0))
    (property "Value" "10k" (at 0 0 0))
    (property "Footprint" "Resistor_SMD:R_0603" (at 0 0 0)))
  (symbol (lib_id "Device:R") (at 120 100 90)
    (property "Reference" "R2" (at 0 0 0))
    (property "Value" "4.7k" (at 0 0 0)))
  (symbol (lib_id "Device:R") (at 140 100 0) (mirror x)
    (property "Reference" "R3" (at 0 0 0))
    (property "Value" "1k" (at 0 0 0)))
  (symbol (lib_id "Custom:STACK") (at 160 100 0)
    (property "Reference" "U1" (at 0 0 0))
    (property "Value" "STACK" (at 0 0 0)))
  (symbol (lib_id "power:GND") (at 123.81 100 0)
    (property "Reference" "#PWR01" (at 0 0 0))
    (property "Value" "GND" (at 0 0 0)))
  (wire (pts (xy 100 96.19) (xy 100 90)))
  (wire (pts (xy 100 90) (xy 116.19 90)))
  (wire (pts (xy 116.19 90) (xy 116.19 100)))
  (label "SIG" (at 100 90 0))
  (wire (pts (xy 140 103.81) (xy 145 103.81)))
  (label "M" (at 145 103.81 0))
  (no_connect (at 100 103.81))
)
"""


@pytest.fixture()
def sch_and_report(tmp_path):
    p = tmp_path / "fixture.kicad_sch"
    p.write_text(FIXTURE, encoding="utf-8")
    return import_kicad_sch(str(p))


def test_components_imported_with_footprint(sch_and_report):
    sch, report = sch_and_report
    refs = {c.ref: c for c in sch.components}
    assert set(refs) == {"R1", "R2", "R3", "U1"}   # power symbol is not a component
    assert refs["R1"].value == "10k"
    assert refs["R1"].footprint == "R_0603"        # library prefix stripped
    assert report.imported["symbols"] == 4
    assert report.imported["power_symbols"] == 1


def test_rotation_and_wire_chain_derive_named_net(sch_and_report):
    sch, _ = sch_and_report
    # R1.1 (rot 0, pin at y-up 3.81 -> sheet 96.19) chains through two wire
    # segments to R2.1 (rot 90 -> pin at x-116.19); the label names the net.
    assert sorted(sch.nets["SIG"]) == ["R1.1", "R2.1"]


def test_power_symbol_names_net_at_pin_point(sch_and_report):
    sch, _ = sch_and_report
    assert sch.nets["GND"] == ["R2.2"]


def test_mirror_x_flips_pin_positions(sch_and_report):
    sch, _ = sch_and_report
    # R3 has (mirror x): pin 1 lands at y+3.81 instead of y-3.81, where the
    # wire to label "M" starts. Wrong mirror handling puts pin 2 there instead.
    assert sch.nets["M"] == ["R3.1"]


def test_no_connect_excludes_pin_from_nets(sch_and_report):
    sch, _ = sch_and_report
    all_pins = {pr for prs in sch.nets.values() for pr in prs}
    assert "R1.2" not in all_pins


def test_stacked_pins_join_one_net(sch_and_report):
    sch, _ = sch_and_report
    # U1 pins 1+2 sit at the same library coordinate (stacked) -> one net.
    stacked = [prs for prs in sch.nets.values() if "U1.1" in prs]
    assert stacked and sorted(stacked[0]) == ["U1.1", "U1.2"]


def test_transform_self_check_reports_full_hit_rate(sch_and_report):
    _, report = sch_and_report
    assert report.imported["wire_end_hit_pct"] == 100
    assert not report.warnings


def test_pin_types_map_into_gitcad_vocabulary(sch_and_report):
    sch, _ = sch_and_report
    u1 = next(c for c in sch.components if c.ref == "U1")
    assert {p.type for p in u1.pins} == {"power_in", "passive"}
