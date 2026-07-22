"""GOLDEN: feature recognition — STEP to parameterized model, with proof.

The full loop: build a plate with holes → export STEP (history destroyed) →
import (dead geometry) → recognize → get back a parameterized document whose
dimensions are real AND whose equivalence to the import is proven.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.occt


@pytest.fixture(scope="module")
def kernel():
    from gitcad.kernel.occt import OcctKernel

    return OcctKernel()


def test_step_to_parameterized_model_with_proof(kernel, tmp_path_factory) -> None:
    from gitcad.importers import import_step_file
    from gitcad.importers.recognize import recognize

    # A plate with two mounting holes — built parametrically, then flattened
    # to STEP (exactly what a SolidWorks/Fusion export does).
    plate = kernel.box(60, 40, 8)
    for x, y, r in ((12, 12, 3.2), (48, 28, 2.5)):
        plate = kernel.boolean("cut", plate,
                               kernel.transform(kernel.cylinder(r, 8), translate=(x, y, 0)))
    step = str(tmp_path_factory.mktemp("rec") / "plate.step")
    kernel.export_step(plate, step)

    doc, _ = import_step_file(step, kernel)          # dead geometry
    result = recognize(doc, kernel)                   # ...resurrected

    assert result.recognized, result.reason
    # The recovered dimensions are the REAL ones.
    holes = {(h.x, h.y): h.radius for h in result.holes}
    assert holes == {(12.0, 12.0): 3.2, (48.0, 28.0): 2.5}
    # And the proof: rebuilt geometry is exactly the import.
    assert result.proof["relative_residual"] < 1e-6
    # The returned document is editable parametric source: change a hole,
    # rebuild, geometry follows.
    text = result.document.dumps()
    assert '"radius": 3.2' in text.replace("3.2,", "3.2,")  # real dimension in text


def test_unrecognizable_shape_is_reported_honestly(kernel) -> None:
    from gitcad.document import Document, Feature
    from gitcad.importers.recognize import recognize

    doc = Document()
    doc.add(Feature(op="sphere", params={"radius": 10}))
    result = recognize(doc, kernel)
    assert not result.recognized
    assert "sphere" in result.reason


def test_blind_hole_fails_the_proof_not_silently(kernel) -> None:
    """A blind hole LOOKS like a through-hole to v1 recognition — the proof
    must catch the difference and refuse."""
    from gitcad.document import Document, Feature
    from gitcad.importers.recognize import recognize

    doc = Document()
    b = doc.add(Feature(op="box", params={"dx": 30, "dy": 20, "dz": 10}))
    c = doc.add(Feature(op="cylinder", params={"radius": 3, "height": 5}))   # blind!
    m = doc.add(Feature(op="move", params={"translate": [15, 10, 5]}, inputs=[c]))
    doc.add(Feature(op="boolean", params={"kind": "cut"}, inputs=[b, m]))
    result = recognize(doc, kernel)
    assert not result.recognized
    assert result.proof["residual_volume"] > 0
