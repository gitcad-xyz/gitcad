# Altium Designer — Feature Taxonomy (research input)

> Raw competitive research compiled from official Altium documentation
> (altium.com/documentation/altium-designer, v25 tree), the Altium features
> pages, Altium 365 docs, and MCAD CoDesigner docs. **[Altium 365]** marks
> features requiring a connected Altium 365 Workspace.
>
> Status: research input for the gitcad-ecad roadmap. ~330 discrete features
> across 14 areas. See `feature-map.md` (forthcoming) for the gitcad tiering.

## 1. Schematic Capture

**Documents & environment**
- **Schematic document setup** — configurable sheet formatting, standard/custom sizes, margins, zones, borders, title blocks.
- **Schematic templates** — reusable sheet templates (title block, parameters) applied per document or project-wide.
- **Document/project parameters** — user-defined parameters with special-string substitution into sheet text.
- **Schematic placement & editing techniques** — selection, dragging with maintained connectivity, smart paste, alignment, distribution tools.
- **Smart Paste** — paste-transform clipboard contents into other object types (e.g., net labels into ports, wire arrays).
- **Object attribute inheritance / preferences** — per-object-type defaults ("primitive defaults") in Schematic preferences.
- **Query-driven selection (Find Similar Objects / SCH List)** — locate and batch-edit schematic objects via logical queries.

**Components on sheets**
- **Components panel search & place** — parametric search of all libraries/Workspace and drag-drop placement.
- **Manufacturer Part Search panel** — search real manufacturer parts with datasheets, parametrics, supply data, and place them directly (component created on the fly).
- **Multi-part components** — components split into multiple schematic parts (gates) with part swapping.
- **Alternate display modes** — per-symbol alternate graphical modes (e.g., IEEE vs. simple).
- **Pin swapping / part swapping (schematic side)** — swap equivalent pins/parts and back-annotate.

**Connectivity**
- **Wires** — point-to-point electrical connection object with auto-junctioning.
- **Buses & bus entries** — graphical grouping of related nets with bus-range net labels (e.g., D[0..7]).
- **Net labels** — net naming/identification on wires and buses.
- **Ports** — inter-sheet connectivity points (horizontal I/O types: input/output/bidirectional).
- **Sheet symbols & sheet entries** — parent-sheet blocks representing child sheets with mapped entries.
- **Power ports** — global power/ground net connectivity objects with multiple standard styles.
- **Off-sheet connectors** — flat-design connectivity between sheets of the same hierarchy level.
- **Signal harnesses (schematic harnesses)** — bundle dissimilar nets/buses into a single named harness with harness connectors, harness entries, and harness definitions.
- **No-ERC directive** — suppress specific electrical checks at a node (generic and specific-violation variants).
- **Parameter Set / directives** — attach parameters (e.g., net class, differential pair, rule directives) to nets via parameter set objects.
- **Differential pair directive** — mark net pairs as differential pairs at capture.
- **Net class / rule directives** — define PCB classes and rules from schematic objects/blankets.
- **Blanket directive** — apply a directive to all nets under a drawn region.
- **Compile mask** — exclude a schematic region from compilation/validation.
- **NetTie components** — legitimate short between distinct nets (documented net-tie/short pattern).

**Structure & hierarchy**
- **Flat multi-sheet design** — designs spread over sheets with global connectivity.
- **Hierarchical design** — tree-structured parent/child sheets via sheet symbols; unlimited depth.
- **Vertical connectivity scoping** — automatic/selectable net identifier scope (ports, net labels, global).
- **Sheet numbering** — automatic sheet numbering and document-number assignment across the project.
- **Create sheet from sheet symbol / symbol from sheet** — bidirectional hierarchy productivity commands.

**Multi-channel & reuse**
- **Multi-channel design** — instantiate a child sheet N times via Repeat() sheet symbols; logical channels expanded at compile.
- **Channel designator formats** — configurable room/designator naming per channel (flat or hierarchical numbering).
- **Room-based channel layout replication** — copy placement/routing of one channel to all others in PCB ("copy room formats").
- **Design reuse (snippets)** — save/reuse circuit fragments (schematic and PCB sections) from a Snippets panel.
- **Managed/reuse blocks (Design Reuse)** — Workspace-stored reusable schematic/PCB blocks. **[Altium 365]**
- **Device sheets** — read-only reusable schematic sheets stored in central locations.

**Annotation**
- **Schematic annotation** — automatic designator assignment (all or selected), with directional ordering schemes.
- **Board-level annotation** — designators unique across a multi-channel/flattened design.
- **Positional annotation (PCB-side re-annotate)** — renumber designators by board location and back-annotate.
- **Back annotation** — push PCB designator/pin/part swap changes back to schematic.
- **Annotation of multi-part components** — gate packing control during annotation.

**Validation (ERC)**
- **Project compilation/validation** — unified data model build with logical, electrical, and drafting checks ("Validate Project").
- **Error reporting matrix** — per-violation-type severity configuration (No Report/Warning/Error/Fatal) in Project Options.
- **Connection matrix** — pin-type vs. pin-type electrical compatibility matrix (e.g., output-to-output = error).
- **Messages panel violation navigation** — click-through cross-probe from violation to offending object.
- **Class generation control** — configure which component classes/net classes/rooms are generated for PCB.
- **Multi-board ERC** — connectivity checks at system level (see §6).

**Variants**
- **Variant Manager** — define assembly variants of one base design.
- **Fitted / Not Fitted components** — per-variant population control.
- **Alternate part variation** — substitute a different component in a variant.
- **Parameter variations** — per-variant parameter value overrides (e.g., resistance value).
- **Variant-aware outputs** — BOMs, assembly drawings, PDF, Draftsman, and 3D views generated per variant; not-fitted graphic marking styles.
- **Variants in sheet displays** — cross-out/marking of unfitted parts on schematic and assembly views.

