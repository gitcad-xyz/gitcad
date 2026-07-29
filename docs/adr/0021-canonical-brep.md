# ADR-0021 — one canonical B-rep; representations become constructors

Status: accepted (2026-07-24)
Extends [ADR-0018](0018-native-kernel.md) (forge is the kernel) and
[ADR-0020](0020-forge-sole-kernel.md) (forge is the *only* kernel). The
exactness charter ([ADR-0019](0019-certified-intervals.md)) is unchanged and
governs everything below.

## Context

The capability matrix (`python -m gitcad.bench.capability`) measured the kernel
for the first time: **23 seam operations × 15 solid representations = 345
cells, 63% working.** The remaining 127 gaps are not one missing algorithm —
they are the shape of the architecture.

forge grew a *separate representation per feature*: `Solid` (planar BSP), `Cyl`,
`Sphere`, `Cone`, `AxisStack`, `DrilledSolid`, `RevolveSolid`, `DisjointUnion`,
`RoundedBox`, `FilletedBox`, `MiteredSweep`, `SphereOverlap`, `TubeSolid`,
`LoftSolid`, `SplinePrism`. Each was the fastest way to make one feature exact,
and each implements a *different subset* of the geometry protocol. So:

- work is **O(ops × representations)** — every new op must be written 15 times,
  every new representation must implement 23 ops;
- coverage is a lookup table nobody can hold in their head, which is why
  fundamental holes (STEP export of any drilled part) went unnoticed for months;
- an op written against the planar `Solid` API silently duck-typed onto a
  quadric and raised `AttributeError` — 55 such crashes, one root cause.

No amount of patching closes a quadratic matrix. Mature kernels (OCCT,
Parasolid) do not have this problem because they have exactly **one** topology
representation, and every operation is written once against it.

## Decision

**Introduce a single canonical B-rep, `forgekernel.body.Body`, and make every
existing representation a CONSTRUCTOR for it rather than a parallel universe.**

```
Body  = [Face]
Face  = (Surface, [Loop], sense)      # sense: outward normal == surface normal?
Loop  = [Edge]                        # first loop outer, rest are holes
Edge  = (Curve, v0, v1)               # v0 == v1 for a full circle
Surface ∈ {Plane, Cylinder, Cone, Sphere}          (NURBS arrives with K3.7)
Curve   ∈ {Line, Circle}                           (NURBS arrives with K3.7)
```

Every surface and curve carries **exact** parameters (rational or ℚ[√d] points,
directions and radii). The canonical form is *analytic, never faceted* — a hole
is a `Cylinder`, not a polygon fan.

Three consequences:

1. **Operations are written once.** `transform`, `bbox`, `mass_props`,
   `entities`, `tessellate`, `export_step` become one implementation each
   against `Body`, replacing up to fifteen. Work drops from O(ops × reps) to
   **O(ops) + O(reps)** — 23 implementations plus 15 converters instead of 345
   cells.

2. **Existing representations stay** — as exact constructors and as fast paths.
   `DrilledSolid` still computes its volume in ℚ[π] directly; that is exact and
   cheap and there is no reason to lose it. What changes is that when a
   specialised path has nothing to offer, the op converts to `Body` and runs the
   generic implementation instead of refusing.

3. **Booleans are explicitly NOT unified here.** General surface–surface
   intersection is the K3/K7 crown work and does not get easier by having one
   representation. Booleans keep their specialised exact paths and their honest
   refusals. This ADR is about the other 20 operations, which are the bulk of
   the gaps and need no SSI.

## Exactness

Unchanged: no float decides topology. Specifically —

- Surface/curve parameters are `Fraction` or `SurdVal`; transforms of them are
  exact (a rotation by a ℚ[√d] angle maps a `Cylinder` to a `Cylinder`).
- **Mass properties stay exact** via the divergence theorem applied per face
  analytically: a planar face contributes `(1/3)·(n·p)·Area`, a cylindrical band
  contributes a closed form in ℚ[π], and so on. No integration by sampling.
- Tessellation and hidden-line remain **display** properties where floats are
  legal (ADR-0019), and now have one implementation instead of fifteen.
- An operation that would leave the exact number field still **refuses with its
  stage**. A canonical representation does not license approximation.

## Consequences

- **Coverage becomes reachable.** The matrix is the acceptance test: every
  non-boolean cell should become ✅, and the roadmap collapses from 127
  scattered gaps to a short list of genuinely-hard boolean/blend work.
- **A conversion layer is new surface area.** Each converter must be proven
  against the representation it replaces — the shadow-run below is not optional.
- **Some conversions are lossy in provenance, not geometry.** A `TubeSolid`
  carries a certified `CInterval` volume; converting it to `Body` and
  re-integrating must reproduce the same interval or the converter is wrong.
- **Non-uniform scale of a cylinder is not a cylinder.** The canonical form
  refuses it (an elliptical cylinder is a new surface type, deferred) rather
  than silently approximating — the same honesty rule as everywhere else.

## Migration (the CLAUDE.md major-change process)

1. This ADR extends ADR-0018/0020; the charter is untouched.
2. Build `body.py` **behind the existing seam** — no caller changes while it
   lands.
3. **Shadow-run**: for every representation, convert to `Body` and diff the
   geometry against the specialised implementation — exact volume equality,
   bbox equality, and mesh-volume agreement. A converter ships only when its
   representation's own numbers reproduce.
4. Wire the seam to fall back to `Body` when a specialised op refuses; never
   the reverse (fast exact paths keep priority). **A fallback must preserve the
   FAILURE behaviour too, not just the successes** — routing `entities` through
   the canonical form changed the exception *type* raised for a representation
   with no converter yet (`NotImplementedError` → `KernelError`) and broke five
   passing tests that depended on it. "No regression" means observable
   behaviour, including how an operation declines.
5. Re-run the capability matrix. Coverage must rise and crashes stay at 0
   (pinned by `tests/invariants/test_seam_enforcement.py`).
6. Cut over per-op, not big-bang: each operation flips to the generic
   implementation only once its shadow-run is clean.
