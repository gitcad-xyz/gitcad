"""Making a part bigger does not make the kernel worse at it.

The third of the transform invariants, after mirror and rotation, and the one
with the cheapest oracle there is: a similarity of ratio f multiplies volume by
f³ exactly, for every shape that exists.

The capability claim is the one that matters, though. A UNIFORM scale is a
similarity and every representation here is closed under one — a scaled
cylinder is a cylinder, radius and all — so nothing the kernel could do with a
shape may be lost by scaling it. It was: ``k.scale`` sent every non-``Solid``
through the canonical ``Body``, and because the feature and boolean paths
dispatch on representation, ``scale then cut`` was 8 of the composed grid's 34
"a transformed solid landed in the canonical B-rep" cells.

ANISOTROPIC scale is genuinely different — squash a cylinder in x and it is an
elliptic cylinder, which no representation here holds — so that case still
goes through the canonical form. Losing capability there is honest; losing it
to a uniform scale was not.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

# The base suite runs with NO KERNEL INSTALLED (CLAUDE.md).
pytest.importorskip("forgekernel")

from gitcad.bench.capability import representations
from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


@pytest.fixture(scope="module")
def k():
    return RefKernel()


@pytest.fixture(scope="module")
def shapes(k):
    return {n: s for n, s in representations(k).items()
            if not isinstance(s, tuple)}


def _mid(k, s):
    lo, hi = k.bbox(s)
    return [(float(lo[i]) + float(hi[i])) / 2 for i in range(3)]


def _ops(k):
    return {
        "mass_props": lambda s: k.mass_props(s),
        "tessellate": lambda s: k.tessellate(s),
        "validate": lambda s: k.validate(s),
        "cut": lambda s: k.boolean("cut", s, k.transform(
            k.box(2, 2, 500), translate=(_mid(k, s)[0], _mid(k, s)[1], -250))),
        "chamfer": lambda s: k.chamfer(s, None, 1),
        "shell": lambda s: k.shell(s, [], 1),
    }


FACTORS = (2, 3, Fraction(1, 2))


@pytest.mark.parametrize("f", FACTORS)
def test_a_uniform_scale_keeps_the_representation(k, shapes, f):
    for name, s in shapes.items():
        out = k.scale(s, f)
        assert type(out) is type(s), (
            f"{name}: scaling by {f} turned a {type(s).__name__} into a "
            f"{type(out).__name__}")


@pytest.mark.parametrize("f", FACTORS)
def test_volume_scales_by_the_cube(k, shapes, f):
    """A similarity of ratio f multiplies volume by f³. No oracle needed —
    this is arithmetic, and it is exact."""
    for name, s in shapes.items():
        v0 = k.mass_props(s)["volume"]
        v1 = k.mass_props(k.scale(s, f))["volume"]
        assert float(v1) == pytest.approx(float(v0) * float(f) ** 3,
                                          rel=1e-12), name


def test_scaling_loses_no_capability(k, shapes):
    """The headline. Anything the kernel could do with a shape, it can still
    do with the same shape twice the size."""
    lost = []
    for name, s in shapes.items():
        big = k.scale(s, 2)
        for op, fn in _ops(k).items():
            try:
                fn(s)
            except KernelError:
                continue                     # it could not do it upright
            try:
                fn(big)
            except KernelError as e:
                lost.append(f"{name}/{op}: {str(e)[:80]}")
            except Exception as raw:         # pragma: no cover - regression
                lost.append(f"{name}/{op}: raw {type(raw).__name__}: {raw}")
    assert not lost, (
        f"{len(lost)} (shape, op) pairs work at size 1 and not at size 2:\n  "
        + "\n  ".join(lost))


def test_a_scale_never_crashes_the_seam(k, shapes):
    """A scaled solid may be REFUSED by any op — that is a roadmap entry — but
    a raw exception through the seam is always a defect."""
    for name, s in shapes.items():
        for f in (2, Fraction(1, 3)):
            try:
                big = k.scale(s, f)
            except KernelError:
                continue
            for op, fn in _ops(k).items():
                try:
                    fn(big)
                except KernelError:
                    pass
                except Exception as raw:     # pragma: no cover - regression
                    pytest.fail(f"{name}/{op} at ×{f}: raw "
                                f"{type(raw).__name__}: {raw}")


def test_an_anisotropic_scale_is_still_honest(k, shapes):
    """Squashing a cylinder in x makes an ELLIPTIC cylinder, which no
    representation here holds and the canonical B-rep cannot build from a
    quadric either. So it refuses — by name, with a stage — and that is the
    correct answer, unchanged by this work. A planar Solid has no such
    problem and must keep scaling anisotropically."""
    with pytest.raises(KernelError) as exc:
        k.scale(shapes["cylinder"], 2, 1, 1)
    assert exc.value.stage, "a refusal must name the stage that delivers it"

    flat = k.scale(shapes["planar box"], 2, 1, 1)
    v0 = k.mass_props(shapes["planar box"])["volume"]
    assert k.mass_props(flat)["volume"] == v0 * 2
