# Autodesk Fusion — Feature Taxonomy (research input)

> Raw competitive research compiled from Autodesk's official Fusion features/
> pricing pages, the official Fusion help documentation (cloudhelp modules), and
> Autodesk's supported-file-formats article. Tier markers: **[MFG-EXT]** =
> Manufacturing Extension, **[SIM-EXT]** = Simulation Extension, **[DESIGN-EXT]**
> = Design Extension, **[CLOUD]** = requires cloud solve/tokens/credits,
> **[PREMIUM]** = paid plan only.
>
> Status: research input for the gitcad-mech roadmap. ~280 discrete features
> across 15 areas. See `feature-map.md` for the gitcad tiering.

## 1. Solid Modeling

**Create features**
- Extrude — add depth to open/closed profiles or faces; one-side, two-side, symmetric; join/cut/intersect/new body/new component; taper angle and thin-extrude option
- Revolve — revolve profile/planar face around an axis (full or partial angle)
- Sweep — sweep profile along path; optional guide rail or twist; chained path support
- Loft — transitional shape between 2+ profiles with guide rails/centerline; end conditions (tangent, direction)
- Rib — thin-wall rib from sketch line
- Web — network of ribs from sketch curves
- Hole — parametric hole feature: simple, counterbore, countersink, tapped (modeled or cosmetic threads), drilled point angles; from sketch points or face placements
- Thread — cosmetic or modeled threads on cylindrical faces, standard thread tables (ISO, ANSI, etc.)
- Primitives: Box, Cylinder, Sphere, Torus, Coil (spring/helix with sections), Pipe (round/square/triangular profile along path)
- Emboss — wrap/emboss sketch text or profiles onto curved faces (raised or debossed)
- Boundary Fill — create solid from cell volumes enclosed by bodies/surfaces/planes

**Pattern / duplicate**
- Rectangular pattern — features, faces, bodies, or components in 1–2 directions with spacing/quantity control and instance suppression
- Circular pattern — around an axis, full/partial/symmetric
- Pattern on Path — instances along a curve/edge path
- Geometry Pattern option — pattern exact geometry for performance
- Mirror — mirror features, faces, bodies, components across a plane

**Modify features**
- Fillet — constant-radius, chordal, variable-radius (multi-point), rule fillets; G2 (curvature-continuous) fillets; rolling-ball vs setback corner options; full round fillet
- Chamfer — equal distance, two-distance, distance + angle; multiple edge sets in one feature
- Shell — hollow body with uniform or per-face thickness, inside/outside/both, face removal
- Draft — angle faces from a parting line/plane, fixed plane or parting line modes
- Scale — uniform or non-uniform scaling of bodies/sketches
- Combine — Boolean join, cut, intersect between bodies (with keep-tools option)
- Offset Face — offset selected faces of a solid
- Replace Face — replace solid faces with surface geometry
- Split Face — divide faces with sketch/surface/plane
- Split Body — divide bodies with plane/surface/sketch
- Silhouette Split — split by view-direction silhouette (mold parting workflows)
- Press Pull — context-sensitive direct offset/fillet/extrude on faces/edges
- Direct editing: Move/Copy faces, bodies, components (free move, translate, rotate, point-to-point)
- Align — align bodies/components via geometry selections
- Physical Material assignment — apply engineering materials to bodies
- Appearance assignment — apply visual materials per body/face
- Delete / Remove — delete faces (with heal) or remove bodies as timeline features
- Change Parameters — edit model dimensions from a central dialog

**Plastics**
- Plastic Rules — wall-thickness/material rule presets driving plastic features **[partly DESIGN-EXT]**
- Boss — screw-boss feature with integrated ribs, countersink geometry
- Snap Fit — cantilever snap features
- Geometric/wall-thickness analysis for moldability

**Direct modeling**
- Timeline-free "Do not capture design history" mode — pure direct editing on any body, including imported geometry
- Base feature editing — direct edits inside a parametric timeline

**Automation / AI**
- Autodesk Assistant AI — natural-language assistant that can execute modeling commands and answer questions
- Feature recognition on imported geometry (holes recognition for editing/manufacture)

