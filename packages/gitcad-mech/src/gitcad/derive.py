"""Deriving part interfaces from real domain data (ADR-0008 domain wiring).

The board side lives on :meth:`gitcad.ecad.board.Board.to_part`. This module
covers the mechanical side: build a Document against a kernel and derive the
envelope from actual geometry. Ports/frames remain *declared* for mech in v1 —
a solid doesn't announce which faces are mounting bosses; that semantic tag is
design intent (a follow-up will attach ports to stable entity ids so they
re-derive positions from geometry too).
"""

from __future__ import annotations

from gitcad.document import Document
from gitcad.part.interface import Frame, Interface, Port
from gitcad.part.manifest import PartManifest
from gitcad.seams import Kernel


def model_to_part(
    doc: Document,
    kernel: Kernel,
    *,
    part_id: str,
    name: str,
    version: str = "0.1.0",
    frames: dict[str, Frame] | None = None,
    ports: dict[str, Port] | None = None,
    properties: dict | None = None,
) -> PartManifest:
    """Build ``doc`` and derive its ``part.json``: envelope from the built
    geometry's bounding box; declared frames/ports carried through."""
    if not len(doc):
        raise ValueError("document has no features")
    final = doc.build(kernel).final(doc)
    (minx, miny, minz), (maxx, maxy, maxz) = kernel.bbox(final)
    # Round to fixed precision: a derived envelope feeds interface-semver
    # (ADR-0009), so float noise between rebuilds must never register as an
    # interface change. 1e-6 mm is far below manufacturing relevance.
    minx, miny, minz, maxx, maxy, maxz = (round(v, 6) for v in
                                          (minx, miny, minz, maxx, maxy, maxz))

    iface_frames = {"origin": Frame()}
    iface_frames.update(frames or {})
    props = {"kernel": kernel.name}
    props.update(properties or {})
    measures = kernel.measure(final)
    if "volume" in measures:
        props["volume_mm3"] = round(measures["volume"], 3)

    return PartManifest(
        id=part_id, name=name, domain="mech", version=version,
        interface=Interface(
            envelope={"origin": [minx, miny, minz],
                      "dx": maxx - minx, "dy": maxy - miny, "dz": maxz - minz},
            frames=iface_frames,
            ports=dict(ports or {}),
            properties=props,
        ),
        body={"model": f"{name}.gitcad.json"},
    )
