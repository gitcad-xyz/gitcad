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

### 2.2 Trimmed quadrics at twelfths, not just quarters

**Corrected: this is not cheap, and it is not independent.** The claim here was
that because sin/cos of π/6 live in `ℚ[√3]`, which the kernel already has,
twelfths cost almost nothing. Checking it before building showed otherwise:
`_band_sweep` (body.py:696) feeds the difference of quarter antiderivatives
straight into the volume, so an endpoint at a twelfth puts `√3/2` into the
volume's π **coefficient**. That is `ℚ[√3][π]` — item 2.1 — not `ℚ[π]`.

So 2.1 is a prerequisite, and the order is: field first, then twelfths. With
2.1 landed the remaining work is real but contained: extend `_quarter_index`,
`_arc_quarters` and `_quarter_antiderivative` to twelfths, and every trimmed
surface widens — bands, sphere octants, torus sweeps.

The general lesson, which cost nothing here and would have cost a day of
rework: a number-field claim is worth checking against the code that consumes
the value, not just the code that produces it.

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

---

## 9. #123 straddling booleans — the analysis, so it is not re-derived

A prism whose corner sits ON a bore axis is the last boolean family the matrix
refuses (2 cells). Before writing any topology, the two questions that decide
whether it is buildable at all were answered — both YES, and the second answer
is not the obvious one.

**Is the volume in an exact field?** Yes, and only ℚ[π] — no surd. Take the
probe's own case: counterbore (bore r=2 over z 0..10, r=4 over z 7..10) cut by
`box(2,2,100)` at the bbox midpoint, so the tool spans x,y ∈ [15,17] with its
corner exactly on the axis.

    z 5..7   bore r=2   removed = square − quarter disc = 4 − π   (per unit z)
    z 7..10  bore r=4   the whole square is inside the bore       = 0

    total removed = 2(4 − π)

**What is the topology?** This is where a hand-built version would go wrong.
The removed face is *not* the square. Its four corners classify:

    (15,15) r²=0  INSIDE      (17,15) r²=4  ON
    (15,17) r²=4  ON          (17,17) r²=8  OUTSIDE

Two corners lie exactly ON the bore, so the region is bounded by the quarter
arc (17,15)→(15,17) plus the two segments meeting at (17,17) — three edges, not
four. **The tool's sides x=15 and y=15 lie entirely inside the bore and
contribute no face whatsoever.** Emitting all four sides — the natural thing to
write — produces a self-intersecting shell.

Trim curves are lines and arcs only; the plane x=15 meets the cylinder in two
straight lines, not a conic, because it passes through the axis. So #123 needs
no new curve type and does not depend on #122.

The real work is that the bore wall stops being a rectangle in (θ,z): it loses
a 90°×2mm patch, so its loop is L-shaped in parameter space. That is the first
non-rectangular quadric face in the kernel, and it is the reason this is a
day's careful work rather than an afternoon's.

**Do it with the audit on.** `_audited` now checks edge pairing and positive
volume on every hand-built body, so the four-sided mistake above fails loudly
instead of shipping a plausible number. That guard did not exist when the
earlier intricate constructions were written, which is why they shipped wrong.

---

## 10. The 16 remaining gaps, triaged — and one that needs no new mathematics

Verified against the probe rather than recalled. All 16 refusals, grouped by
what actually blocks them:

    bored boss / counterbore  x cut box   #123 (analysis in section 9)
    cone                      x cut box   #123, same family
    bored boss / counterbore / drilled(blind) / shelled box  x shell   #120
    cone                      x shell     K4.2 slanted lathe profile
    chamfered box / loft / planar prism / shelled box  x fillet(all)   #121
    cone                      x fillet(all) / chamfer(all)   K5.2 / irrational slant
    sphere                    x cut cylinder   <-- see below

**`sphere x cut cylinder` is the cheapest cell on the board and it has been
mis-filed.** The probe's tool is `cylinder(1, 100)` translated to the bbox
midpoint of `sphere(6)` — which is the ORIGIN. So the cut is coaxial and
centred, and the result is not a general sphere-cylinder intersection at all.
It is a **napkin ring**:

    h = 2*sqrt(R^2 - r^2) = 2*sqrt(35)
    V = (pi/6) * h^3 = (140/3) * sqrt(35) * pi = 867.342597…

