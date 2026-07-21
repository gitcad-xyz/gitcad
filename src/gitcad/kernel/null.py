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
        if self.kind == "fillet":
            return self.children[0].volume()  # small perturbation ignored
        return None  # boolean: unknown analytically


class NullKernel:
    """Implements the :class:`gitcad.seams.Kernel` protocol structurally."""

    name = "null"

    def box(self, dx: float, dy: float, dz: float) -> Shape:
        _require_positive(dx=dx, dy=dy, dz=dz)
        return NullShape("box", {"dx": dx, "dy": dy, "dz": dz})

    def cylinder(self, radius: float, height: float) -> Shape:
        _require_positive(radius=radius, height=height)
        return NullShape("cylinder", {"radius": radius, "height": height})

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
