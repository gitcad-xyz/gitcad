"""Section views (SW-manual FR3): cut, project, hatch.

A section view is three exact-geometry operations composed behind the seams:
the body is cut with a half-space at the section plane, the remainder is
HLR-projected looking at the cut, and the plane∩solid intersection curves
(``Kernel.section_polys`` — same projector frame, so they overlay
coordinate-for-coordinate) are chained into closed loops and hatched at 45
degrees with even-odd clipping. Everything derives from the model: move a
hole, regenerate, and the hatch boundary follows.
"""

from __future__ import annotations

import math

from gitcad.drawing import hlr
from gitcad.drawing.sheet import (MARGIN, SHEETS, STANDARD_SCALES, Drawing,
                                  PlacedView, _fmt, _transform)
from gitcad.errors import GitcadError

Point = tuple[float, float]

_AXES = {"x": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
         "y": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),
         "z": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0))}

_CHAIN_TOL = 1e-4
_HATCH_SPACING = 2.5   # sheet mm between hatch lines


def _chain_loops(polys: list[list[Point]]) -> list[list[Point]]:
    """Chain open polylines into closed loops by matching endpoints."""
    def key(p: Point) -> tuple[int, int]:
        return (round(p[0] / _CHAIN_TOL), round(p[1] / _CHAIN_TOL))

    remaining = [list(p) for p in polys if len(p) >= 2]
    loops: list[list[Point]] = []
    while remaining:
        loop = remaining.pop()
        while key(loop[0]) != key(loop[-1]):
            for i, cand in enumerate(remaining):
                if key(cand[0]) == key(loop[-1]):
                    loop += cand[1:]
                    remaining.pop(i)
                    break
                if key(cand[-1]) == key(loop[-1]):
                    loop += list(reversed(cand))[1:]
                    remaining.pop(i)
                    break
            else:
                break   # open chain — leave unhatched rather than guess
        if key(loop[0]) == key(loop[-1]) and len(loop) >= 4:
            loops.append(loop)
    return loops


def _hatch_loops(loops: list[list[Point]], spacing: float) -> list[list[Point]]:
    """45-degree hatching with even-odd clipping across ALL loops together
    (so holes inside the section stay clear)."""
    if not loops:
        return []
    c, s = math.cos(math.radians(45)), math.sin(math.radians(45))
    rot = [[(x * c + y * s, -x * s + y * c) for x, y in lp] for lp in loops]
    ys = [y for lp in rot for _, y in lp]
    out: list[list[Point]] = []
    yy = min(ys) + spacing / 2
    while yy < max(ys):
        xs: list[float] = []
        for lp in rot:
            for (x1, y1), (x2, y2) in zip(lp, lp[1:]):
                if (y1 <= yy < y2) or (y2 <= yy < y1):
                    xs.append(x1 + (yy - y1) / (y2 - y1) * (x2 - x1))
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2]):
            # rotate the segment back
            out.append([(a * c - yy * s, a * s + yy * c),
                        (b * c - yy * s, b * s + yy * c)])
        yy += spacing
    return out


def make_section_drawing(shape, kernel=None, *, axis: str = "x",
                         offset: float = 0.0, title: str = "part",
                         sheet: str = "A4") -> Drawing:
    """One-view section drawing: SECTION A-A at ``axis = offset``.

    Material on the viewer side of the plane is removed; the cut surface is
    hatched. The view direction looks along -axis (the drafting arrows)."""
    if kernel is None:
        from gitcad.kernel import get_kernel

        kernel = get_kernel(require="occt")
    if axis not in _AXES:
        raise GitcadError(f"section axis must be x|y|z, got {axis!r}")
    direction, xdir = _AXES[axis]

    # Half-space cut: remove material between the viewer and the plane.
    (lo, hi) = kernel.bbox(shape)
    span = [hi[i] - lo[i] for i in range(3)]
    pad = max(span) + 1.0
    ax_i = {"x": 0, "y": 1, "z": 2}[axis]
    box = kernel.box(*[pad * 3] * 3)
    shift = [lo[i] - pad for i in range(3)]
    # Viewer side = +direction: half-space starts at the plane and extends +.
    shift[ax_i] = offset if direction[ax_i] > 0 else offset - pad * 3
    tool = kernel.transform(box, translate=tuple(shift))
    cut = kernel.boolean("cut", shape, tool)

    proj = kernel.hlr_project(cut, direction, xdir)
    section = kernel.section_polys(shape, direction, xdir, offset * direction[ax_i]
                                   if direction[ax_i] < 0 else offset)
    all_polys = proj["visible"] + proj["hidden"] + section
    b = hlr.bounds(all_polys)
    size = (b[2] - b[0], b[3] - b[1])

    w, h = SHEETS[sheet]
    avail_w, avail_h = w - 2 * MARGIN - 20, h - 2 * MARGIN - 30
    scale = next((s for s in STANDARD_SCALES
                  if size[0] * s <= avail_w and size[1] * s <= avail_h), 0.01)
    ox, oy = MARGIN + 10, MARGIN + 18

    d = Drawing(sheet=sheet, width=w, height=h, scale=scale,
                title=f"{title} - SECTION A-A ({axis.upper()}={_fmt(offset)})")
    d.views.append(PlacedView(
        name="section",
        visible=_transform(proj["visible"], scale, ox, oy, (b[0], b[1])),
        hidden=_transform(proj["hidden"], scale, ox, oy, (b[0], b[1])),
        label=f"SECTION A-A  ({axis.upper()} = {_fmt(offset)})"))

    section_sheet = _transform(section, scale, ox, oy, (b[0], b[1]))
    loops = _chain_loops(section_sheet)
    d.views.append(PlacedView(
        name="section-outline", visible=loops, hidden=[], label=""))
    d.views.append(PlacedView(
        name="hatch", visible=_hatch_loops(loops, _HATCH_SPACING),
        hidden=[], label=""))
    return d
