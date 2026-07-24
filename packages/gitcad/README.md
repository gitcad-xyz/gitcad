# gitcad

Headless, git-native B-rep CAD — mechanical and electrical.

Models are stored as canonical text; geometry is a build artifact. Entity
identity is derived from construction lineage rather than ordinal position.
Each build produces a report.

This metapackage installs:

- `gitcad-core` — canonical text, identity, the Part standard, report pipeline.
- `gitcad-mech` — document model, geometry kernel, sketches, drawings, importers.
- `gitcad-ecad` — schematic and ERC, board and DRC, fabrication outputs.

## Install

```
pip install gitcad            # core, mechanical, electrical, MCP server, native kernel
pip install gitcad[occt]      # add the optional alternative kernel backend
```

The mechanical geometry kernel uses exact rational arithmetic. Its native
(compiled) build is installed by default on common platforms; elsewhere the
pure-Python build is used.

## Console commands

`gitcad-init`, `gitcad-render`, `gitcad-view`, `gitcad-review`, `gitcad-merge`,
`gitcad-verify`, `gitcad-convert`, `gitcad-explore`, `gitcad-mcp`, `gitcad-lot`.

License: Apache-2.0. https://gitcad.xyz · https://github.com/gitcad-xyz/gitcad
