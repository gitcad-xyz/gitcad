# Native kernel: full coverage & functionality plan (ADR-0018)

The parity bar is the existing `Kernel` seam — every method the OCCT
backend implements today, verified differentially against OCCT on the
corpus. This document is the complete coverage matrix, the staged
milestones with acceptance gates, and the verification harness that
drives the schedule.

## 0. The three-oracle chain

```
ref (Python, exact rationals)  = executable spec, correctness oracle
  ⇄ differential vs occt      = independent 30-year-hardened check
forge (Rust port, later)       = production speed; ref is its oracle
```

Disagreement triage: if ref and OCCT disagree, exactness usually wins
— but every disagreement is investigated and recorded (some will be
genuine OCCT bugs on our corpus; those become torture-corpus entries
and marketing material).

## 1. Coverage matrix — the seam contract, stage by stage

Status key: each row must reach ✅ in `ref` (exact or bounded-error),
with scorecard green vs OCCT, before its class cuts over.

### Stage K1 — exact planar core (the topological proof)
| Seam method | ref approach | oracle test |
|---|---|---|
| `box` | exact polyhedral B-rep | volume/bbox/topology counts exact |
| `transform` (rigid) | exact rational matrices (rotations of 90° exact; arbitrary angles bounded) | mass-props delta ≤ 1e-9 rel |
| `scale` | exact | volume scales by f³ exactly |
| `boolean` union/cut/intersect on planar solids | exact plane-based BSP/face-splitting classification; NO epsilons | volume additivity identity; diff vs OCCT ≤ 1e-9 rel; watertight; Euler check |
| `extrude` (line-segment profiles) | exact prism | volume = area × h exact |
| `mirror` | exact | mass-props parity |
| `compound` | trivial | count parity |
| `bbox`, `mass_props`, `measure`, `validate` | exact integrals over planar faces (divergence theorem on polygons) | closed-form + OCCT parity |
| `entities` (planar faces/line edges) | native descriptors incl. lineage | descriptor-set parity with OCCT enumeration |
| `tessellate` (planar) | triangulate faces (ear-clip, deterministic) | watertight mesh, volume-of-mesh ≈ volume |
| `pattern_*`, `split`, `rib`, `engrave`, `boss`, `hole` (square cases) | compositions — free once boolean lands | doc-level parity runs |

Gate G1: the polyhedral subset of the corpus (boxes, plates, brackets,
sheet-metal solids) builds on `ref` with scorecard fully green.

### Stage K2 — quadrics + torus (most of real mech)
| Capability | ref approach | oracle test |
|---|---|---|
| `cylinder`, `sphere`, `cone` primitives | exact analytic surface types | closed-form mass-props exact |
| plane–quadric, quadric–quadric intersections | closed-form curve classes (lines, circles, ellipses, quartics as exact algebraic curves with certified parameterization) | branch-completeness vs constructed ground truth; OCCT diff |
| booleans over quadric solids | classification via exact algebra where possible, certified intervals elsewhere | volume identity + OCCT diff ≤ 1e-7 rel |
| `revolve`, arc profiles in `extrude` | analytic | volume closed-form |
| `hole` (all variants), `fillet`/`chamfer` on **linear edges** | chamfer = planar cut (exact); cylindrical fillet on straight edges = quarter-cylinder patch | volume deltas closed-form |
| `helix`, `pipe` (circular section) | procedural sweep surface, bounded-error eval | volume vs analytic wire-length formula |
| `draft` on planar faces | plane re-tilt, exact | volume monotonicity + OCCT diff |
| `hlr_project`, `section_polys` | analytic silhouettes/sections for planes+quadrics | drawing overlay diff vs OCCT rasters |
| `export_stl`/`export_step` (planar+quadric) | native writers (STEP AP214 subset: analytic surfaces) | round-trip through OCCT import; volume parity |

Gate G2: ≥80% of the full gitcad corpus (measured, not asserted)
builds on `ref` scorecard-green. `ref` promotes to default backend
for the classes it covers (OCCT auto-fallback for the rest).

### Stage K3 — NURBS + general SSI (the crown jewel; longest stage)
| Capability | approach | oracle test |
|---|---|---|
| NURBS curve/surface eval + arithmetic | interval-certified de Boor; exact rational control points | eval parity vs OCCT ≤ 1e-10 |
| **General SSI** | subdivision + Bézier-clipping *complete* branch detection, then certified marching (interval Newton) per branch | branch-count ground truth on constructed cases; torture corpus; OCCT diff (expect to BEAT occt on completeness) |
| booleans over NURBS solids | SSI + certified point classification | corpus + fuzz volume identities |
| `loft`, `sweep` (general path), imported STEP free-form | native | mass-props diff vs OCCT; SW-exported STEP round-trips |
| `import_step`/`export_step` full | complete AP214/AP242 geometry | corpus round-trip parity |

