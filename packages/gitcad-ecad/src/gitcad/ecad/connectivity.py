"""Copper connectivity — the unrouted-net and short checks (feature-map B4).

Parity checks *declared* nets; DRC checks *spacing*. This closes the third
gap: does the copper actually form the circuit? Pure geometry — items that
touch (copper distance 0) on a shared layer are connected, vias bridge
layers, and then:

- every net's pads must land in ONE connected component  → else unrouted
- no component may span two different nets' pads          → else short

Geometric, not label-trusting: a mislabeled track that physically bridges
two nets is reported as the short it is.
"""

from __future__ import annotations

from gitcad.ecad.board import Board
from gitcad.ecad.drc import _copper_dist, _items
from gitcad.errors import ValidationReport

_TOUCH_TOL = 1e-9


class _DSU:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def check_connectivity(board: Board) -> ValidationReport:
    items = _items(board)
    dsu = _DSU(len(items))
    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            b = items[j]
            if not any(a.on(layer) and b.on(layer) for layer in ("top", "bottom")):
                continue
            if _copper_dist(a, b) <= _TOUCH_TOL:
                dsu.union(i, j)

    violations: list[str] = []

    # net -> pad item indices
    net_pads: dict[str, list[int]] = {}
    for i, it in enumerate(items):
        if it.kind == "pad" and it.net:
            net_pads.setdefault(it.net, []).append(i)

    for net, pads in sorted(net_pads.items()):
        roots = {dsu.find(i) for i in pads}
        if len(roots) > 1:
            islands = len(roots)
            labels = ",".join(items[i].label for i in pads)
            violations.append(f"net-unrouted:{net}:{islands}islands:{labels}")

    # shorts: one copper component containing pads of different nets
    by_root: dict[int, set[str]] = {}
    for net, pads in net_pads.items():
        for i in pads:
            by_root.setdefault(dsu.find(i), set()).add(net)
    for root, nets in sorted(by_root.items()):
        if len(nets) > 1:
            violations.append(f"net-short:{'+'.join(sorted(nets))}")

    return ValidationReport(
        ok=not violations,
        checks={"copper_items": len(items), "nets": len(net_pads),
                "pads_with_nets": sum(len(v) for v in net_pads.values()),
                "method": "geometric-touch-graph"},
        violations=violations,
    )
