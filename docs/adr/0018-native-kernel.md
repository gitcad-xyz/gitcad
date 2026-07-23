# ADR-0018: gitcad-native B-rep kernel, from scratch, oracle-verified

## Status

Accepted (2026-07-23, project owner directive: "let's give it a try
from scratch so we aren't encumbered... we can just test against the
output of the occt").

## Context

gitcad binds OCCT behind the `Kernel` seam (ADR-0002). OCCT's ceiling
on complex surfaces — fragmenting surface–surface intersections,
tolerance smearing, early NURBS approximation, fragile fillets — is
the gap between FreeCAD-class and SolidWorks-class geometry
(docs/research/kernel-from-scratch.md). Forking OCCT would carry that
architecture; the owner has chosen unencumbered from-scratch, with
OCCT retained indefinitely as the differential oracle and fallback
backend behind the seam.

## Decision

1. **Three-backend architecture.** The seam hosts, simultaneously:
   - `occt` — production backend and *differential oracle*.
   - `ref` — the new kernel's **reference implementation in Python
     with exact rational arithmetic**: slow, correct-by-construction,
     the executable specification of kernel semantics.
   - `forge` — the production port (Rust) of whatever `ref` has
     proven, added per operator class. `ref` is forge's oracle; OCCT
     is the independent cross-check. Until forge exists, `ref` itself
     is promoted for operator classes where its performance suffices.
2. **Correctness discipline.** Topological decisions in `ref` use
   exact arithmetic (rationals) — no epsilons in classification, ever.
   Approximation appears only with tracked error bounds. Identity
   lineage and structured failure are native op results, not wrappers.
3. **Verification is the schedule.** A corpus + scorecard harness
   (kernel-independent, runs today against OCCT alone) defines
   per-operator-class metrics: build success, volume/area/bbox deltas
   vs oracle, topology counts, watertightness. An operator class cuts
   over per ADR-0002 shadow-run only when its scorecard is green over
   the whole corpus; OCCT remains the fallback for everything else.
4. **Scope ordering** (docs/research/kernel-coverage-plan.md holds the
   full matrix): exact planar solids → quadrics/torus closed-form →
   NURBS + general SSI → offsets/shell/draft → blends → surfacing
   suite. Complex surfaces are the end goal; value ships from the
   planar stage onward.
5. **No format change.** Document text, feature ops, and entity-id
   semantics are unchanged; the kernel swap is invisible above the
   seam. Auto-generated regression tests that encode OCCT quirks may
   be quarantined per the constitution; `invariants/` + `golden/` stay
   green throughout.

## Consequences

- Two kernels to maintain during the (long) transition; the seam
  contract must stay disciplined — every new op lands in the Protocol,
  null, occt, and (as it matures) ref.
- `ref` doubles as documentation: the readable statement of what every
  operator MEANS, something OCCT never gave us.
- The scorecard harness immediately quantifies today's OCCT failures
  on our own corpus, useful even if forge never ships.
- License: ref/forge are gitcad-licensed (unencumbered); OCCT remains
  a clean LGPL-with-exception dependency.
