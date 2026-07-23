# gitcad

**Agent-first, headless, git-native CAD — mechanical and electrical, one substrate.**

gitcad is a boundary-representation CAD system designed from the ground up to be
driven by agents over [MCP](https://modelcontextprotocol.io), with git as the
source of truth and a browser as the (optional) viewer. It leans on the mature
[OpenCASCADE](https://dev.opencascade.org/) geometry kernel via
[`cadquery-ocp`](https://pypi.org/project/cadquery-ocp/) rather than reinventing
b-rep math — the value lives in the *layers around* the kernel:

- an **intent-based API** agents can author without visualizing raw NURBS,
- a **verification loop** so agents model by checking, not hoping — ERC, DRC,
  electrical envelopes, interference, executable requirements,
- **KiCad-grade schematics** and a 2-layer board flow through to Gerbers,
- a **git-native text format** so designs diff, branch, review, and **merge
  semantically** like code, and
- a **privacy-preserving bug loop** where failures are auto-reduced to minimal,
  synthetic, shareable repros.

> Website: [gitcad.xyz](https://gitcad.xyz) · Registry: [gitcad-xyz/registry](https://github.com/gitcad-xyz/registry)

## Why this exists

Agents fall back to shelling out to FreeCAD or KiCad for anything real — not
because that's good, but because it's what's in the training distribution, and
they model *blind*. gitcad's thesis: wrap proven kernels and formats in an
intent API plus a deterministic check/render loop, make the design **text** so
git works, and make MCP the *primary* interface so the product is agent-legible
from day one.

Because designs are canonical text with stable identity, gitcad does things the
incumbent architectures structurally cannot:

| | |
|---|---|
| **A type system for hardware** | 5V into a 3.6V-max pin is a design-time error (pin envelopes, rail budgets — ADR-0015) |
| **PRs that show their physics** | `gitcad-review`: check deltas (introduced vs fixed) + side-by-side renders, merge-gated |
| **Semantic 3-way merge** | `gitcad-merge`: features by id, connectivity by pin, copper by content — no file locks (ADR-0016) |
| **Simulation as tests** | `to_spice` + ngspice assertions: "OUT sits at 2.5±0.05 V" runs on every commit |
| **Requirements as code** | `gitcad-verify`: the traceability matrix that executes (mass, envelopes, rails, DRC, fit) |
| **Fab-lot bisect** | `gitcad-lot`: builds pinned to commits + artifact hashes; field failures bisect through design history |

## A project is a repo

```
widget/
├── widget.gitcad        # THE product: the top-level assembly (mech + elec parts)
├── housing.part         #   a mechanical part…
├── housing.model        #   …and the feature tree that gives it shape
├── mainboard.pcba       #   an electrical assembly: mechanical outside,
├── mainboard.board      #   enter it for the electrical workflow
├── mainboard.sch        #   the electrical source of truth
├── requirements.reqs    # executable requirements
└── release-*/           # built artifacts + *.lot fab provenance
```

`gitcad-init widget` scaffolds all of it — merge driver wired, CI gates included.
Extensions are roles; detection is by content; `.json` variants stay accepted.

## The CLI surface

| command | what it does |
|---|---|
| `gitcad-init` | new project: product root, merge driver, CI, requirements |
| `gitcad-mcp` | the MCP server — the primary interface (60+ tools) |
| `gitcad-view` | live viewer: 3D + explode + cross-probe + schematics + checks; `--review BASE` adds in-app PR review |
| `gitcad-render` | PNG/SVG artifacts from any design file (drawn sheets, board top, 3D) |
| `gitcad-review` | semantic + check-delta + visual diff between git refs; exit 1 gates merges |
| `gitcad-merge` | git merge driver: semantic 3-way at each kind's natural grain |
| `gitcad-verify` | run `requirements.reqs` — measured-vs-limit per requirement |
| `gitcad-explore` | branch scoreboard: N variants judged by the same gates |
| `gitcad-convert` | multi-body FreeCAD `.FCStd` → a whole gitcad project |
| `gitcad-lot` | fab-lot provenance: record + tamper-verify |

## Quick start

```bash
pip install --no-deps -e packages/gitcad-core -e packages/gitcad-mech -e packages/gitcad-ecad -e packages/gitcad && pip install pytest
pytest                          # runs against the pure-Python null kernel
pip install cadquery-ocp        # add the real OCCT kernel (~large wheel)
```

The test suite runs with **no geometry kernel installed** — the null backend
covers identity, documents, netlists, checks, merge, and reduction. Tests that
need real geometry are marked `@pytest.mark.occt` and skip when `cadquery-ocp`
is absent.

## What works (v0.7.x)

**Mechanical** — primitives, booleans, fillets/chamfers/shell, extrude/revolve/
loft/sweep/mirror, sketch planes + sketch-on-face, constraint solver
(authoring-time, ADR-0013), holes with counterbore/countersink, patterns,
stable entity identity (fillet-by-id survives upstream edits), mass properties,
STEP/STL/DXF, dimensioned drawings (third-angle + section views with hatching
+ assembly BOM/balloons), exploded views (ADR-0014), mate checking + `mate_solve`,
exact interference with clash budgets, feature recognition from STEP, FreeCAD
import (parametric tree where possible, multi-body conversion always).

**Electrical** — schematic capture (typed pins) + sheet *authoring* with a
KiCad-convention symbol library, `.kicad_sch` import validated
**pin-group-identical against KiCad's own netlist engine** (hierarchical
sheets, buses, multi-sheet systems), sheet-fidelity rendering, ERC + electrical
envelopes + power budgets, forward/back annotation, 2-layer boards with net
classes, keepouts, courtyard DRC, copper zones, silkscreen text (stroke font),
copper connectivity, `route()` with guardrails, Gerber X2 / Excellon / PnP /
IPC-D-356 / KiCad-netlist export, board stats + matched-pair length checks,
Eagle `.sch` import, SPICE export + ngspice sim-as-test.

**Cross-domain** — parts with typed interfaces + interface-semver + lockfiles
(ADR-0008/9), MPN-atomic registry parts (ADR-0010), PCBA duality (`.pcba`:
mechanical outside, electrical inside), populated board envelopes for
enclosure fit checks, the `interference_clear` requirement, releases with
all-or-nothing gates, fab-lot records.

Everything deferred is deferred *explicitly with rationale* — see
[docs/research/kicad-feature-map.md](docs/research/kicad-feature-map.md).

See `docs/adr/` for the reasoning (17 ADRs) and `CLAUDE.md` for the rules
agents must follow.

## License

Apache-2.0. The OCCT kernel it binds is LGPL-2.1-with-exception; see `NOTICE`.
