"""Scrub + similarity tests — the ADR-0007 transmit-safety gate."""

from __future__ import annotations

from gitcad.document import Document, Feature
from gitcad.report.scrub import prepare_submission, scrub, similarity


def _user_design() -> tuple[Document, str]:
    """A 'proprietary' design: distinctive dimensions, a file param, and one
    culprit feature that trips the failure."""
    d = Document()
    b = d.add(Feature(op="box", params={"dx": 47.13, "dy": 23.77, "dz": 6.35}))
    c = d.add(Feature(op="cylinder", params={"radius": 1.588, "height": 6.35}))
    d.add(Feature(op="boolean", params={"kind": "cut"}, inputs=[b, c]))
    culprit = d.add(Feature(op="fillet", params={"radius": 999.0, "comment": "acme-proj-x"},
                            inputs=[b]))
    d.add(Feature(op="sphere", params={"radius": 12.7}))
    return d, culprit


def _oracle_for(op_name: str, param: str, threshold: float):
    """Failure class: any feature of ``op_name`` with param > threshold."""
    def oracle(doc: Document) -> str | None:
        for f in doc.features:
            if f.op == op_name and f.params.get(param, 0) > threshold:
                return "fp_demo"
        return None
    return oracle


def test_scrub_strips_context_and_rounds_dimensions() -> None:
    doc, _ = _user_design()
    scrubbed = scrub(doc)
    all_params = [f.params for f in scrubbed.features]
    assert not any("comment" in p for p in all_params)
    # Distinctive dims coarsened: 47.13 -> 47.1
    assert any(p.get("dx") == 47.1 for p in all_params)


def test_similarity_reports_leakage_metrics() -> None:
    doc, _ = _user_design()
    m = similarity(doc, scrub(doc))
    assert m["surviving_feature_fraction"] == 1.0   # scrub alone doesn't reduce


def test_prepare_submission_safe_case() -> None:
    """Failure survives scrubbing and the minimal repro is tiny → safe."""
    doc, culprit = _user_design()
    sub = prepare_submission(doc, _oracle_for("fillet", "radius", 100))
    assert sub.transmit_safe, sub.reasons
    assert sub.fingerprint == "fp_demo"
    # The safe payload is small and scrubbed of the user's context.
    assert len(sub.scrubbed) < len(doc)
    assert not any("comment" in f.params for f in sub.scrubbed.features)


def test_prepare_submission_unsafe_when_exact_dims_matter() -> None:
    """A failure that depends on an exact dimension does NOT survive rounding —
    the verdict must be unsafe (fallback: fingerprint-only report)."""
    doc = Document()
    doc.add(Feature(op="box", params={"dx": 47.13, "dy": 1.0, "dz": 1.0}))

    def oracle(d: Document) -> str | None:
        for f in d.features:
            if f.op == "box" and f.params.get("dx") == 47.13:
                return "fp_exact"
        return None

    sub = prepare_submission(doc, oracle)
    assert not sub.transmit_safe
    assert "failure-does-not-survive-scrubbing" in sub.reasons
