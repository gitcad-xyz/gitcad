"""The project viewer contract, from the field bug (one session, three defects):

(A) LIFECYCLE — the viewer died with the MCP session because it ran as a
    daemon THREAD of that process. It is now a DETACHED process: killing the
    parent leaves HTTP serving and live-reload working; only the explicit
    viewer_stop / ``gitcad-view --stop`` ends it.
(B) PROACTIVITY — viewer_open launches the user's browser and ALWAYS returns
    the URL loudly; re-opening (any session) finds the running server through
    ``.gitcad/viewer.json`` and re-surfaces the same URL instead of spawning.
(C) ONE SERVER PER PROJECT — the default view is the TOP assembly; every part
    is a sub-interface in the one page (``/api/parts`` + ``#part=`` deep
    links), never a second server on another port.

Kernel-free: these tests exercise resolution, discovery, HTTP plumbing and
process lifecycle — none of which builds geometry.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from gitcad.document import Document, Feature
from gitcad.part import Assembly, PartManifest


def _get(url: str, timeout: float = 10.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def _project(root: Path) -> Path:
    """Two parts + one assembly — the demo project from the bug report."""
    def publish(name: str, part_id: str, dims) -> PartManifest:
        doc = Document()
        doc.add(Feature(op="box", params={"dx": dims[0], "dy": dims[1],
                                          "dz": dims[2]}))
        (root / f"{name}.model").write_text(doc.dumps(), newline="\n")
        part = PartManifest(id=part_id, name=name, domain="mech",
                            version="0.1.0", body={"model": f"{name}.model"})
        (root / f"{name}.part").write_text(part.dumps(), newline="\n")
        return part

    base = publish("base", "prt_0000000000000001", (60, 40, 8))
    lid = publish("lid", "prt_0000000000000002", (60, 40, 3))
    asm = Assembly("stack")
    asm.add("base", base)
    asm.add("lid", lid, translate=(0, 0, 8))
    apath = root / "stack.part.json"
    apath.write_text(asm.to_manifest("prt_00000000000000aa").dumps(),
                     newline="\n")
    return apath


# -- (C) resolution: the project, its designs, its top assembly ---------------

def test_default_view_is_the_top_assembly(tmp_path) -> None:
    from gitcad.viewer.project import discover_designs, resolve_default

    _project(tmp_path)
    designs = discover_designs(tmp_path)
    by_file = {d["file"]: d for d in designs}
    assert {"base.model", "lid.model", "stack.part.json"} <= set(by_file)
    assert by_file["stack.part.json"]["kind"] == "assembly"
    assert resolve_default(tmp_path, designs) == "stack.part.json"


def test_single_part_project_falls_back_to_the_model(tmp_path) -> None:
    from gitcad.viewer.project import discover_designs, resolve_default

    doc = Document()
    doc.add(Feature(op="box", params={"dx": 5, "dy": 5, "dz": 5}))
    (tmp_path / "solo.model").write_text(doc.dumps(), newline="\n")
    assert resolve_default(tmp_path, discover_designs(tmp_path)) == "solo.model"


def test_sub_assembly_is_never_the_default(tmp_path) -> None:
    from gitcad.viewer.project import discover_designs, resolve_default

    _project(tmp_path)
    # wrap the stack in a bigger top-level assembly referencing it
    sub = PartManifest.loads((tmp_path / "stack.part.json").read_text())
    top = Assembly("machine")
    top.add("stack", sub)
    (tmp_path / "machine.part.json").write_text(
        top.to_manifest("prt_00000000000000bb").dumps(), newline="\n")
    assert resolve_default(tmp_path, discover_designs(tmp_path)) \
        == "machine.part.json"


def test_serve_a_directory_serves_the_whole_project(tmp_path) -> None:
    import threading

    from gitcad.viewer.server import serve

    _project(tmp_path)
    httpd = serve(str(tmp_path), port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/"
    try:
        # default view = the top assembly
        v = _get(base + "api/version")
        assert v["kind"] == "assembly" and v["name"] == "stack.part.json"
        # the parts sub-interface index
        parts = _get(base + "api/parts")
        assert parts["default"] == "stack.part.json"
        files = {d["file"] for d in parts["designs"]}
        assert {"base.model", "lid.model", "stack.part.json"} <= files
        # any part, IN the same server — the ?file= plumbing behind #part=
        v_lid = _get(base + "api/version?file=lid.model")
        assert v_lid["kind"] == "model" and v_lid["name"] == "lid.model"
        # a path escape is refused, not served
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(
                base + "api/version?file=../../../etc/passwd", timeout=10)
        assert e.value.code == 500 and b"escapes" in e.value.read()
    finally:
        httpd.shutdown()


def test_page_ships_the_parts_navigator() -> None:
    from gitcad.viewer.page import PAGE

    assert "/api/parts" in PAGE
    assert 'id="parts"' in PAGE
    assert "part=" in PAGE and "encodeURIComponent" in PAGE
    # every design fetch is re-pointable at a part
    for ep in ("/api/version", "/api/mesh", "/api/checks", "/api/schematics",
               "/api/board.svg"):
        assert f'"{ep}" + qs()' in PAGE, ep


# -- (A)+(B) lifecycle: detached, discoverable, reusable, stoppable -----------

_PARENT = """
import json, sys
from gitcad.viewer.daemon import ensure_viewer
state, reused = ensure_viewer(sys.argv[1])
print(json.dumps({"state": state, "reused": reused}), flush=True)
"""


def test_viewer_outlives_its_parent_and_only_stops_on_request(tmp_path) -> None:
    """THE death test: the daemon spawned by an agent process keeps serving
    after that process dies, live-reloads a part edit, is reused by a new
    session, and stops only on the explicit stop."""
    from gitcad.viewer.daemon import (discovery_path, ensure_viewer, probe,
                                      read_state, stop_viewer)

    _project(tmp_path)
    script = tmp_path / "parent.py"
    script.write_text(_PARENT, encoding="utf-8")
    try:
        # 1. the "MCP session": a separate process opens the viewer, then DIES
        out = subprocess.run([sys.executable, str(script), str(tmp_path)],
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr
        state = json.loads(out.stdout)["state"]
        url = state["url"]
        assert state["default"] == "stack.part.json"

        # 2. parent is gone; the viewer must still serve 10+ seconds later
        time.sleep(10)
        v1 = _get(url + "api/version")
        assert v1["kind"] == "assembly"

        # 3. live reload across the orphaning: edit a PART file on disk and
        #    the assembly digest (deps included) must change
        lid = tmp_path / "lid.model"
        doc = Document.loads(lid.read_text())
        doc.add(Feature(op="box", params={"dx": 1, "dy": 1, "dz": 1}))
        lid.write_text(doc.dumps(), newline="\n")
        v2 = _get(url + "api/version")
        assert v2["version"] != v1["version"]

        # 4. a NEW session reuses the same server and URL — never respawns
        state2, reused = ensure_viewer(tmp_path)
        assert reused is True and state2["url"] == url

        # 5. only the explicit stop ends it; the record is cleared
        r = stop_viewer(tmp_path)
        assert r["stopped"] is True
        assert probe(read_state(tmp_path)) is None
        assert not discovery_path(tmp_path).exists()

        # 6. re-open after a stop starts FRESH
        state3, reused3 = ensure_viewer(tmp_path)
        assert reused3 is False
        assert _get(state3["url"] + "api/health")["ok"] is True
    finally:
        stop_viewer(tmp_path)


def test_stale_discovery_record_is_replaced_not_trusted(tmp_path) -> None:
    from gitcad.viewer.daemon import discovery_path, ensure_viewer, stop_viewer

    _project(tmp_path)
    dpath = discovery_path(tmp_path)
    dpath.parent.mkdir(parents=True, exist_ok=True)
    # a dead viewer's leftovers: nothing listens on this port, pid long gone
    dpath.write_text(json.dumps({"pid": 999999999, "port": 1,
                                 "url": "http://127.0.0.1:1/",
                                 "root": str(tmp_path)}), encoding="utf-8")
    try:
        state, reused = ensure_viewer(tmp_path)
        assert reused is False and state["port"] != 1
        assert _get(state["url"] + "api/health")["ok"] is True
    finally:
        stop_viewer(tmp_path)


def test_viewer_open_launches_browser_and_shouts_the_url(tmp_path, monkeypatch) -> None:
    """(B): the MCP tool opens the user's browser and the URL is in the result
    — loudly — whether or not the launch worked."""
    import webbrowser

    from gitcad.mcp import server as S

    _project(tmp_path)
    launched: list[str] = []
    monkeypatch.delenv("GITCAD_NO_BROWSER", raising=False)
    monkeypatch.setattr(webbrowser, "open", lambda u, *a, **k:
                        launched.append(u) or True)
    r = S.REGISTRY["viewer_open"](path=str(tmp_path))
    try:
        assert r["ok"] and r["browser_opened"] is True
        assert launched == [r["url"]]
        assert r["url"] in r["message"]           # the URL is always surfaced
        assert r["default_view"] == "stack.part.json"
        # parts are IN-PAGE deep links on the SAME port, never other servers
        by_file = {p["file"]: p for p in r["parts"]}
        assert by_file["lid.model"]["url"] == r["url"] + "#part=lid.model"
        # idempotent re-open: same URL, reused, no second spawn
        r2 = S.REGISTRY["viewer_open"](path=str(tmp_path), open_browser=False)
        assert r2["reused"] is True and r2["url"] == r["url"]
    finally:
        S.REGISTRY["viewer_stop"](path=str(tmp_path))


def test_mcp_guidance_teaches_the_persistent_project_viewer() -> None:
    """The field agent behaved wrongly because our instructions let it. The
    contract must be IN the guidance an MCP host shows its agent."""
    from gitcad.mcp import server as S

    text = S._SERVER_INSTRUCTIONS
    assert "ONE viewer per PROJECT" in text
    assert "TOP ASSEMBLY" in text
    assert "#part=" in text
    assert "NEVER shut it down" in text
    assert "viewer_stop" in text
    doc = S.viewer_open.__doc__
    assert "DETACHED" in doc and "survives" in doc
    assert "NEVER stop the viewer" in doc
    assert "explicitly asks" in S.viewer_stop.__doc__
    assert "never a reason" in S.viewer_stop.__doc__


def test_top_assembly_becomes_the_default_when_it_is_written_later(tmp_path) -> None:
    """The order of work is parts-then-assembly, so the viewer that
    ``model_new(path=...)`` auto-starts is always looking at a PART. The
    default view must re-resolve, or the promised "opens on the TOP
    ASSEMBLY" never comes true for any real project."""
    import threading

    from gitcad.viewer.server import serve

    # a project with parts but NO assembly yet — this is what the daemon
    # sees at the moment the first model_new lands
    doc = Document()
    doc.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 2}))
    (tmp_path / "base.model").write_text(doc.dumps(), newline="\n")

    httpd = serve(str(tmp_path), port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/"
    try:
        assert _get(base + "api/parts")["default"] == "base.model"
        assert _get(base + "api/health")["default"] == "base.model"

        _project(tmp_path)                  # the assembly arrives afterwards

        assert _get(base + "api/parts")["default"] == "stack.part.json"
        assert _get(base + "api/health")["default"] == "stack.part.json"
        # and the page's own default view follows, not just the label
        v = _get(base + "api/version")
        assert v["kind"] == "assembly" and v["name"] == "stack.part.json"
    finally:
        httpd.shutdown()


def test_a_viewer_served_on_one_file_keeps_that_file(tmp_path) -> None:
    """``serve(<design file>)`` documents the opposite contract — the file
    stays the default view even though the project has a top assembly."""
    import threading

    from gitcad.viewer.server import serve

    _project(tmp_path)
    httpd = serve(str(tmp_path / "lid.model"), port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/"
    try:
        assert _get(base + "api/parts")["default"] == "lid.model"
        assert _get(base + "api/version")["name"] == "lid.model"
    finally:
        httpd.shutdown()
