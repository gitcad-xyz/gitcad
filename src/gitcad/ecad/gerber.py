"""Gerber X2 writer (RS-274X with X2 file-function attributes).

Deterministic by construction: apertures are collected in sorted order and
coordinates are fixed-format integers (4.6, mm), so the same board text yields
byte-identical Gerbers on any machine — which makes fab outputs diffable and
release-reproducible (ADR-0004/0009).

v0.1 layers: top/bottom copper, top/bottom solder mask, top silkscreen
(courtyards + no text yet), and the board profile.
"""

from __future__ import annotations

import gitcad
from gitcad.ecad.board import Board

_SCALE = 1_000_000  # 4.6 format: mm * 1e6


def _c(v: float) -> int:
    return round(v * _SCALE)


class _GerberFile:
    def __init__(self, function: str, polarity: str = "Positive") -> None:
        self.head = [
            f"%TF.GenerationSoftware,gitcad,gitcad,{gitcad.__version__}*%",
            f"%TF.FileFunction,{function}*%",
            f"%TF.FilePolarity,{polarity}*%",
            "%FSLAX46Y46*%",
            "%MOMM*%",
            "%LPD*%",
        ]
        self._apertures: dict[str, int] = {}
        self._ops: list[tuple[int, list[str]]] = []  # (aperture, commands)

    def aperture(self, spec: str) -> int:
        """Register an aperture template (e.g. 'C,0.800000') and return its D-code."""
        if spec not in self._apertures:
            self._apertures[spec] = 0  # numbered later, deterministically
        return 0

    def flash(self, spec: str, x: float, y: float) -> None:
        self._op(spec, [f"X{_c(x)}Y{_c(y)}D03*"])

    def line(self, spec: str, x1: float, y1: float, x2: float, y2: float) -> None:
        self._op(spec, [f"X{_c(x1)}Y{_c(y1)}D02*", f"X{_c(x2)}Y{_c(y2)}D01*"])

    def _op(self, spec: str, commands: list[str]) -> None:
        self.aperture(spec)
        self._ops.append((spec, commands))  # type: ignore[arg-type]

    def render(self) -> str:
        # Deterministic aperture numbering: sorted specs, D10 upward.
        numbers = {spec: 10 + i for i, spec in enumerate(sorted(self._apertures))}
        lines = list(self.head)
        for spec in sorted(numbers, key=numbers.get):
            lines.append(f"%ADD{numbers[spec]}{spec}*%")
        current = None
        for spec, commands in self._ops:
            code = numbers[spec]
            if code != current:
                lines.append(f"D{code}*")
                current = code
            lines.extend(commands)
        lines.append("M02*")
        return "\n".join(lines) + "\n"


def _pad_spec(w: float, h: float, shape: str) -> str:
    if shape == "circle":
        return f"C,{max(w, h):.6f}"
    if shape == "obround":
        return f"O,{w:.6f}X{h:.6f}"
    return f"R,{w:.6f}X{h:.6f}"


def copper(board: Board, side: str) -> str:
    layer = "L1,Top" if side == "top" else "L2,Bot"
    g = _GerberFile(f"Copper,{layer}")
    for comp in board.components:
        for pad, bx, by, rot in comp.placed_pads():
            on_this_side = pad.drill is not None or comp.side == side
            if not on_this_side:
                continue
            w, h = (pad.h, pad.w) if round(rot) % 180 == 90 else (pad.w, pad.h)
            g.flash(_pad_spec(w, h, pad.shape), bx, by)
    for t in board.tracks:
        if t.layer == side:
            g.line(f"C,{t.width:.6f}", t.x1, t.y1, t.x2, t.y2)
    for v in board.vias:
        g.flash(f"C,{v.diameter:.6f}", v.x, v.y)
    return g.render()


def mask(board: Board, side: str) -> str:
    """Solder mask openings (negative layer): pad shapes expanded per side."""
    g = _GerberFile(f"Soldermask,{'Top' if side == 'top' else 'Bot'}", polarity="Negative")
    e2 = board.mask_expansion * 2
    for comp in board.components:
        for pad, bx, by, rot in comp.placed_pads():
            if pad.drill is None and comp.side != side:
                continue
            w, h = (pad.h, pad.w) if round(rot) % 180 == 90 else (pad.w, pad.h)
            g.flash(_pad_spec(w + e2, h + e2, pad.shape), bx, by)
    return g.render()


def silkscreen(board: Board, side: str = "top") -> str:
    """Component courtyard outlines. Reference text lands in a later release."""
    g = _GerberFile(f"Legend,{'Top' if side == 'top' else 'Bot'}")
    pen = "C,0.150000"
    for comp in board.components:
        if comp.side != side or comp.footprint.courtyard is None:
            continue
        cw, ch = comp.footprint.courtyard
        if round(comp.rot) % 180 == 90:   # courtyard follows the rotation
            cw, ch = ch, cw
        x0, y0 = comp.x - cw / 2, comp.y - ch / 2
        corners = [(x0, y0), (x0 + cw, y0), (x0 + cw, y0 + ch), (x0, y0 + ch), (x0, y0)]
        for (x1, y1), (x2, y2) in zip(corners, corners[1:]):
            g.line(pen, x1, y1, x2, y2)
    return g.render()


def profile(board: Board) -> str:
    g = _GerberFile("Profile,NP")
    pen = "C,0.100000"
    pts = list(board.outline)
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        g.line(pen, x1, y1, x2, y2)
    return g.render()