## 2. Sketching

**Sketch entities**
- Line, Rectangle (2-point, 3-point, center), Circle (center, 2-point, 3-point, 2-tangent, 3-tangent), Arc (3-point, center, tangent), Polygon (edge, circumscribed, inscribed), Ellipse, Slot (center-to-center, overall, center-point, 3-point arc slot, arc slot), Conic Curve, Point, Text (including text-on-path), Fit-point Spline, Control-point Spline (with degree control)

**Sketch tools**
- Fillet (sketch), Trim, Extend, Break, Offset (with chaining), Mirror, Circular Pattern, Rectangular Pattern, Project, Intersect, Include 3D Geometry, Project to Surface, Intersection Curve, Slice view, Sketch Scale, Move/Copy sketch entities
- Construction-line and center-line line types
- Sketch on any plane/planar face; 3D Sketch mode (out-of-plane lines/splines)
- Spline handle editing — tangency/curvature handles, curvature comb display

**Constraints (12 types)**
- Horizontal/Vertical, Coincident, Tangent, Equal, Parallel, Perpendicular, Fix/UnFix, Midpoint, Concentric, Collinear, Symmetry, Curvature (G2)
- Automatic constraint inference while sketching; constraint display/deletion; fully-constrained sketch indication (color change)

**Dimensions**
- Sketch Dimension tool — linear, aligned, angular, radial, diameter, ordinate dimensions inferred by selection
- Driven (reference) dimensions
- Dimension expressions — any dimension can reference user parameters/formulas
- Units per document, mixed unit entry

## 3. Surface Modeling

- Extrude/Revolve/Sweep/Loft as surfaces — all core create tools produce open surface bodies
- Patch — fill boundary loop with surface; tangency/curvature edge continuity control
- Trim / Untrim / Extend — surface boundary editing (natural/tangent/perpendicular extension)
- Stitch / Unstitch — sew surfaces into quilts/solids (with tolerance control), decompose
- Offset (surface), Thicken, Boundary Fill, Reverse Normal
- Ruled Surface — draft/ruled surface from edges (parting surfaces)
- Flange surface (tangent extension for tooling)
- Freeform curve tools: project curves, intersection curves, curves on surface **[DESIGN-EXT for some advanced surfacing]**
- Face/edit continuity analysis: Zebra, Curvature comb, Draft analysis, Curvature map display

**Forms (T-spline sculpting environment)**
- T-spline primitives: Box, Plane, Cylinder, Sphere, Torus, Quadball, Pipe, Face
- Edit Form — push/pull/rotate/scale vertices, edges, faces with manipulator
- Insert Edge, Subdivide, Insert Point, Merge Edge, Bridge, Fill Hole, Erase and Fill
- Weld/Unweld vertices and edges; Crease / Uncrease; Bevel Edge
- Symmetry (mirror/circular/duplicate with live editing), Clear Symmetry
- Thicken, Freeze/Unfreeze, Smooth/box display modes
- Pull — snap T-spline vertices to target geometry
- Match — T-spline edge match to curves/edges with continuity
- Convert — T-spline body ⇄ BRep; quad-mesh to T-spline conversion
- Make Solid/Make Uniform, repair body utilities

**Mesh environment**
- Import/repair STL, OBJ, 3MF scans; Insert Mesh
- Direct mesh edits: Remesh, Reduce, Smooth, Plane Cut, Combine, Separate, Erase & Fill holes, Reverse Normals, Delete Faces
- Convert Mesh — mesh → solid/surface BRep (faceted or **prismatic conversion with face recognition [DESIGN-EXT]**)
- Generate Face Groups — segment mesh for conversion
- Section Sketch from mesh — sketch geometry from mesh cross-sections

## 4. Assemblies

