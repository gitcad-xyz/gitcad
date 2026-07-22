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
    doc = json.loads(text)
    schema = doc.get("schema", "")
    if schema.startswith("gitcad/board"):
        return "board"
    if schema.startswith("gitcad/schematic"):
        return "schematic"
    if schema.startswith("gitcad/document"):
        return "model"
    if schema.startswith("gitcad/part"):
        if doc.get("domain") == "assembly":
            return "assembly"
        if (doc.get("body") or {}).get("kind") == "pcba":
            return "pcba"   # the Fusion duality: enter the electrical workflow
        raise ValueError("view a part's MODEL file, not its manifest "
                         "(only assembly and pcba manifests are viewable directly)")
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


# Distinct-instance palette (dark-theme friendly), cycled.
_PALETTE = [(0.35, 0.62, 0.85), (0.85, 0.55, 0.35), (0.45, 0.78, 0.55),
            (0.78, 0.45, 0.72), (0.80, 0.75, 0.40), (0.45, 0.72, 0.78),
            (0.65, 0.50, 0.85), (0.60, 0.60, 0.60)]


def assembly_mesh_payload(manifest_path: Path, kernel: Kernel) -> dict:
    """Merge every instance's built, placed geometry into one colored mesh.

    Instances resolve part id -> sibling part.json (scanned from the assembly
    file's directory tree) -> its body["model"] document, built and placed per
    the instance transform.
    """
    from gitcad.part import PartManifest

    manifest = PartManifest.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent

    by_id: dict[str, tuple[PartManifest, Path]] = {}
    for pj in sorted(list(root.rglob("*part.json")) + list(root.rglob("*.part"))
                     + list(root.rglob("*.pcba"))):
        if pj == manifest_path:
            continue
        try:
            m = PartManifest.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        by_id.setdefault(m.id, (m, pj))

    positions: list[float] = []
    colors: list[float] = []
    indices: list[int] = []
    groups: list[dict] = []
    los, his = [], []

    for n, (name, inst) in enumerate(sorted(manifest.body.get("instances", {}).items())):
        entry = by_id.get(inst["part"])
        if entry is None:
            raise ValueError(f"instance {name!r}: part {inst['part']!r} not found "
                             f"next to the assembly (need its part.json + model)")
        part, pj_path = entry
        model_name = part.body.get("model")
        board_name = part.body.get("board")
        if model_name:
            model_file = pj_path.parent / model_name
            if not model_file.is_file():
                raise ValueError(f"instance {name!r}: model file {model_file.name!r} "
                                 f"missing next to {pj_path.name}")
            doc = Document.loads(model_file.read_text(encoding="utf-8"))
        elif board_name:
            # board-backed part: extrude the board through the bridge
            from gitcad.bridge import board_to_model
            from gitcad.ecad.board import Board

            board_file = pj_path.parent / board_name
            if not board_file.is_file():
                raise ValueError(f"instance {name!r}: board file {board_file.name!r} "
                                 f"missing next to {pj_path.name}")
            doc = board_to_model(Board.loads(board_file.read_text(encoding="utf-8")))
        else:
            raise ValueError(f"instance {name!r}: part {part.name!r} has neither "
                             f"body.model nor body.board — nothing to render")
        shape = kernel.transform(
            doc.build(kernel).final(doc),
            translate=tuple(inst.get("translate", (0, 0, 0))),
            rotate_axis=(0, 0, 1), rotate_deg=inst.get("rotate_z_deg", 0.0))
        mesh = kernel.tessellate(shape)
        lo, hi = kernel.bbox(shape)
        los.append(lo)
        his.append(hi)
        base = len(positions) // 3
        color = _PALETTE[n % len(_PALETTE)]
        positions.extend(mesh["positions"])
        colors.extend(color * (len(mesh["positions"]) // 3))
        indices.extend(base + i for i in mesh["indices"])
        groups.append({"name": name, "part": part.name, "triangles": len(mesh["indices"]) // 3,
                       "color": list(color)})

    lo = [min(p[i] for p in los) for i in range(3)] if los else [0, 0, 0]
    hi = [max(p[i] for p in his) for i in range(3)] if his else [0, 0, 0]
    return {
        "kind": "assembly",
        "positions": positions, "colors": colors, "indices": indices,
        "bbox": [lo, hi], "groups": groups,
        "stats": {"vertices": len(positions) // 3, "triangles": len(indices) // 3,
                  "instances": len(groups), "kernel": kernel.name,
                  "volume_mm3": 0, "features": len(groups)},
    }


def discover_schematics(root: Path, limit: int = 12) -> list[dict]:
    """The schematics that make up a design, rendered for review.

    Scans the design's directory tree for schematic sources: ``*.kicad_sch``
    (rendered exactly as drawn via the importer + fidelity renderer) and
    ``*.schematic.json`` (canonical gitcad schematics, auto-layout). This is
    the electrical view under a 3D assembly — same sibling-scan rule the
    assembly mesh resolver uses."""
    out: list[dict] = []
    sources = (sorted(root.rglob("*.kicad_sch"))
               + sorted(root.rglob("*.schematic.json"))
               + sorted(root.rglob("*.sch.json"))
               + sorted(p for p in root.rglob("*.sch")
                        if not p.name.endswith(".kicad_sch")))
    for src in sources[:limit]:
        try:
            if src.suffix == ".kicad_sch":
                from gitcad.ecad.schsvg import sheet_to_svg
                from gitcad.importers.kicad_sch import import_kicad_sch

                sch, _report = import_kicad_sch(str(src))
                svg = sheet_to_svg(sch)
            else:
                from gitcad.ecad import Schematic, schematic_to_svg

                sch = Schematic.loads(src.read_text(encoding="utf-8"))
                svg = schematic_to_svg(sch)
            out.append({"name": sch.name, "file": src.name, "svg": svg})
        except Exception as exc:   # a broken sheet must not sink the review
            out.append({"name": src.stem, "file": src.name,
                        "error": f"{type(exc).__name__}: {exc}"})
    return out


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
                kind = detect_kind(text)
                if kind == "assembly":
                    payload = assembly_mesh_payload(self.path_watched, self.kernel)
                elif kind == "pcba":
                    from gitcad.bridge import board_to_model
                    from gitcad.pcba import pcba_sources

                    src = pcba_sources(text, str(self.path_watched.parent))
                    board = Board.loads(src["board"].read_text(encoding="utf-8"))
                    payload = mesh_payload(board_to_model(board), self.kernel)
                else:
                    payload = mesh_payload(Document.loads(text), self.kernel)
                self._send(200, json.dumps(payload).encode(), "application/json")
            elif self.path == "/api/schematics":
                sheets = discover_schematics(self.path_watched.parent)
                self._send(200, json.dumps({"sheets": sheets}).encode(),
                           "application/json")
            elif self.path == "/api/board.svg":
                kind = detect_kind(text)
                if kind == "schematic":
                    from gitcad.ecad import Schematic, schematic_to_svg

                    svg = schematic_to_svg(Schematic.loads(text))
                elif kind == "pcba":
                    from gitcad.pcba import pcba_sources

                    src = pcba_sources(text, str(self.path_watched.parent))
                    svg = board_to_svg(Board.loads(
                        src["board"].read_text(encoding="utf-8")))
                else:
                    svg = board_to_svg(Board.loads(text))
                self._send(200, svg.encode(), "image/svg+xml")
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
