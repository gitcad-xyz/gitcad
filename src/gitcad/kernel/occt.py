"""OCCT kernel backend via ``cadquery-ocp``.

The real b-rep geometry engine behind the :class:`gitcad.seams.Kernel` seam.
All OCP imports live here and nowhere else, so OCCT stays a single swappable
dependency (ADR-0002). Optional: importing without ``cadquery-ocp`` raises an
actionable error and :func:`gitcad.kernel.get_kernel` falls back to the null
backend.
"""

from __future__ import annotations

import math
from typing import Any

from gitcad.errors import FailureSignature, KernelError, ValidationReport
from gitcad.seams import Shape

try:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepPrimAPI import (
        BRepPrimAPI_MakeBox,
        BRepPrimAPI_MakeCone,
        BRepPrimAPI_MakeCylinder,
        BRepPrimAPI_MakeSphere,
    )
    from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    from OCP.GProp import GProp_GProps
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.StlAPI import StlAPI_Writer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    _OCP_AVAILABLE = True
except Exception as _exc:  # pragma: no cover - depends on environment
    _OCP_AVAILABLE = False
    _IMPORT_ERROR = _exc


_BOOL_OPS = {"union": "Fuse", "cut": "Cut", "intersect": "Common"}


def _unique_shapes(shape, kind) -> list:
    """Unique sub-shapes in stable order. TopExp_Explorer visits shared
    topology once per parent (a box's 12 edges appear 24 times) — the indexed
    map deduplicates, and BOTH entities() and fillet() must use this same
    enumeration so selector indices line up."""
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, m)
    return [m.FindKey(i) for i in range(1, m.Extent() + 1)]


