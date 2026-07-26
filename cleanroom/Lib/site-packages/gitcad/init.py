"""gitcad init — a new project in one command.

A gitcad project IS a git repo; this scaffolds the anatomy and seeds
``<name>.gitcad`` — THE project root: the top-level assembly manifest
whose instances are the product's parts, mechanical and electrical alike
(an assembly IS a part, ADR-0008; a board-backed part is an instance like
any other). Mech feature-tree models are ``.model`` files referenced from
a part's body — a model is how one part gets its shape, never the product.

Also wired: the semantic merge driver (.gitattributes + git config), a CI
workflow running the review gate and the requirements suite, and a README
that explains the layout to the next person who clones it.

Extensions are directory legibility only — every tool detects document
kind by CONTENT (the schema field), and the old *.json names remain
accepted everywhere, forever.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError

_GITATTRIBUTES = """\
# gitcad semantic merge (ADR-0016): features by stable id, schematic
# connectivity by pin — never line-level merges of canonical JSON.
*.gitcad merge=gitcad
*.model  merge=gitcad
*.sch    merge=gitcad
*.board  merge=gitcad
*.part   merge=gitcad
*.pcba   merge=gitcad
"""

_WORKFLOW = """\
name: gitcad
on: [push, pull_request]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install gitcad
      - name: requirements suite
        run: gitcad-verify requirements.reqs
      - name: review gate (PRs)
        if: github.event_name == 'pull_request'
        run: gitcad-review --base origin/${{ github.base_ref }}
"""

_README = """\
# {name}

A [gitcad](https://gitcad.xyz) project — the repo IS the project.

| file | what it is |
|------|-----------|
| `{name}.gitcad` | THE project: the top-level assembly of every part, mechanical and electrical |
| `*.part`   | part manifests (envelope / frames / typed ports; subassemblies are parts too) |
| `*.model`  | mechanical feature-tree models (canonical text; geometry is a build artifact) |
| `*.pcba`   | electrical assemblies — mechanical from outside, enter for the electrical workflow |
| `*.sch`    | schematics — the electrical source of truth |
| `*.board`  | board layouts |
| `requirements.reqs` | executable requirements — `gitcad-verify` runs them |
| `release-*/` | built artifacts + `*.lot` fab-lot provenance records |

Branch = design variant. PR = design review with physics
(`gitcad-review`). Tag + lot record = a physical production run.
Merges are semantic (`gitcad-merge`, wired in `.gitattributes`).
View locally: `gitcad-view <file>`.
"""


def init_project(path: str, *, name: str | None = None) -> list[str]:
    """Scaffold a project at path (created if missing). Returns files written.
    Refuses to overwrite anything — init is for new projects, not repair."""
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    project = name or root.resolve().name

    from gitcad.part import Assembly, new_part_id

    root_manifest = Assembly(project).to_manifest(new_part_id())
    files = {
        ".gitattributes": _GITATTRIBUTES,
        ".github/workflows/gitcad.yml": _WORKFLOW,
        "README.md": _README.format(name=project),
        f"{project}.gitcad": root_manifest.dumps(),
        "requirements.reqs": canonical_json(
            {"schema": "gitcad/requirements@1", "requirements": []},
            indent=2) + "\n",
    }
    existing = [rel for rel in files if (root / rel).exists()]
    if existing:
        raise GitcadError(f"refusing to overwrite existing files: {existing} "
                          "— gitcad init is for new projects")

    written = []
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        written.append(rel)

    if not (root / ".git").exists():
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    # Wire the merge driver into this clone's config (gitattributes names it;
    # config supplies the command — both halves are needed).
    subprocess.run(["git", "-C", str(root), "config",
                    "merge.gitcad.name", "gitcad semantic merge"], check=True)
    subprocess.run(["git", "-C", str(root), "config",
                    "merge.gitcad.driver", "gitcad-merge %O %A %B"], check=True)
    return written


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse

    ap = argparse.ArgumentParser(
        description="gitcad init — scaffold a new project (the repo IS the project)")
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--name", help="project name (default: directory name)")
    args = ap.parse_args()
    written = init_project(args.path, name=args.name)
    print("initialized gitcad project:")
    for rel in written:
        print(f"  {rel}")
    print("merge driver wired (merge.gitcad in git config)")
