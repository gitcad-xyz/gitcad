"""schematic_annotate — deterministic reference numbering (KiCad-map P4).

Components with placeholder refs (``R?``, ``U?`` — the KiCad convention)
get the lowest free number for their prefix, in a deterministic order:
sheet position (top-to-bottom, then left-to-right) when placements exist,
declaration order otherwise. Existing numbered refs are never touched —
annotation fills gaps, it does not reshuffle a reviewed design. Net pin
references follow the renames atomically.
"""

from __future__ import annotations

import re

from gitcad.ecad.schematic import Schematic
from gitcad.errors import GitcadError

_REF = re.compile(r"^([A-Za-z_]+)(\?|\d+)$")


def annotate(sch: Schematic) -> dict[str, str]:
    """Assign numbers to ``?`` refs in place; returns {old_label: new_ref}
    keyed by a positional label (``R?@2`` for the third placeholder R).

    Nets may not reference placeholders — ``R?.1`` is ambiguous when two
    unannotated Rs exist, so we refuse rather than guess: annotate first,
    then connect (or connect by final refs)."""
    for net, prs in sch.nets.items():
        for pr in prs:
            if "?" in pr.split(".", 1)[0]:
                raise GitcadError(
                    f"net {net!r} references placeholder ref {pr!r} — "
                    "annotate before connecting, or connect by the final ref")
    used: dict[str, set[int]] = {}
    placeholders = []
    decl_counter: dict[str, int] = {}
    for i, comp in enumerate(sch.components):
        m = _REF.match(comp.ref)
        if not m:
            raise GitcadError(f"unparseable ref {comp.ref!r} (want PREFIX+number or PREFIX?)")
        prefix, num = m.groups()
        if num == "?":
            at = comp.attrs.get("at")
            sort_key = (at[1], at[0], i) if at else (float("inf"), float("inf"), i)
            k = decl_counter.get(prefix, 0)          # label by DECLARATION order
            decl_counter[prefix] = k + 1
            placeholders.append((prefix, sort_key, f"{prefix}?@{k}", comp))
        else:
            used.setdefault(prefix, set()).add(int(num))

    renames: dict[str, str] = {}
    counters: dict[str, int] = {}
    # numbering order is READING order (top-to-bottom, left-to-right)
    for prefix, _key, label, comp in sorted(placeholders, key=lambda p: (p[0], p[1])):
        n = counters.get(prefix, 1)
        taken = used.setdefault(prefix, set())
        while n in taken:
            n += 1
        taken.add(n)
        counters[prefix] = n + 1
        renames[label] = f"{prefix}{n}"
        comp.ref = f"{prefix}{n}"
    return renames
