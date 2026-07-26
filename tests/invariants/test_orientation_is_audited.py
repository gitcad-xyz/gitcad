"""Edge pairing counts uses. It never looks at direction.

`manifold_violations` asks how many faces use each edge. Reverse one face's
loop and every edge is still used exactly twice, so it reports nothing — the
shell is inside-out on that face and the audit shrugs. Measured, not assumed:
the assertion below fails on the pairing check and passes on this one.

Gauss closes the gap. For a closed surface the face vector areas sum to zero,
and vector area is a BOUNDARY integral — (1/2)∮ r × dr — so it needs no
per-surface area formula, only the loop, and it is exact in ℚ for straight
edges.

WHAT IT DOES NOT COVER, stated because a half-run check is worse than none: a
body carrying a circular edge is skipped WHOLE and returns None, which callers
must read as "not checked", never "passed". The arc term is
(1/2)[c × (p₁ − p₀) + r²·Δθ·n̂] — derived, exact in ℚ[π] via the twelfth span,
not yet implemented. Summing only the straight edges of a body that has arcs
would be nonzero for a perfectly good solid, which is why it skips rather than
partially sums.
"""

from __future__ import annotations

import pytest

from forgekernel import body as B
from forgekernel.brep import Solid
from forgekernel.quadric import Cyl


def _reverse_one_face(bd):
    f0 = bd.faces[0]
    rev = B.Loop([B.Edge(e.curve, e.v1, e.v0)
                  for e in reversed(f0.loops[0].edges)])
    return B.Body([B.Face(f0.surface, [rev], f0.sense)] + list(bd.faces[1:]))


def test_a_correct_shell_sums_to_exactly_zero() -> None:
    for solid in (Solid.box(20, 20, 10), Solid.box(30, 20, 10)):
        assert B.vector_area_defect(B.to_body(solid)) == (0, 0, 0)


def test_edge_pairing_is_blind_to_a_reversed_face_and_this_is_not() -> None:
    """The whole reason the check exists, pinned as a comparison so nobody
    later 'simplifies' it away as redundant with pairing."""
    broken = _reverse_one_face(B.to_body(Solid.box(20, 20, 10)))

    assert B.manifold_violations(broken) == [], (
        "if pairing ever starts catching this, say so here — but as of now it "
        "does not, which is what makes the vector-area check load-bearing")

    defect = B.vector_area_defect(broken)
    assert defect is not None and any(d != 0 for d in defect), (
        "a reversed face must be caught")
    assert defect == (0, 0, 800), f"expected (0,0,800), got {defect}"


def test_a_body_with_arcs_is_skipped_whole_not_partially_summed() -> None:
    """None means NOT CHECKED. A partial sum over only the straight edges
    would be nonzero for a correct solid and would fire on every cylinder."""
    assert B.vector_area_defect(B.to_body(Cyl(0, 0, 5, 0, 12))) is None


def test_the_audit_runs_it_on_every_corpus_shape_it_can(  # noqa: D103
) -> None:
    from gitcad.bench.capability import representations
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    checked = 0
    for name, shape in representations(k).items():
        if isinstance(shape, tuple):
            continue
        canon = shape if isinstance(shape, B.Body) else B.to_body(shape)
        defect = B.vector_area_defect(canon)
        if defect is None:
            continue                      # carries arcs — honestly not checked
        checked += 1
        assert all(d == 0 for d in defect), (
            f"{name}: shell vector areas sum to {defect}, not zero")
    assert checked >= 3, (
        f"only {checked} corpus shapes were orientation-checked — if this "
        "drops to zero the check has silently stopped applying to anything")
