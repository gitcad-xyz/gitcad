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

**340/345 (99%) working · 0 honest gaps · 5 permanent (outside any exact
field) · 0 crashes** — identical on main (repo venv, 2026-07-27) and on the
released **0.9.8** wheels (clean-venv `pip install gitcad==0.9.8`).

(Progression: 218/345 when this document was written; 236 after ADR-0021
landed; 247 after transforms and STEP moved to the canonical form; 290 after
the Cone and RevolveSolid converters, the native body text format, and
chamfer/shell on curved solids; 327 at the 0.9.6 release; 339 after
the trimmed-quadric, torus, and Q[√d] exact-field work; 340 — the ceiling
short of the five proven walls — measured on the 0.9.8 wheels.)

The matrix does not yet probe the K7 freeform boolean cells (loft × loft
and PatchSolid × PatchSolid land outside its 15 representations × 23 ops
grid); 0.9.8's freeform booleans are verified by their own oracle suite
and by hand-derived closed forms instead.

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

### What the last 55 cells actually needed — and what is left

The 55 gaps were **three missing geometry types**, not fifty-five missing
features, and that diagnosis held: trimmed quadric faces, torus surfaces, and
the shipped conic-section cases all landed (on main, unreleased), taking the
matrix from 290 to 339. The predictions that paid off:

- **Trimmed quadrics at 90° are exact** (sin/cos of a right angle are 0 and
  ±1) — rounded boxes, blind bores, counterbores, and composite shells now
  build.
- **Torus volume is exact in ℚ[π]** (Pappus: V = 2πR·A) — filleted rims,
  napkin rings, and torus-aware erosion for shells landed, and torus bodies
  are no longer exempt from the edge-pairing audit.
- **Widening the exact field beat faceting.** `F()` now admits ℚ[√d] and
  ℚ[√d][π], which is what unblocked cone shell/chamfer, the mitred sweep, and
  the straddling-bore cuts.

What remains, per the matrix on the 0.9.8 wheels (0 honest gaps, 5
permanent — each wall carries a transcendence proof, recorded in
`docs/releases/0.9.7.md`):

| cell | status |
|---|---|
| sphere × cut box | permanent — the intersection curve is outside any exact field |
| cone × cut box | permanent — same |
| cone × fillet(all) | permanent — same |
| chamfered box × chamfer(all) | permanent — same |
| loft × fillet(all) | permanent — a wall, not a gap |

"Permanent" is a classification, not a defeat: those cells refuse by name
rather than approximate, per the charter.

Each landing carried its own oracle (analytic volume AND Monte Carlo) — every
silent wrong-volume bug this kernel has had was caught by an oracle, never by
the suite.

### Deliberately deferred
- **engrave** — text strokes rotate by arbitrary angles, which leave ℚ[√d]
  (mixed radicals). Needs a bigger number field (K3.1) or a different
  formulation. Honest refusal is correct for now.
- **freeform STEP topology (K3.7)** — still open (the real-world round-trip
  for SolidWorks exports; consumes K7's trimmed-patch type).
- **NURBS booleans (K7)** — shipped in 0.9.8 for PatchSolid × PatchSolid and
  loft × loft, with certified volume brackets and named refusals for the
  tangent/corner/mixed cases; re-trim of results, prism/tube skins, and
  rational operands remain (see `docs/ROADMAP.md`).

## How to work this list

1. Re-run the matrix at the start of a batch: `python -m gitcad.bench.capability --md`.
2. Pick the highest-priority cluster (not a single cell — cells cluster by root
   cause; 55 crashes were one bug).
3. Implement exactly; refuse honestly where the field runs out.
4. Adversarially review — on this kernel that has repeatedly caught silent
   wrong-volume bugs that tests missed, including **a test that asserted the
   wrong answer**. A green suite is not evidence until you check what it claims.
5. Re-run the matrix; coverage must go up and crashes must stay at 0.
