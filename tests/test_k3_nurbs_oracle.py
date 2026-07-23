"""K3.1 — de Boor NURBS evaluation, oracle-checked against OCCT.

forge evaluates B-spline/NURBS curves exactly (rational control points →
rational points); OCCT can only approximate. This asserts they agree to
machine precision AND that forge's answer is the exact one.
"""

from fractions import Fraction

import pytest

pytest.importorskip("forgekernel")
pytest.importorskip("OCP")


def _occt_bezier(points):
    from OCP.Geom import Geom_BezierCurve
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array1OfPnt

    arr = TColgp_Array1OfPnt(1, len(points))
    for i, (x, y, z) in enumerate(points):
        arr.SetValue(i + 1, gp_Pnt(x, y, z))
    return Geom_BezierCurve(arr)


@pytest.mark.occt
def test_de_boor_bezier_matches_occt_to_machine_eps() -> None:
    from forgekernel.nurbs import bezier

    P = [(0, 0, 0), (1, 3, 0), (3, 3, 1), (4, 0, 0)]
    ref, occt = bezier(P), _occt_bezier(P)
    worst = 0.0
    for k in range(11):
        t = Fraction(k, 10)
        fx = ref.eval(t)
        ox = occt.Value(float(t))
        worst = max(worst, abs(float(fx[0]) - ox.X()),
                    abs(float(fx[1]) - ox.Y()), abs(float(fx[2]) - ox.Z()))
    assert worst < 1e-12
    # forge's midpoint is the exact rational; OCCT can only carry a double
    assert ref.eval(Fraction(1, 2)) == (Fraction(2), Fraction(9, 4), Fraction(3, 8))


@pytest.mark.occt
def test_de_boor_bspline_matches_occt() -> None:
    from OCP.Geom import Geom_BSplineCurve
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal

    from forgekernel.nurbs import BSplineCurve

    # a cubic B-spline, one interior knot (knot 0.5 with multiplicity 1)
    P = [(0, 0, 0), (1, 2, 0), (3, 2, 1), (4, 0, 0), (6, 1, 0)]
    # clamped knot vector: [0,0,0,0, 1/2, 1,1,1,1]  (n+p+1 = 9 knots)
    ref = BSplineCurve(3, P, [0, 0, 0, 0, Fraction(1, 2), 1, 1, 1, 1])

    poles = TColgp_Array1OfPnt(1, len(P))
    for i, (x, y, z) in enumerate(P):
        poles.SetValue(i + 1, gp_Pnt(x, y, z))
    uk = TColStd_Array1OfReal(1, 3)              # distinct knots 0, 1/2, 1
    for i, v in enumerate((0.0, 0.5, 1.0)):
        uk.SetValue(i + 1, v)
    mult = TColStd_Array1OfInteger(1, 3)
    for i, v in enumerate((4, 1, 4)):
        mult.SetValue(i + 1, v)
    occt = Geom_BSplineCurve(poles, uk, mult, 3)

    worst = 0.0
    for k in range(1, 10):
        t = Fraction(k, 10)
        fx = ref.eval(t)
        ox = occt.Value(float(t))
        worst = max(worst, abs(float(fx[0]) - ox.X()),
                    abs(float(fx[1]) - ox.Y()), abs(float(fx[2]) - ox.Z()))
    assert worst < 1e-12
    assert all(isinstance(v, Fraction) for v in ref.eval(Fraction(3, 10)))


