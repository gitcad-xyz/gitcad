# gitcad Feature Map — synthesis of the Fusion & Altium taxonomies

> Derived from `fusion-feature-taxonomy.md` (~280 features) and
> `altium-feature-taxonomy.md` (~330 features). This is the planning tiering for
> gitcad — not a commitment to build everything. The tiers:
>
> - **MVP** — can't call it a CAD tool without it. Build first.
> - **PARITY** — needed to compete for real engineering work. Build second.
> - **LATER** — legitimate features, deliberately deferred.
> - **SKIP** — GUI-era compensation or business-model artifacts that dissolve in
>   an agent-first, git-native architecture. Not built; the *need* is met
>   differently or vanishes.
> - **DIFF** — differentiators: things gitcad does that the incumbents
>   structurally cannot. These justify the project.

The single most important observation from both sweeps: **a large fraction of
both products is compensation for being GUI-first, file-opaque, and
cloud-walled.** Fusion has no branching ("linear versions + milestones" is
official); Altium gates collaboration, library governance, lifecycle, and
release management behind Altium 365 subscription tiers. gitcad gets those from
git + text + the part standard *for free*. The moat is not feature count.

---

## Part A — gitcad-mech vs. Autodesk Fusion

### A1. Solid modeling — MVP core

| Tier | Features |
|---|---|
| **MVP** | Extrude, Revolve, Sweep, Loft (with guide rails/end conditions), primitives (box/cyl/sphere/torus/coil/pipe), Boolean combine (join/cut/intersect), Fillet (constant + variable + G2), Chamfer (all 3 modes), Shell, Draft, Hole feature (simple/cbore/csink/tapped + thread tables), patterns (rect/circ/path) + Mirror, Split Body/Face, Offset Face, Scale |
| **PARITY** | Rib/Web, Emboss, Boundary Fill, Replace Face, Silhouette Split, plastic features (boss, snap-fit, wall-thickness rules), delete-face-with-heal |
| **LATER** | Direct editing on imported geometry (needs robust local ops), feature recognition on imports |
| **SKIP** | Press Pull (a GUI gesture — agents state intent directly); Autodesk Assistant (the entire product is that) |

Note: the Hole feature is disproportionately important — holes + threads + standard tables are the workhorse of real MCAD, they're pure data + simple geometry, and they're highly agent-legible. Prioritize above exotic surfacing.

### A2. Sketching — MVP core, with an agent twist

| Tier | Features |
|---|---|
| **MVP** | All 12 constraint types (coincident, tangent, equal, parallel, perpendicular, H/V, fix, midpoint, concentric, collinear, symmetry, G2), full entity set (lines/arcs/circles/rects/polygons/ellipses/slots/conics/splines/text), dimensions with expressions + user parameters, **fully-constrained detection as a machine-readable check** |
| **PARITY** | 3D sketching, project/intersect/include-3D-geometry, sketch patterns, curvature-comb data |
| **SKIP** | Constraint *inference while dragging* (a GUI affordance — agents declare constraints explicitly, which is strictly more reliable) |

Agent twist: Fusion tells a human "sketch is fully constrained" by color. gitcad exposes DOF-remaining as data (`sketch.dof() -> 0`), making under-constraint a lintable, CI-checkable condition. That's better, not just equivalent.

### A3. Parametrics & timeline — already gitcad's spine

