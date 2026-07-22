"""GOLDEN: cross-domain co-design — a mech bracket mates an ecad board.

The scenario the Part standard exists for: the board publishes mounting holes
as `mech.bolt` ports; the bracket publishes bosses as `mech.boss` ports; the
assembly declares the mates and validation checks type compatibility and
positional coincidence. Then the board revs with a moved hole — and both the
release gate and the assembly check catch it, mechanically.
"""

from __future__ import annotations

import pytest

from gitcad.part import (
    Assembly, Frame, Interface, PartManifest, Port, check_release,
)


def _board(hole2=(27.0, 17.0)) -> PartManifest:
    return PartManifest(
        id="prt_b0a4d0000000cafe", name="blinky", domain="ecad", version="1.0.0",
        interface=Interface(
            envelope={"origin": [0, 0, 0], "dx": 30, "dy": 20, "dz": 1.6},
            frames={"mnt_1": Frame(origin=(3, 3, 0)),
                    "mnt_2": Frame(origin=(hole2[0], hole2[1], 0))},
            ports={"mnt_1": Port("mnt_1", "mech.bolt", "mnt_1", {"thread": "M3"}),
                   "mnt_2": Port("mnt_2", "mech.bolt", "mnt_2", {"thread": "M3"})},
        ),
    )


def _bracket() -> PartManifest:
    return PartManifest(
        id="prt_facade0000000001", name="bracket", domain="mech", version="1.0.0",
        interface=Interface(
            envelope={"origin": [0, 0, 0], "dx": 60, "dy": 40, "dz": 8},
            frames={"boss_1": Frame(origin=(13, 13, 8)),
                    "boss_2": Frame(origin=(37, 27, 8))},
            ports={"boss_1": Port("boss_1", "mech.boss", "boss_1", {"thread": "M3"}),
                   "boss_2": Port("boss_2", "mech.boss", "boss_2", {"thread": "M3"})},
        ),
    )


def _product(board: PartManifest) -> Assembly:
    asm = Assembly("product")
    asm.add("bracket", _bracket())
    asm.add("board", board, translate=(10, 10, 8))   # board holes land on bosses
    asm.mate("board.mnt_1", "bracket.boss_1")
    asm.mate("board.mnt_2", "bracket.boss_2")
    return asm


def test_board_mates_bracket() -> None:
    report = _product(_board()).validate()
    assert report.ok, report.violations


def test_moved_hole_fails_the_mate_check() -> None:
    """The board revs; hole 2 moves 1.5mm. The assembly check catches the
    physical mismatch — this is co-design as machine verification."""
    report = _product(_board(hole2=(28.5, 17.0))).validate()
    assert not report.ok
    assert any(v.startswith("mate:position-mismatch:board.mnt_2") for v in report.violations)


def test_moved_hole_also_fails_the_release_gate() -> None:
    """...and the same rev cannot ship as a patch/minor: interface-semver
    requires MAJOR for a moved frame (ADR-0009)."""
    old, new = _board(), _board(hole2=(28.5, 17.0))
    assert check_release("1.0.0", "1.0.1", old.interface, new.interface)
    assert check_release("1.0.0", "1.1.0", old.interface, new.interface)
    assert check_release("1.0.0", "2.0.0", old.interface, new.interface) == []


def test_incompatible_port_types_rejected() -> None:
    board = _board()
    board.interface.ports["mnt_1"] = Port("mnt_1", "elec.pin", "mnt_1")
    report = _product(board).validate()
    assert any(v.startswith("mate:incompatible-types") for v in report.violations)


def test_assembly_envelope_unions_instances() -> None:
    manifest = _product(_board()).to_manifest("prt_00000000000000dd")
    env = manifest.interface.envelope
    assert env["dx"] == pytest.approx(60)      # bracket dominates X/Y
    assert env["dz"] == pytest.approx(9.6)     # bracket 8 + board 1.6 stacked