@pytest.mark.occt
def test_de_boor_surface_matches_occt() -> None:
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal

    from forgekernel.nurbs import BSplineSurface

    # biquadratic, interior knot in u — same data both kernels
    net = [[(x, y, (x * y) % 3) for y in range(3)] for x in range(4)]
    ref = BSplineSurface(2, 2, net, [0, 0, 0, 1, 2, 2, 2], [0, 0, 0, 1, 1, 1])

    poles = TColgp_Array2OfPnt(1, 4, 1, 3)
    for i in range(4):
        for j in range(3):
            x, y, z = net[i][j]
            poles.SetValue(i + 1, j + 1, gp_Pnt(x, y, z))
    uk = TColStd_Array1OfReal(1, 3)
    for i, v in enumerate((0.0, 1.0, 2.0)):
        uk.SetValue(i + 1, v)
    um = TColStd_Array1OfInteger(1, 3)
    for i, v in enumerate((3, 1, 3)):
        um.SetValue(i + 1, v)
    vk = TColStd_Array1OfReal(1, 2)
    for i, v in enumerate((0.0, 1.0)):
        vk.SetValue(i + 1, v)
    vm = TColStd_Array1OfInteger(1, 2)
    for i, v in enumerate((3, 3)):
        vm.SetValue(i + 1, v)
    occt = Geom_BSplineSurface(poles, uk, vk, um, vm, 2, 2)

    worst = 0.0
    for a in range(1, 8):
        for b in range(1, 8):
            u, v = Fraction(a, 4), Fraction(b, 8)   # u in (0,2), v in (0,1)
            fx = ref.eval(u, v)
            ox = occt.Value(float(u), float(v))
            worst = max(worst, abs(float(fx[0]) - ox.X()),
                        abs(float(fx[1]) - ox.Y()), abs(float(fx[2]) - ox.Z()))
    assert worst < 1e-12
    # forge partials vs OCCT D1
    from OCP.gp import gp_Vec
    p = gp_Pnt()
    d1u, d1v = gp_Vec(), gp_Vec()
    occt.D1(0.75, 0.5, p, d1u, d1v)
    S, Su, Sv = ref.partials(Fraction(3, 4), Fraction(1, 2))
    assert abs(float(Su[0]) - d1u.X()) < 1e-12
    assert abs(float(Su[2]) - d1u.Z()) < 1e-12
    assert abs(float(Sv[1]) - d1v.Y()) < 1e-12


@pytest.mark.occt
def test_ssi_finds_tangent_branch_occt_misses() -> None:
    """The K3 differentiation moment (kernel-coverage-plan gate G3):
    z=(u-1/2)^2 touches z=0 along the line u=1/2 — a tangential
    intersection branch. OCCT's GeomAPI_IntSS returns ZERO lines for it;
    forge's subdivision SSI finds the branch and certifies points on it
    with exact rational residuals. Also: both agree on the transversal
    ground-truth cases (2 lines / 1 line / certified-empty)."""
    from OCP.Geom import Geom_BezierSurface
    from OCP.GeomAPI import GeomAPI_IntSS
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt

    from forgekernel.ssi import BezierPatch, ssi

    def occt_patch(net):
        arr = TColgp_Array2OfPnt(1, len(net), 1, len(net[0]))
        for i, row in enumerate(net):
            for j, (x, y, z) in enumerate(row):
                arr.SetValue(i + 1, j + 1, gp_Pnt(float(x), float(y), float(z)))
        return Geom_BezierSurface(arr)

    plane_net = [[(0, 0, 0), (0, 1, 0)], [(1, 0, 0), (1, 1, 0)]]

    def quad(b0, b1, b2):
        return [[(0, 0, b0), (0, 1, b0)],
                [(Fraction(1, 2), 0, b1), (Fraction(1, 2), 1, b1)],
                [(1, 0, b2), (1, 1, b2)]]

    cases = [
        ("two-lines", quad(Fraction(3, 16), Fraction(-5, 16), Fraction(3, 16)), 2),
        ("empty", quad(1, 1, 2), 0),
        ("tangent", quad(Fraction(1, 4), Fraction(-1, 4), Fraction(1, 4)), 1),
    ]
    occt_plane = occt_patch(plane_net)
    for name, net, truth in cases:
        inter = GeomAPI_IntSS(occt_plane, occt_patch(net), 1e-7)
        occt_n = inter.NbLines() if inter.IsDone() else -1
        r = ssi(BezierPatch(plane_net), BezierPatch(net), depth=5)
        assert r["branches"] == truth, f"forge wrong on {name}"
        if name == "tangent":
            assert occt_n == 0          # OCCT misses the tangential branch
            assert r["uncertified"] == 0
        else:
            assert occt_n == truth      # both right on transversal cases


