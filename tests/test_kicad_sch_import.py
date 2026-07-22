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


def test_no_connect_marker_types_the_pin(sch_and_report):
    # The X marker is design intent: the pin becomes type no_connect so ERC
    # does not flag the designer's deliberate "open" as pin-unconnected.
    sch, _ = sch_and_report
    r1 = next(c for c in sch.components if c.ref == "R1")
    assert r1.pin("2").type == "no_connect"
    assert not any(v.startswith("pin-unconnected:R1.2") for v in sch.erc().violations)


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


# -- sheet-fidelity rendering (the designer's actual drawing) -----------------

def test_importer_attaches_sheet_graphics(sch_and_report):
    sch, _ = sch_and_report
    gfx = sch.graphics
    assert len(gfx["wires"]) == 4          # 3 SIG-chain segments + M wire
    assert gfx["powers"][0]["name"] == "GND"
    assert {lb["name"] for lb in gfx["labels"]} == {"SIG", "M"}
    # graphics are a runtime projection — never serialized into canonical text
    assert "graphics" not in sch.dumps()
    assert "wires" not in sch.dumps()


def test_sheet_to_svg_draws_real_geometry(sch_and_report):
    from gitcad.ecad.schsvg import sheet_to_svg

    sch, _ = sch_and_report
    svg = sheet_to_svg(sch)
    # the SIG wire segment from R1.1 down to the label lane, as drawn
    assert '<line x1="100" y1="96.19" x2="100" y2="90"' in svg
    assert ">SIG</text>" in svg
    assert 'stroke="#008400"' in svg       # KiCad wire green
    assert 'stroke="#840000"' in svg       # maroon pin stubs


def test_sheet_to_svg_refuses_schematic_without_graphics():
    import pytest as _pytest

    from gitcad.ecad.schematic import Schematic
    from gitcad.ecad.schsvg import sheet_to_svg
    from gitcad.errors import GitcadError

    with _pytest.raises(GitcadError, match="no sheet graphics"):
        sheet_to_svg(Schematic(name="born-in-gitcad"))


# -- sheet parity: drawn geometry must equal the declared netlist -------------

def test_imported_sheet_passes_parity(sch_and_report):
    from gitcad.ecad.netderive import sheet_parity

    sch, _ = sch_and_report
    report = sheet_parity(sch)
    assert report.ok, report.violations


def test_moving_a_wire_breaks_parity(sch_and_report):
    from gitcad.ecad.netderive import sheet_parity

    sch, _ = sch_and_report
    # sever the SIG chain: drop the middle wire segment from the drawing
    sch.graphics["wires"] = [w for w in sch.graphics["wires"]
                             if w != [100, 90, 116.19, 90]]
    report = sheet_parity(sch)
    assert not report.ok
    assert any(v.startswith("sheet-net-not-drawn:SIG") for v in report.violations)


def test_parity_requires_sheet_graphics():
    import pytest as _pytest

    from gitcad.ecad.netderive import sheet_parity
    from gitcad.ecad.schematic import Schematic
    from gitcad.errors import GitcadError

    with _pytest.raises(GitcadError, match="no sheet graphics"):
        sheet_parity(Schematic(name="netlist-only"))


# -- multi-board system merge (nets union by name across sheets) --------------

def test_merge_schematics_unions_named_nets():
    from gitcad.ecad.schematic import Pin, SchComponent, Schematic, merge_schematics

    a = Schematic(name="board_a", components=[
        SchComponent(ref="U1", pins=[Pin("SDA", "1", "bidirectional")])])
    a.connect("I2C_SDA", "U1.1")
    a.connect("N$1", "U1.1")
    b = Schematic(name="board_b", components=[
        SchComponent(ref="U2", pins=[Pin("SDA", "3", "bidirectional")])])
    b.connect("I2C_SDA", "U2.3")
    b.connect("N$1", "U2.3")

    sys_sch = merge_schematics("system", [a, b])
    assert sorted(sys_sch.nets["I2C_SDA"]) == ["U1.1", "U2.3"]
    # auto-named nets are sheet-local: never falsely merged
    assert sys_sch.nets["board_a.N$1"] == ["U1.1"]
    assert sys_sch.nets["board_b.N$1"] == ["U2.3"]


def test_merge_schematics_rejects_duplicate_refs():
    import pytest as _pytest

    from gitcad.ecad.schematic import SchComponent, Schematic, merge_schematics
    from gitcad.errors import GitcadError

    a = Schematic(name="a", components=[SchComponent(ref="U1")])
    b = Schematic(name="b", components=[SchComponent(ref="U1")])
    with _pytest.raises(GitcadError, match="duplicate ref"):
        merge_schematics("system", [a, b])
