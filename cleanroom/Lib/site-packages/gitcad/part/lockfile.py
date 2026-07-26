"""Dependency resolution and the lockfile (ADR-0009).

A dependency is an intent constraint (`^1.4`); the lock pins the exact resolved
version *and its canonical-text content hash*, so a build is byte-reproducible
from a git tag forever. Resolution is deliberately simple in v1: highest
available version satisfying the constraint, from a local Workspace (a
directory of part.json files). The registry (ADR-0010) slots in behind the
same Workspace shape later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError
from gitcad.part.manifest import PartManifest
from gitcad.part.semver import Version, satisfies


class Workspace:
    """All known part versions, keyed by part id. v1 source: a directory tree
    scanned for ``*.part.json`` / ``part.json`` files."""

    def __init__(self) -> None:
        self._versions: dict[str, dict[str, PartManifest]] = {}

    def add(self, manifest: PartManifest) -> None:
        self._versions.setdefault(manifest.id, {})[manifest.version] = manifest

    @classmethod
    def scan(cls, root: str) -> "Workspace":
        ws = cls()
        for path in sorted(Path(root).rglob("*part.json")):
            ws.add(PartManifest.loads(path.read_text()))
        return ws

    @classmethod
    def from_git(cls, url: str, *, ref: str = "main", cache_dir: str | None = None) -> "Workspace":
        """A workspace backed by a git registry (e.g. gitcad-xyz/registry).

        Shallow-clones (or updates) into a local cache and scans it — the
        registry IS a git repo (ADR-0010), so the client is just git + scan.
        Resolution then pins content hashes (ADR-0009) exactly as with any
        local workspace.
        """
        import hashlib
        import subprocess
        import tempfile

        key = hashlib.blake2b(f"{url}#{ref}".encode(), digest_size=8).hexdigest()
        dest = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "gitcad-registry" / key
        if (dest / ".git").exists():
            subprocess.run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", ref],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"],
                           check=True, capture_output=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--depth", "1", "--branch", ref, url, str(dest)],
                           check=True, capture_output=True)
        return cls.scan(str(dest))

    def versions_of(self, part_id: str) -> list[str]:
        return sorted(self._versions.get(part_id, {}), key=Version.parse)

    def get(self, part_id: str, version: str) -> PartManifest:
        try:
            return self._versions[part_id][version]
        except KeyError:
            raise GitcadError(f"workspace has no {part_id}@{version}") from None


@dataclass
class Lockfile:
    """{part id: {version, content}} — committed next to the consumer."""

    locks: dict[str, dict[str, str]] = field(default_factory=dict)

    SCHEMA = "gitcad/lock@1"

    def dumps(self) -> str:
        return canonical_json({"schema": self.SCHEMA, "locks": self.locks}, indent=2) + "\n"

    @classmethod
    def loads(cls, text: str) -> "Lockfile":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported lock schema {doc.get('schema')!r}")
        return cls(locks=dict(doc["locks"]))

    def verify(self, workspace: Workspace) -> list[str]:
        """Confirm every locked hash still matches the workspace content —
        catches tampering and accidental drift. Empty list = sound."""
        problems: list[str] = []
        for part_id, entry in sorted(self.locks.items()):
            try:
                manifest = workspace.get(part_id, entry["version"])
            except GitcadError:
                problems.append(f"missing:{part_id}@{entry['version']}")
                continue
            actual = manifest.content_hash()
            if actual != entry["content"]:
                problems.append(f"hash-mismatch:{part_id}@{entry['version']}")
        return problems


def resolve(consumer: PartManifest, workspace: Workspace) -> Lockfile:
    """Resolve ``consumer.deps`` (and transitively their deps) against the
    workspace: highest version satisfying each constraint. Deterministic —
    same workspace + same manifest → identical lockfile."""
    lock = Lockfile()
    queue = list(consumer.deps.items())
    while queue:
        part_id, constraint = queue.pop(0)
        candidates = [v for v in workspace.versions_of(part_id) if satisfies(v, constraint)]
        if not candidates:
            raise GitcadError(
                f"unresolvable: {part_id} {constraint!r} "
                f"(available: {workspace.versions_of(part_id) or 'none'})"
            )
        chosen = candidates[-1]  # versions_of is sorted ascending
        prior = lock.locks.get(part_id)
        if prior is not None:
            if prior["version"] != chosen and not satisfies(prior["version"], constraint):
                raise GitcadError(f"conflict: {part_id} locked {prior['version']}, needs {constraint}")
            continue
        manifest = workspace.get(part_id, chosen)
        lock.locks[part_id] = {"version": chosen, "content": manifest.content_hash()}
        queue.extend(manifest.deps.items())
    return lock
