"""Sheet layout: views arranged third-angle on a standard sheet, auto-scaled,
with overall dimensions and a title block. Output via :mod:`.svg` / :mod:`.pdf`.
"""

from __future__ import annotations

import math
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
class Callout:
    """A leader annotation: anchor point on geometry, label offset away."""
    anchor: Point
    label: Point
    text: str


@dataclass
class Drawing:
    sheet: str
    width: float
    height: float
    scale: float
    title: str
    views: list[PlacedView] = field(default_factory=list)
    dims: list[Dimension] = field(default_factory=list)
    callouts: list[Callout] = field(default_factory=list)
    notes: list[tuple[float, float, str]] = field(default_factory=list)

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


def _clip_poly_to_circle(poly, cx: float, cy: float, r: float):
    """Sub-polylines of ``poly`` inside the circle — exact segment clipping
    (quadratic in the segment parameter), for detail views."""
    out: list[list[Point]] = []
    run: list[Point] = []

    def inside(px, py):
        return (px - cx) ** 2 + (py - cy) ** 2 <= r * r

    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        dx, dy = x2 - x1, y2 - y1
        a = dx * dx + dy * dy
        fx, fy = x1 - cx, y1 - cy
        b = 2 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - r * r
        ts: list[float] = []
        if a > 1e-12:
            disc = b * b - 4 * a * c
            if disc > 0:
                sq = math.sqrt(disc)
                ts = sorted(t for t in ((-b - sq) / (2 * a), (-b + sq) / (2 * a))
                            if 0.0 < t < 1.0)
        pts = [(x1, y1)] + [(x1 + t * dx, y1 + t * dy) for t in ts] + [(x2, y2)]
        for (ax, ay), (bx2, by2) in zip(pts, pts[1:]):
            mx, my = (ax + bx2) / 2, (ay + by2) / 2
            if inside(mx, my):
                if not run:
                    run = [(ax, ay)]
                run.append((bx2, by2))
            elif run:
                out.append(run)
                run = []
    if run:
        out.append(run)
    return out


def make_drawing(shape, kernel=None, *, title: str = "part", sheet: str = "A3",
                 thread_specs: dict | None = None,
                 notes: list | None = None,
                 details: list | None = None) -> Drawing:
    """Project ``shape`` into front/top/right/iso via the kernel's HLR engine,
    lay out third-angle on the sheet, add overall dimensions."""
    if kernel is None:
        from gitcad.kernel import get_kernel

        kernel = get_kernel(require="occt")
    w, h = SHEETS[sheet]

    proj = {v: hlr.project(kernel, shape, v) for v in ("front", "top", "right", "iso")}
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

    # Detail views (SW-map P8): circle-clipped scaled crops of the TOP view.
    # Each spec is model-space {cx, cy, r, scale (default 2)}; the parent
    # view gets a circle marker + letter, the crop lands bottom-right.
    tx0, ty0 = placements["top"]
    b_top = bb["top"]
    detail_x = w - MARGIN
    for di, spec in enumerate(details or []):
        letter = chr(ord("A") + di)
        dcx, dcy, dr = spec["cx"], spec["cy"], spec["r"]
        dscale = spec.get("scale", 2.0) * scale
        # marker on the parent top view (sheet coords)
        mcx = tx0 + (dcx - b_top[0]) * scale
        mcy = ty0 + (dcy - b_top[1]) * scale
        mr = dr * scale
        circle = [(mcx + mr * math.cos(a), mcy + mr * math.sin(a))
                  for a in [i * math.tau / 32 for i in range(33)]]
        d.views[[v.name for v in d.views].index("top")].visible.append(circle)
        d.callouts.append(Callout((mcx + mr * 0.7071, mcy + mr * 0.7071),
                                  (mcx + mr + 3.0, mcy + mr + 3.0), letter))
        # the crop itself, rescaled and placed bottom-right, right-to-left
        clipped_v = [c for poly in proj["top"]["visible"]
                     for c in _clip_poly_to_circle(poly, dcx, dcy, dr)]
        clipped_h = [c for poly in proj["top"]["hidden"]
                     for c in _clip_poly_to_circle(poly, dcx, dcy, dr)]
        box = 2 * dr * dscale
        detail_x -= box + GAP
        ox, oy = detail_x, MARGIN + 30.0
        d.views.append(PlacedView(
            name=f"detail_{letter}",
            visible=_transform(clipped_v, dscale, ox, oy, (dcx - dr, dcy - dr)),
            hidden=_transform(clipped_h, dscale, ox, oy, (dcx - dr, dcy - dr)),
            label=f"DETAIL {letter}  ({_fmt(spec.get('scale', 2.0))}:1)"))

    _add_hole_dimensions(d, kernel, shape, placements["top"], bb["top"], scale,
                         thread_specs or {})
    # notes block (GD&T table, general tolerances): stacked bottom-left,
    # rendered through the existing callout machinery (zero-length leader)
    for i, note in enumerate(notes or []):
        ny = 28.0 + 5.0 * i
        d.callouts.append(Callout((MARGIN + 2.0, ny), (MARGIN + 2.0, ny),
                                  str(note)))
    return d


def _add_hole_dimensions(d: Drawing, kernel, shape, top_origin: Point,
                         top_bounds, scale: float,
                         thread_specs: dict | None = None) -> None:
    """Derived (associative) hole dimensions on the top view: a Ø-callout per
    unique hole plus x/y position dims from the part datum. Derived from the
    kernel's face enumeration — the same geometry source feature recognition
    uses — so regenerating the drawing after a model edit updates every value.
    Failures degrade to an undimensioned (but correct) drawing, never a crash.
    """
    try:
        faces = kernel.entities(shape, "face")
    except NotImplementedError:
        return
    holes: dict[tuple, tuple[float, float, float]] = {}
    for f in faces:
        if f.get("surface") == "cylinder" and abs(abs(f["axis_dir"][2]) - 1.0) < 1e-6:
            hx, hy = round(f["axis_origin"][0], 6), round(f["axis_origin"][1], 6)
            holes[(hx, hy, round(f["radius"], 6))] = (hx, hy, f["radius"])
    if not holes:
        return

    ox, oy = top_origin
    bx, by = top_bounds[0], top_bounds[1]
    to_sheet = lambda mx, my: (ox + (mx - bx) * scale, oy + (my - by) * scale)  # noqa: E731
    top_h = (top_bounds[3] - top_bounds[1]) * scale

    for i, (hx, hy, r) in enumerate(sorted(holes.values())):
        cx, cy = to_sheet(hx, hy)
        rs = r * scale
        # Ø-callout: leader from the circle's 45° edge point outward.
        k = 0.7071
        anchor = (cx + rs * k, cy + rs * k)
        spec = (thread_specs or {}).get((round(hx, 3), round(hy, 3)))
        label = f"{spec} (Ø{_fmt(2 * r)})" if spec else f"Ø{_fmt(2 * r)}"
        d.callouts.append(Callout(anchor, (anchor[0] + 5.0, anchor[1] + 5.0),
                                  label))
        # Position dims from the part datum (view min corner), stacked above
        # the view (x) and left of it (y) so multiple holes don't collide.
        x_off = top_h + DIM_OFFSET * (i + 1)
        d.dims.append(Dimension((ox, oy + x_off), (cx, oy + x_off), _fmt(hx - bx)))
        y_off = DIM_OFFSET * (i + 2)   # (i+2): outside the overall-depth dim
        d.dims.append(Dimension((ox - y_off, oy), (ox - y_off, cy),
                                _fmt(hy - by), vertical=True))
