"""Feature recognition — dead geometry back into parameters, with proof.

The fundamental problem of CAD interchange: STEP (and every other translation
path, commercial ones included) discards the parametric history. This module
recovers it for the shapes that dominate real mechanical work — plates with
holes — and, unlike heuristic recognizers, **proves** the reconstruction:

    residual = volume(rebuilt Δ imported)   (symmetric boolean difference)

A recognition is only offered when the residual is ~0 — the parameterized
model is then *exactly* the imported geometry, not an approximation. Anything
unrecognizable (blind holes, fillets, freeform) is reported honestly instead
of shipping a plausible-but-wrong feature tree. Recognition never modifies the
input; it returns a NEW document whose dimensions are real and editable — and
whose recovered holes can become `mech.bolt` ports (ADR-0008), so even a dead
STEP file gets a live derived interface.

v1 scope: axis-aligned rectangular base + through cylindrical holes along Z.
The pattern extends feature-by-feature (counterbores, slots, fillets) — each
addition inherits the same proof obligation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gitcad.document import Document, Feature
from gitcad.seams import Kernel

_AXIS_TOL = 1e-6      # |axis · ẑ| tolerance for "along Z"
_REL_TOL = 1e-6       # residual volume / part volume — the proof bar


@dataclass
class RecognizedHole:
    x: float
    y: float
    radius: float


@dataclass
class Recognition:
    recognized: bool
    reason: str = ""
    document: Document | None = None
    holes: list[RecognizedHole] = field(default_factory=list)
    proof: dict = field(default_factory=dict)


def recognize(doc: Document, kernel: Kernel) -> Recognition:
    """Attempt verified parameterization of ``doc``'s final shape."""
    shape = doc.build(kernel).final(doc)
    (minx, miny, minz), (maxx, maxy, maxz) = kernel.bbox(shape)
    dx, dy, dz = maxx - minx, maxy - miny, maxz - minz
    v_import = kernel.measure(shape)["volume"]

    # -- find candidate through-holes: cylindrical faces with Z axes ----------
    holes: list[RecognizedHole] = []
    unrecognized_surfaces = set()
    for face in kernel.entities(shape, "face"):
        surface = face["surface"]
        if surface == "plane":
            continue
        if surface == "cylinder":
            ax = face["axis_dir"]
            if abs(abs(ax[2]) - 1.0) < _AXIS_TOL:
                ox, oy, _ = face["axis_origin"]
                holes.append(RecognizedHole(round(ox, 6), round(oy, 6),
                                            round(face["radius"], 6)))
                continue
        unrecognized_surfaces.add(surface)

    if unrecognized_surfaces:
        return Recognition(False, reason=f"unrecognized surfaces: {sorted(unrecognized_surfaces)}")

    # Deduplicate (a hole can present as multiple cylindrical faces).
    unique: dict[tuple, RecognizedHole] = {}
    for h in holes:
        unique[(h.x, h.y, h.radius)] = h
    holes = sorted(unique.values(), key=lambda h: (h.x, h.y, h.radius))

    # -- propose the parameterized document -----------------------------------
    candidate = Document()
    base = candidate.add(Feature(op="box", params={"dx": dx, "dy": dy, "dz": dz}))
    if (minx, miny, minz) != (0.0, 0.0, 0.0):
        base = candidate.add(Feature(op="move", params={"translate": [minx, miny, minz]},
                                     inputs=[base]))
    body = base
    for h in holes:
        cyl = candidate.add(Feature(op="cylinder", params={"radius": h.radius, "height": dz}))
        moved = candidate.add(Feature(op="move", params={"translate": [h.x, h.y, minz]},
                                      inputs=[cyl]))
        body = candidate.add(Feature(op="boolean", params={"kind": "cut"},
                                     inputs=[body, moved]))

    # -- the proof: symmetric difference must vanish --------------------------
    rebuilt = candidate.build(kernel).final(candidate)
    v_rebuilt = kernel.measure(rebuilt)["volume"]
    residual = (kernel.measure(kernel.boolean("cut", rebuilt, shape))["volume"]
                + kernel.measure(kernel.boolean("cut", shape, rebuilt))["volume"])
    proof = {
        "volume_imported": round(v_import, 6),
        "volume_rebuilt": round(v_rebuilt, 6),
        "residual_volume": round(residual, 6),
        "relative_residual": round(residual / v_import, 12) if v_import else None,
    }
    if v_import <= 0 or residual / v_import > _REL_TOL:
        return Recognition(False, reason="reconstruction does not match imported geometry",
                           holes=holes, proof=proof)

    return Recognition(True, document=candidate, holes=holes, proof=proof)
