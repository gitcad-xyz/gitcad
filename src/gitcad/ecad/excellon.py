"""Excellon (NC drill) writer — plated holes from through-pads and vias.

Deterministic: tools are numbered by sorted drill diameter, coordinates in
fixed decimal mm.
"""

from __future__ import annotations

from gitcad.ecad.board import Board


def drills(board: Board) -> str:
    """All plated holes (through-hole pads + vias), one METRIC Excellon file."""
    holes: list[tuple[float, float, float]] = []  # (diameter, x, y)
    for comp in board.components:
        for pad, bx, by, _ in comp.placed_pads():
            if pad.drill is not None:
                holes.append((pad.drill, bx, by))
    for v in board.vias:
        holes.append((v.drill, v.x, v.y))

    diameters = sorted({d for d, _, _ in holes})
    tool_of = {d: i + 1 for i, d in enumerate(diameters)}

    lines = ["M48", ";GenerationSoftware,gitcad,0.1.0", "METRIC,TZ"]
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
