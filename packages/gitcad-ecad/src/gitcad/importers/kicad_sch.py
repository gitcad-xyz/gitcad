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

from gitcad.ecad.netderive import (derive_nets_ex, key as _key,
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


def import_kicad_sch(path: str, *,
                     _seen: frozenset = frozenset(),
                     _inst_path: tuple = ()) -> tuple[Schematic, ImportReport]:
    report = ImportReport(source=path, format="kicad_sch")
    with open(path, encoding="utf-8") as f:
        root = parse(f.read())
    if not (isinstance(root, list) and root and root[0] == "kicad_sch"):
        raise GitcadError(f"{path!r} is not a kicad_sch document")

    lib = _lib_symbols(find_one(root, "lib_symbols"))

    # Instance path (KiCad instances model): "/root-uuid/sheet-uuid/..." keys
    # the per-instance reference of every symbol, which is what makes SHEET
    # REUSE work — one file instanced twice yields different refs per path.
    # At the root the path is just this file's own uuid.
    inst_chain = _inst_path or (str(value_of(root, "uuid", default="")),)
    inst_key = "/" + "/".join(u for u in inst_chain if u)

    # hierarchical subsheets: parsed here, recursed + bridged at the end
    subsheets: list[dict] = []
    for sh in find_all(root, "sheet"):
        props = {p[1]: str(p[2]) for p in find_all(sh, "property") if len(p) >= 3}
        at = find_one(sh, "at") or ["at", 0, 0]
        size = find_one(sh, "size") or ["size", 20, 20]
        spins = []
        for sp in find_all(sh, "pin"):
            pat = find_one(sp, "at") or ["at", 0, 0]
            spins.append({"name": str(sp[1]),
                          "x": float(pat[1]), "y": float(pat[2])})
        file = props.get("Sheetfile") or props.get("Sheet file") or ""
        subsheets.append({
            "name": props.get("Sheetname") or props.get("Sheet name")
            or (file.rsplit(".", 1)[0] or "sheet"),
            "file": file, "x": float(at[1]), "y": float(at[2]),
            "w": float(size[1]), "h": float(size[2]), "pins": spins,
            "uuid": str(value_of(sh, "uuid", default=""))})
    # sheet-scope names must be unique or two instances' locals would merge
    seen_names: dict[str, int] = {}
    for ss in subsheets:
        n = seen_names.get(ss["name"], 0)
        seen_names[ss["name"]] = n + 1
        if n:
            ss["name"] = f"{ss['name']}#{n + 1}"

    # buses: VISUAL groupings — connectivity comes from member labels, which
    # unify by name in the shared engine, so a bus imports as graphics plus
    # honest counting (KiCad-map tier 2). Ranged bus labels (D[0..7]) name
    # the group; the member wires carry the individual labels.
    gfx_buses: list[list[float]] = []
    for bn in find_all(root, "bus"):
        pts = find_one(bn, "pts")
        xs = find_all(pts, "xy") if pts else []
        if len(xs) >= 2:
            gfx_buses.append([float(xs[0][1]), float(xs[0][2]),
                              float(xs[-1][1]), float(xs[-1][2])])
            report.count("buses", 1)
    gfx_bus_entries: list[list[float]] = []
    for be in find_all(root, "bus_entry"):
        at = find_one(be, "at") or ["at", 0, 0]
        size = find_one(be, "size") or ["size", 2.54, 2.54]
        x, y = float(at[1]), float(at[2])
        gfx_bus_entries.append([x, y, x + float(size[1]), y + float(size[2])])

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
        # per-instance reference: the entry whose path matches OUR instance
        # chain wins (sheet reuse); a lone entry is trusted as-is
        inst = find_one(sym, "instances")
        if inst is not None:
            by_path = {}
            for proj in find_all(inst, "project"):
                for pth in find_all(proj, "path"):
                    pref = value_of(pth, "reference")
                    if pref is not None and len(pth) >= 2:
                        by_path[str(pth[1])] = str(pref)
            if inst_key in by_path:
                ref = by_path[inst_key]
            elif len(by_path) == 1:
                ref = next(iter(by_path.values()))
            elif by_path:
                report.warnings.append(
                    f"symbol {ref!r}: no instance entry for path {inst_key!r} "
                    f"— using the Reference property")
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

    gfx_notes: list[dict] = []
    for tx in find_all(root, "text"):
        at = find_one(tx, "at") or ["at", 0, 0]
        gfx_notes.append({"text": str(tx[1]), "x": float(at[1]),
                          "y": float(at[2]), "size": 1.6})

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
    # sheet pins are legitimate wire targets too, else hierarchy sheets
    # self-report a false transform warning
    sheet_pin_pts = [((sp["x"], sp["y"]), f"sheet:{ss['name']}.{sp['name']}", "sheet_pin")
                     for ss in subsheets for sp in ss["pins"]]
    rate = wire_end_hit_rate(pin_pts + sheet_pin_pts, wires_mm, net_names)
    if rate is not None:
        report.imported["wire_end_hit_pct"] = round(rate * 100)
        if rate < 0.9:
            report.warnings.append(
                f"only {rate:.0%} of wire endpoints land on known points — "
                "symbol transform may be wrong for some rotations/mirrors")

    # -- geometry -> netlist (the shared engine; see ecad/netderive.py) --------
    query_pts = tuple((sp["x"], sp["y"]) for ss in subsheets for sp in ss["pins"])
    parent_nets, query_net = derive_nets_ex(pin_pts, wires_mm, junctions_mm,
                                            net_names, nc_mm, query_pts)

    # -- recurse into subsheets, then bridge structurally ----------------------
    children: list = []
    if subsheets:
        from pathlib import Path as _Path

        me = _Path(path).resolve()
        seen = _seen | {me}
        for ss in subsheets:
            child = None
            if not ss["file"]:
                report.warnings.append(f"sheet {ss['name']!r} has no Sheetfile")
            else:
                cp = (me.parent / ss["file"]).resolve()
                if cp in seen:
                    report.warnings.append(f"sheet cycle at {ss['file']!r} — skipped")
                elif not cp.is_file():
                    report.warnings.append(f"sheet file missing: {ss['file']!r}")
                else:
                    child, crep = import_kicad_sch(
                        str(cp), _seen=seen,
                        _inst_path=inst_chain + (ss["uuid"],))
                    report.warnings += [f"{ss['name']}: {w}" for w in crep.warnings]
            children.append(child)
        report.imported["subsheets"] = sum(1 for c in children if c is not None)

    if any(c is not None for c in children):
        _hier_merge(sch, parent_nets, subsheets, children, query_net,
                    gfx_labels, gfx_powers, report)
    else:
        for name, refs in parent_nets.items():
            if refs:
                sch.connect(name, *refs)

    report.count("nets", len(sch.nets))
    report.imported["power_symbols"] = power_count
    sch.graphics = {  # type: ignore[attr-defined]
        "wires": gfx_wires, "powers": gfx_powers, "labels": gfx_labels,
        "symbols": gfx_symbols, "sheets": subsheets,
        "buses": gfx_buses, "bus_entries": gfx_bus_entries, "notes": gfx_notes,
        "junctions": [[jx, jy] for jx, jy in junctions_mm]}
    return sch, report


def _hier_merge(sch, parent_nets, subsheets, children, query_net,
                gfx_labels, gfx_powers, report) -> None:
    """Flatten the hierarchy into one netlist — thin wrapper over the shared
    engine (ecad/netderive.hier_merge), so authored and imported hierarchies
    mean exactly the same thing."""
    from gitcad.ecad.netderive import hier_merge

    hier_merge(sch, parent_nets, subsheets, children, query_net,
               gfx_labels, gfx_powers, report.warnings)
