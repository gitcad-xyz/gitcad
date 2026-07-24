# Kernel roadmap — from a measured capability matrix

*Generated basis: `python -m gitcad.bench.capability --md` (re-run it; this
document is a snapshot with judgement layered on top).*

## Why gaps kept surfacing "unexpectedly"

Three structural reasons, all now fixed or fixable:

1. **OCCT was masking the truth.** Until ADR-0020, `AutoKernel` silently fell
   back to OCCT whenever forge refused an operation. forge's real coverage was
   therefore never measured — every gap was invisible by construction. Cutting
   OCCT did not create the gaps; it *revealed* a backlog that had been hidden
   for the kernel's whole life.

2. **The gap list was reactive.** It was assembled from whichever tests happened
   to fail. That only finds gaps a test already looks at — which is why STEP
   export of *any* drilled part (the primary manufacturing handoff, broken for
   every real part) went unnoticed until it was probed by hand.

3. **Failures crashed instead of reporting.** 55 operation/representation
   combinations raised a bare `AttributeError` through the seam rather than an
   honest refusal, so they were indistinguishable from bugs and invisible to any
   census. One structural fix (`_guard_seam` in `kernel/ref.py`) converted all
   of them into stage-named `NotYetImplemented` refusals.

**The fix for the meta-problem is the capability matrix**: every `Kernel` seam
operation × every solid representation, probed mechanically, classified as
works / honest-refusal / bad-input / crash. It is the roadmap, and it is
regenerable — no more discovering fundamentals by accident.

## Current state

**218/345 (63%) working · 127 honest gaps · 0 crashes.**

Rules this establishes:

- **A crash is always a defect**, whether or not the capability exists. Raw
  exceptions through the seam are not allowed; the matrix must stay at 0.
- **A refusal is a roadmap entry**, not a bug. It is the charter's preferred
  failure (ADR-0019) and must name the stage that will deliver it.
- **Coverage is the number to move.** Every kernel batch should raise it, and
  regressions should be visible.

## What works everywhere (the solid floor)

`measure`, `mass_props`, `bbox`, `validate`, `tessellate`, `entities(face)`,
`hlr_project`, `section_polys`, `export_stl` work on **every** representation.
So: measuring, viewing, 2D drawings and mesh export are universal. That is the
verify/render loop the product is built on, and it is complete.

## The gaps, in priority order

Priority = (how common the part is) × (how blocking the loss is).

### P1 — rigid transforms on curved/composite solids
`mirror` and `scale` refuse on every non-planar representation; `rotate` refuses
on drilled/composite ones. This blocks symmetric parts, mirrored brackets and
unit changes for anything with a hole — the most common shapes there are.
*Tractable:* mirror/scale of a `DrilledSolid` is mirror/scale of its base plus
each bore, all exact. Same for `DisjointUnion` (per member) and `RevolveSolid`
(profile). Mostly plumbing, little new math.

### P2 — booleans on curved operands (K2.2/K2.3)
`cut box` and `union box` refuse on quadrics; `cut cylinder` refuses on spheres
and cones. This is the countersink blocker (cone-vs-solid) and the general
"pocket a curved part" case. *Real math:* needs quadric∩planar surface
intersection. The `bore_cyl` revolve-profile trick generalises here — a coaxial
cut of a solid of revolution is another solid of revolution — and covers
countersinks and tapered bores without full K2.3.

### P3 — `entities(edge)` on curved solids
Refuses everywhere except planar. Blocks edge selection (fillet/chamfer
targeting, dimension anchoring) on any part with a hole. *Tractable:* a bore
contributes two circular edges with known centre/radius/plane; that descriptor
already exists in `cylinder_faces()`.

### P4 — blends and shells on curved/composite solids
`fillet(all)` refuses nearly everywhere; `shell` refuses on curved solids.
*Genuinely hard* (K5.2 general blends, K4.2 offset surfaces) — schedule after
P1–P3 and do not let it block them.

### P5 — `export_step`/`export_brep` on the remaining representations
Drilled solids now export exactly (0.9.5); bare cylinders, revolves, lofts and
disjoint unions still refuse. *Tractable:* the STEP writer already emits
`CYLINDRICAL_SURFACE` + `CIRCLE`; a bare `Cyl` is two disks and a wall, and a
`RevolveSolid` is a lathe of the same primitives. `export_brep` needs the forge
text format to describe non-planar solids at all.

### Deliberately deferred
- **engrave** — text strokes rotate by arbitrary angles, which leave ℚ[√d]
  (mixed radicals). Needs a bigger number field (K3.1) or a different
  formulation. Honest refusal is correct for now.
- **freeform STEP topology (K3.7), general NURBS booleans (K7)** — the crown
  work; unchanged in scope.

## How to work this list

1. Re-run the matrix at the start of a batch: `python -m gitcad.bench.capability --md`.
2. Pick the highest-priority cluster (not a single cell — cells cluster by root
   cause; 55 crashes were one bug).
3. Implement exactly; refuse honestly where the field runs out.
4. Adversarially review — on this kernel that has repeatedly caught silent
   wrong-volume bugs that tests missed, including **a test that asserted the
   wrong answer**. A green suite is not evidence until you check what it claims.
5. Re-run the matrix; coverage must go up and crashes must stay at 0.
