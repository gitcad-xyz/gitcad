"""Hidden-line-removal projection via OCCT.

One function: :func:`project` — a 3D shape and a named view direction in,
2D polylines (visible + hidden) out. This is the same engine FreeCAD's TechDraw
drives; we consume it headless and hand structured data to the sheet layer.
"""

from __future__ import annotations

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

Polyline = list[tuple[float, float]]

# Named views: (projection direction, x-direction of the sheet).
# Third-angle-friendly conventions; +Y on the sheet is derived (dir × xdir).
VIEWS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "front": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),
    "top":   ((0.0, 0.0, 1.0),  (1.0, 0.0, 0.0)),
    "right": ((1.0, 0.0, 0.0),  (0.0, 1.0, 0.0)),
    "iso":   ((1.0, 1.0, 1.0),  (1.0, -1.0, 0.0)),
}


def project(shape, view: str, *, deflection: float = 0.05) -> dict[str, list[Polyline]]:
    """Project ``shape`` into the named view. Returns 2D polylines in sheet
    coordinates (mm), classified visible/hidden."""
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r} (want one of {sorted(VIEWS)})")
    direction, xdir = VIEWS[view]

    algo = HLRBRep_Algo()
    algo.Add(shape)
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*direction), gp_Dir(*xdir))
    algo.Projector(HLRAlgo_Projector(ax))
    algo.Update()
    algo.Hide()
    hlr = HLRBRep_HLRToShape(algo)

    out: dict[str, list[Polyline]] = {"visible": [], "hidden": []}
    for key, compound in (("visible", hlr.VCompound()), ("hidden", hlr.HCompound())):
        if compound.IsNull():
            continue
        exp = TopExp_Explorer(compound, TopAbs_EDGE)
        while exp.More():
            edge = TopoDS.Edge_s(exp.Current())
            poly = _discretize(edge, deflection)
            if len(poly) >= 2:
                out[key].append(poly)
            exp.Next()
    return out


def _discretize(edge, deflection: float) -> Polyline:
    """Sample an HLR output edge to a 2D polyline. HLR edges live in the
    projection plane, so Z is ~0 and (X, Y) are sheet coordinates."""
    curve = BRepAdaptor_Curve(edge)
    sampler = GCPnts_QuasiUniformDeflection(curve, deflection)
    if not sampler.IsDone():
        return []
    pts: Polyline = []
    for i in range(1, sampler.NbPoints() + 1):
        p = sampler.Value(i)
        pts.append((p.X(), p.Y()))
    return pts


def bounds(polys: list[Polyline]) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) over a polyline set."""
    xs = [x for poly in polys for x, _ in poly]
    ys = [y for poly in polys for _, y in poly]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))
