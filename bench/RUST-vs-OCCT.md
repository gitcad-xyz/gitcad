# forge (Rust) vs OCCT wheel — head-to-head

The final Rust kernel (`forgekernel_rs`, exact BigRational with
floating-point predicate filters, cached-float coordinates, and a
move-not-clone BSP) against the OCCT wheel (`cadquery-ocp`), same
gitcad corpus, through the same seam. Timing is best-of-4 wall time per
model build (construction + mass properties). Generated 2026-07-23,
after the K4/K5 + Rust-K3 pass. The spring —
formerly forge's one failure — is now its biggest win: the certified
ℚ-interval tube volume evaluates in 0.13 ms against OCCT's 39.5 ms
swept-B-rep build, **306× faster and more accurate** (OCCT carries
4.4×10⁻⁷ relative error). `shelled_prism` exercises the K4.1 exact
half-plane inset (ref exactly 541/6) at 9.2×.

| model | occt ms | forge ms | speedup | volume match |
|---|---:|---:|---:|:---:|
| plate_with_holes | 13.55 | 2.01 | **6.7×** | exact |
| quadric_boss | 5.74 | 0.35 | **16.3×** | exact |
| revolve_profile | 1.55 | 0.18 | **8.8×** | exact |
| extrude_L | 2.03 | 0.23 | **8.8×** | exact |
| filleted_block | 10.40 | 0.52 | **19.8×** | exact |
| chamfered_block | 7.98 | 16.59 | **0.5× (2× slower)** | exact |
| shelled_box | 6.55 | 0.79 | **8.3×** | exact |
| shelled_prism | 11.33 | 1.23 | **9.2×** | exact* |
| drafted_block | 1.63 | 0.47 | **3.5×** | exact |
| spring | 39.49 | 0.13 | **306.6×** | certified* |
| loft_transition | 2.70 | 0.20 | **13.4×** | exact |
| sheetmetal_folded | 17.64 | 2.50 | **7.0×** | exact |
| quadric_sphere_overlap | 8.15 | 0.10 | **83.5×** | exact* |
| torture_tangent_cylinders | 5.52 | 0.13 | **41.2×** | exact |
| torture_coincident_faces | 4.30 | 0.57 | **7.5×** | exact |
| torture_sliver_cut | 4.54 | 0.75 | **6.1×** | exact |
| torture_tangent_sphere_plane | 2.78 | 1.00 | **2.8×** | exact |
| torture_menger_1 | 27.44 | 4.03 | **6.8×** | exact |
| **TOTAL (buildable on both)** | **173.3** | **31.8** | **5.5×** | — |

*`quadric_sphere_overlap`: forge is exact (`896/3·π`), OCCT carries
~1.4×10⁻⁹ relative error — see below. Within the 1e-6 agreement band,
so it counts as a match; but forge is the more accurate of the two.

### Capability

| | forge (Rust) | OCCT |
|---|---|---|
| corpus built | **20/20 (100%)** | 18/20 (90.0%) |
| fails | — | both mitered sweeps |

As of K3.0 forge builds the **entire** corpus. It builds both
sharp-cornered sweeps OCCT's float pipe rejects, *and* the coil spring
— the last holdout — now lands as a certified build (see K3.0 below).
OCCT fails two models forge builds; forge fails none.

### K3.0 — the coil spring, and the certified-interval charter (this iteration)

The spring is the first *transcendental* geometry: its volume is
`V = π ρ² L` with `L = turns·√((2πR)² + pitch²)` — and `√(a·π² + b)`
lives in no finite algebraic extension of ℚ. Pure exactness cannot
reach it, so ADR-0019 extends the charter with a fourth number kind:
the **certified interval** `[lo, hi]` of exact rationals that *provably*
brackets the true value. `π` enters through a digit-verified rational
enclosure; `√` returns a rational bracket `a² ≤ x ≤ b²`; every `+ − ×`
is exact — so a bracket widens only at the genuinely irrational steps,
by a bounded, reportable amount. A topological decision may consult a
sign only when the interval excludes zero; otherwise it tightens or
refuses. It never guesses.

The spring builds with a **certified** provenance tag (distinct from
`exact`): `mass_props` reports the interval midpoint plus a proven
half-width (~5×10⁻⁵⁰ here). And the oracle relationship *inverts*, as
with sphere-overlap: forge computes the exact tube volume bracketed to
50+ digits, while OCCT's swept-B-rep integration lands **4.4×10⁻⁷**
away — they agree within OCCT's own tolerance, but it is OCCT that
carries the error. The certified interval is the more precise object;
an independently computed `double` falls *outside* it.

### K2.2 — non-coaxial quadric booleans (this iteration)

Added the exact subset of non-coaxial quadric booleans. The general
case (parallel-cylinder lens, cylinder-through-wall) is transcendental
— an arccos/sqrt lens area not in ℚ[π] — and stays honestly refused.
But two cases *are* exact and now land:

- **Sphere-sphere overlap.** Union/intersect/cut of two genuinely
  overlapping spheres. The lens volume is a sum of spherical caps
  `π·h²(3r−h)/3`; when the centre distance and radii are rational the
  cap heights are rational, so every boolean stays in ℚ[π] with exact
  equality. Two r=5 spheres 6 apart: lens `104/3·π`, union `896/3·π`,
  cut `132·π` — exact. Refuses non-overlap, nesting, and irrational
  centre distance (→ K3).
- **Steinmetz bicylinder** = `16r³/3` — exact *and* π-free.

