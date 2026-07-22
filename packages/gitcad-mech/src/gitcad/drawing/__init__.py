"""The drawing engine — 3D models to dimensioned 2D manufacturing drawings.

Projection is delegated to OCCT's hidden-line-removal engine (:mod:`.hlr`);
this package owns the 2D document model on top: sheet layout, views, overall
dimensions, title block, and SVG/PDF output (ADR-0002, DrawingEngine seam).

v0.1 scope: third-angle front/top/right + isometric views, auto-scaled onto a
standard sheet, with overall width/height dimensions per orthographic view.
Associative feature-level dimensions (anchored to stable entity ids) follow.
"""

from gitcad.drawing.sheet import make_drawing

__all__ = ["make_drawing"]
