"""Assembly drawings (SW-manual FR3): top view + balloons + BOM table.

Balloon numbers are the BOM item numbers — the same ``assembly_bom`` that
feeds procurement feeds the drawing, so the table and the balloons can never
disagree. Instances with model geometry are HLR-projected; bought parts
without geometry contribute their interface envelope rectangle (drawn
hidden-style) so every balloon still points at something real.
"""

from __future__ import annotations

from gitcad.drawing import hlr
from gitcad.drawing.sheet import (GAP, MARGIN, SHEETS, STANDARD_SCALES,
                                  Callout, Drawing, PlacedView, _transform)
from gitcad.part.assembly import Assembly
from gitcad.part.bought import assembly_bom

Point = tuple[float, float]


def assembly_drawing(asm: Assembly, kernel=None, *,
                     models: dict | None = None, exploded=None,
                     title: str | None = None, sheet: str = "A3") -> Drawing:
    """``models`` maps instance name -> built Document for instances with
    geometry (part.json's body.model is a file reference — the caller owns
    resolution, same split as the viewer). Instances without a document fall
    back to their interface envelope, drawn hidden-style. ``exploded`` takes
    an ExplodedView spec (ADR-0014): the drawing shows the exploded state,
    balloons follow, and the assembly text is untouched."""
    if kernel is None:
        from gitcad.kernel import get_kernel

        kernel = get_kernel(require="occt")
    if exploded is not None:
        asm = exploded.apply(asm)

    shapes = []
    env_rects: list[list[Point]] = []          # world-mm envelope outlines
    anchors: dict[str, Point] = {}             # instance -> world (x, y)
    for name, inst in sorted(asm.instances.items()):
        doc = (models or {}).get(name)
        if doc is not None:
            placed = kernel.transform(doc.build(kernel).final(doc),
                                      translate=inst.translate,
                                      rotate_axis=(0, 0, 1),
                                      rotate_deg=inst.rotate_z_deg)
            shapes.append(placed)
            (lo, hi) = kernel.bbox(placed)
            anchors[name] = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
        else:
            eb = inst.envelope_bounds()
            if eb is None:
                continue   # no geometry, no envelope — nothing to point at
            (x1, y1, _), (x2, y2, _) = eb
            env_rects.append([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)])
            anchors[name] = ((x1 + x2) / 2, (y1 + y2) / 2)

    proj = (kernel.hlr_project(kernel.compound(shapes), (0, 0, 1), (1, 0, 0))
            if shapes else {"visible": [], "hidden": []})
    all_polys = proj["visible"] + proj["hidden"] + env_rects
    b = hlr.bounds(all_polys)
    size = (b[2] - b[0], b[3] - b[1])

    w, h = SHEETS[sheet]
    table_w = 96.0
    avail_w = w - 2 * MARGIN - table_w - GAP
    avail_h = h - 2 * MARGIN - 30
    scale = next((s for s in STANDARD_SCALES
                  if size[0] * s <= avail_w and size[1] * s <= avail_h), 0.01)
    ox, oy = MARGIN + 10, MARGIN + 18

    d = Drawing(sheet=sheet, width=w, height=h, scale=scale,
                title=title or f"{asm.name} - assembly")
    d.views.append(PlacedView(
        name="top",
        visible=_transform(proj["visible"], scale, ox, oy, (b[0], b[1])),
        hidden=_transform(proj["hidden"] + env_rects, scale, ox, oy, (b[0], b[1])),
        label="TOP"))

    # Balloons: BOM item number circled at each instance, leader to geometry.
    lines = assembly_bom(asm)
    to_sheet = lambda mx, my: (ox + (mx - b[0]) * scale, oy + (my - b[1]) * scale)  # noqa: E731
    for item_no, line in enumerate(lines, start=1):
        for iname in line["instances"]:
            if iname not in anchors:
                continue
            ax, ay = to_sheet(*anchors[iname])
            d.callouts.append(Callout((ax, ay), (ax + 9.0, ay + 9.0),
                                      f"({item_no})"))

    # BOM table, top-right: ITEM | QTY | NAME/MPN — same lines, same order.
    tx = w - MARGIN - table_w
    ty = h - MARGIN - 6
    d.notes.append((tx, ty, "ITEM  QTY  PART"))
    for item_no, line in enumerate(lines, start=1):
        if line["type"] == "bought":
            mfr = line.get("manufacturer", "")
            label = f"{line['mpn']} ({mfr})" if mfr else line["mpn"]
        else:
            label = f"{line['name']}@{line['version']}"
        d.notes.append((tx, ty - 5.0 * item_no,
                        f"{item_no:<5} {line['qty']:<4} {label}"))
    return d
