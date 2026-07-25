# Kernel improvement backlog

Written after nine adversarial review rounds that found ~40 silent wrong-number
defects, none of which the ~1080 tests caught. Everything here is grounded in a
specific thing that went wrong or a specific thing that cost time — no item is
here because it sounded like good practice.

Ordered by leverage, not by size.

---

## 1. Make a wrong number impossible to ship

This is the whole ballgame. Every defect found in nine rounds shares one shape:
**the code validated its INPUT by sampling, instead of validating its ANSWER.**

The pocket guard probed four points of a footprint. The bore guard walked
vertices instead of edges — then the same flaw reappeared in the pocket path
because they are separate code. The box predicate tested `volume == dx*dy*dz`,
then tested `volume ∧ vertices-at-corners`, and both were satisfiable by
something that is not a box. A property test can always be satisfied by
something that is not the thing.

### 1.1 Answer validation on every constructive op (highest value, ~1 day)

Before any op returns a `Body`, run: every edge paired, volume > 0, mesh
watertight at a coarse deflection. All three exist already —
`body.manifold_violations`, `body.volume`, `tessellate` — they are just not
applied uniformly. A defect becomes a refusal instead of a shipped artifact.

The precedent is already in the tree and it worked: `write_step_body` now runs
the manifold oracle on itself before emitting. Every topology defect ever found
in that writer would have refused at the moment it was introduced.

### 1.2 A differential oracle harness in CI (~2 days)

Every op × every representation, exact volume against Monte Carlo with a stated
σ, plus centroid and bbox. Tonight's method, automated. Report anything outside
5σ. This is what actually found the defects; the unit tests found none of them.

Corollary: **any op with a closed-form oracle should carry it in the test file**
— Steiner for rounded boxes, Pappus for tori, Green's theorem for lathes,
πr²h for bores. Tests that assert a number the implementation produced are
worth very little.

### 1.3 Property-based tests over the seam (~1 day)

Random shapes × random ops, asserting only invariants:

- `cut` never increases volume; `union` never decreases it
- `vol(cut(a,b)) + vol(intersect(a,b)) == vol(a)`
- every rigid transform preserves volume exactly
- every returned solid meshes watertight
- `validate(x).ok` for everything the kernel returns without refusing

Those five would have caught most of the ~40.

### 1.4 An ADR-0019 lint (~half a day)

The "no float decides topology" rule is currently enforced by discipline and
review. A checker over the geometry modules flagging `float(`, `round(`,
`< 1e-`, and `** 2` on exact types would have caught two defects outright: the
containment guard that floated a cap's ring (accepting a mouth 1.0 mm outside
the flat at large coordinates), and `_disc_misses_solid` raising a raw
`TypeError` on every rotated solid because `SurdVal` has no `__pow__`.

---

## 2. Number fields — each one unlocks a family, not a cell

The kernel refuses whenever a value leaves its exact field. That is the correct
behaviour and it is also the main capability ceiling. Current fields: `ℚ`,
`ℚ[π]` (as a polynomial ring), `ℚ[√d]`, and `CInterval`.

### 2.1 ℚ[√d][π] — PiPoly over SurdVal coefficients (~1 day, high value)

π is transcendental over any algebraic extension of ℚ, so equality stays
coefficient equality and the ring stays free. `PiPoly` already exists and
already refuses floats; it needs its coefficient type widened and its `sign()`
interval evaluation taught to bound a `SurdVal`.

Unlocks: the napkin ring (sphere ∩ coaxial cylinder — volume `(140/3)π√35`),
curved volumes of exactly-rotated bodies, cone chamfers (slant √109), chamfered
box normals (√2). At least 4 currently-refused cells, and it removes the
"leaves the field" excuse from a much larger space of user geometry.

### 2.2 Trimmed quadrics at twelfths, not just quarters (~1 day)

Trimmed bands are exact only where sin/cos ∈ {0, ±1}, i.e. multiples of π/2.
But sin/cos of π/6 and π/3 live in `ℚ[√3]`, which the kernel **already has**.
Extending `_quarter_index` / `_arc_quarters` to twelfths widens every trimmed
surface — bands, octants, tori — for very little work.

### 2.3 A multi-radical tower (~1 week)

Booleans between a body rotated 45° (`ℚ[√2]`) and one rotated 30° (`ℚ[√3]`)
refuse with "mixed radicals". A general algebraic number field — minimal
polynomials with resultant-based arithmetic — removes that whole refusal class.
Assemblies of rotated parts are where this bites in real use.

---

## 3. Geometry capability (the actual roadmap)

Ranked by how many refusals each removes.

