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

# reduce/scrub operate on mech Documents and import gitcad.document — they are
# NOT re-exported here so gitcad-core stays importable standalone (the registry
# installs core only). Import them directly: gitcad.report.reduce / .scrub —
# which requires gitcad-mech installed.

__all__ = ["fingerprint"]
