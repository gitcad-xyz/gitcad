"""Assemblies — parts whose body is composition (ADR-0008).

An assembly places **instances** of parts by explicit rigid transform and
declares **mates** between ports. v1 has deliberately no constraint solver:
mates are *checks* — port-type compatibility and positional coincidence after
transforms — so assembly validation is interface checking, cheap and exact.

The assembly is itself a Part: :meth:`Assembly.to_manifest` derives its own
manifest (envelope = union of instance envelopes), which is what makes
assemblies nest with no special cases.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gitcad.errors import GitcadError, ValidationReport
from gitcad.part.interface import Interface
from gitcad.part.manifest import PartManifest

# Port types that may mate with each other (symmetric; extended by domains).
COMPATIBLE_TYPES: set[frozenset[str]] = {
    frozenset({"mech.bolt", "mech.boss"}),
    frozenset({"mech.bolt", "mech.bolt"}),
    frozenset({"elec.connector", "elec.connector"}),
    frozenset({"elec.pin", "elec.pin"}),
}

_TOL = 0.01  # mm — positional coincidence tolerance for mates


@dataclass
class Instance:
    name: str
    part: PartManifest
    translate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotate_z_deg: float = 0.0    # v1: rotation about global Z only

    def port_position(self, port_name: str) -> tuple[float, float, float]:
        iface = self.part.interface
        if port_name not in iface.ports:
            raise GitcadError(f"instance {self.name!r}: no port {port_name!r}")
        frame = iface.frames[iface.ports[port_name].frame]
        x, y, z = frame.origin
        rad = math.radians(self.rotate_z_deg)
        rx = x * math.cos(rad) - y * math.sin(rad)
        ry = x * math.sin(rad) + y * math.cos(rad)
        tx, ty, tz = self.translate
        return (rx + tx, ry + ty, z + tz)

    def envelope_bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        env = self.part.interface.envelope
        if env is None:
            return None
        ox, oy, oz = env.get("origin", (0.0, 0.0, 0.0))
        dx, dy, dz = env["dx"], env["dy"], env["dz"]
        corners = [(ox + a, oy + b) for a in (0, dx) for b in (0, dy)]
        rad = math.radians(self.rotate_z_deg)
        rot = [(x * math.cos(rad) - y * math.sin(rad), x * math.sin(rad) + y * math.cos(rad))
               for x, y in corners]
        tx, ty, tz = self.translate
        xs = [x + tx for x, _ in rot]
        ys = [y + ty for _, y in rot]
        return ((min(xs), min(ys), oz + tz), (max(xs), max(ys), oz + dz + tz))


@dataclass
class Mate:
    """A declared connection: instance_a.port_a mates instance_b.port_b."""
    a: str          # "instance.port"
    b: str

    def split(self) -> tuple[tuple[str, str], tuple[str, str]]:
        def parse(ref: str) -> tuple[str, str]:
            if "." not in ref:
                raise GitcadError(f"mate ref {ref!r} must be 'instance.port'")
            inst, port = ref.split(".", 1)
            return inst, port
        return parse(self.a), parse(self.b)


@dataclass
class Assembly:
    name: str
    instances: dict[str, Instance] = field(default_factory=dict)
    mates: list[Mate] = field(default_factory=list)

    def add(self, name: str, part: PartManifest, *, translate=(0.0, 0.0, 0.0),
            rotate_z_deg: float = 0.0) -> Instance:
        if name in self.instances:
            raise GitcadError(f"duplicate instance name {name!r}")
        inst = Instance(name, part, tuple(translate), rotate_z_deg)
        self.instances[name] = inst
        return inst

    def mate(self, a: str, b: str) -> None:
        self.mates.append(Mate(a, b))

    # -- component patterns (SW "linear/circular component pattern") -----------

    def pattern_linear(self, seed: str, *, direction, spacing: float,
                       count: int) -> list[Instance]:
        """Replicate an existing instance ``count`` times along ``direction``
        at ``spacing`` apart (count includes the seed). The seed keeps its
        place; copies are named ``{seed}#1``, ``{seed}#2``, …. Returns the
        newly created instances (excluding the seed)."""
        if seed not in self.instances:
            raise GitcadError(f"pattern_linear: no seed instance {seed!r}")
        if count < 1:
            raise GitcadError("pattern_linear: count must be >= 1")
        base = self.instances[seed]
        dx, dy, dz = (float(direction[0]), float(direction[1]),
                      float(direction[2]) if len(direction) > 2 else 0.0)
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < _TOL:
            raise GitcadError("pattern_linear: zero-length direction")
        ux, uy, uz = dx / length, dy / length, dz / length
        made: list[Instance] = []
        tx, ty, tz = base.translate
        for k in range(1, count):
            step = k * spacing
            name = f"{seed}#{k}"
            if name in self.instances:
                raise GitcadError(f"pattern_linear: duplicate copy name {name!r}")
            inst = Instance(name, base.part,
                            (tx + ux * step, ty + uy * step, tz + uz * step),
                            base.rotate_z_deg)
            self.instances[name] = inst
            made.append(inst)
        return made

    def pattern_circular(self, seed: str, *, center=(0.0, 0.0),
                         count: int, total_angle_deg: float = 360.0) -> list[Instance]:
        """Replicate an instance ``count`` times about the global Z axis
        through ``center`` (an XY point). Copies span ``total_angle_deg`` —
        a full 360° drops the redundant final copy (it would coincide with
        the seed); a partial arc keeps both ends. Each copy is the seed
        rigidly rotated about ``center`` (translate revolves, ``rotate_z_deg``
        advances), which is exact within the rotate-about-Z placement model."""
        if seed not in self.instances:
            raise GitcadError(f"pattern_circular: no seed instance {seed!r}")
        if count < 1:
            raise GitcadError("pattern_circular: count must be >= 1")
        base = self.instances[seed]
        cx, cy = float(center[0]), float(center[1])
        # a closed 360° ring divides the full turn into ``count`` gaps; an
        # open arc puts the last copy AT total_angle (count-1 gaps).
        full = abs((total_angle_deg % 360.0)) < 1e-9 and total_angle_deg != 0.0
        gaps = count if full else max(count - 1, 1)
        step_deg = total_angle_deg / gaps
        tx, ty, tz = base.translate
        rx, ry = tx - cx, ty - cy
        made: list[Instance] = []
        for k in range(1, count):
            ang = math.radians(step_deg * k)
            ca, sa = math.cos(ang), math.sin(ang)
            nx = cx + rx * ca - ry * sa
            ny = cy + rx * sa + ry * ca
            name = f"{seed}#{k}"
            if name in self.instances:
                raise GitcadError(f"pattern_circular: duplicate copy name {name!r}")
            inst = Instance(name, base.part, (nx, ny, tz),
                            base.rotate_z_deg + step_deg * k)
            self.instances[name] = inst
            made.append(inst)
        return made

    # -- validation: interface checking (the whole point) ---------------------

    def validate(self) -> ValidationReport:
        violations: list[str] = []
        for m in self.mates:
            (ia, pa), (ib, pb) = m.split()
            # Per-mate validity — earlier mates' failures must never swallow
            # this mate's checks (reviewed 2026-07-22).
            missing = [i for i in (ia, ib) if i not in self.instances]
            if missing:
                violations.extend(f"mate-unknown-instance:{i}" for i in missing)
                continue
            inst_a, inst_b = self.instances[ia], self.instances[ib]
            try:
                port_a = inst_a.part.interface.ports[pa]
                port_b = inst_b.part.interface.ports[pb]
            except KeyError as exc:
                violations.append(f"mate-unknown-port:{exc.args[0]}")
                continue
            if frozenset({port_a.type, port_b.type}) not in COMPATIBLE_TYPES:
                violations.append(f"mate-incompatible-types:{m.a}({port_a.type})<->{m.b}({port_b.type})")
            pos_a, pos_b = inst_a.port_position(pa), inst_b.port_position(pb)
            dist = math.dist(pos_a, pos_b)   # full 3D coincidence
            if dist > _TOL:
                violations.append(f"mate-position-mismatch:{m.a}<->{m.b}:d={dist:.3f}mm")
        # checks states METHOD and coverage so ok=True can never overstate what
        # was verified (frame orientation is not yet checked, only position).
        return ValidationReport(
            ok=not violations,
            checks={"instances": len(self.instances), "mates": len(self.mates),
                    "coincidence": "xyz-position", "orientation_checked": False},
            violations=violations,
        )

    # -- an assembly is a part ------------------------------------------------

    def to_manifest(self, part_id: str, version: str = "0.1.0") -> PartManifest:
        """Derive this assembly's own part manifest: union envelope, body =
        composition, deps = constraints on every instanced part."""
        bounds = [b for inst in self.instances.values() if (b := inst.envelope_bounds())]
        envelope = None
        if bounds:
            los, his = [b[0] for b in bounds], [b[1] for b in bounds]
            lo = tuple(min(p[i] for p in los) for i in range(3))
            hi = tuple(max(p[i] for p in his) for i in range(3))
            envelope = {"origin": list(lo), "dx": hi[0] - lo[0],
                        "dy": hi[1] - lo[1], "dz": hi[2] - lo[2]}
        body = {
            "kind": "assembly",
            "instances": {
                n: {"part": i.part.id, "translate": list(i.translate),
                    "rotate_z_deg": i.rotate_z_deg}
                for n, i in sorted(self.instances.items())
            },
            "mates": [{"a": m.a, "b": m.b} for m in self.mates],
        }
        deps = {i.part.id: f"^{i.part.version}" for i in self.instances.values()}
        return PartManifest(
            id=part_id, name=self.name, domain="assembly", version=version,
            interface=Interface(envelope=envelope), deps=deps, body=body,
        )
