"""Standard sheets + ISO 7200 title block on real drawings (task #139).

The geometry half (the pure-data half is ``test_sheet_formats.py``): a part
rendered through make_drawing lands on an ISO 5457 / ANSI Y14.1 sheet with
the frame, grid references, centring marks and the ISO 7200 title block,
views and dimensions stay inside the frame, and the PDF page is exactly the
paper size in points. Coordinates asserted here come from the standards:
the ISO 5457 A3 frame is 390x277 inside 420x297; the block is 180 mm wide.
"""

from __future__ import annotations

import re

import pytest

from gitcad.drawing import make_drawing
from gitcad.drawing.formats import FORMATS, STANDARD_SCALES


@pytest.fixture(scope="module")
def kernel():
    from gitcad.kernel.ref import RefKernel

    return RefKernel()


def _bracket(kernel):
    plate = kernel.box(60, 40, 8)
    for x, y in ((12, 12), (48, 28)):
        plate = kernel.boolean(
            "cut", plate, kernel.transform(kernel.cylinder(3.2, 8), translate=(x, y, 0)))
    return plate


def _rect_attrs(svg: str, cls: str) -> list[dict[str, float]]:
    out = []
    for m in re.finditer(r'<rect([^>]*class="%s"[^>]*)/>' % cls, svg):
        t = m.group(1)
        out.append({k: float(re.search(k + r'="([-\d.]+)"', t).group(1))
                    for k in ("x", "y", "width", "height")})
    return out


def test_a4_drawing_is_portrait(kernel) -> None:
    d = make_drawing(kernel.box(30, 20, 5), kernel, sheet="A4")
    assert (d.width, d.height) == (210.0, 297.0)


# -- the ISO 5457 frame --------------------------------------------------------

def test_iso_a3_frame_is_390_by_277(kernel) -> None:
    svg = make_drawing(_bracket(kernel), kernel, sheet="A3").to_svg()
    frames = _rect_attrs(svg, "frame")
    assert len(frames) == 1
    f = frames[0]
    # 20 left, 10 right/top/bottom (SVG y-down: top-left corner at (20, 10))
    assert (f["x"], f["y"], f["width"], f["height"]) == (20.0, 10.0, 390.0, 277.0)


def test_iso_a4_frame_is_180_by_277(kernel) -> None:
    svg = make_drawing(kernel.box(30, 20, 5), kernel, sheet="A4").to_svg()
    f = _rect_attrs(svg, "frame")[0]
    assert (f["x"], f["y"], f["width"], f["height"]) == (20.0, 10.0, 180.0, 277.0)


def test_grid_references_and_centring_marks(kernel) -> None:
    svg = make_drawing(_bracket(kernel), kernel, sheet="A3").to_svg()
    refs = re.findall(r'class="ref"[^>]*>([^<]+)</text>', svg)
    # A3: 6 rows (A-F) on both vertical sides, 8 columns (1-8) top and bottom
    assert refs.count("A") == 2 and refs.count("F") == 2
    assert refs.count("1") == 2 and refs.count("8") == 2
    assert "G" not in refs and "9" not in refs
    assert svg.count('class="cm"') == 4          # four centring marks


# -- the ISO 7200 title block --------------------------------------------------

def test_title_block_is_180_wide_anchored_bottom_right(kernel) -> None:
    svg = make_drawing(_bracket(kernel), kernel, sheet="A3").to_svg()
    b = _rect_attrs(svg, "block")[0]
    assert b["width"] == 180.0
    assert b["x"] == 410.0 - 180.0               # against the frame's right edge
    assert b["y"] + b["height"] == 287.0         # against the frame's bottom edge


def test_title_block_fields_from_settings(kernel) -> None:
    d = make_drawing(_bracket(kernel), kernel, sheet="A3", title="bracket",
                     settings={"owner": "ACME GmbH", "drawing_number": "GC-1042",
                               "revision": "B", "date": "2026-07-27",
                               "author": "dwillis", "approved_by": "qa-bot",
                               "sheet_no": 2, "sheet_count": 5})
    svg = d.to_svg()
    for value in ("ACME GmbH", "GC-1042", "2026-07-27", "dwillis", "qa-bot"):
        assert value in svg
    assert "2/5" in svg                          # sheet n/N
    # overrides are recorded as data on the drawing, not just baked into text
    assert d.block.drawing_number == "GC-1042"
    assert d.block.overrides["owner"] == "ACME GmbH"


