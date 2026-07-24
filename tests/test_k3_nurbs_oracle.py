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


@pytest.mark.occt
def test_gaussian_curvature_matches_occt_slprops() -> None:
    """forge's EXACT rational Gaussian curvature vs OCCT's float
    GeomLProp_SLProps on the same biquadratic patch — OCCT approximates
    what forge holds exactly (and forge's developable K is exactly 0)."""
    from OCP.Geom import Geom_BezierSurface
    from OCP.GeomLProp import GeomLProp_SLProps
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt

    from forgekernel.nurbs import bezier_surface
    from forgekernel.surfacing import gaussian_curvature

    B = [0, 0, 1]
    net = [[(Fraction(i, 2), Fraction(j, 2), B[i] + B[j])
            for j in range(3)] for i in range(3)]
    ref = bezier_surface(net)
    arr = TColgp_Array2OfPnt(1, 3, 1, 3)
    for i in range(3):
        for j in range(3):
            x, y, z = net[i][j]
            arr.SetValue(i + 1, j + 1, gp_Pnt(float(x), float(y), float(z)))
    occt = Geom_BezierSurface(arr)
    for (u, v) in ((Fraction(0), Fraction(0)), (Fraction(1, 2), Fraction(1, 2)),
                   (Fraction(1, 4), Fraction(3, 4))):
        props = GeomLProp_SLProps(occt, float(u), float(v), 2, 1e-9)
        k_ref = gaussian_curvature(ref, u, v)
        assert abs(float(k_ref) - props.GaussianCurvature()) < 1e-9
    # the exact-zero check no float kernel can make: a developable's K
    cyl = bezier_surface([[(Fraction(i, 2), j, B[i]) for j in range(2)]
                          for i in range(3)])
    assert gaussian_curvature(cyl, Fraction(1, 3), Fraction(2, 7)) == 0


@pytest.mark.occt
def test_freeform_solid_volume_exact_vs_occt(tmp_path) -> None:
    """K7.0: forge computes the volume of a Bézier-patch-bounded solid as
    an EXACT rational (divergence-theorem flux of a polynomial integrand);
    OCCT sews the same 6 faces and integrates numerically. They agree, but
    forge's answer is a Fraction, not a float."""
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakeSolid,
                                    BRepBuilderAPI_Sewing)
    from OCP.BRepGProp import BRepGProp
    from OCP.Geom import Geom_BezierSurface
    from OCP.gp import gp_Pnt
    from OCP.GProp import GProp_GProps
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    from forgekernel.bsolid import PatchSolid, box_patches
    from forgekernel.nurbs import bezier_surface

    xs, ys = [Fraction(0), Fraction(3, 2), Fraction(3)], \
        [Fraction(0), Fraction(2), Fraction(4)]
    znet = [[5, 5, 5], [5, 8, 5], [5, 5, 5]]
    top = bezier_surface([[(xs[i], ys[j], znet[i][j]) for j in range(3)]
                          for i in range(3)])
    patches = box_patches(3, 4, 5)
    patches[1] = top
    v_ref = PatchSolid(patches).volume()
    assert isinstance(v_ref, Fraction)              # EXACT

    def occ_face(patch):
        net = patch.cp
        a = TColgp_Array2OfPnt(1, len(net), 1, len(net[0]))
        for i, row in enumerate(net):
            for j, pt in enumerate(row):
                a.SetValue(i + 1, j + 1,
                           gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))
        return BRepBuilderAPI_MakeFace(Geom_BezierSurface(a), 1e-7).Face()

    sew = BRepBuilderAPI_Sewing(1e-6)
    for p in patches:
        sew.Add(occ_face(p))
    sew.Perform()
    exp = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
    solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(exp.Current())).Solid()
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, g)
    assert abs(float(v_ref) - abs(g.Mass())) < 1e-6


