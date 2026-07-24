"""GOLDEN: the viewer — tessellation, mesh payload, board SVG, live server."""

from __future__ import annotations

import json
import urllib.request

import pytest

from gitcad.document import Document, Feature
from gitcad.ecad import Board, Component, Footprint, MountingHole, Pad, Track, Via
from gitcad.viewer import board_to_svg


def _board() -> Board:
    fp = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                                  Pad("2", 0.75, 0, 0.9, 0.95)])
    b = Board(name="t", outline=[(0, 0), (30, 0), (30, 20), (0, 20)])
    b.components.append(Component("R1", fp, x=15, y=10, nets={"1": "A", "2": "B"}))
    b.tracks.append(Track(2, 5, 14.25, 10, 0.3, "top", "A"))
    b.vias.append(Via(25, 5))
    b.mounting_holes.append(MountingHole("mnt_1", 27, 17, 3.2))
    return b


def test_board_svg_renders_all_elements() -> None:
    svg = board_to_svg(_board())
    assert svg.startswith("<svg")
    assert svg.count("<rect") == 2      # two SMD pads
    assert "<polygon" in svg            # outline
    assert svg.count("<line") == 1      # one track
    assert ">R1</text>" in svg          # designator
    assert svg.count("<circle") == 3    # via + via hole + mounting hole
    assert board_to_svg(_board()) == svg  # deterministic


def test_tessellation_produces_valid_mesh() -> None:
    from gitcad.kernel.ref import RefKernel

    k = RefKernel()
    # a drilled plate — the most common part; must mesh watertight around the hole
    shape = k.boolean("cut", k.box(60, 40, 8),
                      k.transform(k.cylinder(3.2, 8), translate=(15, 20, 0)))
    mesh = k.tessellate(shape)                 # forge seam: {vertices, triangles}
    verts, tris = mesh["vertices"], mesh["triangles"]
    n_verts = len(verts)
    assert n_verts > 8 and all(len(t) == 3 for t in tris)
    assert max(i for t in tris for i in t) < n_verts   # indices in range
    xs = [v[0] for v in verts]
    zs = [v[2] for v in verts]
    assert min(xs) == pytest.approx(0, abs=1e-3) and max(xs) == pytest.approx(60, abs=1e-3)
    assert max(zs) == pytest.approx(8, abs=1e-3)
    # watertight: every edge shared by exactly two triangles
    from collections import defaultdict
    ec = defaultdict(int)
    for a, b, c in tris:
        for e in ((a, b), (b, c), (c, a)):
            ec[tuple(sorted(e))] += 1
    assert all(n == 2 for n in ec.values())


def test_server_serves_page_version_and_mesh(tmp_path) -> None:
    from gitcad.viewer.server import serve

    doc = Document()
    doc.add(Feature(op="box", params={"dx": 10, "dy": 20, "dz": 5}))
    path = tmp_path / "m.gitcad.json"
    path.write_text(doc.dumps(), newline="\n")

    httpd = serve(str(path), port=0)   # ephemeral port
    port = httpd.server_address[1]
    import threading

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        page = urllib.request.urlopen(f"{base}/").read().decode()
        assert "webgl2" in page and "gitcad" in page

        version = json.loads(urllib.request.urlopen(f"{base}/api/version").read())
        assert version["kind"] == "model" and len(version["version"]) == 64

        mesh = json.loads(urllib.request.urlopen(f"{base}/api/mesh").read())
        assert mesh["stats"]["volume_mm3"] == pytest.approx(1000.0)
        assert mesh["bbox"] == [[0, 0, 0], [10, 20, 5]]

        # Live reload: change the file, the version hash changes.
        doc.add(Feature(op="sphere", params={"radius": 2}))
        path.write_text(doc.dumps(), newline="\n")
        version2 = json.loads(urllib.request.urlopen(f"{base}/api/version").read())
        assert version2["version"] != version["version"]
    finally:
        httpd.shutdown()


def test_server_board_svg_route(tmp_path) -> None:
    from gitcad.viewer.server import serve

    path = tmp_path / "b.gitcad.json"
    path.write_text(_board().dumps(), newline="\n")
    httpd = serve(str(path), port=0)
    port = httpd.server_address[1]
    import threading

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        version = json.loads(urllib.request.urlopen(f"{base}/api/version").read())
        assert version["kind"] == "board"
        svg = urllib.request.urlopen(f"{base}/api/board.svg").read().decode()
        assert svg.startswith("<svg") and ">R1</text>" in svg
    finally:
        httpd.shutdown()
