"""GOLDEN: MPN-atomic components — what you place is what you buy."""

from __future__ import annotations

import pytest

from gitcad.ecad import (
    Footprint, Pad, Pin, SchComponent, Schematic,
    bom, bom_csv, footprint_to_part, mpn_component,
)
from gitcad.part import PartManifest


def _r0603_fp_part() -> PartManifest:
    fp = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                                  Pad("2", 0.75, 0, 0.9, 0.95)], courtyard=(2.4, 1.4))
    return footprint_to_part(fp, "prt_ec0a0000000000a3", "0.1.0")


def test_mpn_component_is_atomic_and_references_shared_footprint() -> None:
    part = mpn_component("RC0603FR-0710KL", "Yageo", _r0603_fp_part(),
                         "prt_00000000000000d1", kind="resistor",
                         params={"value": "10k", "tolerance": "1%", "power": "0.1W"})
    assert part.name == "RC0603FR-0710KL" and part.domain == "ecad.component"
    # Interface inherited from the footprint (pads ARE the interface)...
    assert set(part.interface.ports) == {"pad_1", "pad_2"}
    # ...facts are properties of THIS MPN, not constraints to resolve later.
    assert part.interface.properties["tolerance"] == "1%"
    # Shared asset: dependency on the footprint component, lockfile-pinnable.
    assert part.deps == {"prt_ec0a0000000000a3": "^0.1.0"}
    assert PartManifest.loads(part.dumps()).dumps() == part.dumps()


def _sch() -> Schematic:
    s = Schematic(name="t")
    for i, ref in enumerate(("R1", "R2", "R3"), start=1):
        s.components.append(SchComponent(
            ref, value="10k", footprint="R0603",
            pins=[Pin("1", "1", "passive"), Pin("2", "2", "passive")],
            attrs={"mpn": "RC0603FR-0710KL", "manufacturer": "Yageo"}))
    s.components.append(SchComponent("R9", value="1k", footprint="R0603",
                                     pins=[Pin("1", "1", "passive"),
                                           Pin("2", "2", "passive")]))  # no MPN!
    s.connect("A", "R1.1", "R2.1", "R3.1", "R9.1")
    s.connect("B", "R1.2", "R2.2", "R3.2", "R9.2")
    return s


def test_bom_groups_by_mpn_and_flags_unresolved() -> None:
    lines, report = bom(_sch())
    by_mpn = {x["mpn"]: x for x in lines}
    assert by_mpn["RC0603FR-0710KL"]["qty"] == 3
    assert by_mpn["RC0603FR-0710KL"]["refs"] == ["R1", "R2", "R3"]
    assert "component-missing-mpn:R9" in report.violations
    csv_text = bom_csv(lines)
    assert "RC0603FR-0710KL,Yageo,10k,R0603,3,R1 R2 R3" in csv_text


def test_strict_bom_is_the_release_posture() -> None:
    _, report = bom(_sch(), strict=True)
    assert not report.ok            # unresolved MPN fails a strict BOM
    clean = _sch()
    clean.components[-1].attrs = {"mpn": "RC0603FR-071KL", "manufacturer": "Yageo"}
    _, report2 = bom(clean, strict=True)
    assert report2.ok


def test_attrs_survive_schematic_roundtrip() -> None:
    s = _sch()
    back = Schematic.loads(s.dumps())
    assert back.components[0].attrs["mpn"] == "RC0603FR-0710KL"
    assert back.dumps() == s.dumps()
