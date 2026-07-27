"""K7 through the seam: PatchSolid booleans → a certified TrimmedShell
(#96 gap 5 + the dispatch half of gap 10).

``RefKernel.boolean`` dispatches PatchSolid × PatchSolid operands to
forge's ``boolean_trimmed`` — per face-pair SSI, certified trim loops,
certified fragment membership, principled orientation, full shell audit.
The result carries provenance ``"certified"`` and its volume crosses the
seam as midpoint + ``volume_halfwidth`` ("certified ± e", ADR-0019),
never a bare float.

Configurations the assembly cannot certify surface as K7-staged
structured refusals with the forge guard's own predicate name — tangent
contact, open branches, mixed operands, re-booleaning a result — and the
shell's unbuilt sides (tessellation, bbox/measure) refuse by name
instead of leaking an AttributeError.
"""

from __future__ import annotations

from fractions import Fraction as F

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md); everything
# here needs real geometry.
pytest.importorskip("forgekernel")

from forgekernel.bsolid import PatchSolid, box_patches
from forgekernel.nurbs import bezier_surface
from forgekernel.trimshell import TrimmedShell

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel

# the stage-1 dome (z = 24u(1-u)v(1-v), peak 3/2) closed into the pillow
DOME = bezier_surface([[(0, 0, 0), (0, 2, 0), (0, 4, 0)],
                       [(2, 0, 0), (2, 2, 6), (2, 4, 0)],
                       [(4, 0, 0), (4, 2, 0), (4, 4, 0)]])
BOT = bezier_surface([[(0, 0, 0), (4, 0, 0)], [(0, 4, 0), (4, 4, 0)]])
PILLOW = PatchSolid([DOME, BOT])                            # volume 32/3
BOX = PatchSolid(box_patches(4, 4, 2, origin=(0, 0, 1)))    # volume 32

# independent stage-1 Simpson reference for the cap = pillow ∩ box
CAP_REF = 1.0794724554159079


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def cap(k):
    return k.boolean("intersect", PILLOW, BOX)


def _refusal(fn) -> KernelError:
    with pytest.raises(KernelError) as e:
        fn()
    return e.value


# --- the dispatch: PatchSolid × PatchSolid reaches K7 and comes back ---------

def test_boolean_of_patch_solids_returns_an_audited_shell(cap) -> None:
    assert isinstance(cap, TrimmedShell)
    assert cap.provenance == "certified"
    assert len(cap.faces) == 2


def test_mass_props_reports_certified_volume_with_its_bracket(k, cap) -> None:
    mp = k.mass_props(cap)
    assert mp["provenance"] == "certified"
    assert mp["volume_halfwidth"] > 0.0
    # the bracket is a PROOF: the midpoint sits within halfwidth of truth
    assert abs(mp["volume"] - CAP_REF) <= mp["volume_halfwidth"]
    # no certified centroid machinery exists for trimmed shells — the
    # honest answer is a flagged non-answer, not a fabricated location
    assert mp["centroid_unavailable"] is True


def test_validate_runs_the_shell_audit_and_carries_provenance(k, cap) -> None:
    report = k.validate(cap)
    assert report.ok
    assert report.checks["provenance"] == "certified"
    assert report.checks["faces"] == 2


# --- refusals: forge guard names cross the seam intact -----------------------

def test_tangent_contact_is_a_k7_staged_refusal(k) -> None:
    graze = PatchSolid(box_patches(4, 4, 1, origin=(0, 0, F(3, 2))))
    err = _refusal(lambda: k.boolean("intersect", PILLOW, graze))
    assert err.stage is not None and "K7" in err.stage
    assert err.predicate is not None
    assert err.remedy


def test_open_branch_is_a_k7_staged_refusal(k) -> None:
    half = PatchSolid(box_patches(2, 4, 2, origin=(0, 0, 1)))
    err = _refusal(lambda: k.boolean("intersect", PILLOW, half))
    assert err.stage is not None and "K7" in err.stage
    assert err.predicate is not None


def test_mixed_patchsolid_operand_refuses_by_name(k) -> None:
    err = _refusal(lambda: k.boolean("cut", PILLOW, k.box(4, 4, 4)))
    assert err.stage is not None and "K7" in err.stage
    assert err.predicate == "mixed_patchsolid_boolean_unbuilt"


def test_rebooleaning_a_result_refuses_by_name(k, cap) -> None:
    err = _refusal(lambda: k.boolean("cut", cap, BOX))
    assert err.stage is not None and "K7" in err.stage
    assert err.predicate == "trimmed_shell_reboolean_unbuilt"


def test_the_refusals_serialise_for_an_agent(k) -> None:
    import json

    graze = PatchSolid(box_patches(4, 4, 1, origin=(0, 0, F(3, 2))))
    err = _refusal(lambda: k.boolean("intersect", PILLOW, graze))
    json.dumps(err.as_dict())


# --- the shell's unbuilt sides refuse by name, never AttributeError ----------

def test_tessellate_of_a_trimmed_shell_refuses_by_name(k, cap) -> None:
    err = _refusal(lambda: k.tessellate(cap))
    assert err.stage is not None and "K7" in err.stage
    assert "no attribute" not in str(err)


def test_bbox_and_measure_of_a_trimmed_shell_refuse_by_name(k, cap) -> None:
    for fn in (lambda: k.bbox(cap), lambda: k.measure(cap)):
        err = _refusal(fn)
        assert err.stage is not None and "K7" in err.stage
        assert "no attribute" not in str(err)
