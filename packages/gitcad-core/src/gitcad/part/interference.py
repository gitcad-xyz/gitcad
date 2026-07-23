"""Real interference checking — co-design upgraded from "probably fits" to
"provably fits" (list item 4).

Envelope AABBs (Assembly.validate) are the fast pre-filter; this module is
the exact check: place each instance's real geometry with its transform and
boolean-intersect every pair. A nonzero common volume is a collision, with
the overlap measured in mm³ — not a guess, a measurement. Face-on-face
contact (mated parts touching) intersects with zero volume and passes.
"""

from __future__ import annotations

from gitcad.errors import ValidationReport
from gitcad.seams import Kernel, Shape

_VOL_TOL = 1e-6  # mm^3 — below this, "intersection" is contact/noise


def check_interference(
    kernel: Kernel,
    instances: dict[str, tuple[Shape, tuple[float, float, float], float]],
    *,
    ignore: set[frozenset[str]] | None = None,
    tol_mm3: float | None = None,
) -> ValidationReport:
    """``instances``: name -> (shape, translate, rotate_z_deg). ``ignore``:
    pairs (as frozensets of names) intentionally in contact/overlap.
    ``tol_mm3``: allowed overlap volume per pair (None = exact, the strict
    default; a clash budget like 1.0 matches common enclosure practice).
    The pairwise overlap matrix is always reported — a passing check still
    shows HOW CLOSE it passed."""
    ignore = ignore or set()
    tol = _VOL_TOL if tol_mm3 is None else tol_mm3

    placed: dict[str, Shape] = {}
    boxes: dict[str, tuple] = {}
    for name, (shape, translate, rot_z) in instances.items():
        s = kernel.transform(shape, translate=translate,
                             rotate_axis=(0, 0, 1), rotate_deg=rot_z)
        placed[name] = s
        boxes[name] = kernel.bbox(s)

    def aabb_overlaps(a, b) -> bool:
        (alo, ahi), (blo, bhi) = a, b
        return all(alo[i] <= bhi[i] and blo[i] <= ahi[i] for i in range(3))

    violations: list[str] = []
    overlaps: dict[str, float] = {}
    names = sorted(placed)
    checked = 0
    for i, na in enumerate(names):
        for nb in names[i + 1:]:
            if frozenset({na, nb}) in ignore:
                continue
            if not aabb_overlaps(boxes[na], boxes[nb]):
                continue   # envelope pre-filter: cannot collide
            checked += 1
            common = kernel.boolean("intersect", placed[na], placed[nb])
            vol = kernel.measure(common).get("volume", 0.0)
            if vol > _VOL_TOL:
                overlaps[f"{na}<->{nb}"] = round(vol, 4)
            if vol > tol:
                violations.append(f"interference:{na}<->{nb}:overlap={vol:.3f}mm3")

    return ValidationReport(
        ok=not violations,
        checks={"instances": len(instances), "pairs_intersected": checked,
                "overlaps_mm3": overlaps, "tol_mm3": tol,
                "method": "exact-boolean-common", "kernel": kernel.name},
        violations=violations,
    )
