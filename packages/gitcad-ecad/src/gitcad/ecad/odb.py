"""ODB++ export — the CAM-exchange tree (matrix, steps, layers, cadnet).

Structure copied from a kicad-cli ODB++ export of the real Altair board
(``kicad-cli pcb export odb``): a directory tree with ``matrix/matrix``
declaring the layer stack, per-layer ``features`` files (P/L/S records
with a local symbol table), component layers (CMP/TOP records), per-span
drill layers with ``tools``, the board ``profile``, and the ``cadnet``
netlist. Deterministic: pass ``creation`` to stamp real dates; the
default is the epoch so identical boards produce identical trees.

This is the producer subset CAM tools consume — pads, tracks, zones,
components, drills, nets. Attributes/eda fine detail beyond that are
emitted minimally and honestly (empty attrlists, minimal eda/data).
"""

from __future__ import annotations

from pathlib import Path

from gitcad._version import __version__ as _gitcad_version
from gitcad.ecad.board import Board
from gitcad.errors import GitcadError


def _f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _sym_pad(shape: str, w: float, h: float) -> str:
    """ODB++ symbol name; dimensions in µm (metric symbol convention)."""
    if shape == "circle":
        return f"r{max(w, h) * 1000:.1f}"
    if shape == "obround":
        return f"oval{w * 1000:.1f}x{h * 1000:.1f}"
    return f"rect{w * 1000:.1f}x{h * 1000:.1f}"


class _Features:
    """One layer's features file: local symbol table + records."""

    def __init__(self) -> None:
        self.syms: dict[str, int] = {}
        self.records: list[str] = []

    def sym(self, name: str) -> int:
        return self.syms.setdefault(name, len(self.syms))

    def pad(self, x: float, y: float, sym_name: str, rot: float = 0.0) -> None:
        self.records.append(
            f"P {_f(x)} {_f(y)} {self.sym(sym_name)} P 0 8 {rot:.1f}")

    def line(self, x1, y1, x2, y2, sym_name: str) -> None:
        self.records.append(
            f"L {_f(x1)} {_f(y1)} {_f(x2)} {_f(y2)} {self.sym(sym_name)} P 0")

    def surface(self, polygon) -> None:
        pts = list(polygon)
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        self.records.append("S P 0")
        self.records.append(f"OB {_f(pts[0][0])} {_f(pts[0][1])} I")
        for px, py in pts[1:]:
            self.records.append(f"OS {_f(px)} {_f(py)}")
        self.records.append("SE")

    def render(self) -> str:
        lines = ["UNITS=MM", "#", "#Num Features", "#",
                 f"F {len(self.records)}", "", "#", "#Feature symbol names", "#"]
        for name, idx in sorted(self.syms.items(), key=lambda kv: kv[1]):
            lines.append(f"${idx} {name}")
        lines.append("")
        lines += self.records
        return "\n".join(lines) + "\n"


