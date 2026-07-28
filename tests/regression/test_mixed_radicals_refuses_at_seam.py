"""A boolean across two different quadratic fields refuses; it never crashes.

Found by the certified-tier audit (2026-07-28). ``k.boolean("cut", rot45_box,
rot30_box)`` raised ``builtins.ValueError: mixed radicals √3 and √2`` straight
out of ``forgekernel/surd.py`` — unwrapped, through the Kernel seam. By the
capability bench's own taxonomy a raw exception escaping the seam is a CRASH,
always a defect.

The irony is the point: ℚ[√2] and ℚ[√3] genuinely have no common home until
the biquadratic tower (#127, K3.1), so this is one of the few walls that IS
about exactness — and it was the one place the seam failed to say so. Every
other exact-field boundary in this kernel surfaces as a structured refusal.

Root cause: the bbox-separation early-out in ``boolean`` compares coordinates
that may live in different fields, and nothing caught the field error.
Violated invariant: every failure crosses the seam as a structured refusal
naming its stage (ADR-0019 / #114); a raw exception a caller cannot tell from
a bug is never acceptable.
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


def _rot(k, shape, deg, axis=(0, 0, 1)):
    return k.transform(shape, rotate_axis=axis, rotate_deg=deg)


def test_cut_across_two_radicals_refuses_structurally():
    """The verbatim repro from the audit."""
    k = RefKernel()
    a45 = _rot(k, k.box(10, 10, 10), 45)   # ℚ[√2]
    b30 = _rot(k, k.box(10, 10, 10), 30)   # ℚ[√3]

    with pytest.raises(KernelError) as exc:
        k.boolean("cut", a45, b30)

    err = exc.value
    assert err.stage.startswith("K3.1")
    assert err.predicate == "mixed_radicals"
    assert set(err.measured.values()) >= {2, 3}
    assert err.remedy  # says what would make it work


def test_it_is_not_a_raw_exception():
    """The specific defect: the failure must not arrive as a bare
    ValueError from inside forge. KernelError is not a ValueError, so
    catching KernelError and re-checking the type is the whole assertion."""
    k = RefKernel()
    a45 = _rot(k, k.box(10, 10, 10), 45)
    b30 = _rot(k, k.box(10, 10, 10), 30)

    try:
        k.boolean("cut", a45, b30)
    except KernelError:
        pass  # correct
    except ValueError as raw:  # pragma: no cover - this is the regression
        pytest.fail(f"raw {type(raw).__name__} escaped the seam: {raw}")


def test_one_shared_radical_still_computes_exactly():
    """Control. Both operands in ℚ[√2] is not a wall and must stay exact —
    a guard that refused this would close ordinary rotated booleans."""
    k = RefKernel()
    a45 = _rot(k, k.box(10, 10, 10), 45)
    tool = _rot(k, k.box(2, 2, 100), 45)

    out = k.boolean("cut", a45, tool)
    assert k.mass_props(out)["volume"] < 1000.0  # material was removed


def test_a_rational_rotation_against_a_radical_one_is_fine():
    """90° carries no radical at all (ℚ), so pairing it with a 45° body
    must NOT trip the guard — b == 0 means there is no radical to mix."""
    k = RefKernel()
    a90 = _rot(k, k.box(10, 10, 10), 90)
    tool45 = _rot(k, k.box(2, 2, 100), 45)

    out = k.boolean("cut", a90, tool45)
    assert k.mass_props(out)["volume"] < 1000.0
