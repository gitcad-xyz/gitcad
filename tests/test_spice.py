"""Golden: sim-as-test v1 — SPICE export + assertion runner.

The exporter is pure text and fully golden-tested (a resistor divider has
one right netlist). The runner needs ngspice and is skipped without it —
but its refusal path (no simulator -> loud error, never a fake green) is
tested everywhere.
"""

import pytest

from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.ecad.spice import _find_ngspice, _spice_value, sim_check, to_spice
from gitcad.errors import GitcadError


@pytest.mark.parametrize("raw,parsed", [
    ("10k", "10k"), ("4.7k", "4.7k"), ("330R", "330"), ("330", "330"),
    ("100nF", "100n"), ("10uF", "10u"), ("1MEG", "1MEG"), ("garbage", None),
])
def test_value_parser(raw, parsed):
    assert _spice_value(raw) == parsed


def _divider():
    sch = Schematic(name="divider")
    sch.components = [
        SchComponent(ref="R1", value="10k", pins=[Pin("1", "1"), Pin("2", "2")]),
        SchComponent(ref="R2", value="10k", pins=[Pin("1", "1"), Pin("2", "2")]),
    ]
    sch.connect("+5V", "R1.1")
    sch.connect("OUT", "R1.2", "R2.1")
    sch.connect("GND", "R2.2")
    return sch


def test_divider_exports_one_right_netlist():
    text, report = to_spice(_divider())
    lines = text.splitlines()
    assert "R1 +5V OUT 10k" in lines
    assert "R2 OUT 0 10k" in lines            # ground net becomes node 0
    assert "VRAIL1 +5V 0 5" in lines          # rail name -> ideal source
    assert lines[-1] == ".end"
    assert report["modeled"] == ["R1", "R2"]
    assert report["unmodeled"] == []


def test_unmodeled_parts_reported_never_dropped():
    sch = _divider()
    sch.components.append(SchComponent(ref="U1", value="OPAMP",
                                       pins=[Pin("1", "1")]))
    sch.connect("OUT", "U1.1")
    _text, report = to_spice(sch)
    assert any(u.startswith("U1") for u in report["unmodeled"])


def test_custom_spice_card_and_model():
    sch = _divider()
    sch.components.append(SchComponent(
        ref="Q1", pins=[Pin("C", "1"), Pin("B", "2"), Pin("E", "3")],
        attrs={"spice": {"card": "{ref} {n1} {n2} {n3} BC846",
                         "model": ".model BC846 NPN(BF=200)"}}))
    sch.connect("OUT", "Q1.1")
    sch.connect("+5V", "Q1.2")
    sch.connect("GND", "Q1.3")
    text, report = to_spice(sch)
    assert "Q1 OUT +5V 0 BC846" in text
    assert ".model BC846 NPN(BF=200)" in text
    assert "Q1" in report["modeled"]


def test_diode_gets_default_model():
    sch = Schematic(name="d")
    sch.components = [SchComponent(ref="D1", pins=[Pin("A", "1"), Pin("K", "2")])]
    sch.connect("+3V3", "D1.1")
    sch.connect("GND", "D1.2")
    text, _ = to_spice(sch)
    assert "D1 +3V3 0 DGEN" in text
    assert ".model DGEN D(" in text


@pytest.mark.skipif(_find_ngspice() is None, reason="ngspice not installed")
def test_divider_midpoint_asserts_2v5():
    r = sim_check(_divider(), [{"node": "OUT", "min": 2.45, "max": 2.55}])
    assert r.ok, r.violations


def test_sim_check_without_ngspice_refuses_loudly():
    if _find_ngspice() is not None:
        pytest.skip("ngspice present — refusal path not reachable")
    with pytest.raises(GitcadError, match="ngspice not found"):
        sim_check(_divider(), [{"node": "OUT", "min": 0}])
