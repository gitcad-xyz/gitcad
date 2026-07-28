"""A boolean across two quadratic fields COMPUTES; a degree-8 one refuses.
Neither ever crashes.

Found by the certified-tier audit (2026-07-28). ``k.boolean("cut", rot45_box,
rot30_box)`` raised ``builtins.ValueError: mixed radicals √3 and √2`` straight
out of ``forgekernel/surd.py`` — unwrapped, through the Kernel seam. By the
capability bench's own taxonomy a raw exception escaping the seam is a CRASH,
always a defect.

That was fixed twice. First the refusal was named and wrapped, which is what
this file originally pinned. Then #127 connected ``SurdVal`` to ``BiSurd``,
which had held ℚ(√p,√q) — arithmetic, comparison, sign, inverse — the whole
time without ever being wired in, and ℚ[√2] with ℚ[√3] stopped being a wall at
all. A 45° body cutting a 30° body is now an ordinary exact answer.

The wall did not disappear, it moved to where it belongs: an axis like (1,2,0)
needs √5 to normalise, and √2, √3, √5 together generate a degree-8 field that
no biquadratic normal form names. That still refuses, by name, with its
radicands in ``measured``.

Violated invariant: every failure crosses the seam as a structured refusal
naming its stage (ADR-0019 / #114); a raw exception a caller cannot tell from
a bug is never acceptable. A wrong NUMBER is worse still — see
``tests/invariants/test_reported_volume_matches_the_shape.py``, which is what
caught the truncation this same promotion exposed.
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


def _rot(k, shape, deg, axis=(0, 0, 1)):
    return k.transform(shape, rotate_axis=axis, rotate_deg=deg)


def test_cut_across_two_radicals_now_computes():
    """The verbatim repro from the audit, which used to refuse."""
    k = RefKernel()
    a45 = _rot(k, k.box(10, 10, 10), 45)   # ℚ[√2]
    b30 = _rot(k, k.box(10, 10, 10), 30)   # ℚ[√3]

    out = k.boolean("cut", a45, b30)
    v = k.mass_props(out)["volume"]
    assert 0 < v < 1000                     # material removed, none invented
    assert v == pytest.approx(233.17, abs=1.0)   # Monte-Carlo oracle
    assert k.validate(out).ok


def test_the_answer_is_exact_where_a_closed_form_exists():
    """box@45 cut by a 2-wide slab@60 leaves 960 − 20√3 exactly: the removed
    wedge is a triangle of base 2 and height 2·tan75° = 2(2+√3), so the area is
    4 + 2√3 and the height is 10. The kernel reported the rational 960 for one
    commit — the radical was dropped in ``body._as_fraction``."""
    k = RefKernel()
    out = k.boolean("cut", _rot(k, k.box(10, 10, 10), 45),
                    _rot(k, k.box(2, 100, 100), 60))
    assert k.mass_props(out)["volume"] == pytest.approx(925.3589838486224,
                                                        abs=1e-9)


def test_a_degree_eight_tower_still_refuses_structurally():
    """√2 (45°), √3 (30°) and √5 (the (1,2,0) axis) together need degree 8.
    No coprime pair of generators names that field, so the refusal is real."""
    k = RefKernel()
    a45 = _rot(k, k.box(10, 10, 10), 45)
    b = _rot(k, k.box(2, 100, 100), 30, axis=(1, 2, 0))

    with pytest.raises(KernelError) as exc:
        k.boolean("cut", a45, b)

    err = exc.value
    assert err.predicate == "mixed_radicals"
    assert err.stage.startswith("K3")
    assert set(err.measured["radicals"]) & {2, 3, 5}
    assert err.remedy  # says what would make it work


def test_it_is_not_a_raw_exception():
    """The original defect: the failure must not arrive as a bare ValueError
    (or TypeError) from inside forge. KernelError is neither, so catching
    KernelError and re-checking the type is the whole assertion."""
    k = RefKernel()
    a45 = _rot(k, k.box(10, 10, 10), 45)
    b = _rot(k, k.box(2, 100, 100), 30, axis=(1, 2, 0))

    try:
        k.boolean("cut", a45, b)
    except KernelError:
        pass  # correct
    except (ValueError, TypeError) as raw:  # pragma: no cover - the regression
        pytest.fail(f"raw {type(raw).__name__} escaped the seam: {raw}")


def test_a_rotated_tool_never_crashes_the_seam():
    """The sweep that found the second defect: a ``Fraction`` coercion inside
    ``notch.py`` raised TypeError on a rotated body's ℚ(√p,√q) coordinates,
    from a straddled-bore fast path that was only probing whether the shape was
    its family. Refuse or answer — never crash."""
    k = RefKernel()
    box, slab = k.box(10, 10, 10), k.box(2, 100, 100)
    axes = [(0, 0, 1), (1, 0, 0), (1, 2, 0)]
    seen = 0
    for ax in axes:
        for d1 in (45, 90):
            for d2 in (30, 60):
                try:                      # some rotations are not built yet;
                    a = _rot(k, box, d1)  # that is a different, honest gap
                    t = _rot(k, slab, d2, axis=ax)
                except KernelError:
                    continue
                seen += 1
                try:
                    k.mass_props(k.boolean("cut", a, t))
                except KernelError:
                    pass
                except Exception as raw:  # pragma: no cover - the regression
                    pytest.fail(f"{type(raw).__name__} at axis {ax} "
                                f"{d1}/{d2}: {raw}")
    assert seen >= 8, f"corpus collapsed to {seen} pairs"


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
