"""Golden: json-free extensions + gitcad init.

Extensions are legibility only — kind detection stays content-based, so a
schematic named main.sch reviews, discovers, and merges exactly like
main.schematic.json did. init scaffolds the whole anatomy in one command
and refuses to clobber an existing project.
"""

import subprocess

import pytest

from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.errors import GitcadError
from gitcad.init import init_project
from gitcad.review import review_range
from gitcad.viewer.server import discover_schematics


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


def _sch(value="10k") -> str:
    sch = Schematic(name="s")
    sch.components = [SchComponent(ref="R1", value=value,
                                   pins=[Pin("1", "1"), Pin("2", "2")])]
    sch.connect("A", "R1.1")
    sch.connect("B", "R1.2")
    return sch.dumps()


def test_init_scaffolds_everything(tmp_path):
    written = init_project(str(tmp_path / "widget"), name="widget")
    root = tmp_path / "widget"
    assert set(written) == {".gitattributes", ".github/workflows/gitcad.yml",
                            "README.md", "widget.gitcad", "requirements.reqs"}
    assert "*.gitcad merge=gitcad" in (root / ".gitattributes").read_text()
    assert "gitcad-verify requirements.reqs" in \
        (root / ".github/workflows/gitcad.yml").read_text()
    driver = subprocess.run(["git", "-C", str(root), "config",
                             "merge.gitcad.driver"],
                            capture_output=True, text=True)
    assert driver.stdout.strip() == "gitcad-merge %O %A %B"


def test_project_root_is_an_assembly_of_parts(tmp_path):
    # THE .gitcad file is the product: a top-level assembly manifest that
    # instances parts (mech + elec alike) — never a mech model document.
    from gitcad.part import PartManifest

    init_project(str(tmp_path / "widget"), name="widget")
    root_doc = PartManifest.loads(
        (tmp_path / "widget" / "widget.gitcad").read_text(encoding="utf-8"))
    assert root_doc.name == "widget"
    assert root_doc.body["kind"] == "assembly"
    assert root_doc.body["instances"] == {}          # ready for parts


def test_init_refuses_to_overwrite(tmp_path):
    init_project(str(tmp_path))
    with pytest.raises(GitcadError, match="refusing to overwrite"):
        init_project(str(tmp_path))


def test_dot_sch_files_are_discovered_for_review_ui(tmp_path):
    (tmp_path / "main.sch").write_text(_sch(), encoding="utf-8")
    sheets = discover_schematics(tmp_path)
    assert [s["file"] for s in sheets] == ["main.sch"]
    assert "<svg" in sheets[0]["svg"]


def test_dot_sch_files_flow_through_review(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "main.sch").write_text(_sch(), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "main.sch").write_text(_sch("22k"), encoding="utf-8")
    _git(tmp_path, "commit", "-aqm", "value change")
    report = review_range(str(tmp_path), "HEAD~1", "HEAD")
    assert [f["file"] for f in report["files"]] == ["main.sch"]
    assert report["files"][0]["kind"] == "schematic"


def test_lot_records_use_dot_lot(tmp_path):
    from gitcad.lots import record_lot, verify_lot

    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    rel = tmp_path / "release-0.1.0"
    rel.mkdir()
    (rel / "b.gtl").write_text("M02*\n", encoding="utf-8")
    (rel / "release-manifest.json").write_text('{"version": "0.1.0"}',
                                              encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "rel")
    path = record_lot(str(rel), "L1", repo=str(tmp_path))
    assert path.endswith("L1.lot")
    assert verify_lot(path)["ok"]
    # the lot record itself is never one of the hashed artifacts
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "lot")
    path2 = record_lot(str(rel), "L2", repo=str(tmp_path))
    r2 = verify_lot(path2)
    assert r2["ok"] and r2["artifacts"] == 2
