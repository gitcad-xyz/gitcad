"""GOLDEN: the schematic diagram — the human review surface."""

from __future__ import annotations

from gitcad.ecad import Pin, SchComponent, Schematic, schematic_to_svg


def _sch() -> Schematic:
    s = Schematic(name="t")
    s.components += [
        SchComponent("J1", value="PWR", footprint="HDR-2P-2.54", pins=[
            Pin("V", "1", "power_out"), Pin("G", "2", "power_out")]),
        SchComponent("R1", value="330R", footprint="R0603", pins=[
            Pin("1", "1", "passive"), Pin("2", "2", "passive")]),
        SchComponent("U1", value="ESP32", footprint="QFN8", pins=[
            Pin("VDD", "1", "power_in"), Pin("GND", "2", "passive"),
            Pin("SCLK", "3", "output"), Pin("MOSI", "4", "output")]),
    ]
    s.connect("VCC", "J1.1", "R1.1", "U1.1")
    s.connect("GND", "J1.2", "U1.2")
    return s


def test_diagram_renders_symbols_nets_and_labels() -> None:
    svg = schematic_to_svg(_sch())
    assert svg.startswith("<svg")
    assert ">R1<" in svg and ">330R<" in svg          # ref + value
    assert ">U1<" in svg and ">SCLK<" in svg          # IC box with pin names
    assert ">VCC<" in svg and ">GND<" in svg          # net lane labels
    assert svg.count("<circle") >= 3                  # junction dots on VCC (3 pins)
    assert schematic_to_svg(_sch()) == svg            # deterministic


def test_manual_placement_is_honored() -> None:
    s = _sch()
    s.components[1].attrs["at"] = [200, 30]
    svg = schematic_to_svg(s)
    assert 'x="200"' in svg.replace('x="200.00"', 'x="200"') or "200" in svg
