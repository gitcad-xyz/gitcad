"""The design-session loop (#6/#7/#12).

Three contracts that make the loop self-enforcing rather than advisory:

* #12 — ``feature_add`` builds the tree it just extended and refuses an
  unbuildable feature THERE, with the kernel's structured reason — never a
  success now and a refusal three tools later. ``validate=false`` opts into
  deferral (batching); the default is eager truth.
* #7 — a model can be FILE-BACKED (``model_new(path=...)``): the document
  lives in the project from the moment it exists (ADR-0004: text IS source),
  and every successful ``feature_add`` persists, so the viewer watches
  features land. A refused feature never touches the file.
* #6 — the project viewer is a consequence of starting work: ``model_new``
  (file-backed) and ``get_started`` auto-ensure the detached viewer and carry
  its URL in the tool result, unless ``GITCAD_NO_BROWSER=1`` opts out.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from gitcad.mcp import server as S

BOX = {"dx": 10, "dy": 10, "dz": 10}


def _get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def _boxed() -> tuple[str, str]:
    m = S.REGISTRY["model_new"]()["model"]
    r = S.REGISTRY["feature_add"](model=m, op="box", params=BOX)
    return r["model"], r["feature_id"]


# --- #12: eager truth at feature_add -----------------------------------------


def test_feature_add_refuses_an_unknown_op_immediately() -> None:
    m = S.REGISTRY["model_new"]()["model"]
    r = S.REGISTRY["feature_add"](model=m, op="bogus_op")
    assert r["ok"] is False and r["buildable"] is False
    assert r["refused"]["op"] == "bogus_op"
    assert "bogus_op" in r["error"]["message"]
    assert r["model"] == m           # the poisoned feature was NOT kept


def test_feature_add_refuses_missing_inputs_immediately() -> None:
    m, _fid = _boxed()
    r = S.REGISTRY["feature_add"](
        model=m, op="hole",
        params={"x": 5, "y": 5, "top_z": 10, "depth": 5, "diameter": 3})
    assert r["ok"] is False and r["buildable"] is False
    assert "inputs" in r["error"]["message"]
    assert r["model"] == m


def test_feature_add_success_reports_buildable() -> None:
    m = S.REGISTRY["model_new"]()["model"]
    r = S.REGISTRY["feature_add"](model=m, op="box", params=BOX)
    assert r["buildable"] is True and "feature_id" in r
    assert "geometry_verified" in r  # null backend must not masquerade


def test_feature_add_validate_false_defers_to_the_next_build() -> None:
    m = S.REGISTRY["model_new"]()["model"]
    r = S.REGISTRY["feature_add"](model=m, op="bogus_op", validate=False)
    assert "feature_id" in r and "buildable" not in r    # batching keeps it
    meas = S.REGISTRY["model_measure"](model=r["model"])
    assert meas["ok"] is False                           # truth still arrives


@pytest.mark.kernel
def test_feature_add_surfaces_a_real_kernel_refusal_with_its_reason() -> None:
    """The #12 field case: a boolean the exact kernel refuses (a quadric
    operand, K2.2) is refused AT feature_add, structured, fingerprinted."""
    m, box_id = _boxed()
    r = S.REGISTRY["feature_add"](model=m, op="sphere", params={"radius": 4})
    m2, sph_id = r["model"], r["feature_id"]
    assert r["buildable"] is True
    bad = S.REGISTRY["feature_add"](model=m2, op="boolean",
                                    params={"kind": "cut"},
                                    inputs=[box_id, sph_id])
    assert bad["ok"] is False and bad["buildable"] is False
    assert "boolean" in bad["error"]["message"]
    assert bad["refusal"]["op"].startswith("boolean")    # the kernel's reason
    assert "fingerprint" in bad                          # feeds the bug loop
    assert bad["model"] == m2                            # tree not poisoned


# --- #7: the model lives in the project --------------------------------------


def test_model_new_with_path_creates_the_file(tmp_path) -> None:
    p = tmp_path / "body.model"
    r = S.REGISTRY["model_new"](path=str(p))
    assert p.exists()
    assert p.read_text(encoding="utf-8") == r["model"]
    assert r["path"] == str(p)


def test_model_new_refuses_to_overwrite(tmp_path) -> None:
    p = tmp_path / "body.model"
    S.REGISTRY["model_new"](path=str(p))
    r = S.REGISTRY["model_new"](path=str(p))
    assert r["ok"] is False and "exists" in r["error"]["message"]


def test_model_new_requires_a_viewable_suffix(tmp_path) -> None:
    r = S.REGISTRY["model_new"](path=str(tmp_path / "body.txt"))
    assert r["ok"] is False and ".model" in r["error"]["message"]


def test_feature_add_on_a_file_backed_model_persists_every_feature(tmp_path) -> None:
    p = tmp_path / "body.model"
    S.REGISTRY["model_new"](path=str(p))
    r = S.REGISTRY["feature_add"](model=str(p), op="box", params=BOX)
    assert r["buildable"] is True and r["path"] == str(p)
    on_disk = p.read_text(encoding="utf-8")
    assert on_disk == r["model"]                          # every add writes
    assert json.loads(on_disk)["features"][0]["op"] == "box"

    bad = S.REGISTRY["feature_add"](model=str(p), op="bogus_op")
    assert bad["ok"] is False
    assert p.read_text(encoding="utf-8") == on_disk       # file never poisoned


def test_model_tools_accept_the_file_handle(tmp_path) -> None:
    p = tmp_path / "body.model"
    S.REGISTRY["model_new"](path=str(p))
    S.REGISTRY["feature_add"](model=str(p), op="box", params=BOX)
    meas = S.REGISTRY["model_measure"](model=str(p))
    assert "measures" in meas
    val = S.REGISTRY["model_validate"](model=str(p))
    assert "results" in val


def test_model_parameters_persist_on_a_file_backed_model(tmp_path) -> None:
    p = tmp_path / "body.model"
    S.REGISTRY["model_new"](path=str(p))
    r = S.REGISTRY["model_parameters"](model=str(p), set={"W": 30})
    assert r["resolved"] == {"W": 30.0}
    assert json.loads(p.read_text(encoding="utf-8"))["parameters"] == {"W": 30}


def test_a_missing_model_file_is_an_actionable_error() -> None:
    r = S.REGISTRY["feature_add"](model="no_such_dir/nope.model", op="box",
                                  params=BOX)
    assert r["ok"] is False and "model_new" in r["error"]["message"]


# --- #6: the GUI is a consequence of starting work ----------------------------


def test_no_browser_optout_suppresses_viewer_autostart(tmp_path) -> None:
    # conftest sets GITCAD_NO_BROWSER=1 for the whole suite
    p = tmp_path / "body.model"
    r = S.REGISTRY["model_new"](path=str(p))
    assert "viewer_url" not in r
    gs = S.REGISTRY["get_started"](cwd=str(tmp_path))
    assert gs["has_project"] and "viewer_url" not in gs


def test_viewer_treats_an_empty_model_as_building_not_an_error(tmp_path) -> None:
    """model_new(path=...) creates the file BEFORE the first feature, and the
    auto-started viewer opens on it: an empty document is a state ('building')
    the mesh/checks endpoints must answer, never a 500 (#6)."""
    from gitcad.document import Document
    from gitcad.kernel.null import NullKernel
    from gitcad.viewer.server import mesh_payload, run_checks_for

    payload = mesh_payload(Document(), NullKernel())
    assert payload["stats"]["features"] == 0
    assert payload["stats"]["triangles"] == 0
    assert "building" in payload["stats"]
    assert payload["positions"] == [] and payload["indices"] == []

    p = tmp_path / "body.model"
    p.write_text(Document().dumps(), encoding="utf-8")
    checks = run_checks_for(p, NullKernel())
    assert checks["ok"] is True and checks["total_violations"] == 0


def test_design_session_e2e_the_viewer_follows_the_work(tmp_path, monkeypatch) -> None:
    """The whole loop against a REAL detached viewer: model_new starts the GUI
    and returns its URL -> the viewer lists the model -> feature_add persists
    and the viewed content version changes -> a bad feature is refused
    immediately and the viewer's content is untouched."""
    monkeypatch.delenv("GITCAD_NO_BROWSER", raising=False)
    launched: list[str] = []
    monkeypatch.setattr("gitcad.viewer.daemon.launch_browser",
                        lambda url: launched.append(url) or True)
    p = tmp_path / "body.model"
    r = S.REGISTRY["model_new"](path=str(p))
    try:
        url = r["viewer_url"]
        assert url.startswith("http://127.0.0.1:")
        assert launched == [url]              # the user's browser was opened
        assert any(d["file"] == "body.model"
                   for d in _get(url + "api/parts")["designs"])
        v0 = _get(url + "api/version")["version"]
        m0 = _get(url + "api/mesh")           # empty model: 'building', not 500
        assert m0["stats"]["triangles"] == 0 and "building" in m0["stats"]

        r2 = S.REGISTRY["feature_add"](model=str(p), op="box", params=BOX)
        assert r2["buildable"] is True
        assert r2["viewer_url"] == url        # slow tools carry the URL
        v1 = _get(url + "api/version")["version"]
        assert v1 != v0                       # the page saw the feature land
        if m0["stats"]["kernel"] != "null":   # geometry claims need a kernel
            assert _get(url + "api/mesh")["stats"]["triangles"] > 0

        gs = S.REGISTRY["get_started"](cwd=str(tmp_path))
        assert gs["viewer_url"] == url        # get_started rejoins, same URL

        bad = S.REGISTRY["feature_add"](model=str(p), op="bogus_op")
        assert bad["ok"] is False             # immediate structured refusal
        assert _get(url + "api/version")["version"] == v1   # file untouched
    finally:
        S.REGISTRY["viewer_stop"](path=str(tmp_path))
