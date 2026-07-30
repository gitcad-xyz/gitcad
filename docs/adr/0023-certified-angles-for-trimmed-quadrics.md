# ADR-0023 — certified angles for trimmed quadric faces

Status: accepted (2026-07-29)
Extends [ADR-0019](0019-certified-intervals.md) (certified intervals) and
[ADR-0021](0021-canonical-brep.md) (one canonical B-rep). Supersedes nothing:
the exactness charter is unchanged, and this is an application of the escape
hatch ADR-0019 already built rather than a loosening of it.

**Restates** ADR-0021's surface/trim schema, which had drifted from the code
(see *ADR-0021's data model* below). ADR-0021's decision — one canonical B-rep,
representations as constructors — is untouched.

## Context

### The measurement

The capability matrix scores a **cell** green when one representative solid
meets one representative operation. It has never asked what fraction of the
**parameter space** behind that cell answers. `gitcad.bench.coverage` now does:

| family | parameter coverage |
|---|---|
| face off a box (planar control) | 77/77 — **100%** |
| cap on a sphere (K2.x rung 2) | 33/33 — **100%** |
| drill a plate, bore fully inside | 41/41 — **100%** |
| pocket into a bar | 39/39 — **100%** |
| flat on a bar (K2.x rung 1) | 3/33 — **9%** |
| slot through a bar — *the composed grid's own `cut box` shape* | 0/25 — **0%** |
| bore across a plate wall (the 17-cell family) | 8/33, all 8 non-crossing; the crossing set is **0%** |

**The discriminator is whether the cut leaves a circular SEGMENT.** Not which
quadric is involved, and not which curve the two surfaces meet in. A full disc
removed, a polygon pocket, and a plane cutting a sphere all have polynomial
closed forms and answer everywhere. A chord across a disc leaves

    A = r²(t − sin t cos t),   t = arccos(h/r)

and by Niven `t` is a rational multiple of π only at twelfths. The admissible
set is finite inside a continuum. K2.x rung 1 is a green cell on the matrix and
answers a machinist at **three depths** on a Ø10 bar.

### Why this is a decision and not a bug

Every remaining boolean family in the composed grid is segment-producing.
Continuing to build exact rungs therefore closes cells on the matrix while
shipping capabilities that refuse on essentially every real input — and the
matrix, counting cells, would report progress the whole way. Two earlier
roadmap plans were already killed by measuring the denominator
(`docs/kernel-improvement-backlog.md` §2); this is the third and the most
expensive to have got wrong, because the work would have *looked* like it was
succeeding.

### What is actually in the way

`body._band_sweep` returns a swept angle **in quarter turns** — an integer
index — and `_quarter_antiderivative` is indexed the same way. Trimmed
cylindrical, conical and spherical faces are measured by *counting sectors*,
not by carrying an angle. That representation is what pins every arc to
twelfths, and `notch.py` already records the consequence: a face whose angular
span is not a whole number of sectors "would need a new quadric measure that
500+ existing faces also depend on."

So this is not a routing job inside one rung. It is a change to how a trimmed
quadric face states its extent.

### Where the scope was originally set too narrow

ADR-0019 introduced certified intervals as a **K3** need: "K1 and K2 hold to a
hard rule … K3 breaks that comfort." That rule is still literally true — K2
uses no floats, it *refuses* — but it framed exactness as settled for K2, and
the coverage sweep says otherwise. K2's failure mode is not the one ADR-0019
anticipated. It is not "the quantity cannot be represented at all"; it is
**"the quantity can be represented only on a null set"**, which reads as
success on a cell-counting instrument and as refusal to every user.

ADR-0019 needs no revision for this. Its governing consequence —

> The exact fields remain the default and the first choice; `CInterval` is used
> only where no exact field reaches. A model that *could* be exact must not
> silently fall back to an interval.

— is exactly the constraint this ADR must honour, and is why the exact sector
path stays primary and bit-identity is the acceptance criterion below. What
changes is only the *reach* of the escape hatch, from K3 to K2.

## Decision

**Carry the angular extent of a trimmed quadric face as a certified angle (an
ADR-0019 `CInterval`) rather than an integer sector index, and let the exact
sector path remain as the fast, exact special case it already is.**

1. A trim carries `(k0, span)` **or** a certified `[θ0, θ1]`. Where the
   endpoints land on twelfths the exact path is taken and the result is
   `provenance: "exact"`, bit-identical to today.
2. Where they do not, the face is trimmed at exact surd endpoints — the chord
   meets the circle at `(h, ±√(r²−h²))`, which is already representable in
   ℚ[√d] for any rational `h` — and the *measure* is certified.
3. `mass_props` reports `provenance: "certified"` with a proven half-width, as
   it already does for `TubeSolid` and `TrimmedShell`. A certified result is
   never silently mixed with an exact one.
4. Topological decisions continue to require a **certified sign** (ADR-0019).
   Where a bracket straddles zero the kernel tightens and retries, and refuses
   if it cannot certify within budget. It never guesses.

The missing primitive is already built: forge `f61e2aa` adds certified
`arccos`, `sin` and `cos`, with the enclosure verified against identities
rather than against a double (the brackets are ~1e-40 wide; a `float` oracle
carries ~1e-16 of error and cannot witness them).

### This is not a move to floating point

A bare float carries no proof — you cannot tell a correct 534.6435 from a
rounding artifact, which is the argument ADR-0019 already made and this ADR
does not reopen. Moving to tolerance-based arithmetic would be a different
decision, would supersede ADR-0018/0019, and would give up the property that
distinguishes this kernel: an agent can act on "certified ± ε" and on a
refusal, and cannot act on a silent wrong number.

## Consequences

### The permanent exact-field boundary is not permanent

`capability._EXACT_FIELD_BOUNDARY` marks 4 single-op and 10 composed cells as
**outside any exact field, permanently** — a square prism through a sphere
(arcsin), through a cone (`ln(1+√2)`, by Baker), a fillet's turn angle
(arctan, by Lindemann), a loft's sweep (`arccos(1/√37)`, by
Gelfond–Schneider). Every one of those constants is *transcendental* and every
one is *bracketable*. Under this ADR they stop being permanent walls and become
**certified answers** — 14 cells that the roadmap currently excludes from its
own denominator.

