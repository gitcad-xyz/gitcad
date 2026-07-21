"""Reducer tests — the privacy-preserving repro pipeline (ADR-0007).

Uses a synthetic oracle so no kernel is needed: we declare that the failure
"reproduces" iff a specific culprit feature is present. The reducer must strip
everything else down to a minimal case that still reproduces — modelling the
"recreate the bug in a simple, unrelated design" step.
"""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.report.reduce import reduce_document


def _noisy_doc_with_culprit() -> tuple[Document, str]:
    d = Document()
    b = d.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 10}))
    c = d.add(Feature(op="cylinder", params={"radius": 1, "height": 5}))
    culprit = d.add(Feature(op="fillet", params={"radius": 999}, inputs=[b]))  # the "bug"
    d.add(Feature(op="boolean", params={"kind": "cut"}, inputs=[b, c]))
    return d, culprit


def test_reduces_to_minimal_repro() -> None:
    doc, culprit = _noisy_doc_with_culprit()

    def oracle(candidate: Document) -> str | None:
        # "Fails" iff the culprit fillet is still present.
        return "fp_demo" if any(f.id == culprit for f in candidate.features) else None

    result = reduce_document(doc, oracle)

    assert result.fingerprint == "fp_demo"
    assert result.minimal_size < result.original_size
    # The minimal repro still contains the culprit (and its required input).
    ids = {f.id for f in result.minimal.features}
    assert culprit in ids


def test_raises_when_nothing_fails() -> None:
    doc, _ = _noisy_doc_with_culprit()
    with pytest.raises(ValueError):
        reduce_document(doc, lambda _c: None)
