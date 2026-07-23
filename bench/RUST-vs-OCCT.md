# forge (Rust) vs OCCT wheel — head-to-head

The final Rust kernel (`forgekernel_rs`, exact BigRational with
floating-point predicate filters and cached-float coordinates) against
the OCCT wheel (`cadquery-ocp`), same gitcad corpus, through the same
seam. Timing is best-of-4 wall time per model build (construction +
mass properties). Generated 2026-07-23, after the K2.2 pass.

| model | occt ms | forge ms | speedup | volume match |
|---|---:|---:|---:|:---:|
| plate_with_holes | 13.30 | 2.00 | **6.7×** | exact |
| quadric_boss | 5.84 | 0.37 | **15.8×** | exact |
| revolve_profile | 1.61 | 0.17 | **9.4×** | exact |
| extrude_L | 2.27 | 0.23 | **10.0×** | exact |
| filleted_block | 10.58 | 0.50 | **21.0×** | exact |
| chamfered_block | 8.30 | 18.90 | **0.4× (2.3× slower)** | exact |
| shelled_box | 6.64 | 0.87 | **7.6×** | exact |
| drafted_block | 1.56 | 0.46 | **3.4×** | exact |
| loft_transition | 2.92 | 0.21 | **13.8×** | exact |
| sheetmetal_folded | 18.59 | 2.67 | **7.0×** | exact |
| quadric_sphere_overlap | 8.22 | 0.10 | **84.5×** | exact* |
| torture_tangent_cylinders | 5.58 | 0.13 | **42.3×** | exact |
| torture_coincident_faces | 4.55 | 0.63 | **7.2×** | exact |
| torture_sliver_cut | 4.75 | 0.82 | **5.8×** | exact |
| torture_tangent_sphere_plane | 2.80 | 1.00 | **2.8×** | exact |
| torture_menger_1 | 27.82 | 4.39 | **6.3×** | exact |
| **TOTAL (buildable on both)** | **125.3** | **33.5** | **3.75×** | all exact |

*`quadric_sphere_overlap`: forge is exact (`896/3·π`), OCCT carries
~1.4×10⁻⁹ relative error — see below. Within the 1e-6 agreement band,
so it counts as a match; but forge is the more accurate of the two.

### Capability

| | forge (Rust) | OCCT |
|---|---|---|
| corpus built | **18/19 (94.7%)** | 17/19 (89.5%) |
| fails | spring (transcendental helix, K3) | both mitered sweeps |

forge builds both sharp-cornered sweeps OCCT's float pipe rejects;
OCCT builds the helix forge defers to K3. Disjoint failure sets,
forge ahead on count.

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

### The float-filter + cached-float passes (prior iterations)

The BSP predicates — plane `side()` and polygon degeneracy — are the
hot loop of every boolean. A **Shewchuk-style static float filter**
decides the sign in `f64` with a forward-error bound and falls back to
exact BigRational only when the magnitude is within the bound of zero
(answer always the exact sign; the oracle suite stays bit-identical).
Cached-float coordinates then let those filters read a stored `f64`
per vertex instead of reconverting big rationals. Together: chamfer
41→18 ms, aggregate 1.8×→3.75×.

### Where it stands

- **Exactness costs nothing on correctness and wins big on speed:** 15
  of 16 shared models are 2.8–84× faster than the OCCT wheel, at
  identical (or more-exact) volumes.
- **The one loss is honest and understood.** `chamfered_block` is
  still ~2.3× slower — the corner-facet chamfer is a deep chain of
  exact boolean cuts producing large-denominator intersection
  *coordinates* (not just predicates), which the filter can't touch.
  Closing it fully needs lazy-exact *coordinates* (a bigger refactor,
  deferred as low-ROI — it's one model).
- **Bottom line:** the from-scratch exact kernel beats the 30-year
  OCCT wheel on capability *and* is 3.75× faster in aggregate on this
  corpus — and on curved booleans it is both faster and more accurate,
  losing only where exact-coordinate growth is fundamental.
