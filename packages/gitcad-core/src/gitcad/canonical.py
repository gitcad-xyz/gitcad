"""The one canonicalization policy for every serialized number (ADR-0004).

Canonical text is load-bearing: identities, content hashes, lockfiles, and
semantic diffs all assume "semantically equal ⇒ byte-identical". Floats are
where that promise quietly breaks, so every module that serializes model data
routes numbers through here. The rules:

1. **Non-finite numbers are rejected.** NaN/Infinity are not geometry; JSON's
   default ``allow_nan=True`` would emit non-JSON and break hash equality
   (``nan != nan``).
2. **Negative zero is normalized to zero.** ``round(-1e-9, 6)`` is ``-0.0``,
   which serializes as ``"-0.0"`` — float noise crossing zero must never split
   an identity or a hash.
3. **All non-bool numbers serialize as floats.** ``{"dx": 1}`` and
   ``{"dx": 1.0}`` are the same model and must hash identically.

(Reviewed 2026-07-22: all three holes were verified live before this module
existed — see docs/reviews/2026-07-22-early-architecture-review.md.)
"""

from __future__ import annotations

import json
import math
from typing import Any

from gitcad.errors import GitcadError


def canon_number(v: float) -> float:
    """Apply rules 1-3 to a single number."""
    if not math.isfinite(v):
        raise GitcadError(f"non-finite number is not serializable: {v!r}")
    return float(v) + 0.0  # int -> float; -0.0 + 0.0 == 0.0


def canonicalize(obj: Any) -> Any:
    """Recursively canonicalize every number in a JSON-able structure.
    Bools are preserved (bool is an int subclass — check it first)."""
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float)):
        return canon_number(obj)
    if isinstance(obj, dict):
        return {k: canonicalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [canonicalize(v) for v in obj]
    raise GitcadError(f"not canonically serializable: {type(obj).__name__}")


def canonical_json(obj: Any, *, indent: int | None = None) -> str:
    """Canonical JSON text: numbers per the rules above, sorted keys, no NaN
    escape hatch. THE serializer for model/board/part/lock text."""
    return json.dumps(canonicalize(obj), indent=indent, sort_keys=True,
                      allow_nan=False,
                      separators=(",", ":") if indent is None else None)
