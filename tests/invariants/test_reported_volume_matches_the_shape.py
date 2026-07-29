"""The volume the seam REPORTS is the volume of the shape it RETURNS.

An invariant, not a table of expected numbers: it needs nobody to guess which
configuration breaks. For any solid the kernel hands back as a polygon soup,
integrate that soup in ordinary floats and compare against the exact volume
reported through ``mass_props``. The two are computed by completely different
machinery — one exact over a number field, one a float divergence sum over the
returned vertices — so they can only agree by being right.

This is the check that found the ``_as_fraction`` truncation: ``cut(box@45°,
slab@60°)`` returned polygons worth 925.359 and reported 960.000, because
``960 − 20√3`` is stored in ``BiSurd`` with a zero √2 coefficient and a helper
that duck-typed on ``.b`` read it as the rational 960. The geometry had been
right the whole time; only the number was wrong, which is the worst way for a
CAD kernel to fail — a wrong answer is invisible, a refusal is not.

Floats are legal here (ADR-0019): nothing about the model is DECIDED from this
number. It is a cross-check on a value the kernel already computed exactly, and
it only ever causes a test to fail.
"""

from __future__ import annotations

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


def _soup_volume(solid) -> float | None:
    """Float divergence-theorem volume over a polygon soup, or None if the
    shape is not one (a Cyl, a Body, a TubeSolid — those have no soup to
    disagree with and are covered by their own goldens).

    ADR-0022: the seam returns a canonical Body, so the soup is reached through
    `source_form`. Without that every case returned None, the `checked > 60`
    guard below fired, and this invariant reported a collapsed corpus — which is
    exactly what that guard is for. The PROPERTY here is unchanged; only the
    route to the polygons is.
    """
    from gitcad.kernel import source_form

    polys = getattr(source_form(solid), "polys", None)
    if not polys:
        return None
    tot = 0.0
    for p in polys:
        v = [tuple(float(x) for x in pt) for pt in p.verts]
        for i in range(1, len(v) - 1):
            a, b, c = v[0], v[i], v[i + 1]
            tot += (a[0] * (b[1] * c[2] - b[2] * c[1])
                    - a[1] * (b[0] * c[2] - b[2] * c[0])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return abs(tot)


def _rot(k, s, deg, axis=(0, 0, 1)):
    return k.transform(s, rotate_axis=axis, rotate_deg=deg)


# Every rotation the kernel admits, paired every way round. 45° lands in ℚ[√2]
# and 30/60/120/150° in ℚ[√3], so most of these pairs are exactly the
# two-fields case; 0/90/180 are rational and must keep working untouched.
ANGLES = (0, 30, 45, 60, 90, 120, 135, 150, 180)


def _cases(k):
    box, slab, bar = k.box(10, 10, 10), k.box(2, 100, 100), k.box(3, 3, 40)
    for ad in ANGLES:
        for bd in ANGLES:
            yield f"cut box@{ad} by slab@{bd}", _rot(k, box, ad), _rot(k, slab, bd)
    for ad in (0, 30, 45, 60, 135):
        for bd in (0, 30, 45, 90, 150):
            yield f"cut box@{ad} by box@{bd}", _rot(k, box, ad), _rot(k, box, bd)
            yield f"cut box@{ad} by bar@{bd}", _rot(k, box, ad), _rot(k, bar, bd)
    # a rotation about a different axis puts the radical in a different place
    for ad in (30, 45, 90):
        yield (f"cut box@x{ad} by slab@45", _rot(k, box, ad, (1, 0, 0)),
               _rot(k, slab, 45))


def test_every_reachable_cut_reports_the_volume_it_returns(k):
    checked = refused = 0
    wrong: list[str] = []
    for name, a, b in _cases(k):
        try:
            out = k.boolean("cut", a, b)
            reported = float(k.mass_props(out)["volume"])
        except KernelError:
            refused += 1          # a refusal is honest; a wrong number is not
            continue
        soup = _soup_volume(out)
        if soup is None:
            continue
        checked += 1
        # tolerance scales with the magnitude: these are ~10^3 with float
        # coordinates through a rotation, so ~1e-9 relative is generous-tight
        if abs(reported - soup) > 1e-6 * max(1.0, soup):
            wrong.append(f"{name}: reported {reported!r} vs soup {soup!r}")
    assert checked > 60, f"corpus collapsed to {checked} live cases"
    assert not wrong, (
        f"{len(wrong)} of {checked} cuts reported a volume that is not the "
        f"volume of the returned shape ({refused} refused honestly):\n  "
        + "\n  ".join(wrong[:12]))


def test_a_cut_depends_only_on_the_RELATIVE_rotation(k):
    """Rotating BOTH bodies is a rigid motion of the whole configuration, so
    the answer cannot move — the same isometry argument as the mirror
    invariant, and it holds across the field boundary or the field handling is
    wrong. box@45/slab@60 and box@30/slab@45 are both 15° apart."""
    box, slab = k.box(10, 10, 10), k.box(2, 100, 100)

    def vol(ad, bd):
        out = k.boolean("cut", _rot(k, box, ad), _rot(k, slab, bd))
        return k.mass_props(out)["volume"]

    for a0, b0, a1, b1 in ((45, 60, 30, 45), (0, 45, 45, 90), (30, 60, 60, 90),
                           (0, 30, 90, 120), (45, 135, 0, 90)):
        assert vol(a0, b0) == pytest.approx(vol(a1, b1), abs=1e-9), (
            f"({a0},{b0}) and ({a1},{b1}) are the same configuration rotated")


def test_the_case_that_found_it(k):
    """Verbatim, with the value an independent Monte-Carlo oracle confirmed.
    960 − 20√3: the kernel used to report exactly the 960."""
    out = k.boolean("cut", _rot(k, k.box(10, 10, 10), 45),
                    _rot(k, k.box(2, 100, 100), 60))
    v = k.mass_props(out)["volume"]
    assert v == pytest.approx(925.3589838486224, abs=1e-9)
    assert v != pytest.approx(960.0, abs=1e-6), "the rational part alone"
    assert k.validate(out).ok
