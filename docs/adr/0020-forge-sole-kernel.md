# ADR-0020 — forge is the sole geometry kernel; OCCT is removed

Status: accepted (2026-07-24)
Supersedes the OCCT-fallback and the OCCT leg of the three-oracle chain in
[ADR-0018](0018-native-kernel.md). The exactness charter (ADR-0018/0019)
stands unchanged.

## Context

ADR-0018 introduced forge (the native, exact-arithmetic B-rep kernel) behind
the `Kernel` seam and kept OCCT (`cadquery-ocp`) for two jobs:

1. **A jump-start / fallback** — build the operations forge had not yet
   implemented, so the product worked before the kernel was complete.
2. **An independent oracle** — the differential half of the three-oracle chain
   (`ref` ⇄ OCCT ⇄ Rust), cross-checking forge's answers against a
   30-year-hardened kernel.

Both jobs have largely retired themselves:

- forge now covers the corpus end to end — planar and quadric solids, NURBS
  surfaces and complete-branch SSI, offsets, blends, lofts, exact mass
  properties, tessellation, and native STEP read/write (K1–K7). A default
  install already runs forge-first (ADR-0018 promotion, wired in `get_kernel`).
- The last capability OCCT was load-bearing for in the *default* path was
  hidden-line removal (`HLRBRep`) behind 2D drawings — now replaced by native
  forge HLR + section curves (`forgekernel.hlr`).
- But OCCT was *also* silently backfilling a tail of operations forge does not
  yet reach (it was the `AutoKernel` fallback for source-free ops, and the
  forced backend for a handful of drawing/import sites). Cutting it converts
  those from "works via floats" to an honest, stage-named refusal. That
  capability delta is real and is enumerated below rather than hidden.

Meanwhile OCCT carries real costs: a large LGPL-2.1 binary wheel (install
weight and a license obligation), C-level stdout that corrupts the stdio MCP
stream, and a second geometry representation to convert to and from. Keeping a
whole kernel for one feature is the wrong trade once forge can do that feature.

## Decision

**Remove `cadquery-ocp`. forge becomes the sole geometry kernel.**

1. **Native forge HLR + section curves.** Add hidden-line removal and section
   curves to forge (`forgekernel.hlr`): exact straight edges for planar solids
   (`logical_edges`), sampled rim circles + silhouette generators for cylinders,
   and sharp + view-dependent silhouette edges from the tessellation for the
   rest; occlusion by a hole-respecting inside-classifier (planar parity,
   drilled = base-parity AND-NOT bores, else tessellation parity). `section_polys`
   returns the cut-plane ∩ solid-surface curves in the same sheet frame, so a
   section view's outline overlays its projection exactly. Visibility is a
   display property, not a topological decision, so — under the exactness charter
   — it may use floats; the geometry it draws is still the exact solid. The
   drawing engine consumes projected 2D segments from the kernel seam rather
   than calling any kernel-specific projector.

2. **`get_kernel` is forge or nothing.** The default is `RefKernel` (forge);
   the only fallback is `NullKernel` (structure-only, honest about not checking
   geometry). `OcctKernel` and `AutoKernel` are deleted; `require="occt"` is
   removed.

3. **The oracle leg retires.** forge-vs-OCCT differential tests are converted
   to forge-native invariants or deleted. forge's correctness now rests on the
   three checks it already carries and controls:
   - exact-ℚ invariants (a decidable answer, not a tolerance) — the real spec;
   - `ref` (Python) ⇄ Rust bit-identity — an independent re-implementation;
   - property fuzzing — volume-identity `V(A∪B)+V(A∩B)=V(A)+V(B)`, SSI
     certified-residual, and additivity/partition identities.

4. **STEP is forge-native** (already true via `forgekernel.stepio`); no OCCT in
   any import/export path.

## Consequences

- **Lighter, unencumbered install.** `pip install gitcad` no longer pulls a
  ~hundreds-of-MB LGPL wheel; the whole stack is Apache-2.0 + the exact kernel.
- **No stdio corruption.** With no OCCT, the MCP server has no C-library banner
  to leak onto the JSON-RPC stream (the redirect stays as defense-in-depth).
