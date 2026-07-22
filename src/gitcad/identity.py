"""Stable entity identity — the topological-naming fix.

The problem: a downstream feature references "face 7". An upstream edit adds a
feature, the kernel renumbers faces, and "face 7" silently becomes a different
face. Every reference downstream corrupts. This is FreeCAD's most notorious
weakness and it is *fatal* to a git workflow, where merges and rebases reorder
operations constantly (ADR-0003).

The fix: an entity's identity is derived from **how it was constructed** (its
lineage) plus a **geometric fingerprint** — never from an ordinal index. Two
rebuilds of the same construction yield the same ID; an unrelated edit upstream
does not perturb the IDs of entities it didn't touch.

This module is pure Python and has no kernel dependency, so identity logic is
fully unit-testable without OCCT.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError


@dataclass(frozen=True)
class EntityId:
    """A durable reference to a topological entity (face/edge/vertex)."""

    value: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


def _round_geo(descriptor: dict[str, Any], ndigits: int) -> dict[str, Any]:
    """Round geometric quantities so floating-point noise doesn't split an
    identity. ``+ 0.0`` normalizes the ``-0.0`` that rounding a tiny negative
    produces — without it, noise crossing zero splits identities (reviewed
    2026-07-22). Non-numeric fields pass through unchanged."""
    def r(x: Any) -> Any:
        return round(x, ndigits) + 0.0 if isinstance(x, float) else x

    out: dict[str, Any] = {}
    for k, v in descriptor.items():
        if isinstance(v, (list, tuple)):
            out[k] = [r(x) for x in v]
        else:
            out[k] = r(v)
    return out


class IdentityService:
    """Default identity backend: lineage + rounded geometric fingerprint hash.

    ``assign`` is deterministic and collision-resistant across unrelated
    constructions. ``resolve`` re-binds a stored ID after a rebuild by scoring
    candidate entities against the fingerprint embedded in the ID.
    """

    def __init__(self, *, geo_tolerance_digits: int = 6, id_length: int = 16) -> None:
        self._digits = geo_tolerance_digits
        self._id_length = id_length
        # Maps an assigned id -> the fingerprint payload it was minted from, so
        # resolve() can re-match without re-deriving lineage.
        self._registry: dict[str, dict[str, Any]] = {}

    def assign(self, descriptor: dict[str, Any], lineage: tuple[str, ...]) -> str:
        """Mint a stable id for an entity.

        ``descriptor``: the kernel's order-independent semantic description of
        the entity (surface type, rounded area, adjacency roles, ...).
        ``lineage``: the ids of the features that created it (creation history).
        """
        payload = {
            "lineage": list(lineage),
            "geo": _round_geo(descriptor, self._digits),
        }
        digest = hashlib.blake2b(canonical_json(payload).encode(), digest_size=self._id_length).hexdigest()
        entity_id = f"e_{digest}"
        self._registry[entity_id] = payload
        return entity_id

    # -- persistence (ADR-0003: stored ids must resolve in future processes) --

    SCHEMA = "gitcad/identity@1"

    def dumps(self) -> str:
        """Canonical text of the registry — commit it alongside the model
        (like a lockfile) so entity ids stored in document text can re-bind
        after a rebuild in another process."""
        return canonical_json({"schema": self.SCHEMA, "registry": self._registry}, indent=2) + "\n"

    @classmethod
    def loads(cls, text: str, **kwargs: Any) -> "IdentityService":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported identity schema {doc.get('schema')!r}")
        svc = cls(**kwargs)
        svc._registry = dict(doc["registry"])
        return svc

    def resolve(self, entity_id: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Re-bind ``entity_id`` to the best current candidate after a rebuild.

        Returns the winning candidate descriptor, or ``None`` if nothing matches
        well enough (the entity was genuinely removed). Scoring is a simple
        geometric-similarity vote; a real backend would weight adjacency too.
        """
        payload = self._registry.get(entity_id)
        if payload is None:
            return None
        target = payload["geo"]
        best: tuple[float, dict[str, Any]] | None = None
        for cand in candidates:
            score = _similarity(target, _round_geo(cand, self._digits))
            if best is None or score > best[0]:
                best = (score, cand)
        if best is None or best[0] < 0.5:
            return None
        return best[1]


def _similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Fraction of shared keys whose values match. Deliberately simple and
    explainable — identity heuristics should be auditable, not magical."""
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    matches = sum(1 for k in keys if a.get(k) == b.get(k))
    return matches / len(keys)
