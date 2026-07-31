"""A chamfer of a NON-CONVEX solid must refuse, not silently over-remove.

This file was originally #131: it meshed ``chamfer(shell(box), all, 1)`` — a
shelled-then-chamfered box — to pin a mesher T-junction-sliver fix. Dogfooding
later showed that operation was **silently wrong at the source**: chamfer's
per-edge tool is sized to the whole-part bounding box, which only a CONVEX solid
clips to the local wedge. On a shelled box (non-convex) the oversized tool
reaches across the cavity and over-removes — measured ~14x too much at c=1
(1596 mm3 removed where the outer edges lose ~114), reported ``exact``, passing
``validate()`` and meshing watertight. The old volume assertion here never
caught it because it checked mesh-vs-kernel self-consistency, not truth.

The fix (forge ``brep.solid_is_convex`` guard in ``chamfer_planar``) makes a
non-convex chamfer an honest refusal — the charter's rule, and the same one
``_require_convex`` already enforces for quadric booleans. This test now pins
that refusal. The mesher collinearity fix #131 originally guarded lives on
independently in forge ``tests/test_mesh2d_collinear.py``, so no coverage is
lost by repurposing this contract.
"""

from __future__ import annotations

import pytest

pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def test_chamfer_of_a_shelled_box_refuses_rather_than_over_removing(k) -> None:
    """A shelled box is non-convex; its chamfer used to silently remove ~14x
    too much. It must refuse now, by name."""
    shelled = k.shell(k.box(20, 20, 20), (), 2)
    with pytest.raises(KernelError, match="non-convex"):
        k.chamfer(shelled, [], 1)


def test_a_convex_box_still_chamfers_exactly(k) -> None:
    """The guard must not touch the convex case: a plain box removes the
    correct c^2-scaling wedge (114 mm3 at c=1 on a 20-cube)."""
    box = k.box(20, 20, 20)
    v0 = float(k.mass_props(box)["volume"])
    for c, want in ((0.5, 29.25), (1.0, 114.0)):
        removed = v0 - float(k.mass_props(k.chamfer(box, [], c))["volume"])
        assert removed == pytest.approx(want), (c, removed)


def test_the_refusal_is_an_honest_stage_named_gap(k) -> None:
    """Not a raw crash: a KernelError with the K5.2 stage, like every other
    honest refusal — the distinction the charter draws."""
    shelled = k.shell(k.box(20, 20, 20), (), 2)
    try:
        k.chamfer(shelled, [], 1)
        assert False, "should have refused"
    except KernelError as exc:
        assert "K5.2" in str(exc) or "non-convex" in str(exc)