**Cross-domain**
- **Cross probing & cross selecting** — select/locate objects between schematic and PCB in both directions.
- **Design synchronization (ECO flow)** — Update PCB Document / Import Changes with Engineering Change Order dialog listing every change for selective execution.
- **Component links & synchronization** — match schematic and PCB components via unique IDs.

## 2. Component & Library Management

**Component model**
- **Unified/atomic component model** — one component aggregates symbol, footprint(s), 3D model, sim model, parameters, part choices, lifecycle.
- **Multiple footprints per component** — alternate footprint models selectable per placement.
- **Model types** — schematic symbol, PCB footprint, 3D model, SPICE simulation model, IBIS model, signal-integrity model linked to a component.
- **Component parameters** — arbitrary parametric data incl. datasheet/URL links, supplier/manufacturer fields.
- **Component templates** — Workspace templates enforcing parameter sets, naming, revision naming, lifecycle definitions per component type. **[Altium 365]**
- **Component rule checks** — validation of components against required-data rules (missing models/parameters/duplicates).

**Library types**
- **Schematic libraries (.SchLib)** — file-based symbol libraries.
- **PCB libraries (.PcbLib)** — file-based footprint libraries with 3D body support.
- **Integrated libraries (.IntLib)** — compiled, verified package of symbols + models + parameters.
- **Database libraries (DbLib)** — components live in company database (ODBC/ADO); records link symbols/footprints/parameters.
- **SVN database libraries (SVNDbLib)** — DbLib plus version-controlled symbol/footprint source storage in SVN.
- **Database link file (DbLink)** — link placed design components to external database records by key field for parameter sync.
- **Workspace (managed) library** — cloud-hosted component library, single source of truth with revision control and lifecycle. **[Altium 365]**

**Creation & editing tools**
- **Symbol editor** — full schematic symbol drawing environment (pins with electrical types, IEEE symbols, drawing primitives).
- **Symbol Wizard** — grid/table-driven rapid symbol generation for high-pin-count parts.
- **Footprint editor** — pad/via/track-based footprint authoring, any pad shape, custom pad stacks, mechanical layers.
- **IPC Compliant Footprint Wizard** — parameter-driven IPC-7351 footprint generation for standard package families.
- **IPC-7351 batch generator from spreadsheet** — batch footprint creation from package dimension tables.
- **Footprint wizard (generic)** — pattern-based footprint generation.
- **3D body objects** — extruded/cylinder/sphere primitive bodies or imported STEP/Parasolid models on footprints.
- **Component Editor (Single Component mode)** — form-based authoring of one Workspace component. **[Altium 365]**
- **Component Editor (Batch mode)** — spreadsheet-like multi-component authoring/editing. **[Altium 365]**
- **Direct component editing** — edit a Workspace component in a temporary editor instance and save back as new revision. **[Altium 365]**
- **Component copying/cloning** — duplicate existing components as starting templates.
- **Concurrent library editing** — multiple librarians edit different Workspace components simultaneously without locking. **[Altium 365]**
- **Model reuse & update notifications** — shared symbols/footprints across components with where-used-driven update prompts. **[Altium 365]**

**Governance & lifecycle**
- **Item revisions** — every saved component/model change creates an immutable revision. **[Altium 365]**
- **Lifecycle states & definitions** — configurable lifecycles (e.g., New From Design → In Production → Deprecated/Obsolete) with per-state applicability guards. **[Altium 365]**
- **Lifecycle validation in design** — warnings when using obsolete/EOL component revisions.
- **Where-used traceability** — find every project/component using a given component/model. **[Altium 365]**
- **Component requests** — engineers request new/missing parts; librarians fulfill via workflow with notifications. **[Altium 365]**
- **View-only library permissions** — role-based read-only access to components. **[Altium 365]**
- **Library Health Dashboard** — Workspace-wide component data health/completeness reporting. **[Altium 365]**
- **Library Importer / Library Migrator** — one-click migration of file-based and database libraries into a Workspace. **[Altium 365]**
- **Version control for library sources** — SVN-backed storage of symbol/footprint sources.

**Sourcing**
- **Part Choices** — approved manufacturer part list per component, ranked, used by ActiveBOM. **[Altium 365 for managed part choices]**
- **Altium Parts Provider** — aggregate real-time supplier/pricing/stock feed (Octopart-backed) into panels and BOMs.
- **Supplier links on components** — attach supplier/manufacturer part linkage to components.
- **SiliconExpert integration** — part lifecycle/compliance data enrichment (subscription integration).
- **Z2Data integration** — supply-chain risk/compliance data source integration (subscription integration).
- **IHS Markit part data** — enterprise parts data source support.

## 3. PCB Layout

**Board definition**
- **Board shape definition** — draw/redefine board outline; define from selected objects or 3D body (import from DXF/STEP).
- **Board cutouts & cavities** — internal routed openings; cavity definition for embedded parts.
- **Origin, grids, guides** — Cartesian/polar grids, multiple named grids, snap guides/points.
- **Rooms** — named placement areas with room-scoped rules and channel format copying.
- **Panelization (embedded board arrays)** — step-and-repeat arrays of one or more board designs with routing/v-groove borders for fab panels.

**Placement**
- **Component placement & drag with connectivity** — connection-line-aware drag, rotation, layer flip.
- **Interactive placement alignment tools** — align/space evenly commands, paste arrays.
- **Cross-select-driven placement** — select in schematic, arrange components on PCB ("cross placement").
- **Component swapping** — swap footprint positions of two components.
- **Quick placement from schematic (drag onto board)** — place parts by dropping from schematic selection.
- **Pin/part swap on PCB** — swap electrically equivalent pins/gates during layout with ECO back-annotation.
- **Union/grouping of objects** — treat multiple objects as a movable union.
- **Component snapping/courtyard-based drag** — snap by pads, origin, or reference point.
- **3D-aware placement (under-side, dual side)** — full bottom-side placement support.
- **Replicate layout (copy room formats)** — clone placement+routing between identical channels/rooms.
- **PCB Health Check Monitor** — live dashboard of board completeness/quality metrics (unrouted nets, violations, etc.).