- Component/occurrence architecture — components with instances; bodies vs components distinction
- Top-down (in-context) design; bottom-up (Insert Into Current Design); middle-out hybrid
- External references (XRefs) — linked designs across documents with version update control
- New Component / Derive — derive bodies/sketches/parameters into new design with associative link
- Joint — position + motion in one step; types: **Rigid, Revolute, Slider, Cylindrical, Pin-Slot, Ball, Planar**
- As-Built Joint — define motion between components already in position
- Joint Origin — user-defined joint reference frames
- Joint limits — min/max/rest positions on any DOF
- Joint preview/animation — Animate Joint, Animate Model; Drive Joint
- Motion Link — link two joints with ratio (gears, rack-pinion)
- Motion Study — multi-joint motion timeline with steps
- Contact Sets — physical contact between selected bodies
- Rigid Group; Ground / Ground to Parent; Capture Position
- Interference detection; Section Analysis — live cutaway views
- Center of Mass display, physical properties (mass, volume, moments)
- Component display control, isolate, opacity
- Assembly configurations and configured-component insertion
- Simplify tools for large assemblies **[DESIGN-EXT for some automation]**

## 5. Parametrics & Timeline

- Parametric timeline — full history capture; scrub, reorder, suppress
- Roll back / roll forward marker; edit any historic feature with downstream recompute
- Feature grouping, timeline search/color coding
- Direct + parametric hybrid: "capture design history" toggle per design
- User Parameters — named parameters with units, expressions, functions
- Model/feature parameters — every feature dimension exposed centrally
- Parameter expressions referencing other parameters; imported/derived parameter linking
- Configurations **[PREMIUM]**: Configuration Table (variants configure suppression, parameters, visibility, materials, properties, sheet-metal/plastic rules), Configuration Rules, Theme Tables, Custom Aspects, configurable assemblies, per-configuration downstream outputs (drawings, toolpaths, studies, renders)
- Derived designs — associative push of bodies/components/sketches/parameters to child designs

## 6. Drawings

**Sheet & document**
- Drawing from Design (associative) or templates; multi-sheet
- Standards: ASME and ISO; per-document units, first/third-angle projection
- Title blocks — default, custom editor, DWG import; sheet sizes A–E / A0–A4
- Templates with stored annotation preferences; automated drawing creation

**Views**
- Base View, Projected View, Section View (full/half/offset/aligned), Detail View, Break View, broken-out sections, exploded views from animation storyboards
- View styles: visible edges, hidden lines, shaded, tangent-edge control; per-view scale
- Sheet metal flat-pattern views with bend lines and identifiers

**Dimensions**
- Smart Dimension, Linear, Aligned, Angular, Radius, Diameter, Ordinate, Jogged Radial, Arc Length, Curve Min/Max, Baseline, Chain
- Auto Dimension — strategy-based automatic dimensioning
- Tolerances (symmetric, deviation, limits), precision, inspection dimensions, prefixes/suffixes
- Arrange Dimensions, Tidy Up (auto-layout), Match Dimension, Flip Arrows, Dimension Break

**Annotations & GD&T**
- Text, multi-line notes, Leader notes
- Surface Texture symbols; Feature Control Frames (full GD&T set); Datum Identifiers
- Center Line, Center Mark, Center Mark Pattern, Edge Extension
- Hole/thread callouts, bend notes, punch notes
- Drawing sketch environment — 2D overlay on sheets

**Tables**
- Parts List (BOM) — structured or parts-only, with balloons (auto/manual, renumber, align)
- Hole Tables, Bend Tables, Configuration tables
- Custom properties in title block/parts list; CSV export

**Output**
- Export PDF (multi-sheet), DWG, DXF (per sheet), CSV; print; associative updates

## 7. Sheet Metal

- Sheet Metal Rules — per-material rule library (thickness, bend radius, K-factor, relief shapes/sizes); overrides per body
- Unfold Rule / K-factor control — custom K-factor, bend tables
- Flange — base flange; edge flange (angle/height, multi-edge) with automatic bend/corner relief; miter handling
- Contour Flange — multi-bend flange from open profile in one operation
- Lofted Flange — transitional sheet body between two profiles
- Hem — Flat, Open, Rolled, Teardrop, Rope, Double variants
- Bend — add bend between faces; Fold/refold along sketch lines
- Unfold / Refold — temporarily flatten to cut features, then refold
- Rip — split closed geometry to enable flattening
- Convert to Sheet Metal — turn solid body into sheet metal part
- Flat Pattern — dedicated representation with bend lines, direction/angle data
- Corner reliefs and bend reliefs (rectangular, round, tear)
- Flat pattern export as DXF/DWG (layer mapping, spline-to-arc conversion)
- Flat pattern drawing views with bend tables
- Direct link to Manufacture cutting strategies and **sheet nesting [MFG-EXT]**

