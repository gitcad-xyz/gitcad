# 0013. Sketch constraints: solved at authoring time, never at build time

Date: 2026-07-22
Status: Accepted

## Context

SolidWorks-class sketching is constraint-driven: the user draws roughly, then
coincident/parallel/dimension constraints pull the geometry exact. gitcad
profiles today are explicit coordinates (`Profile.line_to(30, 0)`), which is
precise but pushes all arithmetic onto the author — and our authors are mostly
agents, who are good at arithmetic but bad at *keeping* dozens of derived
coordinates consistent when one dimension changes.

The tempting design is a constraint solver in the build loop: store
constraints in the document, solve on every rebuild. That is how interactive
CAD works, and it is wrong for gitcad:

1. **Determinism.** A numeric solver (Newton on the constraint Jacobian) has
   solution multiplicity — mirrored and flipped branches satisfy the same
   constraints. Which branch you get depends on the initial guess and solver
   internals. A document that builds differently on two machines, or after a
   solver upgrade, violates ADR-0004's byte-canonical → geometry-deterministic
   chain and makes "a geometry change is a breaking change" (ADR-0006)
   unenforceable.
2. **Debuggability.** When a build-time solve fails or jumps branches, the
   failure surfaces far from the edit that caused it, in a file the agent may
   not even be touching.

## Decision

Constraints are an **authoring-time tool**; the document format stays
solved-coordinates-only.

- New module `gitcad.sketch_solver` (mech): a `ConstraintSketch` builder that
  accepts entities (points, lines, arcs) + constraints (coincident,
  horizontal/vertical, parallel, perpendicular, tangent, equal, distance,
  angle, radius) and **emits a plain `Profile`** — the same params dict the
  kernel already consumes. 2D-only, Newton–Raphson on the residual vector with
  the sketch's drawn coordinates as the initial guess (that choice of guess is
  what pins the intended branch).
- The solve happens in the agent/MCP call (`sketch_solve` tool), not in
  `Document.build`. What lands in the document is the solved, exact profile —
  reviewable, diffable, and rebuilt identically forever.
- The *constraint source* may be kept alongside as an annotation
  (`params["constraints_src"]`, ignored by the build) so a later edit can
  re-solve from intent instead of hand-editing coordinates. It is
  documentation, not input: deleting it changes nothing about the geometry.
- Solver failures (over/under-constrained, non-convergence) are authoring
  errors reported with the residual per constraint — never a build failure.
- Degrees-of-freedom accounting is part of the result (`dof` remaining), so an
  agent can see "under-constrained by 2" and add the missing constraints
  instead of trusting a coincidentally-right solution.

## Consequences

- Document format unchanged — no migration, no breaking change, ADR-0004
  intact. Solved profiles from any other tool remain first-class.
- Parametric re-solve is explicit: change a dimension in the constraint
  source, call `sketch_solve`, get a new exact profile, diff it. The geometry
  change is visible in review, exactly where ADR-0006 wants it.
- We accept that constraint intent can drift from the solved profile when
  someone edits coordinates directly. The `constraints_src` annotation is
  best-effort documentation; the solved coordinates are always the truth.
- The solver can start small (the nine constraint kinds above cover the
  SolidWorks intro curriculum) and grow without touching the kernel or the
  document schema.
