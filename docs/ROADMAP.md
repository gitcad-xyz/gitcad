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

## Where things stand (2026-07-23)

The from-scratch kernel beats the OCCT wheel on **five measured axes**:
capability (20/20 corpus vs 18/20), aggregate speed (5.5×), curved-
boolean accuracy, spring accuracy+speed (306×), and SSI branch-
completeness (finds tangential branches OCCT drops). Stages K1–K6.2
shipped: exact planar/quadric solids, certified intervals (ADR-0019),
NURBS eval, complete-branch SSI, exact STEP geometry import + planar
topology import, open/prism shells, selected-edge + corner fillets,
exact Gaussian curvature, G1/G2 continuity **proofs**, Coons patches,
self-certifying blend strips. Rust carries the hot loops (BSP booleans,
NURBS eval, SSI detection), oracle-locked bit-identical to the Python
executable spec.

Platform: full mech+ecad feature surface (SW attack list P1–P8 and the
KiCad map are both complete), registry, semantic merge, requirements-
as-code, review tooling, viewer with zebra inspection.

---

## Horizon 1 — Now (the current arc: finish the kernel's honest edges)

### K7 — booleans over freeform NURBS solids **[K]** — *the crown assembly*
The one big kernel capability not yet attempted: solid booleans where
faces are NURBS patches. Everything it needs now exists — SSI with
complete branch detection, Bézier extraction, exact point classification
machinery.

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
- ⏳ Trimmed-patch volume via Green's theorem over trim loops, then the
  boolean assembly. *Hard — the remaining freeform frontier.* Corpus
  model + OCCT differential (expect to *win* near tangency). Note: the
  trimmed *surface* measure is not exact while trim curves are polyline-
  approximated in parameter space — that gap is this bullet, kept honest.

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
- Fillets on arbitrary straight prism edges (not just boxes) — same
  quarter-cylinder math, general edge frames.
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

### Kernel promotion **[K][I]** — **✅ auto-backend done**
`forge` is now the *default* via the `auto` backend (forge-first, OCCT
fallback on honest refusal; builds 100% of the corpus with the exact
kernel in front). Remaining: publish `forgekernel` wheels on PyPI
(**gated**: PyPI name approval still pending).

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
- ⏳ SSI certified-residual fuzzing over random Bézier patch pairs.

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
- `pip install gitcad` (**gated: PyPI approval**) and `forgekernel`
  wheels (win/mac/linux CI builds via maturin).
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
| PyPI publication (`gitcad`, `forgekernel`) | name approval (pending since 2026-07-22) |
| Cloudflare relay (ADR-0012) | user CF account |
| Night Shift autonomous runs | explicit opt-in + quota |
| ngspice live simulation | install approval |
| IPC-D-356 tester conformance | physical hardware |
| cross-kernel identity redesign | ADR-0003 human sign-off |
| 1.0 version cut | user call (policy: hold at 0.7.x) |

---

*Maintained by the agent loop; every claim of "done" above corresponds
to a commit + test + (where cross-kernel) an oracle differential. When
this document and reality disagree, fix this document.*
