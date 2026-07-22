"""Golden: PR review packaging — the merge gate catches introduced violations.

Kernel-free: uses a real throwaway git repo. The oracle is behavioral —
committing a schematic edit that shorts 5V onto a 3.6V-max pin must flip
the gate to FAIL with the exact violation named as INTRODUCED, while a
pre-existing red on base must not block (not this PR's fault).
"""

import subprocess

import pytest

from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.review import review_range, to_html, to_markdown


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


def _sch(rail: str, extra_violation: bool = False) -> str:
    sch = Schematic(name="rev")
    sch.components = [
        SchComponent(ref="U1", value="MCU", pins=[Pin("VDD", "1", "power_in")],
                     attrs={"pin_specs": {"1": {"v_abs_max": 3.6, "i_draw_ma": 50}}}),
        SchComponent(ref="U2", value="LDO", pins=[Pin("OUT", "1", "power_out")],
                     attrs={"pin_specs": {"1": {"i_source_ma": 100}}}),
    ]
    sch.connect(rail, "U1.1", "U2.1")
    if extra_violation:   # a dangling single-pin net, red in ERC
        sch.components.append(SchComponent(ref="R9", pins=[Pin("1", "1")]))
        sch.connect("LONELY", "R9.1")
    return sch.dumps()


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "main.schematic.json").write_text(_sch("+3V3"), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "branch", "-M", "main")
    return tmp_path


def test_clean_edit_passes_gate(repo):
    (repo / "main.schematic.json").write_text(_sch("+3V3") + "\n", encoding="utf-8")
    _git(repo, "commit", "-aqm", "whitespace")
    report = review_range(str(repo), "main~1", "main")
    assert report["gate_ok"]


def test_introduced_overvoltage_fails_gate_with_named_violation(repo):
    (repo / "main.schematic.json").write_text(_sch("+5V"), encoding="utf-8")
    _git(repo, "commit", "-aqm", "rewire to 5V")
    report = review_range(str(repo), "main~1", "main")
    assert not report["gate_ok"]
    f = report["files"][0]
    assert f["violations_introduced"] == ["pin-overvoltage:+5V:U1.1:5>3.6"]
    md = to_markdown(report)
    assert "gate: FAIL" in md
    assert "pin-overvoltage" in md


def test_preexisting_red_does_not_block(repo):
    # base is ALREADY red (dangling net) — a rename PR must not be blamed
    (repo / "main.schematic.json").write_text(_sch("+3V3", extra_violation=True),
                                              encoding="utf-8")
    _git(repo, "commit", "-aqm", "introduce lonely net (base state)")
    (repo / "main.schematic.json").write_text(
        _sch("+3V3", extra_violation=True).replace('"MCU"', '"MCU2"'),
        encoding="utf-8")
    _git(repo, "commit", "-aqm", "rename value only")
    report = review_range(str(repo), "main~1", "main")
    assert report["gate_ok"]
    f = report["files"][0]
    assert f["violations_introduced"] == []
    assert "net-single-pin:LONELY" in f["violations_preexisting"]


def test_fixed_violations_are_celebrated(repo):
    (repo / "main.schematic.json").write_text(_sch("+3V3", extra_violation=True),
                                              encoding="utf-8")
    _git(repo, "commit", "-aqm", "red base")
    (repo / "main.schematic.json").write_text(_sch("+3V3"), encoding="utf-8")
    _git(repo, "commit", "-aqm", "fix the lonely net")
    report = review_range(str(repo), "main~1", "main")
    assert report["gate_ok"]
    assert report["summary"]["fixed"] >= 1


def test_html_report_embeds_side_by_side_renders(repo):
    (repo / "main.schematic.json").write_text(_sch("+5V"), encoding="utf-8")
    _git(repo, "commit", "-aqm", "rewire")
    html = to_html(review_range(str(repo), "main~1", "main"))
    assert html.count("<svg") >= 2          # base and head renders
    assert "FAIL" in html