## 8. CAM / Manufacturing

**Setup & infrastructure**
- Setup types: Milling, Turning/Mill-Turn, Cutting, Additive, Inspection
- Stock definition, WCS definition, fixtures/workholding modeling
- Machine Library — machine definitions, custom builder, kinematics, linked post + 3D model
- Tool Library — cloud/local/document, holders, shaft profiles, feeds/speeds, import/export
- Manufacturing Models — CAM-side editable derivations (defeature for machining)
- Templates — reusable operation templates; associative toolpaths update with design changes

**2D milling**
- 2D Adaptive Clearing, 2D Pocket, Face, 2D Contour (tabs, leads, compensation), Slot, Trace, Thread mill, Bore, Circular, Engrave, 2D Chamfer

**Drilling**
- Drill — canned cycles: drilling, peck, chip-break, deep drill, tapping, boring, reaming, counterboring; automatic hole selection/sorting
- Hole Recognition — automated multi-tool, multi-plane (3- and 5-axis) **[MFG-EXT]**

**3D milling**
- Adaptive Clearing (+ rest roughing), Pocket Clearing, 3+2 Clearing **[MFG-EXT]**, Steep and Shallow **[MFG-EXT]**, Flat, Parallel, Scallop, Contour, Ramp, Pencil, Horizontal, Spiral, Radial, Morphed Spiral, Project, Blend, Morph, Corner **[MFG-EXT]**, Flow, Deburr **[MFG-EXT]**, Geodesic **[MFG-EXT]**
- Rest machining, slope/boundary containment, smoothing/feed optimization

**Multi-axis** (simultaneous 4/5-axis are **[MFG-EXT]**)
- Tool orientation/tilt (3+1, 3+2 positional in base)
- 4th-axis Wrap; multi-axis options for 3D Contour/Blend/Flow; Swarf and Advanced Swarf; Multi-Axis Contour/Clearing/Finishing/Deburr; Rotary Parallel/Pocket/Contour; Inclined Flat; automatic collision avoidance and tool-axis limits

**Turning & mill-turn**
- Face, Profile Roughing/Finishing, Adaptive Roughing, Groove Roughing/Finishing, Thread, Chamfer, Part-off, Trace
- Chuck/jaw and tailstock; spindle/live-tooling mill-turn; C/Y-axis wrapped milling
- Stock simulation with collision checks

**Cutting (fabrication)**
- 2D Profile cutting for Waterjet, Laser, Plasma (kerf compensation, lead-in/out, pierce control)
- Sheet nesting: manual and **automatic multi-sheet nesting, nest reports [MFG-EXT]**

**Additive**
- Processes: FFF, SLA/DLP, MJF, SLS, MPBF **[MFG-EXT]**, eBeam, Binder Jetting, DED **[MFG-EXT]**
- Additive machine library + print settings library
- Automatic part orientation optimization; build-volume arrangement/packing
- Support generation — automatic/manual, bar/volume, associative **[metal supports MFG-EXT]**
- Slicing preview & layer-by-layer simulation; FFF infill patterns
- Metal build simulation (thermo-mechanical) **[MFG-EXT + CLOUD]**
- Export: print files, gcode, 3MF; direct-print connectivity

**Verification & output**
- Toolpath Simulation — stock removal, machine simulation with 3D models, collision/gouge detection, rest-material comparison
- Manual NC; Post Processing — open, free, editable post library (JavaScript .cps) for all major controls
- Setup Sheets (HTML); NC program containers
- Toolpath modification: trim, delete passes, replace tool, edit leads/links **[MFG-EXT]**
- Machining time estimation & cycle-time statistics

