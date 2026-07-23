# SolidWorks feature map — every workbench, agent-first

Audited against the SolidWorks 2024-era interface (CommandManager tabs:
Features / Sketch / Surfaces / Sheet Metal / Weldments / Mold Tools /
Evaluate / MBD, plus the assembly and drawing environments and the
system-level machinery around them). Same translation rule as the KiCad
map: a SolidWorks feature is a button a human clicks; the gitcad
equivalent is an MCP op, a check, or a projection an agent calls.
Status is honest: ✅ shipped · 🟡 partial · ❌ missing · — non-goal.

## Why everyone uses SolidWorks — the actual moats

1. **Kernel robustness on ugly geometry.** Parasolid plus 30 years of
   edge-case hardening: fillets that resolve on tangent chains, shells
   that survive drafted ribs, drafts on complex parting lines. Our
   OCCT is the same *class* of kernel but with less armor; we mitigate
   with honest failure (an op that fails says so) rather than pretending.
2. **The feature tree as an editing surface.** Rollback bar, reorder,
   suppress, edit-any-feature-and-regenerate. This is design *intent*
   kept live. gitcad's answer is structurally stronger — the tree IS
   the text file, editing is a diff, identity is lineage-stable
   (ADR-0003) — but several verbs (suppress, reorder-with-check) need
   first-class ops.
3. **Sketcher inference.** Constraints appear as you draw. Agents don't
   need inference — they declare constraints (ADR-0013 solver) — so
   this moat doesn't translate; it's a human-hand optimization.
4. **Configurations + design tables.** One part file that is a whole
   product family (M3×8, M3×10, M3×12...). THE biggest modeling gap in
   gitcad today: our documents are one-geometry. Agent-first form is
   obvious and better: named parameters + a variants table = a part
   that is a *function*, built and tested per-variant in CI.
5. **Manufacturing workbenches.** Sheet metal (flat pattern → DXF is
   the mech Gerber), weldments (cut lists), hole wizard, mold tools.
   These win real engineers because the output is what the shop needs.
   Sheet metal is our single highest-value missing capability.
6. **Drawings a QA department accepts.** Full GD&T, datums, surface
   finish, weld symbols, standards compliance. We have associative
   dims/sections/BOM; the tolerance layer is missing.
7. **Ecosystem gravity.** Toolbox, PDM, FEA/CAM add-ins, a trained
   workforce, file-format lock-in. Our counters: registry + MPN-atomic
   bought parts (Toolbox), git + semantic merge (PDM, strictly better),
   requirements-as-code + sim-as-test (the seed of analysis), and
   text-native files that never lock anyone in.

## 1. Part modeling (Features tab)

| SolidWorks | agent-first form | status |
|---|---|---|
| Extruded/Revolved boss & cut | `extrude`/`revolve` add/cut | ✅ |
| Swept boss/cut | `sweep` | ✅ |
| Lofted boss/cut | `loft` (+ ruled) | ✅ |
| Boundary boss | loft covers common cases; true boundary surfaces | ❌ defer |
| Fillet (constant radius) | `fillet` on lineage-stable edge refs | ✅ |
| Variable-radius / face / full-round fillet | per-edge radius table | ❌ |
| Chamfer | `chamfer` | ✅ |
| Shell | `shell` | ✅ |
| **Draft** | ✅ `draft` op: selected faces (lineage-stable ids), pull dir, neutral plane; non-draftable faces refused loud | ✅ |
| **Rib** | ✅ `rib` op: wall along a segment, exact-volume-tested | ✅ |
| Hole Wizard | `hole` (plain/cbore/csink/pilot) | ✅ |
| **Threads (cosmetic + modeled)** | 🟡 thread spec as data on holes, surfaced in drawing callouts ("M3x0.5-6H (Ø2.5)"); modeled helical cut later | 🟡 |
| Linear/circular pattern | `pattern_linear` / `pattern_circular` | ✅ |
| Mirror | `mirror` | ✅ |
| Table-driven pattern | placements-as-data pattern (agent-natural) | ❌ |
| Scale | ✅ `scale` op (uniform factor or fx/fy/fz) | ✅ |
| Combine (booleans) | `boolean` fuse/cut/common | ✅ |
| Split body | ✅ `split` op: axis-aligned plane, keep above/below, self-sized half-space | ✅ |
| Move/Copy body | `move` (translate/rotate) | ✅ |
| Wrap / Dome / Freeform | — | ❌ defer (niche) |
| Reference planes | sketch planes incl. sketch-on-face | ✅ |
| Reference axis/point/coordinate system | part `Frame`s at interface level | 🟡 |
| **Equations / global variables** | ✅ named parameters (`=expr`, degree trig, cross-references, cycle-detection); ids minted from expression text so re-valuing never re-identifies | ✅ |
| **Configurations / design tables** | ✅ named override sets in the document; whole table re-resolves per variant; every variant builds with identical feature ids | ✅ |
| Helix/spiral curve | ✅ `kernel.helix` + `pipe` sweep; `spring` intent op (volume-verified vs analytic wire length) | ✅ |

