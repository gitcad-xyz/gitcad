"""Teardrop generation — reliability copper at track-to-barrel junctions.

A teardrop is extra copper easing the transition where a thin track meets
a wider via or through-pad barrel: it guards against drill breakout and
pad lift. Agent-first form: a generator op — ``generate_teardrops`` adds
same-net copper zones (wedges) at every qualifying junction, and the
normal check chain (DRC clearance, connectivity) gates the result like
any other copper edit. Deterministic and idempotent: a wedge whose exact
polygon already exists on the board is never added twice.
"""

from __future__ import annotations

import math

from gitcad.ecad.board import Board, Zone

_TOL = 0.01


def generate_teardrops(board: Board, *, length_ratio: float = 1.0,
                       width_ratio: float = 0.9) -> int:
    """Add teardrop wedges where track ends meet vias or through-pads whose
    barrel is wider than the track. Returns the number added. Wedge length
    = barrel radius * ``length_ratio`` beyond the barrel edge; base width
    = barrel diameter * ``width_ratio``."""
    existing = {(z.net, z.layer, tuple(z.polygon)) for z in board.zones}

    # barrels: (x, y, radius, layer-set or None for all)
    copper = board.copper_layers()
    barrels: list[tuple[float, float, float, frozenset | None]] = []
    for v in board.vias:
        sp = v.span(copper)
        barrels.append((v.x, v.y, v.diameter / 2,
                        frozenset(sp) if sp else None))
    for comp in board.components:
        for pad, bx, by, _rot in comp.placed_pads():
            if pad.drill is not None and pad.shape == "circle":
                barrels.append((bx, by, max(pad.w, pad.h) / 2, None))

    added = 0
    for t in board.tracks:
        for (ex, ey), (ox, oy) in (((t.x1, t.y1), (t.x2, t.y2)),
                                   ((t.x2, t.y2), (t.x1, t.y1))):
            for bx, by, r, span in barrels:
                if abs(ex - bx) > _TOL or abs(ey - by) > _TOL:
                    continue
                if span is not None and t.layer not in span:
                    continue
                if t.width >= 2 * r * width_ratio:
                    continue                        # track as wide as the barrel
                dx, dy = ox - bx, oy - by
                d = math.hypot(dx, dy)
                if d < 1e-9:
                    continue
                ux, uy = dx / d, dy / d             # along the track
                px, py = -uy, ux                    # perpendicular
                base = r * width_ratio
                apex = min(r * (1 + length_ratio), d)
                poly = [
                    (bx + px * base, by + py * base),
                    (bx + ux * apex + px * t.width / 2,
                     by + uy * apex + py * t.width / 2),
                    (bx + ux * apex - px * t.width / 2,
                     by + uy * apex - py * t.width / 2),
                    (bx - px * base, by - py * base),
                ]
                rounded = [(round(x, 4), round(y, 4)) for x, y in poly]
                key = (t.net, t.layer, tuple(rounded))
                if key in existing:
                    continue                        # idempotent re-run
                existing.add(key)
                board.zones.append(Zone(net=t.net, layer=t.layer,
                                        polygon=rounded, kind="copper"))
                added += 1
    return added
