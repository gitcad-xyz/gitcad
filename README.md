# gitcad

Headless, git-native boundary-representation (B-rep) CAD — mechanical and
electrical.

Models are stored as canonical text; geometry is a build artifact and is not
committed. Entity and feature identity is derived from construction lineage
rather than ordinal position, so references survive upstream edits. Each build
produces a report, and designs diff, branch, review, and merge at each kind's
natural grain. The primary interface is an MCP server; a browser viewer is
optional.

Website: [gitcad.xyz](https://gitcad.xyz) · Registry:
[gitcad-xyz/registry](https://github.com/gitcad-xyz/registry)

## Packages

- `gitcad-core` — canonical text, identity, the Part standard, report pipeline.
- `gitcad-mech` — document model, exact-arithmetic geometry kernel, sketches,
  drawings, importers.
- `gitcad-ecad` — schematic and ERC, board and DRC, connectivity, fabrication
  outputs.
- `gitcad` — metapackage installing the three above and the MCP server.

## A project is a repo

```
widget/
├── widget.gitcad        # top-level assembly (mechanical + electrical parts)
├── housing.part         # a mechanical part
├── housing.model        # its feature tree
├── mainboard.pcba       # an electrical assembly
├── mainboard.board      # the board
├── mainboard.sch        # the schematic
├── requirements.reqs    # executable requirements
└── release-*/           # built artifacts + fab-lot provenance
```

`gitcad-init widget` scaffolds a project with the merge driver and CI gates
configured. Roles are detected by file content.

## Console commands

| command | description |
|---|---|
| `gitcad-init` | create a new project |
| `gitcad-mcp` | run the MCP server |
| `gitcad-view` | live viewer: 3D, exploded views, cross-probe, schematics, checks; `--review BASE` for in-app review |
| `gitcad-render` | render PNG/SVG from a design file |
| `gitcad-review` | semantic, check-delta, and visual diff between git refs |
| `gitcad-merge` | git merge driver: semantic 3-way per kind |
| `gitcad-verify` | run executable requirements |
| `gitcad-explore` | compare design variants against shared gates |
| `gitcad-convert` | convert parametric part files into a gitcad project |
| `gitcad-lot` | record and verify fab-lot provenance |

## Install

```
pip install gitcad            # core, mechanical, electrical, MCP server, native kernel
pip install gitcad[occt]      # add the optional alternative kernel backend
```

The mechanical kernel uses exact rational arithmetic; its native build is
installed by default on common platforms. The test suite also runs with no
geometry kernel installed — a null backend covers identity, documents,
netlists, checks, and merge; tests needing geometry are marked and skipped
otherwise.

## Capabilities

Mechanical — primitives and booleans; fillet, chamfer, shell; extrude, revolve,
loft, sweep, mirror; sketch planes and sketch-on-face; an authoring-time
constraint solver; holes with counterbore/countersink; patterns; sheet metal;
weldments; stable entity identity; exact mass properties; STEP/STL/DXF;
dimensioned drawings (third-angle and section views, GD&T, BOM and balloons);
exploded views; mate checking and solving; exact interference with clash
budgets; feature recognition from STEP; parametric part import.

Electrical — schematic capture with typed pins and sheet authoring;
hierarchical sheets, buses, and multi-sheet systems; ERC, electrical envelopes,
and power budgets; forward and back annotation; multi-layer boards with net
classes, keepouts, courtyard DRC, copper zones, and silkscreen text;
connectivity and guided routing; Gerber, Excellon, pick-and-place, IPC-D-356,
and netlist export; board statistics and length checks; SPICE export and
simulation-as-test.

Cross-domain — parts with typed interfaces, interface semantic versioning, and
lockfiles; registry parts; electrical assemblies as parts (`.pcba`); enclosure
fit checks; all-or-nothing release gates; fab-lot records.

## Documentation

See `docs/adr/` for design decisions and `CLAUDE.md` for the rules agents
follow.

## License

Apache-2.0. The optional geometry backend it can bind is
LGPL-2.1-with-exception; see `NOTICE`.
