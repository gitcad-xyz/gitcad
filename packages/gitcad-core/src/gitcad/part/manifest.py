"""The part manifest — ``part.json`` (ADR-0008).

Domain-neutral wrapper every part carries: identity, version, interface, deps,
and an opaque domain-specific body core never parses. Canonical serialization
and content hashing follow the same rules as the document model (ADR-0004):
byte-stable text is what makes locks, diffs, and releases trustworthy.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError
from gitcad.part.interface import Interface
from gitcad.part.semver import Version

KNOWN_DOMAINS = {"mech", "ecad", "ecad.component", "assembly"}  # open set; these get validation


def new_part_id() -> str:
    """Mint a part id. Assigned once at creation and stable forever — never
    derived from name or path (ADR-0003 discipline, one level up)."""
    return "prt_" + secrets.token_hex(8)


@dataclass
class PartManifest:
    id: str
    name: str
    domain: str
    version: str
    interface: Interface = field(default_factory=Interface)
    deps: dict[str, str] = field(default_factory=dict)   # part id -> constraint
    body: dict = field(default_factory=dict)

    SCHEMA = "gitcad/part@1"

    def __post_init__(self) -> None:
        if not self.id.startswith("prt_"):
            raise GitcadError(f"part id must start with 'prt_': {self.id!r}")
        Version.parse(self.version)  # validates

    def dumps(self) -> str:
        doc = {
            "schema": self.SCHEMA,
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "version": self.version,
            "interface": self.interface.to_dict(),
            "deps": dict(sorted(self.deps.items())),
            "body": self.body,
        }
        return canonical_json(doc, indent=2) + "\n"

    @classmethod
    def loads(cls, text: str) -> "PartManifest":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported part schema {doc.get('schema')!r}")
        return cls(
            id=doc["id"],
            name=doc["name"],
            domain=doc["domain"],
            version=doc["version"],
            interface=Interface.from_dict(doc["interface"]),
            deps=dict(doc.get("deps", {})),
            body=dict(doc.get("body", {})),
        )

    def content_hash(self) -> str:
        """Hash of the canonical text — what the lockfile pins (ADR-0009)."""
        return "blake2b:" + hashlib.blake2b(self.dumps().encode(), digest_size=16).hexdigest()
