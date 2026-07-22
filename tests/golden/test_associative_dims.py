"""GOLDEN: associative dimensions — drawing dims derived from geometry.

The property that matters: move a hole in the MODEL, regenerate the drawing,
and the dimension values follow. No hand-maintained annotation in between.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.occt


@pytest.fixture(scope="module")
def kernel():
    from gitcad.kernel.occt import OcctKernel

    return OcctKernel()


def _plate(kernel, hole_at=(15.0, 20.0), r=3.2):
    plate = kernel.box(60, 40, 8)
    return kernel.boolean("cut", plate,
                          kernel.transform(kernel.cylinder(r, 8),
                                           translate=(hole_at[0], hole_at[1], 0.0)))


def test_hole_dimensions_appear_on_the_drawing(kernel) -> None:
    from gitcad.drawing import make_drawing

    d = make_drawing(_plate(kernel), kernel, title="plate")
    svg = d.to_svg()
    assert "Ø6.4" in svg                       # diameter callout
    assert len(d.callouts) == 1
    # Position dims from the datum: x=15, y=20.
    dim_texts = {dim.text for dim in d.dims}
    assert {"15", "20"} <= dim_texts
    # PDF renders the same callout (Ø is latin-1, survives the writer).
    assert b"\xd86.4" in d.to_pdf() or "Ø6.4".encode("latin-1") in d.to_pdf()


def test_dimensions_follow_the_model(kernel) -> None:
    """THE associative property: edit the geometry, dims update."""
    from gitcad.drawing import make_drawing

    before = make_drawing(_plate(kernel, hole_at=(15.0, 20.0)), kernel)
    after = make_drawing(_plate(kernel, hole_at=(22.0, 11.0), r=2.5), kernel)

    before_texts = {dim.text for dim in before.dims}
    after_texts = {dim.text for dim in after.dims}
    assert {"15", "20"} <= before_texts
    assert {"22", "11"} <= after_texts
    assert not {"15", "20"} <= after_texts
    assert before.callouts[0].text == "Ø6.4"
    assert after.callouts[0].text == "Ø5"


def test_multiple_holes_stack_without_collision(kernel) -> None:
    from gitcad.drawing import make_drawing

    plate = kernel.box(60, 40, 8)
    for x, y, r in ((12, 12, 3.2), (48, 28, 2.5)):
        plate = kernel.boolean("cut", plate,
                               kernel.transform(kernel.cylinder(r, 8), translate=(x, y, 0)))
    d = make_drawing(plate, kernel)
    assert len(d.callouts) == 2
    # 3 overall dims + 2 position dims per hole.
    assert len(d.dims) == 3 + 4
    # Stacked dim lines must not share a y (x-dims) or x (y-dims) lane.
    x_dims = [dim for dim in d.dims if not dim.vertical and dim.text in ("12", "48")]
    assert len({dim.p1[1] for dim in x_dims}) == len(x_dims)


def test_hole_free_part_has_no_callouts(kernel) -> None:
    from gitcad.drawing import make_drawing

    d = make_drawing(kernel.box(30, 20, 5), kernel)
    assert d.callouts == [] and len(d.dims) == 3
