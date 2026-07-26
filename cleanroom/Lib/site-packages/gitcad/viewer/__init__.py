"""The web viewer — a local, dependency-free window into models and boards.

``gitcad-view model.gitcad.json`` serves a single-page viewer at localhost:
3D models render in a ~200-line WebGL2 client (no three.js, no CDN — the
page is self-contained, matching the project's zero-dependency ethos); boards
render as server-generated SVG. The page polls for file changes and reloads
live, which makes it simultaneously:

- the human's window while an agent works, and
- the agent's eyes (drive the file, screenshot the viewer).

Server: Python stdlib only. The Renderer seam gets a real backend the day we
need offscreen PNGs; the tessellation source is already kernel-side.
"""

from gitcad.viewer.boardsvg import board_to_svg
from gitcad.viewer.server import main, mesh_payload

__all__ = ["board_to_svg", "mesh_payload", "main"]
