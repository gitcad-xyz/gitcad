"""Check waivers — a silenced check must leave a trace (KiCad-map tier 2).

KiCad has per-violation exclusions buried in project files; here a waiver
is reviewable canonical text next to the design:

    {"schema": "gitcad/waivers@1", "waivers": [
      {"match": "erc:net-single-pin:TP*", "reason": "test points", "author": "dan"}]}

Rules with teeth:
- every waiver REQUIRES a reason — suppression without rationale refused;
- ``match`` is an fnmatch glob over the violation string, so one waiver
  can cover a family without hiding unrelated failures;
- waived violations stay VISIBLE (moved to ``waived``, never deleted);
- a waiver that matches nothing is reported ``unused`` — stale
  suppressions are debt, and debt shows.
"""

from __future__ import annotations

import json
from fnmatch import fnmatchcase

from gitcad.errors import GitcadError

SCHEMA = "gitcad/waivers@1"


def load_waivers(text: str) -> list[dict]:
    doc = json.loads(text)
    if doc.get("schema") != SCHEMA:
        raise GitcadError(f"unsupported waivers schema {doc.get('schema')!r}")
    waivers = doc.get("waivers", [])
    for w in waivers:
        if not w.get("match"):
            raise GitcadError("every waiver needs a match pattern")
        if not (w.get("reason") or "").strip():
            raise GitcadError(
                f"waiver {w['match']!r} has no reason — suppression without "
                "rationale is refused")
    return waivers


def waive(violations: list[str], waivers: list[dict]
          ) -> tuple[list[str], list[dict], list[str]]:
    """(kept, waived [{violation, match, reason}], unused_matches)."""
    kept: list[str] = []
    waived: list[dict] = []
    hits = {w["match"]: 0 for w in waivers}
    for v in violations:
        for w in waivers:
            if fnmatchcase(v, w["match"]):
                hits[w["match"]] += 1
                waived.append({"violation": v, "match": w["match"],
                               "reason": w["reason"]})
                break
        else:
            kept.append(v)
    unused = [m for m, n in hits.items() if n == 0]
    return kept, waived, unused