def test_block_scale_is_true_and_from_the_standard_series(kernel) -> None:
    d = make_drawing(_bracket(kernel), kernel, sheet="A3")
    assert d.scale in STANDARD_SCALES
    assert d.block.scale in ("2:1", "1:1", "1:2")
    assert f">{d.block.scale}<" in d.to_svg()


def test_detail_views_annotate_their_own_scale(kernel) -> None:
    d = make_drawing(_bracket(kernel), kernel, sheet="A3",
                     details=[{"cx": 12.0, "cy": 12.0, "r": 6.0, "scale": 2.0}])
    labels = [v.label for v in d.views if v.name.startswith("detail")]
    assert labels and "2:1" in labels[0]         # per-view scale, ISO style


def test_make_drawing_refuses_first_angle(kernel) -> None:
    # make_drawing lays views out third-angle; a first-angle symbol would lie
    with pytest.raises(ValueError):
        make_drawing(kernel.box(10, 10, 10), kernel, settings={"projection": "first"})


# -- sheet auto-pick and PDF page size -----------------------------------------

def test_auto_sheet_on_make_drawing(kernel) -> None:
    d = make_drawing(kernel.box(500, 300, 100), kernel, sheet="auto")
    assert d.sheet in ("A2", "A1", "A0")
    assert d.scale in STANDARD_SCALES


def _mediabox(pdf: bytes) -> tuple[float, float]:
    m = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", pdf)
    return float(m.group(1)), float(m.group(2))


def test_pdf_page_size_matches_paper_exactly(kernel) -> None:
    box = kernel.box(30, 20, 5)
    w, h = _mediabox(make_drawing(box, kernel, sheet="A4").to_pdf())
    assert abs(w - 210 * 72 / 25.4) < 0.01 and abs(h - 297 * 72 / 25.4) < 0.01
    w, h = _mediabox(make_drawing(box, kernel, sheet="A3").to_pdf())
    assert abs(w - 420 * 72 / 25.4) < 0.01 and abs(h - 297 * 72 / 25.4) < 0.01
    w, h = _mediabox(make_drawing(box, kernel, sheet="ANSI B").to_pdf())
    assert abs(w - 1224.0) < 0.01 and abs(h - 792.0) < 0.01   # 17 x 11 in


# -- content stays inside the frame --------------------------------------------

@pytest.mark.parametrize("sheet", ["A4", "A3", "ANSI B"])
def test_views_and_dims_land_inside_the_frame(kernel, sheet) -> None:
    d = make_drawing(_bracket(kernel), kernel, sheet=sheet)
    fmt = FORMATS[sheet]
    x0, x1 = fmt.left, d.width - fmt.right
    y0, y1 = fmt.bottom, d.height - fmt.top
    pts = [p for v in d.views for poly in v.visible + v.hidden for p in poly]
    pts += [d1 for dim in d.dims for d1 in (dim.p1, dim.p2)]
    for x, yv in pts:
        assert x0 - 1e-6 <= x <= x1 + 1e-6, (sheet, x, (x0, x1))
        assert y0 - 1e-6 <= yv <= y1 + 1e-6, (sheet, yv, (y0, y1))


def test_section_view_clears_the_title_block(kernel) -> None:
    from gitcad.drawing.sections import make_section_drawing

    d = make_section_drawing(_bracket(kernel), kernel, axis="x", offset=12)
    fmt = FORMATS[d.sheet]
    block_top = fmt.bottom + 24.0
    pts = [p for v in d.views for poly in v.visible + v.hidden for p in poly]
    assert pts
    for x, yv in pts:
        assert fmt.left <= x <= d.width - fmt.right
        assert block_top < yv <= d.height - fmt.top