**Connectivity display**
- **Ratsnest/connection lines** — dynamic from-to display with net color override.
- **Net color override & highlighting** — per-net coloring across editor.
- **Board Insight system** — heads-up display, popup object insight, insight lens magnifier.
- **Single layer mode / layer visibility profiles** — focus display modes; View Configuration panel with layer sets and transparency.

**Interactive routing**
- **Interactive routing engine** — click-pad-to-route with real-time rule obedience.
- **Conflict mode: Ignore Obstacles** — route over obstacles (violations flagged).
- **Conflict mode: Push Obstacles** — shove existing tracks/vias aside.
- **Conflict mode: Walkaround Obstacles** — route around obstacles observing clearance.
- **Conflict mode: Hug & Push** — hug obstacles, push only when necessary.
- **Conflict mode: Stop At First Obstacle** — halt at blockage.
- **Conflict mode: AutoRoute on Current Layer / on Multiple Layers** — auto-completion assist modes.
- **Look-ahead routing mode** — uncommitted preview segment.
- **Auto-complete connection (Ctrl+Click)** — engine finishes the route to target automatically.
- **Loop removal** — re-route by drawing new path; old loop auto-deleted.
- **Follow mode (Shift+F)** — trace along existing contours/shapes.
- **Multi-routing (bundle routing)** — route many selected nets simultaneously with convergence/spacing control.
- **Fanout commands** — automatic escape routing of SMT/BGA pads per Fanout Control rules.
- **Track width cycling (rule min/preferred/max/user)** — hotkey width selection within rule bounds.
- **Via cycling & via types during routing** — cycle via sizes/spans; blind/buried/µvia insertion per layer stack.
- **Layer switching mid-route with auto-via** — via placed per applicable Routing Via Style rule.
- **Glossing (weak/strong/off)** — automatic route cleanup; neighbor glossing of affected nets.
- **Retrace / Apply current rules to existing routing** — re-run width/gap conformance on selected routing.
- **Corner styles & mitering** — 45°, 90°, rounded, any-angle; miter ratio control; arc corners with adjustable radius.
- **Any-angle routing** — free-angle track placement.
- **Trace auto-centering & auto-shrinking** — center between obstacles; neck down through tight gaps.
- **Pad entry protection** — preserves clean pad entries during gloss.
- **Length gauge** — live length/rule-target gauge while routing.
- **Clearance boundary display** — visualize keep-away halos while routing.
- **Interactive slicing of tracks** — cut multiple tracks at once.
- **Dragging with rubber-banding & via dragging** — maintain routed connectivity while moving parts/tracks; drag track segments with 45/arc preservation.
- **ActiveRoute** — guided semi-automated multi-net routing engine: route selected nets/guide path, layer balancing, tuning support.
- **Topological autorouter (Situs)** — full-board autorouting with strategy editor (legacy; superseded in practice by ActiveRoute).
- **Differential pair interactive routing** — paired routing with gap per rule, single-track continuation at obstacles, phase control.
- **Controlled-impedance routing** — width/gap driven by impedance profile selection in width/diff-pair rules.
- **Pin-swap-enabled routing** — route to nearest swappable pin with automatic swap ECO.

**Length tuning**
- **Interactive length tuning (accordion patterns)** — add amplitude-controlled sawtooth/rounded/trombone patterns to meet length rules.
- **Differential pair phase tuning** — intra-pair skew correction patterns.
- **Tuning driven by rules or manual targets** — target from Length/Matched Length rules, xSignals, or user value.
- **Live tuning gauge** — real-time target/limit display during tuning.

**Vias & holes**
- **Through-hole vias** — standard full-stack vias with per-layer size (pad stack) support.
- **Blind/buried vias** — layer-span-limited vias per layer stack via types.
- **Microvias (µVia)** — HDI vias with stacked/staggered spans, defined in Layer Stack Manager.
- **Back drilling definition** — controlled-depth drill pairs to remove via stubs, with Max Via Stub Length rule.
- **Via stitching** — automated stitching via arrays across polygons/nets.
- **Via shielding** — automated via fences along selected routes/nets.
- **Testpoint system** — fabrication/assembly testpoint assignment with testpoint rules and reports.
- **Pad/via templates & pad stacks** — reusable pad/via definitions; per-layer pad shapes, thermal relief control.
- **Slotted & rotated holes** — round/square/slot hole types with rotation.
- **Castellated/edge plating support** — plated board edges.

**Copper**
- **Polygon pours** — solid/hatched/none-fill copper areas with automatic pour-around per clearance rules.
- **Polygon repour & shelving** — batch repour, shelve/restore, modified-polygon DRC.
- **Polygon Manager** — centralized polygon naming, ordering (pour priority), net assignment, actions.
- **Polygon cutouts** — keep-out voids within pours.
- **Solid regions / custom shapes** — arbitrary copper region objects.
- **Planes (internal power planes)** — negative-plane layers with split planes and plane connection/clearance rules.
- **Teardrops** — curved/line teardrops on pad/via/track junctions with selective application and DRC-aware removal.
- **Copper balancing** — balanced copper distribution practices support (via panelization/plane tools).
- **Keepouts** — layer-specific or all-layer keepout regions/tracks/arcs for copper/via/component restrictions.

**Mechanical layers & documentation in PCB**
- **Unlimited named mechanical layers** — with layer pairs (component-side pairing) and layer types (courtyard, assembly, 3D body, etc.).
- **Dimensions in PCB editor** — linear/angular/radial/datum/ordinate dimension objects.
- **Strings with special strings** — dynamic text fields (e.g., .Layer_Name, .Print_Date) incl. barcode text.
- **Objects: arcs, fills, regions, 3D bodies, drill tables, layer stack tables** — full drafting object set.

