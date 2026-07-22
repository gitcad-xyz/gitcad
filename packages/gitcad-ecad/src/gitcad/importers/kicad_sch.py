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

from gitcad.ecad.netderive import (derive_nets, key as _key,
                                   pin_abs as _pin_abs, wire_end_hit_rate)
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

    pin_pts: list[tuple[tuple[float, float], str, str]] = []   # (mm pt, "REF.num", type)
    net_names: dict[tuple[float, float], str] = {}             # mm pt -> net name
    wires_mm: list[tuple[tuple[float, float], tuple[float, float]]] = []
    junctions_mm: list[tuple[float, float]] = []
    sch = Schematic(name=path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].replace(".kicad_sch", ""))

    # no_connect X markers are design intent: the pin under one becomes
    # type no_connect, so ERC honors the designer's "yes, deliberately open".
    nc_mm = {(float((find_one(n, "at") or ["at", 0, 0])[1]),
              float((find_one(n, "at") or ["at", 0, 0])[2]))
             for n in find_all(root, "no_connect")}
    nc_keys = {_key(*p) for p in nc_mm}

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
                net_names[pt] = name
            gfx_powers.append({"name": name, "x": sx, "y": sy, "rot": rot})
            power_count += 1
            continue

        comp_pins: list[Pin] = []
        pin_xy: dict[str, list[float]] = {}
        for p in pins:
            pt = _pin_abs(p["x"], p["y"], sx, sy, rot, mirror)
            ptype = "no_connect" if _key(*pt) in nc_keys else p["type"]
            comp_pins.append(Pin(p["name"] if p["name"] != "~" else p["number"],
                                 p["number"], ptype))
            pin_pts.append((pt, f"{ref}.{p['number']}", ptype))
            pin_xy[p["number"]] = [pt[0], pt[1]]
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

    # -- wires / junctions / labels --------------------------------------------
    for w in find_all(root, "wire"):
        pts = find_one(w, "pts")
        xs = find_all(pts, "xy") if pts else []
        if len(xs) >= 2:
            x1, y1 = float(xs[0][1]), float(xs[0][2])
            x2, y2 = float(xs[-1][1]), float(xs[-1][2])
            wires_mm.append(((x1, y1), (x2, y2)))
            gfx_wires.append([x1, y1, x2, y2])
            report.count("wires", 1)

    junctions_mm = [(float((find_one(j, "at") or ["at", 0, 0])[1]),
                     float((find_one(j, "at") or ["at", 0, 0])[2]))
                    for j in find_all(root, "junction")]

    for lbl_kind in ("label", "global_label", "hierarchical_label"):
        for lb in find_all(root, lbl_kind):
            name = str(lb[1])
            at = find_one(lb, "at") or ["at", 0, 0]
            lx, ly = float(at[1]), float(at[2])
            net_names[(lx, ly)] = name
            gfx_labels.append({"name": name, "x": lx, "y": ly, "kind": lbl_kind,
                               "rot": float(at[3]) if len(at) > 3 else 0.0})
            report.count("labels", 1)

    # -- transform self-check: wire endpoints should land somewhere known -----
    rate = wire_end_hit_rate(pin_pts, wires_mm, net_names)
    if rate is not None:
        report.imported["wire_end_hit_pct"] = round(rate * 100)
        if rate < 0.9:
            report.warnings.append(
                f"only {rate:.0%} of wire endpoints land on known points — "
                "symbol transform may be wrong for some rotations/mirrors")

    # -- geometry -> netlist (the shared engine; see ecad/netderive.py) --------
    for name, refs in derive_nets(pin_pts, wires_mm, junctions_mm,
                                  net_names, nc_mm).items():
        sch.connect(name, *refs)
    report.count("nets", len(sch.nets))
    report.imported["power_symbols"] = power_count
    sch.graphics = {  # type: ignore[attr-defined]
        "wires": gfx_wires, "powers": gfx_powers, "labels": gfx_labels,
        "symbols": gfx_symbols,
        "junctions": [[jx, jy] for jx, jy in junctions_mm]}
    return sch, report
