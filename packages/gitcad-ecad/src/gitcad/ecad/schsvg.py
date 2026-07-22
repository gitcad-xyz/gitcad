"""Schematic diagram rendering — the human feedback loop (visual track v1).

The netlist is the source of truth; this module makes it REVIEWABLE: IEC-style
symbols, auto-layout, orthogonal net lanes with junction dots, refs/values/
pin names — the diagram a human reads before anything moves to layout.

v1 is auto-layout only (components on a grid, one horizontal lane per net).
Manual placement (``SchComponent.attrs["at"] = [x, y]``) is honored when
present; drawn-wire data and hierarchical sheets are the next stages of this
track. A drawn diagram can never disagree with the circuit: geometry is
always derived from (or checked against) the netlist.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from gitcad.ecad.schematic import SchComponent, Schematic

_C = {"bg": "#0d1117", "ink": "#c9d1d9", "sym": "#8b949e", "acc": "#58a6ff",
      "val": "#7ee787", "net": "#c74e39", "lane": "#3d7dca"}

_GRID_X = 46.0     # component pitch
_BODY_Y = 30.0     # symbol row centerline
_LANE0_Y = 62.0    # first net lane
_LANE_DY = 7.0


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


class _Sym:
    """A placed symbol: draws itself, exposes pin positions by pin number."""

    def __init__(self, comp: SchComponent, cx: float, cy: float) -> None:
        self.comp, self.cx, self.cy = comp, cx, cy
        self.pins: dict[str, tuple[float, float]] = {}
        self.parts: list[str] = []
        kind = self._kind()
        getattr(self, f"_draw_{kind}")()

    def _kind(self) -> str:
        fp = (self.comp.footprint or "").upper()
        v = (self.comp.value or "").upper()
        n = len(self.comp.pins)
        if n == 2:
            if fp.startswith("R") or v.endswith(("R", "K", "M")) or "OHM" in v:
                return "resistor"
            if fp.startswith("C") or "F" in v[-2:]:
                return "capacitor"
            if "LED" in fp or "LED" in v:
                return "led"
            if "HDR" in fp or "CONN" in fp:
                return "header"
            return "resistor"
        if "HDR" in fp or "CONN" in fp:
            return "header"
        return "ic"

    def _line(self, x1, y1, x2, y2, color=_C["sym"], w=0.5):
        self.parts.append(f'<line x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}" '
                          f'stroke="{color}" stroke-width="{w}"/>')

    def _rect(self, x, y, w, h):
        self.parts.append(f'<rect x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" '
                          f'fill="none" stroke="{_C["sym"]}" stroke-width="0.5"/>')

    def _text(self, x, y, s, color=_C["ink"], size=3.2, anchor="middle"):
        self.parts.append(f'<text x="{_f(x)}" y="{_f(y)}" fill="{color}" font-size="{size}" '
                          f'text-anchor="{anchor}" font-family="monospace">{escape(s)}</text>')

    def _two_pin(self, body):
        """Common 2-pin frame: horizontal leads, pin 0 left / pin 1 right."""
        cx, cy = self.cx, self.cy
        self._line(cx - 14, cy, cx - body / 2, cy)
        self._line(cx + body / 2, cy, cx + 14, cy)
        self.pins[self.comp.pins[0].number] = (cx - 14, cy)
        self.pins[self.comp.pins[1].number] = (cx + 14, cy)
        self._label()

    def _label(self):
        self._text(self.cx, self.cy - 8, self.comp.ref, _C["acc"], 3.6)
        if self.comp.value:
            self._text(self.cx, self.cy + 11.5, self.comp.value, _C["val"])

    def _draw_resistor(self):
        self._two_pin(16)
        self._rect(self.cx - 8, self.cy - 3, 16, 6)   # IEC box

    def _draw_capacitor(self):
        self._two_pin(4)
        self._line(self.cx - 2, self.cy - 5, self.cx - 2, self.cy + 5, _C["sym"], 1.0)
        self._line(self.cx + 2, self.cy - 5, self.cx + 2, self.cy + 5, _C["sym"], 1.0)

    def _draw_led(self):
        self._two_pin(10)
        cx, cy = self.cx, self.cy
        self.parts.append(f'<polygon points="{_f(cx-5)},{_f(cy-5)} {_f(cx-5)},{_f(cy+5)} '
                          f'{_f(cx+5)},{_f(cy)}" fill="none" stroke="{_C["sym"]}" stroke-width="0.5"/>')
        self._line(cx + 5, cy - 5, cx + 5, cy + 5, _C["sym"], 1.0)

    def _draw_header(self):
        n = len(self.comp.pins)
        h = max(n * 7 + 4, 12)
        cx, top = self.cx, self.cy - h / 2
        self._rect(cx - 6, top, 12, h)
        for i, pin in enumerate(self.comp.pins):
            py = top + 5.5 + i * 7
            self._line(cx - 14, py, cx - 6, py)
            self.pins[pin.number] = (cx - 14, py)
            self._text(cx - 3, py + 1.2, pin.number, _C["sym"], 2.6, "start")
        self._text(cx, top - 3, self.comp.ref, _C["acc"], 3.6)
        if self.comp.value:
            self._text(cx, top + h + 4.5, self.comp.value, _C["val"])

    def _draw_ic(self):
        pins = self.comp.pins
        left = pins[: (len(pins) + 1) // 2]
        right = pins[(len(pins) + 1) // 2:]
        rows = max(len(left), len(right))
        h = rows * 7 + 6
        w = 30
        cx, top = self.cx, self.cy - h / 2
        self._rect(cx - w / 2, top, w, h)
        for i, pin in enumerate(left):
            py = top + 6.5 + i * 7
            self._line(cx - w / 2 - 8, py, cx - w / 2, py)
            self.pins[pin.number] = (cx - w / 2 - 8, py)
            self._text(cx - w / 2 + 1.5, py + 1.1, pin.name, _C["ink"], 2.6, "start")
        for i, pin in enumerate(right):
            py = top + 6.5 + i * 7
            self._line(cx + w / 2, py, cx + w / 2 + 8, py)
            self.pins[pin.number] = (cx + w / 2 + 8, py)
            self._text(cx + w / 2 - 1.5, py + 1.1, pin.name, _C["ink"], 2.6, "end")
        self._text(cx, top - 3, self.comp.ref, _C["acc"], 3.6)
        if self.comp.value:
            self._text(cx, top + h + 4.5, self.comp.value, _C["val"])


def schematic_to_svg(sch: Schematic) -> str:
    """The reviewable diagram: placed symbols + one orthogonal lane per net."""
    # Placement: honored from attrs["at"], else a grid row.
    symbols: dict[str, _Sym] = {}
    x = 30.0
    for comp in sch.components:
        at = (comp.attrs or {}).get("at")
        if at:
            sym = _Sym(comp, float(at[0]), float(at[1]))
        else:
            sym = _Sym(comp, x, _BODY_Y)
            x += _GRID_X + (18 if len(comp.pins) > 2 else 0)
        symbols[comp.ref] = sym

    parts: list[str] = []
    lane_y = _LANE0_Y
    for net, pin_refs in sorted(sch.nets.items()):
        points = []
        for pr in pin_refs:
            ref, num = pr.split(".", 1)
            sym = symbols.get(ref)
            if sym and num in sym.pins:
                points.append(sym.pins[num])
        if not points:
            continue
        color = _C["net"] if net.upper() in ("GND", "VSS", "0V") else _C["lane"]
        for px, py in points:                       # drop from pin to lane
            parts.append(f'<line x1="{_f(px)}" y1="{_f(py)}" x2="{_f(px)}" y2="{_f(lane_y)}" '
                         f'stroke="{color}" stroke-width="0.6"/>')
            if len(points) > 2:                     # junction dots on multi-point nets
                parts.append(f'<circle cx="{_f(px)}" cy="{_f(lane_y)}" r="1.1" fill="{color}"/>')
        xs = sorted(p[0] for p in points)
        parts.append(f'<line x1="{_f(xs[0])}" y1="{_f(lane_y)}" x2="{_f(xs[-1])}" y2="{_f(lane_y)}" '
                     f'stroke="{color}" stroke-width="0.6"/>')
        parts.append(f'<text x="{_f(xs[0] - 3)}" y="{_f(lane_y + 1.2)}" fill="{color}" '
                     f'font-size="3" text-anchor="end" font-family="monospace">{escape(net)}</text>')
        lane_y += _LANE_DY

    all_parts = [p for s in symbols.values() for p in s.parts] + parts
    width = max((s.cx for s in symbols.values()), default=100) + 40
    height = lane_y + 14
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(width)} {_f(height)}" '
            f'width="{_f(width * 3)}" style="background:{_C["bg"]}">'
            f'<text x="{_f(width - 4)}" y="8" fill="{_C["sym"]}" font-size="3.4" '
            f'text-anchor="end" font-family="monospace">{escape(sch.name)} — gitcad</text>'
            + "".join(all_parts) + "</svg>\n")
