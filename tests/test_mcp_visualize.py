"""MCP visualization surface: inline images, the image bridge, the live
viewer tools, and the viewer's drawing tab."""

from __future__ import annotations

import json
import urllib.request

import pytest

from gitcad.mcp import server as S
from gitcad.viewer.page import PAGE


def _box_model() -> str:
    m = S.REGISTRY["model_new"]()["model"]
    return S.REGISTRY["feature_add"](model=m, op="box",
                                     params={"dx": 20, "dy": 10, "dz": 5})["model"]


_MODEL = _box_model()


def test_new_visual_tools_are_registered() -> None:
    for name in ("visualize", "viewer_open", "viewer_list", "viewer_close"):
        assert name in S.REGISTRY


def test_viewer_open_serves_and_closes() -> None:
    r = S.REGISTRY["viewer_open"](design=_MODEL)
    assert r["ok"] and r["url"].startswith("http://127.0.0.1:")
    try:
        assert any(v["url"] == r["url"] for v in S.REGISTRY["viewer_list"]()["viewers"])
        page = urllib.request.urlopen(r["url"], timeout=5).read().decode()
        assert "gitcad" in page and 'id="tabs"' in page          # the viewer page
        ver = json.loads(urllib.request.urlopen(r["url"] + "api/version", timeout=5).read())
        assert ver["kind"] == "model"
    finally:
        closed = S.REGISTRY["viewer_close"](url=r["url"])
        assert closed["stopped"] == 1
    assert all(v["url"] != r["url"] for v in S.REGISTRY["viewer_list"]()["viewers"])


def test_visualize_without_browser_is_actionable(monkeypatch) -> None:
    monkeypatch.setattr("gitcad.render.find_browser", lambda: None)
    r = S.REGISTRY["visualize"](design=_MODEL)
    assert r["ok"] is False and r["error"]["type"] == "NoBrowser"


def test_image_bridge_converts_image_payload() -> None:
    import base64

    class FakeImage:
        def __init__(self, data, format):     # noqa: A002 - mirror the SDK
            self.data, self.format = data, format

    png = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    plain = S._image_bridge(lambda: {"ok": True, "x": 1}, FakeImage)
    assert plain() == {"ok": True, "x": 1}                        # passthrough

    imaged = S._image_bridge(
        lambda: {"ok": True, "kind": "model",
                 "image": {"png_base64": png, "mime": "image/png"}}, FakeImage)
    out = imaged()
    assert isinstance(out, list) and isinstance(out[0], FakeImage)
    assert out[0].format == "png" and out[0].data == b"\x89PNG\r\n\x1a\n"
    assert out[1] == {"ok": True, "kind": "model"}               # image stripped


def test_page_ships_the_drawing_tab() -> None:
    assert 'id="drawing"' in PAGE
    assert 'mk("drawing"' in PAGE
    assert "/api/drawing.pdf" in PAGE
    assert "drawingAvail" in PAGE


def test_github_report_is_consent_gated_by_default() -> None:
    r = S.REGISTRY["github_report"](repo="gitcad-xyz/gitcad", title="t",
                                    body="b", kind="issue")
    assert r["ok"] and r["preview"] is True
    assert r["would_file"]["repo"] == "gitcad-xyz/gitcad"
    assert "filed" not in r                       # nothing was filed
    bad = S.REGISTRY["github_report"](repo="x/y", title="t", body="b", kind="bogus")
    assert bad["ok"] is False                      # decorator catches the ValueError


def test_update_apply_preview_does_not_run_pip(monkeypatch) -> None:
    monkeypatch.setattr(S, "_pypi_latest", lambda pkg="gitcad": "999.0.0")
    r = S.REGISTRY["update_apply"](confirm=False)
    assert r["ok"] and r.get("preview") is True and r["to"] == "999.0.0"


def test_update_check_reports_versions(monkeypatch) -> None:
    monkeypatch.setattr(S, "_server_version", lambda: "0.8.0")
    monkeypatch.setattr(S, "_pypi_latest", lambda pkg="gitcad": "0.8.0")
    r = S.REGISTRY["update_check"]()
    assert r["ok"] and r["current"] == "0.8.0" and r["update_available"] is False


def test_drawing_endpoint_serves_svg_and_pdf_for_a_model() -> None:
    r = S.REGISTRY["viewer_open"](design=_MODEL)
    try:
        svg = urllib.request.urlopen(r["url"] + "api/drawing.svg", timeout=20).read()
        assert svg.lstrip().startswith(b"<") and b"svg" in svg[:200].lower()
        pdf = urllib.request.urlopen(r["url"] + "api/drawing.pdf", timeout=20).read()
        assert pdf.startswith(b"%PDF")
    finally:
        S.REGISTRY["viewer_close"](url=r["url"])


def test_drawing_endpoint_404_for_non_model() -> None:
    board = json.dumps({"schema": "gitcad/board/1", "outline": [[0, 0], [10, 0], [10, 10], [0, 10]]})
    r = S.REGISTRY["viewer_open"](design=board)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(r["url"] + "api/drawing.svg", timeout=10)
        assert e.value.code == 404
    finally:
        S.REGISTRY["viewer_close"](url=r["url"])
