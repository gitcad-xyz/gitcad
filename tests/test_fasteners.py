"""SW-map P6: the fastener generator — Toolbox as a function.

The proof loop: mounting holes publish mech.bolt ports (ADR-0008); the
generator sizes a bolt from each port's thread spec, places it, MATES it,
and the ordinary assembly validation (type compatibility + positional
coincidence) confirms every screw is exactly where a screw belongs."""

from __future__ import annotations

import pytest

from gitcad.fasteners import bolt_family, bolt_part, generate_fasteners
from gitcad.kernel.null import NullKernel
from gitcad.part import Assembly, Frame, Interface, PartManifest, Port


def _plate(with_thread: bool = True) -> PartManifest:
    spec = {"thread": "M3", "length": 8} if with_thread else {}
    iface = Interface(
        envelope={"origin": [0, 0, 0], "dx": 60, "dy": 40, "dz": 3},
        frames={"mnt_1": Frame(origin=(5, 5, 0)),
                "mnt_2": Frame(origin=(55, 35, 0))},
        ports={"mnt_1": Port(name="mnt_1", type="mech.bolt", frame="mnt_1",
                             spec=dict(spec)),
               "mnt_2": Port(name="mnt_2", type="mech.bolt", frame="mnt_2",
                             spec=dict(spec))},
    )
    return PartManifest(id="prt_plate", name="plate", domain="mech",
                        version="1.0.0", interface=iface)


def test_bolt_family_is_parameters_plus_configurations() -> None:
    fam = bolt_family(3)
    assert "M3x8" in fam.configurations and "M3x25" in fam.configurations
    assert fam.resolved_parameters("M3x12")["L"] == 12
    assert fam.resolved_parameters("M3x12")["head_d"] == pytest.approx(4.5)
    fam.build(NullKernel(), config="M3x8")            # every variant builds


def test_generate_fasteners_populates_and_validates() -> None:
    asm = Assembly("demo")
    asm.add("plate", _plate(), translate=(10, 20, 5))
    result = generate_fasteners(asm)
    assert [a["port"] for a in result["added"]] == ["plate.mnt_1", "plate.mnt_2"]
    assert result["added"][0]["thread"] == "M3"
    # bolts landed at the ports' WORLD positions and the mates prove it
    assert result["added"][0]["position"] == [15, 25, 5]
    r = asm.validate()
    assert r.ok, r.violations
    assert len(asm.mates) == 2


def test_specless_ports_are_reported_not_guessed() -> None:
    asm = Assembly("demo")
    asm.add("plate", _plate(with_thread=False))
    result = generate_fasteners(asm)
    assert result["added"] == []
    assert [s["reason"] for s in result["skipped"]] == ["no-thread-spec"] * 2


def test_already_mated_ports_and_fastener_parts_are_skipped() -> None:
    asm = Assembly("demo")
    asm.add("plate", _plate())
    generate_fasteners(asm)
    again = generate_fasteners(asm)                   # idempotent second pass
    assert again["added"] == []
    assert all(s["reason"] == "already-mated" for s in again["skipped"])


def test_mcp_assembly_fasteners_tool() -> None:
    from gitcad.mcp.server import REGISTRY

    plate = _plate()
    out = REGISTRY["assembly_fasteners"](
        assembly_body={"name": "demo",
                       "instances": {"plate": {"part": "prt_plate",
                                               "translate": [0, 0, 0]}}},
        parts=[plate.dumps()])
    assert out["ok"], out["violations"]
    assert out["bolt_sizes"] == ["M3x8"]
    assert len(out["assembly"]["mates"]) == 2
    assert bolt_part("M3", 8).interface.ports["seat"].type == "mech.bolt"
