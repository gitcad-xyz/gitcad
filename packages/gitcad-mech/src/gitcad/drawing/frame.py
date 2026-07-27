"""Sheet furniture: the ISO 5457 / ANSI Y14.1 frame and the ISO 7200 title
block, as renderer-neutral primitives.

Both output backends (:mod:`.svg`, :mod:`.pdf`) consume the same primitive
lists, so the frame geometry exists exactly once. All coordinates are sheet
millimetres, y **up**; the SVG renderer flips. A :class:`~.sheet.Drawing`
whose (width, height) does not match its named format — hand-built test
sheets, cropped canvases — keeps the legacy plain border, so opting into a
standard sheet is a property of the drawing, never a silent global change.

Primitives:
  rects:   (cls, x, y, w, h)          outline rectangles
  lines:   (cls, [(x, y), ...])       polylines
  circles: (cls, cx, cy, r)
  texts:   (cls, x, y, h, s, anchor)  baseline at (x, y), height h mm,
                                      anchor in {start, middle, end}
cls encodes line weight / text role: "frame" and "cm" are wide (0.7 mm),
"thin" is 0.35 mm; text cls "ref" marks grid references.
"""

from __future__ import annotations

from gitcad.drawing.formats import (FORMATS, TITLE_BLOCK_H, TITLE_BLOCK_W,
                                    SheetFormat, scale_text)
from gitcad.drawing.titleblock import TitleBlock

REV_ROW_H = 5.0


def projection_symbol(cx: float, cy: float, h: float, projection: str) -> dict:
    """ISO 128-34 projection symbol: the truncated cone, front view
    (trapezoid) beside its view from the small end (two concentric
    circles). Third angle: the view sits on the side it was taken from, so
    the narrow end points **toward** the circles; first angle: the view is
    projected through to the far side, narrow end points **away**."""
    length, gap, big, small = 1.2 * h, 0.4 * h, 0.5 * h, 0.25 * h
    total = length + gap + 2 * big
    x0 = cx - total / 2                    # trapezoid left edge
    ccx = x0 + length + gap + big          # circle centre
    if projection == "third":
        left_h, right_h = big, small       # narrow end toward the circles
    else:
        left_h, right_h = small, big       # narrow end away from them
    lines = [("thin", [(x0, cy - left_h), (x0, cy + left_h),
                       (x0 + length, cy + right_h), (x0 + length, cy - right_h),
                       (x0, cy - left_h)])]
    circles = [("thin", ccx, cy, big), ("thin", ccx, cy, small)]
    return {"lines": lines, "circles": circles}


def _grid_references(fmt: SheetFormat) -> dict:
    """Zone ticks + labels in the margin band. ISO counts letters from the
    top down and numbers left to right; ANSI counts from the bottom-right
    corner (letters up, numbers leftward)."""
    x0, y0, x1, y1 = fmt.frame
    lines: list = []
    texts: list = []
    if not fmt.cols or not fmt.rows:
        return {"lines": lines, "texts": texts}
    tick = 5.0
    # column boundaries + numbers (top and bottom bands)
    zw = (x1 - x0) / fmt.cols
    for i in range(1, fmt.cols):
        bx = x0 + i * zw
        lines.append(("thin", [(bx, y1), (bx, y1 + tick)]))
        lines.append(("thin", [(bx, y0), (bx, y0 - tick)]))
    for i in range(fmt.cols):
        n = i + 1 if fmt.style == "iso" else fmt.cols - i
        tx = x0 + (i + 0.5) * zw
        texts.append(("ref", tx, y1 + 1.2, 2.5, str(n), "middle"))
        texts.append(("ref", tx, y0 - 3.7, 2.5, str(n), "middle"))
    # row boundaries + letters (left and right bands)
    zh = (y1 - y0) / fmt.rows
    for i in range(1, fmt.rows):
        by = y0 + i * zh
        lines.append(("thin", [(x0, by), (x0 - tick, by)]))
        lines.append(("thin", [(x1, by), (x1 + tick, by)]))
    for i in range(fmt.rows):
        idx = fmt.rows - 1 - i if fmt.style == "iso" else i   # ISO: A at top
        letter = chr(ord("A") + idx)
        ty = y0 + (i + 0.5) * zh - 1.25
        texts.append(("ref", x0 - 2.5, ty, 2.5, letter, "middle"))
        texts.append(("ref", x1 + 2.5, ty, 2.5, letter, "middle"))
    return {"lines": lines, "texts": texts}