@pytest.mark.occt
def test_step_roundtrip_forge_reads_occt_export_exactly(tmp_path) -> None:
    """OCCT exports a freeform B-spline face to STEP; forge's native
    reader parses it and evaluates BITWISE-identically to the original
    OCCT surface (zero delta) — because STEP reals are decimal text and
    forge converts decimal text to exact rationals."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.STEPControl import STEPControl_StepModelType, STEPControl_Writer
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal

    from forgekernel.stepio import read_step_geometry

    net = [[(x, y, Fraction(x * y, 4) + Fraction(x, 8)) for y in range(3)]
           for x in range(4)]
    poles = TColgp_Array2OfPnt(1, 4, 1, 3)
    for i in range(4):
        for j in range(3):
            x, y, z = net[i][j]
            poles.SetValue(i + 1, j + 1, gp_Pnt(float(x), float(y), float(z)))
    uk = TColStd_Array1OfReal(1, 3)
    for i, v in enumerate((0.0, 1.0, 2.0)):
        uk.SetValue(i + 1, v)
    um = TColStd_Array1OfInteger(1, 3)
    for i, v in enumerate((3, 1, 3)):
        um.SetValue(i + 1, v)
    vk = TColStd_Array1OfReal(1, 2)
    for i, v in enumerate((0.0, 1.0)):
        vk.SetValue(i + 1, v)
    vm = TColStd_Array1OfInteger(1, 2)
    for i, v in enumerate((3, 3)):
        vm.SetValue(i + 1, v)
    surf = Geom_BSplineSurface(poles, uk, vk, um, vm, 2, 2)
    face = BRepBuilderAPI_MakeFace(surf, 1e-7).Face()

    path = str(tmp_path / "freeform.step")
    w = STEPControl_Writer()
    w.Transfer(face, STEPControl_StepModelType.STEPControl_AsIs)
    w.Write(path)

    with open(path, encoding="utf-8", errors="replace") as f:
        geo = read_step_geometry(f.read())
    assert len(geo["surfaces"]) == 1
    s = geo["surfaces"][0]
    worst = 0.0
    for a in range(1, 8):
        for b in range(1, 8):
            u, v = Fraction(a, 4), Fraction(b, 8)
            fx = s.eval(u, v)
            ox = surf.Value(float(u), float(v))
            worst = max(worst, abs(float(fx[0]) - ox.X()),
                        abs(float(fx[1]) - ox.Y()), abs(float(fx[2]) - ox.Z()))
    assert worst == 0.0                        # bitwise, not just close
    assert s.cp[1][1] == (1, 1, Fraction(3, 8))  # exact rational recovered


@pytest.mark.occt
def test_full_pipeline_step_to_ssi(tmp_path) -> None:
    """The K3 capstone: OCCT exports a freeform B-spline face to STEP →
    forge's native reader imports it EXACTLY → forge's SSI intersects it
    with a plane, finding the branch with certified points. STEP in,
    certified intersection out — no OCCT in the loop after export."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.STEPControl import STEPControl_StepModelType, STEPControl_Writer
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal

    from forgekernel.nurbs import BSplineSurface
    from forgekernel.ssi import ssi_surfaces
    from forgekernel.stepio import read_step_geometry

    # a sheet rising through z=0: z = u - 1 over u in [0,2] (interior knot)
    net = [[(x, y, Fraction(2 * x - 3, 3)) for y in range(3)] for x in range(4)]
    poles = TColgp_Array2OfPnt(1, 4, 1, 3)
    for i in range(4):
        for j in range(3):
            x, y, z = net[i][j]
            poles.SetValue(i + 1, j + 1, gp_Pnt(float(x), float(y), float(z)))
    uk = TColStd_Array1OfReal(1, 3)
    for i, v in enumerate((0.0, 1.0, 2.0)):
        uk.SetValue(i + 1, v)
    um = TColStd_Array1OfInteger(1, 3)
    for i, v in enumerate((3, 1, 3)):
        um.SetValue(i + 1, v)
    vk = TColStd_Array1OfReal(1, 2)
    for i, v in enumerate((0.0, 1.0)):
        vk.SetValue(i + 1, v)
    vm = TColStd_Array1OfInteger(1, 2)
    for i, v in enumerate((3, 3)):
        vm.SetValue(i + 1, v)
    face = BRepBuilderAPI_MakeFace(
        Geom_BSplineSurface(poles, uk, vk, um, vm, 2, 2), 1e-7).Face()
    path = str(tmp_path / "sheet.step")
    w = STEPControl_Writer()
    w.Transfer(face, STEPControl_StepModelType.STEPControl_AsIs)
    w.Write(path)

    with open(path, encoding="utf-8", errors="replace") as f:
        imported = read_step_geometry(f.read())["surfaces"][0]
    plane = BSplineSurface(1, 1, [[(0, 0, 0), (0, 2, 0)],
                                  [(3, 0, 0), (3, 2, 0)]],
                          [0, 0, 3, 3], [0, 0, 2, 2])
    r = ssi_surfaces(plane, imported, depth=4)
    assert r["branches"] == 1                     # the z=0 crossing line
    assert r["uncertified"] == 0
    assert len(r["points"]) > 0
    # certified points sit on the plane z=0 by construction; the sheet's
    # z=0 line lives where its z(u)=0 — check in SPACE via the plane side
    for u, v, s, t in r["points"]:
        pa = plane.eval(u, v)
        pb = imported.eval(s, t)
        d2 = sum((pa[c] - pb[c]) ** 2 for c in range(3))
        assert d2 < Fraction(1, 10 ** 20)         # exact certificate re-check


