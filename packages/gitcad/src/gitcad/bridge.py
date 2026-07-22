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


def board_to_model(board: Board) -> Document:
    """The board as a 3D body: extruded outline with mounting holes cut."""
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
    return doc
