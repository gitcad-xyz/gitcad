"""GenCAD 1.4 export — the test/assembly-machine exchange format.

Section grammar copied from a kicad-cli GenCAD export of the real Altair
board (``kicad-cli pcb export gencad``): $HEADER/$BOARD/$PADS/$PADSTACKS/
$SHAPES/$COMPONENTS/$DEVICES/$SIGNALS/$TRACKS/$ROUTES. Units are INCH
(the convention that export uses and testers expect); coordinates convert
from our mm model here. Deterministic — no timestamps.
"""

from __future__ import annotations

from gitcad._version import __version__ as _gitcad_version
from gitcad.ecad.board import Board
from gitcad.errors import GitcadError

_IN = 1 / 25.4


def _i(v: float) -> str:
    return f"{v * _IN:.6f}"


def to_gencad(board: Board) -> str:
    report = board.validate()
    if not report.ok:
        raise GitcadError(f"board failed fab validation: {report.violations}")

    copper = board.copper_layers()
    out: list[str] = []

    out += ["$HEADER", "GENCAD 1.4", f'USER "gitcad {_gitcad_version}"',
            f'DRAWING "{board.name}"', 'REVISION " "', "UNITS INCH",
            "ORIGIN 0 0", "INTERTRACK 0", "$ENDHEADER", ""]

    # board outline
    out.append("$BOARD")
    pts = list(board.outline)
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        out.append(f"LINE {_i(x1)} {_i(y1)} {_i(x2)} {_i(y2)}")
    out.append("$ENDBOARD")
    out.append("")

    # pad shapes: one PAD per distinct (shape, w, h, drill)
    pad_defs: dict[tuple, str] = {}

    def pad_name(shape: str, w: float, h: float, drill: float | None) -> str:
        key = (shape, round(w, 4), round(h, 4), round(drill or 0, 4))
        if key not in pad_defs:
            pad_defs[key] = f"P{len(pad_defs) + 1}"
        return pad_defs[key]

    for comp in board.components:
        for pad in comp.footprint.pads:
            pad_name(pad.shape, pad.w, pad.h, pad.drill)
    via_names = {}
    for v in board.vias:
        via_names[(v.diameter, v.drill)] = pad_name("circle", v.diameter,
                                                    v.diameter, v.drill)

    out.append("$PADS")
    for (shape, w, h, drill), name in sorted(pad_defs.items(), key=lambda kv: kv[1]):
        out.append(f"PAD {name} {'ROUND' if shape == 'circle' else 'RECTANGULAR'} "
                   f"{_i(drill)}")
        if shape == "circle":
            out.append(f"CIRCLE 0 0 {_i(max(w, h) / 2)}")
        else:
            out.append(f"RECTANGLE {_i(-w / 2)} {_i(-h / 2)} {_i(w)} {_i(h)}")
    out.append("$ENDPADS")
    out.append("")

    out.append("$PADSTACKS")
    for (shape, w, h, drill), name in sorted(pad_defs.items(), key=lambda kv: kv[1]):
        out.append(f"PADSTACK PS{name[1:]} {_i(drill)}")
        out.append(f"PAD {name} TOP 0 0")
        if drill:
            out.append(f"PAD {name} BOTTOM 0 0")
    out.append("$ENDPADSTACKS")
    out.append("")

    # shapes (one per footprint) with pins
    fps = {}
    for comp in board.components:
        fps.setdefault(comp.footprint.name, comp.footprint)
    out.append("$SHAPES")
    for fp_name in sorted(fps):
        fp = fps[fp_name]
        out.append("")
        out.append(f'SHAPE "{fp_name}"')
        out.append("INSERT " + ("TH" if any(p.drill for p in fp.pads) else "SMD"))
        if fp.courtyard:
            cw, chh = fp.courtyard
            for (x1, y1), (x2, y2) in [((-cw/2, -chh/2), (cw/2, -chh/2)),
                                       ((cw/2, -chh/2), (cw/2, chh/2)),
                                       ((cw/2, chh/2), (-cw/2, chh/2)),
                                       ((-cw/2, chh/2), (-cw/2, -chh/2))]:
                out.append(f"LINE {_i(x1)} {_i(y1)} {_i(x2)} {_i(y2)}")
        for pad in fp.pads:
            out.append(f'PIN "{pad.name}" {pad_name(pad.shape, pad.w, pad.h, pad.drill)} '
                       f"{_i(pad.x)} {_i(pad.y)} TOP 0 0")
    out.append("$ENDSHAPES")
    out.append("")

    out.append("$COMPONENTS")
    for comp in sorted(board.components, key=lambda c: c.ref):
        out.append("")
        out.append(f'COMPONENT "{comp.ref}"')
        out.append(f'DEVICE "DEV_{comp.footprint.name}"')
        out.append(f"PLACE {_i(comp.x)} {_i(comp.y)}")
        out.append(f"LAYER {'TOP' if comp.side == 'top' else 'BOTTOM'}")
        out.append(f"ROTATION {comp.rot:g}")
        out.append(f'SHAPE "{comp.footprint.name}" 0 0')
    out.append("$ENDCOMPONENTS")
    out.append("")

    out.append("$DEVICES")
    for fp_name in sorted(fps):
        values = sorted({c.value for c in board.components
                         if c.footprint.name == fp_name and c.value})
        out.append("")
        out.append(f'DEVICE "DEV_{fp_name}"')
        out.append(f'PART "{values[0] if values else fp_name}"')
        out.append(f'PACKAGE "{fp_name}"')
    out.append("$ENDDEVICES")
    out.append("")

    # signals: net -> component pins
    nets: dict[str, list[tuple[str, str]]] = {}
    for comp in board.components:
        for pin, net in comp.nets.items():
            if net:
                nets.setdefault(net, []).append((comp.ref, pin))
    out.append("$SIGNALS")
    for net in sorted(nets):
        out.append("")
        out.append(f'SIGNAL "{net}"')
        for ref, pin in sorted(nets[net]):
            out.append(f'NODE "{ref}" "{pin}"')
    out.append("$ENDSIGNALS")
    out.append("")

    # tracks (width classes) + routes (copper per net)
    widths = sorted({t.width for t in board.tracks})
    width_idx = {w: i for i, w in enumerate(widths)}
    out.append("$TRACKS")
    for w in widths:
        out.append(f"TRACK T{width_idx[w]} {_i(w)}")
    out.append("$ENDTRACKS")
    out.append("")

    def layer_name(layer: str) -> str:
        if layer == "top":
            return "TOP"
        if layer == "bottom":
            return "BOTTOM"
        return f"INNER{copper.index(layer)}"

    out.append("$ROUTES")
    routed = sorted({t.net for t in board.tracks} | {v.net for v in board.vias})
    for net in routed:
        out.append("")
        out.append(f'ROUTE "{net if net else "N$unnamed"}"')
        for t in board.tracks:
            if t.net != net:
                continue
            out.append(f"TRACK T{width_idx[t.width]}")
            out.append(f"LAYER {layer_name(t.layer)}")
            out.append(f"LINE {_i(t.x1)} {_i(t.y1)} {_i(t.x2)} {_i(t.y2)}")
        for v in board.vias:
            if v.net != net:
                continue
            out.append(f"VIA PS{via_names[(v.diameter, v.drill)][1:]} "
                       f"{_i(v.x)} {_i(v.y)} ALL")
    out.append("$ENDROUTES")
    return "\n".join(out) + "\n"