| Tier | Features |
|---|---|
| **MVP** | Feature history (= the Document feature tree, already built), user parameters + expressions, edit-upstream-with-recompute (= stable identity, ADR-0003), suppression |
| **PARITY** | Configurations (tables of parameter/suppression variants) — maps beautifully to text: a config is a patch-set over the base document; **config tables become data files, diffable in git** |
| **SKIP** | Timeline scrubbing/rollback UI (git *is* the timeline); milestones (git tags); "capture design history" toggle (history is always on — it's the source) |

Fusion's Configurations are **[PREMIUM]**. gitcad's are a text overlay — free, diffable, mergeable. Cheap win, listed as **DIFF-adjacent**.

### A4. Assemblies — MVP via the Part standard

| Tier | Features |
|---|---|
| **MVP** | Component/instance model, joints (rigid, revolute, slider, cylindrical, pin-slot, ball, planar) as typed **port-to-port mates** (ADR-0008 frames/ports), joint limits, rigid groups, ground, interference detection, mass properties roll-up |
| **PARITY** | Motion links (gear ratios), motion studies, contact sets, in-context (top-down) editing, derived designs |
| **LATER** | Large-assembly simplification/LOD |
| **SKIP** | XRef version-update UI (the lockfile + `gitcad update` is the mechanism, ADR-0009); reserve/checkout (git branches) |

### A5. Drawings — MVP deliverable (the "be a mechanical engineer" requirement)

| Tier | Features |
|---|---|
| **MVP** | Base/projected/section/detail views via HLR, smart + linear/aligned/angular/radius/diameter/ordinate dimensions (associative to stable IDs), tolerances (symmetric/deviation/limits), GD&T (feature control frames, datums), center marks/lines, hole callouts, parts list + balloons, title blocks, ASME + ISO, PDF + DXF export |
| **PARITY** | Break/broken-out views, auto-dimension strategies, hole/bend tables, drawing templates, baseline/chain dims |
| **DIFF** | **Drawing-lint** — machine-checkable drafting-standard conformance (missing datum, un-dimensioned feature, duplicate dims) as CI; incumbents rely on human review |
| **SKIP** | Manual dimension "tidy-up" gestures (auto-layout is the only mode agents use) |

### A6. Surfaces, sheet metal, mesh

| Tier | Features |
|---|---|
| **PARITY** | Surface extrude/revolve/sweep/loft, patch, trim/extend/stitch/thicken, ruled surface; continuity analysis **as data** (zebra/curvature/draft → arrays, not pictures). Sheet metal: rules (thickness/K-factor/reliefs), flange/contour/lofted flange, hem variants, unfold/refold, rip, flat pattern + **DXF export** (the actual deliverable for laser/waterjet) |
| **LATER** | Mesh import/repair/convert (scan-to-CAD), T-spline-equivalent freeform (see note) |
| **SKIP** | Forms/T-spline *sculpting environment* — push-pull vertex manipulation is the single most GUI-bound workflow in Fusion; the agent-native equivalent is intent-driven freeform (target curvature, matched boundaries) which is **LATER** research, not a port |

### A7. CAM, simulation, generative, rendering

| Tier | Verdict |
|---|---|
| **LATER (CAM)** | Real CAM is a second product. But the *fabrication outputs that make gitcad-mech usable* are earlier: **flat-pattern DXF (PARITY)**, STL/3MF export (MVP), 3D-print orientation checks (LATER). Full milling/turning strategies: partner or defer; the post-processor world (.cps) is its own ecosystem |
| **LATER (Sim)** | Don't write an FEA solver. Define a **`SimBackend` seam** exporting to open solvers (CalculiX, Elmer) — mesh + loads + constraints from the model, results as data. Fusion's own story is "send to Ansys"; ours is the same shape, open |
| **SKIP (Generative)** | Cloud-token generative design is Autodesk's business model, not a user need gitcad must meet in v1. An agent iterating against mass/stress checks is a primitive form of it already |
| **LATER (Render)** | Headless raster/glTF render is **MVP as the agent's eyes** (already in seams); *photoreal* rendering, HDRI scenes, turntables, animation storyboards are marketing-asset features — LATER |

### A8. Data management — the DIFF column

| Fusion has | gitcad answer |
|---|---|
| Linear versions + milestones, **no branching/merging** | **git: branch, merge, rebase, PR, blame — DIFF** |
| Reserve/checkout conflict avoidance | Branches + semantic merge on text — **DIFF** |
| Cloud hub, per-folder permissions, separate collaboration SKU | Any git host; permissions are the host's (GitHub/GitLab); free — **DIFF** |
| Version promote/restore | `git revert`/`checkout` — free |
| Comments/markup in web viewer | PR review comments on *semantic diffs* (volume delta, feature add/remove, before/after renders) — **DIFF** |
| Fusion Manage (PLM, paid extension) | Release = tag + lockfile + generated artifacts; change orders = PRs with required reviewers (CODEOWNERS) — **DIFF** |
| AnyCAD associative cross-format refs | STEP import (PARITY); associative foreign refs LATER |

---

## Part B — gitcad-ecad vs. Altium Designer

### B1. Schematic capture — MVP, but text-first

| Tier | Features |
|---|---|
| **MVP** | Net/wire/bus/net-label model, ports & hierarchical sheets (hierarchy = document tree), power ports, multi-part components (gates), NetTie, no-ERC directives, **ERC with pin-type connection matrix + configurable severities**, designator annotation (incl. multi-part gate packing), netlist export |
| **PARITY** | Multi-channel (Repeat() instantiation — maps perfectly to text macros/part instancing), variants (fitted/not-fitted/alternate-part = patch-set overlay, same mechanism as mech configurations), harness/signal-harness bundling, blanket directives, back-annotation |
| **DIFF** | Schematic **source is text** → schematic diff/merge/blame in git; Altium's graphical compare is a viewer, ours is the substrate |
| **SKIP** | Smart Paste, alignment/distribution gestures, "find similar objects" query UI (agents query the model directly); sheet templates as a *product feature* (they're just files) |

Design note: schematic *rendering* (the human-readable diagram) is a **projection** of the netlist source, like drawings are of the 3D model — SVG out, auto-laid-out, versioned as an artifact. Hand-placed aesthetic schematic layout is supported but optional data, not the source of truth.

### B2. Component & library management — the registry (ADR-0010)

| Tier | Features |
|---|---|
| **MVP** | Atomic component model (symbol+footprint+3D+pin-map+parameters in one versioned Part), shared content-addressed assets, IPC-7351 footprint *generator* (parameter-driven, agent-perfect), symbol generator from pin tables, component-completeness rule checks |
| **PARITY** | Multiple footprint variants per component, alternate display modes, supplier/MPN parameters, lifecycle states |
| **DIFF** | Everything Altium gates behind 365: item revisions (= content-hash versions), lifecycle, where-used (registry query), concurrent library editing (git), library health (registry CI), component requests (issues) — **all structural in gitcad, all subscription features in Altium**. Plus trust tiers (`draft/verified/reviewed/proven`) and datasheet-derived agent verification, which Altium has no analog for |
| **SKIP** | DbLib/SVNDbLib/IntLib format zoo (one canonical form + importers LATER); manufacturer part *search panel* (runtime supply-data service, ADR-0010, not baked into the tool) |

### B3. PCB layout — MVP is the data model + DRC, not the gestures

The Altium taxonomy's ~35 interactive-routing entries (push/shove modes, hug,
follow, glossing, look-ahead…) are **one feature** in an agent-first tool: a
router that produces rule-clean geometry. The GUI gesture vocabulary is the part
that dissolves.

| Tier | Features |
|---|---|
| **MVP** | Board outline (+ from mech envelope — co-design!), layer stack model, placement with courtyard checks, tracks/arcs/vias (through + blind/buried/µvia data model), pads/pad-stacks, polygon pours with priority + thermal reliefs, keepouts, net classes, ratsnest-equivalent connectivity state **as data** (`unrouted_count`), teardrops, via stitching (programmatic) |
| **PARITY** | Differential-pair routing, length matching + tuning (meander generation is algorithmic — agent-friendly), fanout generation, rooms, panelization, rigid-flex stack regions, testpoints |
| **LATER** | Autorouting beyond rule-driven completion (ActiveRoute-class guided routing), HDI planning aids, embedded components, printed electronics, 3D-MID, wire bonding |
| **SKIP** | The interactive-gesture layer (conflict modes, follow mode, board insight lens, heads-up display); Situs legacy autorouter |

### B4. Rules & DRC — MVP crown jewel

Altium's rule system is its best idea and it's *already agent-shaped*: scoped,
queryable, machine-checked. Adopt the architecture wholesale.

| Tier | Features |
|---|---|
| **MVP** | Query-scoped rules with priorities; the core rule set: clearance (+ object-kind matrix), short-circuit, unrouted, width, via style, annular ring, hole size/h2h, mask sliver/expansion, silk clearances, board-outline clearance, net antennae, courtyard/component clearance, height; **batch DRC with machine-readable violations** (the agent loop input); severity config |
| **PARITY** | Diff-pair rules, matched length, topology, neck-down, plane connect styles, creepage, z-axis clearance, return path, via-count/stub rules, constraint-set reuse ("rule packs" — shareable as versioned parts!) |
| **DIFF** | **DRC in CI on every commit** — Altium runs DRC in-session; gitcad makes rule-clean a merge gate. Rule packs distributed through the registry (e.g., a fab publishes its capability profile as a versioned rule pack) |
| **SKIP** | Online-DRC-while-dragging (that's the GUI loop; the agent loop is check-after-op) |

### B5. Outputs & manufacturing — MVP, it's the point of the tool

| Tier | Features |
|---|---|
| **MVP** | Gerber X2, Excellon NC drill, pick-and-place, IPC-D-356 netlist, BOM (CSV/JSON with MPNs), assembly/fab drawing basics, **release = validated, immutable, tagged artifact set** (Project-Releaser-as-code: DRC/ERC/BOM gates then tag + lock — ADR-0009 machinery) |
| **PARITY** | ODB++, IPC-2581, stackup/drill/impedance tables, variant-aware outputs, Draftsman-class board documentation (shares the mech drawing engine!), panel outputs |
| **DIFF** | Releases are reproducible from the lockfile forever; "what shipped" is a git tag; BOM compare is `git diff` on a data file |
| **LATER** | CAM editing (CAMtastic-class), supply-chain-ranked ActiveBOM sourcing (runtime service) |
| **SKIP** | Output-job GUI containers (a release recipe is a text file); 20-format legacy netlist zoo (export the 2–3 that matter, add on demand) |

### B6. High-speed, simulation, multi-board

| Tier | Verdict |
|---|---|
| **PARITY (HS)** | xSignals-equivalent (pin-to-pin path definition through series parts — pure graph data, very agent-friendly), impedance profiles from stackup (there are open field solvers), length/skew rules |
| **LATER (SI/PI)** | Don't write SPICE or a field solver. `SimBackend` seam → ngspice for circuit sim (Altium's own engine is SPICE-derived), open SI/PI where available; export handoffs (Touchstone, HyperLynx-class) |
| **PARITY (Multi-board)** | This is just **the Part/assembly standard doing its job**: boards are parts, connectors are ports, the Connection Manager is the assembly's port-mapping table, system ERC is interface checking (ADR-0008). Altium needed a separate project type; gitcad gets it from the core model |
| **LATER** | Harness design as a third body type (wires/splices/bundles — it's a first-class citizen of the part standard when it comes) |

### B7. Collaboration — the DIFF column again

| Altium has (mostly [Altium 365]) | gitcad answer |
|---|---|
| Git-backed managed projects, project history timeline | Native git, any host — **DIFF, free** |
| PCB CoDesign concurrent authoring (25-author cap, Agile Teams tier) | Branch-per-workstream + semantic merge on text; no author cap — **DIFF** |
| Web viewer + commenting | Web UI is a client of the same MCP API; PR comments on semantic diffs — **DIFF** |
| Release lifecycle, item revisions | Tags + lockfiles + content hashes — core machinery |
| Workflows/tasks engine (Pro/Enterprise) | Issues/PRs/CI on the git host |
| On-prem Enterprise Server | It's a git repo. On-prem is trivially the default option |

---

## Part C — Cross-cutting conclusions

1. **Feature-count parity is the wrong goal.** Roughly a third of both
   taxonomies is GUI gesture vocabulary or subscription-tier packaging. The
   engineering substance to match is: kernel ops, the rule/check engines, the
   drawing/output generators, and the component/part data model.

2. **The check engines are the real spine of both products** (Fusion: sketch
   constraints, interference, DRC-ish manufacture checks; Altium: ERC + the
   ~50-type DRC system). These are exactly what the agent loop needs as
   machine-readable tools, and exactly what CI can run. Build them first-class,
   headless, structured — they are simultaneously MVP features *and* the
   verification loop (ADR-0002).

3. **Both incumbents' collaboration stacks are their business model, not their
   engineering.** Fusion cannot branch; Altium meters concurrent authors.
   git + text + lockfiles deletes the entire category — the single largest
   structural advantage gitcad has, and it costs nothing because it's the
   architecture (ADR-0004/0008/0009).

4. **Shared engines to build once, in core:** the drawing/documentation engine
   (mech drawings ≡ Draftsman), the rule/violation framework (DRC ≡ ERC ≡
   drawing-lint ≡ interface checks), variants/configurations (one patch-set
   overlay mechanism), release machinery (one Releaser for both domains).

5. **Suggested build order from this map:**
   - mech: sketch+constraints → solid MVP set → measurement/validation →
     drawings (HLR) → STEP/DXF/STL out → assemblies via part standard
   - ecad: atomic component + netlist model → ERC → board data model → DRC →
     Gerber/drill/BOM out → placement/routing
   - core (both): rule/violation framework, drawing engine, release machinery,
     variants overlay — extracted as they prove common.
