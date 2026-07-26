"""Board statistics + net length reporting (KiCad-map tier 2).

``board_stats`` mirrors `kicad-cli pcb export stats` — counts, areas,
drill histogram — as data, not a dialog. ``net_lengths`` sums routed
copper per net; ``check_length_match`` turns matched-pair routing (USB,
LVDS, clocks) into a named violation when lengths diverge beyond
tolerance — length tuning's *check* half (the tuning itself is routing).
"""

from __future__ import annotations

import math

from gitcad.ecad.board import Board


def _polygon_area(pts) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def board_stats(board: Board) -> dict:
    smd = sum(1 for c in board.components for p in c.footprint.pads
              if p.drill is None)
    pth = sum(1 for c in board.components for p in c.footprint.pads
              if p.drill is not None)
    drills: dict[str, int] = {}
    for c in board.components:
        for p in c.footprint.pads:
            if p.drill is not None:
                drills[f"{p.drill:g}"] = drills.get(f"{p.drill:g}", 0) + 1
    for v in board.vias:
        drills[f"{v.drill:g}"] = drills.get(f"{v.drill:g}", 0) + 1
    for m in board.mounting_holes:
        drills[f"{m.drill:g}"] = drills.get(f"{m.drill:g}", 0) + 1
    nets = {n for c in board.components for n in c.nets.values() if n}
    track_len = sum(math.hypot(t.x2 - t.x1, t.y2 - t.y1) for t in board.tracks)
    return {
        "name": board.name,
        "area_mm2": round(_polygon_area(board.outline), 3),
        "thickness_mm": board.thickness,
        "components": {"total": len(board.components),
                       "top": sum(1 for c in board.components if c.side == "top"),
                       "bottom": sum(1 for c in board.components if c.side == "bottom")},
        "pads": {"smd": smd, "through_hole": pth},
        "nets": len(nets),
        "tracks": {"count": len(board.tracks), "length_mm": round(track_len, 3)},
        "vias": len(board.vias),
        "via_kinds": {k: sum(1 for v in board.vias
                             if v.kind(board.copper_layers()) == k)
                      for k in ("through", "blind", "buried")},
        "zones": sum(1 for z in board.zones if z.kind == "copper"),
        "keepouts": sum(1 for z in board.zones if z.kind == "keepout"),
        "mounting_holes": len(board.mounting_holes),
        "drill_sizes_mm": dict(sorted(drills.items())),
    }


def net_lengths(board: Board) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for t in board.tracks:
        if not t.net:
            continue
        e = out.setdefault(t.net, {"track_mm": 0.0, "segments": 0})
        e["track_mm"] += math.hypot(t.x2 - t.x1, t.y2 - t.y1)
        e["segments"] += 1
    for e in out.values():
        e["track_mm"] = round(e["track_mm"], 3)
    return out


def check_length_match(board: Board, pairs: list[tuple[str, str]],
                       tol_mm: float = 1.0):
    """Matched-pair length check: |len(a) - len(b)| <= tol, both routed."""
    from gitcad.errors import ValidationReport

    lengths = net_lengths(board)
    violations: list[str] = []
    detail: dict[str, str] = {}
    for a, b in pairs:
        la = lengths.get(a, {}).get("track_mm")
        lb = lengths.get(b, {}).get("track_mm")
        if la is None or lb is None:
            missing = a if la is None else b
            violations.append(f"length-match-unrouted:{missing}")
            continue
        delta = abs(la - lb)
        detail[f"{a}~{b}"] = f"{la}mm vs {lb}mm (d={delta:.3f}mm)"
        if delta > tol_mm + 1e-9:
            violations.append(
                f"length-mismatch:{a}~{b}:d={delta:.3f}mm>{tol_mm:g}mm")
    return ValidationReport(ok=not violations,
                            checks={"pairs": detail, "tol_mm": tol_mm},
                            violations=violations)
