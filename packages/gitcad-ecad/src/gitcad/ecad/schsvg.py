"""Schematic diagram rendering in KiCad's visual language (visual track v2).

Engineers' eyes are trained on the KiCad look — so the diagram speaks it:
white canvas, maroon symbol outlines with cream fill, green wires and
junction dots, dark-cyan refs/values, and the idiom that matters most for
readable auto-layout: **power nets become power symbols** (GND flags, VCC
arrows) at each pin instead of wires snaking everywhere; only signal nets
route as wires.

The netlist remains the source of truth; this renders it. Manual placement
via ``attrs["at"]`` is honored; drawn-wire data and hierarchical sheets are
the next stages of the track.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from gitcad.ecad.schematic import SchComponent, Schematic

# KiCad default-theme palette.
_C = {"bg": "#FFFFFF", "sym": "#840000", "fill": "#FFFFC2", "wire": "#008400",
      "field": "#008484", "pinnum": "#840000", "pinname": "#008484",
      "label": "#000000"}

_GRID_X = 50.0
_ROW_Y = 34.0
_GND_NAMES = {"GND", "VSS", "AGND", "DGND", "0V", "GNDA", "GNDD"}


def _is_gnd(net: str) -> bool:
    return net.upper() in _GND_NAMES


def _is_power(net: str) -> bool:
    u = net.upper()
    return (u.startswith(("+", "V")) and any(ch.isdigit() for ch in u)) or \
        u in {"VCC", "VDD", "VBAT", "VIN", "VBUS"}


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


class _Sym:
    """A placed symbol; KiCad-styled drawing + pin positions by number."""

    def __init__(self, comp: SchComponent, cx: float, cy: float) -> None:
        self.comp, self.cx, self.cy = comp, cx, cy
        self.pins: dict[str, tuple[float, float]] = {}
        self.parts: list[str] = []
        getattr(self, f"_draw_{self._kind()}")()

    def _kind(self) -> str:
        fp = (self.comp.footprint or "").upper()
        v = (self.comp.value or "").upper()
        n = len(self.comp.pins)
        if n == 2:
            if "LED" in fp or "LED" in v:
                return "led"
            if fp.startswith("C") and not fp.startswith("CONN"):
                return "capacitor"
            if fp.startswith("R") or v.endswith(("R", "K", "M")):
                return "resistor"
            if "HDR" in fp or "CONN" in fp:
                return "header"
            return "resistor"
        if "HDR" in fp or "CONN" in fp:
            return "header"
        return "ic"

    def _line(self, x1, y1, x2, y2, color=_C["sym"], w=0.5):
        self.parts.append(f'<line x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}" '
                          f'stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>')

    def _rect(self, x, y, w, h, fill=_C["fill"]):
        self.parts.append(f'<rect x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" '
                          f'fill="{fill}" stroke="{_C["sym"]}" stroke-width="0.55"/>')

    def _text(self, x, y, s, color, size=3.2, anchor="middle", style=""):
        self.parts.append(f'<text x="{_f(x)}" y="{_f(y)}" fill="{color}" font-size="{size}" '
                          f'text-anchor="{anchor}" font-family="monospace"{style}>{escape(s)}</text>')

    def _two_pin(self, body):
        cx, cy = self.cx, self.cy
        self._line(cx - 15, cy, cx - body / 2, cy)
        self._line(cx + body / 2, cy, cx + 15, cy)
        self.pins[self.comp.pins[0].number] = (cx - 15, cy)
        self.pins[self.comp.pins[1].number] = (cx + 15, cy)
        self._fields(cy - 7.5, cy + 11)

    def _fields(self, ry, vy):
        self._text(self.cx, ry, self.comp.ref, _C["field"], 3.4)
        if self.comp.value:
            self._text(self.cx, vy, self.comp.value, _C["field"], 3.0)

    def _draw_resistor(self):
        self._two_pin(17)
        self._rect(self.cx - 8.5, self.cy - 3.2, 17, 6.4)

    def _draw_capacitor(self):
        self._two_pin(3.6)
        for dx in (-1.8, 1.8):
            self._line(self.cx + dx, self.cy - 5, self.cx + dx, self.cy + 5, _C["sym"], 1.0)

    def _draw_led(self):
        self._two_pin(9)
        cx, cy = self.cx, self.cy
        self.parts.append(f'<polygon points="{_f(cx-4.5)},{_f(cy-4.5)} {_f(cx-4.5)},{_f(cy+4.5)} '
                          f'{_f(cx+4.5)},{_f(cy)}" fill="{_C["fill"]}" '
                          f'stroke="{_C["sym"]}" stroke-width="0.55"/>')
        self._line(cx + 4.5, cy - 4.5, cx + 4.5, cy + 4.5, _C["sym"], 1.0)
        # emission arrows
        for dy in (-6.5, -4.0):
            self._line(cx + 1, cy + dy, cx + 4, cy + dy - 3, _C["sym"], 0.45)

    def _draw_header(self):
        n = len(self.comp.pins)
        h = max(n * 7 + 4, 12)
        cx, top = self.cx, self.cy - h / 2
        self._rect(cx - 5, top, 10, h)
        for i, pin in enumerate(self.comp.pins):
            py = top + 5.5 + i * 7
            self._line(cx - 15, py, cx - 5, py)
            self.pins[pin.number] = (cx - 15, py)
            self._text(cx - 6.2, py + 1.1, pin.number, _C["pinnum"], 2.5, "end")
        self._text(cx, top - 3, self.comp.ref, _C["field"], 3.4)
        if self.comp.value:
            self._text(cx, top + h + 4.8, self.comp.value, _C["field"], 3.0)

    def _draw_ic(self):
        pins = self.comp.pins
        left = pins[: (len(pins) + 1) // 2]
        right = pins[(len(pins) + 1) // 2:]
        rows = max(len(left), len(right))
        h, w = rows * 7 + 6, 32
        cx, top = self.cx, self.cy - h / 2
        self._rect(cx - w / 2, top, w, h)
        for side, group in ((-1, left), (1, right)):
            for i, pin in enumerate(group):
                py = top + 6.5 + i * 7
                x_in, x_out = cx + side * w / 2, cx + side * (w / 2 + 9)
                self._line(x_in, py, x_out, py)
                self.pins[pin.number] = (x_out, py)
                self._text(x_in - side * 1.6, py + 1.1, pin.name, _C["pinname"], 2.6,
                           "start" if side < 0 else "end")
                self._text((x_in + x_out) / 2, py - 1.2, pin.number, _C["pinnum"], 2.2)
        self._text(cx, top - 3, self.comp.ref, _C["field"], 3.4)
        if self.comp.value:
            self._text(cx, top + h + 4.8, self.comp.value, _C["field"], 3.0)


def _gnd_symbol(x: float, y: float, net: str) -> str:
    """KiCad-style GND flag: stub down, three shrinking bars."""
    p = [f'<line x1="{_f(x)}" y1="{_f(y)}" x2="{_f(x)}" y2="{_f(y+5)}" stroke="{_C["wire"]}" stroke-width="0.6"/>']
    for i, half in enumerate((3.4, 2.1, 0.8)):
        yy = y + 5 + i * 1.7
        p.append(f'<line x1="{_f(x-half)}" y1="{_f(yy)}" x2="{_f(x+half)}" y2="{_f(yy)}" '
                 f'stroke="{_C["sym"]}" stroke-width="0.6"/>')
    if net.upper() != "GND":
        p.append(f'<text x="{_f(x)}" y="{_f(y+13.5)}" fill="{_C["label"]}" font-size="2.4" '
                 f'text-anchor="middle" font-family="monospace">{escape(net)}</text>')
    return "".join(p)


def _power_symbol(x: float, y: float, net: str) -> str:
    """KiCad-style power flag: stub up, open circle, net name above."""
    return (f'<line x1="{_f(x)}" y1="{_f(y)}" x2="{_f(x)}" y2="{_f(y-5)}" '
            f'stroke="{_C["wire"]}" stroke-width="0.6"/>'
            f'<circle cx="{_f(x)}" cy="{_f(y-6.5)}" r="1.5" fill="none" '
            f'stroke="{_C["sym"]}" stroke-width="0.55"/>'
            f'<text x="{_f(x)}" y="{_f(y-9.5)}" fill="{_C["label"]}" font-size="2.8" '
            f'text-anchor="middle" font-family="monospace">{escape(net)}</text>')


def schematic_to_svg(sch: Schematic) -> str:
    symbols: dict[str, _Sym] = {}
    x = 34.0
    for comp in sch.components:
        at = (comp.attrs or {}).get("at")
        if at:
            sym = _Sym(comp, float(at[0]), float(at[1]))
        else:
            sym = _Sym(comp, x, _ROW_Y)
            x += _GRID_X + (22 if len(comp.pins) > 2 else 0)
        symbols[comp.ref] = sym

    wires: list[str] = []
    lane_y = _ROW_Y + 32.0
    for net, pin_refs in sorted(sch.nets.items()):
        points = []
        for pr in pin_refs:
            ref, num = pr.split(".", 1)
            sym = symbols.get(ref)
            if sym and num in sym.pins:
                points.append(sym.pins[num])
        if not points:
            continue
        if _is_gnd(net):
            wires += [_gnd_symbol(px, py, net) for px, py in points]
            continue
        if _is_power(net):
            wires += [_power_symbol(px, py, net) for px, py in points]
            continue
        # Signal net: green orthogonal trunk + drops, junctions on 3+ pins.
        for px, py in points:
            wires.append(f'<line x1="{_f(px)}" y1="{_f(py)}" x2="{_f(px)}" y2="{_f(lane_y)}" '
                         f'stroke="{_C["wire"]}" stroke-width="0.6"/>')
            if len(points) > 2:
                wires.append(f'<circle cx="{_f(px)}" cy="{_f(lane_y)}" r="1.0" fill="{_C["wire"]}"/>')
        xs = sorted(p[0] for p in points)
        wires.append(f'<line x1="{_f(xs[0])}" y1="{_f(lane_y)}" x2="{_f(xs[-1])}" y2="{_f(lane_y)}" '
                     f'stroke="{_C["wire"]}" stroke-width="0.6"/>')
        wires.append(f'<text x="{_f(xs[0] + 1.5)}" y="{_f(lane_y - 1.3)}" fill="{_C["label"]}" '
                     f'font-size="2.9" font-family="monospace">{escape(net)}</text>')
        lane_y += 6.5

    body = [p for s in symbols.values() for p in s.parts] + wires
    width = max((s.cx for s in symbols.values()), default=100) + 46
    height = lane_y + 20
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(width)} {_f(height)}" '
            f'width="{_f(width * 3)}" style="background:{_C["bg"]}">'
            f'<rect x="1.5" y="1.5" width="{_f(width-3)}" height="{_f(height-3)}" '
            f'fill="none" stroke="{_C["sym"]}" stroke-width="0.3"/>'
            f'<text x="{_f(width-4)}" y="{_f(height-4)}" fill="{_C["field"]}" font-size="3" '
            f'text-anchor="end" font-family="monospace">{escape(sch.name)} — gitcad</text>'
            + "".join(body) + "</svg>\n")


# -- sheet-fidelity rendering (visual track v3) --------------------------------
#
# For IMPORTED schematics: draw the designer's actual sheet — symbol body
# graphics, real wire routes, junction dots, labels and power flags, all at
# their original coordinates (mm). The auto-layout above stays the renderer
# for born-in-gitcad netlists that have no drawing yet.

def _sheet_power_glyph(p: dict) -> str:
    name = p["name"]
    x, y, rot = p["x"], p["y"], p.get("rot", 0.0)
    g = [f'<g transform="translate({_f(x)},{_f(y)}) rotate({_f(rot)})" '
         f'stroke="{_C["wire"]}" fill="none" stroke-width="0.25">']
    if _is_gnd(name):
        g.append('<line x1="0" y1="0" x2="0" y2="1.3"/>')
        for i, w in enumerate((1.3, 0.85, 0.4)):
            yy = 1.3 + i * 0.55
            g.append(f'<line x1="{_f(-w)}" y1="{_f(yy)}" x2="{_f(w)}" y2="{_f(yy)}"/>')
    else:
        g.append('<line x1="0" y1="0" x2="0" y2="-1.6"/>')
        g.append('<line x1="-0.9" y1="-1.6" x2="0.9" y2="-1.6"/>')
        g.append(f'<text x="0" y="-2.4" fill="{_C["label"]}" stroke="none" '
                 f'font-size="1.27" text-anchor="middle" '
                 f'font-family="monospace">{escape(name)}</text>')
    g.append("</g>")
    return "".join(g)


def sheet_to_svg(sch: Schematic) -> str:
    """Render an imported schematic exactly as drawn — KiCad's own sheet.

    Requires the runtime ``graphics`` projection the .kicad_sch importer
    attaches; born-in-gitcad schematics render via :func:`schematic_to_svg`.
    """
    from gitcad.errors import GitcadError

    gfx = getattr(sch, "graphics", None)
    if not gfx:
        raise GitcadError(
            "schematic has no sheet graphics (not imported from .kicad_sch?) "
            "— use schematic_to_svg for auto-layout rendering")

    xs: list[float] = []
    ys: list[float] = []
    for w in gfx["wires"]:
        xs += [w[0], w[2]]; ys += [w[1], w[3]]
    for sym in gfx["symbols"].values():
        for shp in sym["shapes"]:
            for px, py in shp["pts"]:
                xs.append(px); ys.append(py)
    for lb in gfx["labels"]:
        xs.append(lb["x"]); ys.append(lb["y"])
    for p in gfx["powers"]:
        xs.append(p["x"]); ys.append(p["y"])
    if not xs:
        raise GitcadError("sheet graphics are empty")
    m = 8.0
    x0, y0 = min(xs) - m, min(ys) - m
    w, h = max(xs) - x0 + m, max(ys) - y0 + m

    out: list[str] = []
    # symbol bodies first (cream fills under everything else)
    for ref, sym in gfx["symbols"].items():
        for shp in sym["shapes"]:
            pts = shp["pts"]
            if shp["kind"] == "rect":
                (x1, y1), (x2, y2) = pts
                out.append(f'<rect x="{_f(min(x1, x2))}" y="{_f(min(y1, y2))}" '
                           f'width="{_f(abs(x2 - x1))}" height="{_f(abs(y2 - y1))}" '
                           f'fill="{_C["fill"]}" stroke="{_C["sym"]}" stroke-width="0.25"/>')
            elif shp["kind"] == "poly":
                d = " ".join(f"{_f(px)},{_f(py)}" for px, py in pts)
                out.append(f'<polyline points="{d}" fill="none" '
                           f'stroke="{_C["sym"]}" stroke-width="0.25"/>')
            elif shp["kind"] == "circle":
                (cx, cy), = pts
                out.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{_f(shp["r"])}" '
                           f'fill="none" stroke="{_C["sym"]}" stroke-width="0.25"/>')
            elif shp["kind"] == "arc":
                (x1, y1), (xm, ym), (x2, y2) = pts
                out.append(f'<path d="M {_f(x1)} {_f(y1)} Q {_f(2*xm-(x1+x2)/2)} '
                           f'{_f(2*ym-(y1+y2)/2)} {_f(x2)} {_f(y2)}" fill="none" '
                           f'stroke="{_C["sym"]}" stroke-width="0.25"/>')
            elif shp["kind"] == "pin":
                (x1, y1), (x2, y2) = pts
                out.append(f'<line x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}" '
                           f'stroke="{_C["sym"]}" stroke-width="0.25"/>')

    # ref/value fields near the symbol anchor
    for comp in sch.components:
        at = comp.attrs.get("at")
        if not at or comp.ref not in gfx["symbols"]:
            continue
        out.append(f'<text x="{_f(at[0] + 1.2)}" y="{_f(at[1] - 1.2)}" fill="{_C["field"]}" '
                   f'font-size="1.27" font-family="monospace">{escape(comp.ref)}</text>')
        if comp.value:
            out.append(f'<text x="{_f(at[0] + 1.2)}" y="{_f(at[1] + 2.2)}" fill="{_C["field"]}" '
                       f'font-size="1.27" font-family="monospace">{escape(comp.value)}</text>')

    for wx in gfx["wires"]:
        out.append(f'<line x1="{_f(wx[0])}" y1="{_f(wx[1])}" x2="{_f(wx[2])}" y2="{_f(wx[3])}" '
                   f'stroke="{_C["wire"]}" stroke-width="0.25"/>')
    for jx, jy in gfx["junctions"]:
        out.append(f'<circle cx="{_f(jx)}" cy="{_f(jy)}" r="0.45" fill="{_C["wire"]}"/>')
    for lb in gfx["labels"]:
        anchor = "start" if lb.get("rot", 0) in (0, 360) else "end" if lb.get("rot") == 180 else "start"
        weight = ' font-weight="bold"' if lb["kind"] != "label" else ""
        out.append(f'<text x="{_f(lb["x"])}" y="{_f(lb["y"] - 0.4)}" fill="{_C["label"]}" '
                   f'font-size="1.27" text-anchor="{anchor}"{weight} '
                   f'font-family="monospace">{escape(lb["name"])}</text>')
    for p in gfx["powers"]:
        out.append(_sheet_power_glyph(p))
    for ss in gfx.get("sheets", []):
        # hierarchical subsheet box, KiCad-style: outline + name + pin ticks
        out.append(f'<rect x="{_f(ss["x"])}" y="{_f(ss["y"])}" '
                   f'width="{_f(ss["w"])}" height="{_f(ss["h"])}" '
                   f'fill="{_C["fill"]}" stroke="{_C["sym"]}" stroke-width="0.3"/>')
        out.append(f'<text x="{_f(ss["x"])}" y="{_f(ss["y"] - 0.6)}" '
                   f'fill="{_C["field"]}" font-size="1.6" '
                   f'font-family="monospace">{escape(ss["name"])}</text>')
        for sp in ss.get("pins", []):
            out.append(f'<circle cx="{_f(sp["x"])}" cy="{_f(sp["y"])}" r="0.4" '
                       f'fill="none" stroke="{_C["sym"]}" stroke-width="0.25"/>')
            out.append(f'<text x="{_f(sp["x"] + 0.8)}" y="{_f(sp["y"] + 0.4)}" '
                       f'fill="{_C["label"]}" font-size="1.1" '
                       f'font-family="monospace">{escape(sp["name"])}</text>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{_f(x0)} {_f(y0)} {_f(w)} {_f(h)}" '
            f'width="{_f(w * 5)}" style="background:{_C["bg"]}">'
            f'<text x="{_f(x0 + w - 2)}" y="{_f(y0 + h - 2)}" fill="{_C["field"]}" '
            f'font-size="1.6" text-anchor="end" font-family="monospace">'
            f'{escape(sch.name)} — gitcad sheet</text>'
            + "".join(out) + "</svg>\n")
