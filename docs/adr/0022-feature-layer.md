# ADR-0022 — A feature layer above the kernel, and `Body` as the only public return type

Status: **accepted**. A and B implemented 2026-07-29 (#125); C not started.
Date: 2026-07-25
Supersedes: nothing. Extends ADR-0021 (canonical B-rep).

> **Implementation note (2026-07-29).** Decisions **A** (`Body` is the only type
> the seam returns) and **B** (the `_repr` hint, spelled `Body.repr_hint`) are
> live. Decision **C** — features as named, re-playable operations with their
> own lineage ids — is **not** started; nothing below should be read as claiming
> it. The measurement this ADR demanded first was run and its answer decided the
> design: `to_body` succeeds for all 15 corpus representations and agrees with
> every one of the 13 closed forms **exactly**, but conversion costs *more* than
> the operation it replaces for all 15 — 3-10x typically, 400x for a filleted
> box. So the hint is load-bearing exactly as predicted here, not an
> optimisation, and B is not optional.
>
> The consolidation was made answer-preserving rather than merely tested: the
> seam recovers the source form on the way in, so every internal computation is
> byte-identical to what it was before. Two things that took finding — the
> conversion must happen only at the OUTERMOST seam frame (ops call each other,
> and handing an inner call a canonical `Body` made `shell` invent refusals and
> `_exact_bbox` return `None` into a tuple unpack), and `tessellate` must never
> take the hint path, which is the defect this ADR was written from.
>
> Verified: single-op 353/360 and composed 180/285, both **unchanged**, which is
> this ADR's "does not add capability" claim in the only form that can be
> checked. The hint-may-never-change-the-answer oracle it asks for is
> `tests/invariants/test_a_repr_hint_never_changes_the_answer.py`.
>
> The `isinstance` chains it hoped to collapse have **not** collapsed — 175 of
> them remain inside `ref.py`, now reached through the recovered form. Migrating
> them op by op under the differential oracle is the remaining work, and doing
> it that way is deliberate: all at once would produce a refactor nobody can
> bisect.

## Context

ADR-0021 established one canonical `Body` that every representation converts to,
so an operation is written once rather than once per representation. That fixed
the *arithmetic* duplication. It did not fix the *interface* duplication, and
this session produced the evidence for why that still matters.

`Kernel` operations return whatever representation the implementation happened
to produce — `Solid`, `Cyl`, `DrilledSolid`, `AxisStack`, `RevolveSolid`,
`RoundedBox`, `DisjointUnion`, `MiteredSweep`, `SphereOverlap`, `FilletedBox`,
`TubeSolid`. Eleven types through one seam. Three consequences, all observed:

**1. Every downstream operation must re-dispatch.** `ref.py` contains long
`isinstance` chains — one per op — and each is a place where two branches can
disagree about the same question. They did. `tessellate` preferred each
representation's own mesher over the canonical one; measuring the pair showed
the canonical path was strictly better on every curved shape, and worse, several
representations' method does not *accept* a deflection, so `except TypeError:
return shape.tessellate()` silently discarded the caller's argument. That is a
wrong answer to a reasonable question, and it was invisible because the mesh was
still valid — just not the one asked for.

**2. Capability depends on construction history, not on the shape.** A plate
with a hole is a `DrilledSolid` if you drilled it and something else if you
built it another way, and the two support different operations. An agent cannot
predict what will work from the geometry it can see. This is the single largest
source of "refused" cells that are not real exact-field limits.

**3. Representations leak into user code.** Callers `isinstance`-check kernel
outputs to decide what to do next, which pins the internal taxonomy as public
API and makes any consolidation a breaking change.

## Decision

**A. `Body` is the only type the `Kernel` seam returns.** Every public operation
returns a `Body`. The eleven representations become private construction
strategies — retained, because they are how exactness is achieved cheaply, but
never surfaced.

**B. Representations become a lazily-attached optimisation, not an identity.**
A `Body` may carry a `_repr` hint naming the special form it came from. Ops may
consult the hint to take a fast exact path. **The hint may never change the
answer** — only the cost of computing it. Concretely: if an op produces a
different result with and without the hint, that is a defect, and the existing
differential oracle can be pointed at exactly this question by running the
corpus twice with hints stripped.

**C. Features are named, re-playable operations above the kernel.** A feature
records intent (`hole(d=6, through=True, at=(15,15))`) rather than the boolean
that implemented it. This is what makes identity durable under ADR-0003: a
feature has a lineage id, so a downstream reference survives a change in how the
kernel chose to build it.

## Consequences

**What gets better.** The `isinstance` chains collapse to one dispatch at
construction. A capability becomes a property of the shape, not of its history.
The matrix stops having cells that differ only because two paths reach the same
solid. Ops are written once, against `Body`, which is the ADR-0021 bet applied
to the interface as well as the arithmetic.

**What gets worse, honestly.** Converting to `Body` eagerly costs time on shapes
where the special form was the whole point — `Cyl.volume()` is a closed form and
`B.volume(B.to_body(cyl))` is a divergence sum over faces. This is why B keeps
the hint rather than deleting the representations. The measurement to make
before implementing: convert the corpus and record the cost, per shape, of
`to_body`. If any shape's conversion dominates its own operations, the hint path
is load-bearing rather than an optimisation, and that shape needs its exact
closed form reachable *through* `Body` — not around it.

**What this does NOT do.** It does not add capability. Every cell the matrix
refuses today for an exact-field reason still refuses. This is an interface
consolidation, and claiming otherwise would misread the matrix afterwards.

## Sequencing — and the precondition

Under the constitution's own procedure for an architecture change, this is step
1 of 6, and steps 3–5 (build behind the seam, shadow-run old vs new against the
corpus diffing volume and topology hash, then cut over) are the substance.

**Precondition, stated so it is not quietly skipped:** this refactor touches
every operation and every caller. It must not be started while confirmed
correctness defects are open, because a refactor on top of known-broken
foundations makes it impossible to tell a new defect from a pre-existing one
when the shadow-run diverges. The order is: burn down the open review findings,
then do this.

## Why it is written now rather than after

Because the evidence is fresh and specific. `tessellate`'s discarded deflection
argument is the exact failure mode this ADR exists to prevent, and it was found
by measurement this session. Recording the decision while the measurement is at
hand is worth more than recording it later from memory.
