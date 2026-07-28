"""Project resolution for the viewer: ONE server per PROJECT, not per file.

The viewer serves the project a design lives in. The default view is the TOP
assembly (the one no other assembly instances); individual parts are
sub-interfaces inside the one page, reached through ``/api/parts`` and the
``#part=<file>`` deep link — never a second server on another port.

Kernel-free by construction: everything here is JSON reading and file-tree
walking, so project resolution works identically with no geometry installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

__all__ = ["find_project_root", "discover_designs", "resolve_default",
           "resolve_project"]

# Files that can BE a view (detect_kind accepts them). Part manifests are
# indexed too: a viewable assembly/pcba manifest is a *.part/part.json.
_CANDIDATE_SUFFIXES = (".model", ".part", ".part.json", ".pcba", ".board",
                       ".sch", ".sch.json", ".schematic.json", ".gitcad",
                       ".gitcad.json")
_PRUNE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
               ".gitcad", "out", "build", "dist"}
_MAX_DESIGNS = 200
_MAX_DIRS = 5000


def find_project_root(path: str | Path) -> Path:
    """The project a path belongs to: its git root when there is one, else the
    file's directory (or the directory itself). Same anchoring rule as
    :func:`gitcad.activity.session_dir`, so the viewer, the narration log and
    the discovery file all agree on where the project lives."""
    p = Path(path).resolve()
    if p.is_file():
        p = p.parent
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand
    return p


def _candidate_files(root: Path) -> list[Path]:
    out: list[Path] = []
    seen_dirs = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _PRUNE_DIRS)
        seen_dirs += 1
        if seen_dirs > _MAX_DIRS:
            break
        for fn in sorted(filenames):
            if fn.endswith(_CANDIDATE_SUFFIXES):
                out.append(Path(dirpath) / fn)
        if len(out) >= _MAX_DESIGNS:
            break
    return out[:_MAX_DESIGNS]


def discover_designs(root: Path) -> list[dict]:
    """Every viewable design under ``root``: ``{"file", "kind", "name"}`` with
    ``file`` as a root-relative POSIX path — the value ``?file=`` and
    ``#part=`` take. Unviewable or broken candidates are skipped, never fatal:
    a half-written file must not sink the parts menu."""
    from gitcad.viewer.server import detect_kind

    root = Path(root).resolve()
    designs: list[dict] = []
    for p in _candidate_files(root):
        try:
            text = p.read_text(encoding="utf-8")
            kind = detect_kind(text)
        except Exception:              # noqa: BLE001 - see docstring
            continue
        try:
            name = json.loads(text).get("name") or p.stem
        except ValueError:
            name = p.stem
        designs.append({"file": p.relative_to(root).as_posix(),
                        "kind": kind, "name": str(name)})
    return designs


def _assembly_rank(root: Path, assemblies: list[dict]) -> list[dict]:
    """Assemblies ordered top-first: an assembly referenced as an instance of
    another assembly is a sub-assembly, never the default view."""
    ids: dict[str, str] = {}
    referenced: set[str] = set()
    instance_count: dict[str, int] = {}
    for d in assemblies:
        try:
            doc = json.loads((root / d["file"]).read_text(encoding="utf-8"))
        except Exception:              # noqa: BLE001
            continue
        ids[d["file"]] = doc.get("id", "")
        insts = (doc.get("body") or {}).get("instances") or {}
        instance_count[d["file"]] = len(insts)
        for inst in insts.values():
            if isinstance(inst, dict) and inst.get("part"):
                referenced.add(inst["part"])

    def key(d: dict):
        is_sub = ids.get(d["file"], "") in referenced
        depth = d["file"].count("/")
        return (is_sub, -instance_count.get(d["file"], 0), depth, d["file"])

    return sorted(assemblies, key=key)


def resolve_default(root: Path, designs: list[dict]) -> str | None:
    """The project's default view, as a root-relative path: the TOP assembly
    when there is one, else (in order) a pcba, a single model, a board, a
    schematic. ``None`` when the project holds nothing viewable."""
    by_kind: dict[str, list[dict]] = {}
    for d in designs:
        by_kind.setdefault(d["kind"], []).append(d)
    if by_kind.get("assembly"):
        return _assembly_rank(root, by_kind["assembly"])[0]["file"]
    for kind in ("pcba", "model", "board", "schematic"):
        if by_kind.get(kind):
            return sorted(by_kind[kind],
                          key=lambda d: (d["file"].count("/"), d["file"]))[0]["file"]
    return None


def resolve_project(path: str | Path) -> tuple[Path, Path]:
    """``(project_root, default_design_file)`` for a directory or file path.
    A directory resolves to its top assembly (or fallback); a file keeps
    itself as the default view but still gets its whole project served."""
    p = Path(path).resolve()
    if not p.exists():
        raise ValueError(f"{p} does not exist — pass a project directory or "
                         "a design file")
    root = find_project_root(p)
    if p.is_file():
        return root, p
    rel = resolve_default(root, discover_designs(root))
    if rel is None:
        raise ValueError(f"no viewable design found under {root} — "
                         "create a .model/.board/.sch or an assembly first")
    return root, (root / rel).resolve()
