"""Golden: PCBA parts — mechanical outside, electrical workflow inside.

Kernel-free. Oracles: a board's derived .pcba part carries the mechanical
face (envelope, mech.bolt ports) AND the electrical references; the
pcba_verify gate runs the full electrical suite over those references and
catches a deliberately-broken parity; the viewer recognizes the kind.
"""

import pytest

from gitcad.ecad import Board, Component, Footprint, MountingHole, Pad
from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.errors import GitcadError
from gitcad.pcba import is_pcba, pcba_verify

FP = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                              Pad("2", 0.75, 0, 0.9, 0.95)])


def _board() -> Board:
    b = Board(name="blinky", outline=[(0, 0), (20, 0), (20, 12), (0, 12)])
    b.mounting_holes = [MountingHole("mh1", 2, 2, 2.2, thread="M2"),
                        MountingHole("mh2", 18, 10, 2.2, thread="M2")]
    b.components += [
        Component("R1", FP, x=6, y=6, nets={"1": "VCC", "2": "GND"}),
    ]
    return b


def _sch() -> Schematic:
    sch = Schematic(name="blinky")
    sch.components = [SchComponent(ref="R1", value="10k",
                                   pins=[Pin("1", "1"), Pin("2", "2")])]
    sch.connect("VCC", "R1.1")
    sch.connect("GND", "R1.2")
    return sch


@pytest.fixture()
def project(tmp_path):
    board = _board()
    (tmp_path / "blinky.board").write_text(board.dumps(), encoding="utf-8")
    (tmp_path / "blinky.sch").write_text(_sch().dumps(), encoding="utf-8")
    part = board.to_part("prt_pcba_0001", schematics=["blinky.sch"])
    (tmp_path / "blinky.pcba").write_text(part.dumps(), encoding="utf-8")
    return tmp_path


def test_pcba_part_is_mechanical_outside(project):
    from gitcad.part import PartManifest

    text = (project / "blinky.pcba").read_text(encoding="utf-8")
    assert is_pcba(text)
    part = PartManifest.loads(text)
    assert part.body == {"kind": "pcba", "board": "blinky.board",
                         "schematics": ["blinky.sch"]}
    assert part.interface.envelope["dx"] == 20        # outline bbox
    assert part.interface.ports["mh1"].type == "mech.bolt"


def test_entering_the_pcba_runs_the_electrical_suite(project):
    text = (project / "blinky.pcba").read_text(encoding="utf-8")
    r = pcba_verify(text, str(project))
    assert r["checks"]["schematics_checked"] == 1
    assert r["checks"]["blinky.sch:parity"] == "ok"
    # violations that DO exist are single-pin nets etc. from the tiny board;
    # parity/erc structure is what this asserts, not a clean tiny fixture
    assert "board:validate" in r["checks"]


def test_broken_parity_is_caught_inside(project):
    # rewire the schematic so pin nets disagree with the board
    sch = _sch()
    sch.nets = {"VCC": ["R1.2"], "GND": ["R1.1"]}     # swapped!
    (project / "blinky.sch").write_text(sch.dumps(), encoding="utf-8")
    text = (project / "blinky.pcba").read_text(encoding="utf-8")
    r = pcba_verify(text, str(project))
    assert not r["ok"]
    assert any(v.startswith("parity:blinky.sch:net-mismatch") for v in r["violations"])


def test_missing_board_fails_loud(project):
    (project / "blinky.board").unlink()
    text = (project / "blinky.pcba").read_text(encoding="utf-8")
    with pytest.raises(GitcadError, match="board file missing"):
        pcba_verify(text, str(project))


def test_viewer_recognizes_pcba_kind(project):
    from gitcad.viewer.server import detect_kind

    assert detect_kind((project / "blinky.pcba").read_text(encoding="utf-8")) == "pcba"
    # a non-pcba, non-assembly part manifest still refuses direct viewing
    from gitcad.part import bought_part

    with pytest.raises(ValueError, match="assembly and pcba"):
        detect_kind(bought_part("X", "Y", "prt_zzz").dumps())
