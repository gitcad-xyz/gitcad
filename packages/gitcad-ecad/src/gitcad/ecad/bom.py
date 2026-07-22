"""MPN-atomic components and the BOM (ADR-0010, hardened per design review).

The parametric-generic ("10k 1% 0603, resolve an MPN later") is rejected as
an antipattern: it unties the design from what actually gets soldered, and
substitutions happen silently at procurement. gitcad's rule:

    **Every placeable component is a concrete manufacturer part.**

- :func:`mpn_component` — an atomic ``ecad.component`` registry part: MPN +
  manufacturer + electrical FACTS (value/tolerance/power as properties of
  that MPN, not constraints) + a reference to its footprint component
  (shared asset, content-addressed by part id).
- :func:`bom` — falls straight out of the schematic because refs ARE MPNs;
  components missing an MPN are flagged, and a strict release can refuse.
- Alternates are explicit, versioned documents — substitution is a reviewed
  git change, never a resolver's silent choice.
"""

from __future__ import annotations

import csv
import io

from gitcad.ecad.schematic import Schematic
from gitcad.errors import GitcadError, ValidationReport
from gitcad.part import Interface, PartManifest


def mpn_component(mpn: str, manufacturer: str, footprint_part: PartManifest,
                  part_id: str, version: str = "0.1.0", *,
                  kind: str = "", params: dict | None = None,
                  datasheet: str = "") -> PartManifest:
    """An atomic MPN part. Pads/envelope inherit from the footprint component
    (the shared asset); electrical facts ride as properties."""
    if footprint_part.domain != "ecad.component":
        raise GitcadError("footprint_part must be an ecad.component")
    iface = Interface.from_dict(footprint_part.interface.to_dict())
    iface.properties = {
        "mpn": mpn, "manufacturer": manufacturer, "kind": kind,
        **(params or {}),
        **({"datasheet": datasheet} if datasheet else {}),
    }
    return PartManifest(
        id=part_id, name=mpn, domain="ecad.component", version=version,
        interface=iface,
        deps={footprint_part.id: f"^{footprint_part.version}"},
        body={"kind": "mpn-component", "mpn": mpn, "manufacturer": manufacturer,
              "footprint": footprint_part.id, "footprint_name": footprint_part.name},
    )


def bom(schematic: Schematic, *, strict: bool = False) -> tuple[list[dict], ValidationReport]:
    """BOM lines grouped by MPN. A component's ``attrs`` must carry ``mpn``
    (+ ``manufacturer``); missing MPNs are violations — strict mode makes the
    whole BOM invalid (release-gate posture)."""
    lines: dict[str, dict] = {}
    violations: list[str] = []
    for comp in schematic.components:
        attrs = getattr(comp, "attrs", {}) or {}
        mpn = attrs.get("mpn", "")
        if not mpn:
            violations.append(f"component-missing-mpn:{comp.ref}")
            mpn = f"UNRESOLVED:{comp.value or comp.ref}"
        line = lines.setdefault(mpn, {
            "mpn": mpn, "manufacturer": attrs.get("manufacturer", ""),
            "value": comp.value, "footprint": comp.footprint,
            "refs": [], "qty": 0,
        })
        line["refs"].append(comp.ref)
        line["qty"] += 1
    report = ValidationReport(
        ok=not (violations and strict) and True if not strict else not violations,
        checks={"lines": len(lines), "components": sum(x["qty"] for x in lines.values()),
                "strict": strict},
        violations=violations,
    )
    return sorted(lines.values(), key=lambda x: x["mpn"]), report


def bom_csv(lines: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["MPN", "Manufacturer", "Value", "Footprint", "Qty", "Refs"])
    for x in lines:
        w.writerow([x["mpn"], x["manufacturer"], x["value"], x["footprint"],
                    x["qty"], " ".join(sorted(x["refs"]))])
    return buf.getvalue()
