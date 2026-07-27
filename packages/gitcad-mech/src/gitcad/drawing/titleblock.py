"""ISO 7200 title-block data — git-derived, never hand-typed strings.

The gitcad twist: the sheet is a build artifact of a git-tracked text model,
so the fields that drafting standards want maintained by hand fall out of
the repository instead. Author comes from ``git config user.name``; the
revision id, date and revision-history table come from the git log of the
source part file; the drawing number derives from the part name. Every git
lookup degrades to a **blank** field — outside a repo, for an uncommitted
file, or with git missing, the block stays honest rather than inventing
data. A tracked-but-modified file is flagged (``<sha>*``), not hidden.

Explicit values win over derivation via the drawing-settings dict and are
recorded as data on the block (``overrides``), so a regenerated drawing
knows which fields were pinned by a human and which are derived.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_REV_ROWS = 5           # revision-history rows shown on the sheet
_FIELDS = ("owner", "title", "drawing_number", "revision", "date", "author",
           "approved_by", "projection", "units", "sheet_no", "sheet_count")


@dataclass
class TitleBlock:
    """Resolved field values for one sheet. All strings; blank means
    "unknown", never a guess."""
    owner: str = ""
    title: str = ""
    drawing_number: str = ""
    revision: str = ""
    date: str = ""
    author: str = ""
    approved_by: str = ""
    scale: str = "1:1"
    projection: str = "third"           # "first" | "third"
    units: str = "mm"
    sheet_name: str = "A3"
    sheet_no: int = 1
    sheet_count: int = 1
    revisions: list[tuple[str, str, str]] = field(default_factory=list)
    overrides: dict = field(default_factory=dict)


def _git(args: list[str], cwd: str | None) -> str:
    """Run git; any failure at all (no git, no repo, untracked file) is an
    empty string — blank fields, never a lie."""
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


@lru_cache(maxsize=64)
def _user_name(cwd: str | None) -> str:
    """git config user.name, cached per directory — every drawing render
    resolves a block, and the config does not change mid-process."""
    return _git(["config", "user.name"], cwd)


def git_fields(source_path: str | None) -> dict:
    """Fields derivable from the repository around ``source_path``."""
    cwd = None
    rel = None
    if source_path:
        p = Path(source_path)
        cwd, rel = str(p.parent), p.name
    out: dict = {}
    name = _user_name(cwd)
    if name:
        out["author"] = name
    if rel is None:
        return out
    log = _git(["log", "--follow", "--format=%h|%ad|%s",
                "--date=format:%Y-%m-%d", "--", rel], cwd)
    if not log:
        return out
    rows = [line.split("|", 2) for line in log.splitlines()
            if line.count("|") >= 2]
    if not rows:
        return out
    dirty = bool(_git(["status", "--porcelain", "--", rel], cwd))
    out["revision"] = rows[0][0] + ("*" if dirty else "")
    out["date"] = rows[0][1]
    out["revisions"] = [(h, d, s) for h, d, s in rows[:_REV_ROWS]]
    return out


def _drawing_number(title: str, source_path: str | None) -> str:
    """Part name -> drawing number: the source file stem (or the title),
    uppercased, spaces collapsed to dashes. Derived, deterministic data."""
    stem = title
    if source_path:
        stem = Path(source_path).name
        for suffix in (".gitcad.json", ".json"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
    slug = re.sub(r"[^A-Z0-9._-]+", "-", stem.upper()).strip("-")
    return slug


def resolve_title_block(*, title: str, scale: str, sheet_name: str,
                        settings: dict | None = None,
                        part_name: str | None = None) -> TitleBlock:
    """Derive the block from git + the part name, then apply explicit
    overrides from the drawing-settings dict (recorded in ``overrides``).
    ``part_name`` feeds the derived drawing number when the sheet title is a
    composed string (section/assembly views); it defaults to the title."""
    settings = dict(settings or {})
    source_path = settings.pop("source_path", None)

    block = TitleBlock(title=title, scale=scale, sheet_name=sheet_name)
    derived = git_fields(source_path)
    block.author = derived.get("author", "")
    block.revision = derived.get("revision", "")
    block.date = derived.get("date", "")
    block.revisions = derived.get("revisions", [])
    block.drawing_number = _drawing_number(part_name or title, source_path)

    for key in _FIELDS:
        if key in settings and settings[key] is not None:
            setattr(block, key, settings[key])
            block.overrides[key] = settings[key]
    if "revisions" in settings and settings["revisions"] is not None:
        block.revisions = [tuple(r) for r in settings["revisions"]]
        block.overrides["revisions"] = block.revisions
    if block.projection not in ("first", "third"):
        raise ValueError(f"projection must be 'first' or 'third', "
                         f"got {block.projection!r}")
    return block
