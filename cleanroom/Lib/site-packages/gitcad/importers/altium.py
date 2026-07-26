"""Altium PcbDoc import — ASCII records; binary OLE detected with guidance.

Altium saves .PcbDoc in two containers: an OLE compound document (binary,
undocumented) and an ASCII form (pipe-delimited ``|KEY=VALUE`` records,
one per line). This importer parses the ASCII form at netlist+copper
level — components with pads, tracks, vias, nets — with every drop
reported (the import-report contract). Binary files are refused with the
working migration path, exactly like SolidWorks imports: KiCad opens
Altium binaries (File > Import > Non-KiCad Board), and the resulting
.kicad_pcb imports fully here.

Format notes (community-documented; Altium's ASCII is stable across
versions): coordinates carry a ``mil`` suffix (``3700mil``) or ``mm``;
pads reference their component by index; ``MULTILAYER`` pads are PTH.
"""

from __future__ import annotations

import re

from gitcad.ecad.board import (Board, Component, Footprint, MountingHole,
                               Pad, Track, Via)
from gitcad.errors import GitcadError
from gitcad.importers.report import ImportReport

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _mm(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    v = value.strip().lower()
    try:
        if v.endswith("mil"):
            return float(v[:-3]) * 0.0254
        if v.endswith("mm"):
            return float(v[:-2])
        return float(v) * 0.0254          # bare numbers are mil
    except ValueError:
        return default


def _map_layer(name: str, layers: int) -> str | None:
    up = (name or "").upper()
    if up in ("TOP", "TOPLAYER", "F.CU"):
        return "top"
    if up in ("BOTTOM", "BOTTOMLAYER", "B.CU"):
        return "bottom"
    m = re.match(r"MID(?:LAYER)?(\d+)$", up)
    if m and int(m.group(1)) <= layers - 2:
        return f"in{m.group(1)}"
    return None


def import_altium_pcb(path: str) -> tuple[Board, ImportReport]:
    report = ImportReport(source=path, format="altium_pcbdoc")
    with open(path, "rb") as f:
        head = f.read(8)
    if head == _OLE_MAGIC:
        raise GitcadError(
            "binary (OLE) Altium PcbDoc — the working path: open it in KiCad "
            "(File > Import > Non-KiCad Board), save as .kicad_pcb, then "
            "`board_import` that file; or save from Altium as ASCII "
            "(Save As > Advanced > ASCII) and import it here directly")

    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    records: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip().lstrip("﻿")
        if not line.startswith("|"):
            continue
        fields: dict[str, str] = {}
        for part in line.strip("|").split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                fields[k.upper()] = v
        if "RECORD" in fields:
            records.append(fields)
    if not any(r.get("RECORD") == "Board" for r in records):
        raise GitcadError(
            f"{path!r} has no Altium ASCII Board record — not an ASCII PcbDoc")

    # layer census: deepest MID layer referenced decides the stack
    max_mid = 0
    for r in records:
        for key in ("LAYER", "STARTLAYER", "ENDLAYER"):
            m = re.match(r"MID(?:LAYER)?(\d+)$", (r.get(key) or "").upper())
            if m:
                max_mid = max(max_mid, int(m.group(1)))
    layers = max(2, max_mid + 2)

    # nets by index
    net_by_id: dict[str, str] = {}
    net_ordinal = 0
    for r in records:
        if r.get("RECORD") == "Net":
            name = r.get("NAME", f"NET{net_ordinal}")
            net_by_id[r.get("ID", str(net_ordinal))] = name
            net_by_id.setdefault(str(net_ordinal), name)
            net_ordinal += 1

    def net_of(r: dict) -> str:
        return net_by_id.get(r.get("NET", ""), "")

    board = Board(name="imported-altium", outline=[], layers=layers)

    # components (by index, as pads reference them)
    comp_records = [r for r in records if r.get("RECORD") == "Component"]
    comps: list[Component] = []
    for i, r in enumerate(comp_records):
        rot = float(r.get("ROTATION", "0") or 0)
        side = "bottom" if (r.get("LAYER", "TOP").upper()
                            in ("BOTTOM", "BOTTOMLAYER")) else "top"
        if round(rot) % 90 != 0:
            report.warnings.append(
                f"component {r.get('SOURCEDESIGNATOR', i)}: rotation {rot} "
                "not a right angle — kept, fab validation will flag it")
        comps.append(Component(
            ref=r.get("SOURCEDESIGNATOR") or f"CMP{i}",
            footprint=Footprint(r.get("PATTERN") or f"pattern{i}", pads=[]),
            value=r.get("COMMENT", ""),
            x=_mm(r.get("X")), y=_mm(r.get("Y")),
            rot=rot % 360, side=side, nets={}))
        report.count("components", 1)

    # pads: absolute coords -> footprint-relative (un-rotate)
    import math
    free_pads = 0
    for r in records:
        if r.get("RECORD") != "Pad":
            continue
        ci = r.get("COMPONENT")
        ax, ay = _mm(r.get("X")), _mm(r.get("Y"))
        w = _mm(r.get("XSIZE"), 1.0)
        h = _mm(r.get("YSIZE"), 1.0)
        shape = {"ROUND": "circle", "RECTANGLE": "rect",
                 "OCTAGONAL": "rect", "ROUNDEDRECTANGLE": "rect"}.get(
                     (r.get("SHAPE") or "ROUND").upper(), "rect")
        hole = _mm(r.get("HOLESIZE")) or None
        if hole == 0.0:
            hole = None
        plated = (r.get("PLATED", "TRUE").upper() != "FALSE")
        if hole and not plated:
            board.mounting_holes.append(MountingHole(
                name=f"npth_{len(board.mounting_holes) + 1}",
                x=ax, y=ay, drill=hole))
            report.count("mounting_holes", 1)
            continue
        if ci is None or not ci.isdigit() or int(ci) >= len(comps):
            free_pads += 1
            continue
        comp = comps[int(ci)]
        dx, dy = ax - comp.x, ay - comp.y
        rad = math.radians(-comp.rot)
        rx = dx * math.cos(rad) - dy * math.sin(rad)
        ry = dx * math.sin(rad) + dy * math.cos(rad)
        name = r.get("NAME", str(len(comp.footprint.pads) + 1))
        comp.footprint.pads.append(Pad(name, round(rx, 4), round(ry, 4),
                                       w, h, shape=shape, drill=hole))
        n = net_of(r)
        if n:
            comp.nets[name] = n
        report.count("pads", 1)
    if free_pads:
        report.dropped.append(f"{free_pads} free pads without a component")

    board.components = [c for c in comps if c.footprint.pads]
    for c in comps:
        if not c.footprint.pads:
            report.dropped.append(f"component {c.ref}: no pads parsed")

    copper = board.copper_layers()
    for r in records:
        if r.get("RECORD") == "Track":
            layer = _map_layer(r.get("LAYER", ""), layers)
            if layer is None:
                continue                      # silk/mech lines are not copper
            board.tracks.append(Track(
                _mm(r.get("X1")), _mm(r.get("Y1")),
                _mm(r.get("X2")), _mm(r.get("Y2")),
                _mm(r.get("WIDTH"), 0.25), layer, net_of(r)))
            report.count("tracks", 1)
        elif r.get("RECORD") == "Via":
            a = _map_layer(r.get("STARTLAYER", "TOP"), layers) or "top"
            b = _map_layer(r.get("ENDLAYER", "BOTTOM"), layers) or "bottom"
            order = {n: i for i, n in enumerate(copper)}
            lf, lt = sorted((a, b), key=order.__getitem__)
            board.vias.append(Via(
                _mm(r.get("X")), _mm(r.get("Y")),
                drill=_mm(r.get("HOLESIZE"), 0.4),
                diameter=_mm(r.get("DIAMETER"), 0.8),
                net=net_of(r), layer_from=lf, layer_to=lt))
            report.count("vias", 1)

    # outline: Altium ASCII board vertices are version-fickle — bbox of the
    # imported copper, honestly reported (same convention as complex
    # Edge.Cuts in the KiCad importer)
    xs: list[float] = []
    ys: list[float] = []
    for c in board.components:
        for _p, bx, by, _r in c.placed_pads():
            xs.append(bx); ys.append(by)
    for t in board.tracks:
        xs += [t.x1, t.x2]; ys += [t.y1, t.y2]
    for v in board.vias:
        xs.append(v.x); ys.append(v.y)
    if not xs:
        raise GitcadError("no copper parsed from the ASCII PcbDoc")
    m = 1.0
    x0, y0, x1, y1 = min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m
    board.outline = [(0, 0), (x1 - x0, 0), (x1 - x0, y1 - y0), (0, y1 - y0)]
    report.warnings.append("outline approximated by copper bounding box")

    # normalize to (0,0) origin like every gitcad import
    for c in board.components:
        c.x -= x0; c.y -= y0
    for t in board.tracks:
        t.x1 -= x0; t.y1 -= y0; t.x2 -= x0; t.y2 -= y0
    for v in board.vias:
        v.x -= x0; v.y -= y0
    for mh in board.mounting_holes:
        mh.x -= x0; mh.y -= y0

    report.count("nets", len({n for c in board.components
                              for n in c.nets.values() if n}))
    return board, report
