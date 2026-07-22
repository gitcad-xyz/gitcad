"""Eagle schematic importer (KiCad-map tier 2) — XML, netlist-explicit.

Eagle's .sch is XML with the netlist spelled out (<nets><segment><pinref>),
so unlike KiCad no geometric derivation is needed: parts + nets read
directly. Gate/pin naming: Eagle pins are names, not numbers — the pin
NAME becomes both name and number in the imported schematic (Eagle's
model has no separate pad-number at schematic level; the device mapping
carries it, reported as a limitation). Multi-sheet Eagle schematics
merge — nets in Eagle are already file-global per sheet segment list.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.errors import GitcadError
from gitcad.importers.report import ImportReport


def import_eagle_sch(path: str) -> tuple[Schematic, ImportReport]:
    report = ImportReport(source=path, format="eagle_sch")
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise GitcadError(f"not parseable Eagle XML: {exc}") from exc
    root = tree.getroot()
    if root.tag != "eagle":
        raise GitcadError(f"{path!r} is not an Eagle file (root {root.tag!r})")
    sch_node = root.find(".//schematic")
    if sch_node is None:
        raise GitcadError(f"{path!r} has no <schematic> (a .brd file?)")

    sch = Schematic(name=(path.replace("\\", "/").rsplit("/", 1)[-1]
                          .rsplit(".", 1)[0]))

    # parts: ref, value, device/package as footprint hint
    parts = {}
    for part in sch_node.findall(".//parts/part"):
        ref = part.get("name", "?")
        parts[ref] = {"value": part.get("value", "") or part.get("deviceset", ""),
                      "footprint": part.get("device", "")}
    # pins used per part are discovered from the nets (Eagle schematics
    # don't restate the full pin list per part)
    pins_used: dict[str, set[str]] = {r: set() for r in parts}

    net_pins: dict[str, list[str]] = {}
    for net in sch_node.findall(".//nets/net"):
        name = net.get("name", "")
        prs = []
        for pinref in net.findall(".//segment/pinref"):
            ref = pinref.get("part", "")
            pin = pinref.get("pin", "")
            if ref not in parts:
                report.warnings.append(f"net {name!r}: unknown part {ref!r}")
                continue
            pins_used.setdefault(ref, set()).add(pin)
            prs.append(f"{ref}.{pin}")
        if prs:
            net_pins[name] = sorted(set(prs))
        report.count("labels", 1)

    for ref, meta in sorted(parts.items()):
        comp_pins = [Pin(p, p) for p in sorted(pins_used.get(ref, set()))]
        sch.components.append(SchComponent(
            ref=ref, value=meta["value"], footprint=meta["footprint"],
            pins=comp_pins, attrs={"eagle": True}))
        report.count("symbols", 1)
    for name, prs in sorted(net_pins.items()):
        sch.connect(name, *prs)
    report.count("nets", len(sch.nets))
    report.dropped.append(
        "Eagle sheet drawings (wires/frames) — netlist-only import; pin "
        "numbers are Eagle pin NAMES (device pad mapping not resolved)")
    return sch, report
