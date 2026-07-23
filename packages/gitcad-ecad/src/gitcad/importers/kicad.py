"""KiCad .kicad_pcb importer → gitcad Board.

Supports the KiCad 6/7/8/9 s-expression board format for 2-layer boards:
footprints (SMD + through-hole pads, both fp_text and property-style
references), segments, vias, NPTH pads as mounting holes, Edge.Cuts outline,
and net names. Coordinates convert from KiCad's y-down mm to gitcad's y-up mm,
normalized so the outline's min corner lands at (0, 0).

Honesty rules (ImportReport):
- >2 copper layers is a hard error — dropping copper would import a wrong board.
- Zones/pours are DROPPED with a report entry (v0.1 board model has no pours).
- Non-rectangular outlines are approximated by their bounding box (warning).
- Bottom-side placements carry a verify-this warning (mirror conventions vary).
"""

from __future__ import annotations

import re

from gitcad.ecad.board import Board, Component, Footprint, MountingHole, Pad, Track, Via, Zone
from gitcad.errors import GitcadError
from gitcad.importers.report import ImportReport
from gitcad.importers.sexp import find_all, find_one, parse, value_of

_SHAPE_MAP = {"circle": "circle", "rect": "rect", "roundrect": "rect", "oval": "obround"}


def import_kicad_pcb(path: str) -> tuple[Board, ImportReport]:
    report = ImportReport(source=path, format="kicad_pcb")
    with open(path, encoding="utf-8") as f:
        root = parse(f.read())
    if not (isinstance(root, list) and root and root[0] == "kicad_pcb"):
        raise GitcadError(f"{path!r} is not a kicad_pcb document")

    # -- copper layer census: multi-layer stacks map In<k>.Cu -> in<k> --------
    layers_node = find_one(root, "layers") or []
    copper = [c for c in layers_node if isinstance(c, list) and len(c) >= 2
              and isinstance(c[1], str) and c[1].endswith(".Cu")]
    inner = [c[1] for c in copper if c[1] not in ("F.Cu", "B.Cu")]
    layer_count = max(2, len(copper))
    if layer_count > 16:
        raise GitcadError(f"{layer_count} copper layers — gitcad supports up to 16")

    def map_layer(kc: str) -> str | None:
        if kc == "F.Cu":
            return "top"
        if kc == "B.Cu":
            return "bottom"
        m = re.match(r"In(\d+)\.Cu$", kc or "")
        if m and int(m.group(1)) <= layer_count - 2:
            return f"in{m.group(1)}"
        return None
    if inner:
        report.count("inner_layers", len(inner))

    # -- nets ------------------------------------------------------------------
    net_names: dict[float, str] = {}
    for n in find_all(root, "net"):
        if len(n) >= 3:
            net_names[n[1]] = str(n[2])
        elif len(n) == 2:
            net_names[n[1]] = ""

    # -- outline from Edge.Cuts ------------------------------------------------
    pts: list[tuple[float, float]] = []
    rect_count, other_edges = 0, 0
    for tag in ("gr_line", "gr_rect", "gr_arc", "gr_circle", "gr_poly"):
        for g in find_all(root, tag):
            if value_of(g, "layer") != "Edge.Cuts":
                continue
            if tag == "gr_rect":
                rect_count += 1
            elif tag != "gr_line":
                other_edges += 1
            for key in ("start", "end", "center", "mid"):
                node = find_one(g, key)
                if node and len(node) >= 3:
                    pts.append((float(node[1]), float(node[2])))
            xy_holder = find_one(g, "pts")
            if xy_holder:
                for xy in find_all(xy_holder, "xy"):
                    pts.append((float(xy[1]), float(xy[2])))
    if not pts:
        raise GitcadError("no Edge.Cuts outline found — cannot determine board shape")

    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)

    # KiCad y-down -> gitcad y-up, normalized to (0,0) at outline min corner.
    def cx(x: float) -> float:
        return x - minx

    def cy(y: float) -> float:
        return maxy - y

    board = Board(name="imported", outline=[(0, 0), (cx(maxx), 0), (cx(maxx), cy(miny)), (0, cy(miny))],
                  layers=layer_count)
    if other_edges or (rect_count == 0 and len(pts) > 8):
        report.warnings.append("outline approximated by bounding box (arcs/complex Edge.Cuts)")
    report.count("outline_points", len(pts))

    # -- footprints ------------------------------------------------------------
    for fp in find_all(root, "footprint") + find_all(root, "module"):  # module = v5 name
        fp_name = fp[1] if len(fp) > 1 and isinstance(fp[1], str) else "unknown"
        layer = value_of(fp, "layer", default="F.Cu")
        side = "top" if layer == "F.Cu" else "bottom"
        at = find_one(fp, "at") or ["at", 0, 0]
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 else 0.0

        ref, value = _ref_and_value(fp)
        pads: list[Pad] = []
        nets: dict[str, str] = {}
        for pad_node in find_all(fp, "pad"):
            pad_name = str(pad_node[1])
            pad_type = pad_node[2] if len(pad_node) > 2 else "smd"
            pad_shape = pad_node[3] if len(pad_node) > 3 else "rect"
            pat = find_one(pad_node, "at") or ["at", 0, 0]
            px, py = float(pat[1]), -float(pat[2])   # y-flip within footprint frame
            size = find_one(pad_node, "size") or ["size", 1, 1]
            w, h = float(size[1]), float(size[2])
            drill = value_of(pad_node, "drill")
            drill = float(drill) if isinstance(drill, float) else None
            net_node = find_one(pad_node, "net")

            if pad_type == "np_thru_hole":
                # NPTH pad -> mounting hole (a mech port, per ADR-0008)
                board.mounting_holes.append(MountingHole(
                    name=f"{ref or fp_name}_{pad_name}",
                    x=cx(fx + px if frot == 0 else fx + px), y=cy(fy - py),
                    drill=drill or max(w, h)))
                report.count("mounting_holes", 1)
                continue

            shape = _SHAPE_MAP.get(str(pad_shape))
            if shape is None:
                report.dropped.append(f"pad {ref}.{pad_name}: unsupported shape {pad_shape!r}")
                continue
            if pad_shape == "roundrect":
                report.warnings.append(f"pad {ref}.{pad_name}: roundrect imported as rect")
            pads.append(Pad(pad_name, px, py, w, h, shape=shape,
                            drill=drill if pad_type == "thru_hole" else None))
            if net_node is not None and len(net_node) >= 2:
                nets[pad_name] = net_names.get(net_node[1], str(net_node[2]) if len(net_node) > 2 else "")
            report.count("pads", 1)

        if not pads:
            continue
        board.components.append(Component(
            ref=ref or fp_name, footprint=Footprint(fp_name, pads=pads),
            value=value, x=cx(fx), y=cy(fy),
            rot=(-frot) % 360, side=side, nets=nets))
        report.count("components", 1)
        if side == "bottom":
            report.warnings.append(f"{ref}: bottom-side placement imported — verify mirroring")

    # -- tracks and vias -------------------------------------------------------
    for seg in find_all(root, "segment"):
        layer = map_layer(value_of(seg, "layer", default="F.Cu"))
        if layer is None:
            report.dropped.append(
                f"track on unmapped layer {value_of(seg, 'layer')!r}")
            continue
        start, end = find_one(seg, "start"), find_one(seg, "end")
        net = net_names.get(value_of(seg, "net", default=-1.0), "")
        board.tracks.append(Track(
            cx(float(start[1])), cy(float(start[2])),
            cx(float(end[1])), cy(float(end[2])),
            float(value_of(seg, "width", default=0.25)),
            layer, net))
        report.count("tracks", 1)

    for via_node in find_all(root, "via"):
        at = find_one(via_node, "at")
        board.vias.append(Via(
            cx(float(at[1])), cy(float(at[2])),
            drill=float(value_of(via_node, "drill", default=0.4)),
            diameter=float(value_of(via_node, "size", default=0.8)),
            net=net_names.get(value_of(via_node, "net", default=-1.0), "")))
        report.count("vias", 1)

    # -- zones: the real routing strategy of pour-based boards ----------------
    for zn in find_all(root, "zone"):
        layer = map_layer(value_of(zn, "layer", default="F.Cu"))
        if layer is None:
            report.dropped.append(
                f"zone on unmapped layer {value_of(zn, 'layer')!r}")
            continue
        poly = find_one(zn, "polygon")
        pts_node = find_one(poly, "pts") if poly else None
        if not pts_node:
            report.dropped.append("zone without polygon")
            continue
        polygon = [(cx(float(p[1])), cy(float(p[2]))) for p in find_all(pts_node, "xy")]
        keepout = find_one(zn, "keepout") is not None
        net = "" if keepout else net_names.get(value_of(zn, "net", default=-1.0), "")
        board.zones.append(Zone(net=net, layer=layer, polygon=polygon,
                                kind="keepout" if keepout else "copper"))
        report.count("keepouts" if keepout else "zones", 1)
    arcs = find_all(root, "arc")
    if arcs:
        report.dropped.append(f"{len(arcs)} track arc(s) — v0.1 tracks are straight segments")

    return board, report


def _ref_and_value(fp) -> tuple[str, str]:
    """Reference/value from either v6+ (property "Reference" ...) or
    v5 (fp_text reference ...) style."""
    ref = value_str = ""
    for prop in find_all(fp, "property"):
        if len(prop) >= 3 and prop[1] == "Reference":
            ref = str(prop[2])
        elif len(prop) >= 3 and prop[1] == "Value":
            value_str = str(prop[2])
    for t in find_all(fp, "fp_text"):
        if len(t) >= 3 and t[1] == "reference":
            ref = ref or str(t[2])
        elif len(t) >= 3 and t[1] == "value":
            value_str = value_str or str(t[2])
    return ref, value_str