**Rigid-flex & advanced technologies**
- **Rigid-flex (standard mode)** — multiple board regions assigned to different layer substacks.
- **Rigid-flex advanced mode** — overlapping flex regions, visual substack Z-plane definition, branches from rigid sections.
- **Bending lines & fold simulation** — define bend radius/angle; animate folding in 3D.
- **Bikini coverlays** — flex coverlay layer support in stack.
- **Layer stack regions editor** — graphical assignment of substacks to board areas.
- **Embedded components** — components embedded in internal cavities.
- **Printed electronics mode** — additive conductive/insulating layer stacks without conventional laminate.
- **3D-MID design (True 3D-MID)** — component placement and routing on 3D molded interconnect device substrates.
- **HDI support** — µvia span planning, stacked/staggered microvias, via-in-pad.
- **Wire bonding support** — bond wire objects and Wire Bonding routing rule.

## 4. Design Rules & Constraints

**Rule system (PCB Rules and Constraints Editor)**
- **Query-based rule scoping** — every rule scoped by query expressions (All, net, net class, layer, component, custom query language with hundreds of keywords).
- **Rule priorities** — ordered precedence within each rule type.
- **Binary-scoped rules** — rules between two object sets (e.g., clearance A-to-B).
- **Rule wizard** — guided rule creation.
- **Import/export rules** — transfer rule sets between designs.
- **Rules from schematic directives** — parameter-set-driven rule creation at capture.

**Rule categories & types**
- **Electrical: Clearance** — min copper-to-copper clearance, with object-kind clearance matrix (pad-pad, track-via, etc.).
- **Electrical: Short-Circuit** — disallow/allow copper shorts between nets.
- **Electrical: Un-Routed Net** — flag incomplete connections.
- **Electrical: Un-Connected Pin** — flag pins with no net/track.
- **Electrical: Modified Polygon** — flag shelved/un-repoured polygons.
- **Electrical: Creepage Distance** — surface creepage path checking around edges/cutouts/holes.
- **Electrical: Z-Axis Clearance** — inter-layer vertical clearance checking.
- **Routing: Width** — min/preferred/max track width per scope/layer, impedance-profile-driven option.
- **Routing: Routing Topology** — net topology patterns (shortest, daisy-simple, daisy-mid-driven, daisy-balanced, starburst).
- **Routing: Routing Priority** — net ordering for autorouting.
- **Routing: Routing Layers** — allowed layers per net.
- **Routing: Routing Corners** — corner style constraints.
- **Routing: Routing Via Style** — allowed via geometry during routing.
- **Routing: Fanout Control** — BGA/SMD fanout style, direction, via placement.
- **Routing: Differential Pairs Routing** — width/gap (min/pref/max) per layer, max uncoupled length, impedance profile option.
- **Routing: Neck-Down** — percentage/length limits for necked segments.
- **Routing: Wire Bonding** — bond wire length/angle constraints.
- **SMT: SMD To Corner** — min distance pad-to-first-corner.
- **SMT: SMD To Plane** — max distance SMD pad to plane connection.
- **SMT: SMD Neck-Down** — track-to-pad width ratio limit.
- **SMT: SMD Entry** — route entry from pad ends/sides.
- **Mask: Solder Mask Expansion** — mask opening expansion per pad/via scope.
- **Mask: Paste Mask Expansion** — stencil aperture expansion.
- **Plane: Power Plane Connect Style** — thermal relief/direct connect style, conductor count/width.
- **Plane: Power Plane Clearance** — clearance for non-connected drills through planes.
- **Plane: Polygon Connect Style** — thermal/direct connection of pads to polygons.
- **Testpoint: Fabrication/Assembly Testpoint Style** — size, allowed sides, under-component rules, grid.
- **Testpoint: Fabrication/Assembly Testpoint Usage** — required/invalid/allowed testpoints per net.
- **Manufacturing: Minimum Annular Ring** — pad/via annular ring floor.
- **Manufacturing: Acute Angle** — minimum angle between connected copper.
- **Manufacturing: Hole Size** — min/max drill sizes.
- **Manufacturing: Layer Pairs** — enforce used drill pairs match stack definition.
- **Manufacturing: Hole To Hole Clearance** — drill-to-drill spacing.
- **Manufacturing: Minimum Solder Mask Sliver** — min web between mask openings.
- **Manufacturing: Silk To Solder Mask Clearance** — silkscreen to exposed copper spacing.
- **Manufacturing: Silk To Silk Clearance** — silkscreen object spacing.
- **Manufacturing: Net Antennae** — flag open-ended copper stubs.
- **Manufacturing: Board Outline Clearance** — copper-to-board-edge clearance.
- **High Speed: Parallel Segment** — coupled parallelism limits by gap/length.
- **High Speed: Length** — min/max net length or delay.
- **High Speed: Matched Lengths** — length-match tolerance across nets/xSignals (incl. within diff pairs).
- **High Speed: Daisy Chain Stub Length** — max stub in daisy topologies.
- **High Speed: Vias Under SMD** — permit/deny via-in-pad under SMD.
- **High Speed: Maximum Via Count** — via count ceiling per net.
- **High Speed: Max Via Stub Length (Back Drilling)** — stub limit driving backdrill.
- **High Speed: Return Path** — continuous reference-plane return path verification with gap width.
- **Placement: Room Definition** — component containment regions.
- **Placement: Component Clearance** — 2D/3D body-aware component-to-component spacing.
- **Placement: Component Orientations** — allowed rotations.
- **Placement: Permitted Layers** — top/bottom placement permission.
- **Placement: Nets To Ignore** — nets excluded from clustering (autoplacement).
- **Placement: Height** — min/preferred/max component height per room/scope.
- **Signal Integrity rules (13 types)** — signal stimulus, overshoot/undershoot (rising/falling), impedance, signal top/base value, flight time (rising/falling), slope (rising/falling), supply nets.

**Checking**
- **Online DRC** — continuous real-time rule checking with immediate violation display.
- **Batch DRC** — on-demand full-board check with configurable rule participation.
- **DRC report** — HTML/report output with violation details and links.
- **Violation display styles** — violation overlay graphics and detail popups; PCB Rules And Violations panel with per-rule browsing.
- **DRC violation limits & stop conditions** — max violation counts per check.

