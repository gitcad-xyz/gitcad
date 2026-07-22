# ADR-0011: Night Shift — scheduled autonomous work sessions

**Status:** accepted (implementation staged after the registry MVP)

## Context

Most subscription users leave the majority of their agent quota unused daily;
it expires worthless. The project has an unbounded queue of exactly the work
agents do well unattended. Connect the two — and answer the question every
open-source CAD project dies on: who does the unglamorous work?

## Decision

A built-in scheduler: *"between these hours, spend up to X of my quota on this
queue, show me a morning report."* Opt-in, visible budget, one-click off.

**Queues, in priority order:**
1. **The user's own backlog** (why they turn it on): DRC/validation sweeps with
   fix-proposals as draft PRs; drawing regeneration; reduced repros for their
   failing invariants; lockfile update proposals with impact diffs;
   cross-domain checks ("enclosure changed Tuesday — board still fits").
2. **The community queue** (the flywheel, separately opt-in): part verification
   (re-derive `draft` components from datasheets — the `verified` tier of
   ADR-0010, embarrassingly parallel); synthetic-reproducer search for
   fingerprint-only bug reports (ADR-0007); regression triage; corpus fuzzing.

**Hard rules (stricter than daytime, per ADR-0006):**
- Overnight work produces **proposals only** — draft PRs, attestations,
  reports. Nothing merges. Tier-1 stays Tier-1 at 3am.
- Hard caps on tokens, wall-clock, task count; any cap halts cleanly.
- Circuit breakers stop; the report explains why. Nobody is paged at 3am.
- Community tasks process untrusted input (datasheets, bug reports =
  prompt-injection vectors): maximally sandboxed, no path to the user's own
  designs — separate process, separate mounts, no credentials.
- Anything ambiguous → skip and report. Precision over recall, always.

**The morning report is the product surface:** what ran, what it cost, every
proposal linked to a diff, decisions ranked, halts explained, and an explicit
"nothing merged, nothing left this machine except what you pre-approved."

**Incentives are reputation, not payment:** attestation counts and registry
standing. Monetizing idle quota invites verification fraud; reputation with
consequences is self-policing.

**Queue coordination:** a simple lease on the registry so two users' agents
don't verify the same part redundantly.

## Consequences

- The registry's verification army is everyone's idle agents, with humans
  promoted to reviewers.
- Requires the fingerprint queue (ADR-0006), reducer (ADR-0007), and registry
  trust tiers (ADR-0010) — staged accordingly; daytime tooling is built with
  "unattended mode" as a known future consumer (clean halts, resumable tasks,
  machine-readable results).