**Inspection**
- Setup probing: spindle touch-probe WCS/stock measurement (base)
- Part alignment probing, geometry/surface inspection with in-process reports and offset updating **[MFG-EXT]**

## 9. Simulation

Official study types (**[CLOUD]** tokens unless **[SIM-EXT]**):
- Static Stress; Modal Frequencies (with/without preload); Thermal (steady-state); Thermal Stress; Structural Buckling
- Nonlinear Static Stress **[SIM-EXT]**; Quasi-Static Event **[SIM-EXT]**; Dynamic Event (explicit impact/drop) **[SIM-EXT]**; Shape Optimization **[SIM-EXT]**; Electronics Cooling (Tech Preview) **[SIM-EXT]**; Plastic Injection Molding **[SIM-EXT]**

Supporting:
- Simplify environment — defeature for simulation
- Mesh controls — adaptive refinement, local sizing, convergence
- Loads: force, pressure, moment, bearing, remote, gravity, angular velocity, bolt preload; thermal loads
- Constraints: fixed, pin, frictionless, prescribed displacement, remote
- Contacts: bonded, separation, sliding, press-fit; automatic detection
- Point mass idealization, bolt connectors; editable material library
- Multiple load cases; study cloning across configurations
- Results: contour plots, animation, probes, section results, reactions; Compare view (up to 4 studies)
- Report generation
- Ansys interoperability — send studies to Ansys Mechanical; **Signal Integrity Extension (Ansys)** for PCB EM/SI **[paid extension]**

## 10. Generative Design

**[CLOUD tokens per study, or unlimited with SIM-EXT]**
- Preserve Geometry / Obstacle Geometry / Starting Shape setup
- Design space with automatic feature obstacles
- Multiple structural load cases; objectives: minimize mass or maximize stiffness with safety-factor targets
- Manufacturing constraints: Unrestricted, Additive (overhang/build direction), Milling 2.5/3/5-axis, 2-axis Cutting, Die Casting
- Multi-material exploration; cloud parallel generation
- Outcome exploration — gallery with ML filtering, sorting, scatter plots, similarity grouping; comparison view
- Cost estimation per outcome
- Export outcomes as native editable designs (T-spline/BRep); mesh export
- Generative studies from configurations

## 11. Rendering & Visualization

**Render workspace**
- Appearance library — PBR materials, custom appearances, texture/decal mapping
- Scene settings — HDRI environments, brightness, background, ground plane, reflections/shadows
- Camera — focal length, exposure, depth of field, aspect ratio, named views
- In-canvas ray-traced rendering; local render; cloud render **[CLOUD; PREMIUM]**; turntables
- Render gallery, PNG/JPEG/TIFF/EXR output

**Animation workspace**
- Storyboard timeline; Auto Explode (one/all levels) and manual explode
- Camera keyframing, component transforms, visibility/opacity, callouts
- Publish MP4/AVI

**In-model visualization**
- Section Analysis, named views, display styles
- Zebra/curvature/draft analysis; minimum radius analysis
- Web viewer — browser 3D preview for shared links

## 12. Data Management & Collaboration

- Cloud data platform — designs stored in Autodesk cloud (Fusion Team hubs)
- Hubs, projects & folders with per-folder permissions; roles (admin/editor/viewer)
- Version control — automatic versioning per save, history browsing, promote/restore, descriptions
- Milestones — flag significant versions. **No branching/merging — linear versions only**
- Reserve/checkout in collaborative editing; conflict warnings
- Offline mode with cached data; auto-sync
- Design references (XRefs) with controlled version update
- Fusion Team web app — browser view, comment, markup, manage
- Comments & markup — threaded, in app and web viewer
- Public/private share links — password-protectable 3D preview, optional download
- Live Review sessions; BOM view in Team; where-used
- Admin tools — user management, activity streams, archiving
- Team Participant seat **[separate SKU]**
- Fusion Manage Extension **[paid]** — PLM: change orders, release management, part numbering, BOM management, workflows
- AnyCAD — associative use of non-native CAD models without translation
- Personal Use tier: 10 active editable docs, no multi-user collaboration

