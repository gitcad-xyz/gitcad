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
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_Transform,
    )
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
    from OCP.BRepOffset import BRepOffset_Skin
    from OCP.GeomAbs import GeomAbs_Arc
    from OCP.TopTools import TopTools_ListOfShape
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepPrimAPI import (
        BRepPrimAPI_MakeBox,
        BRepPrimAPI_MakeCone,
        BRepPrimAPI_MakeCylinder,
        BRepPrimAPI_MakeSphere,
    )
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.GProp import GProp_GProps
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
    from OCP.StlAPI import StlAPI_Writer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX, TopAbs_Orientation
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
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

    def chamfer(self, shape: Shape, edges: list[int] | None, distance: float) -> Shape:
        """Chamfer by edge enumeration index (same contract as fillet)."""
        mk = BRepFilletAPI_MakeChamfer(shape)
        wanted = set(edges) if edges is not None else None
        count = 0
        for index, raw in enumerate(_unique_shapes(shape, TopAbs_EDGE)):
            if wanted is None or index in wanted:
                mk.Add(distance, TopoDS.Edge_s(raw))
                count += 1
        if wanted is not None and count != len(wanted):
            raise KernelError(
                f"chamfer: {len(wanted)} edge indices given, only {count} exist",
                FailureSignature(op="chamfer", diagnostic="EdgeIndexOutOfRange", kernel=self.name),
            )
        try:
            mk.Build()
        except Exception as exc:
            raise KernelError(
                f"chamfer d={distance} failed",
                FailureSignature(op="chamfer", diagnostic=type(exc).__name__, kernel=self.name),
            ) from exc
        if not mk.IsDone():
            raise KernelError(
                f"chamfer d={distance} did not converge",
                FailureSignature(op="chamfer", diagnostic="MakeChamfer:NotDone", kernel=self.name),
            )
        out = mk.Shape()
        self.validate(out).raise_if_invalid("chamfer", self.name)
        return out

    def shell(self, shape: Shape, remove_faces: list[int], thickness: float) -> Shape:
        """Hollow to a wall thickness, removing the listed faces (by face
        enumeration index) to leave openings."""
        faces = TopTools_ListOfShape()
        all_faces = _unique_shapes(shape, TopAbs_FACE)
        for idx in remove_faces:
            if idx >= len(all_faces):
                raise KernelError(
                    f"shell: face index {idx} out of range ({len(all_faces)} faces)",
                    FailureSignature(op="shell", diagnostic="FaceIndexOutOfRange", kernel=self.name),
                )
            faces.Append(all_faces[idx])
        mk = BRepOffsetAPI_MakeThickSolid()
        mk.MakeThickSolidByJoin(shape, faces, -abs(thickness), 1e-3,
                                BRepOffset_Skin, False, False, GeomAbs_Arc)
        if not mk.IsDone():
            raise KernelError(
                f"shell t={thickness} failed",
                FailureSignature(op="shell", diagnostic="MakeThickSolid:NotDone", kernel=self.name),
            )
        out = mk.Shape()
        self.validate(out).raise_if_invalid("shell", self.name)
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

    # -- sketch-based features (the 2D -> 3D workflow) ------------------------

    def _profile_face(self, profile: dict) -> "TopoDS_Shape":
        """Build a planar face (XY plane) from a validated profile dict."""
        wire = BRepBuilderAPI_MakeWire()
        prev = tuple(profile["start"])
        for seg in profile["segments"]:
            to = tuple(seg["to"])
            p1, p2 = gp_Pnt(prev[0], prev[1], 0), gp_Pnt(to[0], to[1], 0)
            if seg["kind"] == "line":
                edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
            else:  # arc via three points
                via = seg["via"]
                arc = GC_MakeArcOfCircle(p1, gp_Pnt(via[0], via[1], 0), p2).Value()
                edge = BRepBuilderAPI_MakeEdge(arc).Edge()
            wire.Add(edge)
            prev = to
        if not wire.IsDone():
            raise KernelError(
                "profile wire construction failed (self-intersecting or disconnected?)",
                FailureSignature(op="sketch", diagnostic="MakeWire:NotDone", kernel=self.name),
            )
        face = BRepBuilderAPI_MakeFace(wire.Wire())
        if not face.IsDone():
            raise KernelError(
                "profile does not bound a valid planar face",
                FailureSignature(op="sketch", diagnostic="MakeFace:NotDone", kernel=self.name),
            )
        return face.Face()

    def extrude(self, profile: dict, height: float) -> Shape:
        """Linear sweep of a closed XY profile along +Z."""
        face = self._profile_face(profile)
        shape = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, height)).Shape()
        self.validate(shape).raise_if_invalid("extrude", self.name)
        return shape

    def revolve(self, profile: dict, angle_deg: float = 360.0) -> Shape:
        """Revolve a closed XY profile about the Y axis (profile x >= 0)."""
        face = self._profile_face(profile)
        axis = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0))
        shape = BRepPrimAPI_MakeRevol(face, axis, math.radians(angle_deg)).Shape()
        self.validate(shape).raise_if_invalid("revolve", self.name)
        return shape

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
                desc: dict[str, Any] = {
                    "surface": GeomAbs_SurfaceType(surf.GetType()).name.replace("GeomAbs_", "").lower(),
                    "area": props.Mass(),
                    "centroid": [c.X(), c.Y(), c.Z()],
                }
                # Analytic parameters where the surface has them — the raw
                # material of feature recognition (dead geometry -> dimensions).
                if desc["surface"] == "cylinder":
                    cyl = surf.Cylinder()
                    loc, direction = cyl.Axis().Location(), cyl.Axis().Direction()
                    desc["radius"] = cyl.Radius()
                    desc["axis_origin"] = [loc.X(), loc.Y(), loc.Z()]
                    desc["axis_dir"] = [direction.X(), direction.Y(), direction.Z()]
                out.append(desc)
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
            report.violations.append("brepcheck-invalid")
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

    def tessellate(self, shape: Shape, *, deflection: float = 0.2) -> dict[str, list]:
        """Triangulate for display: flat position array + triangle indices.
        The viewer's (and any future Renderer backend's) geometry source."""
        BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
        positions: list[float] = []
        indices: list[int] = []
        for raw in _unique_shapes(shape, TopAbs_FACE):
            face = TopoDS.Face_s(raw)
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, loc)
            if tri is None:
                continue
            trsf = loc.Transformation()
            base = len(positions) // 3
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                positions.extend((round(p.X(), 5), round(p.Y(), 5), round(p.Z(), 5)))
            flip = face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                if flip:
                    a, c = c, a
                indices.extend((base + a - 1, base + b - 1, base + c - 1))
        return {"positions": positions, "indices": indices}

    # -- projection (the drawing engine's geometry backend) -------------------

    def hlr_project(self, shape: Shape, direction: tuple[float, float, float],
                    xdir: tuple[float, float, float], *,
                    deflection: float = 0.05) -> dict[str, list[list[tuple[float, float]]]]:
        """Hidden-line-removal projection: 2D polylines (sheet coords, mm)
        classified visible/hidden. The DrawingEngine consumes this through the
        Kernel seam — no OCP outside this module (ADR-0002, enforced by an
        invariant test)."""
        algo = HLRBRep_Algo()
        algo.Add(shape)
        ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*direction), gp_Dir(*xdir))
        algo.Projector(HLRAlgo_Projector(ax))
        algo.Update()
        algo.Hide()
        hlr = HLRBRep_HLRToShape(algo)

        out: dict[str, list[list[tuple[float, float]]]] = {"visible": [], "hidden": []}
        for key, compound in (("visible", hlr.VCompound()), ("hidden", hlr.HCompound())):
            if compound.IsNull():
                continue
            for raw in _unique_shapes(compound, TopAbs_EDGE):
                curve = BRepAdaptor_Curve(TopoDS.Edge_s(raw))
                sampler = GCPnts_QuasiUniformDeflection(curve, deflection)
                if not sampler.IsDone():
                    continue
                poly = [(sampler.Value(i).X(), sampler.Value(i).Y())
                        for i in range(1, sampler.NbPoints() + 1)]
                if len(poly) >= 2:
                    out[key].append(poly)
        return out

    # -- imports (onboarding existing work) -----------------------------------

    def import_step(self, path: str) -> Shape:
        """Read a STEP file into one shape (compound if multi-body)."""
        reader = STEPControl_Reader()
        status = reader.ReadFile(path)
        if int(status) != 1:  # IFSelect_RetDone
            raise KernelError(
                f"STEP read failed for {path!r} (status {int(status)})",
                FailureSignature(op="import.step", diagnostic=f"IFSelect:{int(status)}", kernel=self.name),
            )
        reader.TransferRoots()
        n = reader.NbShapes()
        if n == 0:
            raise KernelError(
                f"STEP file {path!r} contained no transferable shapes",
                FailureSignature(op="import.step", diagnostic="NoShapes", kernel=self.name),
            )
        if n == 1:
            return reader.Shape(1)
        return self.compound([reader.Shape(i) for i in range(1, n + 1)])

    def import_brep(self, path: str) -> Shape:
        """Read OCCT's native .brep text format (what .FCStd files embed)."""
        shape = TopoDS_Shape()
        builder = BRep_Builder()
        if not BRepTools.Read_s(shape, path, builder):
            raise KernelError(
                f"BREP read failed for {path!r}",
                FailureSignature(op="import.brep", diagnostic="BRepTools:ReadFalse", kernel=self.name),
            )
        return shape

    def export_brep(self, shape: Shape, path: str) -> None:
        if not BRepTools.Write_s(shape, path):
            raise KernelError(
                f"BREP write failed for {path!r}",
                FailureSignature(op="export.brep", diagnostic="BRepTools:WriteFalse", kernel=self.name),
            )

    def compound(self, shapes: list[Shape]) -> Shape:
        """Combine shapes into one compound (multi-body import container)."""
        comp = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(comp)
        for s in shapes:
            builder.Add(comp, s)
        return comp

    def export_stl(self, shape: Shape, path: str, *, deflection: float = 0.1) -> None:
        BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
        writer = StlAPI_Writer()
        if not writer.Write(shape, path):
            raise KernelError(
                "STL write failed",
                FailureSignature(op="export.stl", diagnostic="StlAPI:WriteFalse", kernel=self.name),
            )
