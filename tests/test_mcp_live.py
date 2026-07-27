"""MCP live-loop surface: the agent's half of the watch-and-answer channel.

The core mechanism (gitcad.activity) existed and the page could render it, but
nothing let an MCP-driven agent SAY anything — viewer_note narrates onto the
live rail, viewer_ask blocks on the human in the page. Both are plain REGISTRY
handlers, tested here without an MCP host.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request

from gitcad.mcp import server as S


def _model() -> str:
    m = S.REGISTRY["model_new"]()["model"]
    return S.REGISTRY["feature_add"](model=m, op="box",
                                     params={"dx": 5, "dy": 5, "dz": 5})["model"]


def _get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def _open(tmp_path):
    p = tmp_path / "m.model"
    p.write_text(_model(), encoding="utf-8")
    return S.REGISTRY["viewer_open"](path=str(p))


def test_live_tools_are_registered() -> None:
    for name in ("viewer_note", "viewer_ask"):
        assert name in S.REGISTRY


def test_viewer_note_lands_on_the_watched_rail(tmp_path) -> None:
    r = _open(tmp_path)
    try:
        n = S.REGISTRY["viewer_note"](text="milling the pocket",
                                      instance="left_arm")
        assert n["ok"]
        s = _get(r["url"] + "api/activity?since=0")
        assert any(e.get("text") == "milling the pocket" for e in s["events"])
        assert s["active"]["instance"] == "left_arm"

        assert S.REGISTRY["viewer_note"](text="pocket done", kind="done")["ok"]
        assert _get(r["url"] + "api/activity?since=0")["active"] is None
    finally:
        S.REGISTRY["viewer_close"](url=r["url"])


def test_viewer_note_refuses_an_unknown_kind(tmp_path) -> None:
    r = _open(tmp_path)
    try:
        bad = S.REGISTRY["viewer_note"](text="x", kind="celebration")
        assert bad["ok"] is False
    finally:
        S.REGISTRY["viewer_close"](url=r["url"])


def test_viewer_note_without_any_viewer_is_an_actionable_error() -> None:
    S.REGISTRY["viewer_close"]()                   # none watching, nobody to tell
    r = S.REGISTRY["viewer_note"](text="into the void")
    assert r["ok"] is False and "viewer_open" in r["error"]["message"]


def test_viewer_ask_round_trips_through_the_page_api(tmp_path) -> None:
    """The whole loop: agent blocks in viewer_ask, the page's POST /api/answer
    releases it with the human's choice."""
    r = _open(tmp_path)
    try:
        def human() -> None:
            for _ in range(200):
                s = _get(r["url"] + "api/activity?since=0")
                if s["pending"]:
                    req = urllib.request.Request(
                        r["url"] + "api/answer", method="POST",
                        data=json.dumps({"id": s["pending"]["id"],
                                         "choice": "M4"}).encode(),
                        headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=10)
                    return
                time.sleep(0.05)

        t = threading.Thread(target=human, daemon=True)
        t.start()
        a = S.REGISTRY["viewer_ask"](question="Bolt size?",
                                     options=["M3", "M4"], timeout_s=30)
        t.join(timeout=5)
        assert a["ok"] and a["answered"] is True and a["answer"] == "M4"
    finally:
        S.REGISTRY["viewer_close"](url=r["url"])


def test_viewer_ask_timeout_is_a_real_answer_not_consent(tmp_path) -> None:
    r = _open(tmp_path)
    try:
        a = S.REGISTRY["viewer_ask"](question="anyone there?", timeout_s=0.1)
        assert a["ok"] and a["answered"] is False and a["answer"] is None
    finally:
        S.REGISTRY["viewer_close"](url=r["url"])


def test_viewer_ask_with_explicit_path_needs_no_open_viewer(tmp_path) -> None:
    """A viewer run as `gitcad view` lives in another process — this one's
    registry cannot see it. An explicit path targets its project directly."""
    from gitcad.activity import Activity

    S.REGISTRY["viewer_close"]()
    a = S.REGISTRY["viewer_ask"](question="still there?", timeout_s=0.1,
                                 path=str(tmp_path))
    assert a["ok"] and a["answered"] is False
    events = Activity(tmp_path).state()["events"]
    assert any(e["kind"] == "question" for e in events)
