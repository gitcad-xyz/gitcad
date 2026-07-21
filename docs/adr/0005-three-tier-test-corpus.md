# ADR-0005: Three-tier test corpus (invariants over snapshots)

**Status:** accepted

## Context

A self-fixing agent loop generates tests. Unchecked, in 18 months you have
hundreds of thousands of auto-generated snapshot tests that make any architecture
change impossible — the tests encode the current implementation, so changing it
turns the suite red and the project ossifies.

## Decision

Tests live in three tiers with **different lifetimes**:

| Tier | What | Lifetime | Location |
|------|------|----------|----------|
| **Invariants** | Properties that must always hold, kernel-independent (booleans yield watertight solids; identity survives edits; export→import preserves topology) | **Permanent** | `tests/invariants/` |
| **Golden** | Small, curated, hand-written user-visible contracts | Permanent | `tests/golden/` |
| **Regression** | Auto-generated from reduced bug repros | **Disposable, bulk-invalidatable** | `tests/regression/` |

Rules:

- Auto-generated tests are **second-class**: quarantinable, samplable, and
  declarable obsolete *en masse* during a rewrite — no per-test sign-off.
- Auto-generated tests must pin to the **public API only**. Reaching into
  internals cements internals forever — forbidden.
- Snapshot tests encode *implementation*; invariants encode *meaning*. Only
  invariants survive an architecture change, so **invariants are the real spec.**
- Promotion (regression → invariant) is human-only and is how a durable property
  is recognized.

## Consequences

- Major architecture changes stay possible: quarantine `regression/`, keep
  `invariants/` + `golden/` green, shadow-run the new backend against the corpus.
- The permanent tiers are deliberately small and jealously guarded.
