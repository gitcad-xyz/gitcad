# gitcad roadmap

The full feature map ahead, across both repos (this one and
[gitcad-xyz/forge](https://github.com/gitcad-xyz/forge)). Organized by
horizon, with dependencies and honest effort notes. Detailed per-domain
audits live in `docs/research/` (SolidWorks / KiCad / Fusion / Altium
feature maps, kernel coverage plan); execution history in the ADRs and
`forge/PLAN.md`. This document is the *forward* view.

Ground rules carried from CLAUDE.md: identity-semantics changes need
human sign-off; geometry-output changes are breaking; every kernel
stage either lands exact/certified or refuses by name.

Legend: **[K]** forge kernel · **[M]** mech · **[E]** ecad · **[X]**
cross-domain · **[G]** GUI/viewer · **[I]** infra/ecosystem ·
**(gated)** blocked on a user decision or external resource.

---

## Where things stand (2026-07-27)

**Released:** all six packages are live on PyPI at **0.9.8** (`gitcad`,
`gitcad-core`, `gitcad-mech`, `gitcad-ecad`, `forgekernel`, `forgekernel_rs`).
A clean `pip install gitcad==0.9.8` scores **340/345 (99%)** on the capability
matrix (`python -m gitcad.bench.capability --md`) — 0 honest gaps, 5 cells
permanently outside any exact field (each carries a transcendence proof; see
`docs/releases/0.9.7.md`), 0 crashes. Main and the release currently coincide
— the matrix run from the repo venv reports the same 340/345.

**0.9.8's headline is K7**: booleans over freeform NURBS solids — two lofted
solids in, one audited shell out, the volume reported as a certified interval
(a bracket proven to contain the true value, never a bare float), and
`mass_props` carrying provenance `exact` vs `certified ± e`. Verified from
the released wheels: the loft × loft flagship brackets its hand-derived
89/16 intersection at ±0.72, the dome cap brackets 1.0794724554159 at
±0.019, and the tangent-contact / operand-corner / mixed loft × planar
cases refuse by name. Bracket widths are O(2^-depth); loft × planar-Body
refuses (only PatchSolid × PatchSolid and loft × loft are assembled).
0.9.8 also shipped the SolidWorks-parity wave: direct editing
(move/offset/delete face + exact heal, recorded as replayable intent),
draft with face selection and parting lines, the blend family beyond one
radius, and the STEP border audit that refuses a lying `CLOSED_SHELL` with
a gap report in millimetres.

OCCT is gone entirely (ADR-0020): forge is the sole geometry kernel, and the
OCCT references below are to its former role as a differential oracle. Before
the cut, the from-scratch kernel beat the OCCT wheel on **five measured axes**:
capability (20/20 corpus vs 18/20), aggregate speed (5.5×), curved-
boolean accuracy, spring accuracy+speed (306×), and SSI branch-
completeness (finds tangential branches OCCT drops). Stages K1–K6.2
shipped: exact planar/quadric solids, certified intervals (ADR-0019),
NURBS eval, complete-branch SSI, exact STEP geometry import + planar
topology import, open/prism shells, selected-edge + corner fillets,
exact Gaussian curvature, G1/G2 continuity **proofs**, Coons patches,
self-certifying blend strips — and, in 0.9.8, the K7 freeform boolean
assembly itself. Rust carries the hot loops (BSP booleans,
NURBS eval, SSI detection, strip pruning), oracle-locked bit-identical
to the Python executable spec.

Platform: full mech+ecad feature surface (SW attack list P1–P8 and the
KiCad map are both complete), registry, semantic merge, requirements-
as-code, review tooling, viewer with zebra inspection.

---

## Horizon 1 — Now (the current arc: finish the kernel's honest edges)

### K7 — booleans over freeform NURBS solids **[K]** — *shipped in 0.9.8*
Solid booleans where faces are NURBS patches, released end to end in
0.9.8 (loft × loft included). What remains open, per the item notes
below: re-trim of boolean results, prism/tube patch-skin converters,
rational operands end to end, a watertight trimmed-patch mesher, and
the tube error bound for rational faces and open branches. The
`k7/closure-signoff` soundness upgrade to SSI closure classification
awaits sign-off and is not in the release.

- **✅ K7.0 — exact volume of a Bézier-patch-bounded solid** (done). The
  divergence-theorem flux `⅓∮ S·(S_u×S_v)` has a *polynomial* integrand,
  so the volume is an exact ℚ (interpolatory rational quadrature).
  OCCT-oracle-verified.
- **✅ K7.0b — exact inertia tensor** (done) via the same flux, one
  degree up; matches OCCT `MatrixOfInertia`, off-diagonals exactly zero.
- **✅ K7.0c — native STEP AP214 export** (done). Full product structure,
  OCCT reads forge's file back exactly. With the K3.4/K3.6 reader, forge
  round-trips STEP with no OCCT in the loop.
- **✅ Ordered SSI curve output** (done). `ssi.ssi_curves` chains the
  certified points into one parameter-space polyline **per branch**
  (branch = connected component of surviving cells in A's domain),
  ordered by nearest-neighbour with double-sweep endpoint seeding, and
  flags branches that close on themselves. Points stay exact ℚ; the
  ordering is a float render/report layer on top.
- **✅ Trimmed-patch representation** (done). `trim.TrimmedPatch` =
  surface + parameter-space trim loops (outer + holes), with exact
  signed/unsigned parameter-domain area (shoelace in ℚ), winding
  normalization (outer CCW, holes CW), and structural validation.
- **✅ Point-in-trimmed-region classification** (done). Exact even-odd
  ray parity in ℚ returning in / **on** / out — a boundary point is
  reported, never silently bucketed. No tolerance touches the topology
  decision (ADR-0019).
- **✅ Trimmed-patch volume via Green's theorem** (done). `bsolid.
  trimmed_patch_flux` reduces (1/3)∮∮_D S·(S_u×S_v) over a polygonal trim
  region D to contour integrals over the loop edges + a nested exact
  u-antiderivative — exact ℚ for polynomial patches. Validated three ways:
  equals the tensor-quadrature `patch_flux` on the full rectangle (two
  independent exact methods), additive over a triangulation, and holes
  subtract by orientation. `trimmed_solid_volume` sums it over a closed
  shell (box = 60 exactly); `TrimmedPatch.flux()` exposes it per face.
- **✅ Boolean-assembly volume reduction** (done, the volume half). Volume
  is Σ trimmed-face flux; proven invariant when a face is re-trimmed
  (split by an added edge) — exactly the operation a boolean performs.
  *Still open:* the full boolean topology build (classify + stitch the
  trimmed faces into the result shell), and — the honest caveat — the flux
  is exact for the given *polygon*, so a curved SSI trim carries the
  boundary's polyline-discretization error, not a rounding one.
- **✅ SSI branches → trim loops on BOTH parameter domains** (done).
  `ssi.ssi_trim_loops`: closed branches become loops directly; OPEN
  branches are stitched — each chain end extended to a residual-certified
  domain-border crossing (constrained Newton with the border value pinned
  exactly in ℚ), then closed with border segments and the patch corners
  passed on a CCW border walk. The loops read the SAME certified chain in
  A's (u,v) and B's (s,t), so both describe one 3D curve. A branch that
  cannot be stitched (endpoint strictly interior to either domain, or an
  uncertifiable border crossing) refuses by name (`TrimLoopUnstitchable`)
  — never a guessed loop. Verified on the dome∩half-space closed loop
  (cap volume converging second-order to the 1.079472 reference) and an
  open ridge×plane pair whose assembled volume hits the closed form
  16√3/9 to 4e-15.
- **✅ Exact partition of a face's parameter domain by trim loops**
  (done). `trim.split_trim_region`: the domain border and loop edges are
  split at all incident vertices into an exact planar subdivision and the
  faces traced with exact orientation predicates (half-plane + cross-sign
  angular order — no floats). Returns polygon-with-holes regions in the
  `TrimmedPatch` convention; crossing loops refuse by name; an exact
  Σ-areas == domain-area audit runs before returning. Handles interior
  loops (holes), nested loops, and border-touching stitched loops, and is
  independent of which side each stitched loop happened to enclose.
- **✅ The boolean assembly** (done — the crown piece). `bsolid.
  boolean_trimmed(op, A, B)`: per face-pair SSI → certified trim loops →
  exact domain-partition audit → certified ray-parity membership of every
  strip-free fragment (one raycast per connected component of the strip's
  complement — membership is constant there by the enclosure property) →
  stitch into an audited `TrimmedShell`. Orientation is PRINCIPLED, not
  enumerated: operand faces are preflighted outward (Σ flux > 0 exact) and
  the result's sense follows from membership monotonicity — union/
  intersect keep every face's own outward normal, cut flips B's
  (A ∩ ¬B is decreasing in B); a loop-role mistake provably cannot ship a
  wrong shell (measures never read roles; pairing refuses a single flip
  and a double flip is a no-op). Volume is a `CInterval` ("certified ± e"),
  exact-width when nothing is trimmed. Verified end to end on
  pillow∩box = the stage-1 cap (bracket contains 1.0794724554159, halving
  per depth), union and cut with the conservation identities
  vol(A)+vol(B) ∈ vol(∪)+vol(∩) and vol(A) ∈ vol(−)+vol(∩) in intervals,
  and MC membership spot-checks with certified signs. Refuses BY NAME:
  tangent contact, open/stitched branches (their border segments await
  pairing with operand seam edges), rational/multi-span/inward operands,
  unresolved regions, empty result. Seam: `RefKernel.boolean` dispatches
  PatchSolid × PatchSolid; `mass_props` reports midpoint +
  `volume_halfwidth`, provenance `"certified"`; `validate` re-runs the
  three-oracle audit; tessellate/bbox/measure refuse by name until the
  trimmed-patch mesher (shared with K3.7) lands. *Still open:* booleans of
  already-trimmed results (re-trim), loft/prism/tube patch-skin
  converters, open-branch assembly, rational operands end to end.
- **✅ Loft skin + the open-branch loft × loft boolean** (done — the
  flagship). `LoftSolid.to_patches()`: the loft's EXACT Bézier skin —
  walls degree (1,3) straight from the natural-spline coefficients, caps
  planar — whose flux volume equals the loft's own `∫A(v)z′(v)dv` as one
  rational (two independent exact pipelines; pinned on 1668/35, 2582/35).
  Convex-quad skins carry seam topology PROVEN by exact 3D control-point
  equality (`PatchSolid.seams`). On top of it, OPEN branches landed in
  `boolean_trimmed` — forced by the flagship, since two z-fibered lofts
  can never meet in a closed single-face-pair loop: `ssi.ssi_chains`
  returns certified chains with exactly-classified border-crossing ends;
  every seam crossing is canonicalized (one certified solve, transferred
  to the adjacent face through the seam's exact control-point equality —
  one `TrimVertex` bound to three faces); chains glue across the other
  operand's seams; `trim.split_domain_by_paths` partitions a face by
  border-anchored paths; kept faces carry full border loops so the exact
  pairing audit closes over seam edges. Verified on barrel(2582/35) ×
  slab(12): intersect bracket contains the hand-derived 89/16, union/cut
  contain their closed forms, interval conservation identities hold,
  certified-MC membership agrees at 6 points × 3 ops, and any operand
  without proven seams still refuses `open_branch` by name. Seam:
  `RefKernel.boolean` converts LoftSolid operands via `to_patches` (loft
  × loft returns "certified ± e" through `mass_props`); `tessellate` on a
  `TrimmedShell` is now the CERTIFIED-SAFE view (`tess.
  trimmed_shell_mesh`): only certain-membership cells are meshed, the SSI
  strip shows as explicit gap quads, provenance `"render"`. *Still open:*
  re-trim of results, prism/tube skins, rational operands, fan-cap
  (non-quad-section) lofts in the open-branch path, a watertight
  trimmed-patch mesher.
- **✅ Bracket tightening — the second-order tube bound** (done). Three
  stage-1/2 limits closed at once (`forgekernel/tube.py`). (1) A boolean
  face's flux is now the EXACT polygon flux over its certified trim
  loops ± a tube error built from what SSI already certifies: a
  transversality anchor δ = residual/σ (σ from a 4·det/trace² singular-
  value bound over hodograph hulls), a tangent cone whose chord
  components are hulled as exact B-forms (`D_u = n_other·H_u` — the
  near-cancellation survives), a two-ended ramp area bound, and a Band
  flood-fill audit that verifies polygon parity against certified
  membership per Band-free component (pockets are priced, not guessed).
  Chord-halving via extra residual-certified midpoints (`tube_refine`)
  halves the error per round. Dome cap at depth 5: width 2.04 → 0.038
  default, ±2.2e-3 at `tube_refine=5` — the hand pipeline's error scale,
  now with a rigorous bar; converges O(h²) per depth (d6: ±2.0e-3 at
  r3). `TrimmedShell.volume` intersects tube and strip brackets
  (disjointness = proven contradiction → audit error); positivity now
  certifies at depth 4. (2) Certified B-side strip prune: `ssi_chains`
  returns strips where every dropped cell is PROVEN empty (swapped-role
  subdivision exclusion, Rust hot loop with the Python path as spec) —
  the measured 3× B-side inflation (228→76 cells on dome×plane) is gone,
  and the boolean runs one SSI detection instead of two. (3) Dyadic
  snapping: closed-loop vertices snap to the 2^-(2·depth+10) grid
  (denominators 2^20 vs ~1e12), snap distance folded into the tube pads
  — enclosures stay enclosures. Rational leaves upgraded too: the
  Neumann rule 1/Q = 2/qm − Q/qm² + (Q−qm)²/(qm²Q) with the P·Q product
  form subdivided alongside makes `patch_flux_ci` second order — quarter
  cylinder at depth 5: width 0.375 → 0.0147. Documented premise (same
  residual class as chain ordering): one branch pass per covered cell
  set; guarded by the one-signed cone, coverage fixpoint, and the strip
  intersection. *Still open:* the tube path for rational faces and open
  branches (falls back to the strip bracket by name), a Rust port of the
  hull descent (pure-Python cost ~4 s at depth 5 default).

### K3.7 — the freeform import gap **[K]**
- Freeform STEP **topology**: trimmed `ADVANCED_FACE` over B-spline
  surfaces → importable freeform solids (consumes K7's trimmed-patch
  type). This is the real-world STEP round-trip for SolidWorks exports.
- **✅ Smooth (spline-fit) multi-section lofts** (done). Natural cubic
  spline through the section rows (exact ℚ tridiagonal solve); `LoftSolid`
  returns **exact volume AND exact centroid** by polynomial integration of
  the shoelace area, its Qx/Qy area-moments, and z·A per spline segment.
  Along the way, fixed a latent bbox-centre-as-centroid approximation in
  both `LoftSolid` and `SplinePrism` — now both give the true first-moment
  centroid in ℚ (spline-prism oracle-checked against OCCT). Full B-spline
  *surface* skin still pending the trimmed-topology assembly above.
- Sign-varying rational weights in SSI (rare in practice; low priority).

### K5.2 / K4.2 — blend & offset edges **[K]**
- ✅ `fillet(all)` on rectilinear right prisms (`FilletedPrism`, exact in
  ℚ[π]) — released (the prism × fillet(all) cell is green in the 0.9.8
  wheels' matrix). Arbitrary (non-rectilinear) prism edge frames still
  open.
- Two-edge corner blends (the genuinely non-spherical patch) — likely
  certified rather than exact.
- Variable-radius fillet along an edge (linear r(t): exact volume by
  integral of r(t)²; still ℚ[π]).
- Certified insets for non-Pythagorean prism shells (CInterval normals);
  non-convex profiles (straight-skeleton style splitting).
- FilletedBox / open-shell tessellation for the viewer.

### Chamfer's last 2× **[K]** — bbox-culled boolean cutting
The one corpus loss. Localized cutting: only re-clip faces the tool's
bbox touches. A real BSP change; do it in Rust where the engine lives.

---

## Horizon 2 — Near (platform features on top of the kernel)

### Kernel promotion **[K][I]** — **✅ done, then superseded**
The `auto` backend (forge-first, OCCT fallback) shipped, and then
ADR-0020 removed OCCT outright — `forge` is the *only* kernel; a
refusal is now surfaced honestly instead of backfilled. `forgekernel`
and `forgekernel_rs` are published on PyPI (0.9.8).

### Native STEP **export** from forge **[K]** — **✅ done**
`stepio.write_step_planar_solid`: AP214 planar-solid export with full
product structure; OCCT reads forge's file and volumes match (box 72,
non-convex L-prism 4800). With the reader, forge round-trips STEP with
no OCCT in the loop. Remaining: B-spline-surface faces once K7 trimmed
topology lands.

### Validation gauntlet **[K]** — *partial*
- ✅ Volume-identity fuzzing: `V(A∪B)+V(A∩B) == V(A)+V(B)` holds EXACTLY
  over random box pairs — a decidable correctness net (exact kernel), not
  a tolerance check. (done)
- ⏳ ABC dataset sample census, NIST/CAx-IF conformance files
  (**gated**: dataset download).
- **✅ SSI certified-residual fuzzing** over random Bézier patch pairs
  (done). 40 seeded random bilinear graph-patch pairs; every certified
  point provably lies on both graphs (residual < 1e-18 ⇒ parameters agree),
  plus operand-symmetry of the branch count. Exercises the hit and the
  certified-empty paths.

### Cross-kernel identity stability **[I]** — **(gated: human sign-off)**
Entity ids are minted per-kernel today (fingerprints differ across
backends), which blocks id-referencing corpus models and cross-kernel
document portability. Design: kernel-independent descriptors (lineage +
quantized geometric invariants). Touches ADR-0003 — *identity semantics
change, requires human approval before implementation.*

### GUI: the curvature loop **[G]**
- Curvature-comb overlay for sketches/curves (kernel data exists:
  `curve_curvature_comb`).
- Smooth vertex normals option so zebra reads surface quality rather
  than facet quality at low tessellation.
- K-map coloring: sample exact Gaussian curvature over imported
  freeform faces, color-ramp in the viewer (`#kmap`).
- Section-curve display from SSI results.

### ECAD deepening **[E]**
- ngspice install → live sim tests un-skip; AC + transient analyses in
  `sim_check`; operating-point back-annotation onto sheets. **(gated:
  install choice)**
- Differential pairs: paired routing in `route()`, length-match checks
  by class, skew report.
- Impedance profiles: stackup-aware Zo calculation per net class
  (microstrip/stripline closed forms), DRC-checkable.
- IPC-D-356 physical tester run **(gated: hardware)**; Eagle board
  geometry import; Altium binary via KiCad migration remains the path.

### Mech deepening **[M]**
- Sheet metal: curved flanges (cylindrical bend segments — exact in
  ℚ[π] with the existing quadric machinery), cross-breaks, gussets.
- Fastener generator: nut/washer stacks, thread engagement checks.
- Patterns: sketch-driven and curve-driven patterns.
- Weldment/frame profiles (structural members along sketch lines).

---

## Horizon 3 — Later (strategic bets)

### The surfacing suite completed (K6.3+) **[K]**
- 4-sided G1 fill networks (Coons + blend-strip composition with
  certified corner compatibility).
- G2 blend strips (quintic Hermite; same separate-proof pattern).
- Trim/untrim/knit as first-class ops.
- The stated end goal: import SolidWorks surfacing exercises and pass
  a "complex surfaces demo" gate with proofs OCCT can't offer.

### K8 — variational/parametric frontier **[K][M]**
- 3D constraint solving (assembly-level DOF analysis on mates).
- Direct editing: push/pull faces with exact re-solve where possible.
- History-free import editing (feature recognition already recovers
  holes; extend to fillets/shells/patterns).

### Agent platform **[I]**
- Night Shift (ADR-0011): scheduled autonomous improvement runs with
  the Tier system + circuit breakers. **(gated: user opt-in)**
- Accountless contribution relay (ADR-0012). **(gated: Cloudflare
  account)**
- Registry trust tiers + attestation tooling; more seeded parts.
- Bug-loop hardening: delta-reduction pipeline exercised end-to-end on
  synthetic reports.

### Ecosystem **[I]**
- ✅ `pip install gitcad` is live — six packages on PyPI at 0.9.8,
  including `forgekernel` and the `forgekernel_rs` native build.
- Docs site: task-oriented guides (import your SW parts, route a board,
  verify a release), kernel whitepaper from the bench data (the
  five-axes story is publishable).
- Examples gallery: the Altair project as the flagship walkthrough.

### Simulation & analysis **[X]**
- ✅ Exact inertia tensors (done in `bsolid.mass_properties` — full
  tensor as exact rationals; OCCT `MatrixOfInertia` differential).
  Remaining: surface it through the seam/`mass_props` for all solid
  classes and a `model_inertia` MCP tool.
- Thermal envelope pass (power budget → per-component dissipation →
  board copper-area heuristic checks).
- Clearance/creepage electrical-mechanical co-checks (voltage-aware
  spacing DRC using envelope data).

---

## Standing gates (user decisions needed)

| item | needs |
|---|---|
| ~~PyPI publication (`gitcad`, `forgekernel`)~~ | done — all six packages live at 0.9.8 |
| release tags (`vX.Y.Z` publish trigger) | user call, per release |
| Cloudflare relay (ADR-0012) | user CF account |
| Night Shift autonomous runs | explicit opt-in + quota |
| ngspice live simulation | install approval |
| IPC-D-356 tester conformance | physical hardware |
| cross-kernel identity redesign | ADR-0003 human sign-off |
| 1.0 version cut | user call (policy: hold at 0.x patch bumps) |

---

*Maintained by the agent loop; every claim of "done" above corresponds
to a commit + test + (where cross-kernel) an oracle differential. When
this document and reality disagree, fix this document.*