def to_odb(board: Board, *, creation: str = "19700101.000000") -> dict[str, str]:
    """The full ODB++ job as {relative path: content}. ``export_odb`` writes
    it to disk; keeping it a dict keeps tests and MCP transport trivial."""
    report = board.validate()
    if not report.ok:
        raise GitcadError(f"board failed fab validation: {report.violations}")

    copper = board.copper_layers()
    files: dict[str, str] = {}

    # -- misc/info -------------------------------------------------------------
    files["misc/info"] = "\n".join([
        f"JOB_NAME={board.name}",
        "UNITS=MM",
        "ODB_VERSION_MAJOR=8",
        "ODB_VERSION_MINOR=1",
        "ODB_SOURCE=gitcad",
        f"CREATION_DATE={creation}",
        f"SAVE_DATE={creation}",
        f"SAVE_APP=gitcad {_gitcad_version}",
    ]) + "\n"
    files["fonts/standard"] = "\n"

    # -- layer plan ------------------------------------------------------------
    comps_top = [c for c in board.components if c.side == "top"]
    comps_bot = [c for c in board.components if c.side == "bottom"]
    spans = sorted(
        {(v.layer_from, v.layer_to) for v in board.vias
         if v.span(copper) and v.kind(copper) != "through"},
        key=lambda sp: (copper.index(sp[0]), copper.index(sp[1])))

    layers: list[tuple[str, str]] = []          # (name, TYPE)
    if comps_top:
        layers.append(("comp_+_top", "COMPONENT"))
    layers.append(("f.silkscreen", "SILK_SCREEN"))
    layers.append(("f.mask", "SOLDER_MASK"))
    for name in copper:
        layers.append((name, "SIGNAL"))
    layers.append(("b.mask", "SOLDER_MASK"))
    if comps_bot:
        layers.append(("comp_+_bot", "COMPONENT"))
    layers.append((f"drill_plated_{copper[0]}-{copper[-1]}", "DRILL"))
    for a, b in spans:
        layers.append((f"drill_plated_{a}-{b}", "DRILL"))
    layers.append((f"drill_non-plated_{copper[0]}-{copper[-1]}", "DRILL"))

    mx = ["STEP {", "    COL=1", "    NAME=PCB", "}", ""]
    for row, (name, typ) in enumerate(layers, start=1):
        mx += ["LAYER {", f"    ROW={row}", "    CONTEXT=BOARD",
               f"    TYPE={typ}", f"    NAME={name.upper()}", "    OLD_NAME=",
               "    POLARITY=POSITIVE", "    COLOR=0", "}", ""]
    files["matrix/matrix"] = "\n".join(mx)

    # -- step header + profile -------------------------------------------------
    files["steps/pcb/stephdr"] = "\n".join([
        "UNITS=MM", "X_DATUM=0", "Y_DATUM=0", "RIGHT_ACTIVE=0",
        "X_ORIGIN=0", "Y_ORIGIN=0", "LEFT_ACTIVE=0", "TOP_ACTIVE=0",
        "BOTTOM_ACTIVE=0", "AFFECTING_BOM=", "AFFECTING_BOM_CHANGED=0",
    ]) + "\n"
    prof = _Features()
    prof.surface(board.outline)
    files["steps/pcb/profile"] = prof.render()

    # -- net numbering (cadnet + eda share it) --------------------------------
    net_names = sorted({n for c in board.components for n in c.nets.values() if n}
                       | {t.net for t in board.tracks if t.net}
                       | {v.net for v in board.vias if v.net})
    net_idx = {n: i + 1 for i, n in enumerate(net_names)}   # 0 = $NONE$

    # -- copper layers ---------------------------------------------------------
    for layer in copper:
        f = _Features()
        outer = layer in ("top", "bottom")
        for comp in sorted(board.components, key=lambda c: c.ref):
            for pad, bx, by, rot in comp.placed_pads():
                if not (pad.drill is not None or (outer and comp.side == layer)):
                    continue
                w, h = (pad.h, pad.w) if round(rot) % 180 == 90 else (pad.w, pad.h)
                f.pad(bx, by, _sym_pad(pad.shape, w, h))
        for via in board.vias:
            if layer in via.span(copper):
                f.pad(via.x, via.y, _sym_pad("circle", via.diameter, via.diameter))
        for t in board.tracks:
            if t.layer == layer:
                f.line(t.x1, t.y1, t.x2, t.y2, f"r{t.width * 1000:.1f}")
        for z in board.zones:
            if z.layer == layer and z.kind == "copper":
                f.surface(z.polygon)
        files[f"steps/pcb/layers/{layer}/features"] = f.render()
        files[f"steps/pcb/layers/{layer}/attrlist"] = "UNITS=MM\n"

    # -- mask + silkscreen (openings / legend as drawn) ------------------------
    for side in ("top", "bottom"):
        f = _Features()
        e2 = board.mask_expansion * 2
        for comp in board.components:
            for pad, bx, by, rot in comp.placed_pads():
                if pad.drill is None and comp.side != side:
                    continue
                w, h = (pad.h, pad.w) if round(rot) % 180 == 90 else (pad.w, pad.h)
                f.pad(bx, by, _sym_pad(pad.shape, w + e2, h + e2))
        name = "f.mask" if side == "top" else "b.mask"
        files[f"steps/pcb/layers/{name}/features"] = f.render()
        files[f"steps/pcb/layers/{name}/attrlist"] = "UNITS=MM\n"
    silk = _Features()
    for comp in board.components:
        if comp.side != "top" or comp.footprint.courtyard is None:
            continue
        cw, ch = comp.footprint.courtyard
        x1, y1 = comp.x - cw / 2, comp.y - ch / 2
        x2, y2 = comp.x + cw / 2, comp.y + ch / 2
        for a, b in [((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)),
                     ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))]:
            silk.line(*a, *b, "r150.0")
    files["steps/pcb/layers/f.silkscreen/features"] = silk.render()
    files["steps/pcb/layers/f.silkscreen/attrlist"] = "UNITS=MM\n"

    # -- component layers ------------------------------------------------------
    pkgs = sorted({c.footprint.name for c in board.components})
    pkg_idx = {p: i for i, p in enumerate(pkgs)}
    for side, comps, lname in (("top", comps_top, "comp_+_top"),
                               ("bottom", comps_bot, "comp_+_bot")):
        if not comps:
            continue
        lines = ["UNITS=MM", ""]
        for ci, comp in enumerate(sorted(comps, key=lambda c: c.ref)):
            lines.append(f"# CMP {ci}")
            lines.append(f"CMP {pkg_idx[comp.footprint.name]} {_f(comp.x)} "
                         f"{_f(comp.y)} {comp.rot:.1f} N {comp.ref} "
                         f"{comp.value or comp.footprint.name} ;")
            for pi, (pad, bx, by, rot) in enumerate(comp.placed_pads()):
                n = comp.nets.get(pad.name, "")
                lines.append(f"TOP {pi} {_f(bx)} {_f(by)} {rot:.1f} N "
                             f"{net_idx.get(n, 0)} {pi} {pad.name}")
            lines.append("")
        files[f"steps/pcb/layers/{lname}/components"] = "\n".join(lines) + "\n"
        files[f"steps/pcb/layers/{lname}/features"] = _Features().render()
        files[f"steps/pcb/layers/{lname}/attrlist"] = "UNITS=MM\n"

    # -- drill layers (per span) + tools --------------------------------------
    def _drill_layer(name: str, holes: list[tuple[float, float, float]],
                     plated: bool) -> None:
        f = _Features()
        for d, hx, hy in holes:
            f.pad(hx, hy, f"r{d * 1000:.1f}")
        files[f"steps/pcb/layers/{name}/features"] = f.render()
        files[f"steps/pcb/layers/{name}/attrlist"] = "UNITS=MM\n"
        tl = ["UNITS=MM", "THICKNESS=0", "USER_PARAMS=", "TOOLS {"]
        for i, d in enumerate(sorted({d for d, _, _ in holes}), start=1):
            tl += [f"    NUM={i}", f"    TYPE={'PLATED' if plated else 'NON_PLATED'}",
                   "    TYPE2=STANDARD", "    MIN_TOL=0", "    MAX_TOL=0",
                   "    BIT=", f"    FINISH_SIZE={d * 1000:.1f}",
                   f"    DRILL_SIZE={d * 1000:.1f}"]
        tl += ["}", ""]
        files[f"steps/pcb/layers/{name}/tools"] = "\n".join(tl)

    through: list[tuple[float, float, float]] = []
    for comp in board.components:
        for pad, bx, by, _ in comp.placed_pads():
            if pad.drill is not None:
                through.append((pad.drill, bx, by))
    for v in board.vias:
        if v.kind(copper) == "through":
            through.append((v.drill, v.x, v.y))
    _drill_layer(f"drill_plated_{copper[0]}-{copper[-1]}", sorted(through), True)
    for a, b in spans:
        holes = sorted((v.drill, v.x, v.y) for v in board.vias
                       if (v.layer_from, v.layer_to) == (a, b))
        _drill_layer(f"drill_plated_{a}-{b}", holes, True)
    npth = sorted((m.drill, m.x, m.y) for m in board.mounting_holes)
    _drill_layer(f"drill_non-plated_{copper[0]}-{copper[-1]}", npth, False)

    # -- cadnet netlist --------------------------------------------------------
    cn = ["H optimize n staggered n", "$0 $NONE$"]
    for n in net_names:
        cn.append(f"${net_idx[n]} {n}")
    cn += ["#", "#Netlist points", "#"]
    for comp in sorted(board.components, key=lambda c: c.ref):
        side_flag = "T" if comp.side == "top" else "B"
        for pad, bx, by, rot in comp.placed_pads():
            n = comp.nets.get(pad.name, "")
            w, h = (pad.h, pad.w) if round(rot) % 180 == 90 else (pad.w, pad.h)
            cn.append(f"{net_idx.get(n, 0)} 0 {_f(bx)} {_f(by)} {side_flag} "
                      f"{w:.2f} {h:.2f} e s")
    files["steps/pcb/netlists/cadnet/netlist"] = "\n".join(cn) + "\n"

    # -- minimal eda/data ------------------------------------------------------
    eda = [f"# gitcad {_gitcad_version}", "HDR gitcad", "UNITS=MM",
           "LYR " + " ".join(n for n, _ in layers), ""]
    for n in ["$NONE$"] + net_names:
        eda.append(f"NET {n}")
    files["steps/pcb/eda/data"] = "\n".join(eda) + "\n"

    return files


def export_odb(board: Board, outdir: str) -> dict[str, str]:
    """Write the ODB++ tree under ``outdir/<name>-odb/``; returns
    {relpath: abspath} of every file written."""
    tree = to_odb(board)
    root = Path(outdir) / f"{board.name}-odb"
    written: dict[str, str] = {}
    for rel, content in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, newline="\n")
        written[rel] = str(p)
    return written
