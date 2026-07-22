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
                pts = " ".join(f"{x:.3f},{y(yy):.3f}" for x, yy in poly)
                out.append(f'<polyline class="{cls}" points="{pts}"/>')
        # View label under the view geometry.
        if view.visible:
            xs = [x for p in view.visible for x, _ in p]
            ys = [v for p in view.visible for _, v in p]
            out.append(f'<text class="lbl" x="{min(xs):.2f}" y="{y(min(ys)) + 5:.2f}">{escape(view.label)}</text>')

    for dim in d.dims:
        out.append(_dim_svg(dim, y))

    for c in d.callouts:
        out.append(f'<line class="d" x1="{c.anchor[0]:.2f}" y1="{y(c.anchor[1]):.2f}" '
                   f'x2="{c.label[0]:.2f}" y2="{y(c.label[1]):.2f}"/>')
        out.append(f'<text class="t" x="{c.label[0] + 0.8:.2f}" y="{y(c.label[1]):.2f}">'
                   f'{escape(c.text)}</text>')

    out.append(_title_block(d, y))
    out.append("</svg>")
    return "".join(out) + "\n"


def _dim_svg(dim: Dimension, y) -> str:
    (x1, y1), (x2, y2) = dim.p1, dim.p2
    s = [f'<line class="d" x1="{x1:.2f}" y1="{y(y1):.2f}" x2="{x2:.2f}" y2="{y(y2):.2f}"/>']
    # Arrowheads (simple 1.2mm strokes at 30°) and extension ticks.
    a = 1.2
    if dim.vertical:
        for xx, yy, sgn in ((x1, y1, 1), (x2, y2, -1)):
            s.append(f'<line class="d" x1="{xx:.2f}" y1="{y(yy):.2f}" x2="{xx - a/2:.2f}" y2="{y(yy + sgn*a):.2f}"/>')
            s.append(f'<line class="d" x1="{xx:.2f}" y1="{y(yy):.2f}" x2="{xx + a/2:.2f}" y2="{y(yy + sgn*a):.2f}"/>')
        mx, my = x1 - 1.2, (y1 + y2) / 2
        s.append(f'<text class="t" x="{mx:.2f}" y="{y(my):.2f}" text-anchor="middle" '
                 f'transform="rotate(-90 {mx:.2f} {y(my):.2f})">{escape(dim.text)}</text>')
    else:
        for xx, yy, sgn in ((x1, y1, 1), (x2, y2, -1)):
            s.append(f'<line class="d" x1="{xx:.2f}" y1="{y(yy):.2f}" x2="{xx + sgn*a:.2f}" y2="{y(yy) - a/2:.2f}"/>')
            s.append(f'<line class="d" x1="{xx:.2f}" y1="{y(yy):.2f}" x2="{xx + sgn*a:.2f}" y2="{y(yy) + a/2:.2f}"/>')
        s.append(f'<text class="t" x="{(x1 + x2) / 2:.2f}" y="{y(y1) - 1.2:.2f}" text-anchor="middle">{escape(dim.text)}</text>')
    return "".join(s)


def _title_block(d: Drawing, y) -> str:
    """Bottom-right title block: title, scale, units, generator."""
    w, h = 92.0, 20.0
    x0, y0 = d.width - 5 - w, 5.0
    rows = [
        (d.title, 5.2, "lbl"),
        (f"SCALE {d.scale:g}:1   UNITS mm   SHEET {d.sheet}", 10.6, "t"),
        ("gitcad — generated drawing", 15.6, "t"),
    ]
    s = [f'<rect x="{x0}" y="{y(y0 + h):.2f}" width="{w}" height="{h}" class="tb"/>']
    for text, dy, cls in rows:
        s.append(f'<text class="{cls}" x="{x0 + 3:.2f}" y="{y(y0 + h) + dy:.2f}">{escape(text)}</text>')
    return "".join(s)
