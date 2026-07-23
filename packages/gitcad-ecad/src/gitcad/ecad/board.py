"""The board model — text-first, deterministic, minimal but fab-complete.

Coordinates are mm, origin bottom-left, y up (same convention as the drawing
sheet). Rotation is degrees CCW. Sides are "top"/"bottom".

Pads live on footprints; a Component instance places a footprint at (x, y, rot,
side) — pad positions in board space are computed, never stored, so moving a
component is a one-line diff (ADR-0004: derived data is never source).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field

from gitcad.canonical import canonical_json
from gitcad.errors import GitcadError, ValidationReport


@dataclass
class Pad:
    name: str
    x: float                     # relative to footprint origin
    y: float
    w: float
    h: float
    shape: str = "rect"          # rect | circle | obround
    drill: float | None = None   # None = SMD; a value = plated through hole
    net: str = ""                # assigned per-instance via Component.nets


@dataclass
class Footprint:
    name: str
    pads: list[Pad] = field(default_factory=list)
    courtyard: tuple[float, float] | None = None   # (w, h) centered on origin
    height: float | None = None    # body height mm (IDF-style envelope; None = unknown)


@dataclass
class Component:
    ref: str                     # designator, e.g. "R1"
    footprint: Footprint
    value: str = ""
    x: float = 0.0
    y: float = 0.0
    rot: float = 0.0
    side: str = "top"
    nets: dict[str, str] = field(default_factory=dict)   # pad name -> net name

    def placed_pads(self) -> list[tuple[Pad, float, float, float]]:
        """Yield (pad, board_x, board_y, rotation) for each pad, with the
        component's placement applied. Bottom-side placement mirrors X."""
        out = []
        cos, sin = math.cos(math.radians(self.rot)), math.sin(math.radians(self.rot))
        for pad in self.footprint.pads:
            px, py = pad.x, pad.y
            if self.side == "bottom":
                px = -px
            bx = self.x + px * cos - py * sin
            by = self.y + px * sin + py * cos
            out.append((pad, bx, by, self.rot))
        return out


@dataclass
class Track:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    layer: str = "top"           # top | bottom
    net: str = ""


@dataclass
class Via:
    x: float
    y: float
    drill: float = 0.4
    diameter: float = 0.8
    net: str = ""


@dataclass
class Zone:
    """A zone: closed polygon on one layer. ``kind`` (KiCad-map P2):

    - ``copper`` (default): a pour tied to a net — the real Altair board is
      routed almost entirely with these.
    - ``keepout``: a rule area FORBIDDING copper — tracks, vias, and copper
      zones intersecting it are DRC violations; it never emits to Gerber
      and never conducts. ``net`` is meaningless for keepouts ("")."""
    net: str
    layer: str                          # top | bottom
    polygon: list[tuple[float, float]]  # closed (first != last is fine)
    kind: str = "copper"                # copper | keepout


@dataclass
class MountingHole:
    """A non-plated mounting hole — and, equally, a published mech interface:
    every mounting hole becomes a `mech.bolt` port in the board's part.json
    (ADR-0008), which is what the enclosure mates against."""
    name: str            # port name, e.g. "mnt_1"
    x: float
    y: float
    drill: float         # NPTH diameter
    thread: str | None = None   # clearance for e.g. "M3" — informational spec