**Constraint Manager (AD24+)**
- **Spreadsheet-style constraints editor** — document-based constraint definition shared by schematic and PCB domains.
- **Object-type scoping** — rule targeting by design object hierarchy instead of queries.
- **Constraint sets** — reusable named groups of constraints applied to nets/classes.
- **Clearance matrix view** — net-class × net-class clearance grid.
- **Six rule sections** — Nets, Diff Pairs, xSignals, Polygons, Components, Advanced with automatic priority.
- **Constraints from schematic** — same constraint UI accessible during capture.

## 5. High-Speed Design

- **xSignals** — user-defined pin-to-pin signal paths spanning series components (terminators, AC caps) for true length/delay constraints.
- **xSignals Wizard** — heuristic auto-creation of xSignals between selected components incl. DDR-style byte-lane grouping.
- **xSignal classes** — group xSignals for matched-length rule scoping.
- **Matched length & tuning against xSignals** — tuning targets computed across full signal path.
- **Differential pair definition (schematic or PCB)** — directive- or panel-based pair creation, pair classes.
- **Controlled impedance profiles** — per-layer single-ended/differential/coplanar impedance profiles computed by integrated **Simbeor engine**; drive width/gap rules.
- **Impedance profile types** — single, differential, single-coplanar, differential-coplanar structures; asymmetric stripline support.
- **Layer stack material library** — Dk/Df-characterized materials underpinning impedance accuracy.
- **Return Path rule/checking** — DRC for continuous reference plane under signals.
- **Back drilling (stack + rule + outputs)** — backdrill definition, checking, and NC drill/fab outputs.
- **Via stub management** — Max Via Stub Length rule with blind/buried/µvia alternatives.
- **Signal Integrity analyzer (pre/post-layout)** — reflection and crosstalk screening/waveform analysis from schematic or routed board; termination advisor with what-if termination models; IBIS model support.
- **SI screening results** — impedance, over/undershoot, flight time, slope tables against SI rules.
- **Crosstalk analysis** — aggressor/victim coupled-net waveform simulation.
- **Length tuning engines** — accordion/trombone/sawtooth tuning for nets, xSignals, diff pairs.
- **Interactive impedance-driven width switching** — width follows profile per routing layer.
- **HyperLynx / Ansys / Simbeor export** — .hyp, Ansoft neutral, Ansys EDB, Simbeor .esx exports for third-party SI/PI tools.

## 6. Multi-Board Design

- **Multi-board project type (*.PrjMbd)** — system-level project referencing child PCB projects.
- **Multi-board schematic (*.MbsDoc)** — logical system diagram.
- **Modules** — blocks representing child PCB projects (or nested multi-board projects) with entries mapped to connectors.
- **Direct connections** — module-to-module mated-connector links.
- **Cable connections** — wire/cable interconnects between modules.
- **Harness connections** — reference harness design projects as system interconnect.
- **Connection Manager** — table of all system connections, pin mapping, conflict identification and resolution (swap pins, change nets).
- **Import from child projects** — pull connector/net data from child PCBs via ECO.
- **Change propagation to child projects** — push net/pin changes back down to PCB projects.
- **System-level ERC** — multi-board connectivity rule check.
- **Multi-board assembly (*.MbaDoc)** — 3D physical assembly editor.
- **Update Assembly** — import each child board's 3D data.
- **3D positioning gizmo** — translate/rotate boards in assembly space.
- **Mating tool / alignment constraints** — mate planar/cylindrical surfaces, connector-based auto-mating.
- **STEP part insertion** — add enclosures/mechanical parts to the assembly.
- **Collision detection** — surface intersection checking (mated surfaces excluded).
- **Multiboard Assembly panel** — tree of boards, mates, STEP models.
- **Multi-board Draftsman documentation** — multi-board view, section view, board detail view, realistic 3D view, dimensions, callouts, BOM tables.
- **System-level BOM (ActiveBOM)** — consolidated BOM across child projects with Module traceability columns.
- **Multi-board exports** — STEP, Parasolid, PDF3D of the full assembly.
- **MCAD sync of multi-board assemblies** — via MCAD CoDesigner (Creo, SOLIDWORKS). **[Altium 365]**

## 7. 3D & MCAD Integration

- **Native 3D PCB editor** — real-time 3D visualization of board, components, enclosure with photorealistic rendering and configurable view configurations.
- **3D measurement tools** — point-to-point distance/clearance measurement in 3D.
- **3D component clearance checking** — Component Clearance rule evaluated against 3D bodies in online/batch DRC.
- **3D body import** — STEP, Parasolid, SolidWorks part import onto footprints; generic 3D body primitives.
- **Board shape from 3D model** — derive outline/heights from imported mechanical model.
- **Rigid-flex 3D folding** — animated fold states with collision checking in folded state.
- **STEP export (board/assembly)** — 3D export with configurable component inclusion.
- **Parasolid export** — native Parasolid kernel export.
- **VRML export** — 3D visualization format export.
- **IDF/IDX exchange** — legacy mechanical collaboration formats (import/export).
- **PDF3D export** — interactive 3D PDF documents.
- **MCAD CoDesigner** — bidirectional ECAD-MCAD sync through Altium 365 Workspace. **[Altium 365]**
  - **Supported MCAD tools** — SOLIDWORKS, Autodesk Inventor Professional, Autodesk Fusion, PTC Creo Parametric, Siemens NX.
  - **Push/pull change workflow** — selective, commented transfers of changes in either direction with change preview.
  - **Board outline & cutout sync** — bidirectional shape changes.
  - **Component placement sync** — move/add/delete components from either side; MCAD-side placement from native MCAD libraries linked to ECAD components.
  - **Copper/silkscreen/mask transfer** — detailed copper and graphic layers to MCAD for accurate models.
  - **Hole/mounting feature sync** — plated/non-plated holes.
  - **Rigid-flex transfer with folding** — flex regions and bend states (SOLIDWORKS, Creo).
  - **Multi-board assembly sync** — assembly-level collaboration (SOLIDWORKS, Creo).
  - **Harness CoDesign** — connectors/splices/connectivity/topology exchange with MCAD harness tools (SOLIDWORKS, Creo).
  - **Enclosure-driven co-design** — pull enclosure into PCB editor as reference.
  - **Parasolid-format model exchange** — component 3D models passed natively.

