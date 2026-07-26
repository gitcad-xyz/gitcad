"""Cross-domain bridges (metapackage — the one place mech and ecad meet).

:func:`board_to_model` — the dogfood's #2 friction finding: interference
checking needed the board as real 3D geometry, previously hand-extruded.
Now: outline (polygon, any shape) x thickness, mounting holes cut through —
a mech Document derived from the ecad source, ready for assemblies,
interference, STEP export, or the viewer.
"""

from __future__ import annotations

from gitcad.document import Document, Feature
from gitcad.ecad.board import Board
from gitcad.sketch import Profile


def component_envelope(comp, *, default_height: float = 2.0
                       ) -> tuple[float, float, float] | None:
    """(w, h, height) of a component's IDF-style envelope, rotation applied:
    courtyard when declared, pads' extent + margin otherwise, None when the
    footprint has neither."""
    cy = comp.footprint.courtyard
    if cy is not None:
        cw, ch = cy
    else:
        pads = comp.footprint.pads
        if not pads:
            return None
        cw = max(abs(p.x) + p.w / 2 for p in pads) * 2 + 0.4
        ch = max(abs(p.y) + p.h / 2 for p in pads) * 2 + 0.4
    if round(comp.rot) % 180 == 90:
        cw, ch = ch, cw
    return (cw, ch, comp.footprint.height or default_height)


def board_to_model(board: Board, *, components: bool = True,
                   default_height: float = 2.0) -> Document:
    """The board as a 3D body: extruded outline with mounting holes cut,
    plus IDF-style component envelopes — each part's courtyard extruded to
    its footprint height (``default_height`` when unknown). That makes the
    populated board a REAL mechanical envelope: enclosure interference
    checks see the tall electrolytic, not a bare slab."""
    pts = list(board.outline)
    prof = Profile(tuple(pts[0]))
    for x, y in pts[1:]:
        prof.line_to(x, y)
    prof.close()

    doc = Document()
    fid = doc.add(Feature(op="extrude", params={"profile": prof.to_params(),
                                                "height": board.thickness}))
    for mh in board.mounting_holes:
        fid = doc.add(Feature(op="hole", params={
            "x": mh.x, "y": mh.y, "top_z": board.thickness,
            "diameter": mh.drill, "depth": board.thickness}, inputs=[fid]))
    if components:
        for comp in board.components:
            env = component_envelope(comp, default_height=default_height)
            if env is None:
                continue
            cw, ch, h = env
            # top: sits on the board surface; bottom: hangs below z=0
            base = board.thickness if comp.side == "top" else -h
            body = Profile((comp.x - cw / 2, comp.y - ch / 2)) \
                .line_to(comp.x + cw / 2, comp.y - ch / 2) \
                .line_to(comp.x + cw / 2, comp.y + ch / 2) \
                .line_to(comp.x - cw / 2, comp.y + ch / 2).close()
            fid = doc.add(Feature(op="extrude", params={
                "profile": body.to_params(), "height": h,
                "plane": {"offset": base},
                "mode": "add"}, inputs=[fid]))
    return doc
