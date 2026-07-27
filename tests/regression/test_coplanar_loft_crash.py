"""Chip task_f68af885: coincident-wall loft booleans crashed through the seam.

Union (and cut) of two lofts sharing an EXACTLY coincident wall — A's
x=2 face is B's x=2 face with opposite outward normals — raised a raw
``builtins.ValueError("all four parameters fixed — nothing to solve")``
from forge's ``ssi._refine_constrained`` straight through
``RefKernel.boolean``: the seam's except-list wraps the five structured
K7 refusal types and correctly does NOT catch bare ValueError. Shipped
in the released 0.9.8 wheels; reachable from the fully public
``k.loft(...) → k.boolean(...)`` path.

Root cause: when a corner cell of A's coincident wall pairs with a
corner cell of B's, the border-pinning last resort pins ALL FOUR
parameters — a fully-determined candidate point that the code treated
as an error instead of evaluating (the exact residual certificate
decides, 0 Newton iterations; the same matched-corner-probe idiom the
file already uses).

Violated invariant: the zero-crash rule — every kernel refusal crosses
the seam as a structured ``KernelError`` naming its predicate; a raw
Python exception through the seam is a defect (capability-matrix CRASH
class). Coincident contact stays REFUSED (tangential contact is
genuinely uncertifiable by subdivision — deepening never prunes
coincident surfaces); these tests pin refusal shape, not a merge.
"""

from __future__ import annotations

import pytest

from gitcad.errors import KernelError

pytest.importorskip("forgekernel")

from forgekernel.loft import LoftSolid

from gitcad.kernel.ref import RefKernel


def _sq(x0, x1, y0, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _coincident_pair():
    a = LoftSolid([(_sq(0, 2, 0, 2), 0), (_sq(0, 2, 0, 2), 1),
                   (_sq(0, 2, 0, 2), 2)])
    b = LoftSolid([(_sq(2, 4, 0, 2), 0), (_sq(2, 4, 0, 2), 1),
                   (_sq(2, 4, 0, 2), 2)])
    return a, b


@pytest.mark.parametrize("op", ["union", "cut", "intersect"])
def test_coincident_wall_boolean_is_a_structured_refusal(op) -> None:
    a, b = _coincident_pair()
    k = RefKernel()
    with pytest.raises(KernelError) as ei:
        k.boolean(op, a, b)
    assert ei.value.predicate == "ssi_cell_uncertified"


@pytest.mark.parametrize("op", ["union", "cut"])
def test_no_raw_exception_escapes_the_seam(op) -> None:
    a, b = _coincident_pair()
    k = RefKernel()
    try:
        k.boolean(op, a, b)
    except KernelError:
        pass                        # the only acceptable exception type
