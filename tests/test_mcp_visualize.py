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


def _two_part_assembly(tmp_path):
    """A tub + lid assembly on disk: manifest plus the sibling .part/.model
    files its instances resolve against."""
    from gitcad.part import Assembly, Interface, PartManifest, new_part_id

    parts = []
    for name, dz in (("tub", 0.0), ("lid", 5.0)):
        (tmp_path / f"{name}.model").write_text(_MODEL, encoding="utf-8")
        p = PartManifest(
            id=new_part_id(), name=name, domain="mech", version="0.1.0",
            interface=Interface(envelope={"origin": [0, 0, dz], "dx": 20,
                                          "dy": 10, "dz": 5}),
            body={"model": f"{name}.model"})
        (tmp_path / f"{name}.part").write_text(p.dumps(), encoding="utf-8")
        parts.append((name, p, dz))
    asm = Assembly("enclosure")
    for name, p, dz in parts:
        asm.add(name, p, translate=(0, 0, dz))
    path = tmp_path / "enclosure.part"
    path.write_text(asm.to_manifest(new_part_id()).dumps(), encoding="utf-8")
    return path


def test_visualize_refuses_assembly_text_rather_than_shooting_the_error(tmp_path) -> None:
    # An assembly resolves instances from sibling .part files. Handed only the
    # TEXT there are no siblings, and the old path screenshotted the viewer's
    # own "part not found" page and returned ok:true with it.
    path = _two_part_assembly(tmp_path)
    r = S.REGISTRY["visualize"](design=path.read_text(encoding="utf-8"))
    assert r["ok"] is False
    assert r["error"]["type"] == "AssemblyNeedsPath"
    assert "path" in r["error"]["message"].lower()


def test_visualize_renders_a_path_where_it_lives(tmp_path, monkeypatch) -> None:
    path = _two_part_assembly(tmp_path)
    seen: dict[str, str] = {}

    def fake_render(file, out, **kw):
        seen["file"] = file
        seen.update({k: v for k, v in kw.items() if k in ("explode",)})
        open(out, "wb").write(b"\x89PNG\r\n\x1a\n")
        return out

    monkeypatch.setattr("gitcad.render.find_browser", lambda: "chrome")
    monkeypatch.setattr("gitcad.render.render", fake_render)
    r = S.REGISTRY["visualize"](design=str(path), explode=0.6)
    assert r["ok"] is True and r["kind"] == "assembly"
    # rendered the manifest ITSELF, not a copy in a temp dir with no siblings
    assert seen["file"] == str(path)
    assert seen["explode"] == 0.6


def test_visualize_still_takes_model_text(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("gitcad.render.find_browser", lambda: "chrome")
    monkeypatch.setattr("gitcad.render.render",
                        lambda file, out, **kw: open(out, "wb").write(
                            b"\x89PNG\r\n\x1a\n"))
    r = S.REGISTRY["visualize"](design=_MODEL)
    assert r["ok"] is True and r["kind"] == "model"


def test_design_text_and_path_only_treats_real_files_as_paths(tmp_path) -> None:
    assert S._design_text_and_path(_MODEL) == (_MODEL, None)
    assert S._design_text_and_path("no/such/file.model") == ("no/such/file.model", None)
    f = tmp_path / "part.model"
    f.write_text(_MODEL, encoding="utf-8")
    assert S._design_text_and_path(str(f)) == (_MODEL, str(f))


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


def test_get_started_onboards_with_next_steps(tmp_path) -> None:
    # empty dir: should report no project and push init + GUI
    r = S.REGISTRY["get_started"](cwd=str(tmp_path))
    assert r["has_project"] is False and r["designs_found"] == []
    assert r["starter_model"]                       # a ready-to-build model
    joined = " ".join(r["recommended_next_steps"]) + r["open_the_gui"]
    assert "viewer_open" in joined and "model_new" in joined

    # a dir with a design: should find it and point at the GUI
    (tmp_path / "part.model").write_text(r["starter_model"], encoding="utf-8")
    r2 = S.REGISTRY["get_started"](cwd=str(tmp_path))
    assert r2["has_project"] is True
    assert any(d["kind"] == "model" for d in r2["designs_found"])
    assert "viewer_open" in " ".join(r2["recommended_next_steps"])
