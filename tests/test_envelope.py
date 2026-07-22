"""Golden: the hardware type system, electrical v1 (ADR-0015).

Kernel-free. Oracles: a 5V rail on a 3.6V-max pin is an overvoltage error;
a 150 mA regulator feeding 190 mA of loads is an overload; coverage is
reported so green-with-no-specs cannot masquerade as verified.
"""

import pytest

from gitcad.ecad.envelope import check_envelopes, net_voltage, power_budget
from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.errors import GitcadError


@pytest.mark.parametrize("name,volts", [
    ("+3V3", 3.3), ("3V3_IN", 3.3), ("+5V", 5.0), ("+5V_PUMP", 5.0),
    ("12V", 12.0), ("+12V0", 12.0), ("GND", 0.0), ("AGND", 0.0),
    ("VBAT", None), ("SPI_MISO", None),
])
def test_net_voltage_name_contract(name, volts):
    assert net_voltage(name) == volts


def test_net_specs_override_wins():
    assert net_voltage("VBAT", {"VBAT": {"v": 3.7}}) == 3.7


def _sch():
    sch = Schematic(name="typed")
    sch.components = [
        SchComponent(ref="U1", value="LDO", pins=[
            Pin("IN", "1", "power_in"), Pin("OUT", "2", "power_out")],
            attrs={"pin_specs": {"2": {"i_source_ma": 150}}}),
        SchComponent(ref="U2", value="MCU", pins=[Pin("VDD", "1", "power_in")],
                     attrs={"pin_specs": {"1": {"v_abs_max": 3.6, "v_op_min": 2.7,
                                                "i_draw_ma": 80}}}),
        SchComponent(ref="U3", value="SENSOR", pins=[Pin("VDD", "1", "power_in")],
                     attrs={"pin_specs": {"1": {"v_abs_max": 3.6,
                                                "i_draw_ma": 60}}}),
        SchComponent(ref="R1", pins=[Pin("1", "1"), Pin("2", "2")]),  # no specs
    ]
    sch.connect("+3V3", "U1.2", "U2.1", "U3.1", "R1.1")
    return sch


def test_clean_design_passes_with_coverage_reported():
    r = check_envelopes(_sch())
    assert r.ok
    assert r.checks["pins_with_specs"] == 3       # R1 contributed nothing
    assert r.checks["rails"]["+3V3"] == "140.0/150.0ma"


def test_overvoltage_is_a_design_time_type_error():
    sch = _sch()
    # rewire the same loads onto a 5V rail: two abs-max violations
    sch.nets = {"+5V": sch.nets.pop("+3V3")}
    r = check_envelopes(sch)
    assert not r.ok
    assert "pin-overvoltage:+5V:U2.1:5>3.6" in r.violations
    assert "pin-overvoltage:+5V:U3.1:5>3.6" in r.violations


def test_underpowered_pin_flagged():
    sch = _sch()
    sch.net_specs = {"+3V3": {"v": 2.5}}          # sagging rail declared
    r = check_envelopes(sch)
    assert "pin-underpowered:+3V3:U2.1:2.5<2.7" in r.violations


def test_rail_overload_uses_min_source_capacity():
    sch = _sch()
    u3 = next(c for c in sch.components if c.ref == "U3")
    u3.attrs["pin_specs"]["1"]["i_draw_ma"] = 110   # 80 + 110 = 190 > 150
    r = check_envelopes(sch)
    assert "rail-overload:+3V3:draw=190ma>cap=150ma" in r.violations


def test_power_budget_rollup():
    b = power_budget(_sch())
    rail = b["+3V3"]
    assert rail["voltage"] == 3.3
    assert rail["draw_ma"] == 140.0
    assert rail["cap_ma"] == 150
    assert rail["utilization"] == pytest.approx(0.933)
    assert rail["ok"]


def test_power_budget_refuses_zero_data():
    sch = Schematic(name="bare")
    sch.components = [SchComponent(ref="R1", pins=[Pin("1", "1")])]
    sch.connect("N", "R1.1")
    with pytest.raises(GitcadError, match="no pin has electrical specs"):
        power_budget(sch)


def test_net_specs_roundtrip_is_additive():
    sch = _sch()
    plain = sch.dumps()
    assert "net_specs" not in plain               # absent when empty
    sch.net_specs = {"VBAT": {"v": 3.7}}
    again = Schematic.loads(sch.dumps())
    assert again.net_specs == {"VBAT": {"v": 3.7}}
