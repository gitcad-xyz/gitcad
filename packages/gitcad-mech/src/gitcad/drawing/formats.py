"""Standard sheet formats: ISO 5457 (A4-A0) and ANSI/ASME Y14.1 (A-E).

Trimmed sizes are the page; untrimmed sizes ride along as data (ISO 5457
table 1). The frame (drawing space) insets are the standard margins: ISO
keeps a 20 mm filing margin on the left and 10 mm elsewhere — so the A3
frame is 390x277 inside 420x297. ANSI uses a uniform half-inch margin.
Grid-reference zone counts follow the 50 mm (ISO) / zone-table (ANSI)
conventions. A4 is portrait per ISO 5457; every other sheet is landscape.

Scales are the ISO 5455 series; the auto-pick chooses from this list only,
so the title block always shows a true standard ratio.
"""

from __future__ import annotations

from dataclasses import dataclass

_IN = 25.4


@dataclass(frozen=True)
class SheetFormat:
    name: str
    width: float                  # trimmed, mm
    height: float                 # trimmed, mm
    style: str                    # "iso" | "ansi"
    left: float                   # frame margins (mm from trimmed edge)
    right: float
    top: float
    bottom: float
    cols: int                     # grid-reference divisions along the width
    rows: int                     # ... along the height (0 = no grid)
    untrimmed: tuple[float, float]

    @property
    def frame(self) -> tuple[float, float, float, float]:
        """Frame rectangle (x0, y0, x1, y1) in sheet mm, y up."""
        return (self.left, self.bottom, self.width - self.right,
                self.height - self.top)


def _iso(name, w, h, cols, rows, uw, uh):
    return SheetFormat(name, w, h, "iso", 20.0, 10.0, 10.0, 10.0,
                       cols, rows, (uw, uh))


def _ansi(name, w_in, h_in, cols, rows):
    return SheetFormat(name, round(w_in * _IN, 2), round(h_in * _IN, 2),
                       "ansi", 12.7, 12.7, 12.7, 12.7, cols, rows,
                       (round(w_in * _IN, 2), round(h_in * _IN, 2)))


FORMATS: dict[str, SheetFormat] = {f.name: f for f in (
    # ISO 5457: A4 portrait, the rest landscape; ~50 mm reference zones
    _iso("A4", 210.0, 297.0, 4, 6, 240.0, 330.0),
    _iso("A3", 420.0, 297.0, 8, 6, 450.0, 330.0),
    _iso("A2", 594.0, 420.0, 12, 8, 625.0, 450.0),
    _iso("A1", 841.0, 594.0, 16, 12, 880.0, 625.0),
    _iso("A0", 1189.0, 841.0, 24, 16, 1230.0, 880.0),
    # ANSI/ASME Y14.1 (landscape; A has no zones)
    _ansi("ANSI A", 11.0, 8.5, 0, 0),
    _ansi("ANSI B", 17.0, 11.0, 4, 2),
    _ansi("ANSI C", 22.0, 17.0, 4, 4),
    _ansi("ANSI D", 34.0, 22.0, 8, 4),
    _ansi("ANSI E", 44.0, 34.0, 8, 8),
)}

ISO_SERIES = ["A4", "A3", "A2", "A1", "A0"]
ANSI_SERIES = ["ANSI A", "ANSI B", "ANSI C", "ANSI D", "ANSI E"]

# ISO 5455 scale series, magnification first (the existing pick order:
# the largest standard scale on which the views still fit wins).
STANDARD_SCALES = [20.0, 10.0, 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02]

TITLE_BLOCK_W = 180.0   # ISO 7200 maximum width — full frame width on A4
TITLE_BLOCK_H = 24.0


def scale_text(scale: float) -> str:
    """True ratio text for the title block: 2:1 / 1:1 / 1:5."""
    if scale >= 1.0:
        return f"{float(scale):g}:1"
    return f"1:{float(1.0 / scale):g}"


def fitted_scale(need_w: float, need_h: float, avail_w: float,
                 avail_h: float) -> float:
    """Largest standard scale at which (need_w, need_h) fits, else the
    smallest of the series — the caller sees a true (if tiny) ratio."""
    return next((s for s in STANDARD_SCALES
                 if need_w * s <= avail_w and need_h * s <= avail_h),
                STANDARD_SCALES[-1])


def _avail(fmt: SheetFormat) -> tuple[float, float]:
    """Usable drawing area: the frame minus title-block clearance and a
    working margin (mirrors the layout insets in :mod:`.sheet`)."""
    x0, y0, x1, y1 = fmt.frame
    return (x1 - x0 - 50.0, y1 - y0 - TITLE_BLOCK_H - 40.0)


def pick_sheet(need_w: float, need_h: float, series: str = "iso",
               ) -> tuple[str, float]:
    """Auto-pick: the smallest sheet of the series that holds the views at
    full size (1:1) or larger; if none does, the sheet whose fitted standard
    scale is largest (ties go to the smaller sheet). Returns (name, scale).
    """
    names = ANSI_SERIES if series == "ansi" else ISO_SERIES
    best: tuple[str, float] | None = None
    for name in names:
        aw, ah = _avail(FORMATS[name])
        s = fitted_scale(need_w, need_h, aw, ah)
        if s >= 1.0:
            return name, s
        if best is None or s > best[1]:
            best = (name, s)
    return best if best else (names[-1], STANDARD_SCALES[-1])
