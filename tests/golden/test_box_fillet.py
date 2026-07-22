"""GOLDEN: a curated, user-visible contract.

Small and hand-written (contrast the auto-generated regression tier). Verifies
the build → measure loop end to end on the null kernel, plus the same contract
on the real OCCT kernel when available.
"""

from __future__ import annotations

import math

import pytest

from gitcad.document import Document, Feature
from gitcad.kernel.null import NullKernel


def test_box_volume_null_kernel() -> None:
    d = Document()
    d.add(Feature(op="box", params={"dx": 10, "dy": 20, "dz": 5}))
    result = d.build(NullKernel())
    (shape,) = result.shapes.values()
    assert NullKernel().measure(shape)["volume"] == pytest.approx(1000.0)


def test_cylinder_volume_null_kernel() -> None:
    d = Document()
    d.add(Feature(op="cylinder", params={"radius": 2, "height": 10}))
    result = d.build(NullKernel())
    (shape,) = result.shapes.values()
    assert NullKernel().measure(shape)["volume"] == pytest.approx(math.pi * 4 * 10)


@pytest.mark.occt
def test_box_volume_occt() -> None:
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    shape = k.box(10, 20, 5)
    assert k.measure(shape)["volume"] == pytest.approx(1000.0, rel=1e-6)
    assert k.validate(shape).ok