verified against the direct computation to full float agreement. That is
rational x sqrt(35) x pi — squarely inside **ℚ[√35][π], the field #117 already
built**. No new number field, no new curve type, no conic.

**CORRECTION, made by checking rather than assuming.** The paragraph above
originally said "the work is assembling them", implying a small construction.
That was wrong, and the correction is the more useful result.

A napkin ring IS a solid of revolution, so `RevolveSolid` looks like the right
home — but read its constructor: `loop_rz` is a list of `(r, z)` POINTS joined
by STRAIGHT SEGMENTS, and its Green integral sums a per-segment polynomial
term. The napkin ring's profile is a lens bounded by the bore wall `r = r0`
(straight) and the sphere's meridian `r = sqrt(R^2 - z^2)` (an ARC). The arc is
not expressible in that type at all.

So this cell needs `RevolveSolid` to gain arc edges: a second edge kind in the
profile, the Green term for `contour integral of r^2 dz` along a circular arc
(which is precisely where the `sqrt(35)*pi` comes from), and then the mesher,
STEP writer, bbox and section paths all following it. That is a new capability
in a core type, not an assembly job.

**What stands and what does not.** The mathematics is genuinely finished — the
closed form is derived and verified, and it needs no field beyond the ℚ[√d][π]
of #117. The CONSTRUCTION is a real piece of work, comparable to the others on
this list. Those are separate claims and it was sloppy to run them together.

It is still probably the best first target, because arc-profile revolutions
unlock `cone x shell` and `cone x fillet(all)` by the same mechanism — but go
in expecting to extend a core type, not to wire up existing parts.

Caveat worth stating: this closed form holds because the cut is CENTRED. Move
the cylinder off-axis and the volume acquires elliptic integrals and leaves
every algebraic extension. So the honest deliverable is the centred case exact
and an explicit refusal off-axis — not a general sphere-cylinder boolean.

---

## 11. The real blocker under #120 and #122: `Body` is rational-only

Found by testing, after two wrong guesses in the same area on the same day.

`NapkinRing` is exact and works — volume, centroid, bbox, and its own mesh. It
cannot be given a canonical `Body`, and the reason is structural rather than
incidental:

```python
>>> B._circle_at(F(0), F(0), SurdVal(0, 1, 35), F(1))
TypeError: argument should be a string or a Rational instance
```

Every coordinate in `body.py` is coerced through `Fraction()`. That coercion is
deliberate and load-bearing — `from_sphere`'s own comment explains that without
it a directly-constructed `Sphere(0,0,0,6)` holds ints and `4r³/3` silently
becomes a FLOAT, "the one thing the charter forbids". So it is not a bug to
delete; it is a guard whose domain is too narrow.

**Why this gates more than one item.** Any solid whose faces meet at an
irrational height needs surd coordinates in the canonical form:

* a **napkin ring** — bore circles at z = ±√(R²−r²)  (#122's through case)
* a **blind bore in a sphere** — the probe's actual `sphere x cut cylinder`
* **cone x shell** and **cone x fillet(all)** — the offset of a slanted profile
  lands at an irrational height by construction
* **torus-eroded blind bores** (#120) — same reason

So "add a `to_body` converter for NapkinRing" is not the next increment. The
next increment is **making `Body` exact-field-generic**: coordinates typed as
"an exact scalar" (ℚ, ℚ[√d], ℚ[√d][π]) rather than as `Fraction`, with the
existing float-rejection guard preserved but widened. Every consumer follows —
`manifold_violations`, `volume`, `bbox`, `tessellate`, `write_step_body`.

**What is already true and should not be re-derived:** the arithmetic is done.
`surdrev.contour_r2_dz` gives the exact volume for line-and-arc profiles over
any of those fields, proven against a closed form. The mathematics is not the
hard part and never was — the TYPE SYSTEM of the canonical form is.

**Estimating honestly:** this is the largest single item on the list, and it
sits underneath several others, which is an argument for doing it rather than
against. Doing #120 or the rest of #122 first would mean building each on a
representation that cannot enter the canonical form — exactly the
representation/canonical split ADR-0022 exists to end.
