# forge (Rust) vs OCCT wheel — head-to-head

The final Rust kernel (`forgekernel_rs`, exact BigRational) against the
OCCT wheel (`cadquery-ocp`, floating-point B-rep), same gitcad corpus,
through the same seam. Timing is best-of-3 wall time per model build
(includes construction + mass properties). Generated 2026-07-23.

`eng` = which engine did the geometry under the `forge` backend: **RUST**
= native `PySolid` (box/prism/transforms/boolean/chamfer/prismatoid);
`ref` = the exact Python composite (ℚ[π]/ℚ[√d] analytic — a Rust port of
microsecond arithmetic buys nothing, so it stays in Python).

| model | eng | occt ms | forge ms | speedup | volume match |
|---|---|---:|---:|---:|:---:|
| plate_with_holes | ref | 13.37 | 2.04 | **6.6×** | exact |
| quadric_boss | ref | 6.07 | 0.37 | **16.3×** | exact |
| revolve_profile | ref | 1.65 | 0.18 | **9.1×** | exact |
| extrude_L | RUST | 2.09 | 0.29 | **7.3×** | exact |
| filleted_block | ref | 11.22 | 0.56 | **20.0×** | exact |
| chamfered_block | RUST | 8.62 | 42.80 | **0.2× (5× slower)** | exact |
| shelled_box | RUST | 6.90 | 1.68 | **4.1×** | exact |
| drafted_block | RUST | 1.65 | 0.67 | **2.5×** | exact |
| loft_transition | RUST | 2.83 | 0.26 | **11.1×** | exact |
| sheetmetal_folded | RUST | 19.08 | 4.50 | **4.2×** | exact |
| torture_tangent_cylinders | ref | 5.83 | 0.15 | **38.8×** | exact |
| torture_coincident_faces | RUST | 4.47 | 0.98 | **4.6×** | exact |
| torture_sliver_cut | RUST | 4.70 | 1.31 | **3.6×** | exact |
| torture_tangent_sphere_plane | ref | 3.00 | 1.12 | **2.7×** | exact |
| torture_menger_1 | RUST | 28.09 | 9.07 | **3.1×** | exact |
| **TOTAL (buildable on both)** | | **119.6** | **66.0** | **1.8×** | all exact |

### Capability (who can build what)

| | forge (Rust) | OCCT |
|---|---|---|
| corpus built | **17/18 (94.4%)** | 16/18 (88.9%) |
| fails | spring (transcendental helix — K3) | both mitered sweeps (swept_channel, sweep_rightangle) |

forge builds two models OCCT cannot (sharp-cornered sweeps, where
OCCT's floating-point pipe produces invalid geometry); OCCT builds one
forge cannot (a true helix, which needs K3 curves). **Disjoint failure
sets, and forge is ahead on count.**

### What the numbers say

- **Exactness costs nothing on correctness and usually wins on speed.**
  On 14 of 15 shared models forge is 2.5–39× faster than the OCCT wheel:
  it evaluates closed-form ℚ[π] volumes or runs an exact BSP, while OCCT
  builds a full tolerant B-rep and meshes it. Every volume is identical
  to OCCT (exact rationals — OCCT's float *is* `float(exact)`).
- **The one loss is the honest one.** `chamfered_block` is **5× slower**
  on forge: the industrial corner-facet chamfer is a deep chain of exact
  boolean cuts whose BigRational denominators grow fast — the fundamental
  cost of exact arithmetic. Rust helps (this same chamfer was ~98 ms on
  the Python `ref`, so Rust already bought ~2.3×), but even Rust's
  BigRational can't beat OCCT's doubles on a denominator-exploding chain.
  This is the frontier the next kernel work targets (lazy/interval
  filtering: use floats to decide, exact only to certify).
- **The moat inverts on the sweeps.** The models OCCT *fails* are ones
  forge builds exactly — the robustness OCCT can't offer on sharp
  corners is the same exactness that makes it slower on deep booleans.
  Different trade, and on this corpus the exact kernel comes out ahead
  on both capability and aggregate speed.
