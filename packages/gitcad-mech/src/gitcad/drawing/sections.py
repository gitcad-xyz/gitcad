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
from gitcad.drawing.sheet import (STANDARD_SCALES, Drawing, PlacedView, _fmt,
                                  _transform)
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
                         sheet: str = "A4",
                         settings: dict | None = None) -> Drawing:
    """One-view section drawing: SECTION A-A at ``axis = offset``.

    Material on the viewer side of the plane is removed; the cut surface is
    hatched. The view direction looks along -axis (the drafting arrows).
    ``settings`` feeds the ISO 7200 title block (see :func:`.make_drawing`)."""
    if kernel is None:
        from gitcad.kernel import get_kernel

        kernel = get_kernel()          # forge section_polys (ADR-0020)
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
    # The viewer is on the -direction side (hlr: smaller dot(P,direction) is
    # nearer). Remove the NEAR half so the cut face is revealed, not occluded:
    # for +direction axes the near half is coord < offset (tool below the
    # plane); for -direction axes it is coord > offset (tool above).
    shift[ax_i] = offset - pad * 3 if direction[ax_i] > 0 else offset
    tool = kernel.transform(box, translate=tuple(shift))
    # Half-space cut-away removes the material between viewer and plane so the
    # projection reveals the interior. Forge can't yet half-space-cut a solid
    # with cylindrical bores (the cut would produce partial-cylinder walls it
    # can't represent — K2.2); when it refuses, project the whole body. The
    # section outline + hatch below (the defining content) stay exact either way.
    from gitcad.errors import KernelError
    try:
        cut = kernel.boolean("cut", shape, tool)
    except KernelError:
        cut = shape

    proj = kernel.hlr_project(cut, direction, xdir)
    section = kernel.section_polys(shape, direction, xdir, offset * direction[ax_i]
                                   if direction[ax_i] < 0 else offset)
    all_polys = proj["visible"] + proj["hidden"] + section
    b = hlr.bounds(all_polys)
    size = (b[2] - b[0], b[3] - b[1])

    from gitcad.drawing.formats import FORMATS, TITLE_BLOCK_H

    fmt = FORMATS[sheet]
    w, h = fmt.width, fmt.height
    fx0, fy0, fx1, fy1 = fmt.frame
    # the view starts above the ISO 7200 title block, inside the frame
    ox, oy = fx0 + 12.0, fy0 + TITLE_BLOCK_H + 14.0
    avail_w, avail_h = fx1 - ox - 4.0, fy1 - oy - 8.0
    scale = next((s for s in STANDARD_SCALES
                  if size[0] * s <= avail_w and size[1] * s <= avail_h), 0.01)

    d = Drawing(sheet=sheet, width=w, height=h, scale=scale,
                title=f"{title} - SECTION A-A ({axis.upper()}={_fmt(offset)})")
    from gitcad.drawing.formats import scale_text
    from gitcad.drawing.titleblock import resolve_title_block

    d.block = resolve_title_block(title=d.title, scale=scale_text(scale),
                                  sheet_name=sheet, settings=settings,
                                  part_name=title)
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