| Item | Unlocks | Notes |
|---|---|---|
| **K5.2 general blends** | 7 of the 18 remaining cells | `fillet(all)` on a loft, an L-prism, a chamfered box, a shelled box. The single largest block. |
| **K4.2 certified polygon inset** | 3–4 cells | A real straight-skeleton offset with topology change, replacing the per-edge offset that self-intersects on a thin base. Also fixes shelling any non-convex prism. |
| **Torus-aware erosion** | 2 cells | A blind bore's floor rim and a counterbore's shoulder erode to a torus. Forge already has `Torus` and `ℚ[π]`; only the offset logic is missing. |
| **Conic sections** | 1–2 cells | A plane cutting a cone in an ellipse or hyperbola. Needed for any oblique cut on a quadric. |

What is **not** on this list, deliberately: two cells (`sphere / cut box`, and
`chamfered box / chamfer(all)`) are provably outside any exact field — a square
prism through a sphere has an `arcsin` in its volume. Refusing is the correct
final answer there, not a gap.

---

## 4. Agentic ergonomics — what cost the most time tonight

### 4.1 Structured refusals (~1 day, biggest agentic win)

Right now a refusal is a string, and an agent that hits one must read the
kernel source to know what to do. Make it data:

```python
KernelError(
  stage="K2.2",
  predicate="mouth_inside_cap",
  measured={"probe": (16, 6), "cap": ((1,1),(39,19)), "clearance": -0.5},
  remedy="move the bore ≥ 0.5 mm from the flat's edge, or reduce r to 3.5",
)
```

With that, an agent can *repair its own design* — shrink a hole, move a pocket,
pick a through hole instead of a blind one — instead of guessing. Nearly every
minute I spent tonight reading refusal text and grepping for the guard that
produced it would have been zero.

### 4.2 `k.can(op, shape, tool)` — plan without building (~half a day)

A predicate an agent can call while planning a feature tree, so it never
commits to a construction the kernel will refuse three features later. The
capability probe already computes exactly this; it just isn't a library API.

### 4.3 A repro minimiser (~1 day)

Given a failing `(shape, op)`, shrink to the smallest shape that still fails.
I did this by hand roughly ten times tonight. It is mechanical and it is
exactly what makes an adversarial finding cheap to act on.

### 4.4 Faster feedback loops

- The capability matrix is ~15 s, each suite ~35 s. A `--changed-only` mode
  keyed to which seam functions a diff touches would make the inner loop
  seconds instead of a minute.
- Deterministic shape hashing + a result cache. The same corpus shapes were
  rebuilt thousands of times tonight across probes, tests and reviews.

### 4.5 Provenance on every returned solid

The seam returns `Solid`, `Cyl`, `RevolveSolid`, `DrilledSolid`,
`DisjointUnion`, `RoundedBox` or `Body` depending on which path fired. Callers
then need `isinstance` chains to do anything — and that is precisely how
`shell(DisjointUnion)` came to return `Body` members and crash every metric.
A `.provenance` field naming the construction path would let an agent reason
about what it got.

---

## 5. Architecture — finish what ADR-0021 started

### 5.1 One implementation per operation, not one per representation

ADR-0021 says every representation converts to one canonical `Body` and ops are
written once. STEP export reached that state tonight — and finding it *hadn't*
was worth 16 dangling edges in every shelled-box export, because the two
writers disagreed about whether `same_sense` composes into an edge traversal.

Still branching per representation: `tessellate`, `mass_props`, `validate`,
`section_polys`. **Every one of those is a place where two implementations can
disagree, and tonight proved they do.**

### 5.2 A `Feature` layer above the kernel

`hole(through | blind | counterbore)`, `pocket`, `boss`, `fillet`, `shell` —
with each guard expressed exactly once. The same guard flaw appeared twice
tonight (walk edges, not vertices) specifically because the pocket path and the
bore path are separate code that happen to need the same check.

This is also the layer an agent actually wants to program against. `boolean.cut`
with a hand-built tool solid is the assembly language; `hole(dia=8, through)`
is the language a design agent should be writing.

### 5.3 Make `Body` the only public return type

Everything above follows from this one.

---

## Suggested order

1. **1.1 answer validation** and **1.4 the ADR-0019 lint** — days, and they
   change the defect rate rather than the cell count.
2. **4.1 structured refusals** — the biggest multiplier on agent throughput.
3. **2.1 ℚ[√d][π]** and **2.2 twelfths** — cheap, and each unlocks a family.
4. **1.2 the differential oracle in CI** — makes every later change safe.
5. **3 K4.2, then K5.2** — the real geometry work, in that order, because
   certified insets are a prerequisite for a lot of blend work anyway.
