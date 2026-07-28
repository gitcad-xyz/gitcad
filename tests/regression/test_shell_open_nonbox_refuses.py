"""Dogfood #20: open shell of a non-box solid silently cut a bbox void.

``RefKernel.shell`` with ``remove_faces`` reached the "K4: OPEN shell on a
box" branch for ANY planar ``Solid`` — the void it cuts is the inward-inset
bounding box, which is only the right void when the base IS its bounding
box. On a lofted frustum (40x40 base, 20x20 top, h=20) the box void
swallowed every sloped wall above z=4: the "shell" measured 1480 mm^3,
reported with ``geometry_verified: true``, where a true 2 mm open shell is
~5514 mm^3 (56000/3 - 18144 + 2232*sqrt5, derived from the perpendicular
face offsets and Monte-Carlo-verified; the ~3900 first reported in #20 was
itself a wrong number). Silent wrong geometry, found designing a mouse top shell on the
0.9.9 wheels.

Violated invariant: a refusal with a remedy is the product working; a wrong
number presented as verified is the one outcome the verification loop
exists to prevent (ADR-0019 honesty, capability-matrix WRONG class).

The fix keeps K4 refusal-honest: the open-shell branch now proves the base
is exactly its bounding box (every logical face axis-aligned AND lying on
the bbox) before cutting the box void, and otherwise refuses with the same
K4.2 signature the closed-shell paths already use. Boxes keep working.
"""

from __future__ import annotations

import pytest

pytest.importorskip("forgekernel")

from gitcad.errors import KernelError
from gitcad.kernel.ref import RefKernel


def _kernel() -> RefKernel:
    return RefKernel()


def _frustum(kernel):
    """Ruled loft: 40x40 square at z=0 to 20x20 square at z=20."""
    def sq(half):
        return {"start": [-half, -half],
                "segments": [{"kind": "line", "to": [half, -half]},
                             {"kind": "line", "to": [half, half]},
                             {"kind": "line", "to": [-half, half]},
                             {"kind": "line", "to": [-half, -half]}]}
    return kernel.loft([(sq(20.0), 0.0), (sq(10.0), 20.0)], ruled=True)


def _bottom_face_index(kernel, shape) -> int:
    faces = kernel.entities(shape, "face")
    return next(i for i, f in enumerate(faces)
                if f["surface"] == "plane"
                and f["centroid"][2] == pytest.approx(0.0))


def test_open_shell_of_loft_refuses_instead_of_box_void() -> None:
    kernel = _kernel()
    frustum = _frustum(kernel)
    assert kernel.measure(frustum)["volume"] == pytest.approx(56000 / 3, rel=1e-9)
    bottom = _bottom_face_index(kernel, frustum)
    with pytest.raises(KernelError, match="non-box"):
        kernel.shell(frustum, [bottom], 2.0)


def test_open_shell_of_stepped_solid_refuses() -> None:
    # axis-aligned faces are not enough: an L-shaped solid has a face
    # INSIDE its bbox, and the box void would carve through the step.
    kernel = _kernel()
    base = kernel.box(20, 20, 10)
    tower = kernel.transform(kernel.box(10, 20, 10), translate=(0, 0, 10))
    lshape = kernel.boolean("union", base, tower)
    faces = kernel.entities(lshape, "face")
    bottom = next(i for i, f in enumerate(faces)
                  if f["surface"] == "plane"
                  and f["centroid"][2] == pytest.approx(0.0))
    with pytest.raises(KernelError, match="non-box"):
        kernel.shell(lshape, [bottom], 2.0)


def test_open_shell_of_box_still_works() -> None:
    kernel = _kernel()
    box = kernel.box(10, 10, 10)
    faces = kernel.entities(box, "face")
    top = next(i for i, f in enumerate(faces)
               if f["surface"] == "plane"
               and f["centroid"][2] == pytest.approx(10.0))
    out = kernel.shell(box, [top], 1.0)
    assert kernel.measure(out)["volume"] == pytest.approx(1000 - 8 * 8 * 9, rel=1e-6)
