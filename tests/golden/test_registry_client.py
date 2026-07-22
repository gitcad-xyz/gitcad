"""GOLDEN: the git-backed registry client (Workspace.from_git, ADR-0010).

Uses a local git repo as the registry — same code path as GitHub, no network.
"""

from __future__ import annotations

import subprocess

import pytest

from gitcad.part import Frame, Interface, PartManifest, Port, Workspace, resolve


def _publish(repo, name: str, version: str, part_id: str) -> None:
    d = repo / "parts" / name / version
    d.mkdir(parents=True)
    m = PartManifest(
        id=part_id, name=name, domain="ecad", version=version,
        interface=Interface(frames={"m1": Frame(origin=(3, 3, 0))},
                            ports={"m1": Port("m1", "mech.bolt", "m1")}),
    )
    (d / "part.json").write_text(m.dumps(), newline="\n")


@pytest.fixture
def registry_repo(tmp_path):
    repo = tmp_path / "registry"
    repo.mkdir()
    _publish(repo, "widget", "1.0.0", "prt_0000000000000001")
    _publish(repo, "widget", "1.1.0", "prt_0000000000000001")
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"],
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    return repo


def test_from_git_clones_scans_and_resolves(registry_repo, tmp_path) -> None:
    ws = Workspace.from_git(str(registry_repo), cache_dir=str(tmp_path / "cache"))
    assert ws.versions_of("prt_0000000000000001") == ["1.0.0", "1.1.0"]

    consumer = PartManifest(id="prt_00000000000000cc", name="asm", domain="assembly",
                            version="0.1.0", deps={"prt_0000000000000001": "^1.0.0"})
    lock = resolve(consumer, ws)
    assert lock.locks["prt_0000000000000001"]["version"] == "1.1.0"
    assert lock.verify(ws) == []


def test_from_git_updates_existing_cache(registry_repo, tmp_path) -> None:
    cache = str(tmp_path / "cache")
    Workspace.from_git(str(registry_repo), cache_dir=cache)
    # Publish a new version upstream; a fresh from_git must see it.
    _publish(registry_repo, "widget", "1.2.0", "prt_0000000000000001")
    subprocess.run(["git", "add", "-A"], cwd=registry_repo, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "1.2.0"], cwd=registry_repo, check=True, capture_output=True)
    ws = Workspace.from_git(str(registry_repo), cache_dir=cache)
    assert "1.2.0" in ws.versions_of("prt_0000000000000001")
