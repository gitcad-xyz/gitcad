"""The viewer server — Python stdlib only, one file in, live page out.

Serves ``PAGE`` (the self-contained WebGL2 client in :mod:`.page`) plus a
tiny JSON API. The page polls ``/api/version`` (content hash of the watched
file) and refetches on change — edit the model text, the view updates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from gitcad.document import Document
from gitcad.ecad.board import Board
from gitcad.kernel import get_kernel
from gitcad.seams import Kernel
from gitcad.viewer.boardsvg import board_to_svg
from gitcad.viewer.page import PAGE


def detect_kind(text: str) -> str:
    schema = json.loads(text).get("schema", "")
    if schema.startswith("gitcad/board"):
        return "board"
    if schema.startswith("gitcad/document"):
        return "model"
    raise ValueError(f"cannot view schema {schema!r}")


def mesh_payload(doc: Document, kernel: Kernel) -> dict:
    """Everything the 3D client needs, JSON-able."""
    result = doc.build(kernel)
    shape = result.final(doc)
    mesh = kernel.tessellate(shape)
    lo, hi = kernel.bbox(shape)
    measures = kernel.measure(shape)
    return {
        "kind": "model",
        "positions": mesh["positions"],
        "indices": mesh["indices"],
        "bbox": [list(lo), list(hi)],
        "stats": {
            "vertices": len(mesh["positions"]) // 3,
            "triangles": len(mesh["indices"]) // 3,
            "volume_mm3": round(measures.get("volume", 0.0), 2),
            "kernel": kernel.name,
            "features": len(doc),
        },
    }


class _Handler(BaseHTTPRequestHandler):
    # Set by serve(): watched file path + kernel.
    path_watched: Path
    kernel: Kernel

    def log_message(self, *args) -> None:  # quiet
        pass

    def _send(self, status: int, content: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        try:
            text = self.path_watched.read_text(encoding="utf-8")
            if self.path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/version":
                digest = hashlib.sha256(text.encode()).hexdigest()
                kind = detect_kind(text)
                self._send(200, json.dumps({"version": digest, "kind": kind,
                                            "name": self.path_watched.name}).encode(),
                           "application/json")
            elif self.path == "/api/mesh":
                doc = Document.loads(text)
                payload = mesh_payload(doc, self.kernel)
                self._send(200, json.dumps(payload).encode(), "application/json")
            elif self.path == "/api/board.svg":
                board = Board.loads(text)
                self._send(200, board_to_svg(board).encode(), "image/svg+xml")
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as exc:  # surface errors to the page, never crash
            self._send(500, json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode(),
                       "application/json")


def serve(path: str, port: int = 8137, kernel: Kernel | None = None) -> ThreadingHTTPServer:
    """Start (and return) the server; caller decides whether to block."""
    handler = type("Handler", (_Handler,), {
        "path_watched": Path(path),
        "kernel": kernel or get_kernel(),
    })
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main() -> None:  # pragma: no cover - CLI entrypoint
    ap = argparse.ArgumentParser(description="gitcad viewer — live local window on a model or board")
    ap.add_argument("file", help="a .gitcad.json model or board document")
    ap.add_argument("--port", type=int, default=8137)
    args = ap.parse_args()
    httpd = serve(args.file, args.port)
    print(f"gitcad viewer: http://127.0.0.1:{args.port}/  (watching {args.file}, Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
