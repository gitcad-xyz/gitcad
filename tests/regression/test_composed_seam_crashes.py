"""#10's composed-tier census surfaced two crash families — pinned here.

Hand-written regressions (second-class per ADR-0005; the durable guard is
the composed-seam invariant in tests/invariants/test_seam_enforcement.py).

Family 1: a 45°-rotated solid with a cylindrical wall reaches the notch
path with SurdVal center coordinates, and ``notch.py`` computed ``x ** 2``
— SurdVal implements multiplication, not ``__pow__`` (the file's own
comment at the crossing sort names this exact defect class: "x*x, never
x**2"). Raw ``TypeError`` through the seam.

Family 2: shelling a boolean result that lands in ``DisjointUnion`` with a
member whose ``_exact_bbox`` witness is None crashed unpacking it — the
None is a documented, legitimate return ("cannot give bounds without
leaving ℚ") that the separation check never handled.

Either a result or an honest KernelError refusal is a finished answer; a
raw TypeError never is.
"""

from __future__ import annotations

import pytest

from gitcad.errors import KernelError

occt = pytest.importorskip  # noqa: F401 - kernel-marked below

pytestmark = pytest.mark.kernel


def _mid(k, s):
    lo, hi = k.bbox(s)
    return tuple((float(lo[i]) + float(hi[i])) / 2 for i in range(3))


def _kernel():
    from gitcad.kernel import get_kernel

    return get_kernel()


def test_rot45_drilled_solid_cut_by_box_does_not_raise_typeerror() -> None:
    k = _kernel()
    drilled = k.boolean("cut", k.box(40, 20, 5),
                        k.transform(k.cylinder(4, 5), translate=(20, 10, 0)))
    rot = k.transform(drilled, rotate_axis=(0, 0, 1), rotate_deg=45)
    try:
        out = k.boolean("cut", rot,
                        k.transform(k.box(2, 2, 100), translate=_mid(k, rot)))
    except KernelError:
        return                       # an honest, structured refusal is fine
    assert out is not None           # so is a result — anything but a crash


def test_shell_of_a_cut_disjoint_union_does_not_raise_typeerror() -> None:
    k = _kernel()
    boss = k.boolean("union", k.box(30, 30, 3),
                     k.transform(k.cylinder(4, 6), translate=(15, 15, 3)))
    cut = k.boolean("cut", boss,
                    k.transform(k.box(2, 2, 100), translate=_mid(k, boss)))
    try:
        out = k.shell(cut, [], 1)
    except KernelError:
        return                       # honest refusal is a finished answer
    assert out is not None
