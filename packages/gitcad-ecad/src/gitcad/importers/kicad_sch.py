"""KiCad .kicad_sch importer — the gateway to schematic-first designs.

Real projects keep their netlist in the schematic (the human source); this
importer derives it the way KiCad itself does — **geometrically**: pins
connect where wires touch them, wires connect at shared endpoints and
junctions, labels and power symbols name the nets.

Coordinate quirk handled: symbol-library pin coordinates are y-UP while the
sheet is y-DOWN — pin absolute position = symbol_at + R(rot)·(px, -py),
with mirror applied. The import self-checks: it reports the fraction of
wire endpoints that land on a known connection point, so a transform bug
shows up as a number, not silent wrong nets.

v1 scope (honest): flat sheets (hierarchical (sheet ...) reported as
dropped), buses reported as dropped, single unit-1 symbols.
"""

from __future__ import annotations

import math

from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.errors import GitcadError
from gitcad.importers.report import ImportReport
from gitcad.importers.sexp import find_all, find_one, parse, value_of

_TYPE_MAP = {
    "input": "input", "output": "output", "bidirectional": "bidirectional",
    "tri_state": "tristate", "passive": "passive", "free": "passive",
    "unspecified": "passive", "power_in": "power_in", "power_out": "power_out",
    "open_collector": "open_collector", "open_emitter": "open_collector",
    "no_connect": "no_connect",
}


def _lib_symbols(lib_symbols) -> dict[str, dict]:
    """lib_id -> {"pins": [...], "shapes": [...]} in library coords (y-up).

    Shapes are the symbol body graphics (rectangles, polylines, circles,
    arcs) plus pin stubs — enough to reproduce KiCad's drawing of the
    symbol, not just its connectivity."""
    out: dict[str, dict] = {}
    for sym in find_all(lib_symbols or [], "symbol"):
        lib_id = sym[1]
        pins: list[dict] = []
        shapes: list[dict] = []
        for unit in find_all(sym, "symbol"):          # sub-units R_0_1, R_1_1...
            for pin in find_all(unit, "pin"):
                at = find_one(pin, "at") or ["at", 0, 0, 0]
                pins.append({
                    "number": str(value_of(pin, "number", default="")),
                    "name": str(value_of(pin, "name", default="~")),
                    "type": _TYPE_MAP.get(pin[1] if len(pin) > 1 and isinstance(pin[1], str) else "passive", "passive"),
                    "x": float(at[1]), "y": float(at[2]),
                    "angle": float(at[3]) if len(at) > 3 else 0.0,
                    "len": float(value_of(pin, "length", default=0.0) or 0.0),
                })
            for r in find_all(unit, "rectangle"):
                s, e = find_one(r, "start"), find_one(r, "end")
                if s and e:
                    shapes.append({"kind": "rect",
                                   "pts": [[float(s[1]), float(s[2])],
                                           [float(e[1]), float(e[2])]]})
            for pl in find_all(unit, "polyline"):
                pts = find_one(pl, "pts")
                if pts:
                    shapes.append({"kind": "poly",
                                   "pts": [[float(xy[1]), float(xy[2])]
                                           for xy in find_all(pts, "xy")]})
            for c in find_all(unit, "circle"):
                ctr = find_one(c, "center")
                if ctr:
                    shapes.append({"kind": "circle",
                                   "pts": [[float(ctr[1]), float(ctr[2])]],
                                   "r": float(value_of(c, "radius", default=0.5) or 0.5)})
            for a in find_all(unit, "arc"):
                s, m, e = find_one(a, "start"), find_one(a, "mid"), find_one(a, "end")
                if s and m and e:
                    shapes.append({"kind": "arc",
                                   "pts": [[float(s[1]), float(s[2])],
                                           [float(m[1]), float(m[2])],
                                           [float(e[1]), float(e[2])]]})
        out[lib_id] = {"pins": pins, "shapes": shapes}
    return out


def _pin_abs(px: float, py: float, sx: float, sy: float, rot: float,
             mirror: str | None) -> tuple[float, float]:
    """Library pin (y-up) -> sheet coords (y-down) with rotation + mirror."""
    x, y = px, -py                      # library y-up -> sheet y-down
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    rad = math.radians(rot)
    rx = x * math.cos(rad) + y * math.sin(rad)
    ry = -x * math.sin(rad) + y * math.cos(rad)
    return (round(sx + rx, 4), round(sy + ry, 4))


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


