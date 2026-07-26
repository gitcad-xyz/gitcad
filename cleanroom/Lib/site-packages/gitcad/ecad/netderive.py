"""Wire-connectivity netlist derivation — the one engine, shared.

This is how KiCad (and every schematic tool) defines electrical meaning:
pins connect where wires touch them, wires connect at shared endpoints and
junctions, labels and power symbols name the nets. The .kicad_sch importer
derives netlists through this engine (validated pin-group-identical against
KiCad's own exporter on the real Altair sheets), and ``sheet_parity`` uses
the SAME engine to check that an edited sheet's drawing still means the
declared netlist — one definition of connectivity, everywhere.

Coordinates are mm floats; coincidence tolerance is 0.01 mm.
"""

from __future__ import annotations

Point = tuple[float, float]


class _DSU:
    def __init__(self) -> None:
        self.p: dict = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def key(x: float, y: float) -> tuple[int, int]:
    """Grid-snap a point to the 0.01 mm coincidence grid."""
    return (round(x * 100), round(y * 100))


def pin_abs(px: float, py: float, sx: float, sy: float, rot: float,
            mirror: str | None = None) -> tuple[float, float]:
    """Symbol-library point (y-up) -> sheet coords (y-down) with rotation and
    mirror — the one transform for pins AND body graphics, shared by the
    .kicad_sch importer and the sheet editor."""
    import math

    x, y = px, -py                      # library y-up -> sheet y-down
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    rad = math.radians(rot)
    rx = x * math.cos(rad) + y * math.sin(rad)
    ry = -x * math.sin(rad) + y * math.cos(rad)
    return (round(sx + rx, 4), round(sy + ry, 4))


def _on_segment(pk, a, b) -> bool:
    (px, py), (ax, ay), (bx, by) = pk, a, b
    if min(ax, bx) - 1 <= px <= max(ax, bx) + 1 and min(ay, by) - 1 <= py <= max(ay, by) + 1:
        cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
        return abs(cross) <= 100  # centi-unit scale
    return False


def derive_nets(
    pins: list[tuple[Point, str, str]],          # (point, "REF.num", pin_type)
    wires: list[tuple[Point, Point]],
    junctions: list[Point],
    net_names: dict[Point, str],                 # label/power point -> net name
    nc_points: set[Point] = frozenset(),         # no-connect markers
) -> dict[str, list[str]]:
    """Nets from geometry. Auto-named nets get ``N$k`` in deterministic order.

    Pins typed ``no_connect`` (or sitting under an nc marker) are excluded —
    a designer's explicit "open" is intent, not connectivity.
    """
    nets, _ = derive_nets_ex(pins, wires, junctions, net_names, nc_points)
    return nets


def derive_nets_ex(
    pins: list[tuple[Point, str, str]],
    wires: list[tuple[Point, Point]],
    junctions: list[Point],
    net_names: dict[Point, str],
    nc_points: set[Point] = frozenset(),
    query_points: tuple[Point, ...] = (),
) -> tuple[dict[str, list[str]], list[str | None]]:
    """derive_nets plus per-query-point net membership — the structural hook
    hierarchical sheets need: a parent wire ending on a sheet pin belongs to
    SOME net even when no component pin touches it (a pinless bridge between
    two subsheets), so query groups materialize as (possibly empty) nets."""
    dsu = _DSU()
    pin_nodes = [(key(*pt), ref, typ) for pt, ref, typ in pins]
    wire_keys = [(key(*a), key(*b)) for a, b in wires]
    name_keys = {key(*pt): name for pt, name in net_names.items()}
    nc_keys = {key(*pt) for pt in nc_points}

    for k, ref, _ in pin_nodes:
        dsu.union(("pt", k), ("pin", ref))
    for a, b in wire_keys:
        dsu.union(("pt", a), ("pt", b))
    for k in name_keys:
        dsu.find(("pt", k))

    query_keys = [key(*pt) for pt in query_points]
    junction_keys = [key(*j) for j in junctions]
    endpoints = ({p for w in wire_keys for p in w}
                 | {k for k, _, _ in pin_nodes}
                 | set(junction_keys) | set(name_keys) | set(query_keys))
    for pk in endpoints:
        for a, b in wire_keys:
            if pk != a and pk != b and _on_segment(pk, a, b):
                dsu.union(("pt", pk), ("pt", a))

    groups: dict = {}
    for k, ref, typ in pin_nodes:
        if typ == "no_connect" or k in nc_keys:
            continue
        groups.setdefault(dsu.find(("pt", k)), []).append(ref)
    for k in query_keys:
        # a query group with no pins still materializes (pinless bridge)
        groups.setdefault(dsu.find(("pt", k)), [])
    named: dict = {}
    for k, name in name_keys.items():
        named.setdefault(dsu.find(("pt", k)), name)

    nets: dict[str, list[str]] = {}
    name_of_gid: dict = {}
    auto = 0
    # Deterministic auto-naming: order groups by their smallest pin ref
    # (pinless query groups sort by their root token, after pin groups).
    def order(kv):
        gid, refs = kv
        return (0, min(refs)) if refs else (1, str(gid))
    for gid, refs in sorted(groups.items(), key=order):
        name = named.get(gid)
        if not name:
            auto += 1
            name = f"N${auto}"
        name_of_gid[gid] = name
        nets.setdefault(name, []).extend(sorted(set(refs)))
    query_net = [name_of_gid.get(dsu.find(("pt", k))) for k in query_keys]
    return nets, query_net