@dataclass
class Board:
    """A complete board: 2 copper layers by default, up to 16 (``layers``).
    Copper layer names: ``top``, ``in1``..``in{n-2}``, ``bottom``. Vias are
    through-hole (span all layers) — blind/buried vias are a later stage,
    refused honestly rather than modeled wrong."""

    name: str
    outline: list[tuple[float, float]]   # closed polygon (first != last is fine)
    components: list[Component] = field(default_factory=list)
    tracks: list[Track] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    mounting_holes: list[MountingHole] = field(default_factory=list)
    thickness: float = 1.6               # mm — board stack height
    mask_expansion: float = 0.05         # mm per side
    layers: int = 2                      # copper layer count (2..16)
    # Net classes: named net groups binding DRC constraints (KiCad-map P1).
    # {"power": {"nets": ["VCC", "GND", "+*"], "clearance": 0.3,
    #            "track_width_min": 0.5}} — nets may be fnmatch globs; DRC
    # expands each class into net-scoped rules that OVERRIDE the pack's
    # defaults for matching nets.
    net_classes: dict[str, dict] = field(default_factory=dict)

    SCHEMA = "gitcad/board@1"

    # -- canonical text (the git-diffable source) -----------------------------

    def dumps(self) -> str:
        doc = {"schema": self.SCHEMA, "board": asdict(self)}
        return canonical_json(doc, indent=2) + "\n"

    @classmethod
    def loads(cls, text: str) -> "Board":
        doc = json.loads(text)
        if doc.get("schema") != cls.SCHEMA:
            raise GitcadError(f"unsupported board schema {doc.get('schema')!r}")
        b = doc["board"]
        return cls(
            name=b["name"],
            outline=[tuple(p) for p in b["outline"]],
            components=[
                Component(
                    ref=c["ref"],
                    footprint=Footprint(
                        name=c["footprint"]["name"],
                        pads=[Pad(**p) for p in c["footprint"]["pads"]],
                        courtyard=tuple(c["footprint"]["courtyard"]) if c["footprint"]["courtyard"] else None,
                        height=c["footprint"].get("height"),
                    ),
                    value=c["value"], x=c["x"], y=c["y"], rot=c["rot"], side=c["side"],
                    nets=dict(c["nets"]),
                )
                for c in b["components"]
            ],
            tracks=[Track(**t) for t in b["tracks"]],
            vias=[Via(**v) for v in b["vias"]],
            zones=[Zone(net=z["net"], layer=z["layer"],
                        polygon=[tuple(p) for p in z["polygon"]],
                        kind=z.get("kind", "copper"))
                   for z in b.get("zones", [])],
            mounting_holes=[MountingHole(**m) for m in b.get("mounting_holes", [])],
            thickness=b.get("thickness", 1.6),
            mask_expansion=b.get("mask_expansion", 0.05),
            layers=int(b.get("layers", 2)),
            net_classes={k: dict(v) for k, v in b.get("net_classes", {}).items()},
        )

    def copper_layers(self) -> list[str]:
        """Layer names outside-in: top, in1..in{n-2}, bottom."""
        return (["top"] + [f"in{i}" for i in range(1, self.layers - 1)]
                + ["bottom"])

    # -- checks (the agent verification loop) ---------------------------------

    def bbox(self) -> tuple[float, float, float, float]:
        xs = [x for x, _ in self.outline]
        ys = [y for _, y in self.outline]
        return (min(xs), min(ys), max(xs), max(ys))

    def validate(self) -> ValidationReport:
        """Fab-readiness checks, machine-readable. Not a full DRC yet — the
        checks that make a fab reject the files outright."""
        violations: list[str] = []
        # Filesystem-safe name: fab filenames derive from it, and the board
        # text can arrive via MCP from untrusted sources (path traversal was
        # flagged in the 2026-07-22 review).
        if not re.fullmatch(r"[A-Za-z0-9._-]+", self.name) or ".." in self.name:
            violations.append("board-name-not-filesystem-safe")
        if len(self.outline) < 3:
            violations.append("outline-degenerate")
        if not (2 <= self.layers <= 16):
            violations.append(f"layers-out-of-range:{self.layers}")
        valid_layers = set(self.copper_layers())
        minx, miny, maxx, maxy = self.bbox()
        refs = [c.ref for c in self.components]
        if len(refs) != len(set(refs)):
            violations.append("components-duplicate-refs")
        for comp in self.components:
            # v0.1 writers can only render right-angle rotations; anything else
            # would emit wrong copper silently — reject at the fab gate.
            if round(comp.rot) % 90 != 0:
                violations.append(f"rotation-not-multiple-of-90:{comp.ref}")
            for pad, bx, by, _ in comp.placed_pads():
                if not (minx <= bx <= maxx and miny <= by <= maxy):
                    violations.append(f"pad-outside-outline:{comp.ref}.{pad.name}")
                if pad.drill is not None and pad.drill >= min(pad.w, pad.h):
                    violations.append(f"drill-exceeds-pad:{comp.ref}.{pad.name}")
        for i, via in enumerate(self.vias):
            if via.drill >= via.diameter:
                violations.append(f"via-drill-exceeds-diameter:{i}")
        for i, t in enumerate(self.tracks):
            if t.width <= 0:
                violations.append(f"track-zero-width:{i}")
            if (t.x1, t.y1) == (t.x2, t.y2):
                # a zero-length track slipped through in the dogfood build
                violations.append(f"track-degenerate:{i}")
            if t.layer not in valid_layers:
                violations.append(f"track-bad-layer:{i}")
        for i, z in enumerate(self.zones):
            if len(z.polygon) < 3:
                violations.append(f"zone-degenerate:{i}")
            if z.layer not in valid_layers:
                violations.append(f"zone-bad-layer:{i}")
            if z.kind not in ("copper", "keepout"):
                violations.append(f"zone-bad-kind:{i}")
            if z.kind == "keepout" and z.net:
                violations.append(f"keepout-with-net:{i}")
        for cname, spec in sorted(self.net_classes.items()):
            nets = spec.get("nets")
            if not nets or not all(isinstance(n, str) and n for n in nets):
                violations.append(f"netclass-empty-nets:{cname}")
            for key in spec:
                if key == "nets":
                    continue
                if key not in ("clearance", "track_width_min"):
                    violations.append(f"netclass-unknown-param:{cname}:{key}")
                elif not isinstance(spec[key], (int, float)) or spec[key] <= 0:
                    violations.append(f"netclass-bad-value:{cname}:{key}")
        hole_names = [m.name for m in self.mounting_holes]
        if len(hole_names) != len(set(hole_names)):
            violations.append("mounting-holes-duplicate-names")
        for m in self.mounting_holes:
            if not (minx <= m.x <= maxx and miny <= m.y <= maxy):
                violations.append(f"mounting-hole-outside-outline:{m.name}")
            if m.drill <= 0:
                violations.append(f"mounting-hole-zero-drill:{m.name}")
        return ValidationReport(
            ok=not violations,
            checks={"components": len(self.components), "tracks": len(self.tracks),
                    "vias": len(self.vias), "zones": len(self.zones),
                    "mounting_holes": len(self.mounting_holes)},
            violations=violations,
        )

    # -- the derived part interface (ADR-0008: domain wiring) -----------------

    def to_part(self, part_id: str, version: str = "0.1.0",
                *, schematics: list[str] | None = None):
        """Derive this board's PCBA part from its actual geometry — the
        Fusion-360 duality: from the OUTSIDE this is a mechanical part
        (envelope from outline bbox × thickness, one frame + ``mech.bolt``
        port per mounting hole, a 3D body via the bridge); ENTERING it is
        the electrical workflow (the referenced board + schematics, checked
        by the pcba suite). Nothing hand-authored — change the board, and
        the interface (interface-semver, ADR-0009) follows.

        ``schematics`` lists the schematic files (ADR-0017 names) that are
        this PCBA's electrical source; pass them and the part is a full
        PCBA, omit them and it is a bare board part."""
        from gitcad.part import Frame, Interface, PartManifest, Port

        minx, miny, maxx, maxy = self.bbox()
        frames = {"origin": Frame()}
        ports = {}
        for m in self.mounting_holes:
            frames[m.name] = Frame(origin=(m.x, m.y, 0.0))
            spec: dict = {"drill": m.drill}
            if m.thread:
                spec["thread"] = m.thread
            ports[m.name] = Port(m.name, "mech.bolt", m.name, spec)
        body: dict = {"kind": "pcba", "board": f"{self.name}.board"}
        if schematics:
            body["schematics"] = sorted(schematics)
        return PartManifest(
            id=part_id, name=self.name, domain="ecad", version=version,
            interface=Interface(
                envelope={"origin": [minx, miny, 0.0],
                          "dx": maxx - minx, "dy": maxy - miny, "dz": self.thickness},
                frames=frames, ports=ports,
                properties={"layers": 2, "components": len(self.components)},
            ),
            body=body,
        )
