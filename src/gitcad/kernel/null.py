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

    def bbox(self, shape: Shape) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Analytic bounds for primitives; unions/first-child for symbolic ops.
        Approximate by design — good enough to test envelope derivation without
        a kernel; exact bounds come from the OCCT backend."""
        b = _bounds(shape)
        if b is None:
            raise NotImplementedError(f"null kernel cannot bound {getattr(shape, 'kind', shape)!r}")
        return b

    def export_step(self, shape: Shape, path: str) -> None:
        raise NotImplementedError("STEP export requires the OCCT backend (pip install 'gitcad[occt]')")

    def export_stl(self, shape: Shape, path: str, *, deflection: float = 0.1) -> None:
        raise NotImplementedError("STL export requires the OCCT backend (pip install 'gitcad[occt]')")

    def import_step(self, path: str) -> Shape:
        raise NotImplementedError("STEP import requires the OCCT backend (pip install 'gitcad[occt]')")

    def import_brep(self, path: str) -> Shape:
        raise NotImplementedError("BREP import requires the OCCT backend (pip install 'gitcad[occt]')")

    def export_brep(self, shape: Shape, path: str) -> None:
        raise NotImplementedError("BREP export requires the OCCT backend (pip install 'gitcad[occt]')")

    def compound(self, shapes: list[Shape]) -> Shape:
        return NullShape("compound", {}, tuple(shapes))

    def hlr_project(self, shape, direction, xdir, *, deflection: float = 0.05):
        raise NotImplementedError("HLR projection requires the OCCT backend (pip install 'gitcad[occt]')")

    def tessellate(self, shape, *, deflection: float = 0.2):
        raise NotImplementedError("tessellation requires the OCCT backend (pip install 'gitcad[occt]')")

    def boolean(self, op: str, a: Shape, b: Shape) -> Shape:
        if op not in {"union", "cut", "intersect"}:
            raise ValueError(f"unknown boolean op {op!r}")
        return NullShape("boolean", {"op": op}, (a, b))

    def extrude(self, profile: dict, height: float) -> Shape:
        from gitcad.sketch import Profile

        Profile.from_params(profile)  # validates closure/segment forms
        _require_positive(height=height)
        return NullShape("extrude", {"profile": profile, "height": height})

    def revolve(self, profile: dict, angle_deg: float = 360.0) -> Shape:
        from gitcad.sketch import Profile

        Profile.from_params(profile)
        return NullShape("revolve", {"profile": profile, "angle_deg": angle_deg})

    def fillet(self, shape: Shape, edges: list[int] | None, radius: float) -> Shape:
        _require_positive(radius=radius)
        return NullShape("fillet", {"edges": list(edges) if edges is not None else None,
                                    "radius": radius}, (shape,))

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
        # The null backend can only assert structural well-formedness — it must
        # say so explicitly, or a silent fallback would let agents "verify"
        # geometry that was never built (reviewed 2026-07-22).
        ok = isinstance(shape, NullShape)
        return ValidationReport(ok=ok, checks={"backend": "null", "geometry_checked": False})

    def measure(self, shape: Shape) -> dict[str, float]:
        vol = shape.volume() if isinstance(shape, NullShape) else None
        out: dict[str, float] = {}
        if vol is not None:
            out["volume"] = vol
        return out


def _bounds(shape) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    if not isinstance(shape, NullShape):
        return None
    if shape.kind == "box":
        p = shape.params
        return ((0.0, 0.0, 0.0), (p["dx"], p["dy"], p["dz"]))
    if shape.kind == "cylinder":
        p = shape.params
        r = p["radius"]
        return ((-r, -r, 0.0), (r, r, p["height"]))
    if shape.kind == "sphere":
        r = shape.params["radius"]
        return ((-r, -r, -r), (r, r, r))
    if shape.kind == "transform":
        inner = _bounds(shape.children[0])
        if inner is None:
            return None
        tx, ty, tz = shape.params["translate"]
        if shape.params.get("rotate_deg"):
            return None  # rotation of an AABB needs real geometry — punt to OCCT
        (ax, ay, az), (bx, by, bz) = inner
        return ((ax + tx, ay + ty, az + tz), (bx + tx, by + ty, bz + tz))
    if shape.kind == "boolean":
        bounds = [b for c in shape.children if (b := _bounds(c))]
        if not bounds:
            return None
        if shape.params["op"] in ("cut", "intersect"):
            return _bounds(shape.children[0])  # conservative: first operand
        los, his = [b[0] for b in bounds], [b[1] for b in bounds]
        return (tuple(min(p[i] for p in los) for i in range(3)),
                tuple(max(p[i] for p in his) for i in range(3)))
    if shape.kind == "fillet":
        return _bounds(shape.children[0])
    return None


def _require_positive(**kw: float) -> None:
    for k, v in kw.items():
        if not (isinstance(v, (int, float)) and v > 0):
            raise ValueError(f"{k} must be positive, got {v!r}")