## 2. Sketching

| SolidWorks | agent-first form | status |
|---|---|---|
| Line/arc/circle/rect profiles | sketch profiles | ✅ |
| Splines | spline profile segments | ❌ |
| Dimensions + relations | ADR-0013 constraint solver (declared, not inferred) | ✅ |
| Auto-relation inference | — agents declare intent; inference is a mouse optimization | — |
| Sketch on face | ✅ | ✅ |
| 3D sketch | 3D polyline/curve paths (sweeps, weldments need it) | ❌ P5 |
| Convert/offset entities | derive profile from existing geometry | ❌ |
| Sketch text | stroke-font text profiles (engrave/emboss) — font already ships in ECAD silkscreen | ❌ P8 |

## 3. Surfaces

Extrude/revolve/loft/sweep build solids directly; the dedicated surface
suite (offset, knit, trim, thicken, fill, ruled surface) is ❌ deferred:
OCCT supports all of it, demand should pull it in. Industrial-design
surfacing is explicitly not the v1 fight.

## 4. Sheet metal — ✅ shipped (P3)

| SolidWorks | agent-first form | status |
|---|---|---|
| Base flange / edge flange / tab | ✅ declarative base + full-width flange chains (angle/radius/direction, holes per wall) | ✅ |
| Bend allowance (K-factor/bend table) | ✅ BA=θ(R+K·t), OSSB=(R+t)tan(θ/2); machine-readable bend table | ✅ |
| Hem / jog / closed corner | later stages | ❌ |
| **Flat pattern** | ✅ analytic unfold, hand-calc-exact; DXF R12 layers CUT/BEND_UP/BEND_DOWN/HOLES | ✅ |
| Forming tools | — | ❌ defer |

Sheet metal is "the mech Gerber": the flat-pattern DXF + bend lines is a
manufacturing handoff artifact exactly like the fab package, and most
enclosures (including the Altair case class of parts) are bent metal or
could be. This should land before any surfacing work.

## 5. Weldments / Mold tools

Weldments (structural members along 3D sketches, trim/extend, cut lists)
❌ — blocked behind 3D curves (P5), then a natural profiles-from-registry
play. Mold tools (parting lines, core/cavity) ❌ defer; draft analysis
(Evaluate) is the nearer-term piece.

## 6. Evaluate tab

| SolidWorks | agent-first form | status |
|---|---|---|
| Measure | kernel `measure` + viewer measure tools | ✅ |
| Mass properties | `mass_props` (validated vs SW output earlier) | ✅ |
| Interference detection | assembly interference (real solids) | ✅ |
| Clearance verification | `interference_clear` requirements kind | ✅ (beyond: versioned, CI-gated) |
| Section views | drawing sections + viewer | ✅ |
| Sensors/alerts | requirements-as-code | ✅ (beyond) |
| Draft analysis | min-draft-angle check per pull direction | ❌ (pairs with Draft op, P4) |
| Thickness analysis | min-wall check (moldability) | ❌ |
| Curvature/zebra | — | ❌ defer |
| SimulationXpress / FEA | — honest defer: no fake physics; sim-as-test philosophy extends when a real solver integrates | ❌ defer |
| Motion studies | mate solver is static placement | ❌ defer |
| Costing | process cost model per part | ❌ defer (good future agent play) |
| DimXpert / MBD (GD&T) | tolerance data model on dims/features | ❌ P7 |

