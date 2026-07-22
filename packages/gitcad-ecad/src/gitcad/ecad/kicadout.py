"""KiCad netlist EXPORT (kicadsexpr) — the interop OUT path.

``to_kicad_netlist`` writes the same format ``kicad-cli sch export
netlist`` produces, so a gitcad schematic can drive KiCad's pcbnew (or
any tool in that ecosystem): author in gitcad, lay out anywhere.
Deterministic: components and nets sorted, net codes stable.
"""

from __future__ import annotations

from gitcad.ecad.schematic import Schematic


def _q(s: str) -> str:
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def to_kicad_netlist(sch: Schematic) -> str:
    lines = ["(export (version \"E\")",
             "  (design",
             f"    (source {_q(sch.name)})",
             "    (tool \"gitcad\"))",
             "  (components"]
    for c in sorted(sch.components, key=lambda c: c.ref):
        lines.append(f"    (comp (ref {_q(c.ref)})")
        lines.append(f"      (value {_q(c.value or '~')})")
        if c.footprint:
            lines.append(f"      (footprint {_q(c.footprint)})")
        lines.append("    )")
    lines.append("  )")
    lines.append("  (nets")
    for code, (net, pin_refs) in enumerate(sorted(sch.nets.items()), start=1):
        lines.append(f"    (net (code \"{code}\") (name {_q(net)})")
        for pr in sorted(pin_refs):
            ref, pin = pr.split(".", 1)
            lines.append(f"      (node (ref {_q(ref)}) (pin {_q(pin)}))")
        lines.append("    )")
    lines.append("  )")
    lines.append(")")
    return "\n".join(lines) + "\n"