@pytest.mark.occt
def test_freeform_inertia_tensor_matches_occt() -> None:
    """K7.0b: forge's EXACT rational inertia tensor of a bulged freeform
    solid vs OCCT's float MatrixOfInertia (about the centre of mass)."""
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakeSolid,
                                    BRepBuilderAPI_Sewing)
    from OCP.BRepGProp import BRepGProp
    from OCP.Geom import Geom_BezierSurface
    from OCP.gp import gp_Pnt
    from OCP.GProp import GProp_GProps
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    from forgekernel.bsolid import PatchSolid, box_patches, mass_properties
    from forgekernel.nurbs import bezier_surface

    xs, ys = [Fraction(0), Fraction(3, 2), Fraction(3)], \
        [Fraction(0), Fraction(2), Fraction(4)]
    top = bezier_surface([[(xs[i], ys[j], [[5, 5, 5], [5, 8, 5], [5, 5, 5]][i][j])
                           for j in range(3)] for i in range(3)])
    patches = box_patches(3, 4, 5)
    patches[1] = top
    mp = mass_properties(PatchSolid(patches))
    assert all(isinstance(mp["inertia"][i][j], Fraction)
               for i in range(3) for j in range(3))          # EXACT

    def occ_face(patch):
        net = patch.cp
        a = TColgp_Array2OfPnt(1, len(net), 1, len(net[0]))
        for i, row in enumerate(net):
            for j, pt in enumerate(row):
                a.SetValue(i + 1, j + 1,
                           gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))
        return BRepBuilderAPI_MakeFace(Geom_BezierSurface(a), 1e-7).Face()

    sew = BRepBuilderAPI_Sewing(1e-6)
    for p in patches:
        sew.Add(occ_face(p))
    sew.Perform()
    exp = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
    solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(exp.Current())).Solid()
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, g)
    m = g.MatrixOfInertia()             # about the centre of mass
    ref = mp["inertia"]
    for i in range(3):
        for j in range(3):
            assert abs(float(ref[i][j]) - m.Value(i + 1, j + 1)) < 1e-6


