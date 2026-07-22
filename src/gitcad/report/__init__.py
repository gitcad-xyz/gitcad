"""Privacy-preserving bug reporting.

The rule (ADR-0007): a submitted issue must include a *repro*, but users will not
upload proprietary designs — so the local agent **reduces** the failing model to
a minimal, synthetic case unrelated to the user's work, and the user approves the
exact payload before anything leaves the machine.

- :mod:`gitcad.report.fingerprint` — deterministic failure keys for dedup.
- :mod:`gitcad.report.reduce` — delta-debugging reducer (the local "recreate it
  in a simple design" step, done by an agent, not a human).
"""

from gitcad.report.fingerprint import fingerprint
from gitcad.report.reduce import ReductionResult, reduce_document
from gitcad.report.scrub import Submission, prepare_submission, scrub, similarity

__all__ = ["fingerprint", "reduce_document", "ReductionResult",
           "scrub", "similarity", "prepare_submission", "Submission"]