That is a second correction to the same dict, which already carries one: the
`(chamfered box, chamfer(all))` entry was labelled permanent and was merely a
field limitation. A "permanent" label has now hidden closable work twice.

### ADR-0021's data model, restated

ADR-0021 records the canonical B-rep as `Surface ∈ {Plane, Cylinder, Cone,
Sphere}` and `Curve ∈ {Line, Circle}`. That had already drifted: `Torus` is
absent from the ADR, `Sphere` is `SphereS`, and — the part that matters here —
the model says nothing about how a face states **which part** of its surface it
occupies, although two surfaces already carry that on themselves. As accepted,
the schema is:

```
Body    = [Face]
Face    = (Surface, [Loop], sense)     # sense: outward normal == surface normal?
Loop    = [Edge]                       # first loop outer, rest are holes
Edge    = (Curve, v0, v1)              # v0 == v1 for a full circle
Surface ∈ { Plane(n, d)
          , Cylinder(p, d, r)
          , Cone(p, d, tan_half)
          , SphereS(c, r, pole)        # pole: TRIM — which side of the one rim
          , Torus(c, d, R, a, k0, span)  # (k0, span): TRIM — sector extent
          }
Curve   ∈ { Line(p, d), Circle(c, n, ref, r) }
```

**A trim is carried on the surface, not inferred from the loops**, because one
rim bounds a quadric in two ways and the loops cannot say which (ADR-0021's own
`_sphere_zone` note records the same ambiguity for a two-rim sphere face). This
ADR keeps that rule and changes only the *number kind* a trim may hold:

```
trim extent ::= (k0, span)             # exact, integer sectors — unchanged
              | CInterval [θ0, θ1]     # certified, this ADR
```

