"""Schematic PDF plot — the print/archive projection of a drawn sheet.

Walks the same runtime graphics the SVG fidelity renderer uses (wires,
symbol bodies, labels, powers, subsheet boxes) and emits a minimal
self-contained PDF: stroked vectors + Helvetica text, zero dependencies,
byte-deterministic. Sheet coordinates are KiCad y-down; PDF user space is
y-up — coordinates are flipped here once, in Python, so the content
stream stays trivial.
"""

from __future__ import annotations

from gitcad.ecad.schematic import Schematic
from gitcad.errors import GitcadError

MM = 72.0 / 25.4          # PDF points per mm
_K = 0.5522847498         # Bézier circle constant


def sheet_to_pdf(sch: Schematic) -> bytes:
    """Render a drawn schematic (imported or sheet-authored) to PDF bytes."""
    gfx = getattr(sch, "graphics", None)
    if not gfx:
        raise GitcadError(
            "schematic has no sheet graphics (not imported or sheet-authored) "
            "— PDF plots the drawing, not the netlist")

    xs: list[float] = []
    ys: list[float] = []
    for w in gfx.get("wires", []):
        xs += [w[0], w[2]]; ys += [w[1], w[3]]
    for sym in gfx.get("symbols", {}).values():
        for shp in sym["shapes"]:
            for px, py in shp["pts"]:
                xs.append(px); ys.append(py)
    for lb in gfx.get("labels", []):
        xs.append(lb["x"]); ys.append(lb["y"])
    for p in gfx.get("powers", []):
        xs.append(p["x"]); ys.append(p["y"])
    for ss in gfx.get("sheets", []):
        xs += [ss["x"], ss["x"] + ss["w"]]; ys += [ss["y"], ss["y"] + ss["h"]]
    if not xs:
        raise GitcadError("sheet graphics are empty")
    m = 8.0
    x0, y0 = min(xs) - m, min(ys) - m
    w_mm, h_mm = max(xs) - x0 + m, max(ys) - y0 + m

    def X(x: float) -> float:
        return (x - x0) * MM

    def Y(y: float) -> float:
        return (y0 + h_mm - y) * MM      # KiCad y-down -> PDF y-up

    s: list[str] = ["1 J 1 j"]

    def stroke(width_mm: float) -> None:
        s.append(f"{width_mm * MM:.3f} w")

    def line(x1, y1, x2, y2, width=0.25) -> None:
        stroke(width)
        s.append(f"{X(x1):.3f} {Y(y1):.3f} m {X(x2):.3f} {Y(y2):.3f} l S")

    def polyline(pts, width=0.25, close=False) -> None:
        stroke(width)
        (px, py), *rest = pts
        s.append(f"{X(px):.3f} {Y(py):.3f} m")
        for qx, qy in rest:
            s.append(f"{X(qx):.3f} {Y(qy):.3f} l")
        s.append("s" if close else "S")

    def circle(cx, cy, r, width=0.25, fill=False) -> None:
        stroke(width)
        rk = r * _K
        px, py = X(cx), Y(cy)
        rp = r * MM
        rkp = rk * MM
        s.append(f"{px + rp:.3f} {py:.3f} m")
        s.append(f"{px + rp:.3f} {py + rkp:.3f} {px + rkp:.3f} {py + rp:.3f} {px:.3f} {py + rp:.3f} c")
        s.append(f"{px - rkp:.3f} {py + rp:.3f} {px - rp:.3f} {py + rkp:.3f} {px - rp:.3f} {py:.3f} c")
        s.append(f"{px - rp:.3f} {py - rkp:.3f} {px - rkp:.3f} {py - rp:.3f} {px:.3f} {py - rp:.3f} c")
        s.append(f"{px + rkp:.3f} {py - rp:.3f} {px + rp:.3f} {py - rkp:.3f} {px + rp:.3f} {py:.3f} c")
        s.append("f" if fill else "S")

    def text(x, y, size_mm, value, *, anchor_end=False) -> None:
        est = 0.6 * size_mm * len(value)          # Helvetica width estimate
        tx = X(x) - (est * MM if anchor_end else 0.0)
        s.append(f"BT /F1 {size_mm * MM:.2f} Tf {tx:.3f} {Y(y):.3f} Td ({_esc(value)}) Tj ET")

    # symbol bodies
    for sym in gfx.get("symbols", {}).values():
        for shp in sym["shapes"]:
            pts = shp["pts"]
            if shp["kind"] == "rect":
                (x1, y1), (x2, y2) = pts
                polyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], 0.25, close=True)
            elif shp["kind"] in ("poly", "pin"):
                polyline(pts, 0.25)
            elif shp["kind"] == "circle":
                (cx, cy), = pts
                circle(cx, cy, shp["r"], 0.25)
            elif shp["kind"] == "arc":
                (ax1, ay1), (xm, ym), (ax2, ay2) = pts
                # quadratic through midpoint, as the SVG renderer draws it
                cxq = 2 * xm - (ax1 + ax2) / 2
                cyq = 2 * ym - (ay1 + ay2) / 2
                c1x, c1y = ax1 + 2 / 3 * (cxq - ax1), ay1 + 2 / 3 * (cyq - ay1)
                c2x, c2y = ax2 + 2 / 3 * (cxq - ax2), ay2 + 2 / 3 * (cyq - ay2)
                stroke(0.25)
                s.append(f"{X(ax1):.3f} {Y(ay1):.3f} m "
                         f"{X(c1x):.3f} {Y(c1y):.3f} {X(c2x):.3f} {Y(c2y):.3f} "
                         f"{X(ax2):.3f} {Y(ay2):.3f} c S")

    # ref/value fields
    for comp in sch.components:
        at = comp.attrs.get("at")
        if not at or comp.ref not in gfx.get("symbols", {}):
            continue
        text(at[0] + 1.2, at[1] - 1.2, 1.27, comp.ref)
        if comp.value:
            text(at[0] + 1.2, at[1] + 2.2, 1.27, comp.value)

    for wx in gfx.get("wires", []):
        line(wx[0], wx[1], wx[2], wx[3], 0.25)
    for bx in gfx.get("buses", []):
        line(bx[0], bx[1], bx[2], bx[3], 0.75)
    for be in gfx.get("bus_entries", []):
        line(be[0], be[1], be[2], be[3], 0.25)
    for jx, jy in gfx.get("junctions", []):
        circle(jx, jy, 0.45, fill=True)
    for lb in gfx.get("labels", []):
        text(lb["x"], lb["y"] - 0.4, 1.27, lb["name"],
             anchor_end=lb.get("rot") == 180)
    for p in gfx.get("powers", []):
        # simple glyph: a tick + the rail name (the SVG renderer owns pretty)
        line(p["x"], p["y"], p["x"], p["y"] - 1.2, 0.25)
        text(p["x"] + 0.6, p["y"] - 1.2, 1.1, p["name"])
    for nt in gfx.get("notes", []):
        text(nt["x"], nt["y"], nt.get("size", 1.6), nt["text"])
    for ss in gfx.get("sheets", []):
        polyline([(ss["x"], ss["y"]), (ss["x"] + ss["w"], ss["y"]),
                  (ss["x"] + ss["w"], ss["y"] + ss["h"]),
                  (ss["x"], ss["y"] + ss["h"])], 0.3, close=True)
        text(ss["x"], ss["y"] - 0.6, 1.6, ss["name"])
        for sp in ss.get("pins", []):
            circle(sp["x"], sp["y"], 0.4, 0.25)
            text(sp["x"] + 0.8, sp["y"] + 0.4, 1.1, sp["name"])

    text(x0 + w_mm - 2, y0 + h_mm - 2, 1.6, f"{sch.name} - gitcad sheet",
         anchor_end=True)

    return _wrap_pdf("\n".join(s).encode("latin-1", errors="replace"),
                     w_mm * MM, h_mm * MM)


def _esc(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap_pdf(stream: bytes, w_pt: float, h_pt: float) -> bytes:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.2f} {h_pt:.2f}] "
         f"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>").encode(),
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)