def _centring_marks(fmt: SheetFormat) -> list:
    """ISO 5457 centring marks: from each trimmed edge to 5 mm past the
    frame line, at the sheet midlines."""
    w, h = fmt.width, fmt.height
    x0, y0, x1, y1 = fmt.frame
    return [
        ("cm", [(0.0, h / 2), (x0 + 5.0, h / 2)]),
        ("cm", [(w, h / 2), (x1 - 5.0, h / 2)]),
        ("cm", [(w / 2, h), (w / 2, y1 - 5.0)]),
        ("cm", [(w / 2, 0.0), (w / 2, y0 + 5.0)]),
    ]


def _cell(out: dict, x: float, y: float, w: float, h: float,
          label: str, value: str, *, value_h: float = 3.0,
          center: bool = False) -> None:
    """One labelled title-block cell: tiny label upper-left, value inside."""
    out["lines"].append(("thin", [(x, y), (x, y + h)]))
    if label:
        out["texts"].append(("micro", x + 1.0, y + h - 2.6, 1.8, label, "start"))
    if value:
        if center:
            out["texts"].append(("val", x + w / 2, y + 1.6, value_h, value,
                                 "middle"))
        else:
            out["texts"].append(("val", x + 1.2, y + 1.6, value_h, value,
                                 "start"))


def _title_block(fmt: SheetFormat, block: TitleBlock) -> dict:
    """ISO 7200 title block, 180 mm wide, anchored to the frame's
    bottom-right corner; the ANSI variant swaps the scale cell for a
    SIZE cell carrying the sheet letter."""
    x0f, y0f, x1f, y1f = fmt.frame
    bw, bh = min(TITLE_BLOCK_W, x1f - x0f), TITLE_BLOCK_H
    bx, by = x1f - bw, y0f
    row = bh / 3.0

    out: dict = {"rects": [("block", bx, by, bw, bh)],
                 "lines": [("thin", [(bx, by + row), (bx + bw, by + row)]),
                           ("thin", [(bx, by + 2 * row), (bx + bw, by + 2 * row)])],
                 "circles": [], "texts": []}

    # top row: owner | drawn by | date
    _cell(out, bx, by + 2 * row, 80, row, "OWNER", block.owner)
    _cell(out, bx + 80, by + 2 * row, 55, row, "DRAWN", block.author)
    _cell(out, bx + 135, by + 2 * row, 45, row, "DATE", block.date)
    # middle row: title | drawing number | revision
    _cell(out, bx, by + row, 80, row, "TITLE", block.title)
    _cell(out, bx + 80, by + row, 70, row, "DWG NO", block.drawing_number)
    _cell(out, bx + 150, by + row, 30, row, "REV", block.revision, center=True)
    # bottom row: scale/size | units | projection | sheet | approved
    if fmt.style == "ansi":
        _cell(out, bx, by, 30, row, "SIZE", fmt.name.split()[-1], center=True)
        _cell(out, bx + 30, by, 25, row, "SCALE", block.scale, value_h=2.5,
              center=True)
    else:
        _cell(out, bx, by, 30, row, "SCALE", block.scale, center=True)
        _cell(out, bx + 30, by, 25, row, "UNITS", block.units, center=True)
    _cell(out, bx + 55, by, 25, row, "PROJ", "")
    sym = projection_symbol(bx + 55 + 12.5, by + row / 2 - 0.4, 3.2,
                            block.projection)
    out["lines"] += sym["lines"]
    out["circles"] += sym["circles"]
    if fmt.style == "ansi":
        _cell(out, bx + 80, by, 25, row, "UNITS", block.units, center=True)
        _cell(out, bx + 105, by, 35, row, "SHEET",
              f"{block.sheet_no}/{block.sheet_count}", center=True)
    else:
        _cell(out, bx + 80, by, 35, row, "SHEET",
              f"{block.sheet_no}/{block.sheet_count}", center=True)
        _cell(out, bx + 115, by, 25, row, "FMT", fmt.name, center=True)
    _cell(out, bx + 140, by, 40, row, "APPD", block.approved_by, value_h=2.5)

    # revision-history table above the block, newest first
    if block.revisions:
        n = len(block.revisions)
        ty = by + bh
        out["rects"].append(("thin", bx, ty, bw, REV_ROW_H * (n + 1)))
        cols = (18.0, 42.0)              # REV | DATE | DESCRIPTION splits
        for cx in cols:
            out["lines"].append(("thin", [(bx + cx, ty),
                                          (bx + cx, ty + REV_ROW_H * (n + 1))]))
        head_y = ty + REV_ROW_H * n
        out["lines"].append(("thin", [(bx, head_y), (bx + bw, head_y)]))
        for label, cx in (("REV", 1.2), ("DATE", cols[0] + 1.2),
                          ("DESCRIPTION", cols[1] + 1.2)):
            out["texts"].append(("micro", bx + cx, head_y + 1.4, 2.0, label,
                                 "start"))
        for i, (rev, date, desc) in enumerate(block.revisions):
            ry = head_y - REV_ROW_H * (i + 1) + 1.4
            out["lines"].append(("thin", [(bx, ry - 1.4 + REV_ROW_H),
                                          (bx + bw, ry - 1.4 + REV_ROW_H)]))
            out["texts"].append(("val", bx + 1.2, ry, 2.2, rev, "start"))
            out["texts"].append(("val", bx + cols[0] + 1.2, ry, 2.2, date,
                                 "start"))
            out["texts"].append(("val", bx + cols[1] + 1.2, ry, 2.2,
                                 desc[:60], "start"))
    return out