## 8. Outputs & Manufacturing

**Fabrication outputs**
- **Gerber (RS-274X)** — per-layer plot generation with full aperture control.
- **Gerber X2** — attribute-rich Gerber with layer/function metadata.
- **ODB++** — full manufacturing dataset export.
- **IPC-2581 (rev A/B/C)** — single-file intelligent manufacturing data export.
- **NC Drill (Excellon)** — plated/non-plated, per drill-pair files, backdrill support.
- **Drill drawing & drill symbols** — configurable drill charts/symbols.
- **Final artwork prints / composite prints** — configurable layer print sets.
- **Mask prints (solder/paste)** — mask layer plots.
- **Power-plane prints** — plane layer artwork.
- **Test point report (fabrication)** — testpoint location/spec report.
- **Board stack report / layer stack table & legend** — stackup documentation outputs.
- **Checkplots** — review prints per layer.

**Assembly outputs**
- **Pick-and-place files** — component centroid/rotation/side reports in text/CSV/Excel.
- **Assembly drawings** — per-side assembly prints with variant support.
- **IPC-D-356 netlist** — bare-board electrical test netlist.
- **Test point report (assembly)** — assembly testpoint data.
- **Nets/component reports** — status and cross-reference reports.

**Documentation & report outputs**
- **PDF output (smart PDF)** — bookmarked, searchable PDF of schematics/PCB with nets/components navigation.
- **Draftsman PDF/print outputs** — production drawing publishing.
- **Print jobs** — any documents to system printers with scale/color config.
- **Report outputs** — netlist reports, cross-reference, hierarchical report, port cross-references.
- **Design Rules Check report output** — DRC as managed output.
- **Differences/comparison reports** — schematic-vs-PCB comparison outputs.
- **Video/animation output** — PCB 3D video generation output container.
- **PDF3D** — 3D interactive PDF output.
- **SVG/DXF/DWG export** — 2D graphic exports of PCB/schematic.
- **Netlist outputs** — 20+ third-party netlist formats (Calay, EDIF, PADS, Protel, RINF, Tango, Telesis, etc.).

**Output management**
- **Output Job files (.OutJob)** — reusable, pre-configured sets of outputs mapped to containers.
- **Output containers** — PDF, folder-structure file outputs, video containers with naming/path macros.
- **Variant-aware output jobs** — per-output variant selection.
- **PostProcess outputs** — automated copying/distribution of generated files.
- **Batch output generation** — run entire jobs in one action; used headlessly by Project Releaser.

**Release & CAM**
- **Project Releaser** — staged, validated release process producing immutable release packages (fabrication/assembly/documentation datasets) to Workspace, folder, or zip. **[Altium 365 for Workspace targets]**
- **Release validation gates** — ERC/DRC/BOM checks enforced during release.
- **Manufacturing Package Viewer / sharing to manufacturer** — web-shareable release packages. **[Altium 365]**
- **CAMtastic CAM editor** — import/inspect/edit Gerber, ODB++, NC drill data; netlist extraction and comparison; panelization at CAM level; reverse engineering of PCBs from fab data; export back to fab formats.
- **Board panelization (embedded board arrays)** — design-level panels output through standard fab outputs.

**BOM / ActiveBOM**
- **ActiveBOM document (.BomDoc)** — live BOM management editor.
- **BOM line items & consolidation** — automatic grouping, configurable columns, line numbering.
- **Part choices & solutions** — manufacturer part solutions per line with color-coded supplier tiles. **[Altium 365 for managed part choices]**
- **Automatic solution ranking** — availability/price/lifecycle-ranked sourcing solutions.
- **Custom (starred) ranking** — manual override of solution ranking.
- **Real-time supply chain data** — stock, pricing, MOQ from Altium Parts Provider per production quantity.
- **Production quantity costing** — quantity-based price/availability roll-up.
- **Lifecycle & risk indicators** — EOL/NRND flags in BOM.
- **BOM checks** — configurable violation severities (missing part choice, out-of-stock, obsolete, etc.).
- **Non-PCB (documentation-only) BOM items** — add bare board, hardware, glue items.
- **Favorite suppliers & currency selection** — sourcing preferences.
- **BOM output formats** — Excel (templated), CSV, TSV, PDF, HTML, XML.
- **Excel BOM templates** — company-formatted spreadsheet templates with field substitution.
- **BOM compare report** — diff BOMs across revisions/documents.
- **Multi-board system BOM** — consolidated cross-project BOM.
- **BOM Portal** — web-based advanced BOM management/enrichment app. **[Altium 365 — Pro/Enterprise-level plans]**

## 9. Simulation & Analysis

**Mixed-signal circuit simulation (MixedSim)**
- **SPICE3f5/XSPICE-compatible engine** — true mixed analog/digital simulator.
- **PSpice model support** — run PSpice-format device models.
- **LTspice model support** — LTspice model/netlist compatibility, LTspice schematic import.
- **Digital SimCode devices** — digital component simulation language/models.
- **Simulation Dashboard panel** — guided setup: verification, sources, models, analyses, results.
- **Simulation generic components** — quick generic sources/passives with sim models.
- **Model assignment & sim model editing** — per-component SPICE model linking, subcircuit support.
- **Operating Point analysis** — DC bias solution.
- **DC Sweep analysis** — swept-source transfer curves.
- **Transient analysis** — time-domain waveforms with initial conditions.
- **Fourier analysis** — harmonic decomposition of transient results.
- **AC Sweep (small-signal) analysis** — frequency response.
- **Noise analysis** — spectral noise contributions.
- **Pole-Zero analysis** — stability/pole-zero extraction.
- **Transfer Function analysis** — DC small-signal transfer/input/output resistance.
- **Temperature sweep** — analyses across temperature set.
- **Parameter sweep** — component/model parameter stepping.
- **Monte Carlo analysis** — statistical tolerance runs with distributions.
- **Sensitivity analysis** — DC/AC sensitivity of outputs to parameters.
- **Global parameters & expressions** — parameterized circuits.
- **Probes** — persistent measurement probes (voltage, current, power) placed on schematic.
- **Output expressions & measurements** — math on waveforms, dB/phase/real/imag functions.
- **SimData waveform viewer (.sdf)** — multi-plot, multi-cursor waveform environment with zoom/measure/export.
- **Simulation profiles** — named analysis setups per project.

