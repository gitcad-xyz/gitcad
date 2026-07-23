# A gitcad-native kernel from scratch — design study

Goal stated by the project owner: a kernel that ultimately handles
**very complex surfaces** — the territory where SolidWorks (Parasolid)
decisively beats FreeCAD (OCCT). This document is the plan for how we
would build it and, more importantly, how we would *plan and verify*
the functionality so the effort survives contact with reality.

## 1. Why Parasolid wins on surfaces — the actual root causes

Feature lists don't explain the gap. Five engine-level properties do:

1. **Surface–surface intersection (SSI) quality.** The crown jewel.
   Parasolid's SSI finds *every* branch of an intersection (no missed
   loops), traces smooth curves through near-tangencies, and handles
   singular configurations (tangent cylinders, cone apexes) without
   fragmenting. OCCT's SSI misses branches and produces wiggly,
   fragmented curves — and every downstream failure (booleans, fillets,
   shells) is usually an SSI failure in disguise.
2. **Procedural surfaces held exactly.** Parasolid keeps offsets,
   blends, sweeps, and spun surfaces *procedural* — evaluated lazily
   from their definition — instead of approximating early into
   degree-exploded NURBS the way OCCT does. Precision loss compounds;
   not approximating is the cure.
3. **Tolerance discipline.** OCCT gives every vertex/edge/face its own
   mutable tolerance (a fudge factor that grows as errors accumulate —
   "tolerance smearing"). Parasolid tracks *error bounds* against a
   single model tolerance and fails operations that can't meet it.
4. **Blending as a first-class engine.** Variable-radius,
   curvature-continuous (G2) blends with setbacks and corner patches —
   built on top of robust SSI + robust offsets. OCCT's filleting fails
   precisely because its two prerequisites are weak.
5. **Topological decisions never made from inexact tests.** The
   classification logic (in/out/on) is guarded so floating-point noise
   cannot produce an inconsistent topology, even when geometry is
   approximate.

The plan below is these five properties, earned in order.

## 2. Non-negotiable architecture decisions

- **Language: Rust.** Memory safety for a 10-year codebase, fearless
  parallelism for subdivision/tracing workloads, first-class FFI back
  into the existing Kernel seam.
- **Split topology from geometry accuracy.** Topological decisions
  (does this curve cross this face?) are made with *certified*
  computation: interval arithmetic first, escalating to adaptive exact
  arithmetic (Shewchuk-style) or algebraic methods when intervals are
  ambiguous. Geometric results (the curve itself) are approximate but
  carry **tracked error bounds**. A decision is never derived from an
  unbounded approximation.
- **One model tolerance + per-entity error bounds.** No per-entity
  fudge factors. An op that cannot deliver its result within tolerance
  returns a structured failure naming the entities and the achieved
  bound — never a silently sloppy model.
- **Degeneracy by design.** Symbolic perturbation (simulation of
  simplicity) so coincident/tangent inputs take a *consistent* branch
  instead of ad-hoc epsilon tests scattered through the code.
- **Analytic surfaces stay analytic.** Plane/cylinder/cone/sphere/torus
  are exact types with closed-form intersectors; NURBS is the fallback,
  not the substrate. Procedural surfaces (offset, blend, sweep) are
  first-class lazy types.
- **Identity native (ADR-0003 pushed down).** Every operation returns
  (new model, lineage map): which output faces descend from which input
  faces. What we emulate today with fingerprints becomes an engine
  guarantee.
- **Structured results native.** Success carries lineage + error
  bounds; failure carries diagnosis (sub-op, entities, tolerance
  context). The agent repair loop is a first-class consumer.
- **Bit-deterministic.** Fixed evaluation orders, no fast-math,
  canonical serialization; the ADR-0006 geometry gate becomes hash
  equality. Same input, same bytes, every platform.
- **Non-manifold-capable topology** (radial-edge), immutable/persistent
  structures — cheap undo, safe parallelism, natural history.

## 3. How to plan the functionality — method, not feature list

**Plan the operator algebra, not features.** Everything SolidWorks
ships reduces to eight core operators: *boolean, sweep (incl. extrude/
revolve), offset, blend, trim/split, stitch/sew, loft/boundary-fill,
tessellate* — plus the query set (classification, distance, mass
properties, HLR). Features are compositions; the kernel roadmap is the
operator roadmap. The SW/KiCad feature maps we already wrote are the
demand signal telling us which operator capabilities each feature pulls.

