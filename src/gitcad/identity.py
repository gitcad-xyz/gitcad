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


@dataclass(frozen=True)
class EntityId:
    """A durable reference to a topological entity (face/edge/vertex)."""

    value: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


def _canonical(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace jitter. Determinism here
    is load-bearing — the same construction must hash identically on every run
    and every machine, or IDs would not be stable."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _round_geo(descriptor: dict[str, Any], ndigits: int) -> dict[str, Any]:
    """Round geometric quantities so floating-point noise doesn't split an
    identity. Non-numeric fields pass through unchanged."""
    out: dict[str, Any] = {}
    for k, v in descriptor.items():
        if isinstance(v, float):
            out[k] = round(v, ndigits)
        elif isinstance(v, (list, tuple)):
            out[k] = [round(x, ndigits) if isinstance(x, float) else x for x in v]
        else:
            out[k] = v
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
        digest = hashlib.blake2b(_canonical(payload).encode(), digest_size=self._id_length).hexdigest()
        entity_id = f"e_{digest}"
        self._registry[entity_id] = payload
        return entity_id

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
