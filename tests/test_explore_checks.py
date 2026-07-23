"""Golden: branch scoreboard + viewer checks endpoint. Kernel-free.

Scoreboard oracle: two variant branches of one design — the clean one
ranks first with gate PASS; the one shorting a rail to 5V ranks last
with gate FAIL and its introduced count visible. Checks endpoint oracle:
a red schematic reports its exact violations through /api/checks.
"""

import subprocess

import pytest

from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.explore import score_branches, to_markdown


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


def _sch(rail: str) -> str:
    sch = Schematic(name="v")
    sch.components = [
        SchComponent(ref="U1", pins=[Pin("VDD", "1", "power_in")],
                     attrs={"pin_specs": {"1": {"v_abs_max": 3.6}}}),
        SchComponent(ref="U2", pins=[Pin("OUT", "1", "power_out")]),
    ]
    sch.connect(rail, "U1.1", "U2.1")
    return sch.dumps()


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "main.sch").write_text(_sch("+3V3"), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "branch", "-M", "main")
    # variant A: harmless rename
    _git(tmp_path, "checkout", "-qb", "variant-clean")
    (tmp_path / "main.sch").write_text(
        _sch("+3V3").replace('"v"', '"v2"'), encoding="utf-8")
    _git(tmp_path, "commit", "-aqm", "rename")
    # variant B: rewires the rail to 5V — overvoltage introduced
    _git(tmp_path, "checkout", "-q", "main")
    _git(tmp_path, "checkout", "-qb", "variant-hot")
    (tmp_path / "main.sch").write_text(_sch("+5V"), encoding="utf-8")
    _git(tmp_path, "commit", "-aqm", "5V rail")
    _git(tmp_path, "checkout", "-q", "main")
    return tmp_path


def test_scoreboard_ranks_clean_variant_first(repo):
    board = score_branches(str(repo), "main")
    assert [r["branch"] for r in board["rows"]] == ["variant-clean", "variant-hot"]
    clean, hot = board["rows"]
    assert clean["gate"] == "PASS" and clean["introduced"] == 0
    assert hot["gate"] == "FAIL" and hot["introduced"] >= 1
    md = to_markdown(board)
    assert "| variant-hot | **FAIL** |" in md


def test_checks_endpoint_reports_violations(tmp_path):
    from gitcad.viewer.server import run_checks_for
    from gitcad.kernel import get_kernel

    p = tmp_path / "bad.sch"
    p.write_text(_sch("+5V"), encoding="utf-8")
    result = run_checks_for(p, get_kernel())
    assert result["kind"] == "schematic"
    assert not result["ok"]
    flat = [v for r in result["results"] for v in r["violations"]]
    assert any(v.startswith("pin-overvoltage:+5V:U1.1") for v in flat)
    checks_run = [r["check"] for r in result["results"]]
    assert checks_run == ["erc", "envelope"]


def test_client_ships_checks_tab():
    from gitcad.viewer.page import PAGE

    assert '"/api/checks"' in PAGE
    assert "checksState" in PAGE
    assert '"#checks"' in PAGE


def test_review_mode_endpoint_and_client(tmp_path):
    """gitcad-view --review BASE: the review tab, in-app."""
    import json as _json
    import threading
    import urllib.request

    from gitcad.viewer.server import serve

    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "main.sch").write_text(_sch("+3V3"), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "branch", "-M", "main")
    (tmp_path / "main.sch").write_text(_sch("+5V"), encoding="utf-8")
    _git(tmp_path, "commit", "-aqm", "hot rail")

    httpd = serve(str(tmp_path / "main.sch"), port=0, review_base="main~1")
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        version = _json.load(urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/version"))
        assert version["review_base"] == "main~1"
        report = _json.load(urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/review"))
        assert not report["gate_ok"]
        assert any(v.startswith("pin-overvoltage")
                   for f in report["files"]
                   for v in f["violations_introduced"])
    finally:
        httpd.shutdown()

    from gitcad.viewer.page import PAGE

    assert '"/api/review"' in PAGE and "loadReview" in PAGE
    assert "review_base" in PAGE
