"""GOLDEN: made-vs-bought — the MPN pattern generalized to mechanical."""

from __future__ import annotations

from gitcad.part import (
    Assembly, Frame, Interface, PartManifest, Port,
    assembly_bom, bought_part, is_bought,
)


def _screw() -> PartManifest:
    return bought_part(
        "DIN912-M2.5x8-A2", "Bossard", "prt_00000000000000e1", domain="mech",
        interface=Interface(frames={"head": Frame()},
                            ports={"head": Port("head", "mech.bolt", "head",
                                                {"thread": "M2.5", "length": 8})}),
        params={"material": "A2 stainless", "drive": "hex-2mm", "mass_g": 0.7})


def _housing() -> PartManifest:
    return PartManifest(id="prt_a17a1240054e0001", name="altair-housing",
                        domain="mech", version="0.1.0",
                        body={"model": "housing.gitcad.json"})


def test_bought_part_is_mpn_atomic() -> None:
    s = _screw()
    assert is_bought(s) and not is_bought(_housing())
    assert s.interface.properties["mpn"] == "DIN912-M2.5x8-A2"
    assert s.interface.ports["head"].spec["thread"] == "M2.5"
    assert PartManifest.loads(s.dumps()).dumps() == s.dumps()


def test_assembly_bom_splits_made_and_bought() -> None:
    asm = Assembly("product")
    asm.add("housing", _housing())
    screw = _screw()
    for i in range(4):
        asm.add(f"screw_{i}", screw)
    lines = assembly_bom(asm)
    bought = [x for x in lines if x["type"] == "bought"]
    made = [x for x in lines if x["type"] == "made"]
    assert bought[0]["mpn"] == "DIN912-M2.5x8-A2" and bought[0]["qty"] == 4
    assert made[0]["name"] == "altair-housing" and made[0]["version"] == "0.1.0"
