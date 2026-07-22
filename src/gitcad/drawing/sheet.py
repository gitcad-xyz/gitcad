"""Sheet layout: views arranged third-angle on a standard sheet, auto-scaled,
with overall dimensions and a title block. Output via :mod:`.svg` / :mod:`.pdf`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gitcad.drawing import hlr

Point = tuple[float, float]

SHEETS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0)}
STANDARD_SCALES = [20.0, 10.0, 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02]
MARGIN = 12.0
GAP = 18.0          # spacing between views (sheet mm)
DIM_OFFSET = 9.0    # dimension line offset from geometry (sheet mm)


@dataclass
class PlacedView:
    name: str
    visible: list[list[Point]]
    hidden: list[list[Point]]
    label: str


@dataclass
class Dimension:
    """A linear dimension already laid out in sheet coordinates."""
    p1: Point
    p2: Point
    text: str
    vertical: bool = False


@dataclass
class Drawing:
    sheet: str
    width: float
    height: float
    scale: float
    title: str
    views: list[PlacedView] = field(default_factory=list)
    dims: list[Dimension] = field(default_factory=list)

    def to_svg(self) -> str:
        from gitcad.drawing.svg import render_svg
        return render_svg(self)

    def to_pdf(self) -> bytes:
        from gitcad.drawing.pdf import render_pdf
        return render_pdf(self)


def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _transform(polys, scale: float, ox: float, oy: float, bmin: Point):
    return [[(ox + (x - bmin[0]) * scale, oy + (y - bmin[1]) * scale) for x, y in poly] for poly in polys]


def make_drawing(shape, *, title: str = "part", sheet: str = "A3") -> Drawing:
    """Project ``shape`` into front/top/right/iso, lay out third-angle on the
    sheet, add overall dimensions, return a :class:`Drawing`."""
    w, h = SHEETS[sheet]

    proj = {v: hlr.project(shape, v) for v in ("front", "top", "right", "iso")}
    bb = {v: hlr.bounds(p["visible"] + p["hidden"]) for v, p in proj.items()}
    size = {v: (bb[v][2] - bb[v][0], bb[v][3] - bb[v][1]) for v in bb}

    # Auto-scale: front+right across, front+top down, iso shares the top row.
    avail_w = w - 2 * MARGIN - 2 * GAP
    avail_h = h - 2 * MARGIN - GAP - 24.0  # 24 = title block clearance
    need_w = size["front"][0] + size["right"][0] + size["iso"][0]
    need_h = size["front"][1] + size["top"][1]
    scale = next((s for s in STANDARD_SCALES
                  if need_w * s <= avail_w and need_h * s <= avail_h), 0.01)

    d = Drawing(sheet=sheet, width=w, height=h, scale=scale, title=title)

    # Third-angle placement (sheet coords, y up): front bottom-left; top above
    # front; right beside front; iso in the top-right corner.
    fx, fy = MARGIN + DIM_OFFSET + 8, MARGIN + DIM_OFFSET + 8
    placements = {
        "front": (fx, fy),
        "top": (fx, fy + size["front"][1] * scale + GAP),
        "right": (fx + size["front"][0] * scale + GAP, fy),
        "iso": (w - MARGIN - size["iso"][0] * scale,
                h - MARGIN - size["iso"][1] * scale),
    }
    for name, (ox, oy) in placements.items():
        p, b = proj[name], bb[name]
        d.views.append(PlacedView(
            name=name,
            visible=_transform(p["visible"], scale, ox, oy, (b[0], b[1])),
            hidden=_transform(p["hidden"], scale, ox, oy, (b[0], b[1])),
            label=f"{name.upper()}" + ("" if name == "iso" else f"  (1:{_fmt(1/scale)})" if scale < 1 else f"  ({_fmt(scale)}:1)" if scale > 1 else ""),
        ))

    # Overall dimensions on front (width below, height at left) and top (depth).
    fw, fh = size["front"][0] * scale, size["front"][1] * scale
    tx, ty = placements["top"]
    th = size["top"][1] * scale
    d.dims.append(Dimension((fx, fy - DIM_OFFSET), (fx + fw, fy - DIM_OFFSET),
                            _fmt(size["front"][0])))
    d.dims.append(Dimension((fx - DIM_OFFSET, fy), (fx - DIM_OFFSET, fy + fh),
                            _fmt(size["front"][1]), vertical=True))
    d.dims.append(Dimension((tx - DIM_OFFSET, ty), (tx - DIM_OFFSET, ty + th),
                            _fmt(size["top"][1]), vertical=True))
    return d
