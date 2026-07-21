# ADR-0007: Privacy-preserving bug reduction

**Status:** accepted

## Context

A useful bug report needs a repro. But users will not upload proprietary
designs — mechanical/electrical work is frequently confidential or
export-controlled. "Just redact coordinates" leaks: coordinates *are* the shape.

## Decision

A submitted issue must include a repro, and the repro is produced by **automated
test-case reduction on the user's machine** — the local agent recreates the
failure in a minimal, *synthetic* model unrelated to the user's design, and the
user approves the exact payload before anything is transmitted.

Pipeline (`gitcad.report`):

1. **Capture** the failing op + kernel diagnostic → `FailureSignature` →
   `fingerprint` (no coordinates, safe to transmit, stable across models).
2. **Reduce** via delta-debugging (`reduce_document`): greedily drop features,
   keeping only what preserves the same fingerprint. Oracle is deterministic —
   an ideal agent task, fully verifiable.
3. **Scrub**: round dimensions, canonicalize coordinates/orientation, strip names
   and comments.
4. **Verify twice**: reduced case still trips the same fingerprint; similarity
   check confirms it no longer resembles the original.
5. **Approve**: show the user the full minimal script + fingerprint + env. Nothing
   hidden. They click send.

Reduction beats redaction categorically: the submitted artifact **is not the
user's geometry** — it's a new synthetic construction hitting the same code path.
Nothing to leak because nothing was carried over. And a 15-line repro is
*reviewable*; a 4,000-feature assembly never gets legal approval.

## Consequences

- **Fallbacks** when reduction won't converge (some bugs need the complexity):
  fingerprint-only report (zero geometry), or fully local-only bug (nothing
  uploaded, enterprise mode).
- **Synthetic amplification:** from a fingerprint-only report, our own fuzzer can
  search for a synthetic reproducer — coverage with no user data at all.
- **A publishable corpus:** every repro is synthetic and unrelated to real
  designs, so the whole regression corpus is legally clean to open-source — a
  public good and a moat no incumbent (whose bug DBs are locked in customer
  geometry) can match.
