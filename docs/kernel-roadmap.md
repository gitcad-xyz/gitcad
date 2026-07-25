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

**290/345 (84.1%) working · 55 honest gaps · 0 crashes.**
(218/345 when this document was written; 236 after ADR-0021 landed;
247 after transforms and STEP moved to the canonical form; 290 after the
Cone and RevolveSolid converters, the native body text format, and
chamfer/shell on curved solids.)

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

### P1 — rigid transforms, exports, chamfer, shell — DONE
Transforms, STEP, the native text format, chamfer and closed shell all route
through the canonical B-rep now, and the `Cone` and `RevolveSolid` converters
landed. What is left is no longer plumbing.

### What the last 55 cells actually need

The remaining gaps are **three missing geometry types**, not fifty-five
missing features. Nothing here is closable by another fallback.

| # cells | blocked on | why it is real work |
|---|---|---|
| 21 | **conic-section curves** (K2.2) | cutting a quadric with a plane produces an ellipse / parabola / hyperbola. The canonical curve set is `Line | Circle`; a general plane–cylinder edge is none of those, and faceting it would be exactly the approximation the charter forbids. |
| 14 | **torus surfaces** (K5.2) | filleting a lathed rim sweeps a torus. A `RevolveSolid` profile is line segments only, so the fillet arc has nowhere to live. |
| ~10 | **trimmed quadric faces** (`RoundedBox`, cone/sphere chamfer+shell) | a rounded box is quarter-cylinders and octant-spheres — partial bands, with loops that mix arcs and lines on a CURVED surface. |

The good news in each row:

- **Conic sections stay exact.** An ellipse from a plane–cylinder cut has
  rational centre and axes when both operands are rational, so `Ellipse` is a
  ℚ-parameterised curve like `Circle` — no new number field, and the
  divergence-theorem volume terms extend the same way the cone's did.
- **Torus volume is exact in ℚ[π]** (Pappus: V = 2πR·A), so a filleted rim
  costs a surface type, not a number field.
- **Trimmed quadrics at 90° are exact**, because sin/cos of a right angle are
  0 and ±1. A rounded box is the tractable case; arbitrary trims are not, and
  should keep refusing.

The order that pays: **trimmed quadrics → torus → conic sections**, cheapest
and least risky first. Each one should land with its own oracle (analytic
volume AND Monte Carlo) before the next starts — every silent wrong-volume bug
this kernel has had was caught by an oracle, never by the suite.

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
