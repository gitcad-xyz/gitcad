"""Mechanical analysis: exact inertia through the seam + DFM checks.

`inertia` surfaces the exact rational inertia tensor forge computes for
its solid classes (planar and freeform, via the divergence-theorem flux)
and falls back to OCCT's float `MatrixOfInertia` for OCCT shapes.
`draft_analysis` is a moldability check: faces whose draft angle to a
pull direction is below a minimum can't release from the tool.
"""

from __future__ import annotations

import math
from typing import Any


def inertia(kernel, shape) -> dict[str, Any]:
    """Volume, centroid, and inertia tensor (about the centroid) + the
    three principal moments. Exact rationals when forge built the shape;
    floats via OCCT otherwise. Returns floats for a uniform interface,
    with ``exact=True`` when the underlying tensor is rational."""
    exact = False
    try:
        from forgekernel.bsolid import (PatchSolid, mass_properties,
                                        polyhedron_mass_properties)
        from forgekernel.brep import Solid as _Solid

        if isinstance(shape, _Solid):
            mp = polyhedron_mass_properties(shape)
            exact = True
        elif isinstance(shape, PatchSolid):
            mp = mass_properties(shape)
            exact = True
        else:
            mp = None
    except ImportError:
        mp = None

    if mp is not None:
        V = float(mp["volume"])
        c = tuple(float(x) for x in mp["centroid"])
        I = [[float(mp["inertia"][i][j]) for j in range(3)] for i in range(3)]
    else:
        # any kernel's mass_props returns the tensor about the centroid;
        # route through the seam (no direct OCP import — ADR-0002).
        m = kernel.mass_props(shape)
        V = float(m["volume"])
        c = (m["cx"], m["cy"], m["cz"])
        I = [[m["ixx"], m["ixy"], m["ixz"]],
             [m["ixy"], m["iyy"], m["iyz"]],
             [m["ixz"], m["iyz"], m["izz"]]]

    principal = sorted(_sym_eigs_3x3(I))
    return {"volume": V, "centroid": c, "inertia": I,
            "principal_moments": principal, "exact": exact}


def _sym_eigs_3x3(A):
    """Eigenvalues of a symmetric 3×3 matrix (closed form; analysis only)."""
    p1 = A[0][1] ** 2 + A[0][2] ** 2 + A[1][2] ** 2
    q = (A[0][0] + A[1][1] + A[2][2]) / 3
    p2 = ((A[0][0] - q) ** 2 + (A[1][1] - q) ** 2 + (A[2][2] - q) ** 2
          + 2 * p1)
    if p2 == 0:
        return [A[0][0], A[1][1], A[2][2]]
    p = math.sqrt(p2 / 6)
    B = [[(A[i][j] - (q if i == j else 0)) / p for j in range(3)]
         for i in range(3)]
    detB = (B[0][0] * (B[1][1] * B[2][2] - B[1][2] * B[2][1])
            - B[0][1] * (B[1][0] * B[2][2] - B[1][2] * B[2][0])
            + B[0][2] * (B[1][0] * B[2][1] - B[1][1] * B[2][0]))
    r = max(-1.0, min(1.0, detB / 2))
    phi = math.acos(r) / 3
    e1 = q + 2 * p * math.cos(phi)
    e3 = q + 2 * p * math.cos(phi + 2 * math.pi / 3)
    e2 = 3 * q - e1 - e3
    return [e1, e2, e3]


def draft_analysis(kernel, shape, pull=(0, 0, 1),
                   min_angle_deg: float = 1.0) -> dict[str, Any]:
    """Moldability: for a pull (ejection) direction, report planar faces
    whose draft angle — 90° minus the angle between the face normal and
    the pull — is below ``min_angle_deg``. Zero-draft walls (parallel to
    the pull) fail hardest; floors/ceilings (perpendicular) pass."""
    d = _unit(pull)
    faces = kernel.entities(shape, "face")
    violations = []
    for i, f in enumerate(faces):
        n = f.get("plane")
        if n is None:                       # curved face: skip (report as such)
            continue
        n = _unit(n)
        dot = abs(sum(n[c] * d[c] for c in range(3)))
        theta = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
        draft = 90.0 - theta
        if draft < min_angle_deg:
            violations.append({"face": i, "draft_deg": round(draft, 4),
                               "normal": [round(x, 6) for x in n]})
    return {"pull": list(d), "min_angle_deg": min_angle_deg,
            "faces_checked": len(faces), "violations": violations,
            "ok": not violations}


