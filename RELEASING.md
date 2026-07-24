# Releasing gitcad to PyPI

Four distributions ship from `packages/`, all built with hatchling, released in
**lockstep** at one version:

| project | domain | depends on |
|---|---|---|
| `gitcad-core` | canonical text, identity, Part standard | — (pure stdlib) |
| `gitcad-mech` | document model + exact kernel + drawings | `gitcad-core`, **`forgekernel`** |
| `gitcad-ecad` | schematic / board / DRC / fab | `gitcad-core` |
| `gitcad` | metapackage (installs all three) | the three above |

`pip install gitcad` is complete out of the box: both domains (electrical is a
base dep), the exact kernel **with** its native accelerator (`forgekernel_rs`, a
default dep of `gitcad-mech` via a `platform_machine` marker — pure-Python
fallback where no wheel exists), and the **MCP server** (`mcp` is a base dep).
Only `gitcad[occt]` (→ `cadquery-ocp`, a heavy optional oracle) is an extra.

## Version lockstep

All four `packages/*/pyproject.toml` carry the same `version`, and the
inter-package pins are exact (`gitcad-core==X.Y.Z`, etc.). A release bumps the
`version` in all four **and** every matching pin. (Held at 0.x per project
policy — no minor bump without an explicit call; patch-bump each release.)

## One-time setup (maintainer, gated)

1. **Reserve the names** on PyPI: `gitcad`, `gitcad-core`, `gitcad-mech`,
   `gitcad-ecad`.
2. **Trusted Publishing** on each: PyPI project → *Publishing* → add publisher
   `gitcad-xyz/gitcad`, workflow `release.yml`, environment `pypi`.
3. Create the GitHub `pypi` Environment (optionally gated by a reviewer).
4. Release the kernel first — `forgekernel` (and `forgekernel_rs`) must be on
   PyPI before a gitcad release so `gitcad-mech`'s dependency resolves. See
   `forge/RELEASING.md`.

## Build & validate locally (no upload)

```bash
for p in gitcad-core gitcad-mech gitcad-ecad gitcad; do
  python -m build packages/$p --outdir dist
done
python -m twine check dist/*          # all must PASS
# end-to-end: install from the built wheels into a clean venv
python -m venv /tmp/v && /tmp/v/bin/python -m pip install \
  --no-index --find-links dist --find-links ../forge/dist gitcad
/tmp/v/bin/python -c "import gitcad, forgekernel; print('ok')"
```

CI (`.github/workflows/release.yml`) runs build + `twine check` on every push/PR.

## Cut a release

1. Bump `version` in all four `packages/*/pyproject.toml` and update the exact
   inter-package pins to match.
2. Commit; tag and push:
   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```
3. The `release` workflow builds all four and the `publish` job (tags only)
   uploads them to PyPI via Trusted Publishing. PyPI routes each file to its
   project by name.
