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
machinery. Plan:
1. Ordered SSI curve output (chain certified points into parameter-space
   polylines per branch; Rust marching). *Small.*
2. Trimmed-patch representation: a patch + parameter-space trim loops
   (SSI curves + boundary segments). *Medium.*
3. Point-in-trimmed-region classification (exact ray parity in parameter
   space). *Small.*
4. Volume of a freeform solid via the divergence theorem over trimmed
   patches — certified quadrature (interval-bounded), not float. *Hard;
   the honest version is a certified interval, per ADR-0019.*
5. Corpus model + OCCT differential (expect to *win* on tangential
   cases; OCCT booleans notoriously fail near tangency).

### K3.7 — the freeform import gap **[K]**
- Freeform STEP **topology**: trimmed `ADVANCED_FACE` over B-spline
  surfaces → importable freeform solids (consumes K7's trimmed-patch
  type). This is the real-world STEP round-trip for SolidWorks exports.
- Smooth (spline-fit) multi-section lofts: cubic B-spline interpolation
  through section rows (exact tridiagonal solve), surface exact; solid
  volume certified once K7 lands.
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

### Kernel promotion **[K][I]**
Make `forge` the *default* gitcad backend for the classes it covers
(ADR-0018 gate G2 was crossed long ago), with OCCT auto-fallback for
the rest. Needs: shadow-run vs the model corpus per the ADR's
architecture-change protocol, plus `forgekernel` wheels on PyPI
(**gated**: PyPI name approval still pending for `gitcad` itself).

### Native STEP **export** from forge **[K]**
The reader exists; the writer closes the loop: AP214 subset (planar +
B-spline geometry, MANIFOLD_SOLID_BREP topology). Oracle: OCCT imports
forge's file and volumes match. Unlocks OCCT-free CAD exchange.

### Validation gauntlet **[K]**
- ABC dataset sample (10k STEP models): batch-import census — % parsed,
  % topology-imported, failure taxonomy. The public acid test.
- NIST MBE / CAx-IF STEP conformance files.
- Fuzzing: random Bézier patch pairs through SSI with certified-residual
  invariants; random booleans with volume-identity invariants
  (V(A∪B)+V(A∩B) == V(A)+V(B) — exact, so violations are hard proof).

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
- Mass-properties-driven checks are done; next: exact moments of
  inertia through the seam (forge can do these exactly for its solid
  classes — extend mass_props to the full inertia tensor).
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
