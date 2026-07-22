"""GOLDEN: schematic capture + ERC + board parity (feature-map B1).

The blinky circuit as a schematic: power header -> resistor -> LED. ERC
catches the classic electrical mistakes; parity catches schematic/board drift.
"""

from __future__ import annotations

import pytest

from gitcad.ecad import Board, Component, Footprint, Pad, Pin, SchComponent, Schematic, board_parity
from gitcad.errors import GitcadError


def _blinky_schematic() -> Schematic:
    s = Schematic(name="blinky")
    s.components += [
        SchComponent("J1", value="PWR", footprint="HDR-2P-2.54", pins=[
            Pin("VCC", "1", "power_out"), Pin("GND", "2", "power_out")]),
        SchComponent("R1", value="330R", footprint="R0603", pins=[
            Pin("A", "1", "passive"), Pin("B", "2", "passive")]),
        SchComponent("D1", value="RED", footprint="LED0603", pins=[
            Pin("A", "A", "passive"), Pin("K", "K", "passive")]),
    ]
    s.connect("VCC", "J1.1", "R1.1")
    s.connect("LED_A", "R1.2", "D1.A")
    s.connect("GND", "J1.2", "D1.K")
    return s


def test_clean_schematic_passes_erc() -> None:
    r = _blinky_schematic().erc()
    assert r.ok, r.violations


def test_roundtrip_is_canonical() -> None:
    s = _blinky_schematic()
    text = s.dumps()
    assert Schematic.loads(text).dumps() == text


def test_erc_catches_output_conflict() -> None:
    s = _blinky_schematic()
    s.components.append(SchComponent("U1", pins=[Pin("OUT", "1", "output")]))
    s.components.append(SchComponent("U2", pins=[Pin("OUT", "1", "output")]))
    s.connect("BUS", "U1.1", "U2.1")
    r = s.erc()
    assert any(v.startswith("pin-conflict:BUS") for v in r.violations)


def test_erc_catches_undriven_input_and_unconnected_pin() -> None:
    s = _blinky_schematic()
    s.components.append(SchComponent("U1", pins=[
        Pin("IN", "1", "input"), Pin("EN", "2", "input")]))
    s.components.append(SchComponent("U2", pins=[Pin("IN", "1", "input")]))
    s.connect("SIG", "U1.1", "U2.1")   # two inputs, no driver
    r = s.erc()
    assert any(v == "net-undriven:SIG" for v in r.violations)
    assert any(v == "pin-unconnected:U1.2" for v in r.violations)


def test_erc_catches_unpowered_power_in() -> None:
    s = Schematic(name="t")
    s.components += [
        SchComponent("U1", pins=[Pin("VDD", "1", "power_in")]),
        SchComponent("U2", pins=[Pin("VDD", "1", "power_in")]),
    ]
    s.connect("3V3", "U1.1", "U2.1")
    r = s.erc()
    assert any(v == "net-power-unpowered:3V3" for v in r.violations)


def test_no_connect_pin_is_exempt() -> None:
    s = _blinky_schematic()
    s.components.append(SchComponent("U1", pins=[Pin("NC", "1", "no_connect")]))
    assert s.erc().ok


def test_invalid_pin_type_rejected() -> None:
    with pytest.raises(GitcadError):
        Pin("X", "1", "flux_capacitor")


# -- schematic <-> board parity (the ECO check) -------------------------------

def _matching_board() -> Board:
    fp2 = Footprint("HDR-2P-2.54", pads=[Pad("1", 0, -1.27, 1.7, 1.7, "circle", 1.0),
                                         Pad("2", 0, 1.27, 1.7, 1.7, "circle", 1.0)])
    r = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95), Pad("2", 0.75, 0, 0.9, 0.95)])
    led = Footprint("LED0603", pads=[Pad("A", -0.75, 0, 0.9, 0.95), Pad("K", 0.75, 0, 0.9, 0.95)])
    b = Board(name="blinky", outline=[(0, 0), (30, 0), (30, 20), (0, 20)])
    b.components += [
        Component("J1", fp2, x=4, y=10, nets={"1": "VCC", "2": "GND"}),
        Component("R1", r, x=13, y=12, nets={"1": "VCC", "2": "LED_A"}),
        Component("D1", led, x=21, y=12, nets={"A": "LED_A", "K": "GND"}),
    ]
    return b


def test_parity_clean_when_board_matches() -> None:
    r = board_parity(_blinky_schematic(), _matching_board())
    assert r.ok, r.violations


def test_parity_catches_board_drift() -> None:
    board = _matching_board()
    board.components[1].nets["2"] = "GND"      # board edited: R1.2 rerouted to GND
    del board.components[2].nets["A"]          # and D1.A left unconnected
    r = board_parity(_blinky_schematic(), board)
    assert any(v.startswith("net-mismatch:R1.2") for v in r.violations)
    assert any(v.startswith("connection-missing-on-board:D1.A") for v in r.violations)


def test_parity_catches_missing_component() -> None:
    board = _matching_board()
    board.components.pop()                     # D1 never placed
    r = board_parity(_blinky_schematic(), board)
    assert any(v == "component-missing-on-board:D1" for v in r.violations)
