"""Autorouting assist v1 — a grid maze router for agents.

Not push-and-shove: a deterministic BFS over a clearance-aware obstacle
grid (Lee router), one net at a time, through-vias for layer changes.
The result is ordinary Tracks/Vias appended to the board — the same
check chain that gates hand routing (DRC, connectivity) gates this.
Honest refusal: no path means ``autoroute-no-path``, never a
rules-violating trace.

Scope v1: routes between the net's pad centers on the outer layers (or
any copper layer list you pass), rectilinear steps on a fixed grid.
Pour-covered boards refuse fast — a pour IS the route.
"""

from __future__ import annotations

from gitcad.ecad.board import Board, Track, Via
from gitcad.errors import GitcadError


def autoroute(board: Board, net: str, *, grid: float = 0.25,
              width: float = 0.25, clearance: float = 0.2,
              layers: tuple[str, ...] | None = None,
              via_drill: float = 0.4, via_diameter: float = 0.8) -> dict:
    """Route every pad of ``net`` into one connected tree. Returns
    {"tracks": n, "vias": n}. Raises GitcadError when no path exists."""
    copper = board.copper_layers()
    layer_list = list(layers) if layers else ["top", "bottom"]
    for ly in layer_list:
        if ly not in copper:
            raise GitcadError(f"unknown layer {ly!r}")

    minx, miny, maxx, maxy = board.bbox()
    nx = int((maxx - minx) / grid) + 1
    ny = int((maxy - miny) / grid) + 1
    if nx * ny > 1_500_000:
        raise GitcadError(
            f"autoroute grid {nx}x{ny} too large — coarsen `grid`")

    def cell(x: float, y: float) -> tuple[int, int]:
        return (round((x - minx) / grid), round((y - miny) / grid))

    def pos(c: tuple[int, int]) -> tuple[float, float]:
        return (minx + c[0] * grid, miny + c[1] * grid)

    # -- obstacle rasterization (other-net copper, inflated) -------------------
    # tracks need clearance + track half-width; via barrels are wider, so
    # via placement checks a second grid with the bigger margin
    margin = clearance + width / 2
    margin_via = clearance + via_diameter / 2
    blocked: list[set] = [set() for _ in layer_list]
    blocked_via: list[set] = [set() for _ in layer_list]
    li = {name: i for i, name in enumerate(layer_list)}

    def block_disc(x: float, y: float, r: float, idxs) -> None:
        for grid_set, mg in ((blocked, margin), (blocked_via, margin_via)):
            rr = r + mg
            c0x, c0y = cell(x - rr, y - rr)
            c1x, c1y = cell(x + rr, y + rr)
            for cx in range(max(0, c0x), min(nx, c1x + 1)):
                for cy in range(max(0, c0y), min(ny, c1y + 1)):
                    px, py = pos((cx, cy))
                    if (px - x) ** 2 + (py - y) ** 2 <= rr * rr:
                        for i in idxs:
                            grid_set[i].add((cx, cy))

    def block_seg(x1, y1, x2, y2, half_w, idx) -> None:
        steps = max(1, int(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 / grid) * 2)
        for s in range(steps + 1):
            t = s / steps
            block_disc(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, half_w, [idx])

    all_idx = list(range(len(layer_list)))
    for comp in board.components:
        for pad, bx, by, rot in comp.placed_pads():
            if comp.nets.get(pad.name, "") == net:
                continue
            w, h = (pad.h, pad.w) if round(rot) % 180 == 90 else (pad.w, pad.h)
            r = max(w, h) / 2
            if pad.drill is not None:
                block_disc(bx, by, r, all_idx)
            elif comp.side in li:
                block_disc(bx, by, r, [li[comp.side]])
    for v in board.vias:
        if v.net == net:
            continue
        sp = set(v.span(copper))
        idxs = [li[ly] for ly in layer_list if ly in sp] or all_idx
        block_disc(v.x, v.y, v.diameter / 2, idxs)
    for t in board.tracks:
        if t.net == net or t.layer not in li:
            continue
        block_seg(t.x1, t.y1, t.x2, t.y2, t.width / 2, li[t.layer])
    for z in board.zones:
        if z.kind == "keepout":
            xs = [p[0] for p in z.polygon]
            ys = [p[1] for p in z.polygon]
            for ly in ([z.layer] if z.layer in li else []):
                c0, c1 = cell(min(xs), min(ys)), cell(max(xs), max(ys))
                for cx in range(max(0, c0[0]), min(nx, c1[0] + 1)):
                    for cy in range(max(0, c0[1]), min(ny, c1[1] + 1)):
                        blocked[li[ly]].add((cx, cy))
        elif z.kind == "copper" and z.net != net and z.layer in li:
            xs = [p[0] for p in z.polygon]
            ys = [p[1] for p in z.polygon]
            c0, c1 = cell(min(xs), min(ys)), cell(max(xs), max(ys))
            for cx in range(max(0, c0[0]), min(nx, c1[0] + 1)):
                for cy in range(max(0, c0[1]), min(ny, c1[1] + 1)):
                    blocked[li[z.layer]].add((cx, cy))

    # -- terminals -------------------------------------------------------------
    terminals: list[tuple[tuple[int, int], int]] = []   # (cell, layer idx)
    for comp in board.components:
        for pad, bx, by, _rot in comp.placed_pads():
            if comp.nets.get(pad.name, "") != net:
                continue
            if pad.drill is not None:
                terminals.append((cell(bx, by), 0))
            elif comp.side in li:
                terminals.append((cell(bx, by), li[comp.side]))
    if len(terminals) < 2:
        raise GitcadError(f"net {net!r} has fewer than 2 routable pads")

    # -- sequential Lee routing ------------------------------------------------
    tree: set[tuple[int, int, int]] = set()
    first_cell, first_li = terminals[0]
    tree.add((first_cell[0], first_cell[1], first_li))
    tracks_added = vias_added = 0

    for term_cell, term_li in terminals[1:]:
        start = (term_cell[0], term_cell[1], term_li)
        if start in tree:
            continue
        import heapq

        prev: dict = {start: None}
        dist: dict = {start: 0}
        heap: list[tuple[int, tuple]] = [(0, start)]
        via_cost = max(1, int(3.0 / grid))              # a via "costs" ~3 mm
        goal = None
        while heap:
            d, cur = heapq.heappop(heap)
            if d > dist.get(cur, 1 << 30):
                continue
            if cur in tree:
                goal = cur
                break
            cx, cy, cl = cur
            steps = [((cx + 1, cy, cl), 1), ((cx - 1, cy, cl), 1),
                     ((cx, cy + 1, cl), 1), ((cx, cy - 1, cl), 1)]
            for other in range(len(layer_list)):        # through-via move
                if other != cl:
                    steps.append(((cx, cy, other), via_cost))
            for nxt, cost in steps:
                tx, ty, tl = nxt
                if not (0 <= tx < nx and 0 <= ty < ny):
                    continue
                if tl != cl:                            # via: all layers clear
                    if any((tx, ty) in blocked_via[i]
                           for i in range(len(layer_list))):
                        continue
                elif (tx, ty) in blocked[tl]:
                    continue
                nd = d + cost
                if nd < dist.get(nxt, 1 << 30):
                    dist[nxt] = nd
                    prev[nxt] = cur
                    heapq.heappush(heap, (nd, nxt))
        if goal is None:
            raise GitcadError(f"autoroute-no-path:{net}")

        # walk back, merging straight runs into tracks
        path = []
        n_ = goal
        while n_ is not None:
            path.append(n_)
            n_ = prev[n_]
        run_start = path[0]
        for a, b in zip(path, path[1:]):
            if a[2] != b[2]:                            # layer change: via at a
                if run_start[:2] != a[:2]:
                    _emit(board, pos(run_start[:2]), pos(a[:2]),
                          layer_list[a[2]], width, net)
                    tracks_added += 1
                board.vias.append(Via(*pos(a[:2]), drill=via_drill,
                                      diameter=via_diameter, net=net))
                vias_added += 1
                run_start = b
            elif _turns(run_start, a, b):
                _emit(board, pos(run_start[:2]), pos(a[:2]),
                      layer_list[a[2]], width, net)
                tracks_added += 1
                run_start = a
        last = path[-1]
        if run_start[:2] != last[:2]:
            _emit(board, pos(run_start[:2]), pos(last[:2]),
                  layer_list[last[2]], width, net)
            tracks_added += 1
        tree.update(path)

    return {"tracks": tracks_added, "vias": vias_added}


def _turns(run_start, a, b) -> bool:
    return ((b[0] - run_start[0]) * (a[1] - run_start[1])
            != (b[1] - run_start[1]) * (a[0] - run_start[0]))


def _emit(board: Board, p1, p2, layer: str, width: float, net: str) -> None:
    board.tracks.append(Track(p1[0], p1[1], p2[0], p2[1], width, layer, net))
