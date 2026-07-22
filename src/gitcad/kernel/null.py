"""Pure-Python null kernel — a dependency-free test backend.

It does NOT do real b-rep. Primitives carry analytic mass properties, and
booleans/fillets are tracked *symbolically* (as a provenance tree) so the
document model, stable-identity assignment, and the reducer can all be exercised
in CI with no OCCT wheel installed.

Why this exists: keeping a real kernel-free backend behind the same seam means
the bulk of the test suite runs in milliseconds and agents can iterate on the
non-geometry layers without a 400 MB dependency (see README "Quick start").
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from gitcad.errors import ValidationReport
from gitcad.seams import Shape


@dataclass
class NullShape:
    """A symbolic shape: either an analytic primitive or an op over children."""

    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    children: tuple["NullShape", ...] = ()

    def volume(self) -> float | None:
        """Analytic volume for primitives; ``None`` when a boolean makes it
        undecidable without real geometry (honest about the backend's limits)."""
        if self.kind == "box":
            return self.params["dx"] * self.params["dy"] * self.params["dz"]
        if self.kind == "cylinder":
            return math.pi * self.params["radius"] ** 2 * self.params["height"]
        if self.kind == "sphere":
            return 4.0 / 3.0 * math.pi * self.params["radius"] ** 3
        if self.kind in ("fillet", "transform"):
            return self.children[0].volume()  # rigid / small perturbation
        return None  # boolean/cone: unknown analytically here


class NullKernel:
    """Implements the :class:`gitcad.seams.Kernel` protocol structurally."""

    name = "null"

    def box(self, dx: float, dy: float, dz: float) -> Shape:
        _require_positive(dx=dx, dy=dy, dz=dz)
        return NullShape("box", {"dx": dx, "dy": dy, "dz": dz})

    def cylinder(self, radius: float, height: float) -> Shape:
        _require_positive(radius=radius, height=height)
        return NullShape("cylinder", {"radius": radius, "height": height})

    def sphere(self, radius: float) -> Shape:
        _require_positive(radius=radius)
        return NullShape("sphere", {"radius": radius})

    def cone(self, r1: float, r2: float, height: float) -> Shape:
        _require_positive(r1=r1, height=height)
        return NullShape("cone", {"r1": r1, "r2": r2, "height": height})

    def transform(self, shape: Shape, *, translate: tuple[float, float, float] = (0, 0, 0),
                  rotate_axis: tuple[float, float, float] = (0, 0, 1), rotate_deg: float = 0.0) -> Shape:
        # Rigid transforms preserve volume; track symbolically.
        return NullShape("transform", {"translate": list(translate),
                                       "rotate_axis": list(rotate_axis),
                                       "rotate_deg": rotate_deg}, (shape,))

    def export_step(self, shape: Shape, path: str) -> None:
        raise NotImplementedError("STEP export requires the OCCT backend (pip install 'gitcad[occt]')")

    def export_stl(self, shape: Shape, path: str, *, deflection: float = 0.1) -> None:
        raise NotImplementedError("STL export requires the OCCT backend (pip install 'gitcad[occt]')")

    def boolean(self, op: str, a: Shape, b: Shape) -> Shape:
        if op not in {"union", "cut", "intersect"}:
            raise ValueError(f"unknown boolean op {op!r}")
        return NullShape("boolean", {"op": op}, (a, b))

    def fillet(self, shape: Shape, edges: list[str], radius: float) -> Shape:
        _require_positive(radius=radius)
        return NullShape("fillet", {"edges": list(edges), "radius": radius}, (shape,))

    def entities(self, shape: Shape, kind: str) -> list[dict[str, Any]]:
        """Deterministic synthetic topology so identity assignment is testable.
        A box gets 6 faces / 12 edges / 8 vertices with stable descriptors that
        do NOT depend on enumeration order."""
        if not isinstance(shape, NullShape):
            return []
        if shape.kind == "box" and kind == "face":
            dx, dy, dz = shape.params["dx"], shape.params["dy"], shape.params["dz"]
            areas = {"+x": dy * dz, "-x": dy * dz, "+y": dx * dz, "-y": dx * dz, "+z": dx * dy, "-z": dx * dy}
            return [{"surface": "plane", "normal": n, "area": a} for n, a in sorted(areas.items())]
        return []

    def validate(self, shape: Shape) -> ValidationReport:
        # The null backend can only assert structural well-formedness.
        ok = isinstance(shape, NullShape)
        return ValidationReport(ok=ok, checks={"backend": "null", "watertight": None})

    def measure(self, shape: Shape) -> dict[str, float]:
        vol = shape.volume() if isinstance(shape, NullShape) else None
        out: dict[str, float] = {}
        if vol is not None:
            out["volume"] = vol
        return out


def _require_positive(**kw: float) -> None:
    for k, v in kw.items():
        if not (isinstance(v, (int, float)) and v > 0):
            raise ValueError(f"{k} must be positive, got {v!r}")
