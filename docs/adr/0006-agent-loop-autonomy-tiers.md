# ADR-0006: Agent feedback loop — autonomy tiers and circuit breakers

**Status:** accepted

## Context

The self-healing loop (users' agents file bugs, our agents fix them) is the
product's engine and its biggest risk. Unbounded, it floods issues, auto-merges
subtle geometry regressions, and special-cases the kernel into ossified mush.

## Decision

**Tiered autonomy — never one global "auto-fix" switch:**

| Tier | Scope | Gate |
|------|-------|------|
| 0 | File issue only, no code | automatic |
| 1 | Propose patch as PR | **human review required** |
| 2 | Auto-merge | only docs / added tests / dep bumps, full green CI |
| Never | Kernel semantics, identity logic, document format | human sign-off always |

**Hard rule: anything that changes geometric output is never auto-merged,**
regardless of test status (ties to geometric semver, ADR-0004).

**Dedup at the source:** every failure is fingerprinted (`gitcad.report`);
identical fingerprints increment an occurrence counter — one issue, not 10,000.
Occurrence count is the priority signal.

**Circuit breakers:** hard quotas on issues/hour, open auto-PRs, and agent spend.
Exceeding a threshold **halts and pages a human** — a runaway loop fails loud.

**Anti-symptom-fixing:** every fix PR must name the root cause and the violated
invariant, add a failing test first, and respect a complexity budget (special-case
count in kernel adapters) that alarms on growth.

## Security consequences (must-haves, not later)

- **Repro scripts are arbitrary code.** Auto-running a submitted repro = running
  untrusted code. Sandbox hard: container, no network, no secrets, CPU/mem caps,
  ephemeral.
- **Bug reports are untrusted input to the fixing agent** — a prompt-injection
  vector aimed at an agent with commit access. Report content is *data, never
  instructions*; the Tier-1 human gate is the backstop.
- During a major architecture change, drop the loop to **Tier 0** so agents don't
  patch the code being replaced.