@pytest.mark.occt
def test_ruled_multiloft_and_step_import_graduate(tmp_path) -> None:
    """K3.6 graduations, oracle-checked: (1) a ruled 3-section loft is an
    exact prismatoid stack — ref 56 exactly, OCCT 56±1e-14; (2) a planar
    STEP solid (OCCT-exported non-convex L-prism) imports into ref as an
    EXACT Solid with the same volume."""
    from gitcad.kernel.occt import OcctKernel
    from gitcad.kernel.ref import RefKernel

    rk, ok_ = RefKernel(), OcctKernel()

    def sq(z, h):
        return ({"start": [-h, -h], "segments": [
            {"kind": "line", "to": [h, -h]}, {"kind": "line", "to": [h, h]},
            {"kind": "line", "to": [-h, h]},
            {"kind": "line", "to": [-h, -h]}]}, z)

    secs = [sq(0, 2), sq(3, 1), sq(6, 2)]
    vr = rk.mass_props(rk.loft(secs, ruled=True))["volume"]
    vo = ok_.mass_props(ok_.loft(secs, ruled=True))["volume"]
    assert vr == 56.0                            # exact (2×28 prismatoids)
    assert abs(vo - 56.0) < 1e-9                 # OCCT agrees, in float

    L = ok_.extrude({"start": [0, 0], "segments": [
        {"kind": "line", "to": [40, 0]}, {"kind": "line", "to": [40, 10]},
        {"kind": "line", "to": [10, 10]}, {"kind": "line", "to": [10, 30]},
        {"kind": "line", "to": [0, 30]}, {"kind": "line", "to": [0, 0]}]}, 8)
    path = str(tmp_path / "L.step")
    ok_.export_step(L, path)
    imported = rk.import_step(path)
    assert float(imported.volume()) == 4800.0    # exact rational == occt
    assert rk.validate(imported).ok
