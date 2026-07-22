"""Atomic ECAD components — footprints as registry parts (ADR-0010).

The dogfood used inline footprint objects nobody else could reuse. This
module closes the loop: a :class:`Footprint` becomes a versioned
``ecad.component`` part (publishable to the registry, interface-semver
enforced — a moved pad can never ship as a patch), and any design can pull
it back with :func:`footprint_from_part`.

The interface (what consumers may depend on): every pad is an ``elec.pin``
port at its frame position, the envelope is the courtyard footprint area.
Pads/positions ARE the interface — silkscreen-class changes are PATCH, a
moved or removed pad is MAJOR, mechanically (ADR-0009).
"""

from __future__ import annotations

from dataclasses import asdict

from gitcad.ecad.board import Footprint, Pad
from gitcad.errors import GitcadError
from gitcad.part import Frame, Interface, PartManifest, Port


def footprint_to_part(fp: Footprint, part_id: str, version: str = "0.1.0",
                      *, height: float = 1.0, properties: dict | None = None) -> PartManifest:
    """Publishable atomic component from a footprint definition."""
    frames = {"origin": Frame()}
    ports = {}
    for pad in fp.pads:
        name = f"pad_{pad.name}" if pad.name else "pad"
        if name in ports:
            raise GitcadError(f"duplicate pad name {pad.name!r} in {fp.name!r}")
        frames[name] = Frame(origin=(pad.x, pad.y, 0.0))
        spec: dict = {"w": pad.w, "h": pad.h, "shape": pad.shape}
        if pad.drill is not None:
            spec["drill"] = pad.drill
        ports[name] = Port(name, "elec.pin", name, spec)

    if fp.courtyard:
        cw, ch = fp.courtyard
    else:  # derive a courtyard from pad extents + margin
        xs = [p.x for p in fp.pads]
        ys = [p.y for p in fp.pads]
        cw = (max(xs) - min(xs)) + max(p.w for p in fp.pads) + 0.5
        ch = (max(ys) - min(ys)) + max(p.h for p in fp.pads) + 0.5

    return PartManifest(
        id=part_id, name=fp.name, domain="ecad.component", version=version,
        interface=Interface(
            envelope={"origin": [-cw / 2, -ch / 2, 0.0], "dx": cw, "dy": ch, "dz": height},
            frames=frames, ports=ports,
            properties={"pads": len(fp.pads), **(properties or {})},
        ),
        body={"kind": "footprint", "footprint": asdict(fp)},
    )


def footprint_from_part(manifest: PartManifest) -> Footprint:
    """Reconstruct a placeable footprint from a registry component."""
    if manifest.domain != "ecad.component":
        raise GitcadError(f"{manifest.name!r} is domain {manifest.domain!r}, "
                          "not an ecad.component")
    body = manifest.body
    if body.get("kind") != "footprint":
        raise GitcadError(f"{manifest.name!r} has no footprint body")
    fp = body["footprint"]
    return Footprint(
        name=fp["name"],
        pads=[Pad(**p) for p in fp["pads"]],
        courtyard=tuple(fp["courtyard"]) if fp.get("courtyard") else None,
    )