@pytest.mark.occt
def test_forge_step_export_reads_in_occt(tmp_path) -> None:
    """K7.0c: OCCT reads forge's natively-written STEP and recovers the
    exact solid volume — OCCT-free CAD export, verified by the 30-year
    kernel. Box and a non-convex L-prism (triangulated faces)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.STEPControl import STEPControl_Reader

    from gitcad.kernel.ref import RefKernel

    k = RefKernel()

    def occt_volume(path):
        r = STEPControl_Reader()
        r.ReadFile(path)
        r.TransferRoots()
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(r.OneShape(), g)
        return g.Mass()

    box_path = str(tmp_path / "box.step")
    k.export_step(k.box(6, 4, 3), box_path)
    assert abs(occt_volume(box_path) - 72) < 1e-6

    L = k.extrude({"start": [0, 0], "segments": [
        {"kind": "line", "to": [40, 0]}, {"kind": "line", "to": [40, 10]},
        {"kind": "line", "to": [10, 10]}, {"kind": "line", "to": [10, 30]},
        {"kind": "line", "to": [0, 30]}, {"kind": "line", "to": [0, 0]}]}, 8)
    L_path = str(tmp_path / "L.step")
    k.export_step(L, L_path)
    assert abs(occt_volume(L_path) - 4800) < 1e-6


@pytest.mark.occt
def test_spline_profile_extrude_matches_occt() -> None:
    """K3.8: forge's Green's-theorem spline-profile volume is exact ℚ;
    OCCT extrudes the same Bézier-edge face and integrates numerically."""
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge,
                                    BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakeWire)
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.Geom import Geom_BezierCurve
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.GProp import GProp_GProps
    from OCP.TColgp import TColgp_Array1OfPnt

    from gitcad.kernel.ref import RefKernel

    prof = {"start": [0, 0], "segments": [
        {"kind": "line", "to": [10, 0]},
        {"kind": "spline", "to": [0, 0], "ctrl": [[12, 7], [-2, 7]]}]}
    v_ref = RefKernel().extrude(prof, 5).volume()
    assert isinstance(v_ref, Fraction) and v_ref == 231

    e_line = BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(10, 0, 0)).Edge()
    arr = TColgp_Array1OfPnt(1, 4)
    for i, (x, y) in enumerate([(10, 0), (12, 7), (-2, 7), (0, 0)]):
        arr.SetValue(i + 1, gp_Pnt(x, y, 0))
    e_bez = BRepBuilderAPI_MakeEdge(Geom_BezierCurve(arr)).Edge()
    wire = BRepBuilderAPI_MakeWire(e_line, e_bez).Wire()
    face = BRepBuilderAPI_MakeFace(wire, True).Face()
    solid = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, 5)).Shape()
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, g)
    assert abs(float(v_ref) - abs(g.Mass())) < 1e-6


@pytest.mark.occt
def test_trimmed_region_classification_beats_occt_tolerance() -> None:
    """K7 point-in-trimmed-region: forge's even-odd parity decides in/on/out
    in ℚ with NO tolerance, so it correctly calls a point one nanometre
    (1e-9) inside a boundary "in". OCCT's BRepClass_FaceClassifier is
    tolerance-based: at a realistic 1e-7 it rounds those same interior
    points to "on" (wrong). This is the exactness win — forge distinguishes
    near-boundary points OCCT cannot, and its answer never flips with a
    tolerance knob."""
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakePolygon)
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt, gp_Pnt2d
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT

    from forgekernel.nurbs import BSplineSurface
    from forgekernel.trim import TrimmedPatch

    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    plane = BSplineSurface(1, 1, [[(0, 0, 0), (0, 10, 0)], [(10, 0, 0), (10, 10, 0)]],
                           [0, 0, 10, 10], [0, 0, 10, 10])
    tp = TrimmedPatch(plane, [square])

    poly = BRepBuilderAPI_MakePolygon()
    for x, y in square:
        poly.Add(gp_Pnt(x, y, 0))
    poly.Close()
    pln = gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))         # UV == XY
    face = BRepBuilderAPI_MakeFace(pln, poly.Wire(), True).Face()
    state = {TopAbs_IN: "in", TopAbs_OUT: "out", TopAbs_ON: "on"}

    def occt(u, v, tol):
        cl = BRepClass_FaceClassifier(face, gp_Pnt2d(float(u), float(v)), tol)
        return state.get(cl.State(), "?")

    eps = Fraction(1, 10 ** 9)                              # 1 nm inside
    interior = [(Fraction(5), eps), (eps, Fraction(5)), (eps, eps)]
    for u, v in interior:
        assert tp.classify(u, v) == "in"                   # forge: exact, no tol
        assert occt(u, v, 1e-7) == "on"                    # OCCT: tolerance-fooled
    # forge's verdict is tolerance-independent by construction; OCCT's flips
    assert tp.classify(Fraction(5), eps) == "in"
    # exactly on the boundary is an honest "on", not silently in/out
    assert tp.classify(Fraction(5), 0) == "on"
    assert tp.classify(Fraction(5), Fraction(5)) == "in"   # deep interior: agree
    assert occt(5, 5, 1e-7) == "in"


@pytest.mark.occt
def test_spline_prism_exact_centroid_matches_occt_and_beats_bbox() -> None:
    """K3.7 mass properties: forge computes a spline-extruded solid's centroid
    EXACTLY (Green's-theorem area moments in ℚ). For an asymmetric curved
    profile the true area centroid (y=51/22≈2.318) is far from the bbox
    centre (y=3.5) the old code returned — and OCCT's independent float
    integration agrees with forge, not the bbox."""
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge,
                                    BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakeWire)
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.Geom import Geom_BezierCurve
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.GProp import GProp_GProps
    from OCP.TColgp import TColgp_Array1OfPnt

    from forgekernel.profile2d import SplinePrism

    prof = [{"kind": "line", "to": [10, 0]},
            {"kind": "spline", "to": [0, 0], "ctrl": [[12, 7], [-2, 7]]}]
    pr = SplinePrism([0, 0], prof, 5)
    cx, cy, cz = pr.centroid()
    assert (cx, cy, cz) == (Fraction(5), Fraction(51, 22), Fraction(5, 2))

    e_line = BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(10, 0, 0)).Edge()
    arr = TColgp_Array1OfPnt(1, 4)
    for i, (x, y) in enumerate([(10, 0), (12, 7), (-2, 7), (0, 0)]):
        arr.SetValue(i + 1, gp_Pnt(x, y, 0))
    e_bez = BRepBuilderAPI_MakeEdge(Geom_BezierCurve(arr)).Edge()
    wire = BRepBuilderAPI_MakeWire(e_line, e_bez).Wire()
    face = BRepBuilderAPI_MakeFace(wire, True).Face()
    solid = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, 5)).Shape()
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, g)
    com = g.CentreOfMass()
    assert abs(float(cx) - com.X()) < 1e-9
    assert abs(float(cy) - com.Y()) < 1e-9        # OCCT agrees with forge
    assert abs(float(cz) - com.Z()) < 1e-9
    assert abs(com.Y() - 3.5) > 0.5               # ...and NOT with the bbox centre
