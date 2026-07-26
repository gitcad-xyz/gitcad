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
    """Plated through holes (through-hole pads + full-span vias), one METRIC
    Excellon file. Blind/buried vias are separate drilling operations —
    ``span_drills`` emits those."""
    copper = board.copper_layers()
    holes: list[tuple[float, float, float]] = []  # (diameter, x, y)
    for comp in board.components:
        for pad, bx, by, _ in comp.placed_pads():
            if pad.drill is not None:
                holes.append((pad.drill, bx, by))
    for v in board.vias:
        if v.kind(copper) == "through":
            holes.append((v.drill, v.x, v.y))
    return _render(holes)


def span_drills(board: Board) -> dict[tuple[str, str], str]:
    """Blind/buried drill files, one per distinct span — each span is a
    separate drilling (or lamination-stage) operation at the fab. Empty on
    all-through boards, so 2-layer output is untouched."""
    copper = board.copper_layers()
    by_span: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
    for v in board.vias:
        if v.span(copper) and v.kind(copper) != "through":
            by_span.setdefault((v.layer_from, v.layer_to), []).append(
                (v.drill, v.x, v.y))
    order = {name: i for i, name in enumerate(copper)}
    return {span: _render(holes)
            for span, holes in sorted(by_span.items(),
                                      key=lambda kv: (order[kv[0][0]], order[kv[0][1]]))}


def npth_drills(board: Board) -> str:
    """Non-plated holes (mounting holes) — fabs require these in a separate
    file from plated holes."""
    return _render([(m.drill, m.x, m.y) for m in board.mounting_holes])
