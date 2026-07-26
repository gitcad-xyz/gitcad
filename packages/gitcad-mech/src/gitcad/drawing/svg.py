"""SVG renderer for :class:`gitcad.drawing.sheet.Drawing`.

Sheet coordinates are mm with y up; SVG is y down — flipped here once.
Line conventions: continuous for visible edges, dashed for hidden, thin for
dimensions, per usual drafting practice.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from gitcad.drawing.sheet import Callout, Dimension, Drawing  # noqa: F401 - Callout used in render

_STYLE = (
    ".v{stroke:#111;stroke-width:0.35;fill:none;stroke-linecap:round}"
    ".h{stroke:#666;stroke-width:0.18;fill:none;stroke-dasharray:1.8,1.2}"
    ".d{stroke:#111;stroke-width:0.13;fill:none}"
    ".t{font:3px sans-serif;fill:#111}"
    ".lbl{font:3.5px sans-serif;fill:#111}"
    ".tb{stroke:#111;stroke-width:0.3;fill:none}"
)


def render_svg(d: Drawing) -> str:
    y = lambda v: d.height - v  # noqa: E731 — y-up sheet to y-down SVG
    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{d.width}mm" height="{d.height}mm" '
        f'viewBox="0 0 {d.width} {d.height}"><style>{_STYLE}</style>'
        f'<rect x="0" y="0" width="{d.width}" height="{d.height}" fill="white"/>'
        f'<rect x="5" y="5" width="{d.width - 10}" height="{d.height - 10}" class="tb"/>'
    )

    for view in d.views:
        for cls, polys in (("v", view.visible), ("h", view.hidden)):
            for poly in polys:
                pts = " ".join(f"{float(x):.3f},{float(y(yy)):.3f}" for x, yy in poly)
                out.append(f'<polyline class="{cls}" points="{pts}"/>')
        # View label under the view geometry.
        if view.visible:
            xs = [x for p in view.visible for x, _ in p]
            ys = [v for p in view.visible for _, v in p]
            out.append(f'<text class="lbl" x="{float(min(xs)):.2f}" y="{float(y(min(ys)) + 5):.2f}">{escape(view.label)}</text>')

    for dim in d.dims:
        out.append(_dim_svg(dim, y))

    for c in d.callouts:
        out.append(f'<line class="d" x1="{float(c.anchor[0]):.2f}" y1="{float(y(c.anchor[1])):.2f}" '
                   f'x2="{float(c.label[0]):.2f}" y2="{float(y(c.label[1])):.2f}"/>')
        if getattr(c, "balloon", False):
            # BOM balloon: the item number circled, opaque over geometry
            out.append(f'<circle class="d" cx="{float(c.label[0]):.2f}" cy="{float(y(c.label[1])):.2f}" '
                       f'r="2.6" fill="white"/>')
            out.append(f'<text class="t" x="{float(c.label[0]):.2f}" y="{float(y(c.label[1]) + 1.1):.2f}" '
                       f'text-anchor="middle">{escape(c.text)}</text>')
        else:
            out.append(f'<text class="t" x="{float(c.label[0] + 0.8):.2f}" y="{float(y(c.label[1])):.2f}">'
                       f'{escape(c.text)}</text>')

    for nx, ny, text in d.notes:
        out.append(f'<text class="t" x="{float(nx):.2f}" y="{float(y(ny)):.2f}" '
                   f'style="font-family:monospace" xml:space="preserve">{escape(text)}</text>')

    for sf in d.surface_finishes:
        out.append(_surface_finish_svg(sf, y))
    for w in d.welds:
        out.append(_weld_svg(w, y))

    out.append(_title_block(d, y))
    out.append("</svg>")
    return "".join(out) + "\n"


def _surface_finish_svg(sf, y) -> str:
    """ISO 1302 tick: a short left leg and a longer right leg meeting at
    the base point, with the Ra value above the right leg."""
    x, yb = sf.x, sf.y
    # the tick: base at (x, yb); left leg up-left, right leg up-right (taller)
    lx, ly = x - 2.5, yb + 4.3          # left leg top
    rx, ry = x + 4.5, yb + 7.8          # right leg top (60°, longer)
    s = [f'<path class="d" d="M {float(lx):.2f} {float(y(ly)):.2f} L {float(x):.2f} {float(y(yb)):.2f} '
         f'L {float(rx):.2f} {float(y(ry)):.2f}" fill="none"/>']
    s.append(f'<text class="t" x="{float(x + 0.6):.2f}" y="{float(y(ry) - 0.6):.2f}">'
             f'Ra {float(sf.ra):g}</text>')
    if sf.all_around:
        s.append(f'<circle class="d" cx="{float(x):.2f}" cy="{float(y(yb + 5.5)):.2f}" '
                 f'r="1.3" fill="none"/>')
    return "".join(s)


def _weld_svg(w, y) -> str:
    """ISO 2553 weld symbol: leader arrow to the joint, a reference line,
    and a weld-type flag (fillet triangle / square / vee) on it."""
    s = [f'<line class="d" x1="{float(w.x):.2f}" y1="{float(y(w.y)):.2f}" '
         f'x2="{float(w.ax):.2f}" y2="{float(y(w.ay)):.2f}"/>']            # leader
    rl = w.x + 14                                             # reference line
    s.append(f'<line class="d" x1="{float(w.x):.2f}" y1="{float(y(w.y)):.2f}" '
             f'x2="{float(rl):.2f}" y2="{float(y(w.y)):.2f}"/>')
    fx = w.x + 5
    if w.weld == "fillet":                                    # triangle flag
        s.append(f'<path class="d" d="M {float(fx):.2f} {float(y(w.y)):.2f} '
                 f'L {float(fx):.2f} {float(y(w.y + 3.5)):.2f} L {float(fx + 3):.2f} {float(y(w.y)):.2f} Z" '
                 f'fill="black"/>')
    elif w.weld == "square":                                  # two ticks
        for dx in (0, 3):
            s.append(f'<line class="d" x1="{float(fx + dx):.2f}" y1="{float(y(w.y)):.2f}" '
                     f'x2="{float(fx + dx):.2f}" y2="{float(y(w.y + 3.5)):.2f}"/>')
    else:                                                     # vee groove
        s.append(f'<path class="d" d="M {float(fx):.2f} {float(y(w.y + 3.5)):.2f} '
                 f'L {float(fx + 1.8):.2f} {float(y(w.y)):.2f} L {float(fx + 3.6):.2f} {float(y(w.y + 3.5)):.2f}" '
                 f'fill="none"/>')
    if w.size:
        s.append(f'<text class="t" x="{float(fx - 3.5):.2f}" y="{float(y(w.y + 3)):.2f}">'
                 f'{float(w.size):g}</text>')
    return "".join(s)


def _dim_svg(dim: Dimension, y) -> str:
    (x1, y1), (x2, y2) = dim.p1, dim.p2
    s = [f'<line class="d" x1="{float(x1):.2f}" y1="{float(y(y1)):.2f}" x2="{float(x2):.2f}" y2="{float(y(y2)):.2f}"/>']
    # Arrowheads (simple 1.2mm strokes at 30°) and extension ticks.
    a = 1.2
    if dim.vertical:
        for xx, yy, sgn in ((x1, y1, 1), (x2, y2, -1)):
            s.append(f'<line class="d" x1="{float(xx):.2f}" y1="{float(y(yy)):.2f}" x2="{float(xx - a/2):.2f}" y2="{float(y(yy + sgn*a)):.2f}"/>')
            s.append(f'<line class="d" x1="{float(xx):.2f}" y1="{float(y(yy)):.2f}" x2="{float(xx + a/2):.2f}" y2="{float(y(yy + sgn*a)):.2f}"/>')
        mx, my = x1 - 1.2, (y1 + y2) / 2
        s.append(f'<text class="t" x="{float(mx):.2f}" y="{float(y(my)):.2f}" text-anchor="middle" '
                 f'transform="rotate(-90 {float(mx):.2f} {float(y(my)):.2f})">{escape(dim.text)}</text>')
    else:
        for xx, yy, sgn in ((x1, y1, 1), (x2, y2, -1)):
            s.append(f'<line class="d" x1="{float(xx):.2f}" y1="{float(y(yy)):.2f}" x2="{float(xx + sgn*a):.2f}" y2="{float(y(yy) - a/2):.2f}"/>')
            s.append(f'<line class="d" x1="{float(xx):.2f}" y1="{float(y(yy)):.2f}" x2="{float(xx + sgn*a):.2f}" y2="{float(y(yy) + a/2):.2f}"/>')
        s.append(f'<text class="t" x="{float((x1 + x2) / 2):.2f}" y="{float(y(y1) - 1.2):.2f}" text-anchor="middle">{escape(dim.text)}</text>')
    return "".join(s)


def _title_block(d: Drawing, y) -> str:
    """Bottom-right title block: title, scale, units, generator."""
    w, h = 92.0, 20.0
    x0, y0 = d.width - 5 - w, 5.0
    rows = [
        (d.title, 5.2, "lbl"),
        (f"SCALE {float(d.scale):g}:1   UNITS mm   SHEET {d.sheet}", 10.6, "t"),
        ("gitcad — generated drawing", 15.6, "t"),
    ]
    s = [f'<rect x="{x0}" y="{float(y(y0 + h)):.2f}" width="{w}" height="{h}" class="tb"/>']
    for text, dy, cls in rows:
        s.append(f'<text class="{cls}" x="{float(x0 + 3):.2f}" y="{float(y(y0 + h) + dy):.2f}">{escape(text)}</text>')
    return "".join(s)