**Board-level analysis**
- **Signal Integrity analysis (screening + waveform)** — see §5.
- **Power Analyzer by Keysight (DC PI)** — in-editor PDN DC analysis: voltage drop, current density, via current, heatmaps, probes, violations, HTML reports. *Tier-gated.*
- **PDN Analyzer (by CST)** — earlier DC power delivery analysis extension (superseded by Power Analyzer).
- **Keysight PIPro/EMPro-class electrothermal & AC PI** — advanced PI analyses, tier-dependent add-ons.

## 10. Data Management & Collaboration

**Local/external version control**
- **Git version control integration** — commit, push, pull, update, history, diff from within Altium Designer; external Git repo support.
- **SVN version control integration** — full SVN operations plus repository creation from within the tool.
- **Storage Manager panel** — file states, history, revert operations.
- **Schematic document comparison** — graphical diff of two schematic revisions.
- **PCB document comparison** — graphical diff of PCB revisions with change navigation.
- **Concurrent conflict resolution** — merge assistance for parallel PCB edits.

**Altium 365 platform** (all **[Altium 365]**)
- **Workspace (cloud-hosted managed content server)** — projects, components, templates, releases in one governed store.
- **Versioned storage (Git-backed) for projects** — full-history managed projects.
- **Project History timeline** — commits, releases, clones, MCAD exchanges with compare-between-events (schematic/PCB/BOM diffs in browser).
- **Web viewer for projects** — browser-based schematic/PCB/3D/BOM viewing with object properties, search, cross-probe.
- **Web-based commenting/redlining** — place comments on schematic/PCB/3D in browser or in Altium Designer; comment threads, mentions, statuses.
- **Global sharing** — share projects/snapshots with internal users, external guests, or via link; view/edit permission control.
- **Design snapshots (Personal Space)** — lightweight shareable design uploads.
- **Design reviews** — formal review sessions with accept/reject outcomes.
- **Tasks & configurable workflows** — workflow-process engine for design/release/library processes (Pro/Enterprise-level plans).
- **Project releases & item revisions** — immutable release packages with lifecycle states per revision.
- **Lifecycle management** — configurable lifecycle definitions for projects, components, releases.
- **Manufacturing package sharing & viewer** — send release packages to fabricators with web viewing, no license needed.
- **PCB CoDesign (co-authoring)** — multiple designers on the same PCB concurrently: change detection across layout/properties/stack/rules, diff exploration, merge of others' pushed changes. *Up to 25 concurrent ECAD authors on Agile Teams tier.*
- **Soft/hard conflict prevention** — checkout awareness and change notifications.
- **PLM integrations** — bidirectional sync with PTC Windchill, Siemens Teamcenter, Arena, Oracle Agile, Aras Innovator, Duro (Enterprise-level plans).
- **Requirements Portal** — requirements capture, review, verification linked to designs (Enterprise tier).
- **Library health dashboard** — Workspace library quality metrics.
- **User/role/permission administration** — invitations, roles, folder-level permissions, LDAP/SSO.
- **Data acquisition/migration tools** — import content from legacy Vault/Concord servers.
- **Altium 365 Viewer (public)** — free browser viewer for shared snapshots.
- **On-premises Enterprise Server option** — self-hosted Workspace equivalent (Enterprise tier).

## 11. Scripting & API

- **Integrated scripting system** — write/run scripts inside Altium Designer against the API object model.
- **DelphiScript** — primary/default scripting language (Delphi-like, untyped).
- **VBScript support** — run scripts written in VBScript.
- **JScript (JavaScript) support** — run JScript scripts.
- **Script projects (.PrjScr)** — organize script units and forms.
- **Script forms/dialogs** — build GUI dialogs (VCL-style controls) within scripts.
- **Scripting editor with debugger** — breakpoints, stepping, watch within the IDE.
- **Scripting API object interfaces** — documented interfaces for Schematic, PCB, Workspace/Client, ECO, output generation.
- **PCB API (IPCB_* interfaces)** — programmatic board/object creation, iteration, rule access.
- **Schematic API (ISch_* interfaces)** — symbol/document object automation.
- **Process launching (server processes)** — invoke any editor command/process with parameters from scripts or menus.
- **Customizable UI: commands, menus, hotkeys** — bind scripts/processes to UI elements.
- **Altium Designer SDK (extensions API)** — Delphi/C++ SDK for building installable extensions.
- **Extensions & Updates platform** — install/manage functional extensions per installation.
- **Scripting examples reference** — official example script library.
- **Headless-ish automation** — Output Job + Project Releaser automation via API calls.

## 12. Import / Interoperability

**EDA importers**
- **Cadence Allegro importer** — .brd (binary, requires Allegro extracta) and ASCII .alg; .dra footprints.
- **Cadence OrCAD importer** — Capture .dsn/.olb, OrCAD Layout .max/.llb; OrCAD CIS configurations.
- **Siemens (Mentor) PADS importer** — PADS Logic/Layout ASCII schematics, boards, libraries.
- **Siemens Xpedition importer** — Xpedition PCB projects/designs/libraries.
- **Siemens xDX Designer / DxDesigner importer** — schematics and libraries.
- **Autodesk EAGLE importer** — .sch/.brd/.lbr.
- **KiCad importer** — .kicad_pro/.kicad_sch/.kicad_pcb/.kicad_sym/.kicad_mod.
- **Zuken CADSTAR importer** — .csa/.cpa archives and libraries.
- **Zuken CR-5000/CR-8000 importer** — board/schematic/library file sets.
- **P-CAD importer** — schematic/PCB/library (ASCII).
- **Protel 99SE DDB importer** — legacy Altium database designs.
- **CircuitMaker 2000 importer** — legacy .ckt/.lib.
- **CircuitStudio/CircuitMaker (current) project opening** — sibling-product design compatibility.
- **LTspice importer** — .asc schematics and .asy symbols.
- **SPECCTRA export** — .dsn/.rte router interchange (export).
- **Netlist import/export** — 20+ netlist formats.
- **Import Wizard** — batch guided migration of designs plus their libraries with mapping options.

