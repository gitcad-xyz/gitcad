"""gitcad — agent-first, headless, git-native CAD.

Public surface is intentionally small. The load-bearing boundaries are the six
seams in :mod:`gitcad.seams`; everything else is an implementation behind one.
"""

from gitcad.document import Document, Feature
from gitcad.errors import (
    GeometryInvalidError,
    GitcadError,
    IdentityError,
    KernelError,
)
from gitcad.identity import EntityId, IdentityService

__version__ = "0.2.0"

__all__ = [
    "Document",
    "Feature",
    "EntityId",
    "IdentityService",
    "GitcadError",
    "KernelError",
    "GeometryInvalidError",
    "IdentityError",
    "__version__",
]