def revision_table_height(block: TitleBlock | None) -> float:
    """Sheet mm claimed above the title block by the revision table."""
    if block is None or not block.revisions:
        return 0.0
    return REV_ROW_H * (len(block.revisions) + 1)


def sheet_furniture(d) -> dict:
    """Frame + title block primitives for a Drawing, or the legacy plain
    border when the drawing does not carry a standard sheet."""
    fmt = FORMATS.get(d.sheet)
    if fmt is None or (fmt.width, fmt.height) != (d.width, d.height):
        return _legacy(d)
    block = getattr(d, "block", None) or TitleBlock(
        title=d.title, scale=scale_text(d.scale), sheet_name=d.sheet)
    x0, y0, x1, y1 = fmt.frame
    out = {"rects": [("frame", x0, y0, x1 - x0, y1 - y0)],
           "lines": [], "circles": [], "texts": []}
    if fmt.style == "iso":
        out["lines"] += _centring_marks(fmt)
    grid = _grid_references(fmt)
    out["lines"] += grid["lines"]
    out["texts"] += grid["texts"]
    tb = _title_block(fmt, block)
    for key in ("rects", "lines", "circles", "texts"):
        out[key] += tb[key]
    return out


def _legacy(d) -> dict:
    """The pre-#139 sheet: a 5 mm border and the small generic block."""
    w, h = 92.0, 20.0
    x0, y0 = d.width - 5 - w, 5.0
    return {
        "rects": [("legacy", 5.0, 5.0, d.width - 10.0, d.height - 10.0),
                  ("legacy", x0, y0, w, h)],
        "lines": [], "circles": [],
        "texts": [
            ("lbl", x0 + 3, y0 + h - 5.2, 3.5, d.title, "start"),
            ("val", x0 + 3, y0 + h - 10.6, 3.0,
             f"SCALE {float(d.scale):g}:1   UNITS mm   SHEET {d.sheet}",
             "start"),
            ("val", x0 + 3, y0 + h - 15.6, 3.0,
             "gitcad - generated drawing", "start"),
        ],
    }
