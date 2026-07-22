"""Scrub + similarity check — ADR-0007 steps 3 and 4, the transmit-safety gate.

The reducer (:mod:`.reduce`) produces a *subset of the user's actual features
with the user's actual dimensions* — NOT yet safe to transmit. This module
finishes the pipeline:

- :func:`scrub` rewrites the minimal repro with sanitized dimensions (rounded
  to coarse values), stripped non-essential string params (file paths, names),
  and re-minted ids — then re-runs the oracle to confirm the failure survived
  sanitization.
- :func:`similarity` measures how much of the original design leaks into the
  candidate: surviving feature fraction and shared exact dimension values.

:func:`prepare_submission` combines both into a verdict: a payload is
``transmit_safe`` only if the scrubbed repro still fingerprints identically
AND resembles the original weakly enough. When it isn't safe, the honest
fallback is a fingerprint-only report (ADR-0007) — never "ship it anyway".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gitcad.document import Document, Feature
from gitcad.report.reduce import Oracle, ReductionResult, reduce_document

# String params that carry user context and are never needed to reproduce a
# geometry-kernel failure class.
_STRING_DENYLIST = {"file", "sha256", "name", "label", "comment"}

# Feature-count and dimension-overlap ceilings for "does not resemble the
# original". Conservative on purpose; ADR-0007 says precision over recall.
_MAX_SURVIVING_FRACTION = 0.34
_MAX_DIM_OVERLAP = 0.5
# A repro this small is inherently non-identifying — the fraction test only
# applies above it (2 features of a 5-feature doc is 40% but reveals nothing;
# 200 features of a 500-feature design is a different matter).
_SMALL_REPRO_FEATURES = 5


def _scrub_value(v, ndigits: int):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), ndigits)
    if isinstance(v, (list, tuple)):
        return [_scrub_value(x, ndigits) for x in v]
    return v


def scrub(doc: Document, *, ndigits: int = 1) -> Document:
    """Sanitized copy: dimensions coarsened, contextual strings stripped,
    ids re-minted from the scrubbed values."""
    out = Document()
    id_map: dict[str, str] = {}
    for f in doc.features:
        params = {k: _scrub_value(v, ndigits)
                  for k, v in f.params.items() if k not in _STRING_DENYLIST}
        new_id = out.add(Feature(op=f.op, params=params,
                                 inputs=[id_map[i] for i in f.inputs]))
        id_map[f.id] = new_id
    return out


def similarity(original: Document, candidate: Document) -> dict[str, float]:
    """How much of the original leaks into the candidate. Auditable numbers,
    not a verdict — :func:`prepare_submission` applies the thresholds."""
    surviving = len(candidate) / len(original) if len(original) else 0.0
    orig_dims = {round(float(v), 6) for f in original.features
                 for v in f.params.values() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    cand_dims = {round(float(v), 6) for f in candidate.features
                 for v in f.params.values() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    dim_overlap = (len(orig_dims & cand_dims) / len(cand_dims)) if cand_dims else 0.0
    return {"surviving_feature_fraction": round(surviving, 3),
            "dimension_overlap": round(dim_overlap, 3)}


@dataclass
class Submission:
    """The candidate bug-report payload plus its transmit-safety verdict."""

    fingerprint: str
    reduction: ReductionResult
    scrubbed: Document | None
    transmit_safe: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def prepare_submission(doc: Document, oracle: Oracle) -> Submission:
    """Full ADR-0007 pipeline: reduce → scrub → verify twice.

    ``transmit_safe=False`` means: submit the fingerprint only. The scrubbed
    document is still returned for LOCAL debugging either way — it just must
    not leave the machine unless safe.
    """
    reduction = reduce_document(doc, oracle)
    reasons: list[str] = []

    scrubbed = scrub(reduction.minimal)
    # Verify #1: the failure must survive sanitization (some bugs need exact
    # dimensions — then the repro is inherently user data and cannot ship).
    if oracle(scrubbed) != reduction.fingerprint:
        reasons.append("failure-does-not-survive-scrubbing")
        return Submission(reduction.fingerprint, reduction, scrubbed, False, reasons)

    # Verify #2: the scrubbed repro must not resemble the original design.
    metrics = similarity(doc, scrubbed)
    if (len(scrubbed) > _SMALL_REPRO_FEATURES
            and metrics["surviving_feature_fraction"] > _MAX_SURVIVING_FRACTION):
        reasons.append("resembles-original:feature-fraction")
    if metrics["dimension_overlap"] > _MAX_DIM_OVERLAP:
        reasons.append("resembles-original:dimension-overlap")

    return Submission(reduction.fingerprint, reduction, scrubbed,
                      transmit_safe=not reasons, reasons=reasons, metrics=metrics)
