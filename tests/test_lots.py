"""Golden: fab-lot traceability — provenance that cannot be faked.

Behavioral oracles in a real throwaway git repo: a recorded lot pins the
HEAD commit and every artifact hash; tampering with one Gerber byte makes
verify name that exact file; a dirty worktree refuses to record (a lot
pinned to a commit that doesn't contain what shipped is provenance
theater); lots are immutable.
"""

import subprocess

import pytest

from gitcad.errors import GitcadError
from gitcad.lots import record_lot, verify_lot


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


@pytest.fixture()
def fab_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    rel = tmp_path / "release-0.1.0"
    rel.mkdir()
    (rel / "board.gtl").write_text("G04 top copper*\nM02*\n", encoding="utf-8")
    (rel / "board.drl").write_text("M48\nM30\n", encoding="utf-8")
    (rel / "release-manifest.json").write_text('{"version": "0.1.0"}',
                                              encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "release 0.1.0")
    return tmp_path


def test_lot_pins_commit_and_every_artifact(fab_repo):
    path = record_lot(str(fab_repo / "release-0.1.0"), "L7",
                      vendor="jlc", date="2026-07-23", quantity=50,
                      repo=str(fab_repo))
    r = verify_lot(path)
    assert r["ok"] and r["lot"] == "L7" and r["artifacts"] == 3
    assert len(r["commit"]) == 40                      # a real sha, bisectable


def test_tampered_gerber_is_named(fab_repo):
    path = record_lot(str(fab_repo / "release-0.1.0"), "L8", repo=str(fab_repo))
    (fab_repo / "release-0.1.0" / "board.gtl").write_text("EVIL*\n",
                                                          encoding="utf-8")
    r = verify_lot(path)
    assert not r["ok"]
    assert r["mismatched"] == ["board.gtl"]


def test_dirty_worktree_refuses_to_record(fab_repo):
    (fab_repo / "uncommitted.txt").write_text("wip", encoding="utf-8")
    with pytest.raises(GitcadError, match="dirty"):
        record_lot(str(fab_repo / "release-0.1.0"), "L9", repo=str(fab_repo))


def test_lots_are_immutable(fab_repo):
    record_lot(str(fab_repo / "release-0.1.0"), "L10", repo=str(fab_repo))
    _git(fab_repo, "add", "-A")
    _git(fab_repo, "commit", "-qm", "lot L10")
    with pytest.raises(GitcadError, match="immutable"):
        record_lot(str(fab_repo / "release-0.1.0"), "L10", repo=str(fab_repo))