def _key(x: float, y: float) -> tuple[int, int]:
    return (round(x * 100), round(y * 100))


def import_kicad_sch(path: str) -> tuple[Schematic, ImportReport]:
    report = ImportReport(source=path, format="kicad_sch")
    with open(path, encoding="utf-8") as f:
        root = parse(f.read())
    if not (isinstance(root, list) and root and root[0] == "kicad_sch"):
        raise GitcadError(f"{path!r} is not a kicad_sch document")

    lib = _lib_symbols(find_one(root, "lib_symbols"))

    # honesty: out-of-scope structures
    sheets = find_all(root, "sheet")
    if sheets:
        report.dropped.append(f"{len(sheets)} hierarchical sheet(s) — flat import only (v1)")
    buses = find_all(root, "bus")
    if buses:
        report.dropped.append(f"{len(buses)} bus segment(s) — buses not yet modeled")

    dsu = _DSU()
    pin_nodes: list[tuple[tuple, str, str]] = []   # (key, "REF.num", type)
    net_names: dict[tuple, str] = {}               # point -> label/power name
    sch = Schematic(name=path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].replace(".kicad_sch", ""))

    # no_connect X markers are design intent: the pin under one becomes
    # type no_connect, so ERC honors the designer's "yes, deliberately open".
    nc_points = {_key(float((find_one(n, "at") or ["at", 0, 0])[1]),
                      float((find_one(n, "at") or ["at", 0, 0])[2]))
                 for n in find_all(root, "no_connect")}

    # Sheet graphics — the designer's actual drawing, kept as a runtime
    # projection cache (never serialized into the schematic's canonical text;
    # the diagram is a rendering of the source, not part of it).
    gfx_wires: list[list[float]] = []
    gfx_powers: list[dict] = []
    gfx_labels: list[dict] = []
    gfx_symbols: dict[str, dict] = {}

    # -- placed symbols --------------------------------------------------------
    power_count = 0
    for sym in find_all(root, "symbol"):
        lib_id = str(value_of(sym, "lib_id", default=""))
        at = find_one(sym, "at") or ["at", 0, 0, 0]
        sx, sy = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0.0
        mirror = value_of(sym, "mirror")
        props = {p[1]: str(p[2]) for p in find_all(sym, "property") if len(p) >= 3}
        ref = props.get("Reference", "?")
        entry = lib.get(lib_id, {"pins": [], "shapes": []})
        pins = entry["pins"]

        if lib_id.startswith("power:") or ref.startswith("#PWR") or ref.startswith("#FLG"):
            # power symbol: names the net at its pin point
            name = props.get("Value", lib_id.split(":")[-1])
            for p in pins:
                pt = _pin_abs(p["x"], p["y"], sx, sy, rot, mirror)
                net_names[_key(*pt)] = name
                dsu.find(("pt", _key(*pt)))
            gfx_powers.append({"name": name, "x": sx, "y": sy, "rot": rot})
            power_count += 1
            continue

        comp_pins: list[Pin] = []
        pin_xy: dict[str, list[float]] = {}
        for p in pins:
            pt = _pin_abs(p["x"], p["y"], sx, sy, rot, mirror)
            k = _key(*pt)
            ptype = "no_connect" if k in nc_points else p["type"]
            comp_pins.append(Pin(p["name"] if p["name"] != "~" else p["number"],
                                 p["number"], ptype))
            pin_nodes.append((k, f"{ref}.{p['number']}", ptype))
            pin_xy[p["number"]] = [pt[0], pt[1]]
            dsu.union(("pt", k), ("pin", ref, p["number"]))
        attrs = {"at": [sx, sy], "lib_id": lib_id, "pin_xy": pin_xy}
        if rot:
            attrs["rot"] = rot
        if mirror:
            attrs["mirror"] = mirror
        sch.components.append(SchComponent(
            ref=ref, value=props.get("Value", ""),
            footprint=props.get("Footprint", "").split(":")[-1],
            pins=comp_pins, attrs=attrs))
        report.count("symbols", 1)

        # Bake the symbol's body graphics + pin stubs into sheet coordinates.
        def _abs(px: float, py: float) -> list[float]:
            ax, ay = _pin_abs(px, py, sx, sy, rot, mirror)
            return [ax, ay]

        shapes_abs: list[dict] = []
        for shp in entry["shapes"]:
            baked = {"kind": shp["kind"], "pts": [_abs(*pt) for pt in shp["pts"]]}
            if "r" in shp:
                baked["r"] = shp["r"]
            shapes_abs.append(baked)
        for p in pins:
            rad = math.radians(p["angle"])
            bx = p["x"] + p["len"] * math.cos(rad)
            by = p["y"] + p["len"] * math.sin(rad)
            shapes_abs.append({"kind": "pin",
                               "pts": [_abs(p["x"], p["y"]), _abs(bx, by)]})
        gfx_symbols[ref] = {"shapes": shapes_abs, "at": [sx, sy],
                            "value": props.get("Value", "")}

    # -- wires / junctions / labels / no-connects ------------------------------
    wires: list[tuple[tuple, tuple]] = []
    for w in find_all(root, "wire"):
        pts = find_one(w, "pts")
        xs = find_all(pts, "xy") if pts else []
        if len(xs) >= 2:
            x1, y1 = float(xs[0][1]), float(xs[0][2])
            x2, y2 = float(xs[-1][1]), float(xs[-1][2])
            a, b = _key(x1, y1), _key(x2, y2)
            wires.append((a, b))
            gfx_wires.append([x1, y1, x2, y2])
            dsu.union(("pt", a), ("pt", b))
            report.count("wires", 1)

    def on_segment(pk, a, b) -> bool:
        (px, py), (ax, ay), (bx, by) = pk, a, b
        if min(ax, bx) - 1 <= px <= max(ax, bx) + 1 and min(ay, by) - 1 <= py <= max(ay, by) + 1:
            cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
            return abs(cross) <= 100  # 0.01mm*len scale in centi-units
        return False

    # junctions + wire-end-on-wire-interior connections
    junctions = [_key(float((find_one(j, "at") or ["at", 0, 0])[1]),
                      float((find_one(j, "at") or ["at", 0, 0])[2]))
                 for j in find_all(root, "junction")]
    endpoints = {p for w in wires for p in w} | {k for k, _, _ in pin_nodes} \
        | set(junctions) | set(net_names)
    for pk in endpoints:
        for a, b in wires:
            if pk != a and pk != b and on_segment(pk, a, b):
                dsu.union(("pt", pk), ("pt", a))

    for lbl_kind in ("label", "global_label", "hierarchical_label"):
        for lb in find_all(root, lbl_kind):
            name = str(lb[1])
            at = find_one(lb, "at") or ["at", 0, 0]
            lx, ly = float(at[1]), float(at[2])
            k = _key(lx, ly)
            net_names[k] = name
            dsu.find(("pt", k))
            gfx_labels.append({"name": name, "x": lx, "y": ly, "kind": lbl_kind,
                               "rot": float(at[3]) if len(at) > 3 else 0.0})
            report.count("labels", 1)

    # -- transform self-check: wire endpoints should land somewhere known -----
    pin_keys = {k for k, _, _ in pin_nodes} | set(net_names)
    wire_ends = [p for w in wires for p in w]
    if wire_ends:
        hits = sum(1 for p in wire_ends
                   if p in pin_keys or sum(q == p for q in wire_ends) > 1
                   or any(on_segment(p, a, b) for a, b in wires if p not in (a, b)))
        rate = hits / len(wire_ends)
        report.imported["wire_end_hit_pct"] = round(rate * 100)
        if rate < 0.9:
            report.warnings.append(
                f"only {rate:.0%} of wire endpoints land on known points — "
                "symbol transform may be wrong for some rotations/mirrors")

    # -- groups -> nets --------------------------------------------------------
    groups: dict = {}
    for k, pin_ref, ptype in pin_nodes:
        if ptype == "no_connect" or k in nc_points:
            continue
        groups.setdefault(dsu.find(("pt", k)), []).append(pin_ref)
    named: dict = {}
    for k, name in net_names.items():
        named.setdefault(dsu.find(("pt", k)), name)

    auto = 0
    for gid, pin_refs in groups.items():
        if len(pin_refs) < 1:
            continue
        name = named.get(gid)
        if not name:
            auto += 1
            name = f"N${auto}"
        for pr in sorted(set(pin_refs)):
            sch.connect(name, pr)
    report.count("nets", len(sch.nets))
    report.imported["power_symbols"] = power_count
    sch.graphics = {  # type: ignore[attr-defined]
        "wires": gfx_wires, "powers": gfx_powers, "labels": gfx_labels,
        "symbols": gfx_symbols,
        "junctions": [[jx / 100, jy / 100] for jx, jy in junctions]}
    return sch, report
