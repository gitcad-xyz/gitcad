"""GOLDEN: release machinery + semantic diff (the git-native completion)."""

from __future__ import annotations

import json

import pytest

from gitcad.document import Document, Feature
from gitcad.ecad import Board, Component, Footprint, Pad, Pin, SchComponent, Schematic, Track
from gitcad.release import semantic_diff


def _model() -> Document:
    d = Document()
    d.add(Feature(op="box", params={"dx": 30, "dy": 20, "dz": 5}))
    return d


def _sch() -> Schematic:
    s = Schematic(name="b")
    s.components.append(SchComponent("R1", value="1k", footprint="R0603", pins=[
        Pin("1", "1", "passive"), Pin("2", "2", "passive")]))
    s.connect("A", "R1.1")
    s.connect("B", "R1.2")
    # single-pin nets are ERC violations; wire them to a second component
    s.components.append(SchComponent("R2", value="1k", footprint="R0603", pins=[
        Pin("1", "1", "passive"), Pin("2", "2", "passive")]))
    s.connect("A", "R2.1")
    s.connect("B", "R2.2")
    return s


def _board() -> Board:
    fp = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95), Pad("2", 0.75, 0, 0.9, 0.95)])
    b = Board(name="relboard", outline=[(0, 0), (20, 0), (20, 10), (0, 10)])
    b.components += [Component("R1", fp, x=6, y=5, nets={"1": "A", "2": "B"}),
                     Component("R2", fp, x=14, y=5, nets={"1": "A", "2": "B"})]
    # A: R1.1 (5.25,5) -> R2.1 (13.25,5) over the top; B: R1.2 (6.75,5) ->
    # R2.2 (14.75,5) under the bottom — routed to the pads their nets declare.
    b.tracks += [Track(5.25, 5, 5.25, 8, 0.3, "top", "A"),
                 Track(5.25, 8, 13.25, 8, 0.3, "top", "A"),
                 Track(13.25, 8, 13.25, 5, 0.3, "top", "A"),
                 Track(6.75, 5, 6.75, 2, 0.3, "top", "B"),
                 Track(6.75, 2, 14.75, 2, 0.3, "top", "B"),
                 Track(14.75, 2, 14.75, 5, 0.3, "top", "B")]
    return b


# -- semantic diff (null-kernel friendly) -------------------------------------

def test_semantic_diff_model_features() -> None:
    old = _model()
    new = Document.loads(old.dumps())
    added = new.add(Feature(op="sphere", params={"radius": 3}))
    d = semantic_diff(old.dumps(), new.dumps())
    assert d["kind"] == "document"
    assert [f["id"] for f in d["features_added"]] == [added]
    assert d["features_removed"] == [] and not d["identical"]


def test_semantic_diff_part_bump() -> None:
    from gitcad.part import Frame, Interface, PartManifest, Port

    old = PartManifest(id="prt_0000000000000001", name="p", domain="mech", version="1.0.0",
                       interface=Interface(frames={"m": Frame(origin=(1, 1, 0))},
                                           ports={"m": Port("m", "mech.bolt", "m")}))
    new = PartManifest.loads(old.dumps())
    new.interface.frames["m"] = Frame(origin=(2, 1, 0))
    d = semantic_diff(old.dumps(), new.dumps())
    assert d["kind"] == "part" and d["required_bump"] == "major"


def test_semantic_diff_board_deltas() -> None:
    old, new = _board(), _board()
    new.components.pop()
    d = semantic_diff(old.dumps(), new.dumps())
    assert d["components_removed"] == ["R2"]


# -- release (needs OCCT for model artifacts) ---------------------------------

@pytest.mark.occt
def test_release_all_green_produces_artifacts(tmp_path) -> None:
    from gitcad.release import release

    m = tmp_path / "part.gitcad.json"
    m.write_text(_model().dumps(), newline="\n")
    b = tmp_path / "board.gitcad.json"
    b.write_text(_board().dumps(), newline="\n")
    s = tmp_path / "sch.gitcad.json"
    s.write_text(_sch().dumps(), newline="\n")

    r = release([str(m), str(b), str(s)], str(tmp_path / "rel"), "1.0.0")
    assert r.ok, r.failures
    assert "part.step" in r.artifacts and "part.pdf" in r.artifacts
    assert any(k.startswith("board-fab/") and k.endswith(".gtl") for k in r.artifacts)
    manifest = json.loads((tmp_path / "rel" / "release-manifest.json").read_text())
    assert manifest["version"] == "1.0.0"
    assert set(manifest["artifacts"]) == set(r.artifacts)
    assert r.checks[f"parity:{s.name}<->{b.name}"] == "ok"


@pytest.mark.occt
def test_release_refuses_on_any_red_check(tmp_path) -> None:
    from gitcad.release import release

    bad = _board()
    bad.tracks.append(Track(0.05, 2, 5, 2, 0.05, "top", "X"))   # width + edge DRC violations
    b = tmp_path / "board.gitcad.json"
    b.write_text(bad.dumps(), newline="\n")
    r = release([str(b)], str(tmp_path / "rel"), "1.0.0")
    assert not r.ok
    assert any(":drc:" in f for f in r.failures)
    assert not (tmp_path / "rel" / "release-manifest.json").exists()   # no artifacts on red
