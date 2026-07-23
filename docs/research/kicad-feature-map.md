# KiCad feature map — every feature, agent-first

Audited against KiCad 10.0 (menus + `kicad-cli` surface enumerated on a
live install). The translation rule: a KiCad feature is a menu item a
human clicks; the gitcad equivalent is an MCP tool, a check, or a
projection an agent calls — same capability, different actor. Status is
honest: ✅ shipped · 🟡 partial · ❌ missing.

## 1. Schematic editor (eeschema)

| KiCad | agent-first form | status |
|-------|------------------|--------|
| Place symbols | `schematic_author` place ops; built-in lib + imported lib_symbols | ✅ |
| Draw wires / junctions | `SheetEditor.wire/connect/junction`; netlist derived FROM geometry | ✅ |
| Local / global / hierarchical labels | labels in authoring + import; hierarchy flattened with KiCad semantics | ✅ |
| Power symbols / no-connect | power flags name nets; nc markers type pins `no_connect` | ✅ |
| Hierarchical sheets (import) | recursive import, sheet pins bridge structurally, scoped names | ✅ |
| Hierarchical sheets (authoring) | `SheetEditor.sheet()` subsheet instances + hier/global labels; same hier_merge engine as import (equivalence-tested); reuse via `ref_map` | ✅ |
| Sheet reuse (one file, N instances) | per-instance refs from KiCad `instances` paths | ✅ |
| **Buses / bus entries / bus aliases** | grouped-net vocabulary + fan-out helper | ❌ |
| ERC | pin-type matrix + system ERC across sheets | ✅ |
| **ERC/DRC exclusions (waivers)** | reviewed, persistent waiver records (a check you silence must leave a trace) | ❌ |
| Electrical envelope checking | — KiCad has none; ADR-0015 type system | ✅ (beyond) |
| **Annotation (auto ref numbering)** | `schematic_annotate` deterministic renumber | ❌ |
| Netlist export (kicadsexpr/spice…) | SPICE ✅ (`to_spice`); kicad netlist export for interop | 🟡 |
| Simulation (ngspice) | sim-as-test: op assertions per commit | ✅ |
| BOM | `bom`/`bom_csv` + MPN-atomic parts + assembly_bom | ✅ |
| Plot PDF/SVG/DXF | schematic SVG ✅ (auto-layout + sheet fidelity); PDF/DXF of sheets | 🟡 |
| Text / graphic annotations on sheets | notes in authoring + render | ❌ |
| **Net classes** | named net groups binding DRC rules + envelope specs | 🟡 (DRC rules are net-scoped; no named classes) |
| Symbol fields / properties | `attrs` free-form + `pin_specs` typed | ✅ |
| Find/replace, cross-probe | GUI cross-probe (sch ↔ 3D/board) | ❌ (GUI queue) |

## 2. PCB editor (pcbnew)

| KiCad | agent-first form | status |
|-------|------------------|--------|
| Footprint placement | Board components + placement ops | ✅ |
| Interactive routing | `route()` — wrong-net refused, auto-vias; not push-and-shove | ✅ (agent form) |
| **Autorouting assist** | net-order suggestion + simple maze router for agents | ❌ |
| Zones / pours | first-class: model, Gerber G36/G37, DRC, connectivity | ✅ |
| **Keepout / rule areas** | zone kind `keepout` + DRC enforcement | ❌ |
| DRC | net-scoped RulePacks, poly clearance, edge, drill | ✅ |
| **Courtyard overlap check** | courtyards exist; overlap check missing | ❌ |
| Copper connectivity | union-find touch graph, pads_with_nets honesty | ✅ |
| **Length tuning / diff pairs** | length report per net + matched-pair rule | ❌ |
| Teardrops | generator op | ❌ |
| **Silkscreen text (refs/values)** | Gerber legend text (courtyards only today) | ❌ |
| >2 copper layers | honest refusal today; layer-count model | ❌ |
| Forward annotation (sch→pcb sync) | `annotate_board` (63 pads on the real Altair) | ✅ |
| Back annotation | board→schematic writer | ❌ |
| 3D viewer | board_to_model bridge + WebGL viewer | ✅ |
| Gerbers / drill / position | X2 + Excellon + PnP, byte-deterministic | ✅ |
| STEP/GLB/STL export of board | bridge → model exporters | ✅ (STEP/STL) |
| **IPC-2581 / ODB++ / GenCAD / IPC-D-356** | modern fab-exchange exporters | ❌ |
| Board statistics | counts/areas report (trivial over our model) | ❌ |
| Import Eagle/Altium/etc. boards | importers beyond .kicad_pcb | ❌ |
| Render PNG (3D) | headless viewer screenshot path | 🟡 |

## 3. Symbol & footprint editors / libraries

