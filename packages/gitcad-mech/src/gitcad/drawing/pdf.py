"""Minimal PDF writer — vector lines + Helvetica text, zero dependencies.

Enough PDF to ship a manufacturing drawing: one page per Drawing, stroked
polylines (solid + dashed), and text. Deliberately tiny; a richer backend can
replace this behind the DrawingEngine seam without touching callers.
"""

from __future__ import annotations

from gitcad.drawing.sheet import Drawing

MM = 72.0 / 25.4  # PDF user units are points


def render_pdf(d: Drawing) -> bytes:
    w_pt, h_pt = d.width * MM, d.height * MM
    stream = _content_stream(d)

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {float(w_pt):.2f} {float(h_pt):.2f}] "
        f"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>".encode()
    )
    objects.append(
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _esc(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(d: Drawing) -> bytes:
    # Sheet coords are mm y-up; PDF user space is points y-up. One scale, no flip.
    s: list[str] = [f"{float(MM):.6f} 0 0 {float(MM):.6f} 0 0 cm", "1 J 1 j"]

    def polyline(poly, width: float, dash: str | None = None) -> None:
        s.append(f"{float(width):.3f} w")
        s.append(f"[{dash}] 0 d" if dash else "[] 0 d")
        (x0, y0), *rest = poly
        s.append(f"{float(x0):.3f} {float(y0):.3f} m")
        for x, y in rest:
            s.append(f"{float(x):.3f} {float(y):.3f} l")
        s.append("S")

    def text(x: float, y: float, size: float, value: str, rotate90: bool = False) -> None:
        if rotate90:
            s.append(f"BT /F1 {float(size):.2f} Tf 0 1 -1 0 {float(x):.3f} {float(y):.3f} Tm ({_esc(value)}) Tj ET")
        else:
            s.append(f"BT /F1 {float(size):.2f} Tf {float(x):.3f} {float(y):.3f} Td ({_esc(value)}) Tj ET")

    for view in d.views:
        for poly in view.visible:
            polyline(poly, 0.35)
        for poly in view.hidden:
            polyline(poly, 0.18, dash="1.8 1.2")
        if view.visible:
            xs = [x for p in view.visible for x, _ in p]
            ys = [y for p in view.visible for _, y in p]
            text(min(xs), min(ys) - 5.0, 3.5, view.label)

    for dim in d.dims:
        (x1, y1), (x2, y2) = dim.p1, dim.p2
        polyline([(x1, y1), (x2, y2)], 0.13)
        a = 1.2
        if dim.vertical:
            polyline([(x1 - a / 2, y1 + a), (x1, y1), (x1 + a / 2, y1 + a)], 0.13)
            polyline([(x2 - a / 2, y2 - a), (x2, y2), (x2 + a / 2, y2 - a)], 0.13)
            text(x1 - 1.2, (y1 + y2) / 2, 3.0, dim.text, rotate90=True)
        else:
            polyline([(x1 + a, y1 - a / 2), (x1, y1), (x1 + a, y1 + a / 2)], 0.13)
            polyline([(x2 - a, y2 - a / 2), (x2, y2), (x2 - a, y2 + a / 2)], 0.13)
            text((x1 + x2) / 2 - 3, y1 + 1.2, 3.0, dim.text)

    def circle(cx: float, cy: float, r: float) -> None:
        k = 0.552284749 * r
        s.append("0.13 w")
        s.append("[] 0 d")
        s.append(f"{float(cx + r):.3f} {float(cy):.3f} m")
        s.append(f"{float(cx + r):.3f} {float(cy + k):.3f} {float(cx + k):.3f} {float(cy + r):.3f} {float(cx):.3f} {float(cy + r):.3f} c")
        s.append(f"{float(cx - k):.3f} {float(cy + r):.3f} {float(cx - r):.3f} {float(cy + k):.3f} {float(cx - r):.3f} {float(cy):.3f} c")
        s.append(f"{float(cx - r):.3f} {float(cy - k):.3f} {float(cx - k):.3f} {float(cy - r):.3f} {float(cx):.3f} {float(cy - r):.3f} c")
        s.append(f"{float(cx + k):.3f} {float(cy - r):.3f} {float(cx + r):.3f} {float(cy - k):.3f} {float(cx + r):.3f} {float(cy):.3f} c")
        s.append("S")

    for c in d.callouts:
        polyline([c.anchor, c.label], 0.13)
        if getattr(c, "balloon", False):
            circle(c.label[0], c.label[1], 2.6)
            text(c.label[0] - 0.9 * len(c.text), c.label[1] - 1.0, 3.0, c.text)
        else:
            text(c.label[0] + 0.8, c.label[1], 3.0, c.text)

    # notes (BOM tables, headers) — previously dropped on the PDF path
    for nx, ny, value in d.notes:
        text(nx, ny, 3.0, value)

    # Sheet furniture: ISO 5457/ANSI frame + ISO 7200 title block (or the
    # legacy plain border) — same primitives the SVG renderer draws.
    from gitcad.drawing.frame import sheet_furniture

    furn = sheet_furniture(d)
    wide = {"frame": 0.7, "block": 0.7, "cm": 0.7, "legacy": 0.3}
    for cls, x0, y0, rw, rh in furn["rects"]:
        polyline([(x0, y0), (x0 + rw, y0), (x0 + rw, y0 + rh),
                  (x0, y0 + rh), (x0, y0)], wide.get(cls, 0.25))
    for cls, pts in furn["lines"]:
        polyline(pts, wide.get(cls, 0.25))
    for _cls, ccx, ccy, cr in furn["circles"]:
        circle(ccx, ccy, cr)
    for _cls, tx, ty, th, value, anchor in furn["texts"]:
        # Helvetica averages ~0.52 em per glyph — close enough to centre
        # or right-align the short title-block strings.
        dx = {"middle": -0.26, "end": -0.52}.get(anchor, 0.0) * th * len(value)
        text(tx + dx, ty, th, value)

    return "\n".join(s).encode("latin-1", errors="replace")
