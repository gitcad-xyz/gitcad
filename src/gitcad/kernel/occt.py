"""OCCT kernel backend via ``cadquery-ocp``.

This is the real b-rep geometry engine. It is an *optional* dependency: importing
this module without ``cadquery-ocp`` installed raises a clear, actionable error
rather than a bare ``ModuleNotFoundError``, and :func:`gitcad.kernel.get_kernel`
falls back to the null backend.

Only primitives are wired up in this scaffold; booleans/fillets/HLR are the next
work items. The point of the file today is to pin the seam boundary: *all* OCP
imports live here and nowhere else, so OCCT is a single swappable dependency
(ADR-0002).
"""

from __future__ import annotations

from typing import Any

from gitcad.errors import FailureSignature, KernelError, ValidationReport
from gitcad.seams import Shape

try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    _OCP_AVAILABLE = True
except Exception as _exc:  # pragma: no cover - depends on environment
    _OCP_AVAILABLE = False
    _IMPORT_ERROR = _exc


class OcctKernel:
    """Implements :class:`gitcad.seams.Kernel` over OpenCASCADE."""

    def __init__(self) -> None:
        if not _OCP_AVAILABLE:
            raise ImportError(
                "OcctKernel requires the OCCT bindings. Install them with:\n"
                "    pip install 'gitcad[occt]'   # pulls cadquery-ocp binary wheels\n"
                f"(underlying import error: {_IMPORT_ERROR!r})"
            )
        # Version string for fingerprints; refined once OCP exposes it cleanly.
        self.name = "occt"

    def box(self, dx: float, dy: float, dz: float) -> Shape:
        return BRepPrimAPI_MakeBox(dx, dy, dz).Shape()

    def cylinder(self, radius: float, height: float) -> Shape:
        return BRepPrimAPI_MakeCylinder(radius, height).Shape()

    def boolean(self, op: str, a: Shape, b: Shape) -> Shape:
        raise NotImplementedError("boolean ops land next; see docs/adr/0002")

    def fillet(self, shape: Shape, edges: list[str], radius: float) -> Shape:
        raise NotImplementedError("fillet lands with edge-identity resolution; see ADR-0003")

    def entities(self, shape: Shape, kind: str) -> list[dict[str, Any]]:
        raise NotImplementedError("topology enumeration lands with the identity backend")

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
        except Exception as exc:  # surface as a fingerprintable kernel error
            raise KernelError(
                "volume measurement failed",
                FailureSignature(op="measure", diagnostic=type(exc).__name__, kernel=self.name),
            ) from exc
        c = props.CentreOfMass()
        return {"volume": props.Mass(), "cx": c.X(), "cy": c.Y(), "cz": c.Z()}
