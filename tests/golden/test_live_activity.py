"""The live channel: watching an agent work, and answering it.

Three things a person watching a design get built needs, none of which the
viewer could do before: see what is happening WHILE it happens, see WHICH part
of an assembly is being touched, and be asked a question they can answer
without leaving the page.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from gitcad.activity import Activity, session_dir


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()          # marks the repo root
    return tmp_path


def test_the_log_lands_beside_the_repo_root_not_the_cwd(project) -> None:
    """The agent and the viewer must agree on the path without being told it,
    whichever subdirectory each was started from."""
    deep = project / "parts" / "brackets"
    deep.mkdir(parents=True)
    assert session_dir(deep) == project / ".gitcad"
    assert session_dir(project) == project / ".gitcad"


def test_narration_reads_back_in_order_with_the_active_instance(project) -> None:
    act = Activity(project)
    act.status("resolving assembly")
    act.working("left_arm", text="filleting the mounting face")
    act.status("checking interference", instance="left_arm")

    state = act.state()
    assert [e["kind"] for e in state["events"]] == ["status"] * 3
    assert state["seq"] == 3
    assert state["active"]["instance"] == "left_arm"
    assert state["events"][1]["text"] == "filleting the mounting face"


def test_done_clears_the_active_highlight(project) -> None:
    """Otherwise a part stays lit green forever after the agent moves on."""
    act = Activity(project)
    act.working("left_arm")
    assert act.state()["active"] is not None
    act.done("assembly complete")
    assert act.state()["active"] is None


def test_reading_since_a_sequence_returns_only_what_is_new(project) -> None:
    act = Activity(project)
    act.status("one")
    first = act.state()
    act.status("two")
    later = act.state(first["seq"])
    assert [e["text"] for e in later["events"]] == ["two"]
    assert later["seq"] == 2


def test_state_reports_how_long_the_channel_has_been_silent(project) -> None:
    """`idle_s` lets the page stop the "working" pulse honestly: an agent that
    crashed after working() would otherwise look alive forever."""
    act = Activity(project)
    assert act.state()["idle_s"] is None          # no events: nothing to age
    act._append("status", text="long ago", instance="left_arm",
                t=time.time() - 600)
    s = act.state()
    assert s["active"]["instance"] == "left_arm"  # active is still exact…
    assert 590 < s["idle_s"] < 700                # …but its age is visible
    act.status("just now")
    assert act.state()["idle_s"] < 5


def test_a_torn_final_line_is_skipped_not_fatal(project) -> None:
    """The writer may be mid-append when the viewer polls. That must cost the
    reader nothing — the line is complete on the next tick."""
    act = Activity(project)
    act.status("intact")
    with open(act.path, "a", encoding="utf-8") as f:
        f.write('{"kind": "status", "text": "half-writ')
    assert [e["text"] for e in act.state()["events"]] == ["intact"]


def test_a_question_blocks_until_answered_and_returns_the_choice(project) -> None:
    act = Activity(project)
    got = {}

    def answerer():
        for _ in range(400):                 # wait for the question to appear
            q = act.state()["pending"]
            if q:
                act.answer(q["id"], "10 mm")
                return
            threading.Event().wait(0.01)

    t = threading.Thread(target=answerer, daemon=True)
    t.start()
    got["choice"] = act.ask("Boss diameter?", ["8 mm", "10 mm"], timeout=20)
    t.join(timeout=5)
    assert got["choice"] == "10 mm"
    assert act.state()["pending"] is None, "an answered question must clear"


def test_an_unanswered_question_times_out_rather_than_assuming(project) -> None:
    """A timeout is a real answer — "nobody was watching" — and the caller has
    to decide what to do with it. Silently proceeding would be the agent
    inventing consent."""
    act = Activity(project)
    assert act.ask("proceed?", ["yes"], timeout=0.15, poll=0.05) is None
    assert any(e["kind"] == "problem" for e in act.state()["events"])


# --- the same loop over HTTP, which is what the page actually drives ---------

def _serve(path: Path):
    from gitcad.viewer.server import serve

    srv = serve(str(path), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def test_the_page_can_read_activity_and_post_an_answer(project) -> None:
    doc = project / "part.gitcad"
    doc.write_text(json.dumps(
        {"schema": "gitcad/document@1", "features": []}), encoding="utf-8")
    act = Activity(project)
    act.working("left_arm", text="filleting")
    qid = act._append("question", id="q1", text="8 or 10?",
                      options=["8", "10"])["id"]

    srv, base = _serve(doc)
    try:
        state = _get(f"{base}/api/activity?since=0")
        assert state["active"]["instance"] == "left_arm"
        assert state["pending"]["id"] == qid
        assert state["idle_s"] < 60               # the page's staleness signal

        req = urllib.request.Request(
            f"{base}/api/answer", method="POST",
            data=json.dumps({"id": "q1", "choice": "10"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            assert json.loads(r.read())["ok"] is True

        assert _get(f"{base}/api/activity?since=0")["pending"] is None
    finally:
        srv.shutdown()


def test_a_malformed_answer_is_refused_not_recorded(project) -> None:
    """The POST body is untrusted input (ADR-0006/0007)."""
    doc = project / "part.gitcad"
    doc.write_text(json.dumps(
        {"schema": "gitcad/document@1", "features": []}), encoding="utf-8")
    srv, base = _serve(doc)
    try:
        req = urllib.request.Request(
            f"{base}/api/answer", method="POST",
            data=json.dumps({"id": 5, "choice": {"nested": True}}).encode(),
            headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        assert e.value.code == 400
        assert Activity(project).state()["events"] == []
    finally:
        srv.shutdown()


# --- the agent side: build paths narrate on their own ------------------------

def test_building_a_document_narrates_each_feature(project) -> None:
    """A watcher should see WHICH feature a long or failing build is on. The
    event is emitted before the op runs — after the fact is too late to be
    worth showing."""
    from gitcad import activity as A
    from gitcad.document import Document
    from gitcad.kernel import get_kernel

    doc = Document.loads(json.dumps({
        "schema": "gitcad/document@1",
        "features": [
            {"id": "base", "op": "box", "params": {"dx": 10, "dy": 10, "dz": 10}},
            {"id": "round", "op": "fillet", "inputs": ["base"],
             "params": {"edges": [], "radius": 1}},
        ]}))
    act = A.narrate_to(project)
    try:
        doc.build(get_kernel())
    finally:
        A.narrate_to(None)
    said = [e["text"] for e in act.state()["events"]]
    assert any("box · base" in s for s in said)
    assert any("fillet · round" in s for s in said)


def test_a_failing_feature_says_so_on_the_rail(project) -> None:
    from gitcad import activity as A
    from gitcad.document import Document
    from gitcad.kernel import get_kernel

    doc = Document.loads(json.dumps({
        "schema": "gitcad/document@1",
        "features": [
            {"id": "base", "op": "sphere", "params": {"radius": 6}},
            {"id": "cut", "op": "boolean", "inputs": ["base", "base"],
             "params": {"kind": "cut"}},
        ]}))
    act = A.narrate_to(project)
    try:
        with pytest.raises(Exception):
            doc.build(get_kernel())
    finally:
        A.narrate_to(None)
    assert any(e["kind"] == "problem" for e in act.state()["events"])


def test_narration_is_off_by_default_and_never_touches_disk(project) -> None:
    """A design must build identically with nobody watching."""
    from gitcad import activity as A
    from gitcad.document import Document
    from gitcad.kernel import get_kernel

    A.narrate_to(None)
    doc = Document.loads(json.dumps({
        "schema": "gitcad/document@1",
        "features": [{"id": "base", "op": "box",
                      "params": {"dx": 10, "dy": 10, "dz": 10}}]}))
    doc.build(get_kernel())
    assert not (project / ".gitcad").exists()


def test_a_sink_that_cannot_write_does_not_take_the_build_down(project) -> None:
    """A full disk or a read-only tree must not turn a working build into a
    failure — narration is never a dependency of building."""
    from gitcad import activity as A

    A.narrate_to(project)
    try:
        A._SINK.dir = Path("\0 not a directory")   # unopenable on any platform
        A.note(text="this must not raise")
    finally:
        A.narrate_to(None)


# --- the page's half of the live loop (string contracts, browser-free) -------

def test_page_ships_the_activity_tab() -> None:
    """The full build story is a TAB in the one page, not a separate page:
    every event, timestamped, and clicking an event that names an instance
    jumps to that part in 3D (scrub the history by pointing at it)."""
    from gitcad.viewer.page import PAGE

    assert 'id="activity"' in PAGE
    assert 'mk("activity"' in PAGE
    assert "renderActivity" in PAGE


def test_page_ships_camera_follow() -> None:
    """Attention, not just color: when the agent moves to another instance the
    camera glides to frame it. A follow toggle keeps the human in charge."""
    from gitcad.viewer.page import PAGE

    assert 'id="follow"' in PAGE
    assert "focusActive" in PAGE
    assert "glideTo" in PAGE


def test_page_reads_the_idle_signal() -> None:
    """The pulsing "working on X" must go quiet when the channel does."""
    from gitcad.viewer.page import PAGE

    assert "idle_s" in PAGE


def test_page_routes_every_tab_through_the_hash() -> None:
    """ONE page, addressable: #checks, #review, #drawing, #activity, #sheets
    deep-link into the same page, and switching tabs updates the URL."""
    from gitcad.viewer.page import PAGE

    assert "hashTokens" in PAGE
    assert "hashchange" in PAGE
    for t in ("sheets", "checks", "review", "drawing", "activity"):
        assert f'"{t}"' in PAGE


def test_page_reapplies_highlights_after_a_mesh_reload() -> None:
    """A rebuild lands a fresh mesh mid-watch; the green "being worked on"
    highlight must survive it, not vanish until the agent changes subject."""
    from gitcad.viewer.page import PAGE

    body = PAGE[PAGE.index("function upload"):PAGE.index("// -- tiny matrix")]
    assert "recolor()" in body
