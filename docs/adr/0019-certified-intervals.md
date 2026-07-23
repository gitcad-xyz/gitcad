# ADR-0019 — Certified intervals: the K3 extension to the exactness charter

Status: accepted (2026-07-23)
Supersedes nothing; extends ADR-0018 (native kernel) and the exactness
charter recorded in the kernel coverage plan.

## Context

K1 and K2 hold to a hard rule: **no float ever influences a topological
decision.** Numbers live in exact fields — ℚ (Fraction), ℚ[π] (PiVal),
ℚ[√d] (SurdVal) — and anything outside the current field earns an
honest, stage-named refusal.

K3 (curves: helices, NURBS, general surface–surface intersection) breaks
that comfort. The quantities are genuinely transcendental. A coil
spring's volume is

    V = π ρ² · L,   L = turns · √((2πR)² + pitch²)

and `√(a·π² + b)` lies in **no** finite algebraic extension of ℚ we can
close over. A NURBS surface point, the arc length of a free-form edge,
the intersection parameter of two spline patches — none are exactly
representable. Pure exactness cannot reach them. We refuse to answer with
a bare float, because a bare float carries no proof: you cannot tell a
correct 534.6435 from a rounding artifact.

## Decision

Introduce a fourth number kind: the **certified interval** `CInterval`
— a pair of exact rationals `[lo, hi]` that *provably* brackets the true
value, with arithmetic that only ever widens the bracket, never loses
the enclosure. The charter is restated:

> Every topological decision is made from a **certified sign**. A sign
> is certified when it comes from exact field arithmetic (K1/K2) **or**
> from a `CInterval` that strictly excludes zero. If an interval
> straddles zero, the kernel tightens it (more precision) and retries;
> if it cannot certify within budget, it refuses — it never guesses.

So the spirit is unchanged: **no unproven decision.** What changes is
that "proven" now includes "proven by a bracket," not only "proven by an
exact closed form." A `CInterval` is not a float with error bars bolted
on after the fact — the bounds are the primitive, and they are rigorous:
`π` enters only through a hard-coded, digit-verified rational enclosure;
`√` returns a rational bracket `[a, b]` with `a² ≤ x ≤ b²`; every `+ − ×`
on rationals is exact, so an interval widens *only* at the genuinely
irrational steps and by a *bounded, reportable* amount.

### Provenance is first-class

A solid now carries a provenance tag:

- `exact` — every coordinate and decision is exact field arithmetic
  (all of K1/K2). `forge == ref` bit-for-bit; `mass_props` volume is an
  exact `Fraction`/`PiVal`.
- `certified` — some quantity is a `CInterval`. `mass_props` returns the
  interval midpoint as the reported float **plus** a proven half-width;
  the true value is guaranteed inside. Decisions were still certified.

A `certified` result is never silently mixed with an `exact` one, and
the scorecard/report always shows which it is.

### The oracle relationship inverts, honestly

For `exact` ops, OCCT is the oracle and `ref` must match it (it does, to
machine ε). For `certified` ops the relationship flips: **`ref` is the
more principled computation** and OCCT is the approximation. The spring
is the first witness — `ref` gives the exact tube volume bracketed to
arbitrary precision; OCCT's swept-B-rep integration lands 4.4×10⁻⁷ away.
They agree within OCCT's own tolerance, but it is OCCT that carries the
error, not `ref`. The differential test therefore asserts *agreement
within a stated band*, not bit-identity, for `certified` models.

## Consequences

- The exact fields (ℚ, ℚ[π], ℚ[√d]) remain the default and the first
  choice; `CInterval` is used only where no exact field reaches. A model
  that *could* be exact must not silently fall back to an interval.
- Refusals do not disappear — they move outward. An interval that cannot
  certify a sign within the precision budget is still a stage-named
  refusal, not a coin flip.
- This unblocks K3: interval-certified de Boor for NURBS evaluation,
  certified marching for SSI, and — first — the helix/pipe family and
  the coil spring.
- A future ADR may add a third tag (`sampled`) for genuinely
  unbounded-error meshes; K3 does not need it.

## First implementation (K3.0)

`forgekernel.interval.CInterval` (+ `pi_interval`, rational `sqrt`),
`forgekernel.curve.Helix` (arc length as a `CInterval`) and `TubeSolid`
(the swept round section; certified volume `π ρ² L`). The corpus
`spring` model flips from refusal to a `certified` build, taking `ref`
and `forge` to full corpus coverage.
