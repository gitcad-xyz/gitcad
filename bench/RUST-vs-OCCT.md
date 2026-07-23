# forge (Rust) vs OCCT wheel — head-to-head

The final Rust kernel (`forgekernel_rs`, exact BigRational with
floating-point predicate filters) against the OCCT wheel
(`cadquery-ocp`), same gitcad corpus, through the same seam. Timing is
best-of-4 wall time per model build (construction + mass properties).
Generated 2026-07-23, after the float-filter pass.

| model | occt ms | forge ms | speedup | volume match |
|---|---:|---:|---:|:---:|
| plate_with_holes | 13.15 | 2.04 | **6.5×** | exact |
| quadric_boss | 5.88 | 0.37 | **16.0×** | exact |
| revolve_profile | 1.66 | 0.18 | **9.3×** | exact |
| extrude_L | 2.14 | 0.23 | **9.3×** | exact |
| filleted_block | 10.68 | 0.54 | **19.7×** | exact |
| chamfered_block | 8.46 | 18.37 | **0.5× (2× slower)** | exact |
| shelled_box | 6.64 | 0.85 | **7.8×** | exact |
| drafted_block | 1.58 | 0.46 | **3.4×** | exact |
| loft_transition | 2.76 | 0.21 | **13.1×** | exact |
| sheetmetal_folded | 18.31 | 2.67 | **6.9×** | exact |
| torture_tangent_cylinders | 5.58 | 0.14 | **41.2×** | exact |
| torture_coincident_faces | 4.43 | 0.62 | **7.1×** | exact |
| torture_sliver_cut | 4.76 | 0.84 | **5.7×** | exact |
| torture_tangent_sphere_plane | 2.81 | 1.06 | **2.7×** | exact |
| torture_menger_1 | 27.81 | 4.46 | **6.2×** | exact |
| **TOTAL (buildable on both)** | **116.7** | **33.0** | **3.5×** | all exact |

### Capability

| | forge (Rust) | OCCT |
|---|---|---|
| corpus built | **17/18 (94.4%)** | 16/18 (88.9%) |
| fails | spring (transcendental helix, K3) | both mitered sweeps |

forge builds both sharp-cornered sweeps OCCT's float pipe rejects;
OCCT builds the helix forge defers to K3. Disjoint failure sets,
forge ahead on count.

### The float-filter pass (this iteration)

The BSP predicates — plane `side()` and polygon degeneracy — are the
hot loop of every boolean. They ran in exact BigRational arithmetic,
whose cost explodes as intersection denominators grow (the chamfer
weakness). Added a **Shewchuk-style static float filter**: decide the
sign in `f64` with a forward-error bound, fall back to the exact
rational only when the float magnitude is within the bound of zero.
The answer is *always* the exact sign — the filter only skips slow
exact work on the unambiguous common case, verified by the oracle
suite staying bit-identical to ref.

Effect (chamfer, the target): **41.4 ms → 18.1 ms** (2.3×). But the
filter lives in *every* boolean, so the whole corpus sped up:
`torture_menger_1` **27.8→4.5 ms vs OCCT (6.2×)**, aggregate **1.8× →
3.5×**.

### Where it stands

- **Exactness now costs nothing on correctness and wins big on speed:**
  14 of 15 shared models are 2.7–41× faster than the OCCT wheel, at
  identical (exact) volumes.
- **The one remaining loss is honest and understood.**
  `chamfered_block` is still 2× slower — the corner-facet chamfer is a
  deep chain of exact boolean cuts producing large-denominator
  intersection *coordinates* (not just predicates), which the filter
  can't touch. Halving it (5×→2×) came free from the predicate filter;
  closing it fully needs lazy-exact *coordinates* (store a float +
  interval alongside each rational, recompute exact only on demand) —
  the next kernel technique, and a bigger refactor.
- **Bottom line:** the from-scratch exact kernel now beats the 30-year
  OCCT wheel on capability *and* is 3.5× faster in aggregate on this
  corpus, losing only where exact-coordinate growth is fundamental —
  a known, targetable frontier, not a wall.
