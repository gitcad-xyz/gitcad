"""Excellon (NC drill) writer — plated holes from through-pads and vias.

Deterministic: tools are numbered by sorted drill diameter, coordinates in
fixed decimal mm.
"""

from __future__ import annotations

from gitcad._version import __version__ as _gitcad_version
from gitcad.ecad.board import Board


def _render(holes: list[tuple[float, float, float]]) -> str:
    diameters = sorted({d for d, _, _ in holes})
    tool_of = {d: i + 1 for i, d in enumerate(diameters)}

    lines = ["M48", f";GenerationSoftware,gitcad,{_gitcad_version}", "METRIC,TZ"]
    for d in diameters:
        lines.append(f"T{tool_of[d]:02d}C{d:.3f}")
    lines.append("%")
    lines.append("G90")
    lines.append("G05")
    for d in diameters:
        lines.append(f"T{tool_of[d]:02d}")
        for dd, x, y in sorted(holes):
            if dd == d:
                lines.append(f"X{x:.3f}Y{y:.3f}")
    lines.append("M30")
    return "\n".join(lines) + "\n"


def drills(board: Board) -> str:
    """Plated holes (through-hole pads + vias), one METRIC Excellon file."""
    holes: list[tuple[float, float, float]] = []  # (diameter, x, y)
    for comp in board.components:
        for pad, bx, by, _ in comp.placed_pads():
            if pad.drill is not None:
                holes.append((pad.drill, bx, by))
    for v in board.vias:
        holes.append((v.drill, v.x, v.y))
    return _render(holes)


def npth_drills(board: Board) -> str:
    """Non-plated holes (mounting holes) — fabs require these in a separate
    file from plated holes."""
    return _render([(m.drill, m.x, m.y) for m in board.mounting_holes])
