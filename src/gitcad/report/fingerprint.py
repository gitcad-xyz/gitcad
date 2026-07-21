"""Deterministic failure fingerprints.

A fingerprint is the dedup key: 10,000 users hitting one kernel bug must produce
one issue. It is derived only from *what went wrong* — the failing operation and
the kernel's own diagnostic class — never from user coordinates, so it is both
safe to transmit and stable across unrelated models (ADR-0006/0007).

The occurrence count of a fingerprint is the priority signal — strictly better
triage than raw report volume.
"""

from __future__ import annotations

import hashlib

from gitcad.errors import FailureSignature


def fingerprint(signature: FailureSignature) -> str:
    """A short, stable id for a failure class. Same (kernel, op, diagnostic) →
    same fingerprint, on every machine."""
    return "fp_" + hashlib.blake2b(signature.key().encode(), digest_size=10).hexdigest()
