"""Semantic versions and dependency constraints (ADR-0009).

Small on purpose: exactly the subset the lockfile needs — `^` (compatible),
`~` (patch-level), exact, and `*`. No pre-release/build tags in v1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

from gitcad.errors import GitcadError

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

BUMPS = ("patch", "minor", "major")


@total_ordering
@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> "Version":
        m = _VERSION_RE.match(text.strip())
        if not m:
            raise GitcadError(f"invalid version {text!r} (want MAJOR.MINOR.PATCH)")
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __lt__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def bump(self, kind: str) -> "Version":
        if kind == "major":
            return Version(self.major + 1, 0, 0)
        if kind == "minor":
            return Version(self.major, self.minor + 1, 0)
        if kind == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise GitcadError(f"unknown bump kind {kind!r}")

    def actual_bump_from(self, old: "Version") -> str | None:
        """What kind of bump this version is relative to ``old`` — or None if
        it isn't a single well-formed bump (arbitrary jumps are allowed but
        classified by the highest changed field)."""
        if self <= old:
            return None
        if self.major > old.major:
            return "major"
        if self.minor > old.minor:
            return "minor"
        return "patch"


def satisfies(version: Version | str, constraint: str) -> bool:
    """Does ``version`` satisfy ``constraint``? (`^x.y.z`, `~x.y.z`, exact, `*`)"""
    v = Version.parse(version) if isinstance(version, str) else version
    c = constraint.strip()
    if c == "*":
        return True
    if c.startswith("^"):
        base = Version.parse(c[1:])
        if base.major > 0:
            return base <= v < Version(base.major + 1, 0, 0)
        # ^0.y.z: 0.x versions treat minor as breaking (npm/cargo convention)
        return base <= v < Version(0, base.minor + 1, 0)
    if c.startswith("~"):
        base = Version.parse(c[1:])
        return base <= v < Version(base.major, base.minor + 1, 0)
    return v == Version.parse(c)
