"""GOLDEN: entity references survive upstream edits (ADR-0003, wired end-to-end).

The flagship topological-naming scenario: a fillet references a specific edge
by stable id; an unrelated feature is inserted upstream; the reference still
resolves to the same physical edge and produces identical geometry.
"""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.errors import IdentityError

pytestmark = pytest.mark.occt


@pytest.fixture(scope="module")
def kernel():
    from gitcad.kernel.occt import OcctKernel

    return OcctKernel()


def _plate_doc(*, with_unrelated_insert: bool = False) -> tuple[Document, str]:
    d = Document()
    if with_unrelated_insert:
        d.add(Feature(op="sphere", params={"radius": 2}))  # unrelated upstream noise
    box = d.add(Feature(op="box", params={"dx": 60, "dy": 40, "dz": 8}))
    return d, box


def test_fillet_by_entity_id_survives_upstream_insertion(kernel) -> None:
    # Build the original, pick one specific edge of the box by stable id.
    doc, box = _plate_doc()
    result = doc.build(kernel)
    edges = result.entities[box]["edge"]
    eid, desc = edges[0]

    # Fillet that edge by id.
    doc.add(Feature(op="fillet", params={"edges": [eid], "radius": 2.0}, inputs=[box]))
    v_original = kernel.measure(doc.build(kernel).final(doc))["volume"]

    # Same construction, but an unrelated feature inserted upstream. Because
    # feature ids are value-based (not ordinal) and entity ids derive from
    # (feature lineage + geometric fingerprint), the SAME edge id still exists
    # and resolves — the reference survives the edit.
    doc2, box2 = _plate_doc(with_unrelated_insert=True)
    assert box2 == box  # value-based feature identity
    doc2.add(Feature(op="fillet", params={"edges": [eid], "radius": 2.0}, inputs=[box2]))
    v_after_insert = kernel.measure(doc2.build(kernel).final(doc2))["volume"]

    assert v_after_insert == pytest.approx(v_original, rel=1e-9)
    # And it genuinely filleted one edge, not all twelve.
    v_unfilleted = 60 * 40 * 8
    assert v_original < v_unfilleted
    v_all = kernel.measure(kernel.fillet(kernel.box(60, 40, 8), None, 2.0))["volume"]
    assert v_original > v_all  # one-edge fillet removes less than all-edge


def test_dangling_entity_reference_fails_loudly(kernel) -> None:
    doc, box = _plate_doc()
    doc.add(Feature(op="fillet", params={"edges": ["e_deadbeefdeadbeefdeadbeefdeadbeef"],
                                         "radius": 1.0}, inputs=[box]))
    with pytest.raises(IdentityError):
        doc.build(kernel)


def test_entity_ids_are_stable_across_builds(kernel) -> None:
    doc, box = _plate_doc()
    ids_a = [eid for eid, _ in doc.build(kernel).entities[box]["edge"]]
    ids_b = [eid for eid, _ in doc.build(kernel).entities[box]["edge"]]
    assert ids_a == ids_b and len(ids_a) == 12