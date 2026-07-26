"""Exploded views — a display projection, never a model edit (ADR-0014).

The spec is per-instance offset vectors in canonical text. Applying it
produces a *new* assembly with shifted transforms for renderers to consume;
the source assembly text never changes. ``auto_explode`` derives default
offsets deterministically from the mate graph: each instance moves along its
mated port frame's z axis, scaled by its BFS depth from the base instance
(the most-mated one, ties by name) — no solver, pure derivation.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError
from gitcad.part.assembly import Assembly


@dataclass
class ExplodedView:
    assembly: str
    offsets: dict[str, tuple[float, float, float]] = field(default_factory=dict)

    SCHEMA = "gitcad/exploded-view@1"

    def dumps(self) -> str:
        doc = {"schema": self.SCHEMA, "exploded": {
            "assembly": self.assembly,
            "offsets": {k: list(v) for k, v in sorted(self.offsets.items())}}}
        return canonical_json(doc, indent=2) + "\n"

    @classmethod
    def loads(cls, text: str) -> "ExplodedView":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported exploded-view schema {doc.get('schema')!r}")
        e = doc["exploded"]
        return cls(assembly=e["assembly"],
                   offsets={k: tuple(v) for k, v in e.get("offsets", {}).items()})

    def apply(self, asm: Assembly) -> Assembly:
        """A new assembly with offsets added to instance transforms. Unknown
        instance names in the spec are an error — a stale view must fail loud,
        not silently explode the wrong parts."""
        unknown = set(self.offsets) - set(asm.instances)
        if unknown:
            raise GitcadError(f"exploded view names unknown instances: {sorted(unknown)}")
        out = Assembly(f"{asm.name}-exploded")
        for name, inst in asm.instances.items():
            off = self.offsets.get(name, (0.0, 0.0, 0.0))
            out.add(name, inst.part,
                    translate=(inst.translate[0] + off[0],
                               inst.translate[1] + off[1],
                               inst.translate[2] + off[2]),
                    rotate_z_deg=inst.rotate_z_deg)
        out.mates = list(asm.mates)   # carried for reference, not re-checked
        return out


def auto_explode(asm: Assembly, spacing: float = 30.0) -> ExplodedView:
    """Deterministic default explode derived from the mate graph."""
    # Adjacency + per-instance mated-port direction.
    adj: dict[str, set[str]] = {n: set() for n in asm.instances}
    port_dir: dict[str, tuple[float, float, float]] = {}
    for mate in asm.mates:
        (ia, pa), (ib, pb) = mate.split()
        adj[ia].add(ib)
        adj[ib].add(ia)
        for iname, pname in ((ia, pa), (ib, pb)):
            if iname in port_dir:
                continue
            iface = asm.instances[iname].part.interface
            port = iface.ports.get(pname)
            if port is not None:
                port_dir[iname] = tuple(iface.frames[port.frame].z_axis)

    if not asm.instances:
        return ExplodedView(assembly=asm.name)
    base = max(adj, key=lambda n: (len(adj[n]), n))

    # BFS depth from base; unmated instances stack above the deepest level.
    depth = {base: 0}
    queue = [base]
    while queue:
        cur = queue.pop(0)
        for nxt in sorted(adj[cur]):
            if nxt not in depth:
                depth[nxt] = depth[cur] + 1
                queue.append(nxt)
    deepest = max(depth.values(), default=0)
    for i, name in enumerate(sorted(set(asm.instances) - set(depth))):
        depth[name] = deepest + 1 + i

    offsets: dict[str, tuple[float, float, float]] = {}
    for name, d in depth.items():
        if d == 0:
            continue
        dx, dy, dz = port_dir.get(name, (0.0, 0.0, 1.0))
        norm = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        offsets[name] = (round(dx / norm * spacing * d, 9),
                         round(dy / norm * spacing * d, 9),
                         round(dz / norm * spacing * d, 9))
    return ExplodedView(assembly=asm.name, offsets=offsets)
