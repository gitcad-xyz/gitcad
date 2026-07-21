# ADR-0002: Six seams, and an intent-based, MCP-first API

**Status:** accepted

## Context

We must (a) stay able to make major architecture changes — including swapping the
geometry kernel — without a rewrite, and (b) stop agents falling back to shelling
out to FreeCAD for complex curves, which happens because that API is familiar and
lets them model *blind*.

## Decision

**1. Everything swappable lives behind one of six seams** (`gitcad.seams`):
`Kernel`, `IdentityService`, `DocumentModel`, `Renderer`, `DrawingEngine`,
`Storage`. Agents work *inside* a seam, never across one. A "major architecture
change" should mean writing a new backend for one seam. Adding or widening a seam
requires human sign-off — the small, narrow interface set is the property that
makes change cheap, and it erodes if seams multiply.

**2. The `Kernel` API is intent-based, not control-point-based.** Callers state
what must be true ("through these points, tangent to that face, G2-continuous with
that edge") and the kernel solves the geometry. Raw NURBS control-point authoring
is exactly what agents cannot do without visualization.

**3. The kernel is a bought dependency, not our invention.** OCCT via
`cadquery-ocp`. All OCP imports live in `gitcad.kernel.occt` and nowhere else.
Rationale: Fornjot spent ~4 years writing a b-rep kernel from scratch and
concluded its goals were not reached. We do not repeat that.

**4. MCP is the primary interface.** The MCP tool surface is designed first; the
Python API is a thin binding over the same handlers. An interface that everything
actually uses does not rot.

## Consequences

- Verification is first-class: `Kernel.validate` / `.measure` / `.entities` return
  machine-readable data so agents model by *checking*, not hoping.
- A future Rust kernel (Truck/Monstertruck) or a mesh kernel (Manifold) can be
  slotted in behind `Kernel` without touching the layers above.
- The null kernel proves the seam: the suite runs with no OCCT installed.