class OcctKernel:
    """Implements :class:`gitcad.seams.Kernel` over OpenCASCADE."""

    def __init__(self) -> None:
        if not _OCP_AVAILABLE:
            raise ImportError(
                "OcctKernel requires the OCCT bindings. Install them with:\n"
                "    pip install 'gitcad[occt]'   # pulls cadquery-ocp binary wheels\n"
                f"(underlying import error: {_IMPORT_ERROR!r})"
            )
        # Versioned name: fingerprints must distinguish OCCT releases
        # (a bug fixed in 7.9 is not the bug present in 7.8).
        try:
            from importlib.metadata import version

            self.name = f"occt-{version('cadquery-ocp')}"
        except Exception:
            self.name = "occt"

    # -- primitives -----------------------------------------------------------

    def box(self, dx: float, dy: float, dz: float) -> Shape:
        return BRepPrimAPI_MakeBox(dx, dy, dz).Shape()

    def cylinder(self, radius: float, height: float) -> Shape:
        return BRepPrimAPI_MakeCylinder(radius, height).Shape()

    def sphere(self, radius: float) -> Shape:
        return BRepPrimAPI_MakeSphere(radius).Shape()

    def cone(self, r1: float, r2: float, height: float) -> Shape:
        return BRepPrimAPI_MakeCone(r1, r2, height).Shape()

    # -- operations -----------------------------------------------------------

    def boolean(self, op: str, a: Shape, b: Shape) -> Shape:
        if op not in _BOOL_OPS:
            raise ValueError(f"unknown boolean op {op!r} (want union|cut|intersect)")
        algo = {"union": BRepAlgoAPI_Fuse, "cut": BRepAlgoAPI_Cut, "intersect": BRepAlgoAPI_Common}[op](a, b)
        if not algo.IsDone():
            raise KernelError(
                f"boolean {op} failed",
                FailureSignature(op=f"boolean.{op}", diagnostic="BRepAlgoAPI:NotDone", kernel=self.name),
            )
        shape = algo.Shape()
        self.validate(shape).raise_if_invalid(f"boolean.{op}", self.name)
        return shape

    def fillet(self, shape: Shape, edges: list[int] | None, radius: float) -> Shape:
        """Fillet by enumeration index into ``entities(shape, "edge")`` order;
        ``None`` = all edges. Identity-to-index resolution happens in the
        document build — this method only ever sees concrete indices."""
        mk = BRepFilletAPI_MakeFillet(shape)
        wanted = set(edges) if edges is not None else None
        count = 0
        for index, raw in enumerate(_unique_shapes(shape, TopAbs_EDGE)):
            if wanted is None or index in wanted:
                mk.Add(radius, TopoDS.Edge_s(raw))
                count += 1
        if wanted is not None and count != len(wanted):
            raise KernelError(
                f"fillet: {len(wanted)} edge indices given, only {count} exist on shape",
                FailureSignature(op="fillet", diagnostic="EdgeIndexOutOfRange", kernel=self.name),
            )
        if count == 0:
            raise KernelError(
                "fillet: shape has no edges",
                FailureSignature(op="fillet", diagnostic="NoEdges", kernel=self.name),
            )
        try:
            mk.Build()
        except Exception as exc:
            raise KernelError(
                f"fillet r={radius} failed",
                FailureSignature(op="fillet", diagnostic=type(exc).__name__, kernel=self.name),
            ) from exc
        if not mk.IsDone():
            raise KernelError(
                f"fillet r={radius} did not converge",
                FailureSignature(op="fillet", diagnostic="MakeFillet:NotDone", kernel=self.name),
            )
        out = mk.Shape()
        self.validate(out).raise_if_invalid("fillet", self.name)
        return out

    def transform(self, shape: Shape, *, translate: tuple[float, float, float] = (0, 0, 0),
                  rotate_axis: tuple[float, float, float] = (0, 0, 1), rotate_deg: float = 0.0) -> Shape:
        trsf = gp_Trsf()
        if rotate_deg:
            ax = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*rotate_axis))
            trsf.SetRotation(ax, math.radians(rotate_deg))
        t = gp_Trsf()
        t.SetTranslation(gp_Vec(*translate))
        t.Multiply(trsf)  # rotate first, then translate
        return BRepBuilderAPI_Transform(shape, t, True).Shape()

    # -- inspection (the agent verification loop) -----------------------------

    def entities(self, shape: Shape, kind: str) -> list[dict[str, Any]]:
        """Order-independent semantic descriptors per topological entity —
        the raw material the IdentityService hashes into stable ids."""
        out: list[dict[str, Any]] = []
        if kind == "face":
            for raw in _unique_shapes(shape, TopAbs_FACE):
                face = TopoDS.Face_s(raw)
                surf = BRepAdaptor_Surface(face)
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                c = props.CentreOfMass()
                out.append({
                    "surface": GeomAbs_SurfaceType(surf.GetType()).name.replace("GeomAbs_", "").lower(),
                    "area": props.Mass(),
                    "centroid": [c.X(), c.Y(), c.Z()],
                })
        elif kind == "edge":
            for raw in _unique_shapes(shape, TopAbs_EDGE):
                edge = TopoDS.Edge_s(raw)
                curve = BRepAdaptor_Curve(edge)
                props = GProp_GProps()
                BRepGProp.LinearProperties_s(edge, props)
                c = props.CentreOfMass()
                out.append({
                    "curve": GeomAbs_CurveType(curve.GetType()).name.replace("GeomAbs_", "").lower(),
                    "length": props.Mass(),
                    "centroid": [c.X(), c.Y(), c.Z()],
                })
        elif kind == "vertex":
            out.extend({"kind": "vertex"} for _ in _unique_shapes(shape, TopAbs_VERTEX))
        else:
            raise ValueError(f"unknown entity kind {kind!r}")
        return out

    def validate(self, shape: Shape) -> ValidationReport:
        analyzer = BRepCheck_Analyzer(shape)
        ok = bool(analyzer.IsValid())
        report = ValidationReport(ok=ok, checks={"backend": self.name, "brepcheck": ok})
        if not ok:
            report.violations.append("BRepCheck:invalid")
        return report

    def measure(self, shape: Shape) -> dict[str, float]:
        props = GProp_GProps()
        try:
            BRepGProp.VolumeProperties_s(shape, props)
        except Exception as exc:
            raise KernelError(
                "volume measurement failed",
                FailureSignature(op="measure", diagnostic=type(exc).__name__, kernel=self.name),
            ) from exc
        c = props.CentreOfMass()
        return {"volume": props.Mass(), "cx": c.X(), "cy": c.Y(), "cz": c.Z()}

    def bbox(self, shape: Shape) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box, True)  # useTriangulation for tight bounds
        box.SetGap(0.0)  # Bnd_Box pads by a default gap; envelopes must be exact
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        return ((xmin, ymin, zmin), (xmax, ymax, zmax))

    # -- exports (the manufacturing deliverables) -----------------------------

    def export_step(self, shape: Shape, path: str) -> None:
        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        status = writer.Write(path)
        # IFSelect_RetDone == 1
        if int(status) != 1:
            raise KernelError(
                f"STEP write failed (status {int(status)})",
                FailureSignature(op="export.step", diagnostic=f"IFSelect:{int(status)}", kernel=self.name),
            )

    def export_stl(self, shape: Shape, path: str, *, deflection: float = 0.1) -> None:
        BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
        writer = StlAPI_Writer()
        if not writer.Write(shape, path):
            raise KernelError(
                "STL write failed",
                FailureSignature(op="export.stl", diagnostic="StlAPI:WriteFalse", kernel=self.name),
            )