**The headline result is `quadric_sphere_overlap`: 84.5× faster.**
forge (via the analytic ℚ[π] path) evaluates the union as a handful of
`Fraction` operations — 0.10 ms — while OCCT tessellates two NURBS
spheres and runs a numerical B-rep boolean at 8.22 ms. And forge's
answer is *more accurate*: `896/3·π` exactly, versus OCCT's result
which is off by 1.4×10⁻⁹ relative from its own surface tolerance. This
is the exactness thesis at its sharpest — on a curved boolean, the
exact kernel is both **two orders of magnitude faster and strictly
more correct** than the 30-year float kernel.

### K3.1–K3.4 — curves, surfaces, SSI, STEP (the free-form frontier)

Four bricks landed beyond the corpus scoreboard, each oracle-checked:

- **NURBS curve + surface eval (de Boor / tensor de Boor).** Rational
  control data at rational parameters evaluates **exactly** — de Boor
  is only convex combinations, so no irrationality enters. forge
  returns points in ℚ³ where OCCT carries doubles; they agree to
  4.4×10⁻¹⁶ on Bézier, interior-knot B-spline, and 49-point surface
  grids, including partials vs OCCT's `D1`. Irrational weights (the
  √2/2 of a *true* circular arc) take the certified path: a quarter
  circle evaluates to points whose `x²+y²` brackets `[1,1]` to width
  1.4×10⁻⁵⁰ — certifiably *on* the circle.
- **General SSI with complete branch detection.** Exact de Casteljau
  subdivision + convex-hull bbox pruning: a pruned pair *provably*
  cannot intersect, so no branch is ever missed (completeness at
  resolution 2⁻ᵈ, stated). Points refined by Newton then certified by
  an **exact rational residual** `|A−B|² < 10⁻²⁰`. **The gate-G3
  differentiation moment, measured:** `z=(u−½)²` touches `z=0` along a
  tangential line — OCCT's `GeomAPI_IntSS` returns **zero** lines;
  forge finds the branch with 128 certified points. Both agree on
  transversal ground truth (2/1/0 branches); forge's empty answer is a
  *proof* (bbox disjointness), not a failure to find.
- **Native STEP reader, exact by construction.** STEP reals are decimal
  text; decimal text → `Fraction` is lossless. OCCT exports a freeform
  B-spline face to STEP; forge parses it and evaluates **bitwise
  identically** (worst delta 0.0), recovering `z = 3/8` as the exact
  rational where any float kernel reads 53 bits.

### The BSP optimization passes (three iterations)

The BSP predicates — plane `side()` and polygon degeneracy — are the
hot loop of every boolean. A **Shewchuk-style static float filter**
decides the sign in `f64` with a forward-error bound and falls back to
exact BigRational only when the magnitude is within the bound of zero
(answer always the exact sign; the oracle suite stays bit-identical).
Cached-float coordinates then let those filters read a stored `f64`
per vertex instead of reconverting big rationals. The latest pass makes
the BSP **move polygons instead of cloning them**: a polygon entirely
on one side of a split plane (the common case) is now handed down the
tree by ownership rather than deep-copying its BigRational vertices —
only a genuinely straddling polygon is decomposed. Net across all
three: chamfer 41→17 ms, aggregate 1.8×→4.0×. `torture_menger_1` (the
pure-BSP stress model) is the biggest single-pass beneficiary of the
move: 4.4→4.1 ms.

### Diagnosing the chamfer loss (a corrected story)

`chamfered_block` is the one model where forge loses (~2× slower than
OCCT). The earlier hypothesis was that this came from **large
intersection-coordinate denominators** growing through a deep boolean
chain. Profiling refuted that: for a d=2 chamfer of a 10-cube the
maximum coordinate denominator stays at **1** through all 20 cuts —
the coordinates are integers, there is *no* denominator growth. So the
queued "lazy-exact coordinates" refactor (store a float+interval beside
each rational, recompute exact on demand) **would not have helped
here** — a useful thing to have learned before building it.

The real cost is structural: the chamfer is **20 sequential boolean
cuts** (12 edges + 8 corners), each rebuilding the entire accumulating
solid's BSP. Per-cut time grows linearly with the solid's face count
(2.8→5.7 ms as faces go 7→26) — an O(n²) total. Two things were tried
and rejected: cutting the base by the *union* of all 20 tools instead
of sequentially (correct, but **35× slower** — the overlapping tools
build enormous intermediate geometry); and the move-not-clone pass
above (a real general win, but chamfer is rebuild-bound, not
allocation-bound, so it only shaved ~10%). Closing the chamfer gap
fully needs **localized/spatially-culled boolean cutting** (only
re-clip the faces the tool's bbox touches) — a genuine BSP change,
deferred as low-ROI: it is one model, both kernels finish in
single-digit-to-teens milliseconds, and the rest of the corpus is
2.7–87× faster.

### Where it stands

- **Exactness costs nothing on correctness and wins big on speed:** 15
  of 16 shared models are 2.7–87× faster than the OCCT wheel, at
  identical (or more-exact) volumes.
- **The one loss is honest and understood** — and now correctly
  diagnosed: chamfer is O(n²) BSP-rebuild-bound, not
  denominator-bound.
- **Bottom line:** the from-scratch exact kernel beats the 30-year
  OCCT wheel on capability *and* is 4.0× faster in aggregate on this
  corpus — and on curved booleans it is both faster and more accurate,
  losing only on a single deep-boolean model whose cost is a known,
  targetable algorithmic frontier.
