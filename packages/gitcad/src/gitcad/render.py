"""gitcad-render — PNG/SVG artifacts from any design file.

The real-world deliverable set includes IMAGES (board renders, schematic
sheets, assembly views for the styling review). SVG is native everywhere
here; PNG rasterization borrows a local Chrome/Edge in headless mode —
found automatically, and its absence is a loud, actionable error, never
a silent downgrade.

- schematic -> sheet-fidelity SVG (imported) or auto-layout SVG
- board -> board SVG
- model / assembly / pcba -> 3D via the viewer + headless browser
  (#x= deep link renders exploded states)
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from gitcad.errors import GitcadError


def find_browser() -> str | None:
    for name in ("chrome", "google-chrome", "chromium", "chromium-browser",
                 "msedge"):
        exe = shutil.which(name)
        if exe:
            return exe
    for cand in (
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    ):
        if cand.is_file():
            return str(cand)
    return None


def _svg_for(path: Path) -> str:
    if path.suffix == ".kicad_sch":
        # imported sheets render EXACTLY as drawn (fidelity renderer)
        from gitcad.ecad.schsvg import sheet_to_svg
        from gitcad.importers.kicad_sch import import_kicad_sch

        sch, _report = import_kicad_sch(str(path))
        return sheet_to_svg(sch)
    text = path.read_text(encoding="utf-8")
    from gitcad.viewer.server import detect_kind

    kind = detect_kind(text)
    if kind == "schematic":
        from gitcad.ecad import Schematic, schematic_to_svg

        return schematic_to_svg(Schematic.loads(text))
    if kind == "board":
        from gitcad.ecad import Board
        from gitcad.viewer.boardsvg import board_to_svg

        return board_to_svg(Board.loads(text))
    if kind == "pcba":
        from gitcad.ecad import Board
        from gitcad.pcba import pcba_sources
        from gitcad.viewer.boardsvg import board_to_svg

        src = pcba_sources(text, str(path.parent))
        return board_to_svg(Board.loads(src["board"].read_text(encoding="utf-8")))
    raise GitcadError(f"no direct SVG projection for kind {kind!r} — "
                      "use PNG output (3D render via the viewer)")


def _png_from_svg(svg: str, out: Path, browser: str, width: int, height: int) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "r.svg"
        f.write_text(svg, encoding="utf-8")
        _shoot(browser, f.as_uri(), out, width, height)


def _shoot(browser: str, url: str, out: Path, width: int, height: int) -> None:
    proc = subprocess.run(
        [browser, "--headless", "--disable-gpu",
         f"--screenshot={out}", f"--window-size={width},{height}",
         "--virtual-time-budget=10000", url],
        capture_output=True, timeout=120)
    if not out.is_file():
        raise GitcadError(
            f"browser rasterization produced no file "
            f"(exit {proc.returncode}): {proc.stderr.decode(errors='replace')[:200]}")


def render(file: str, out: str, *, width: int = 1400, height: int = 900,
           explode: float = 0.0, three: bool = False) -> str:
    """Render a design file to ``out`` (.svg or .png). ``three`` forces a 3D
    render for boards (the '3d iso' deliverable — board extruded through the
    bridge). Returns the path."""
    src = Path(file)
    dst = Path(out)
    if src.suffix == ".kicad_sch":
        kind = "schematic"
        text = None
    else:
        text = src.read_text(encoding="utf-8")
        from gitcad.viewer.server import detect_kind

        kind = detect_kind(text)

    if dst.suffix.lower() == ".svg":
        dst.write_text(_svg_for(src), encoding="utf-8")
        return str(dst)
    if dst.suffix.lower() != ".png":
        raise GitcadError(f"unknown output format {dst.suffix!r} (want .svg or .png)")

    browser = find_browser()
    if browser is None:
        raise GitcadError(
            "PNG rendering needs a local Chrome/Edge (headless screenshot) — "
            "none found; install one or render .svg instead")

    if kind == "board" and three:
        # the 3D board deliverable: extrude through the bridge, serve, shoot
        import tempfile

        from gitcad.bridge import board_to_model
        from gitcad.ecad import Board

        doc = board_to_model(Board.loads(text))
        with tempfile.TemporaryDirectory() as td:
            model = Path(td) / "board3d.model"
            model.write_text(doc.dumps(), encoding="utf-8")
            return _serve_and_shoot(model, dst, browser, width, height, explode)

    if kind in ("schematic", "board"):
        _png_from_svg(_svg_for(src), dst, browser, width, height)
        return str(dst)

    # 3D kinds: serve the viewer briefly, screenshot it
    return _serve_and_shoot(src, dst, browser, width, height, explode)


def _serve_and_shoot(src: Path, dst: Path, browser: str,
                     width: int, height: int, explode: float) -> str:
    import threading

    from gitcad.viewer.server import serve

    httpd = serve(str(src), port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        time.sleep(0.3)
        frag = f"#x={explode}" if explode else ""
        _shoot(browser, f"http://127.0.0.1:{port}/{frag}", dst, width, height)
    finally:
        httpd.shutdown()
    return str(dst)


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse

    ap = argparse.ArgumentParser(
        description="gitcad render — PNG/SVG images from any design file")
    ap.add_argument("file")
    ap.add_argument("-o", "--out", required=True, help="output .png or .svg")
    ap.add_argument("--width", type=int, default=1400)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--explode", type=float, default=0.0,
                    help="exploded-view amount 0..1 (3D kinds)")
    ap.add_argument("--three", action="store_true",
                    help="render a board in 3D (extruded) instead of top view")
    args = ap.parse_args()
    print(render(args.file, args.out, width=args.width, height=args.height,
                 explode=args.explode, three=args.three))