- **We lose the independent oracle.** This is the real cost: the differential
  against a foreign kernel is gone. Mitigation is (3) above — invariants, the
  ref/Rust cross-check, and fuzzing are internal but decidable and do not
  depend on trusting a float answer. New exact-math still gets an adversarial
  review pass (the established practice).
- **Drawing quality shifts.** Native HLR draws exact straight edges exactly;
  curved silhouettes and circular edges are polyline-approximated at the
  tessellation deflection. Good enough for engineering drawings now; an exact
  per-primitive edge path (clean arcs/ellipses) is a later refinement, not a
  blocker.
- **`gitcad[occt]` extra is removed.** Any lingering OCCT-only feature that
  cannot be reforged is dropped explicitly (with rationale) rather than kept
  alive by an optional dependency.

### Capability delta (what regressed to an honest refusal)

These features worked via the OCCT fallback and now raise a stage-named
`NotYetImplemented` until the forge stage that owns them lands. Each has a
`golden` contract preserved in-tree behind `@pytest.mark.forge_gap`, so it
lights up automatically when forge closes the gap — no coverage is silently
lost, it is quarantined and named. **The 0.9.x patch line restores these one
exact, adversarially-reviewed step at a time; the "restored" rows below are
already back.**

| Feature | Forge stage | Status |
| --- | --- | --- |
| STL export / 3D view of a *drilled* solid | K2.x DrilledSolid tessellation | **restored 0.9.1** |
| 3D view / STL of bare cylinder / sphere / cone | K2.x primitive tessellation | **restored 0.9.1** |
| circular pattern, tilted / diagonal sketch planes | K2.2 exact ℚ[√d] rotation | **restored 0.9.2** (angles that are multiples of 30°/45°) |
| chamfer of a *selected* edge | K1.2 stable edge-id chamfer | **restored 0.9.3** (axis-aligned box edges, exact planar wedge) |
| counterbore holes (coaxial cyl subtraction) | K2.0 drilled solids | **restored 0.9.3** (sequential coaxial cuts) |
| countersink holes (cone subtraction) | K2.2 conical bore cut | forge_gap |
| engrave (text-pocket boolean) | K3.1 arbitrary-angle strokes (mixed radicals) | forge_gap |
| draft on a quadric face | K2.2 tilt of a quadric | forge_gap |
| boss + pilot (Solid ⊍ Cyl disjoint union) | K2.3 mixed disjoint unions | forge_gap |
| curved-solid STEP export + STEP round-trip of a drilled plate | K3.7 freeform STEP | forge_gap |
| fillet on a non-planar base | K5.2 general blends | forge_gap |
| interference of face-touching / pocketed solids | K2.x boolean robustness on degenerate contact | forge_gap |

Deliberately **dropped** (not merely deferred), with an actionable message:

- **FreeCAD `.FCStd` import.** Its geometry is OCCT-format `.brp` payloads; forge
  has no reader for that binary format. `model_import` and `gitcad-convert`
  now return the STEP migration path (export STEP from FreeCAD, import that —
  planar solids come in exactly). Restoring `.FCStd` would need either a native
  OCCT-BREP reader or a FreeCAD-tree-only importer; neither is worth it pre-users.

Non-default features kept working on forge (no regression): model/section/
assembly 2D drawings, box/prism fillet & chamfer-all-edges, shell, planar STEP
import, mass properties + centroid, exact inertia (`gitcad.analysis`), feature
recognition of plate-with-holes, planar-part interference, the select-DSL
(`area_max`/`length_max`/axis extremes, now that `entities()` carries
`centroid`/`area`/`length`).

## Migration (per the CLAUDE.md major-change process)

1. This ADR supersedes the relevant part of ADR-0018.
2. Build forge HLR behind the existing seam; the drawing engine switches to the
   seam's projected-segment output.
3. Shadow-check: the new drawings render the corpus; visibility is verified
   against the tessellation (a point is hidden iff a triangle occludes it).
4. Convert `tests/**` `@pytest.mark.occt` differentials to forge invariants or
   delete; `invariants/` + `golden/` stay green with no kernel-marker.
5. Delete `kernel/occt.py`, `kernel/auto.py`, the `occt` extra, and the
   `cadquery-ocp` dependency. Remove the `occt` pytest marker.
