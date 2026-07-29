"""Two solids that do not touch have a union, whatever they are made of.

This is the weakest possible boolean: the operands share no volume, so there
is no surface intersection to compute and nothing about the curved geometry
matters. The union's volume is the sum of the parts and its bounding box is
the box of theirs, by measure additivity alone — no quadric algebra, no SSI.

So a kernel that refuses it is not reporting a mathematical limit. It is
reporting that it stopped asking whether the operands overlap before it got to
the answer, which is the same defect class as the sphere cap's axis guard: a
construction that was already correct, switched off by a test that ran too
early. The refusal even says so out loud — "their intersection with the tool
is not built yet" — of two solids with no intersection.

WHY THIS IS AN INVARIANT AND NOT A REGRESSION TEST. It is stated entirely in
terms the seam already guarantees (volume is additive over disjoint sets) and
mentions no representation. Whatever replaces `DisjointUnion`, `Body`, or the
boolean dispatch, a disjoint union still has to come out to the sum, so this
survives the architecture that happens to satisfy it today.
"""

from fractions import Fraction as F

import pytest

from gitcad.kernel import get_kernel


def _far_box(k, s, size=2):
    """A small box placed clear of `s` in +x, by a whole diameter's margin."""
    lo, hi = k.bbox(s)
    return k.transform(k.box(size, size, size),
                       translate=(float(hi[0]) + 10, float(lo[1]), float(lo[2])))


def _cut_cylinder(k):
    """A bar with a slot milled through it — lands in the canonical Body, and
    carries a Cylinder face, which is what the union used to refuse over."""
    bar = k.cylinder(5, 12)
    slot = k.transform(k.box(2, 2, 100), translate=(0, 0, 6))
    return k.boolean("cut", bar, slot)


def test_the_volume_is_the_sum_of_the_parts():
    k = get_kernel()
    a = _cut_cylinder(k)
    b = _far_box(k, a)
    va = k.mass_props(a)["volume"]
    vb = k.mass_props(b)["volume"]
    u = k.boolean("union", a, b)
    vu = k.mass_props(u)["volume"]
    # EXACT. Both parts are already exact and the sets are disjoint, so the sum
    # is too — a tolerance here would be hiding an approximation that has no
    # reason to exist.
    assert vu == va + vb, (vu, va, vb, vu - va - vb)


def test_the_union_is_measurable_and_bounded():
    """Closing the boolean is worth nothing if its answer is a dead end.

    The composed grid exists because `rotate 90` once scored green while the
    rotated solid could not be a boolean operand — an operation that returns
    an unusable object has not really landed. So the union's result is asked
    the same questions any solid gets.
    """
    k = get_kernel()
    a = _cut_cylinder(k)
    b = _far_box(k, a)
    u = k.boolean("union", a, b)

    lo_a, hi_a = k.bbox(a)
    lo_b, hi_b = k.bbox(b)
    lo_u, hi_u = k.bbox(u)
    for i in range(3):
        assert float(lo_u[i]) == pytest.approx(min(float(lo_a[i]),
                                                   float(lo_b[i])))
        assert float(hi_u[i]) == pytest.approx(max(float(hi_a[i]),
                                                   float(hi_b[i])))

    # the centroid must land between the parts, on the axis the parts are
    # separated along — a union that quietly dropped a member would still
    # measure, and would still be wrong here
    c = k.mass_props(u)["centroid"]
    ca = k.mass_props(a)["centroid"]
    cb = k.mass_props(b)["centroid"]
    assert min(ca[0], cb[0]) < c[0] < max(ca[0], cb[0]), (c, ca, cb)


@pytest.mark.parametrize("name", ["translate", "mirror", "scale"])
def test_the_union_survives_being_moved(name):
    """A rigid motion or a similarity must not cost the union its usability.

    This is the composed grid's rule applied to the union's own answer: the
    grid exists because `rotate 90` once scored green while the rotated solid
    could no longer be an operand. When this union first landed, all three of
    these refused — the members dispatch on representation and a member that
    is a canonical `Body` has `transformed(Affine)` and none of the feature
    families' `mirrored`/`scaled`/`translated`. It surfaced as "mirror on
    Body, DisjointUnion yet", which reads as an unbuilt capability and was a
    missing branch.

    Volume is checked as well as survival, because a union that quietly
    dropped a member would still return a solid.
    """
    k = get_kernel()
    a = _cut_cylinder(k)
    u = k.boolean("union", a, _far_box(k, a))
    v0 = k.mass_props(u)["volume"]

    moved = {"translate": lambda s: k.transform(s, translate=(1, 2, 3)),
             "mirror": lambda s: k.mirror(s, "xy"),
             "scale": lambda s: k.scale(s, 2)}[name](u)
    # a similarity of ratio 2 multiplies volume by 8; an isometry by 1 —
    # EXACTLY, since both operands were exact and both maps are exact
    expected = v0 * 8 if name == "scale" else v0
    assert k.mass_props(moved)["volume"] == expected


def test_a_genuine_overlap_still_refuses():
    """The point is disjointness, not "unions are easy now".

    If proving separation is what unlocks this, then failing to prove it must
    still refuse. Otherwise the fix is not a proof, it is a shortcut that
    happens to be right about the cases someone tried.
    """
    from gitcad.errors import KernelError

    k = get_kernel()
    a = _cut_cylinder(k)
    lo, hi = k.bbox(a)
    # straddling the bar's wall — a real overlap with positive measure
    overlapping = k.transform(k.box(6, 6, 6),
                              translate=(float(hi[0]) - 3, -3, 0))
    with pytest.raises(KernelError):
        k.boolean("union", a, overlapping)


def test_separation_is_decided_exactly_not_by_a_float_bound():
    """A box placed to touch EXACTLY, at a coordinate no float holds.

    Tangent contact is measure zero, so the union is still the sum. The gap is
    1/3 of a unit off the bar's wall, which is not a binary fraction: a
    separation test that went through floats would be deciding this on a
    rounded value. That is the specific thing ADR-0019 forbids for a
    topological decision.
    """
    k = get_kernel()
    a = _cut_cylinder(k)
    # the bar's wall is at x = 5 exactly; put the near face at 5 + 1/3
    b = k.transform(k.box(F(2), F(2), F(2)),
                    translate=(F(16, 3), F(-1), F(0)))
    u = k.boolean("union", a, b)
    assert (k.mass_props(u)["volume"]
            == k.mass_props(a)["volume"] + k.mass_props(b)["volume"])
