"""A flat milled on a round bar answers at EVERY depth (ADR-0023), certified.

The measurement that motivated ADR-0023: on the exact path a flat on a radius-5
bar answered 3 of 33 rational depths, because the kept area carries an arc angle
that is a rational multiple of pi only at twelfths (Niven). A machinist does not
mill only at 30-degree chords, so a green CELL over a measure-zero family is a
demonstration, not a capability — which is exactly what `gitcad.bench.coverage`
was built to expose.

This is the permanent contract for that row: the answer exists at every depth,
it is honestly LABELLED (exact where an exact field holds it, certified where
only a bracket does), and the certified answer is complete — a real centre of
mass, not a volume with a NaN centroid. It is an invariant because it is a
statement about the ANSWER, not about an implementation: whatever builds the
flat, a depth off the twelfth grid must still come back with a proven-enclosing
volume and a centroid, or the capability has regressed.
"""

from fractions import Fraction as F

import pytest

from gitcad.kernel import get_kernel

R, H = F(5), F(12)
_BIG = F(400)


def _flat(k, h):
    """A half-space cutting a radius-5, height-12 bar, keeping x <= h."""
    bar = k.cylinder(R, H)
    t = [-_BIG / 2, -_BIG / 2, -_BIG / 2]
    t[0] = h                                       # wall at x = h, removes x > h
    tool = k.transform(k.box(_BIG, _BIG, _BIG), translate=tuple(t))
    return k.boolean("cut", bar, tool)


# every quarter-unit depth across the bar — the numbers a person types, and
# almost none of them twelfths
_DEPTHS = [F(n, 4) for n in range(-16, 17)]


@pytest.mark.parametrize("h", _DEPTHS)
def test_a_flat_answers_at_every_rational_depth(h):
    """3/33 before ADR-0023, 33/33 after. The refusal was never about the
    geometry — the body is exact at any depth — only about the measure."""
    k = get_kernel()
    mp = k.mass_props(_flat(k, h))
    v = float(mp["volume"])
    assert v > 0, (h, v)
    # provenance is honest: exact only at the twelfths (h/r in {0, +-1/2, ...})
    assert mp["provenance"] in ("exact", "certified")
    if mp["provenance"] == "certified":
        assert mp["volume_halfwidth"] >= 0


def test_the_twelfth_depths_stay_exact():
    """ADR-0019's rule, which is ADR-0023's acceptance criterion: a model that
    COULD be exact must not fall back to an interval. cos of a twelfth is in
    {0, +-1/2, +-sqrt3/2, +-1}, so h in {0, +-5/2} on r=5 must stay exact."""
    k = get_kernel()
    for h in (F(0), R / 2, -R / 2):
        assert k.mass_props(_flat(k, h))["provenance"] == "exact", h


def test_the_certified_answer_is_complete_not_volume_only():
    """A certified volume with a NaN centroid is half an answer. The off-grid
    centroid (Monte-Carlo verified in forge) makes it whole: a real centre of
    mass, on the bar's symmetry axes."""
    k = get_kernel()
    mp = k.mass_props(_flat(k, F(1)))              # h=1 is not a twelfth
    assert mp["provenance"] == "certified"
    assert mp["cx"] == mp["cx"], "centroid x is NaN — the answer is incomplete"
    assert mp["cx"] < 0                            # material kept on the low-x side
    assert abs(mp["cy"]) < 1e-9                    # symmetric in y
    assert abs(mp["cz"] - float(H) / 2) < 1e-9     # symmetric in z


def test_the_volume_bracket_actually_encloses_the_truth():
    """The certified label is only worth something if the bracket is real.

    The closed form r^2(pi - t + sin t cos t) * H, t = arccos(h/r), is the
    oracle. It must land inside [mid - halfwidth, mid + halfwidth].
    """
    import math

    k = get_kernel()
    for h in (F(1), F(7, 3), F(-3, 2)):
        mp = k.mass_props(_flat(k, h))
        mid, hw = float(mp["volume"]), mp["volume_halfwidth"]
        t = math.acos(float(h) / float(R))
        truth = float(R) ** 2 * (math.pi - t + math.sin(t) * math.cos(t)) * float(H)
        assert mid - hw - 1e-6 <= truth <= mid + hw + 1e-6, (h, mid, hw, truth)
