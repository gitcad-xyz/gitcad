"""Golden: sheet authoring — drawn geometry IS the netlist source.

Kernel-free. The authored sheet must: derive its netlist through the same
engine as the KiCad importer, pass sheet_parity by construction, pass ERC
when the circuit is complete, and render through the fidelity renderer.
"""

import pytest

from gitcad.ecad.netderive import sheet_parity
from gitcad.ecad.sheetedit import SheetEditor
from gitcad.errors import GitcadError


def _led_driver() -> SheetEditor:
    e = SheetEditor("led-driver")
    e.place("R1", "resistor", 100, 80, value="330R")
    e.place("D1", "led", 100, 100, value="RED")
    e.place("J1", "header", 70, 90, value="PWR", n=2)
    e.connect(("J1", "1"), ("R1", "1"), (85, 61), (100, 61))
    e.connect(("R1", "2"), ("D1", "1"))
    e.connect(("J1", "2"), ("D1", "2"), (85, 115), (100, 115))
    e.junction(100, 115)
    e.wire((100, 115), (100, 118))
    e.power("GND", 100, 118)
    e.label("VIN", 85, 61)
    return e


def test_authored_sheet_derives_netlist_from_geometry():
    sch = _led_driver().finish()
    assert sorted(sch.nets["VIN"]) == ["J1.1", "R1.1"]
    assert sorted(sch.nets["GND"]) == ["D1.2", "J1.2"]
    assert sorted(sch.nets["N$1"]) == ["D1.1", "R1.2"]


def test_authored_sheet_passes_parity_and_erc():
    sch = _led_driver().finish()
    assert sheet_parity(sch).ok
    assert sch.erc().ok, sch.erc().violations


def test_authored_sheet_renders_kicad_style():
    from gitcad.ecad.schsvg import sheet_to_svg

    svg = sheet_to_svg(_led_driver().finish())
    assert 'stroke="#008400"' in svg     # green wires
    assert 'fill="#FFFFC2"' in svg       # cream symbol bodies
    assert ">VIN</text>" in svg


def test_netlist_survives_canonical_roundtrip():
    from gitcad.ecad.schematic import Schematic

    sch = _led_driver().finish()
    again = Schematic.loads(sch.dumps())
    assert again.nets == sch.nets
    # pin positions ride in attrs, so a reloaded sheet still knows them
    r1 = next(c for c in again.components if c.ref == "R1")
    assert "pin_xy" in r1.attrs


def test_rotation_places_pins_correctly():
    e = SheetEditor("rot")
    e.place("R1", "resistor", 50, 50, rot=90)
    # rot 90: lib pin1 (0, 3.81) y-up -> sheet (-3.81 in x)
    assert e.pin_pos("R1", "1") == (46.19, 50)
    assert e.pin_pos("R1", "2") == (53.81, 50)


def test_authoring_errors_fail_loud():
    e = SheetEditor("err")
    e.place("R1", "resistor", 0, 0)
    with pytest.raises(GitcadError, match="duplicate ref"):
        e.place("R1", "resistor", 10, 10)
    with pytest.raises(GitcadError, match="unknown symbol kind"):
        e.place("X1", "flux-capacitor", 0, 0)
    with pytest.raises(GitcadError, match="no pin"):
        e.pin_pos("R1", "9")
    with pytest.raises(GitcadError, match="unknown pin type"):
        e.place("U1", "ic", 0, 0, pin_types={"1": "magic"})


def test_ic_and_header_pin_counts():
    e = SheetEditor("ic")
    e.place("U1", "ic", 100, 100, left=3, right=2,
            pin_types={"1": "input", "4": "output"})
    u1 = e.sch.components[0]
    assert len(u1.pins) == 5
    assert u1.pin("1").type == "input"
    assert u1.pin("4").type == "output"
    # left pins west of the body, right pins east
    assert e.pin_pos("U1", "1")[0] < 100 < e.pin_pos("U1", "4")[0]
