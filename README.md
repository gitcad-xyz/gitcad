# gitcad

**Agent-first, headless, git-native CAD.**

gitcad is a boundary-representation CAD system designed from the ground up to be
driven by agents over [MCP](https://modelcontextprotocol.io), with git as the
source of truth and a browser as the (optional) viewer. It leans on the mature
[OpenCASCADE](https://dev.opencascade.org/) geometry kernel via
[`cadquery-ocp`](https://pypi.org/project/cadquery-ocp/) rather than reinventing
b-rep math — the value lives in the *layers around* the kernel:

- an **intent-based API** agents can author without visualizing raw NURBS,
- a **verification/render loop** so agents model by checking, not hoping,
- **associative 2D drawings** derived from the 3D model (mechanical drafting),
- a **git-native text format** so models diff, branch, and merge like code, and
- a **privacy-preserving bug loop** where failures are auto-reduced to minimal,
  synthetic, shareable repros.

> Website: [gitcad.xyz](https://gitcad.xyz)

## Why this exists

Agents fall back to shelling out to FreeCAD for anything with complex curves —
not because that's good, but because it's what's in the training distribution,
and they model *blind*. gitcad's thesis: wrap the same proven kernel (OCCT) in
an intent API plus a deterministic inspect/render loop, make the model **text**
so git works, and make MCP the *primary* interface so the product is
agent-legible from day one.

## The six seams

Everything swappable lives behind a small, stable interface (`gitcad.seams`):

| Seam | Responsibility | Default backend |
|------|----------------|-----------------|
| `Kernel` | b-rep geometry ops | OCCT via `cadquery-ocp` (`gitcad.kernel.occt`) |
| `IdentityService` | stable entity IDs (topological naming) | lineage-hash (`gitcad.identity`) |
| `DocumentModel` | the feature tree + text (de)serialization | `gitcad.document` |
| `Renderer` | headless tessellate → image/glTF | *stub* |
| `DrawingEngine` | 3D → 2D HLR projection + dimensions | *stub* |
| `Storage` | git-backed model + artifact store | *stub* |

A "major architecture change" should mean replacing one backend, not a rewrite.

## Layout

```
src/gitcad/
  seams.py         # the six Protocol interfaces — the load-bearing boundaries
  errors.py        # structured errors that double as bug-repro payloads
  identity.py      # IdentityService: stable IDs from construction lineage
  document.py      # DocumentModel: feature tree + canonical text format
  kernel/
    null.py        # pure-Python test backend (no OCCT dependency)
    occt.py        # OCCT via cadquery-ocp (the real kernel)
  report/
    fingerprint.py # deterministic failure fingerprints (for dedup)
    reduce.py      # delta-debug reducer: proprietary model -> minimal synthetic repro
  mcp/
    server.py      # the MCP tool surface (the PRIMARY interface)
docs/adr/          # architecture decision records (the durable intent)
tests/
  invariants/      # permanent, architecture-independent properties
  golden/          # curated user-visible contracts
  regression/      # auto-generated, second-class, expirable
```

## Quick start

```bash
pip install -e ".[dev]"        # core + pytest, no kernel needed
pytest                          # runs against the pure-Python null kernel
pip install -e ".[occt]"        # add the real OCCT kernel (~large wheel)
```

The test suite runs with **no geometry kernel installed** — the null backend
covers identity, document round-tripping, and reduction. Tests that need real
geometry are marked `@pytest.mark.occt` and skip when `cadquery-ocp` is absent.

## Status

Early scaffold. The seams, document model, stable-identity scheme, reducer, and
MCP surface are real; kernel geometry beyond primitives, the renderer, and the
drawing engine are stubs with defined interfaces. See `docs/adr/` for the
reasoning and `CLAUDE.md` for the rules agents must follow.

## License

Apache-2.0. The OCCT kernel it binds is LGPL-2.1-with-exception; see `NOTICE`.
