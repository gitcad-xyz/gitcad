"""#120: shell of a chamfered box — a ℚ[√2] polyhedron, no torus at all.

A chamfered box is convex, so its erosion is the intersection of its own
half-spaces each offset inward by t. The 6 face planes move t (rational);
the 12 chamfer planes have normals of length √2, so their constants move
t·√2 — and relative to the inset box the void is exactly the chamfered box
of that inset with chamfer depth

    d' = d − (2 − √2)·t        (for the probe d=2, t=1: d' = √2)

which is irrational but lives in ℚ[√2], the field F() already carries.

Closed form, derived from V(a, d) = a³ − 6ad² + 6d³ (inclusion–exclusion
over the 12 edge wedges: pair overlap d³/3 at 24 corner-pairs, triple d³/4
at 8 corners) and verified against an independent Monte-Carlo membership
test (dist to the nearest offset half-space, 16M samples, z = -0.55):

    shell(20³ chamfered 2, t=1) = 7568 − (5616 + 12√2) = 1952 − 12√2
                                = 1935.0294373
"""
from __future__ import annotations

import math

import pytest

pytest.importorskip("forgekernel")

from forgekernel import body as B
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _unpaired(mesh):
    seen: dict = {}
    for t in mesh["triangles"]:
        for i in range(3):
            a, b = t[i], t[(i + 1) % 3]
            seen[(a, b)] = seen.get((a, b), 0) + 1
    return sum(1 for (a, b), n in seen.items() if seen.get((b, a), 0) != n)


def test_chamfered_box_shell_matches_the_closed_form(k) -> None:
    shape = k.chamfer(k.box(20, 20, 20), [], 2)
    shell = k.shell(shape, [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    v = B.volume(body)
    assert float(v) == pytest.approx(1952 - 12 * math.sqrt(2), abs=1e-9)
    assert B.manifold_violations(body) == []
    # planar and closed: the exact Gauss identity must actually run (None
    # would mean NOT CHECKED, and nothing here carries an arc)
    defect = B.vector_area_defect(body)
    assert defect is not None and all(d == 0 for d in defect)
    assert _unpaired(B.tessellate(body, 0.1)) == 0


def test_a_chamfer_swallowed_by_the_offset_leaves_a_plain_box_void(k) -> None:
    """d' = d − (2−√2)t ≤ 0: the offset chamfer plane never reaches the
    inset box, so the void is the plain inset box — exact, not a refusal.
    d=1/2, t=1: d' = 1/2 − (2−√2) ≈ −0.086 < 0. Shell = V_cb − 18³ where
    V_cb = 8000 − 6·20·(1/4) + 6/8 = 7970.75."""
    shape = k.chamfer(k.box(20, 20, 20), [], 0.5)
    shell = k.shell(shape, [], 1)
    body = shell if isinstance(shell, B.Body) else B.to_body(shell)
    assert float(B.volume(body)) == pytest.approx(7970.75 - 5832, abs=1e-9)
    assert B.manifold_violations(body) == []
