"""Delta-debugging reducer — proprietary model → minimal synthetic repro.

This is the "someone local recreates the bug in a simple, unrelated design" step
from the design discussion, done automatically. It is a near-perfect agent task:
a mechanical search with a crisp, deterministic oracle ("does the failure still
fingerprint the same?"), so no judgment is required and every step is verifiable.

Algorithm: a ddmin-style greedy minimization over the feature list. Repeatedly
try removing subsets of features; keep any removal that *preserves the same
failure fingerprint*. Terminate at a 1-minimal document (no single further
feature can be removed without changing the failure).

IMPORTANT: ``ReductionResult.minimal`` is a subset of the user's actual
features with the user's actual dimensions — NOT yet safe to transmit. The
transmit-safety gate is :func:`gitcad.report.scrub.prepare_submission`
(scrub + verify-twice, ADR-0007 steps 3-4).

Nothing here transmits anything. The output is a candidate payload for the user
to inspect and approve (ADR-0007).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from gitcad.document import Document, Feature

# An oracle takes a candidate document and returns the failure fingerprint it
# produces, or None if it no longer fails. Supplied by the caller so the reducer
# stays kernel-agnostic and testable with a synthetic oracle.
Oracle = Callable[[Document], "str | None"]


@dataclass
class ReductionResult:
    minimal: Document
    fingerprint: str
    original_size: int
    minimal_size: int
    steps: int


def _rebuild(features: list[Feature]) -> Document:
    """Rebuild a document from a feature subset, dropping features whose inputs
    were removed (so the tree stays well-formed after deletions)."""
    doc = Document()
    kept: set[str] = set()
    for f in features:
        if all(ref in kept for ref in f.inputs):
            # Re-add preserving the original id for stable fingerprinting.
            doc._features.append(f)          # noqa: SLF001 - internal rebuild
            doc._by_id[f.id] = f             # noqa: SLF001
            kept.add(f.id)
    return doc


def reduce_document(doc: Document, oracle: Oracle) -> ReductionResult:
    """Greedily minimize ``doc`` while preserving its failure fingerprint."""
    target = oracle(doc)
    if target is None:
        raise ValueError("document does not reproduce a failure; nothing to reduce")

    features = list(doc.features)
    steps = 0
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(features):
            candidate_features = features[:i] + features[i + 1 :]
            candidate = _rebuild(candidate_features)
            steps += 1
            if oracle(candidate) == target:
                # Removing feature i preserved the failure — keep it removed.
                features = list(candidate.features)
                changed = True
            else:
                i += 1

    minimal = _rebuild(features)
    return ReductionResult(
        minimal=minimal,
        fingerprint=target,
        original_size=len(doc),
        minimal_size=len(minimal),
        steps=steps,
    )