def sheet_parity(sch) -> "ValidationReport":
    """Does the drawn sheet still MEAN the declared netlist?

    Re-derives connectivity from the schematic's sheet graphics (wires,
    junctions, labels, power flags) and per-component pin positions through
    the same engine the importer uses, then diffs pin-groups and net names
    against ``sch.nets``. This is the gate for sheet edits: an agent that
    moves a wire must leave parity green, or it changed the circuit.
    """
    from gitcad.errors import GitcadError, ValidationReport

    gfx = getattr(sch, "graphics", None)
    if not gfx:
        raise GitcadError(
            "schematic has no sheet graphics — parity applies to drawn "
            "sheets (imported or sheet-authored), not netlist-only schematics")
    if gfx.get("sheets"):
        raise GitcadError(
            "hierarchical parent sheet — run parity per child sheet file; "
            "flattened cross-sheet parity is a later stage")

    pins: list[tuple[Point, str, str]] = []
    for comp in sch.components:
        pin_xy = comp.attrs.get("pin_xy", {})
        for p in comp.pins:
            if p.number in pin_xy:
                pins.append((tuple(pin_xy[p.number]), f"{comp.ref}.{p.number}", p.type))
    wires = [((w[0], w[1]), (w[2], w[3])) for w in gfx.get("wires", [])]
    junctions = [tuple(j) for j in gfx.get("junctions", [])]
    net_names: dict[Point, str] = {}
    for lb in gfx.get("labels", []):
        net_names[(lb["x"], lb["y"])] = lb["name"]
    for pw in gfx.get("powers", []):
        net_names[(pw["x"], pw["y"])] = pw["name"]

    derived = derive_nets(pins, wires, junctions, net_names)
    want = {frozenset(refs): name for name, refs in sch.nets.items() if refs}
    got = {frozenset(refs): name for name, refs in derived.items() if refs}

    violations: list[str] = []
    for group in sorted(set(want) - set(got), key=sorted):
        violations.append(f"sheet-net-not-drawn:{want[group]}:{'+'.join(sorted(group))}")
    for group in sorted(set(got) - set(want), key=sorted):
        violations.append(f"sheet-extra-connection:{got[group]}:{'+'.join(sorted(group))}")
    for group in set(want) & set(got):
        wn, gn = want[group], got[group]
        if wn != gn and not (wn.startswith("N$") and gn.startswith("N$")):
            violations.append(f"sheet-net-name-mismatch:{wn}!={gn}")

    return ValidationReport(
        ok=not violations,
        checks={"declared_nets": len(want), "derived_nets": len(got),
                "parity": "wire-geometry-v1"},
        violations=violations)


def wire_end_hit_rate(pins, wires, net_names) -> float | None:
    """Fraction of wire endpoints landing on a known connection point — the
    transform/drawing self-check. None when there are no wires."""
    pin_keys = {key(*pt) for pt, _, _ in pins} | {key(*pt) for pt in net_names}
    wire_keys = [(key(*a), key(*b)) for a, b in wires]
    ends = [p for w in wire_keys for p in w]
    if not ends:
        return None
    hits = sum(1 for p in ends
               if p in pin_keys or sum(q == p for q in ends) > 1
               or any(_on_segment(p, a, b) for a, b in wire_keys if p not in (a, b)))
    return hits / len(ends)