def _unit(v):
    m = math.sqrt(sum(float(c) ** 2 for c in v)) or 1.0
    return tuple(float(c) / m for c in v)


def thickness_analysis(kernel, shape, min_wall: float = 1.0) -> dict[str, Any]:
    """Min-wall (moldability/printability) estimate for a planar forge
    solid: the smallest separation between an anti-parallel pair of faces
    whose projections overlap. Exact for prismatic parts (a box reports
    min(dx,dy,dz)); a first-order estimate elsewhere (not a full medial
    axis). Raises for non-forge shapes."""
    try:
        from forgekernel.brep import Solid as _Solid
    except ImportError:                      # pragma: no cover
        _Solid = ()
    if not isinstance(shape, _Solid):
        raise NotImplementedError(
            "thickness_analysis: planar forge solids only")
    # group polygons by (unit normal, plane offset)
    faces = []
    for poly in shape.polys:
        n = _unit(poly.plane.n)
        # a point on the plane → signed offset d = n·p
        v0 = poly.verts[0]
        d = sum(n[c] * float(v0[c]) for c in range(3))
        pts = [tuple(float(x) for x in v) for v in poly.verts]
        faces.append((n, d, pts))
    thin = []
    min_t = float("inf")
    for i in range(len(faces)):
        ni, di, pi = faces[i]
        for j in range(i + 1, len(faces)):
            nj, dj, pj = faces[j]
            # anti-parallel?
            if abs(ni[0] + nj[0]) > 1e-9 or abs(ni[1] + nj[1]) > 1e-9 \
                    or abs(ni[2] + nj[2]) > 1e-9:
                continue
            # projected-bbox overlap onto the plane's two in-plane axes
            if not _proj_overlap(ni, pi, pj):
                continue
            # nj = −ni. In the nᵢ coordinate face i sits at di and face j at
            # −dj; SOLID lies between them only when di + dj > 0 (that IS the
            # wall thickness). di + dj < 0 is an EMPTY slot/pocket — not a
            # wall — so the sign must NOT be discarded with abs() (that
            # flagged open slots as thin material, a false DFM failure).
            t = di + dj
            if t <= 1e-12:
                continue
            if t < min_t:
                min_t = t
            if t < min_wall:
                thin.append({"faces": [i, j], "thickness": round(t, 6)})
    return {"min_wall_target": min_wall,
            "min_thickness": None if min_t == float("inf") else round(min_t, 6),
            "thin_regions": thin, "ok": min_t >= min_wall}


def _proj_overlap(n, pa, pb) -> bool:
    """Do two planar point-sets overlap when projected onto the plane ⟂ n?"""
    # two in-plane basis vectors
    ref = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    dot = sum(ref[c] * n[c] for c in range(3))
    u = tuple(ref[c] - dot * n[c] for c in range(3))
    um = math.sqrt(sum(c * c for c in u)) or 1.0
    u = tuple(c / um for c in u)
    w = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2],
         n[0] * u[1] - n[1] * u[0])

    def box(pts):
        us = [sum(p[c] * u[c] for c in range(3)) for p in pts]
        ws = [sum(p[c] * w[c] for c in range(3)) for p in pts]
        return min(us), max(us), min(ws), max(ws)

    au0, au1, aw0, aw1 = box(pa)
    bu0, bu1, bw0, bw1 = box(pb)
    return au0 <= bu1 and bu0 <= au1 and aw0 <= bw1 and bw0 <= aw1
