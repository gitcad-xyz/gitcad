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

    name = "ref-k2-exact"

    def __init__(self) -> None:
        from forgekernel import kernel as fk

        self._fk = fk

    # -- primitives -----------------------------------------------------------

    def box(self, dx: float, dy: float, dz: float):
        return self._fk.box(dx, dy, dz)

    def cylinder(self, radius: float, height: float):
        from forgekernel.quadric import Cyl

        return Cyl.make(radius, height)

    def sphere(self, radius: float):
        from forgekernel.quadric import Sphere

        return Sphere.make(radius)

    def cone(self, r1: float, r2: float, height: float):
        from forgekernel.quadric import Cone

        return Cone.make(r1, r2, height)

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
        from forgekernel.quadric import AxisStack, Cone, Cyl, Sphere

        if isinstance(shape, (Cyl, Cone, Sphere)):
            if rotate_deg and (tuple(rotate_axis) != (0, 0, 1)):
                _nope("transform(tilt a quadric)", "K2.2 (general axes)")
            return shape.translated(*translate)
        if isinstance(shape, AxisStack):
            _nope("transform(AxisStack)", "K2.2")
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
        from forgekernel.brep import Solid
        from forgekernel.quadric import (AxisStack, Cone, Cyl, DrilledSolid,
                                         Sphere)

        from forgekernel.quadric import DisjointUnion

        axis_prims = (Cyl, Cone, Sphere)
        curved = (Cyl, Cone, Sphere, AxisStack, DisjointUnion)
        if op == "union" and (isinstance(a, curved) or isinstance(b, curved)):
            # planar Solid+Solid never reaches here — it stays on the exact
            # BSP engine below. Curved operands: coaxial quadrics fuse into
            # an AxisStack; anything meeting only tangentially unions exactly
            # by measure-zero (DisjointUnion). Genuine overlap refuses (K2.3).
            if isinstance(b, axis_prims) and isinstance(a, (axis_prims, AxisStack)):
                try:
                    stack = a if isinstance(a, AxisStack) else AxisStack(a.cx, a.cy, [a])
                    return stack.fuse(b)
                except ValueError:
                    pass                       # non-coaxial: try DisjointUnion
            try:
                members = a.members if isinstance(a, DisjointUnion) else [a]
                other = b.members if isinstance(b, DisjointUnion) else [b]
                return DisjointUnion(members + other)
            except ValueError as exc:
                raise KernelError(str(exc), FailureSignature(
                    op="boolean.union", diagnostic="NotYetImplemented",
                    kernel="ref"))
        if isinstance(b, Cyl) and op == "cut":
            base = (DrilledSolid(a, []) if isinstance(a, Solid)
                    else a if isinstance(a, DrilledSolid) else None)
            if base is not None:
                try:
                    return base.cut(b)
                except ValueError as exc:
                    raise KernelError(str(exc), FailureSignature(
                        op="boolean.cut", diagnostic="NotYetImplemented",
                        kernel="ref"))
        if isinstance(a, (AxisStack, *axis_prims, DrilledSolid)) or                 isinstance(b, (AxisStack, *axis_prims, DrilledSolid)):
            _nope(f"boolean.{op} on quadric operands", "K2.2")
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
        from forgekernel.quadric import Cyl, DrilledSolid

        from forgekernel.quadric import (AxisStack, Cone, DisjointUnion,
                                         RevolveSolid, Sphere)

        if isinstance(shape, (Cone, Sphere)):
            shape = AxisStack(shape.cx, shape.cy, [shape])
        if isinstance(shape, (Cyl, DrilledSolid, AxisStack, RevolveSolid, DisjointUnion)):
            cx, cy, cz = shape.centroid_f()
            return {"volume": float(shape.volume()),
                    "cx": cx, "cy": cy, "cz": cz}
        c = shape.centroid()
        return {"volume": float(shape.volume()),
                "cx": float(c[0]), "cy": float(c[1]), "cz": float(c[2])}

    def measure(self, shape) -> dict[str, float]:
        (x0, y0, z0), (x1, y1, z1) = shape.bbox()
        return {"volume": float(shape.volume()),
                "dx": float(x1 - x0), "dy": float(y1 - y0),
                "dz": float(z1 - z0)}

    def bbox(self, shape):
        from forgekernel.quadric import AxisStack, Cone, Sphere

        if isinstance(shape, (Cone, Sphere)):
            shape = AxisStack(shape.cx, shape.cy, [shape])
        lo, hi = shape.bbox()
        return (tuple(float(v) for v in lo), tuple(float(v) for v in hi))

    def _bbox_unused(self, shape):
        lo, hi = shape.bbox()
        return (tuple(float(v) for v in lo), tuple(float(v) for v in hi))

    def _is_composite(self, shape) -> bool:
        from forgekernel.quadric import Cyl, DrilledSolid

        return isinstance(shape, (Cyl, DrilledSolid))

    def entities(self, shape, kind: str) -> list[dict[str, Any]]:
        from forgekernel.quadric import Cyl, DrilledSolid

        from forgekernel.quadric import (AxisStack, Cone, DisjointUnion,
                                         RevolveSolid, Sphere)

        if kind != "face":
            raise NotImplementedError("ref enumerates faces only")
        if isinstance(shape, DisjointUnion):
            out = []
            for m in shape.members:
                out += self.entities(m, "face")
            return out
        if isinstance(shape, (Cone, Sphere, AxisStack, RevolveSolid)):
            prims = getattr(shape, "prims", [shape])
            return [{"surface": type(p).__name__.lower()} for p in prims]
        if isinstance(shape, Cyl):
            return [{"surface": "cylinder", "radius": float(shape.r),
                     "axis_dir": [0.0, 0.0, 1.0],
                     "axis_origin": [float(shape.cx), float(shape.cy),
                                     float(shape.z0)]}]
        if isinstance(shape, DrilledSolid):
            base = self.entities(shape.base, "face")
            return base + shape.cylinder_faces()
        out = []
        for (plane_key, source), frags in sorted(
                shape.logical_faces().items(),
                key=lambda kv: (kv[0][1], kv[0][0])):
            out.append({"surface": "plane", "lineage": source,
                        "plane": [float(v) for v in plane_key[:3]],
                        "fragments": len(frags)})
        return out

    def validate(self, shape) -> ValidationReport:
        from forgekernel.quadric import Cyl, DrilledSolid

        from forgekernel.quadric import (AxisStack, Cone, DisjointUnion,
                                         RevolveSolid, Sphere)

        if isinstance(shape, (Cyl, Cone, Sphere, AxisStack, RevolveSolid, DisjointUnion)):
            return ValidationReport(ok=True, checks={"method": "analytic"},
                                    violations=[])
        if isinstance(shape, DrilledSolid):
            bad = shape.watertight_violations()
            return ValidationReport(
                ok=not bad and float(shape.volume()) > 0,
                checks={"method": "exact-composite",
                        "bores": len(shape.bores)},
                violations=list(bad))
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
        from forgekernel.quadric import RevolveSolid

        if angle_deg != 360.0:
            _nope("revolve(partial angle)", "K2.2")
        segs = profile.get("segments", [])
        if any(s.get("kind") != "line" for s in segs):
            _nope("revolve(arc profile)", "K2.2")
        loop = [tuple(profile["start"])] + [tuple(s["to"]) for s in segs]
        if loop[0] == loop[-1]:
            loop = loop[:-1]
        return RevolveSolid(loop)

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
        from forgekernel.brep import Solid
        from forgekernel.kernel import draft as fk_draft

        if not isinstance(shape, Solid) or tuple(pull) != (0, 0, 1):
            _nope("draft(non-planar or tilted pull)", "K2.3")
        try:
            return fk_draft(shape, angle_deg, neutral_z)
        except ValueError as exc:
            raise KernelError(str(exc), FailureSignature(
                op="draft", diagnostic="NotYetImplemented", kernel="ref"))

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
