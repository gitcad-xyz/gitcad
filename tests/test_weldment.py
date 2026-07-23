"""Weldments: 3D sketch + structural members + cut list (fabricator BOM)."""

from fractions import Fraction

import pytest

from gitcad.errors import GitcadError
from gitcad.weldment import Sketch3D, StructuralProfile, Weldment


def _frame():
    s = Sketch3D()
    for n, (x, y) in {"A": (0, 0), "B": (600, 0),
                      "C": (600, 400), "D": (0, 400)}.items():
        s.vertex(n, x, y, 0)
    for a, b in [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]:
        s.segment(a, b)
    return s


def test_structural_profile_area_is_exact() -> None:
    rt = StructuralProfile.rect_tube(40, 40, 3)
    assert rt.area == Fraction(444)                 # 40² − 34², exact
    assert isinstance(StructuralProfile.l_angle(50, 50, 5).area, Fraction)
    assert StructuralProfile.flat_bar(20, 4).area == 80


def test_rect_tube_rejects_thick_wall() -> None:
    with pytest.raises(GitcadError, match="wall too thick"):
        StructuralProfile.rect_tube(10, 10, 5)


def test_cut_list_groups_members() -> None:
    w = Weldment(_frame(), StructuralProfile.rect_tube(40, 40, 3))
    cl = w.cut_list()
    lengths = {(r["length"], r["qty"]) for r in cl}
    assert lengths == {(600.0, 2), (400.0, 2)}
    assert w.total_length() == 2000.0
    assert all(r["profile"] == "RT40x40x3" for r in cl)


def test_mass_uses_exact_area() -> None:
    w = Weldment(_frame(), StructuralProfile.rect_tube(40, 40, 3))
    # 444 mm² × 2000 mm × 7.85e-6 kg/mm³ = 6.9708 kg
    assert abs(w.mass(7.85e-6) - 444 * 2000 * 7.85e-6) < 1e-9


def test_per_member_profile_override_and_stock_summary() -> None:
    s = _frame()
    w = Weldment(s, StructuralProfile.rect_tube(40, 40, 3))
    w.set_profile("A", "B", StructuralProfile.l_angle(50, 50, 5))
    profiles = {r["profile"] for r in w.cut_list()}
    assert "L50x50x5" in profiles and "RT40x40x3" in profiles
    ss = w.stock_summary()
    assert ss["L50x50x5"] == 600.0 and ss["RT40x40x3"] == 1400.0


def test_unknown_vertex_segment_refuses() -> None:
    s = Sketch3D().vertex("A", 0, 0, 0)
    with pytest.raises(GitcadError, match="unknown vertex"):
        s.segment("A", "Z")