def hier_merge(sch, parent_nets, subsheets, children, query_net,
               gfx_labels, gfx_powers, warnings: list) -> None:
    """Flatten a sheet hierarchy into one netlist — KiCad semantics, shared
    by the .kicad_sch importer and SheetEditor authoring so an authored
    hierarchy and an imported one mean exactly the same thing:

    - a sheet pin joins the parent net at its point to the child net named
      by the matching hierarchical label (structural union, so a parent
      label on the same wire still wins the name);
    - global labels and power nets are design-wide — same name, same net,
      across every sheet;
    - everything else in a child is sheet-scoped: names become
      ``sheetname/NAME`` so locals never collide across sheets.
    Sheet REUSE arrives here with per-instance refs already resolved
    (importer: KiCad instances model; authoring: ``ref_map``); refs that
    STILL collide are a genuine error and fail loud."""
    from gitcad.errors import GitcadError

    uf: dict = {}

    def find(a):
        uf.setdefault(a, a)
        while uf[a] != a:
            uf[a] = uf[uf[a]]
            a = uf[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            uf[rb] = ra

    child_global: list[set] = []
    child_hier: list[set] = []
    for c in children:
        g = getattr(c, "graphics", None) or {}
        child_global.append(
            {lb["name"] for lb in g.get("labels", [])
             if lb.get("kind") == "global_label"}
            | {pw["name"] for pw in g.get("powers", [])})
        child_hier.append({lb["name"] for lb in g.get("labels", [])
                           if lb.get("kind") == "hierarchical_label"})
    global_names = ({lb["name"] for lb in gfx_labels
                     if lb.get("kind") == "global_label"}
                    | {pw["name"] for pw in gfx_powers})
    for gset in child_global:
        global_names |= gset

    # 1) sheet pins bridge parent groups to child hier-label nets
    qi = 0
    for ci, ss in enumerate(subsheets):
        for sp in ss["pins"]:
            pnet = query_net[qi]
            qi += 1
            child = children[ci]
            if child is None:
                continue
            if sp["name"] in child.nets:
                union(("P", pnet), ("C", ci, sp["name"]))
            else:
                warnings.append(
                    f"sheet {ss['name']!r}: pin {sp['name']!r} has no matching "
                    "hierarchical label in the child")
    # 2) global/power names are design-wide
    for n in parent_nets:
        if n in global_names:
            union(("P", n), ("G", n))
    for ci, child in enumerate(children):
        if child is None:
            continue
        for n in child.nets:
            if n in global_names:
                union(("C", ci, n), ("G", n))

    # collect every net node's refs, then name each merged group
    members: dict = {}
    for n, refs in parent_nets.items():
        members.setdefault(find(("P", n)), []).append(("P", None, n, refs))
    for ci, child in enumerate(children):
        if child is None:
            continue
        for n, refs in child.nets.items():
            members.setdefault(find(("C", ci, n)), []).append(("C", ci, n, refs))

    def group_name(items) -> str:
        globals_ = sorted(n for _, _, n, _ in items if n in global_names)
        if globals_:
            return globals_[0]
        parents = [n for kind, _, n, _ in items if kind == "P"]
        real_parent = sorted(n for n in parents if not n.startswith("N$"))
        if real_parent:
            return real_parent[0]
        hier = sorted(f"{subsheets[ci]['name']}/{n}" for kind, ci, n, _ in items
                      if kind == "C" and n in child_hier[ci])
        if hier:
            return hier[0]
        if parents:
            return parents[0]                      # parent auto name
        (kind, ci, n, _), = items[:1]
        return f"{subsheets[ci]['name']}/{n}"      # sheet-scoped child net

    for items in members.values():
        name = group_name(items)
        refs = sorted({r for _, _, _, rs in items for r in rs})
        if refs:
            sch.connect(name, *refs)

    for ci, child in enumerate(children):
        if child is None:
            continue
        have = {c.ref for c in sch.components}
        for comp in child.components:
            if comp.ref in have:
                raise GitcadError(
                    f"duplicate ref {comp.ref!r} across sheets — reused "
                    "sheets need per-instance references (importer: KiCad "
                    "instances blocks; authoring: ref_map)")
            sch.components.append(comp)
