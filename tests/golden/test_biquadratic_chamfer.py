"""Chamfer across two quadratic fields (#127, the multi-radical tower).

``SurdVal`` held ℚ[√d] and refused the moment two radicands met; ``BiSurd``
held ℚ(√p,√q), was already general in (p,q) and complete — arithmetic,
comparison, sign, inverse — and the two were never connected. So a chamfer
whose exact home already existed in the kernel refused anyway.

Two cases needed it, and both now compute:

* a TAPERED solid — the face normal is in ℚ[√37], the slanted EDGE direction
  in ℚ[√38], so the wedge needs ℚ(√37,√38);
* a CHAMFERED BOX chamfered again — which the capability bench had recorded as
  a PERMANENT exact-field wall. That was wrong: its stated reason ("normals of
  length √2, so the offset is irrational") is a field limitation, not an
  impossibility, unlike the four real walls that cite arcsin, arctan and
  Baker. The label hid a closable gap.

Every expected value is checked against an INDEPENDENT Monte-Carlo oracle that
first reproduces a case with a closed form — chamfer(box a×b×c, d) =
abc − 2(a+b+c)d² + 6d³ — so the oracle is trusted only after it has been shown
to be right about something known.
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture()
def k():
    return RefKernel()


def _frustum(k):
    return k.loft([
        ({"start": [0, 0], "segments": [{"kind": "line", "to": [10, 0]},
                                        {"kind": "line", "to": [10, 10]},
                                        {"kind": "line", "to": [0, 10]},
                                        {"kind": "line", "to": [0, 0]}]}, 0.0),
        ({"start": [2, 2], "segments": [{"kind": "line", "to": [8, 2]},
                                        {"kind": "line", "to": [8, 8]},
                                        {"kind": "line", "to": [2, 8]},
                                        {"kind": "line", "to": [2, 2]}]}, 12.0)],
        ruled=True)


def test_the_box_closed_form_is_untouched(k):
    """The control the oracle itself was validated against; if this moves,
    nothing below means anything. 10·10·12 − 2·32·1 + 6 = 1142."""
    assert k.mass_props(k.chamfer(k.box(10, 10, 12), None, 1))["volume"] == 1142
    assert k.mass_props(k.chamfer(k.box(20, 20, 20), None, 1))["volume"] == 7886


@pytest.mark.parametrize("d,truth", [(1, 733.68), (2, 607.09)])
def test_a_tapered_solid_chamfers_in_the_biquadratic_field(k, d, truth):
    """ℚ[√37] normal × ℚ[√38] edge direction. Was 100.55 (87% of the solid
    removed) while a non-unit vector scaled every wedge; then an honest
    refusal; now correct."""
    out = k.chamfer(_frustum(k), None, d)
    v = k.mass_props(out)["volume"]
    assert v == pytest.approx(truth, abs=0.5), f"MC truth {truth}, got {v}"
    assert k.validate(out).ok
    assert v != pytest.approx(100.548, abs=1e-2), "the old wrong number"


def test_a_chamfered_box_chamfers_again(k):
    """The wall that was not a wall. MC oracle 7424.256; the oracle's own
    error on a closed-form case was 0.189."""
    cb = k.chamfer(k.box(20, 20, 20), None, 2)
    assert k.mass_props(cb)["volume"] == 7568        # the corrected chamfer
    out = k.chamfer(cb, None, 1)
    assert k.mass_props(out)["volume"] == pytest.approx(7424.256, abs=0.5)
    assert k.validate(out).ok


def test_chamfer_still_commutes_with_reflection(k):
    """The invariant that started this whole thread."""
    f = _frustum(k)

    def out(s):
        try:
            return k.mass_props(k.chamfer(s, None, 1))["volume"]
        except KernelError:
            return "refused"

    assert out(f) == out(k.mirror(f, "xy"))


def test_a_pair_the_normal_form_cannot_name_still_refuses(k):
    """ℚ(√6,√10) is degree 4 — an ordinary biquadratic field — but its
    radicals are 6 = 2·3, 10 = 2·5 and 15 = 3·5, which pairwise share a prime,
    so no coprime pair of generators names it and ``BiSurd``'s tag-matching
    coercion has nowhere to put the value. A shared factor alone is NOT the
    boundary: √2 with √6 promotes, by changing generators to (2,3).
    Promotion must close what it can and refuse the rest by name."""
    from forgekernel.surd import MixedRadicals, SurdVal, sqrt_rational

    with pytest.raises(MixedRadicals):
        SurdVal(0, 1, 6) + SurdVal(0, 1, 10)
    assert float(sqrt_rational(2) + sqrt_rational(6)) == pytest.approx(
        1.4142135623730951 + 2.449489742783178, abs=1e-12)