| KiCad | agent-first form | status |
|-------|------------------|--------|
| Symbol libraries | built-in generator lib + imported lib_symbols + registry | 🟡 |
| Footprint libraries | registry parts, content-addressed shared assets | ✅ |
| **Footprint wizards (QFP/BGA/…)** | parametric generators: `footprint_gen("QFN", pins=32, pitch=0.5)` — perfect agent fit | ❌ |
| Library conventions (KLC) | registry validate.py gates + trust tiers | ✅ |
| Datasheet linkage | hash-anchored datasheet refs (%PDF verified) | ✅ (beyond) |

## 4. Project manager / cross-cutting

| KiCad | agent-first form | status |
|-------|------------------|--------|
| New project | `gitcad-init` (root .gitcad, merge driver, CI, reqs) | ✅ |
| Jobsets (`kicad-cli jobset run`) | `release()` all-or-nothing + CI workflows | ✅ |
| Plugin system (Python/IPC) | the MCP surface IS the API | ✅ |
| Project templates | init `--template` | ❌ |
| Undo/redo, autosave, file locking | git; semantic merge instead of locks | ✅ (beyond) |
| Version control integration | native: review gates, semantic diff/merge, lots | ✅ (beyond) |
| Interactive GUI editing | deliberate non-goal v1: agents author, humans review | — |

## Status after the parity push (all priorities shipped)

Everything above marked ❌/🟡 was worked through in two tiers. Final
state — updated statuses for the previously-missing rows:

| feature | status | note |
|---------|--------|------|
| Net classes | ✅ | glob-scoped, override pack defaults per net |
| Keepouts + courtyard overlap | ✅ | zone kind=keepout; named DRC violations |
| Silkscreen refs | ✅ | built-in stroke font, rasterize-verified |
| Annotation | ✅ | reading-order, existing refs never move |
| Footprint generators | ✅ | chip/SOIC/QFN(+EP)/header |
| Buses | ✅ | visual per KiCad semantics; members unify by label |
| ERC/DRC waivers | ✅ | reasoned, visible, stale-waiver-flagging |
| Board stats | ✅ | + net lengths |
| Length tuning (check half) | ✅ | matched-pair tolerance violations |
| Back annotation | ✅ | values board→sch; board-only refs reported |
| Netlist export (kicadsexpr) | ✅ | author in gitcad, lay out in pcbnew |
| IPC-D-356 | 🟡 | records emitted per spec; not yet run on a physical tester |
| Sheet text annotations | ✅ | authoring + import + render |
| Eagle import | 🟡 | .sch netlist-level (explicit XML nets); board geometry later |
| Sheet reuse (file instanced twice) | ✅ | `(path "/root/sheet-uuid" (reference ..))` resolved per instance; netlist matched against kicad-cli oracle; genuine ref collisions still fail loud |
| Multi-layer (2–16 copper) | ✅ | top/in1..inN/bottom; per-layer DRC/connectivity/Gerbers |
| Blind/buried vias | ✅ | `Via.layer_from/layer_to` span; span-aware Gerber flash, per-span drill files, DRC/connectivity, KiCad import, IPC-2581 `<Span>` drill layers (kicad-cli oracle-matched) |
| IPC-2581 (rev C) | ✅ | conformance-benchmarked element-for-element vs kicad-cli's own export on the real board (holes 58=58, components identical, nets consistent); in the fab package |
| ODB++ | ✅ | full job tree (matrix/features/components/span drills/cadnet); structure copied from kicad-cli's ODB++ and census-checked on the real board (bottom/drill exact; top delta = NPTH-as-mech-port modeling + 0.005mm rounding twins) |
| GenCAD 1.4 | ✅ | $BOARD/$PADS/$PADSTACKS/$SHAPES/$COMPONENTS/$DEVICES/$SIGNALS/$ROUTES, INCH units, deterministic; grammar mirrored from kicad-cli's export |
| Altium import | 🟡 | ASCII PcbDoc importer (components/pads/tracks/vias/nets, drops reported); binary OLE refused with the working path (KiCad Non-KiCad-Board import → .kicad_pcb) |
| Autorouting assist | ✅ | grid maze router (Dijkstra, via-cost, clearance-aware obstacle grid, via-size margins); result gated by DRC+connectivity; honest no-path refusal |
| Teardrops | ✅ | generator: same-net wedges at track→barrel junctions, idempotent, DRC-gated |
| Push-and-shove (interactive) | — | deliberate non-goal: agents re-route; humans review |
| Schematic PDF plot | ✅ | vector PDF of the drawn sheet (wires/symbols/labels/subsheet boxes), zero-dep writer, deterministic |

Deferred means: honest refusal or documented workaround today, with the
design intent recorded here — never a silent gap.
