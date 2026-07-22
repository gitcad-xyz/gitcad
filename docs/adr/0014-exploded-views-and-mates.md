# 0014. Exploded views are projections; mates get semantics before a solver

Date: 2026-07-22
Status: Accepted

## Context

Two related SolidWorks-class features remain undesigned: exploded assembly
views and a mate solver. Both touch the same question: what does an assembly's
text *mean*?

Today (ADR-0008) an assembly is instances with explicit transforms plus
`Mate` records that are **checked, not solved**: `asm.mate("a.port",
"b.port")` validates that the two ports coincide under the given transforms.
The transforms are the truth; mates are assertions about them.

A full mate solver inverts that: transforms become derived outputs of
mate constraints (coincident, concentric, distance...). That is a 3D
constraint system with all the branch-multiplicity problems of ADR-0013,
multiplied by rigid-body DOF bookkeeping.

## Decision

**Exploded views: a projection, shipped now.** An exploded view is a display
transform, never a model edit — the assembly text does not change. Explode
offsets live in a view spec (`view/exploded.part.json` pattern from the
dogfood, promoted to a first-class `ExplodedView` document: per-instance
offset vectors + optional trace lines). Renderers (viewer, drawing engine)
apply offsets at draw time. Auto-explode derives default offsets from mate
directions: each instance moves along the axis of its mate port frame,
ordered by assembly depth. This is pure geometry derivation — deterministic,
no solver.

**Mates: grow semantics inside the checked model, solver stays out of the
document.** The mate vocabulary extends from "ports coincide" to typed
relations (coincident, concentric, distance, angle), each still a *checked
assertion* against explicit transforms. A `mate_solve` authoring tool (same
philosophy as ADR-0013) can compute transforms that satisfy the mates —
seeded from current transforms, branch pinned by the seed — and writes the
solved transforms back into the assembly text. Build never solves; it only
re-checks. Interference (existing exact check) runs after any solve as the
sanity gate.

## Consequences

- Assembly text stays the deterministic truth; two machines can never
  disagree about where a part is (ADR-0004/0006 preserved).
- Exploded views need no new kernel capability and cannot corrupt a model —
  worst case is a silly-looking drawing.
- The mate solver becomes an incremental authoring feature: each new mate
  type ships with its check first (build-time, cheap, deterministic), then
  its solve support (authoring-time). A mate type without solve support is
  still useful as a design-rule assertion.
- Drawing integration: `assembly_drawing` (FR3) gains an `exploded=` option
  consuming the same `ExplodedView` spec, with balloon anchors following the
  offsets — one spec drives viewer, drawing, and docs renders.
