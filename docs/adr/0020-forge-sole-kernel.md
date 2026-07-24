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
- OCCT remained load-bearing for exactly **one** capability: the hidden-line
  removal (`HLRBRep`) behind 2D orthographic drawings. Everything else the
  drawing/viewer/export path needs, forge does.

Meanwhile OCCT carries real costs: a large LGPL-2.1 binary wheel (install
weight and a license obligation), C-level stdout that corrupts the stdio MCP
stream, and a second geometry representation to convert to and from. Keeping a
whole kernel for one feature is the wrong trade once forge can do that feature.

## Decision

**Remove `cadquery-ocp`. forge becomes the sole geometry kernel.**

1. **Native forge HLR.** Add hidden-line removal to forge (`forgekernel.hlr`):
   tessellation-based edge extraction (sharp feature edges + view-dependent
   silhouettes) with occlusion by ray-casting against the solid's triangles.
   Visibility is a display property, not a topological decision, so — under the
   exactness charter — it may use floats; the geometry it draws is still the
   exact solid. The drawing engine consumes projected 2D segments from the
   kernel seam rather than calling any kernel-specific projector.

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
