"""`ref` backend — the forgekernel exact reference kernel behind the seam.

ADR-0018: forgekernel (github.com/gitcad-xyz/forge) is the from-scratch
kernel's executable specification — exact rational arithmetic, no
epsilons in any decision. This shim adapts it to the gitcad Kernel
protocol for the operator classes each stage has earned; everything
else refuses honestly, naming the stage that brings it. The scorecard
(gitcad.bench) measures the growing coverage against OCCT.
"""

from __future__ import annotations

from typing import Any

from gitcad.errors import FailureSignature, KernelError, ValidationReport

_K2 = "arrives at K2 (quadrics)"
_K3 = "arrives at K3 (NURBS/SSI)"
_K5 = "arrives at K5 (blends)"


def _nope(op: str, stage: str):
    raise KernelError(
        f"ref kernel does not implement {op} yet — {stage}",
        FailureSignature(op=op, diagnostic="NotYetImplemented", kernel="ref"))


class RefKernel:
    """K1: exact planar solids (box, line-profile extrude, quarter-turn
    rigid transforms, mirror, scale, booleans, exact mass properties)."""

    name = "ref-k1-exact"

    def __init__(self) -> None:
        from forgekernel import kernel as fk

        self._fk = fk

    # -- primitives -----------------------------------------------------------

    def box(self, dx: float, dy: float, dz: float):
        return self._fk.box(dx, dy, dz)

    def cylinder(self, radius: float, height: float):
        _nope("cylinder", _K2)

    def sphere(self, radius: float):
        _nope("sphere", _K2)

    def cone(self, r1: float, r2: float, height: float):
        _nope("cone", _K2)

    def extrude(self, profile: dict, height: float):
        segs = profile.get("segments", [])
        if any(s.get("kind") != "line" for s in segs):
            _nope("extrude(arc profile)", _K2)
        loop = [tuple(profile["start"])] + [tuple(s["to"]) for s in segs]
        if loop[0] == loop[-1]:
            loop = loop[:-1]
        return self._fk.prism(loop, height)

    # -- transforms -----------------------------------------------------------

    def transform(self, shape, *, translate=(0, 0, 0),
                  rotate_axis=(0, 0, 1), rotate_deg: float = 0.0):
        out = shape
        if rotate_deg:
            axis = {(1, 0, 0): "x", (0, 1, 0): "y", (0, 0, 1): "z"}.get(
                tuple(rotate_axis))
            if axis is None or rotate_deg % 90 != 0:
                _nope(f"transform(rotate {rotate_deg} about {rotate_axis})", _K2)
            out = self._fk.rotate_quarter(out, axis, int(rotate_deg // 90))
        if any(translate):
            out = self._fk.translate(out, *translate)
        return out

    def scale(self, shape, fx: float, fy=None, fz=None):
        return self._fk.scale(shape, fx, fy, fz)

    def mirror(self, shape, plane: str):
        axis = {"yz": "x", "xz": "y", "xy": "z"}.get(plane)
        if axis is None:
            raise KernelError(
                f"mirror plane must be xy|xz|yz, got {plane!r}",
                FailureSignature(op="mirror", diagnostic="BadInput",
                                 kernel="ref"))
        return self._fk.mirror(shape, axis)

    def boolean(self, op: str, a, b):
        try:
            return self._fk.boolean(op, a, b)
        except ArithmeticError as exc:
            raise KernelError(
                f"boolean {op} failed closure: {exc}",
                FailureSignature(op=f"boolean.{op}",
                                 diagnostic="ClosureViolation", kernel="ref"))

    def compound(self, shapes: list):
        from forgekernel.brep import Solid

        return Solid([p for s in shapes for p in s.polys])

    # -- metrics --------------------------------------------------------------

    def mass_props(self, shape) -> dict[str, float]:
        c = shape.centroid()
        return {"volume": float(shape.volume()),
                "cx": float(c[0]), "cy": float(c[1]), "cz": float(c[2])}

    def measure(self, shape) -> dict[str, float]:
        (x0, y0, z0), (x1, y1, z1) = shape.bbox()
        return {"volume": float(shape.volume()),
                "dx": float(x1 - x0), "dy": float(y1 - y0),
                "dz": float(z1 - z0)}

    def bbox(self, shape):
        lo, hi = shape.bbox()
        return (tuple(float(v) for v in lo), tuple(float(v) for v in hi))

    def entities(self, shape, kind: str) -> list[dict[str, Any]]:
        if kind != "face":
            raise NotImplementedError("ref-K1 enumerates faces only")
        out = []
        for (plane_key, source), frags in sorted(
                shape.logical_faces().items(),
                key=lambda kv: (kv[0][1], kv[0][0])):
            out.append({"surface": "plane", "lineage": source,
                        "plane": [float(v) for v in plane_key[:3]],
                        "fragments": len(frags)})
        return out

    def validate(self, shape) -> ValidationReport:
        bad = shape.watertight_violations()
        if shape.volume() <= 0:
            bad = list(bad) + ["nonpositive-volume"]
        return ValidationReport(ok=not bad,
                                checks={"method": "exact-line-coverage",
                                        "polygons": len(shape.polys)},
                                violations=list(bad))

    def tessellate(self, shape, *, deflection: float = 0.2) -> dict[str, list]:
        return shape.tessellate()

    # -- honest refusals (each names its stage) -------------------------------

    def revolve(self, profile, angle_deg=360.0):
        _nope("revolve", _K2)

    def loft(self, sections, *, ruled=False):
        _nope("loft", _K3)

    def sweep(self, profile, path):
        _nope("sweep", _K3)

    def fillet(self, shape, edges, radius):
        _nope("fillet", _K5)

    def chamfer(self, shape, edges, distance):
        if edges:
            _nope("chamfer(selected edges)", "K1.2 (edge enumeration ids)")
        from forgekernel.kernel import chamfer as fk_chamfer

        try:
            return fk_chamfer(shape, distance)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="chamfer", diagnostic="NotYetImplemented", kernel="ref"))

    def shell(self, shape, remove_faces, thickness):
        _nope("shell", "arrives at K4 (offsets)")

    def draft(self, shape, faces, angle_deg, pull=(0, 0, 1), neutral_z=0.0):
        _nope("draft", _K2)

    def helix(self, radius, pitch, turns, ccw=True):
        _nope("helix", _K3)

    def pipe(self, spine, profile_diameter):
        _nope("pipe", _K3)

    def hlr_project(self, shape, direction, up=None):
        _nope("hlr_project", _K2)

    def export_step(self, shape, path):
        _nope("export_step", _K2)

    def export_stl(self, shape, path, *, deflection=0.1):
        from forgekernel import io

        with open(path, "w", newline=chr(10)) as f:
            f.write(io.to_stl(shape))

    def export_brep(self, shape, path):
        from forgekernel import io

        with open(path, "w", newline=chr(10)) as f:
            f.write(io.dumps(shape))

    def import_step(self, path):
        _nope("import_step", _K3)

    def import_brep(self, path):
        from forgekernel import io

        with open(path, encoding="utf-8") as f:
            return io.loads(f.read())
