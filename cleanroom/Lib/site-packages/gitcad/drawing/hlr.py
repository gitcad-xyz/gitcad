"""View definitions for hidden-line-removal projection.

The actual HLR math lives behind the Kernel seam (``Kernel.hlr_project`` —
ADR-0002); this module owns the *drafting* vocabulary: named views with their
projection direction and sheet x-direction, plus 2D bounds helpers.
"""

from __future__ import annotations

from gitcad.seams import Kernel, Shape

Polyline = list[tuple[float, float]]

# Named views: (projection direction, x-direction of the sheet).
# Third-angle-friendly conventions; +Y on the sheet is derived (dir × xdir).
VIEWS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "front": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),
    "top":   ((0.0, 0.0, 1.0),  (1.0, 0.0, 0.0)),
    "right": ((1.0, 0.0, 0.0),  (0.0, 1.0, 0.0)),
    "iso":   ((1.0, 1.0, 1.0),  (1.0, -1.0, 0.0)),
}


def project(kernel: Kernel, shape: Shape, view: str, *,
            deflection: float = 0.05) -> dict[str, list[Polyline]]:
    """Project ``shape`` into the named view via the kernel's HLR engine."""
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r} (want one of {sorted(VIEWS)})")
    direction, xdir = VIEWS[view]
    return kernel.hlr_project(shape, direction, xdir, deflection=deflection)


def bounds(polys: list[Polyline]) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) over a polyline set."""
    xs = [x for poly in polys for x, _ in poly]
    ys = [y for poly in polys for _, y in poly]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))
