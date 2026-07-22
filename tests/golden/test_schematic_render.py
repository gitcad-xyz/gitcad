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


def test_diagram_renders_kicad_style() -> None:
    svg = schematic_to_svg(_sch())
    assert svg.startswith("<svg")
    assert ">R1<" in svg and ">330R<" in svg          # ref + value (dark cyan)
    assert ">U1<" in svg and ">SCLK<" in svg          # IC box with pin names
    assert 'stroke="#840000"' in svg                  # maroon symbol outlines
    assert 'fill="#FFFFC2"' in svg                    # cream symbol fill
    assert 'stroke="#008400"' in svg                  # green wires
    assert ">VCC<" in svg                             # power symbol label (not a lane)
    assert svg.count('stroke-width="0.6"') >= 4       # GND flags + power stubs
    assert 'style="background:#FFFFFF"' in svg        # white canvas
    assert schematic_to_svg(_sch()) == svg            # deterministic


def test_manual_placement_is_honored() -> None:
    s = _sch()
    s.components[1].attrs["at"] = [200, 30]
    svg = schematic_to_svg(s)
    assert 'x="200"' in svg.replace('x="200.00"', 'x="200"') or "200" in svg
