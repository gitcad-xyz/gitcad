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

**247/345 (71.6%) working · 98 honest gaps · 0 crashes.**
(Was 218/345 when this document was written; 236 after ADR-0021 landed.)

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

**A cell being green is not the same as it being right.** Two of these were
green while returning wrong numbers: `mass_props` substituted the bbox centre
for a real centroid behind a flag no caller read, and `tessellate` returned
meshes with hairline cracks whose volume was nonetheless correct. Neither the
matrix nor the suite can see that — only an oracle that knows the true answer
can. Pair every coverage push with one.

## The gaps, in priority order

Priority = (how common the part is) × (how blocking the loss is).

### P1 — rigid transforms on curved/composite solids — MOSTLY DONE
Transforms now route through the canonical B-rep (ADR-0021), which rotates
exactly for the ℚ[√d] angles. `rotate` went from 14 refusals to 3, and what is
left is **not a transform problem at all**: it is four missing `Body`
converters. Every remaining `mirror`/`scale`/`rotate`/`export_step` refusal on
a curved solid reduces to one of

| missing converter | unlocks (cells) |
|---|---|
| `Cone` | mirror, scale, export_step |
| `RevolveSolid` | rotate ×2, mirror, scale, export_step, entities(edge) |
| `RoundedBox` (filleted box) | translate, rotate ×2, mirror, scale, export_step, export_stl |
| `DisjointUnion` with a `DrilledSolid` member | rotate ×2, mirror, scale, export_step |

That is ~22 cells behind four converters — the highest-leverage work left, and
the O(reps) half of ADR-0021 rather than new mathematics.

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
STEP is now written **once** against the canonical B-rep
(`forgekernel.stepbody`), emitting `PLANE`, `CYLINDRICAL_SURFACE` and
`SPHERICAL_SURFACE` analytically with shared edges. Bare cylinders, bosses and
spheres export; what still refuses is the same four converters as P1, plus
`CONICAL_SURFACE`. The acceptance test is a manifold oracle **on the emitted
file** — every `EDGE_CURVE` used by exactly two faces, in opposite directions
once `ADVANCED_FACE`'s same_sense flag is folded in. A file that merely opens
proves nothing; one that fails this will not boolean, mesh for CAM, or import
as a solid.

`export_brep` (10 refusals) needs the forge text format to describe non-planar
solids at all — that is a format decision, not a geometry one, and it should
follow ADR-0004's byte-canonical rule.

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
