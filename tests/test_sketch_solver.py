"""Golden: ADR-0013 sketch constraint solver — authoring-time, exact output.

Kernel-free by design: the solver emits plain Profiles; nothing here touches
geometry. Oracles are exact coordinates a constrained sketch must reach.
"""

import pytest

from gitcad.errors import GitcadError
from gitcad.sketch_solver import ConstraintSketch


def _rough_rect():
    """A sloppy hand-drawn 30x20 rectangle: corners off by up to ~2mm."""
    s = ConstraintSketch()
    s.point("a", 0.3, -0.4)
    s.point("b", 29.1, 1.2)
    s.point("c", 31.0, 21.5)
    s.point("d", -1.8, 19.2)
    s.fix("a", 0, 0)
    s.horizontal("a", "b")
    s.vertical("b", "c")
    s.horizontal("c", "d")
    s.vertical("d", "a")
    s.distance("a", "b", 30)
    s.distance("b", "c", 20)
    return s


def test_constrained_rectangle_solves_exact():
    s = _rough_rect()
    result = s.solve()
    assert result.converged
    assert result.points["a"] == pytest.approx((0, 0), abs=1e-8)
    assert result.points["b"] == pytest.approx((30, 0), abs=1e-8)
    assert result.points["c"] == pytest.approx((30, 20), abs=1e-8)
    assert result.points["d"] == pytest.approx((0, 20), abs=1e-8)
    assert result.dof == 0                     # fully constrained

    prof = s.profile("a", "b", "c", "d")
    params = prof.to_params()                  # validates closure
    assert params["start"] == [0, 0]
    assert len(params["segments"]) == 4


def test_under_constrained_reports_dof():
    s = ConstraintSketch()
    s.point("a", 0, 0)
    s.point("b", 9.7, 0.4)
    s.fix("a", 0, 0)
    s.distance("a", "b", 10)
    result = s.solve()
    assert result.converged
    assert result.dof == 1                     # b can still rotate about a
    # the solved b honors the distance exactly
    bx, by = result.points["b"]
    assert bx * bx + by * by == pytest.approx(100.0, abs=1e-8)


def test_branch_pinned_by_initial_guess():
    # Same constraints, mirrored guesses -> mirrored solutions (ADR-0013:
    # the drawn position picks the branch; the solver never surprises).
    for guess, expected_sign in ((5.0, 1.0), (-5.0, -1.0)):
        s = ConstraintSketch()
        s.point("a", 0, 0)
        s.point("b", guess, 3)
        s.fix("a", 0, 0)
        s.horizontal("a", "b")
        s.distance("a", "b", 10)
        r = s.solve()
        assert r.points["b"][0] == pytest.approx(10.0 * expected_sign, abs=1e-8)


def test_conflicting_constraints_fail_loud():
    s = ConstraintSketch()
    s.point("a", 0, 0)
    s.point("b", 10, 0)
    s.fix("a", 0, 0)
    s.fix("b", 10, 0)
    s.distance("a", "b", 25)                   # impossible: both ends fixed
    with pytest.raises(GitcadError, match="did not converge"):
        s.solve()


def test_perpendicular_parallel_equal():
    s = ConstraintSketch()
    s.point("a", 0, 0)
    s.point("b", 10.2, 0.1)
    s.point("c", 10.1, 9.7)
    s.point("d", -0.2, 10.3)
    s.fix("a", 0, 0)
    s.angle("a", "b", 0)                       # a->b along +x
    s.distance("a", "b", 12)
    s.perpendicular(("a", "b"), ("b", "c"))
    s.parallel(("a", "b"), ("d", "c"))
    s.equal_length(("a", "b"), ("b", "c"))
    s.vertical("d", "a")
    r = s.solve()
    assert r.converged
    assert r.points["b"] == pytest.approx((12, 0), abs=1e-7)
    assert r.points["c"] == pytest.approx((12, 12), abs=1e-7)
    assert r.points["d"] == pytest.approx((0, 12), abs=1e-7)


def test_duplicate_and_unknown_points_error():
    s = ConstraintSketch()
    s.point("a", 0, 0)
    with pytest.raises(GitcadError, match="duplicate"):
        s.point("a", 1, 1)
    with pytest.raises(GitcadError, match="unknown point"):
        s.horizontal("a", "zz")
