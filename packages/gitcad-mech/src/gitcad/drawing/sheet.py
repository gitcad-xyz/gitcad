"""Sheet layout: views arranged third-angle on a standard sheet, auto-scaled,
with overall dimensions and a title block. Output via :mod:`.svg` / :mod:`.pdf`.

Sheets are ISO 5457 (A4 portrait, A3-A0 landscape) or ANSI Y14.1 (A-E); the
frame, grid references and the ISO 7200 title block are drawn by
:mod:`.frame` from :mod:`.formats` data. Title-block fields derive from git
(:mod:`.titleblock`) with explicit overrides via the drawing-settings dict.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gitcad.drawing import hlr
from gitcad.drawing.formats import (FORMATS, STANDARD_SCALES, TITLE_BLOCK_H,
                                    TITLE_BLOCK_W, fitted_scale, pick_sheet,
                                    scale_text)
from gitcad.drawing.titleblock import TitleBlock, resolve_title_block

Point = tuple[float, float]

# Trimmed (w, h) per sheet name — kept for the section/assembly modules.
# ISO 5457 makes A4 portrait; that is the one deliberate size migration
# (task #139): every drawing already carried an implied sheet + title block,
# so the whole engine moved to the standard formats together.
SHEETS = {name: (f.width, f.height) for name, f in FORMATS.items()}
MARGIN = 12.0       # legacy inset (pre-#139); layout now uses the format frame
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
    """A leader annotation: anchor point on geometry, label offset away.
    ``balloon`` renders the text circled — a BOM item balloon."""
    anchor: Point
    label: Point
    text: str
    balloon: bool = False


@dataclass
class SurfaceFinish:
    """ISO 1302 surface-texture symbol at (x, y): the tick, an optional
    'all around' circle, and the roughness value (µm Ra)."""
    x: float
    y: float
    ra: float
    all_around: bool = False


@dataclass
class WeldSymbol:
    """ISO 2553 / AWS weld symbol: an arrow to (ax, ay), a reference line
    starting at (x, y), a weld-type flag on it, and the size."""
    x: float
    y: float
    ax: float
    ay: float
    weld: str = "fillet"        # fillet | square | vee
    size: float = 0.0


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
    surface_finishes: list[SurfaceFinish] = field(default_factory=list)
    welds: list[WeldSymbol] = field(default_factory=list)
    block: TitleBlock | None = None     # resolved title-block fields (data)

    def surface_finish(self, x, y, ra, *, all_around=False) -> "Drawing":
        self.surface_finishes.append(SurfaceFinish(x, y, ra, all_around))
        return self

    def weld(self, x, y, ax, ay, *, weld="fillet", size=0.0) -> "Drawing":
        self.welds.append(WeldSymbol(x, y, ax, ay, weld, size))
        return self

    def to_svg(self) -> str:
        from gitcad.drawing.svg import render_svg
        return render_svg(self)

    def to_pdf(self) -> bytes:
        from gitcad.drawing.pdf import render_pdf
        return render_pdf(self)


def _fmt(v: float) -> str:
    """A dimension text that says what the model says.

    This used to be a one-decimal fixed format, which printed a Ø11.96
    shaft as ``12`` (#72). On a drawing — what a shop cuts from — 0.04 mm is
    not a display preference, it is the whole clearance to the Ø12.00 bore
    it has to enter.

    Fixed to ``_DIM_DECIMALS`` places (which absorbs float residue: 0.1+0.2
    must print 0.3, not 0.30000000000000004), then trailing zeros dropped —
    the decimal point survives the strip, so 120.0 stays "120". Gives
    11.96 -> "11.96", 12.0 -> "12", 2.50 -> "2.5", 0.05 -> "0.05".
    """
    return f"{float(v):.{_DIM_DECIMALS}f}".rstrip("0").rstrip(".")


# a micron is finer than any mechanical drawing needs, and coarse enough
# that binary-float residue never survives to the sheet
_DIM_DECIMALS = 4


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


def _count_top_holes(kernel, shape) -> int:
    """Unique z-axis cylindrical holes — the dims that will stack left of and
    above the top view, so the layout reserves room for them up front."""
    try:
        faces = kernel.entities(shape, "face")
    except Exception:            # noqa: BLE001 — reservation only, never fatal
        return 0
    seen = set()
    for f in faces:
        if f.get("surface") == "cylinder" and abs(abs(f["axis_dir"][2]) - 1.0) < 1e-6:
            seen.add((round(f["axis_origin"][0], 6), round(f["axis_origin"][1], 6),
                      round(f["radius"], 6)))
    return len(seen)


def make_drawing(shape, kernel=None, *, title: str = "part", sheet: str = "A3",
                 thread_specs: dict | None = None,
                 notes: list | None = None,
                 details: list | None = None,
                 bom: list | None = None,
                 settings: dict | None = None) -> Drawing:
    """Project ``shape`` into front/top/right/iso via the kernel's HLR engine,
    lay out third-angle on the sheet, add overall dimensions.

    ``sheet`` names an ISO 5457 (``A4``-``A0``) or ANSI Y14.1 (``ANSI A``-
    ``ANSI E``) format, or ``"auto"`` / ``"auto:ansi"`` to pick the smallest
    sheet of the series holding the views at a standard scale. ``settings``
    is the drawing-settings dict: title-block overrides (owner,
    drawing_number, revision, date, author, approved_by, units, sheet_no,
    sheet_count) plus ``source_path`` for the git-derived fields.
    """
    if kernel is None:
        from gitcad.kernel import get_kernel

        kernel = get_kernel()          # forge HLR (ADR-0020) — no OCCT needed
    settings = settings or {}
    if settings.get("projection") == "first":
        raise ValueError(
            "make_drawing lays views out in third-angle projection; a "
            "first-angle title-block symbol would misstate the sheet")

    proj = {v: hlr.project(kernel, shape, v) for v in ("front", "top", "right", "iso")}
    bb = {v: hlr.bounds(p["visible"] + p["hidden"]) for v, p in proj.items()}
    size = {v: (bb[v][2] - bb[v][0], bb[v][3] - bb[v][1]) for v in bb}
    need_w = size["front"][0] + size["right"][0] + size["iso"][0]
    need_h = size["front"][1] + size["top"][1]

    if sheet.startswith("auto"):
        sheet, _ = pick_sheet(need_w, need_h,
                              "ansi" if sheet.endswith("ansi") else "iso")
    fmt = FORMATS[sheet]
    w, h = fmt.width, fmt.height
    fx0, fy0, fx1, fy1 = fmt.frame

    # Title-block fields resolve before layout: the revision table (git log)
    # and BOM table claim sheet height above the block, and views must start
    # above that whole bottom band — the block spans the full frame on A4.
    block = resolve_title_block(title=title, scale=scale_text(1.0),
                                sheet_name=sheet, settings=settings)
    from gitcad.drawing.frame import revision_table_height

    band = TITLE_BLOCK_H + revision_table_height(block)
    if bom:
        band += 2.0 + 3.6 * (min(len(bom), 14) + 1 + (1 if len(bom) > 14 else 0))

    # Reserved bands inside the frame: stacked hole-position dims left of and
    # above the top view, the title block band at the bottom.
    n_holes = _count_top_holes(kernel, shape)
    left_inset = DIM_OFFSET * (n_holes + 1) + 8
    top_reserve = DIM_OFFSET * n_holes + 4

    # Auto-scale: front+right across, front+top down, iso shares the top row.
    fx, fy = fx0 + left_inset, fy0 + band + DIM_OFFSET + 6
    avail_w = (fx1 - fx0) - left_inset - 2 * GAP
    avail_h = (fy1 - 2) - fy - GAP - top_reserve
    scale = fitted_scale(need_w, need_h, avail_w, avail_h)

    d = Drawing(sheet=sheet, width=w, height=h, scale=scale, title=title)
    block.scale = scale_text(scale)
    d.block = block

    # Third-angle placement (sheet coords, y up): front bottom-left; top above
    # front; right beside front; iso in the top-right corner.
    placements = {
        "front": (fx, fy),
        "top": (fx, fy + size["front"][1] * scale + GAP),
        "right": (fx + size["front"][0] * scale + GAP, fy),
        "iso": (fx1 - 2 - size["iso"][0] * scale,
                fy1 - 2 - size["iso"][1] * scale),
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
    detail_x = fx1 - 2.0
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
        ox, oy = detail_x, fy0 + band + 4.0
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
        ny = fy0 + 18.0 + 5.0 * i
        d.callouts.append(Callout((fx0 + 2.0, ny), (fx0 + 2.0, ny),
                                  str(note)))
    if bom:
        _add_bom(d, bom, placements["front"], bb["front"], scale, fmt)
    return d


def _add_bom(d: Drawing, bom: list, front_origin: Point, front_bounds,
             scale: float, fmt) -> None:
    """BOM table above the title block + numbered balloons on the front view.

    ``bom`` lines come from :func:`gitcad.drawing.bom.model_bom`: item, qty,
    label, and world-mm anchors. Balloons land on the front view (front u = X,
    v = Z per :data:`hlr.VIEWS`), so the balloon numbers and the table can
    never disagree — same list, same order.
    """
    fx, fy = front_origin
    bx0, by0 = front_bounds[0], front_bounds[1]

    max_rows = 14
    rows = bom[:max_rows]
    text_rows = ["ITEM QTY  PART"]
    text_rows += [f"{ln['item']:<4} {ln['qty']:<4} {ln['label']}" for ln in rows]
    if len(bom) > max_rows:
        # no silent caps: the drop is written on the drawing itself
        text_rows.append(f"... {len(bom) - max_rows} more lines not shown")
    line_h = 3.6
    from gitcad.drawing.frame import revision_table_height

    # aligned with the ISO 7200 block, stacked above it (and above the
    # revision table when the git log put one there)
    x0 = fmt.width - fmt.right - TITLE_BLOCK_W + 1.5
    base = fmt.bottom + TITLE_BLOCK_H + revision_table_height(d.block) + 2.0
    y_top = base + line_h * len(text_rows)
    for i, row in enumerate(text_rows):
        d.notes.append((x0, y_top - line_h * i, row))

    for ln in bom:
        for k, (ax, _ay, az) in enumerate(ln.get("anchors", ())[:6]):
            sx = fx + (ax - bx0) * scale
            sy = fy + (az - by0) * scale
            d.callouts.append(Callout(
                (sx, sy), (sx + 8.0, sy + 8.0 + 3.0 * (k % 3)),
                str(ln["item"]), balloon=True))


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
