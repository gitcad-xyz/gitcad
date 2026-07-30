# ADR-0024 — the `sampled` provenance tier

Status: accepted (2026-07-30)
Extends [ADR-0019](0019-certified-intervals.md) (certified intervals). Supersedes
nothing; the exactness charter is unchanged. This adds the third provenance tag
ADR-0019 explicitly anticipated:

> A future ADR may add a third tag (`sampled`) for genuinely unbounded-error
> meshes.

## Context

The kernel answers on three fields today — ℚ, ℚ[√d], ℚ[π] (exact) and
`CInterval` (certified) — and refuses everything outside them. `gitcad.bench`
measured what "outside" costs: of the composed grid's 95 open cells, the bulk
are booleans the exact and certified paths cannot reach because the result is a
general surface–surface intersection (two cylinders meeting in a space curve, a
square prism through a sphere) with no elementary or bracketable closed form.

The charter's rule was never "exact". It is **never silently wrong** — a bare
float is refused because it "carries no proof: you cannot tell a correct
534.6435 from a rounding artifact" (ADR-0019). A float with a *stated error
bound and a provenance label* carries exactly that proof, at coarser resolution.
That is what unblocks the remaining boolean grid without giving up the property
that distinguishes this kernel from OCCT: a caller always knows what it is
holding.

## Decision

**Add a third provenance tier, `sampled`: a Monte-Carlo answer with a reported
statistical error, used only where exact and certified both refuse.**

1. A `SampledSolid` is a CSG expression over the operand meshes. Its measures —
   volume, centroid — are Monte-Carlo estimates over the bounding box, with a
   **3σ half-width reported alongside**, exactly as a certified answer reports
   its bracket half-width. `provenance = "sampled"`.
2. **Deterministic.** The sampler is seeded from a fixed constant, so the same
   model gives the same number every run (ADR-0004's byte-canonical spirit —
   a sampled value is float and never enters `Document.dumps()`, but a bench
   number that jittered every run would be useless).
3. **Last resort only.** The boolean seam tries exact, then certified, then
   sampled. A shape that *could* be exact or certified never reaches the
   sampler — the same ordering rule ADR-0019 gives for intervals.
4. **Honestly labelled, never mixed.** A `sampled` result is never reported as
   `exact` or `certified`. Its error is statistical (∝ 1/√N), not a rigorous
   enclosure — so `sign()` off a sampled interval is NOT certified, and a
   sampled result must never drive a topological decision. It answers a
   measurement, it does not audit a construction.

## What it covers, and what it does not

Covers: the boolean cells — plane×quadric over `Body`, the transcendental walls
(sphere/cone through a prism), and quadric×quadric SSI. These are set operations
on solids that already tessellate, so point membership by ray casting is
well-defined and the volume is an honest unbiased estimator.

Does NOT cover: `fillet` (K5.2) and `shell` (K4.2). Those are not set operations
— they construct NEW surface (a rounded edge, an offset wall) that no membership
test on the inputs produces. A sampled blend needs approximate surface
construction, which is a separate decision, not this one.

## Consequences

- The composed grid's boolean gaps become `sampled` answers rather than
  refusals. The bench must report the tier: a `sampled` cell is not an `exact`
  or `certified` cell, and blending the counts would be the same dishonesty as
  counting a permanent wall as a gap.
- Error scales as 1/√N: ~0.2% relative at N = 200k, tightenable by the caller
  at linear cost. Reported, never hidden.
- The audit (`_audited`) does NOT run on a `SampledSolid` — there is no exact
  b-rep to check. This is the honest boundary: a sampled answer is a
  measurement of a shape the kernel did not construct exactly, and it says so.

## Alternatives considered

**A rigorous certified boolean** (interval marching over the SSI curve). The
principled endpoint, and a real research programme. `sampled` is the pragmatic
tier that answers today while that is built; a cell can later graduate from
`sampled` to `certified` without the caller's contract changing, because both
report a value and a half-width.

**Bare floats** (OCCT's model). Rejected by ADR-0019 and not reopened: a float
without a label or a bound is the one thing the charter forbids.
