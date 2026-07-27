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

> **First rung DONE (biquadratic).** `BiSurd` (forge `bisurd.py`) is exact
> ℚ(√p,√q) for coprime square-free p < q: basis {1, √p, √q, √pq}, the
> (√p)(√q) = √pq closure, exact structural zero (basis independence), sign by
> proven isqrt enclosures, division via the conjugate chain. `PiPoly` carries
> BiSurd coefficients, so ℚ(√2,√3)[π] volumes exist — the field
> `chamfered box × fillet(all)` needed (see §10). `SurdVal` dunders now defer
> (`NotImplemented`) instead of silently NESTING a wider exact type in their
> rational slot — the pre-existing latent bug this work exposed. The general
> n-radical tower (rotated-assembly booleans) remains open.

---

## 3. Geometry capability (the actual roadmap)

Ranked by how many refusals each removes.

| Item | Unlocks | Notes |
|---|---|---|
| **K5.2 general blends** | 7 of the 18 remaining cells | `fillet(all)` on a loft, an L-prism, a chamfered box, a shelled box. The single largest block. |
| **K4.2 certified polygon inset** | 3–4 cells | A real straight-skeleton offset with topology change, replacing the per-edge offset that self-intersects on a thin base. Also fixes shelling any non-convex prism. |
| **Torus-aware erosion** | ~~2 cells~~ **DONE (#120/#130, see §12)** | Closed all five shell gaps (blind, counterbore, bored boss, shelled box, chamfered box) — and exposed two green cells that were silent wrong numbers on the way. |
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

### 9.1 DONE — and three things the analysis above got wrong

Both cells are green: `333/345`, 8 gaps (the two `cut box` rows in section
10's triage table are closed; the table predates this). `forgekernel.notch`
builds the result against the canonical `Body`, so one implementation serves
the counterbore (a `DrilledSolid`) and the bored boss (a `DisjointUnion`
around a lathe). Volumes are exactly `8992 − 74π` and `2682 + 737π/8`, each
re-derived by hand at revival and matched to the letter; both bodies mesh with
0 unpaired directed edges at deflections 0.8 through 0.05.

> **Revival note (this landed via `wip/123-straddling-bore-unreviewed`).** The
> parked commit's message warned of a KNOWN DEFECT — 87 non-manifold directed
> edges from meshing the (θ,z) bounding rectangle. That described the FIRST
> prototype; the parked content already carried the mesher fix (split bands +
> rim arcs on the shared axis grid), and measuring, not re-reading, settled
> it: 0 unpaired at four deflections. The branch was also a stale snapshot of
> everything else (its parents are the 0.9.6-era commits), so it was revived
> by cherry-pick onto main, keeping main's newer napkin-ring / cone-shell /
> fillet work intact.
>
> New at revival, beyond the parked branch: the **odd-twelfth family
> executes**. A wall at r/2 (60° crossing) used to be un-buildable —
> `Fraction()` rejected the √3 coordinates, and after `F()` was widened the
> path still died on `SurdVal ** 2` (backlog 1.4's exact defect class, now
> `x*x`). It returns `8980 − (5/2)√3 − (110/3)π` against the through-bore
> probe, verified against a hand integral; the mesh and STEP paths refuse it
> BY NAME (30° trims are exact but not yet meshable, K3.7), and its walls
> with irrational-length normals report vector-area NOT CHECKED rather than
> passed.
>
> **Two guard holes found by attacking the unreviewed classification, both
> the same shape:** the mouth-face containment was a BBOX test, so (1) an
> L-plate whose reentrant corner the tool pokes past, and (2) a through-
> pocket that appears only as a kept inner loop of the mouth face, both
> classified IN and built a notch through material that does not exist. The
> mesh audit happened to catch both torn artifacts — a lucky net, not a
> contract. The guards now require the polygon mouth to BE an axis-aligned
> rectangle strictly containing the tool, and every kept mouth loop to clear
> the tool footprint (conservative bbox, refuses more, never admits an
> overlap). Both cases are pinned in
> `tests/golden/test_straddling_bore_boolean.py` as guard refusals, not
> audit reports.

Three corrections worth keeping, because each cost real time:

1. **The L-shaped face is not needed and should not be built.** Split the bore
   wall at the notch floor into a full 360° band below and an ordinary trimmed
   band across, and the stock band term measures both correctly. Building the
   L-face instead needs a new quadric measure that 500+ existing faces also go
   through — the one change in this area with a blast radius.
2. **The audit was blind to exactly this family.** `_edge_key` carried no arc
   SPAN, so a 90° arc and the 270° arc on the same circle with the same
   endpoints keyed identically. A quarter cylinder (5π) and the 3/4 wedge glued
   to its flat walls (35π/3) are the same five faces and both passed
   `manifold_violations` clean. Fixing that had to land BEFORE the mixed
   arc/line area measure, or the measure would have turned a refusal into a
   silent wrong number.
3. **Edge pairing cannot see an orientation error at all**, because it audits
   counts. `body.vector_area` — Σ Areaᵢ·n̂ᵢ, exactly zero for any closed shell —
   is the third oracle and now runs in `_audited`, as the arc-capable surface
   form behind the boundary-integral `vector_area_defect` (which skips any body
   carrying an arc). It catches a face whose sense is flipped even when the
   volume stays positive and every edge pairs.

Also found on the way, unrelated to #123 but shipped by it: the trimmed-band
MESHER read its two rim heights off the arcs only, so a band whose far rim is a
whole circle and whose near rim is split into quarters came out zero-tall and
emitted no triangles. And `circle_pts` used a free-form segment count while
bands and corner octants subdivide dyadically, so a whole rim and a trimmed
band on one axis never shared vertices. Both are fixed; every corpus mesh got
strictly finer and stayed watertight.

**Still refused, permanently.** A tool wall at any offset a/r outside
{0, ±1/2, ±√3/2, ±1} — Niven's theorem says those are the only ones whose
crossing angle keeps the removed area in ℚ[√3][π]. The refusal names the field
and the three admissible offsets. Also refused, as gaps rather than boundaries:
a blind straddling pocket (needs a ceiling face), a tool straddling two bores
at once, and a tool that reaches the part's outer wall.

---

## 10. The 16 remaining gaps, triaged — and one that needs no new mathematics

Verified against the probe rather than recalled. All 16 refusals, grouped by
what actually blocks them:

    bored boss / counterbore  x cut box   #123 (analysis in section 9)
    cone                      x cut box   #123, same family
                                          ^ WRONG, and now CLOSED as a wall, not a gap: the
                                            crossing angle arccos(2/r(z)) varies with z and is
                                            integrated, emitting ln(1+√2) — removed V =
                                            40 − (20/3)√2 − (5/3)π − (20/3)·ln(1+√2), outside
                                            every ℚ[√d][π] by Baker. In _EXACT_FIELD_BOUNDARY
                                            (capability.py); matrix denominator −1.
    bored boss / counterbore / drilled(blind) / shelled box  x shell   #120
    cone                      x shell     K4.2 slanted lathe profile
    chamfered box / loft / planar prism / shelled box  x fillet(all)   #121
    cone                      x fillet(all) / chamfer(all)   K5.2 / irrational slant
    sphere                    x cut cylinder   <-- see below

> **#121 partial close (planar prism, shelled box — 331/345).** Both cells
> were, as the analysis said, pure ℚ[π]. The two that closed:
>
> * **`planar prism x fillet(all)`** — `FilletedPrism` (quadric.py): a right
>   prism over any rectilinear simple polygon, every edge blended at one r.
>   The reentrant corner takes an INSIDE fillet, and where that concave
>   vertical blend meets each cap band the ball's centre sweeps a quarter
>   TORUS (major 2r, minor r) — the source of the π² term `n_rf·r³/2`. The
>   probe's L: `3752 + 178π/3 + π²/2`. Closed-form derivation, guards and the
>   full Monte-Carlo verification record are in the class docstring and
>   `tests/golden/test_fillet_rectilinear.py`. Soundness of the guard set:
>   every blend feature lies within r of the boundary element that generates
>   it, so requiring all edges ≥ 2r long and all NON-ADJACENT edge pairs
>   ≥ 2r apart (exact, and it doubles as the simplicity test) makes features
>   from distinct elements disjoint. It is a REPRESENTATION, not a Body: a
>   canonical form needs azimuthally-trimmed torus patches and planar loops
>   mixing lines and arcs, neither of which `body.py` has yet — tessellate /
>   STEP / entities(edge) refuse honestly, so the differential oracle SKIPS
>   it (its volume was pinned by decomposed MC instead: A∩B and the
>   reentrant wedge to ±0.009 / ±0.001).
> * **`shelled box x fillet(all)`** — a hollow box's cavity edges are
>   concave, so their blends ADD material: the cavity becomes exactly the
>   rounded box of its own dimensions, strictly inside the outer one for any
>   wall t > 0. The result IS a canonical Body (outer 26 faces + cavity 26
>   sense-flipped), meshes, exports STEP, and sits in the differential
>   oracle: residual 0.0016%, mc z 0.7.
>
> **Found on the way, the backlog's own defect class:** `_box_check`
> (fillet's box gate) accepted any prism whose vertices are a subset of the
> bbox corners — `fillet(triangular prism, [], 1)` returned a RoundedBox
> holding TWICE the prism's material, silently, on main. The vertex screen
> now confirms with `_is_axis_box`'s exact symmetric difference. Chamfer had
> only been protected by accident (the diagonal face's irrational normal
> refuses downstream). Both new detectors use the same idiom: rebuild the
> claimed shape, require both exact boolean differences empty.
>
> ~~Still open in this family: `chamfered box x fillet(all)` (the blend runs
> along edges whose faces have √2 normals — needs ℚ[√2][π] carried through
> a canonical form that can hold it)~~ — **CLOSED (340/345, 0 achievable
> gaps).** The field claim above was measured wrong: the volume is
> **ℚ(√2,√3)[π]**, biquadratic — √2 rides in on the eroded setback
> t' = d − (2−√2)r, √3 enters as the chamfer–chamfer edge length (√3/2)t'
> times its π/3 sweep (cos dihedral = −1/2 exactly, nice by Niven),
> surfacing as 2√6·π. Landed as `BiSurd` (§2.3) + `FilletedChamferedBox`
> (forge quadric.py): a FilletedPrism-style REPRESENTATION whose volume is
> assembled by the Steiner/opening decomposition over the eroded polytope —
> NEVER per corner patch: the 32 spherical patches individually carry
> arccos(1/3) / arccos(1/√3), transcendental over every ℚ[√d][π], and cancel
> only in aggregate to 4π. Probe cell: V = 8040 − 456√2 + (166/3 − 6√2 +
> 2√6)π = 7557.6867…, MC-verified at three seeds (records in
> `tests/golden/test_fillet_chamfered_box.py`). Detection in the seam is
> sound (rebuild + exact symmetric difference); the bridging regime
> d ≤ (2−√2)r and the thin-face regime X − 2d − (2√2−2)r ≤ 0 refuse by name.
> Mesh/STEP/entities(edge) refuse honestly through `to_body` (no canonical
> form yet — it needs sphere-triangle corner patches and two-sweep cylinder
> bands). `loft x fillet(all)` remains a WALL (Gelfond–Schneider, see
> `_EXACT_FIELD_BOUNDARY`).

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

> **SECOND CORRECTION (#122 follow-up), by running the probe rather than
> reading it.** The paragraph above is wrong on a load-bearing detail, and
> believing it would hand the next agent a green cell that is not green.
> `cylinder(r, h)` spans **z = 0 to h**, so translating it to the bbox midpoint
> `(0, 0, 0)` leaves it spanning **z = 0..100** against a sphere at z = −6..6.
> The cut is coaxial but it is **BLIND, not through** — it enters the top and
> stops nowhere, having removed only the upper half's bore. Measured:
>
> ```
> >>> _mid(k, k.sphere(6))            → (0.0, 0.0, 0.0)
> >>> tool.z0, tool.z1                → 0, 100
> ```
>
> A napkin ring is therefore **not** what this cell asks for. The through case
> is now built, exact and meshing (`NapkinRing` + `from_napkin_ring`), and the
> cell is still 🚧 — correctly, because the seam refuses the blind bore rather
> than answering the wrong solid. The matrix stays 327/345.
>
> **What the blind case actually is**, since the derivation is cheap and should
> not be re-done: sphere minus a coaxial cylinder entering from above and
> stopping at z = 0. Three faces, not two —
>
> * the sphere minus ONE polar cap (a single rim at z = +√(R²−r²), so a
>   `_sphere_zone` with one degenerate rim; the current predicate rejects it,
>   deliberately);
> * the bore wall, z = 0 to √(R²−r²);
> * a **flat disk floor** of radius r at z = 0 — the tool's own bottom cap.
>   Note this is a PLANE, not the spherical-cap floor an earlier note guessed.
>
> Removed volume = the bore cylinder (πr²·√(R²−r²)) plus the sphere's cap above
> z = √(R²−r²), which for R=6, r=1 gives
>
>     V = 288π − π(144 − 70√35/3) = π(144 + 70√35/3) = 886.0606404…
>
> checked against an independent Monte Carlo membership test (4M samples):
> `885.969 ± 1.296` at 3σ. Use that as the oracle when the cell is attempted;
> do not take it from whatever the implementation first prints.
>
> — still inside ℚ[√35][π]. So the field is not the blocker; the third face and
> the one-rim zone predicate are. Do NOT widen `_sphere_zone` to admit one rim
> without also deciding band-versus-caps explicitly (see its docstring).
>
> **CLOSED (334/345).** `SphereBlindBore` (surdrev) + `from_sphere_blind_bore`
> (body). The one-rim ambiguity was decided the way the zone docstring
> demanded — a representational change, not a looser predicate: `SphereS`
> gained a `pole` trim field (the Torus k0/span precedent) naming the pole the
> face CONTAINS, and `_sphere_pole_span` reads it; a bare one-rim face still
> refuses through the octant path. The volume term gained the axis-offset
> piece `c_z·∮n̂_z dA` that a symmetric napkin zone had been silently hiding
> (it is identically zero there; a one-rim face has ∮n̂dA = −πr²ẑ, so a
> translated blind bore pins it). Verified against the banked closed form
> exactly (float diff 0.0) and by fresh analytic MC, seed 987654321, 16M:
> 885.651 ± 0.216 (z = −1.9). Found on the way and fixed with failing tests
> first: (1) `napkin_ring_contour`/`_half_height` truncated a FRACTIONAL band
> height through `int()` — sphere R=3/2 bored at r=1 was 1.6% light, silently
> (`_band_half_height` now routes fractions through `sqrt_rational`); (2) the
> STEP writer's whole-sphere branch IGNORED a sphere face's loops, so a
> rational-rim zone would have shipped as a complete sphere — it now refuses
> trimmed spherical faces by name. Off-axis, band-edge floors, and tools
> stopping inside the material still refuse; bottom-entry blind bores are the
> same mathematics with no constructor yet.

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

> **RESOLVED for the napkin ring, and the diagnosis below was right.** `F()`
> was widened (#122) and `from_napkin_ring` now builds the canonical two-face
> `Body`: a spherical zone plus the bore wall, exact volume `(140/3)√35·π`,
> watertight mesh, clean audit. Keep reading — the section's central claim,
> that the TYPE SYSTEM of the canonical form is the blocker rather than the
> mathematics, is what turned out to be correct, and it still gates `cone x
> shell`, `cone x fillet(all)` and #120.
>
> Two further coercions of exactly this shape were found downstream when the
> converter was finished, both of them SILENT until an irrational coordinate
> reached them:
>
> * `PiPoly.from_pival` forced both coefficients through the stdlib `Fraction`,
>   so a `PiVal` carrying a `SurdVal` on π could not report its own sign — and
>   `PiVal._cmp` swallowed the `TypeError` into `NotImplemented`, surfacing it
>   as "'<=' not supported between instances of 'PiVal' and 'int'" in the
>   ANSWER AUDIT, three modules from the cause. Fixed by routing through
>   `_coef`, which admits ℚ and ℚ[√d] and still refuses a non-integral float.
> * `_audited` ordered an exact volume against a bare `0` instead of asking
>   `.sign()`, which is what let a swallowed exception disarm the audit's one
>   mandatory check. Now asks for the sign.
>
> **The lesson to carry forward:** widening the field is not one edit. Grep for
> `F(` / `Fraction(` on any path an exact coordinate reaches — sign tests,
> comparisons, hashing, bbox, meshing — because each one fails only on the
> irrational case and several of them fail QUIETLY.

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
* **cone x shell** and **cone x chamfer(all)** — the offset (or the bevel
  setback) of a slanted profile lands at an irrational height by construction
* **torus-eroded blind bores** (#120) — same reason

> **CORRECTION.** This list used to name **cone x fillet(all)** where it now
> names `chamfer(all)`, and the two are not the same problem at all. Widening
> the number field closes the chamfer and CANNOT close the fillet.
>
> * **chamfer** sets a corner back by `d` along each edge, i.e. `d/L` with
>   `L = √(dr²+dz²)`. A rational over a surd is still in ℚ[√e] — `1/√e = √e/e`
>   — so ONE slant costs one radical and the answer is exact. Closed; the only
>   real gate is TWO slants with different square-free parts (biquadratic).
> * **fillet** revolves an ARC. ∮r²dz over an arc of centre radius `c_r`
>   carries the arc's TURN ANGLE linearly, coefficient `c_r R²`, and a blend's
>   centre is `R` inside the material so `c_r ≠ 0` always. The turn is `π − φ`,
>   so the answer is in ℚ[√d][π] **iff φ is a rational multiple of π**. Rational
>   profile coordinates make `tan φ` rational, and Niven's theorem then forces
>   `tan φ ∈ {0, ±1, ∞}`: right angles and 45°/135° corners, and nothing else,
>   ever. `cone(6, 2, 10)` has `tan φ = 5/2`, needing `arctan(5/2)` —
>   transcendental by Lindemann. That cell is now an `_EXACT_FIELD_BOUNDARY`
>   entry, not backlog, and no type-system work will move it.
>
> The genuine fillet backlog left over is narrow and worth naming: the
> **45°/135° lathe corner** and the **right angle between two diagonal edges**
> both turn through a rational multiple of π and both ARE expressible in
> ℚ[√d][π]; `_fillet_profile` refuses them by name and does not build them.
>
> **Newly exposed by the chamfer close:** `write_step_body` cannot yet emit a
> `RevolveSolid` with ℚ[√d] coordinates — it refuses honestly (structured
> `NotYetImplemented`, no crash) with the same `Fraction()` coercion
> `TypeError` shown above, wrapped at the seam. Same root cause, same fix.

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


---

## 12. #120/#130 DONE — torus-aware erosion, and the two wrong greens it exposed

The whole shell column is green (339/345, 2 gaps, 0 crashes). What landed,
in dependency order, each volume verified against an INDEPENDENT Monte-Carlo
membership test (`dist(p, complement) >= t`, 16M samples) BEFORE the
construction was written — the closed forms are in the golden test files.

1. **#130 first, because nothing else is auditable without it.** `lathe_body`
   emitted `Face(Torus, (), True)` — no loops — so every rim where a fillet
   meets its neighbours read as used-by-1 and `_audited` carried a blanket
   pairing exemption for any body containing a torus. Torus faces now carry
   their rims as `Loop` edges (a radius-0 rim on the axis is a singular point
   on no edge, the pointed-cone precedent), and the exemption is gone; the
   invariant test now pins the OPPOSITE (a loop-stripped torus body must
   refuse through pairing alone — the mesh and volume checks cannot see it).

2. **Blind bore + counterbore shell** (`_shell_drilled`): the void is
   scaffolded as a stepped DrilledSolid whose FLAT faces are already correct,
   then each scaffold step is replaced by the fillet torus
   (`_erode_rim_to_torus`, k0=3 span=1, carried (ρ, Z−t) → (ρ+t, Z)). The
   banked TRAP held exactly as advertised: the naive floor-disk-at-ρ+t body
   passes all four audit checks while 3.744 mm³ heavy — the closed-form
   golden is the only guard. Probe volumes: `2728 + (107/3)π + (3/2)π²`
   (blind) and `2728 + (107/3)π + 2π²` (counterbore). The zf ≤ t regime was
   a FALSE refusal (no torus exists; the through collar is exact) — fixed,
   `2728 + 34π` pinned; it greens no cell, as predicted. Clipped regimes
   (t < zf−bz0 ≤ 2t, shoulder step ≤ t) refuse by name: arcsin, outside
   every exact field. Bottom-entry and sealed stacks refuse as unbuilt
   mirrors.

3. **Hollow box shell**: no torus — the void is the inset box minus the
   cavity DILATED by t, which is a RoundedBox by Minkowski. Wall == 2t (the
   probe) degenerates to the corner-and-edge lattice: FRAME faces whose
   inner rings are exactly the quarter-cylinders' straight tangency edges.
   `3704 + (148/3)π`; thick-wall case `3344 + (130/3)π`; wall < 2t refuses
   (clipped cylinder = circular segment = arcsin).

4. **Bossed plate (WRONG GREEN #1).** `disjoint union (boss) × shell` was
   returning the PILE answer — members shelled separately — which is 60.9 mm³
   heavy: touching members are one solid, the void connects through the
   plate, and the exposed plate-top rim erodes to a quarter torus swept
   INSIDE the plate (k0=2 span=1). Composite constructions landed for both
   boss cells: `1916 + (103/3)π + 2π²` (plain) and `1916 + 47π + (5/2)π²`
   (bored). `shell(DisjointUnion)` now guards the member-wise path with a
   strict bbox-separation witness and refuses touching members outside the
   bossed-plate pattern.

5. **Chamfered box shell**: convex, so the erosion is the solid's own
   half-spaces offset inward; relative to the inset box the void is the
   chamfered box with depth `d' = d − (2−√2)t` — in ℚ[√2], buildable by
   `fk_chamfer` with a SurdVal distance thanks to the F() widening.
   `1952 − 12√2` pinned; `d' ≤ 0` collapses to a plain box void (exact).

**WRONG GREEN #2, found while pinning the member-wise contract:**
`_prism_shell`'s cap-boundary walk closed one loop without checking it
CONSUMED every boundary edge, so a two-component solid (two 10³ boxes
unioned into one Solid) hollowed ONE component and returned 1488 where the
true member-wise value is 976. The walk now requires full consumption.

**Left on the table, deliberately:**

* `chamfer(DisjointUnion)` still operates member-wise on TOUCHING members —
  the same pile-answer defect class as #1 above: `disjoint union (boss) ×
  chamfer(all)` bevels the boss's buried base rim as if exposed. The fillet
  half of this bullet is DONE (§13): the composite construction and the
  bbox-separation witness landed; chamfer needs its own junction CONE face
  and the same witness. Derive the closed form before touching the code.
* Mirrored (bottom-entry) blind stacks, mixed 2t/thicker hollow-box walls,
  and multi-loop prism caps are honest named refusals — buildable, unbuilt.
* The clipped regimes are NOT gaps: Niven/Lindemann puts the clipped
  torus/cylinder sectors outside every exact field. Do not widen
  `Torus(k0, span)` to general angles to chase them — that is the edit that
  lets the transcendental in.

## 13. #134 DONE — the blend family beyond one constant radius, and its walls

The load-bearing fact, derived by execution before any code moved: **"linear
variable-radius fillet" names two different surfaces**, they share their
tangency curves on both faces, and they sit on opposite sides of the
exact-field boundary.

* **Disc-sweep** (each slice perpendicular to the edge is the 2D fillet arc
  of radius r(t)): an OBLIQUE circular cone, apex on the edge line where r
  extrapolates to 0 (scaling identity verified to 4e-14), G1 to both faces.
  Removed volume `(1−π/4)·L(r0²+r0r1+r1²)/3` — polynomial, ℚ[π]. **This is
  what shipped**: `fillet(shape, edges, radius=(r0, r1))` returns forge's
  `VariableFilletedBox` (volume/bbox/mass_props exact; mesh and STEP refuse
  by name until the oblique-cone band — the FilletedPrism precedent).
  r0 == r1 collapses to the constant fillet (same surface, and it meshes).
* **Rolling ball** (Parasolid/SolidWorks — envelope of spheres r(t)): a
  right cone whose perpendicular slice is an ELLIPSE; the slice-segment area
  carries the eccentric-anomaly span Δu linearly with **cos Δu = b²** (b the
  taper slope). Niven ⇒ in-field only for b² ∈ {0, ½, 1} — never for a
  rational nonzero taper. Same Lindemann class as the cone fillet.
  **Permanent wall**, and the divergence is documented on the class
  docstring (0.33% of removed volume at b=0.1, 4.9% at 0.4, 16.1% at 0.8)
  so nobody mistakes the semantic gap for a defect when diffing against a
  Parasolid-derived kernel.

**WRONG GREEN #3 (the §12 leftover), fixed.** `fillet(DisjointUnion)` ran
member-wise with no touching witness: the bossed plate rounded its BURIED
base rim as if exposed and kept the contact patches as internal walls —
2464 + (425/3)π + 3π² ≈ 2938.67 where the composite is
**2464 + (473/3)π − π² ≈ 2949.45** (matrix boss shape, r=1). The composite
path mirrors `_shell_bossed_plate` off the shared `_bossed_plate_spec`:
rounded plate punched at R+r, the CONCAVE junction quarter torus (tube
circle (R+r, pz1+r), k0=2 span=1, sense False — a blend that ADDS material,
the planar path's reentrant-edge precedent), boss wall, convex top-rim
quarter torus, cap at R−r. Junction term by exact Pappus:
`V_add = πr(2Rr+r²) − π²r²(R+r)/2 + 2πr³/3` (needs π² — PiPoly). A blind
bore keeps its SHARP rims (the DrilledSolid hole precedent); bored cell
`2464 + (458/3)π − π²`. Both cells verified against 2D quadrature AND a
20M-sample Monte-Carlo membership test BEFORE construction (z = +1.13,
+0.94 at 3σ); goldens in `tests/golden/test_blend_family.py`. Touching
members outside the pattern refuse via the same strict bbox-separation
witness shell got in #120 (`members_strictly_separated`); strictly
separated members still fillet member-wise, pinned.

**Overflow is a wall with two pinholes, and now says so as data.** A blend
radius exceeding its face clips the quarter arc to a circular segment
whichever way the overflow resolves; segment area
`r²arccos(d/r) − d√(r²−d²)` is transcendental except **d/r ∈ {1/2, √3/2}**
(d/r = 1/2 → `r²(π/3 − √3/4)`, ℚ[√3][π], meshing gated on K3.7 twelfths).
Every overflow site (constant and variable selected-edge fillets, all four
bossed-plate fit guards) now refuses with `predicate="blend_overflow"`,
the measured radius/room/ratio, and the two admissible ratios in the
remedy. Never clamp; never widen `Torus(k0, span)` to general angles.

**Setback corners are a SPEC wall, not a field wall.** The n-sided setback
patch is a vendor-defined freeform surface; any "exact setback volume"
would be exactness about a fiction. Refusal by name is the finished answer;
the degenerate case (equal radii, setback = r) is RoundedBox's sphere
octant. Related: K5.3 adjacent variable edges stay refused — a sphere
octant at matched vertex radii is C0-watertight but NOT G1 against the
taper cones; if K5.3 picks it, the doc must say C0.

**Still open in the family**, in value order: full-round rib tip
(half-cylinder r = t/2 + quarter-sphere caps, exact ℚ[π], machinery
exists); 45°/135° planar corners (ℚ[√2][π], refused by name in
`_fillet_profile`); cylinder×cylinder and off-axis face pairs (elliptic
integrals — permanent); `chamfer(DisjointUnion)` pile answer (see §12's
leftover bullet, now fillet-free).
