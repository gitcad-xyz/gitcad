"""The Part standard — gitcad's cross-domain interchange contract (ADR-0008/9).

One unit across all domains: a Part is a manifest (domain-neutral) + a body
(domain-specific) + an interface (domain-neutral). An Assembly is a Part whose
body is composition. Versioning is interface-semver with a lockfile.

This package is pure Python, kernel-free, and CODEOWNERS-protected: it is the
most change-resistant surface gitcad owns.
"""

from gitcad.part.assembly import Assembly, Instance, Mate
from gitcad.part.interface import Frame, Interface, Port, check_release, classify_change
from gitcad.part.lockfile import Lockfile, Workspace, resolve
from gitcad.part.manifest import PartManifest, new_part_id
from gitcad.part.semver import Version, satisfies

__all__ = [
    "PartManifest", "new_part_id",
    "Interface", "Frame", "Port", "classify_change", "check_release",
    "Assembly", "Instance", "Mate",
    "Lockfile", "Workspace", "resolve",
    "Version", "satisfies",
]
