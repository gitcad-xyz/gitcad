"""Fastener generation — Toolbox, agent-first (SW-map P6).

Every mounting hole already publishes a ``mech.bolt`` port (ADR-0008);
this module closes the loop: a parametric socket-head bolt FAMILY
(P1 parameters + P2 configurations — one document, every length) and a
generator that walks an assembly's unmated ``mech.bolt`` ports, adds a
correctly sized bolt instance at each, and MATES it — so the standard
assembly validation (position coincidence, type compatibility) is the
proof that every screw is where a screw belongs.

Sizing: the port's ``spec["thread"]`` ("M3") picks the diameter;
``spec["length"]`` or the caller's default picks the length. Ports with
no thread spec are reported, never guessed.
"""

from __future__ import annotations

import re

from gitcad.document import Document, Feature
from gitcad.errors import GitcadError
from gitcad.part import Frame, Interface, PartManifest, Port

# ISO 4762 socket head cap screw proportions: head Ø = 1.5d, head height = d
_STD_LENGTHS = (4, 6, 8, 10, 12, 16, 20, 25, 30)


def bolt_family(d: float) -> Document:
    """A parametric socket-head cap screw as ONE document: parameters for
    every dimension, one configuration per standard length (P1 + P2 doing
    what Toolbox does with thousands of files)."""
    doc = Document()
    doc.set_parameter("d", d)
    doc.set_parameter("L", _STD_LENGTHS[2])
    doc.set_parameter("head_d", "=d*1.5")
    doc.set_parameter("head_h", "=d")
    shaft = doc.add(Feature(op="cylinder",
                            params={"radius": "=d/2", "height": "=L"}))
    head = doc.add(Feature(op="cylinder",
                           params={"radius": "=head_d/2", "height": "=head_h"}))
    head_up = doc.add(Feature(op="move", params={"translate": [0, 0, "=L"]},
                              inputs=[head]))
    doc.add(Feature(op="boolean", params={"kind": "union"},
                    inputs=[shaft, head_up]))
    for length in _STD_LENGTHS:
        doc.set_configuration(f"M{d:g}x{length}", {"L": length})
    return doc


def bolt_part(thread: str, length: float) -> PartManifest:
    """The bolt as a part: envelope from its dimensions, one ``mech.bolt``
    port at the head seat (origin, -z shaft) — the thing that mates into a
    mounting hole's port."""
    d = _thread_diameter(thread)
    head_d, head_h = 1.5 * d, d
    iface = Interface(
        envelope={"origin": [-head_d / 2, -head_d / 2, 0],
                  "dx": head_d, "dy": head_d, "dz": length + head_h},
        frames={"seat": Frame()},
        ports={"seat": Port(name="seat", type="mech.bolt", frame="seat",
                            spec={"thread": thread, "length": length})},
        properties={"standard": "ISO4762", "thread": thread, "length": length},
    )
    safe = f"{thread}x{length:g}".replace(".", "_")
    return PartManifest(id=f"prt_bolt_{safe.lower()}", name=f"{thread}x{length:g} SHCS",
                        domain="mech", version="1.0.0", interface=iface,
                        body={"kind": "fastener", "standard": "ISO4762"})


def generate_fasteners(assembly, *, default_length: float = 8.0) -> dict:
    """Populate every unmated ``mech.bolt`` port with a sized bolt instance
    + mate. Returns {"added": [...], "skipped": [...]} — skipped ports name
    their reason (already mated / no thread spec), never silently."""
    mated: set[tuple[str, str]] = set()
    for m in assembly.mates:
        (ia, pa), (ib, pb) = m.split()
        mated.add((ia, pa))
        mated.add((ib, pb))

    added: list[dict] = []
    skipped: list[dict] = []
    for iname, inst in sorted(assembly.instances.items()):
        if inst.part.body.get("kind") == "fastener":
            continue
        for pname, port in sorted(inst.part.interface.ports.items()):
            if port.type != "mech.bolt":
                continue
            if (iname, pname) in mated:
                skipped.append({"port": f"{iname}.{pname}", "reason": "already-mated"})
                continue
            thread = (port.spec or {}).get("thread")
            if not thread:
                skipped.append({"port": f"{iname}.{pname}", "reason": "no-thread-spec"})
                continue
            length = float((port.spec or {}).get("length", default_length))
            part = bolt_part(thread, length)
            bolt_name = f"bolt_{iname}_{pname}"
            pos = inst.port_position(pname)
            assembly.add(bolt_name, part, translate=pos)
            assembly.mate(f"{bolt_name}.seat", f"{iname}.{pname}")
            added.append({"instance": bolt_name, "port": f"{iname}.{pname}",
                          "thread": thread, "length": length,
                          "position": list(pos)})
    return {"added": added, "skipped": skipped}


def _thread_diameter(thread: str) -> float:
    m = re.fullmatch(r"[Mm](\d+(?:\.\d+)?)", thread.strip())
    if not m:
        raise GitcadError(
            f"unsupported thread spec {thread!r} (want metric 'M<d>', e.g. 'M3')")
    return float(m.group(1))
