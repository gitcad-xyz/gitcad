"""Schematic capture — text-first, netlist-level (feature-map B1).

A gitcad schematic IS the electrical source of truth: components with typed
pins, and nets connecting pins. The *diagram* — placed symbols, wires on a
sheet — is a rendering of this source (a projection, like drawings are of the
3D model) and lands later; the electrical meaning never depends on it.

ERC here is the pin-type connection matrix — the check that makes "the
schematic compiles" a real, machine-decidable statement:

- conflict detection (output driving output, power outputs shorted)
- undriven inputs, unconnected required pins, unpowered power_in pins
- degenerate nets (single pin), dangling references

Violations follow the ``code:detail`` convention (transmit-safe fingerprints).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError, ValidationReport

# Electrical pin types (KiCad/Altium-conventional vocabulary).
PIN_TYPES = {
    "input", "output", "bidirectional", "tristate", "passive",
    "power_in", "power_out", "open_collector", "no_connect",
}

# Drivers: pin types that can source a net.
_DRIVERS = {"output", "bidirectional", "tristate", "power_out", "open_collector", "passive"}

# Hard conflicts: pin-type pairs that must never share a net (ERC errors).
_CONFLICTS: set[frozenset[str]] = {
    frozenset({"output", "output"}),
    frozenset({"output", "power_out"}),
    frozenset({"power_out", "power_out"}),
}


@dataclass
class Pin:
    name: str                 # logical name, e.g. "VCC", "GPIO3"
    number: str               # package pin/pad number, e.g. "1", "A4"
    type: str = "passive"

    def __post_init__(self) -> None:
        if self.type not in PIN_TYPES:
            raise GitcadError(f"unknown pin type {self.type!r} (want one of {sorted(PIN_TYPES)})")


@dataclass
class SchComponent:
    ref: str                  # designator, e.g. "U1"
    value: str = ""
    footprint: str = ""       # footprint name for board sync
    pins: list[Pin] = field(default_factory=list)

    def pin(self, number: str) -> Pin:
        for p in self.pins:
            if p.number == number:
                return p
        raise GitcadError(f"{self.ref}: no pin {number!r}")


@dataclass
class Schematic:
    """Components + nets. A net is a name -> list of "REF.pin_number" refs."""

    name: str
    components: list[SchComponent] = field(default_factory=list)
    nets: dict[str, list[str]] = field(default_factory=dict)

    SCHEMA = "gitcad/schematic@1"

    # -- canonical text -------------------------------------------------------

    def dumps(self) -> str:
        doc = {"schema": self.SCHEMA, "schematic": {
            "name": self.name,
            "components": [asdict(c) for c in self.components],
            "nets": {k: sorted(v) for k, v in self.nets.items()},
        }}
        return canonical_json(doc, indent=2) + "\n"

    @classmethod
    def loads(cls, text: str) -> "Schematic":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported schematic schema {doc.get('schema')!r}")
        s = doc["schematic"]
        return cls(
            name=s["name"],
            components=[SchComponent(ref=c["ref"], value=c.get("value", ""),
                                     footprint=c.get("footprint", ""),
                                     pins=[Pin(**p) for p in c.get("pins", [])])
                        for c in s.get("components", [])],
            nets={k: list(v) for k, v in s.get("nets", {}).items()},
        )

    # -- helpers --------------------------------------------------------------

    def connect(self, net: str, *pin_refs: str) -> None:
        """Attach "REF.pin_number" refs to a net (created on first use)."""
        self.nets.setdefault(net, []).extend(pin_refs)

    def _resolve(self, pin_ref: str) -> tuple[SchComponent, Pin]:
        if "." not in pin_ref:
            raise GitcadError(f"pin ref {pin_ref!r} must be 'REF.pin_number'")
        ref, number = pin_ref.split(".", 1)
        for c in self.components:
            if c.ref == ref:
                return c, c.pin(number)
        raise GitcadError(f"unknown component ref {ref!r}")

    # -- ERC: the electrical rule check ---------------------------------------

    def erc(self) -> ValidationReport:
        violations: list[str] = []
        refs = [c.ref for c in self.components]
        if len(refs) != len(set(refs)):
            violations.append("duplicate-refs")

        connected: set[str] = set()
        for net, pin_refs in sorted(self.nets.items()):
            types: list[tuple[str, str]] = []   # (pin_ref, type)
            for pr in pin_refs:
                try:
                    _, pin = self._resolve(pr)
                except GitcadError:
                    violations.append(f"net-dangling-ref:{net}:{pr}")
                    continue
                connected.add(pr)
                types.append((pr, pin.type))

            if len(types) == 1:
                violations.append(f"net-single-pin:{net}")
            # Pairwise hard conflicts.
            for i, (ra, ta) in enumerate(types):
                for rb, tb in types[i + 1:]:
                    if frozenset({ta, tb}) in _CONFLICTS:
                        violations.append(f"pin-conflict:{net}:{ra}({ta})<->{rb}({tb})")
            tset = {t for _, t in types}
            if "input" in tset and not (tset & _DRIVERS):
                violations.append(f"net-undriven:{net}")
            if "power_in" in tset and "power_out" not in tset and "passive" not in tset:
                violations.append(f"net-power-unpowered:{net}")

        # Unconnected pins (no_connect type is the explicit opt-out).
        for c in self.components:
            for p in c.pins:
                pr = f"{c.ref}.{p.number}"
                if p.type != "no_connect" and pr not in connected:
                    violations.append(f"pin-unconnected:{pr}")

        return ValidationReport(
            ok=not violations,
            checks={"components": len(self.components), "nets": len(self.nets),
                    "erc": "pin-type-matrix-v1"},
            violations=violations,
        )


def board_parity(schematic: Schematic, board) -> ValidationReport:
    """Schematic <-> board consistency — the ECO check (feature-map B1).

    Compares the schematic's pin->net map against the board components' nets:
    every schematic connection must exist on the board (missing = unfinished
    ECO), every board connection must exist in the schematic (extra = board
    edited without the schematic). Refs are matched by designator.
    """
    violations: list[str] = []

    sch_map: dict[str, str] = {}   # "REF.pin" -> net
    for net, pin_refs in schematic.nets.items():
        for pr in pin_refs:
            sch_map[pr] = net

    board_map: dict[str, str] = {}
    board_refs = set()
    for comp in board.components:
        board_refs.add(comp.ref)
        for pad_name, net in comp.nets.items():
            if net:
                board_map[f"{comp.ref}.{pad_name}"] = net

    sch_refs = {c.ref for c in schematic.components}
    for ref in sorted(sch_refs - board_refs):
        violations.append(f"component-missing-on-board:{ref}")
    for ref in sorted(board_refs - sch_refs):
        violations.append(f"component-missing-in-schematic:{ref}")

    for pr in sorted(set(sch_map) | set(board_map)):
        ref = pr.split(".", 1)[0]
        if ref not in (sch_refs & board_refs):
            continue  # already reported at component level
        s_net, b_net = sch_map.get(pr), board_map.get(pr)
        if s_net and not b_net:
            violations.append(f"connection-missing-on-board:{pr}:{s_net}")
        elif b_net and not s_net:
            violations.append(f"connection-missing-in-schematic:{pr}:{b_net}")
        elif s_net and b_net and s_net != b_net:
            violations.append(f"net-mismatch:{pr}:{s_net}!={b_net}")

    return ValidationReport(
        ok=not violations,
        checks={"schematic_connections": len(sch_map), "board_connections": len(board_map)},
        violations=violations,
    )
