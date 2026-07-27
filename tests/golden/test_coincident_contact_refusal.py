"""Seam contract: coincident-face contact refuses structured, by name.

Face-on-face contact between freeform operands (two lofts glued along
an exactly shared wall — the classic mating-assembly geometry) is
tangential: SSI subdivision can never prune coincident surfaces, so no
certified intersection curve exists at any depth. The kernel's answer
is a STRUCTURED refusal — ``KernelError`` with stage K7 and predicate
``ssi_cell_uncertified`` — never a raw Python exception (the released
0.9.8 wheels crashed here with a bare ValueError; the zero-crash rule
is the contract this golden pins).

The geometry is hand-checkable: A spans x∈[0,2], B spans x∈[2,4], same
square z-stack — B is A translated by +2 in x, the shared wall is the
whole x=2 face.
"""

from __future__ import annotations

import pytest

from gitcad.errors import KernelError

pytest.importorskip("forgekernel")

from forgekernel.loft import LoftSolid

from gitcad.kernel.ref import RefKernel


def _sq(x0, x1):
    return [(x0, 0), (x1, 0), (x1, 2), (x0, 2)]


A = LoftSolid([(_sq(0, 2), 0), (_sq(0, 2), 1), (_sq(0, 2), 2)])
B = LoftSolid([(_sq(2, 4), 0), (_sq(2, 4), 1), (_sq(2, 4), 2)])


@pytest.mark.parametrize("op", ["union", "cut", "intersect"])
def test_coincident_contact_refusal_names_its_predicate(op) -> None:
    with pytest.raises(KernelError) as ei:
        RefKernel().boolean(op, A, B)
    exc = ei.value
    assert exc.predicate == "ssi_cell_uncertified"
    assert exc.signature.op.startswith(f"boolean.{op}")