Gate G3: full STEP corpus builds; SSI branch-completeness 100% on the
torture corpus (where OCCT's own score, measured in stage 0, will not
be 100% — that is the differentiation moment).

### Stage K4 — offsets, shell, thicken
Procedural offset surfaces (lazy, exact-definition), self-intersection
trimming via SSI. Gate: shell success rate ≥ OCCT's on corpus, wall
thickness verified by sampling.

### Stage K5 — blends (the SolidWorks-parity milestone)
Rolling-ball constant → variable radius → G2 curvature-continuous;
setbacks and corner patches. Built on K3 SSI + K4 offsets. Gate:
fillet completion rate on the fillet corpus > OCCT (measured today:
OCCT fails a documented subset), G2 verified by curvature sampling.

### Stage K6 — surfacing suite (the stated end goal)
Boundary/fill surfaces with G1/G2 edge constraints, trim/untrim/knit,
curvature analysis (combs, zebra projections in the viewer). Gate:
the "complex surfaces" demo corpus (imported SW surfacing exercises)
round-trips visually and metrically.

## 2. The harness (kernel-independent; built first)

`scripts/kernel_scorecard.py`:
- walks the corpus (repo examples + registry parts + imported STEP +
  torture directory), builds every model on any named backend,
- emits per-model JSON: build ok, wall time, volume/area/bbox,
  face/edge counts, watertightness, and — when two backends are named
  — the deltas,
- aggregates a scorecard per operator class (which ops the model uses
  comes from its feature list — free, since documents are text),
- runs in CI; the dashboard number IS the kernel schedule.

Calibration step (now): occt-vs-occt (must be all-zero deltas), then
occt-alone baseline — quantifying today's failure surface on our own
models before a line of `ref` exists.

**Benchmark discipline (owner requirement: "show we are actually
improving").** Every scorecard run is a dated JSON snapshot committed
under `bench/` — per backend: capability score (% of corpus green,
broken out per operator class), robustness score (torture-corpus pass
rate — the axis where beating OCCT must become visible), correctness
deltas vs oracle, and wall-time per op class. `bench/TREND.md` is
regenerated from the snapshots: backend × metric over time, so any
release can state "ref covers N% of the corpus, beats OCCT on M
torture cases, at K× the runtime" with the receipts in git history.
OCCT's own baseline is measured, not assumed — improvement claims are
always relative to a number in the repo.

**The gauntlet (acid tests).** No public industry standard exists for
B-rep robustness (vendors' real acid suites are proprietary), so the
corpus carries our own, staged to the roadmap: K1 planar killers
(Menger sponge level-1 — five chained booleans, coincident internal
faces, exact answer 20/27·cube; coincident-face unions; float-precision
slivers), K2 quadric killers (tangent cylinders, cone-apex-on-face,
sphere-tangent-plane), K3 SSI killers (near-tangent surface pairs,
ABC-dataset imports), K5 blend corners. Public resources adopted at
their stages: NAS 979/ANC-101 (feature coverage), NIST MBE PMI CTC/FTC
(STEP/PMI gates), CAx-IF round-robin files, ABC dataset slices (bulk
robustness at K3).

Fuzz lane: random CSG programs (bounded depth) with invariant checks
(volume additivity, boolean algebra identities, watertightness) — runs
nightly against whichever backends exist.

## 3. Workstreams & immediate execution order

1. **W0 harness** — scorecard + corpus assembly + OCCT baseline. No
   kernel code. Starts immediately.
2. **W1 ref-core** — `packages/gitcad-ref/` (pure Python, stdlib
   `fractions.Fraction`): exact linear algebra, plane-based polyhedral
   B-rep, the K1 table. Registered as backend `ref` behind the seam.
3. **W2 quadrics** — K2 table.
4. **W3 forge bootstrap** — Rust workspace + pyo3, porting K1 verbatim
   with `ref` as its oracle (starts once K1 is stable, in parallel
   with W2).
5. **W4 SSI research track** — torture-corpus assembly and the
   subdivision/clipping prototype, feeding K3.

Rules of the road (constitution addenda for kernel work):
- Every `ref` operator lands with: property tests, closed-form cases,
  and a scorecard entry. No operator merges on "looks right".
- OCCT-vs-ref disagreements are ISSUES with the model attached, never
  silently resolved toward either side.
- The seam Protocol is updated first whenever an op is added (the
  newer ops — scale, draft, helix, pipe — must be added to the
  Protocol as part of W0).
