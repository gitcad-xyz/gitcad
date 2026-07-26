"""Bought (COTS) parts — the MPN-atomic pattern, domain-neutral.

The made-vs-bought axis, not mech-vs-ecad, is what determines identity:
- MADE parts (housing, board): the model is source; identity = name@release.
- BOUGHT parts (screws, standoffs, cells, pumps, ECAD components): identity
  = a concrete manufacturer part number, with catalog/datasheet hash anchors
  and facts-as-properties. Never a parametric generic (antipattern: unties
  the design from what is actually procured).

:func:`bought_part` builds one for any domain; :func:`assembly_bom` rolls an
assembly into procurement lines: bought by MPN, made by name@version.
"""

from __future__ import annotations

import re

from gitcad.errors import GitcadError
from gitcad.part.assembly import Assembly
from gitcad.part.interface import Interface
from gitcad.part.manifest import PartManifest


def bought_part(mpn: str, manufacturer: str, part_id: str, *, domain: str = "mech",
                version: str = "0.1.0", interface: Interface | None = None,
                params: dict | None = None, datasheet: dict | None = None) -> PartManifest:
    if datasheet is not None:
        if "url" not in datasheet or not re.fullmatch(r"[0-9a-f]{64}", datasheet.get("sha256", "")):
            raise GitcadError("datasheet must be {url, sha256[, retrieved]} (sha256 = 64 hex)")
    iface = interface or Interface()
    iface.properties = {"mpn": mpn, "manufacturer": manufacturer, **(params or {})}
    return PartManifest(
        id=part_id, name=mpn, domain=domain, version=version, interface=iface,
        body={"kind": "mpn-part", "mpn": mpn, "manufacturer": manufacturer,
              **({"datasheet": datasheet} if datasheet else {})},
    )


def is_bought(manifest: PartManifest) -> bool:
    return (manifest.body or {}).get("kind", "").startswith("mpn-")


def assembly_bom(assembly: Assembly) -> list[dict]:
    """Procurement lines for an assembly: bought parts grouped by MPN, made
    parts listed by name@version (their identity is the release)."""
    lines: dict[str, dict] = {}
    for name, inst in sorted(assembly.instances.items()):
        m = inst.part
        if is_bought(m):
            key = f"mpn:{m.body['mpn']}"
            line = lines.setdefault(key, {
                "type": "bought", "mpn": m.body["mpn"],
                "manufacturer": m.body.get("manufacturer", ""),
                "instances": [], "qty": 0})
        else:
            key = f"made:{m.id}@{m.version}"
            line = lines.setdefault(key, {
                "type": "made", "name": m.name, "version": m.version,
                "part_id": m.id, "instances": [], "qty": 0})
        line["instances"].append(name)
        line["qty"] += 1
    return sorted(lines.values(), key=lambda x: (x["type"], x.get("mpn", x.get("name", ""))))
