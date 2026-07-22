"""Parametric footprint generators (KiCad-map P5) — wizards, agent-first.

KiCad's footprint wizards are dialogs; here they are functions: give the
package family and its parameters, get a correct ``Footprint`` with IPC-ish
pad sizes and a courtyard. This multiplies the registry — one generator
covers every pin count and pitch of a family, and an MPN part just binds
facts to a generated footprint.
"""

from __future__ import annotations

from gitcad.ecad.board import Footprint, Pad
from gitcad.errors import GitcadError

# chip (imperial name): body l x w, pad w x h, pad center offset from origin
_CHIP = {
    "0402": (1.0, 0.5, 0.6, 0.62, 0.48),
    "0603": (1.6, 0.8, 0.9, 0.95, 0.75),
    "0805": (2.0, 1.25, 1.0, 1.45, 0.95),
    "1206": (3.2, 1.6, 1.15, 1.8, 1.45),
}


def chip(size: str) -> Footprint:
    """Two-terminal chip package (R/C/L/LED) by imperial size code."""
    if size not in _CHIP:
        raise GitcadError(f"unknown chip size {size!r} (want {sorted(_CHIP)})")
    body_l, _body_w, pad_w, pad_h, off = _CHIP[size]
    return Footprint(
        name=f"CHIP-{size}",
        pads=[Pad("1", -off, 0, pad_w, pad_h), Pad("2", off, 0, pad_w, pad_h)],
        courtyard=(round(2 * off + pad_w + 0.4, 2), round(pad_h + 0.4, 2)))


def soic(n: int, *, pitch: float = 1.27, row_span: float = 5.4,
         pad_w: float = 0.6, pad_h: float = 1.5) -> Footprint:
    """SOIC/SSOP gull-wing: two rows, pin 1 top-left, counter-clockwise."""
    if n < 4 or n % 2:
        raise GitcadError("soic needs an even pin count >= 4")
    per_side = n // 2
    top = (per_side - 1) * pitch / 2
    pads = []
    for i in range(per_side):        # left column: 1..n/2 top to bottom
        pads.append(Pad(str(i + 1), -row_span / 2, top - i * pitch, pad_w, pad_h))
    for i in range(per_side):        # right column: n/2+1..n bottom to top
        pads.append(Pad(str(per_side + i + 1), row_span / 2,
                        -top + i * pitch, pad_w, pad_h))
    return Footprint(
        name=f"SOIC-{n}",
        pads=pads,
        courtyard=(round(row_span + pad_w + 0.5, 2),
                   round((per_side - 1) * pitch + pad_h + 0.5, 2)))


def qfn(n: int, *, pitch: float = 0.5, body: float = 4.0,
        pad_w: float = 0.28, pad_l: float = 0.8,
        ep: float | None = None) -> Footprint:
    """QFN: four sides, pin 1 left-top, counter-clockwise; optional exposed
    pad (named EP, netless until assigned)."""
    if n < 8 or n % 4:
        raise GitcadError("qfn needs a pin count divisible by 4, >= 8")
    per_side = n // 4
    span = (per_side - 1) * pitch / 2
    edge = body / 2
    pads = []
    for i in range(per_side):        # left, top->bottom
        pads.append(Pad(str(i + 1), -edge, span - i * pitch, pad_l, pad_w))
    for i in range(per_side):        # bottom, left->right
        pads.append(Pad(str(per_side + i + 1), -span + i * pitch, -edge,
                        pad_w, pad_l))
    for i in range(per_side):        # right, bottom->top
        pads.append(Pad(str(2 * per_side + i + 1), edge, -span + i * pitch,
                        pad_l, pad_w))
    for i in range(per_side):        # top, right->left
        pads.append(Pad(str(3 * per_side + i + 1), span - i * pitch, edge,
                        pad_w, pad_l))
    if ep:
        pads.append(Pad("EP", 0, 0, ep, ep))
    c = round(body + pad_l + 0.5, 2)
    return Footprint(name=f"QFN-{n}", pads=pads, courtyard=(c, c))


def header(n: int, *, pitch: float = 2.54, rows: int = 1,
           drill: float = 1.0, annular: float = 0.7) -> Footprint:
    """Through-hole pin header, pin 1 at top of column 1."""
    if n < 1 or rows not in (1, 2) or n % rows:
        raise GitcadError("header needs n >= 1 divisible by rows (1 or 2)")
    per_col = n // rows
    top = (per_col - 1) * pitch / 2
    dia = drill + 2 * annular
    pads = []
    for r in range(rows):
        x = (r - (rows - 1) / 2) * pitch
        for i in range(per_col):
            pads.append(Pad(str(r * per_col + i + 1), x, top - i * pitch,
                            dia, dia, "circle", drill))
    return Footprint(
        name=f"HDR-{rows}x{per_col}",
        pads=pads,
        courtyard=(round(rows * pitch + 0.6, 2),
                   round(per_col * pitch + 0.6, 2)))


GENERATORS = {"chip": chip, "soic": soic, "qfn": qfn, "header": header}


def generate(kind: str, **params) -> Footprint:
    if kind not in GENERATORS:
        raise GitcadError(f"unknown footprint family {kind!r} "
                          f"(want {sorted(GENERATORS)})")
    return GENERATORS[kind](**params)
