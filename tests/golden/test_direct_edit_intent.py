"""GOLDEN: direct edits are INTENT records in the document (ADR-0022).

A move_face/offset_face/delete_face feature stores WHICH face (lineage-stable
entity id, ADR-0003) and BY HOW MUCH — never the rebuilt geometry. That is
what makes the edit REPLAY: change an upstream parameter and the direct edit
re-applies to the re-bound face on the new geometry (pinned with real
geometry in test_direct_edits.py; here the document contract runs with no
kernel installed at all).
"""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.kernel.null import NullKernel


def _null_box_doc() -> tuple[Document, str]:
    d = Document()
    fid = d.add(Feature(op="box", params={"dx": 40, "dy": 20, "dz": 10}))
    return d, fid


def test_document_records_offset_face_as_intent_null_kernel() -> None:
    d, fid = _null_box_doc()
    result = d.build(NullKernel())
    face_id, _ = result.entities[fid]["face"][0]
    d.add(Feature(op="offset_face", params={"faces": [face_id], "distance": 2},
                  inputs=[fid]))
    out = d.build(NullKernel())
    shape = out.final(d)
    assert shape.kind == "offset_face"
    assert shape.params["distance"] == 2
    # round-trip through the canonical text form keeps the intent verbatim
    reloaded = Document.loads(d.dumps())
    assert reloaded.features[-1].params["faces"] == [face_id]
    assert reloaded.build(NullKernel()).final(reloaded).kind == "offset_face"


def test_document_move_and_delete_face_build_on_null_kernel() -> None:
    d, fid = _null_box_doc()
    result = d.build(NullKernel())
    face_id, _ = result.entities[fid]["face"][0]
    d.add(Feature(op="move_face",
                  params={"faces": [face_id], "translate": [0, 0, 2]},
                  inputs=[fid]))
    d.add(Feature(op="delete_face", params={"faces": [face_id]},
                  inputs=[fid]))
    shapes = d.build(NullKernel())
    kinds = [s.kind for s in shapes.shapes.values()]
    assert kinds.count("move_face") == 1 and kinds.count("delete_face") == 1


def test_direct_edit_requires_an_input_feature() -> None:
    d = Document()
    d.add(Feature(op="box", params={"dx": 1, "dy": 1, "dz": 1}))
    d.add(Feature(op="offset_face", params={"faces": ["nope"], "distance": 1}))
    from gitcad.errors import GitcadError

    with pytest.raises(GitcadError, match="inputs"):
        d.build(NullKernel())


def test_delete_face_rejects_a_malformed_heal() -> None:
    d, fid = _null_box_doc()
    result = d.build(NullKernel())
    face_id, _ = result.entities[fid]["face"][0]
    d.add(Feature(op="delete_face",
                  params={"faces": [face_id], "heal": "guess"},
                  inputs=[fid]))
    from gitcad.errors import GitcadError

    with pytest.raises(GitcadError, match="heal"):
        d.build(NullKernel())
