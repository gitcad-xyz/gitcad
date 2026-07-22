"""PCBA parts — the Fusion-360 duality, gitcad-style.

At the assembly level a PCBA is a mechanical part: envelope, mounting-hole
ports, a 3D body. ``pcba_verify`` is what "entering" it means for checks —
one call runs the complete electrical workflow gate over the part's
referenced sources:

- ERC + electrical envelopes (ADR-0015) per schematic
- board validation + DRC + copper connectivity
- schematic↔board parity (the ECO check) for every schematic

The part manifest is the front door; the electrical truth lives in the
files it references, exactly like a mech part references its .model.
"""

from __future__ import annotations

import json
from pathlib import Path

from gitcad.errors import GitcadError


def is_pcba(part_text: str) -> bool:
    try:
        doc = json.loads(part_text)
    except Exception:
        return False
    return (doc.get("schema", "").startswith("gitcad/part")
            and (doc.get("body") or {}).get("kind") == "pcba")


def pcba_sources(part_text: str, root: str) -> dict:
    """Resolve the PCBA's referenced files: {"board": Path, "schematics": [Path]}."""
    from gitcad.part import PartManifest

    part = PartManifest.loads(part_text)
    body = part.body or {}
    if body.get("kind") != "pcba":
        raise GitcadError(f"part {part.name!r} is not a pcba (body.kind="
                          f"{body.get('kind')!r})")
    rootp = Path(root)
    board = rootp / body.get("board", "")
    if not body.get("board") or not board.is_file():
        raise GitcadError(f"pcba board file missing: {body.get('board')!r}")
    schematics = []
    for rel in body.get("schematics", []):
        p = rootp / rel
        if not p.is_file():
            raise GitcadError(f"pcba schematic file missing: {rel!r}")
        schematics.append(p)
    return {"part": part, "board": board, "schematics": schematics}


def pcba_verify(part_text: str, root: str) -> dict:
    """The electrical workflow's gate, as one call.

    Multi-schematic semantics: a board's netlist can span many sheets, so
    ERC, envelopes, and parity run on the MERGED system schematic (nets
    union by name — the cross-sheet contract, ADR proved on the real
    4-sheet Altair where per-sheet checks flag inter-sheet signals as
    false positives). Per-sheet checks would lie; the merged system is
    the electrical truth of this PCBA. Coverage is honest: zero referenced
    schematics is visible, never silently green."""
    from gitcad.ecad import (Board, Schematic, board_parity, check_connectivity,
                             check_envelopes, merge_schematics)
    from gitcad.ecad.drc import run_drc

    src = pcba_sources(part_text, root)
    board = Board.loads(src["board"].read_text(encoding="utf-8"))
    checks: dict = {}
    violations: list[str] = []

    r = board.validate()
    checks["board:validate"] = "ok" if r.ok else "FAIL"
    violations += [f"board:{v}" for v in r.violations]
    d = run_drc(board)
    checks["board:drc"] = "ok" if d.ok else "FAIL"
    violations += [f"drc:{v}" for v in d.violations]
    c = check_connectivity(board)
    checks["board:connectivity"] = "ok" if c.ok else "FAIL"
    violations += [f"connectivity:{v}" for v in c.violations]

    sheets = [Schematic.loads(p.read_text(encoding="utf-8"))
              for p in src["schematics"]]
    if sheets:
        system = sheets[0] if len(sheets) == 1 else \
            merge_schematics(f"{src['part'].name}-system", sheets)
        e = system.erc()
        checks["system:erc"] = "ok" if e.ok else "FAIL"
        violations += [f"erc:{v}" for v in e.violations]
        env = check_envelopes(system)
        checks["system:envelope"] = "ok" if env.ok else "FAIL"
        violations += [f"envelope:{v}" for v in env.violations]
        p = board_parity(system, board)
        checks["system:parity"] = "ok" if p.ok else "FAIL"
        violations += [f"parity:{v}" for v in p.violations]

    checks["schematics_checked"] = len(sheets)
    return {"ok": not violations, "part": src["part"].name,
            "checks": checks, "violations": violations}