## 13. Electronics (Fusion ECAD, EAGLE heritage — one level)

- Schematic capture — multi-sheet, nets, buses, ERC, custom attributes, SPICE netlists
- SPICE simulation of schematics
- PCB layout — multi-layer, manual + interactive routing, differential pairs, length matching, copper pours, via stitching, blind/buried vias
- Autorouter / quick-route features
- DRC — customizable rule sets
- Component libraries — managed parts, custom editor (symbol, footprint, 3D package), wizards
- ECAD-MCAD bi-directional sync — PCB outline/components round-trip with 3D workspace; 3D PCB with real component models
- CAM outputs — Gerbers, NC drill, pick-and-place, one-click CAM processor
- EAGLE import (.brd/.sch)
- 3D PCB workspace — board bending (flex), enclosure fit checks
- Electronics Cooling **[SIM-EXT]**; Signal Integrity Extension (Ansys) **[paid]**

## 14. APIs & Automation

- Fusion API — full object model in **Python** and **C++**
- Scripts (run-once) and Add-ins (persistent, custom commands, UI, event handlers)
- API coverage: geometry/BRep, sketches, features, parameters, assemblies/joints, materials, custom features, CAM API (setups, operations, post, additive FFF), drawings (limited), simulation (limited), data (hubs, projects, files, versions), UI customization, custom graphics
- Text Commands window; Custom Features API (user-defined parametric features)
- Palettes with HTML/web UI; Autodesk App Store distribution
- Post-processor customization — JavaScript .cps framework
- Headless "Design Automation for Fusion" (Autodesk Platform Services; limited availability)
- Official API reference + samples

## 15. Interoperability

**Import:** .f3d/.f3z, .123dx, Alias (.wire), DWG, DXF, Rhino (.3dm), CATIA V5, FBX, IGES, Inventor, JT, NX, OBJ, Parasolid, Pro/E–Creo, SAT/SAB, SolidWorks, STEP, SMT/SMB, STL, SketchUp, SVG, 3MF, EAGLE, .cam360 — some translators **[PREMIUM]**
- Upload-based cloud translation and direct open; insert DXF/SVG/mesh
- AnyCAD associative references

**Export:** .f3d/.f3z, STEP, IGES, SAT, SMT, DWG, DXF, STL, OBJ, 3MF, FBX, SketchUp, USD, PDF (drawings), CSV, MP4/AVI, images, Gerber/drill/pick-and-place, G-code via posts, additive print files — some cloud-translated **[CLOUD]**; Personal Use restricts several
- McMaster-Carr parts catalog insertion; Insert Derive between documents

---

## Tier/gating summary

- **Free Personal Use:** core modeling/CAM limited (no simultaneous multi-axis, limited posts, limited exports, 10 active docs).
- **Base commercial:** everything unmarked; 2D–3+2 CAM, static stress + modal via cloud tokens, drawings, sheet metal, ECAD, data management.
- **Manufacturing Extension:** 4/5-axis simultaneous, advanced 3D strategies, hole recognition, toolpath editing, probing/inspection, nesting, metal additive + build simulation.
- **Simulation Extension:** all 11 study types unlimited + unlimited generative solves.
- **Design Extension:** advanced surfacing/mesh conversion, plastics automation, simplification/DFM.
- **Manage Extension:** PLM.
- **Cloud-gated regardless of tier:** generative solves, cloud sim solves, cloud rendering, cloud translation.

## Sources

Autodesk Fusion features/extensions pages (autodesk.com/products/fusion-360),
official Fusion Help cloudhelp modules (Fusion-CAM 2D/3D/multi-axis/turning/
additive overviews, Fusion-Simulate study types, Fusion-Sketch constraints,
Fusion-Drawing reference & dimensions, Fusion-Sheet-Metal flanges,
Fusion-Configurations, Fusion-GenerativeDesign, Fusion-Extensions,
Fusion-360-API reference), and the Autodesk supported-file-formats support
article.
