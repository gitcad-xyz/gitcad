"""The web viewer — ONE local, dependency-free window per PROJECT.

``gitcad-view`` (a project directory, or any design file in one) serves a
single-page viewer at localhost: the default view is the project's TOP
assembly, and every other part is a sub-interface in the same page (the parts
menu / ``#part=<file>`` deep links) — never a second server. 3D models render
in a ~200-line WebGL2 client (no three.js, no CDN — the page is
self-contained, matching the project's zero-dependency ethos); boards render
as server-generated SVG. The page polls for file changes and reloads live,
which makes it simultaneously:

- the human's window while an agent works, and
- the agent's eyes (drive the file, screenshot the viewer).

Lifecycle: through MCP (``viewer_open``) the server is a DETACHED process
(:mod:`gitcad.viewer.daemon`) that outlives the agent session, is discovered
via ``.gitcad/viewer.json``, and stops only on the explicit ``viewer_stop`` /
``gitcad-view --stop``.

Server: Python stdlib only. The Renderer seam gets a real backend the day we
need offscreen PNGs; the tessellation source is already kernel-side.
"""

from gitcad.viewer.boardsvg import board_to_svg
from gitcad.viewer.server import main, mesh_payload

__all__ = ["board_to_svg", "mesh_payload", "main"]
