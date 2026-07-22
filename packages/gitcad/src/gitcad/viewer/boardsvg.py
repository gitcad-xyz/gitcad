"""Board → SVG: a 2D rendering of the board model (viewer + docs + diffs).

KiCad-conventional colors on the site's dark palette. Sheet coordinates are
y-up; SVG is y-down — flipped once via a group transform. Deterministic
output (canonical float formatting), so board renders diff cleanly too.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from gitcad.ecad.board import Board

_C = {
    "bg": "#0d1117", "outline": "#8b949e", "board": "#0f2418",
    "top": "#c74e39", "bottom": "#3d7dca", "pad": "#c9a227",
    "via": "#9aa3b2", "hole": "#0d1117", "silk": "#c9d1d9",
}


def _f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def board_to_svg(board: Board, *, margin: float = 3.0) -> str:
    minx, miny, maxx, maxy = board.bbox()
    w, h = maxx - minx + 2 * margin, maxy - miny + 2 * margin
    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(w)} {_f(h)}" '
        f'width="{_f(w)}mm" height="{_f(h)}mm" style="background:{_C["bg"]}">'
    )
    # One flip: board y-up -> svg y-down.
    out.append(f'<g transform="translate({_f(margin - minx)},{_f(maxy + margin)}) scale(1,-1)">')

    pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in board.outline)
    out.append(f'<polygon points="{pts}" fill="{_C["board"]}" '
               f'stroke="{_C["outline"]}" stroke-width="0.15"/>')

    def track_lines(layer: str, color: str, opacity: str) -> None:
        for t in board.tracks:
            if t.layer == layer:
                out.append(f'<line x1="{_f(t.x1)}" y1="{_f(t.y1)}" x2="{_f(t.x2)}" y2="{_f(t.y2)}" '
                           f'stroke="{color}" stroke-width="{_f(t.width)}" '
                           f'stroke-linecap="round" opacity="{opacity}"/>')

    track_lines("bottom", _C["bottom"], "0.8")
    track_lines("top", _C["top"], "0.9")

    for comp in board.components:
        for pad, bx, by, rot in comp.placed_pads():
            w_, h_ = (pad.h, pad.w) if round(rot) % 180 == 90 else (pad.w, pad.h)
            if pad.shape == "circle":
                out.append(f'<circle cx="{_f(bx)}" cy="{_f(by)}" r="{_f(max(w_, h_) / 2)}" '
                           f'fill="{_C["pad"]}"/>')
            else:
                rx = ' rx="0.2"' if pad.shape == "obround" else ""
                out.append(f'<rect x="{_f(bx - w_ / 2)}" y="{_f(by - h_ / 2)}" '
                           f'width="{_f(w_)}" height="{_f(h_)}" fill="{_C["pad"]}"{rx}/>')
            if pad.drill is not None:
                out.append(f'<circle cx="{_f(bx)}" cy="{_f(by)}" r="{_f(pad.drill / 2)}" '
                           f'fill="{_C["hole"]}"/>')

    for v in board.vias:
        out.append(f'<circle cx="{_f(v.x)}" cy="{_f(v.y)}" r="{_f(v.diameter / 2)}" fill="{_C["via"]}"/>')
        out.append(f'<circle cx="{_f(v.x)}" cy="{_f(v.y)}" r="{_f(v.drill / 2)}" fill="{_C["hole"]}"/>')

    for m in board.mounting_holes:
        out.append(f'<circle cx="{_f(m.x)}" cy="{_f(m.y)}" r="{_f(m.drill / 2)}" '
                   f'fill="{_C["hole"]}" stroke="{_C["outline"]}" stroke-width="0.1"/>')

    # Reference designators (counter-flipped so text reads upright).
    for comp in board.components:
        cy = comp.y + 1.4
        out.append(f'<text x="{_f(comp.x)}" y="{_f(-cy)}" transform="scale(1,-1)" '
                   f'fill="{_C["silk"]}" font-family="monospace" font-size="1.1" '
                   f'text-anchor="middle">{escape(comp.ref)}</text>')

    out.append("</g></svg>")
    return "".join(out) + "\n"