**Mechanical/neutral formats**
- **DXF/DWG import & export** — AutoCAD interchange for PCB and schematic.
- **STEP import/export** — AP214/AP203 3D models and boards.
- **Parasolid import/export** — native kernel exchange.
- **IDF import/export** — board-level mechanical exchange.
- **IDX (ProSTEP EDMD) exchange** — incremental ECAD/MCAD collaboration files.
- **SolidWorks part import** — .sldprt direct import.
- **HyperLynx export** — SI tool handoff.
- **Ansys EDB / Ansoft Neutral export** — EM/SI/PI tool handoff.
- **Simbeor .esx import** — stack exchange with Simbeor.
- **VRML export** — 3D graphics.
- **Gerber/ODB++/NC drill import (CAMtastic)** — fab data re-import and reverse engineering to PCB.

## 13. Documentation Tools (Draftsman)

- **Draftsman document type (.PCBDwf)** — dedicated drawing environment linked live to board data with update-on-demand.
- **Board assembly view** — top/bottom assembly views with configurable component display, variant support.
- **Board fabrication view** — layer-wise fabrication views with drill symbols.
- **Drill drawing view** — dedicated drill chart/symbol view.
- **Board section view** — cross-section cut views through the board.
- **Board detail view** — magnified callout view of a defined area.
- **Board isometric view** — 3D-projected board view.
- **Component view** — standalone views of individual components.
- **Layer stack legend** — automated stackup table/graphic.
- **Linear dimensions** — with configurable units/tolerances.
- **Angular/radial/diametral dimensions** — full dimension set.
- **Ordinate dimensions / axis scales** — X/Y coordinate scales and datum dimensioning.
- **Callouts** — leader annotations incl. BOM item number callouts.
- **Surface finish indicator** — standards-based surface notation.
- **Center marks** — feature center annotation.
- **Notes (custom & automated note lists)** — free text plus design-data-driven note generation, numbered note lists.
- **BOM table (Draftsman)** — live BOM tables with column config and variant awareness.
- **Drill table** — automatic drill symbol/count/size tables per drill pair, backdrill aware.
- **Transmission line (impedance) table** — impedance profile documentation table.
- **Generic table & graphics primitives** — free tables, lines, shapes, images.
- **Sheet templates & document templates** — predefined and custom templates, stored locally or in Workspace. **[Workspace templates: Altium 365]**
- **Automatic update from board changes** — one-click refresh of all views after PCB edits.
- **Draftsman in Output Jobs / Project Releaser** — publishable to PDF/print within release packages.
- **Harness Draftsman documents (.HarDwf)** — harness manufacturing drawings.

## 14. Harness Design

- **Harness design project type (*.PrjHar)** — dedicated project for cable/wiring harness products.
- **Wiring Diagram (.WirDoc)** — logical wiring document: wires, cables, connection definition.
- **Harness Layout Drawing (.LdrDoc)** — physical one-line harness construction drawing.
- **Harness wires & cables** — individual conductors with gauge/color/length properties; multi-core cables.
- **Connectors** — harness interface components with cavity/pin definitions.
- **Splices** — wire junction objects splitting wires into segments.
- **Taps** — branch connection points on wires.
- **No-connect markers** — intentionally unterminated ends.
- **Harness components (reusable)** — Workspace-stored reusable wiring assemblies. **[Altium 365]**
- **Harness bundles** — physical grouping of wires in layout drawing with computed bundle diameter.
- **Connection points** — bundle endpoints/branch points.
- **Layout labels** — physical marker/label objects on bundles.
- **Harness coverings** — protective wrap/sleeve/loom definitions with coverage lengths.
- **Wire length management** — lengths captured in layout and rolled into BOM/wiring list.
- **Connection Manager (harness/multi-board)** — connectivity table linking harness to system design.
- **Harness project validation** — automated completeness/violation checking with configurable severities.
- **Harness ActiveBOM** — BOM of connectors, wires, cables, splices, coverings with lengths.
- **Harness Draftsman (.HarDwf)** — manufacturing drawings: wiring diagram view, layout drawing view, BOM table, wiring list, connection tables, callouts, dimensions.
- **Harness output jobs & release** — full OutJob/Project Releaser support for harness deliverables.
- **Harness in multi-board designs** — harness projects referenced as system interconnect.
- **Harness MCAD CoDesign** — exchange with SOLIDWORKS/Creo harness environments. **[Altium 365]**

---

## Tier-gating notes

Altium's current documentation gates features by solution (Altium Develop / Agile
Teams / Agile Enterprise / AD on active term) rather than a per-feature matrix.
Explicitly documented gates: concurrent PCB co-authoring at scale (Agile Teams),
Power Analyzer by Keysight (tier-dependent), PLM integration, Workflows, BOM
Portal and Requirements Portal (Pro/Enterprise 365 plans); everything marked
**[Altium 365]** requires at minimum a connected Workspace.

## Sources

Official documentation tree at altium.com/documentation/altium-designer
(schematic, components-libraries, pcb/routing, design-rule-types, layer stack,
high-speed-design, constraint-manager, multi-board-design, MCAD CoDesigner,
draftsman, harness-design, preparing-for-manufacture, circuit-simulation,
power-analyzer-keysight, design-tools-interfacing, scripting, version control,
project-history), altium.com/documentation/altium-365, and
altium.com/altium-designer/features.