**Corpus-first.** Before code: assemble the verification corpus.
- The gitcad model corpus (every part in our repos + registry).
- A STEP import corpus (real-world free-form models).
- A **torture corpus**: tangent cylinders, near-parallel planes, cone
  apex intersections, sliver faces, self-tangent offsets, knife edges —
  the graveyard of every kernel effort, collected up front.
- Property-based generators + fuzzing from day 0 (random CSG programs;
  invariants: watertightness, Euler characteristic, volume additivity
  vol(A)+vol(B)=vol(A∪B)+vol(A∩B), boolean idempotence/commutativity).

**Oracle-driven scoring.** Kernel quality is a *number on a dashboard*,
never vibes: SSI branch-completeness rate, boolean success rate,
fillet completion rate, max deviation vs. oracle, watertight rate — per
corpus, per commit. OCCT is the always-available differential oracle;
STEP round-trips through users' SolidWorks installs extend it to
Parasolid ground truth where it matters.

**Acceptance suite already exists.** The Kernel seam is the contract;
`tests/invariants/` is the architecture-independent spec; ADR-0002's
shadow-run protocol (build corpus on both backends, diff volume/
topology/mass, cut over per surface class) is the promotion mechanism.
The new kernel replaces OCCT *operator by operator, surface class by
surface class* — never big-bang.

## 4. The staged roadmap

| Stage | Scope | Proves | Ships value |
|---|---|---|---|
| 0 | Geometry foundation: eval, intervals, exact predicates, STEP reader, tessellation | numerical substrate | corpus + viewer on new tessellator |
| 1 | Planar B-rep booleans, exact arithmetic end-to-end | the topological core is *correct by construction* | boxes/plates/brackets |
| 2 | Quadrics + torus with closed-form intersectors; extrude/revolve/hole/pattern | analytic SSI; most mech parts | replaces OCCT for ~80% of gitcad models |
| 3 | NURBS + **general SSI** (subdivision/Bézier-clipping branch finding + certified marching) | the crown jewel; the long pole (expect 2–3 years alone) | imported free-form, sweeps, lofts |
| 4 | Offsets + shell + draft (procedural offsets, self-intersection trimming) | prerequisite #2 for blends | thin-wall/molded parts |
| 5 | Blends: constant → variable → G2, setbacks, corner patches | the SolidWorks-parity milestone | fillets that just work |
| 6 | Surfacing suite: boundary/fill with G1/G2 constraints, trim/untrim/knit, curvature analysis (combs, zebra) | "complex surfaces" end goal | industrial-design-grade surfacing |

Each stage ends with: shadow-run vs OCCT on the corpus, dashboard
green, cutover for that class behind the seam, OCCT retained as
fallback for everything not yet promoted.

## 5. Honest effort accounting

Parasolid embodies hundreds of person-years. What makes a from-scratch
attempt sane *now*, when it wasn't in 2005:

- The robustness literature is mature (certified numerics, exact
  predicates, subdivision methods) — the algorithms are published;
  the moat was always the *engineering verification*, and
  verification-first is exactly the gitcad discipline.
- Property-based testing + fuzzing + differential oracles industrialize
  robustness work that used to be bug-report-driven.
- We don't need Parasolid's breadth: stages 0–2 already carry most of
  gitcad's real workload, so value ships years before surfacing parity.
- Agents change the economics of the long tail: porting published
  algorithms, generating torture cases, and triaging corpus regressions
  are exactly the workloads this project automates.

Realistic horizon: stages 0–2 ≈ 18–30 months of focused work;
stage 3 is the multi-year center of gravity; stages 5–6 (the stated
end goal) are meaningful only after 3–4 are trustworthy. License:
from-scratch means we choose (Apache-2.0), with OCCT remaining a clean
LGPL-with-exception fallback dependency behind the seam indefinitely.

## 6. First three concrete moves (when this is greenlit)

1. Write `ADR-0018 kernel-strategy` (dependency → surgical fork →
   scoped wedge → staged native kernel) — the durable decision record.
2. Build the corpus + dashboard harness NOW against OCCT alone: the
   scoring infrastructure is kernel-independent and immediately useful
   (it quantifies today's OCCT failures on our own models).
3. Prototype stage 1 (exact planar booleans in Rust behind the seam,
   shadow-run on the corpus) — small enough to be a real go/no-go
   signal on team velocity before any serious commitment.
