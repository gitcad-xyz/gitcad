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
```

The mechanical geometry kernel uses exact rational arithmetic. Its native
(compiled) build is installed by default on common platforms; elsewhere the
pure-Python build is used.

## Now what

gitcad is an MCP server — there is no application to open. Wire it into an
MCP client (either form):

```
claude mcp add gitcad -- gitcad-mcp
```

```json
{ "mcpServers": { "gitcad": { "command": "gitcad-mcp" } } }
```

Once connected, the agent calls the `get_started` tool and opens the live
browser viewer (`viewer_open`). Run `gitcad` (or `python -m gitcad`) any time
to reprint this wiring and the viewer story.

- **Windows per-user installs:** console scripts land in
  `%APPDATA%\Python\PythonXY\Scripts`, typically not on PATH, so `gitcad-mcp`
  can be "not recognized" right after install. Use the PATH-proof spelling
  `{ "mcpServers": { "gitcad": { "command": "python", "args": ["-m", "gitcad.mcp"] } } }`
  or add that Scripts directory to PATH.
- **Introspection:** `gitcad` is a namespace package shared by the three
  subpackages. Without the metapackage installed, `gitcad.__file__` is
  `None` — use `gitcad.__path__` or `importlib.metadata`, never
  `os.path.dirname(gitcad.__file__)`. The metapackage provides
  `gitcad.__version__`.

## Console commands

`gitcad` (this guide), `gitcad-init`, `gitcad-render`, `gitcad-view`,
`gitcad-review`, `gitcad-merge`, `gitcad-verify`, `gitcad-convert`,
`gitcad-explore`, `gitcad-mcp`, `gitcad-lot`.

License: Apache-2.0. https://gitcad.xyz · https://github.com/gitcad-xyz/gitcad