The exact form remains the default and the only form used where the endpoints
land on sectors, per ADR-0019's rule that a model which *could* be exact must
not silently fall back to an interval. Adding the second form is the whole
technical content of this ADR; everything else follows from it.

### Breaking

Geometry output changes for every segment-bearing cut, so by CLAUDE.md rule 3
this is a **breaking change, never auto-merged**, and by ADR-0006 it is
Tier 1 at best. It follows the major-change process in CLAUDE.md:

1. this ADR;
2. drop the agent loop to Tier 0;
3. build the certified trim behind the existing seam, exact path untouched;
4. shadow-run old vs new across the model corpus — every currently-exact
   result must stay **bit-identical**, which is the acceptance criterion, not
   a nice-to-have;
5. `tests/invariants/` and `tests/golden/` stay green throughout;
6. cut over.

### Costs, stated plainly

- Certified arithmetic is slower: exact rational bisection to 1e-40 is
  thousands of operations where an index lookup was one. The exact path
  staying primary is what keeps this off the common case.
- `provenance` becomes load-bearing for consumers. Anything that compares two
  `mass_props` volumes for equality must handle brackets, and a certified
  value must never be written into a byte-canonical document as though exact
  (ADR-0004).
- Two number kinds in one measure path is a real complexity increase, and the
  sector index cannot simply be deleted — it is what makes the 100% families
  exact and fast.

### What it buys

The segment-bearing families move from single-digit parameter coverage to
total coverage, and the composed grid's remaining boolean gaps stop being a
list of rungs that cannot be finished. `gitcad.bench.coverage` is the
acceptance instrument: the number to move is the percentage, not the cell.

## Implementation progress

Following the CLAUDE.md major-change process. Steps 1–2 done (this ADR; the
loop is at Tier 0 for kernel semantics by rule anyway). Step 3 in progress:

- **done, forge `f61e2aa`** — certified trigonometry (`arccos`, `sin`, `cos`),
  with the enclosure verified against identities rather than a double, since
  the brackets are ~1e-40 and a `float` carries ~1e-16.
- **done, forge `15db93b`** — the arc-span foundation: `arc_cos_sin` (exact at
  any angle), `arc_span_certified`, and `certified_bracket` (a float proposes,
  exact comparison disposes). Validated against `_arc_quarters` across all 84
  start/span combinations on the twelfth grid.
- **done (measured)** — the generalised flat geometry is exact and manifold at
  every rational depth: 0 unpaired edges at h = 1, 5/2, 3, −1, 7/3 on a
  radius-5 bar. So only the MEASURE is missing, not the construction. This is
  the fact that makes the rest tractable.
- **next** — the measure. `volume` accumulates a `PiPoly` per face, so a
  certified term means widening that accumulator through the whole integral,
  and `_audited` calls `body.volume` on **every** construction — a half-done
  version puts an unaudited answer in reach, which is the one thing this
  kernel exists to prevent. Then `centroid`, then `vector_area` (which already
  returns `None` for "not checked" and must keep saying so rather than
  guessing).
- **then** — shadow-run (step 4): every currently-exact result bit-identical,
  and `gitcad.bench.coverage` moves rung 1 off 9%.

## Alternatives considered

**Keep building exact rungs.** Rejected by measurement: the next three
candidate rungs are at 0%, 0% and 9%.

**Bare floats with tolerances**, as OCCT and Parasolid use. Rejected — it
supersedes the charter rather than extending it, and it removes the one
property this kernel has that they do not. If it is ever wanted it should be
argued on its own merits in its own ADR, not arrived at by drift.

**Facet the curved faces and measure the mesh.** Rejected; ADR-0019 forbids it
and it converts an exactness problem into an unbounded-error problem.

**Leave the rungs refusing and route users to the certified K7 path.** Rejected
as a non-answer: K7's `PatchSolid` reaches these shapes only through a
freeform conversion that does not exist for `Cyl`, and a D-shaft should not
require a NURBS detour.