## 7. Assembly environment

| SolidWorks | agent-first form | status |
|---|---|---|
| Insert component + standard mates | `mate_solve` (ADR-0014) | ✅ |
| Advanced/mechanical mates (gear, cam, slot, limit) | — static subset only | ❌ defer |
| Assembly patterns | instance pattern helper | ❌ (small) |
| In-context editing (external refs) | cross-part derive; the mech↔ecad co-design loop IS this | 🟡 (ecad↔mech ✅; mech↔mech refs ❌) |
| Exploded views | exploded-view feature + GUI | ✅ |
| BOM | assembly BOM + balloons + MPN-atomic parts | ✅ |
| Toolbox (hardware library) | registry + bought parts, content-addressed | ✅ (beyond) |
| **Smart fasteners** | fastener generator at `mech.bolt` ports (ports already exist on every mounting hole) | ❌ P6 |
| Large-assembly modes | — not the bottleneck at our scale | — |

## 8. Drawing environment

| SolidWorks | agent-first form | status |
|---|---|---|
| Standard/projected views | HLR engine | ✅ |
| Section views | ✅ | ✅ |
| Detail views | scaled crop view | ❌ P8 |
| Broken / crop views | — | ❌ defer |
| Associative dimensions | hole callouts, position dims | ✅ |
| **GD&T: FCF, datums, tolerances** | tolerance objects bound to lineage-stable entities | ❌ P7 |
| Surface finish / weld symbols | annotation set | ❌ |
| BOM table + balloons | ✅ | ✅ |
| Revision table | — git history IS the revision table; projection possible | ✅ (beyond) |
| Sheet formats / standards | title block basic; ASME/ISO styles | 🟡 |

## 9. System machinery

| SolidWorks | agent-first form | status |
|---|---|---|
| Feature tree rollback/reorder/edit | text-native: the tree is the file; edit + regen; lineage-stable ids keep downstream refs alive | ✅ (beyond) |
| Suppress/unsuppress feature | `suppressed` flag honored by regen | ❌ (small, useful for variants) |
| Undo / autosave | git | ✅ (beyond) |
| PDM (vault, workflows) | git + review gates + semantic merge + lots | ✅ (beyond) |
| FeatureWorks (recognition) | recognize v1 (verified hole recovery) | 🟡 |
| Appearances / RealView / render | viewer shading only; photoreal | ❌ defer |
| Macros / API | the MCP surface is the API | ✅ (beyond) |
| File format gravity | text-native, importers, never locked in | ✅ (beyond) |

## The attack order

What actually converts a SolidWorks user, in order of leverage:

1. ~~P1 Named parameters + equations~~ — SHIPPED: `gitcad.expr` +
   `Document.parameters` + build-time resolution + `model_parameters` MCP.
2. ~~P2 Configurations / design tables~~ — SHIPPED: `Document.configurations`
   + per-variant build + `model_configurations` MCP.
3. ~~P3 Sheet metal + flat pattern DXF~~ — SHIPPED: `gitcad.sheetmetal`
   (declarative flanges, exact K-factor unfold, shop DXF, DFM checks,
   folded solid via the ordinary Document pipeline).
4. ~~P4 Draft + rib + scale + split~~ — SHIPPED as document ops with
   OCCT volume proofs (draft/thickness *analysis* checks remain open).
5. ~~P5 Helix + springs + thread specs~~ — SHIPPED (helix/pipe kernel
   ops, spring feature, thread-as-data on holes in callouts); modeled
   thread cuts and general 3D sketch paths remain open.
6. **P6 Fastener generator** — Toolbox, agent-first: every `mech.bolt`
   port can grow a correct bolt stack automatically.
7. **P7 Tolerances/GD&T as data** — the QA handshake.
8. **P8 Detail views + sketch text** — drawing completeness, engraving.

Deferred with reasons recorded: FEA and motion (no fake physics — wait
for a real solver integration), surfacing suite, mold tools, weldments,
photorealistic rendering, mechanical mates.
