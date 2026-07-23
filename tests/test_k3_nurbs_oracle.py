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
