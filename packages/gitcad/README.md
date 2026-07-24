# gitcad

**Agent-first, headless, git-native CAD — mechanical and electrical, one substrate.**

gitcad is a boundary-representation CAD system designed to be driven by agents and
version-controlled like source. Models are byte-canonical text (geometry is a
build artifact, never committed); identity is construction-lineage based, never
ordinal; every build produces a reviewable, diffable report.

This metapackage installs the whole system:

| package | domain |
|---|---|
| [`gitcad-core`](https://pypi.org/project/gitcad-core/) | canonical text, stable identity, the Part standard, report pipeline |
| [`gitcad-mech`](https://pypi.org/project/gitcad-mech/) | document model, **exact B-rep kernel**, sketches, drawings, importers |
| [`gitcad-ecad`](https://pypi.org/project/gitcad-ecad/) | schematic + ERC, board + DRC, fab outputs, KiCad import |

## Install

```bash
pip install gitcad           # full system; exact forge kernel included (pure Python)
pip install gitcad[fast]     # + native compiled accelerator (forgekernel_rs wheel)
pip install gitcad[occt]     # + OCCT kernel oracle/fallback (cadquery-ocp)
pip install gitcad[mcp]      # + Model Context Protocol server for agents
```

The mechanical kernel is **exact**: topological decisions are made in rational
arithmetic (ℚ), never by a floating-point tolerance — see
[`forgekernel`](https://pypi.org/project/forgekernel/) and the
[benchmarks vs OCCT](https://github.com/gitcad-xyz/gitcad/blob/main/bench/RUST-vs-OCCT.md).
`[fast]` adds the compiled Rust build of the hot paths; results are identical, only
faster.

## Console tools

`gitcad-init`, `gitcad-render`, `gitcad-view`, `gitcad-review`, `gitcad-merge`,
`gitcad-verify`, `gitcad-convert`, `gitcad-explore`, `gitcad-mcp`, `gitcad-lot`.

Apache-2.0 · https://gitcad.xyz · https://github.com/gitcad-xyz/gitcad
