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
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.2f} {h_pt:.2f}] "
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
    s: list[str] = [f"{MM:.6f} 0 0 {MM:.6f} 0 0 cm", "1 J 1 j"]

    def polyline(poly, width: float, dash: str | None = None) -> None:
        s.append(f"{width:.3f} w")
        s.append(f"[{dash}] 0 d" if dash else "[] 0 d")
        (x0, y0), *rest = poly
        s.append(f"{x0:.3f} {y0:.3f} m")
        for x, y in rest:
            s.append(f"{x:.3f} {y:.3f} l")
        s.append("S")

    def text(x: float, y: float, size: float, value: str, rotate90: bool = False) -> None:
        if rotate90:
            s.append(f"BT /F1 {size:.2f} Tf 0 1 -1 0 {x:.3f} {y:.3f} Tm ({_esc(value)}) Tj ET")
        else:
            s.append(f"BT /F1 {size:.2f} Tf {x:.3f} {y:.3f} Td ({_esc(value)}) Tj ET")

    # Border
    polyline([(5, 5), (d.width - 5, 5), (d.width - 5, d.height - 5), (5, d.height - 5), (5, 5)], 0.3)

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

    # Title block (bottom right)
    w, h = 92.0, 20.0
    x0, y0 = d.width - 5 - w, 5.0
    polyline([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)], 0.3)
    text(x0 + 3, y0 + h - 6.5, 3.5, d.title)
    text(x0 + 3, y0 + h - 12.0, 3.0, f"SCALE {d.scale:g}:1   UNITS mm   SHEET {d.sheet}")
    text(x0 + 3, y0 + 2.5, 3.0, "gitcad - generated drawing")

    return "\n".join(s).encode("latin-1", errors="replace")
