"""mate_solve — place instances by mate intent (ADR-0014, authoring-time).

The build never solves; it only checks. This tool runs at authoring time,
computes the rigid translation that makes each mated port pair coincide,
and writes the solved transforms back into the assembly — which then
validates like any hand-placed assembly. Rotation is respected but not
solved (v1: rotate_z_deg stays what the author set; the solve moves, it
does not spin — spinning has branch multiplicity, translation does not).

Traversal is BFS from a base instance (the most-mated, ties by name — the
same deterministic choice auto_explode makes). A mate between two
already-placed instances becomes a CHECK: if their ports don't coincide,
that's an over-constraint conflict, reported with the gap, never "fixed"
by silently moving something the solver already placed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gitcad.part.assembly import Assembly


@dataclass
class MateSolveReport:
    base: str = ""
    solved: list[str] = field(default_factory=list)      # instances moved
    unreachable: list[str] = field(default_factory=list)  # no mate path to base
    conflicts: list[str] = field(default_factory=list)   # "a.p<->b.q:gap=..mm"

    @property
    def ok(self) -> bool:
        return not self.conflicts

    def to_dict(self) -> dict:
        return {"base": self.base, "solved": self.solved,
                "unreachable": self.unreachable,
                "conflicts": self.conflicts, "ok": self.ok}


def mate_solve(asm: Assembly, *, base: str | None = None,
               tol: float = 1e-6) -> MateSolveReport:
    """Solve instance translations so mated ports coincide. Mutates ``asm``
    (authoring writes back into reviewable text); returns the report."""
    report = MateSolveReport()
    if not asm.instances:
        return report

    adj: dict[str, list[tuple[str, str, str]]] = {n: [] for n in asm.instances}
    for mate in asm.mates:
        (ia, pa), (ib, pb) = mate.split()
        adj[ia].append((ib, pa, pb))
        adj[ib].append((ia, pb, pa))

    if base is None:
        base = max(adj, key=lambda n: (len(adj[n]), n))
    report.base = base

    placed = {base}
    queue = [base]
    while queue:
        cur = queue.pop(0)
        for other, cur_port, other_port in sorted(adj[cur]):
            anchor = asm.instances[cur].port_position(cur_port)
            inst = asm.instances[other]
            if other in placed:
                # over-constraint: verify instead of move
                have = inst.port_position(other_port)
                gap = math.dist(anchor, have)
                if gap > tol:
                    a, b = sorted([f"{cur}.{cur_port}", f"{other}.{other_port}"])
                    entry = f"{a}<->{b}:gap={gap:.6g}mm"
                    if entry not in report.conflicts:
                        report.conflicts.append(entry)
                continue
            # port position with zero translate = local (rotated) port offset
            local = tuple(p - t for p, t in
                          zip(inst.port_position(other_port), inst.translate))
            inst.translate = tuple(round(a - l, 9) for a, l in zip(anchor, local))
            placed.add(other)
            report.solved.append(other)
            queue.append(other)

    report.unreachable = sorted(set(asm.instances) - placed)
    report.solved.sort()
    report.conflicts.sort()
    return report
