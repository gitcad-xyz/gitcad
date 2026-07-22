"""Golden: forward annotation — schematic nets pushed onto board pads.

Kernel-free. The writer half of the ECO loop (board_parity is the verifier):
matched refs get their pad nets from the schematic; every mismatch is
reported, and conflicting existing assignments are never silently
overwritten.
"""

from gitcad.ecad import Board, Component, Footprint, Pad
from gitcad.ecad.schematic import Pin, SchComponent, Schematic, board_parity
from gitcad.ecad.sync import annotate_board

FP = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                              Pad("2", 0.75, 0, 0.9, 0.95)])


def _sch():
    sch = Schematic(name="s")
    sch.components = [
        SchComponent(ref="R1", pins=[Pin("1", "1"), Pin("2", "2")]),
        SchComponent(ref="R2", pins=[Pin("1", "1"), Pin("2", "2")]),
        SchComponent(ref="U9", pins=[Pin("1", "1")]),        # not on board
    ]
    sch.connect("VCC", "R1.1", "U9.1")
    sch.connect("MID", "R1.2", "R2.1")
    sch.connect("GND", "R2.2")
    return sch


def _board(**r1_nets):
    b = Board(name="b", outline=[(0, 0), (20, 0), (20, 10), (0, 10)])
    b.components += [Component("R1", FP, x=5, y=5, nets=dict(r1_nets)),
                     Component("R2", FP, x=15, y=5),
                     Component("TP1", FP, x=10, y=8)]        # not in schematic
    return b


def test_annotation_writes_nets_and_reports_mismatches():
    board, sch = _board(), _sch()
    report = annotate_board(board, sch)
    r1 = next(c for c in board.components if c.ref == "R1")
    r2 = next(c for c in board.components if c.ref == "R2")
    assert r1.nets == {"1": "VCC", "2": "MID"}
    assert r2.nets == {"1": "MID", "2": "GND"}
    assert report.annotated_pins == 4
    assert report.refs_missing_on_board == ["U9"]
    assert report.refs_missing_in_schematic == ["TP1"]
    assert not report.clean          # mismatches present — reported, not hidden


def test_annotated_board_passes_parity_for_shared_refs():
    board, sch = _board(), _sch()
    annotate_board(board, sch)
    parity = board_parity(sch, board)
    # only component-level mismatches remain (U9/TP1); no net mismatches
    assert all(v.startswith("component-missing") for v in parity.violations)


def test_conflicts_reported_never_silently_overwritten():
    board, sch = _board(**{"1": "WRONG_NET"}), _sch()
    report = annotate_board(board, sch)
    r1 = next(c for c in board.components if c.ref == "R1")
    assert r1.nets["1"] == "WRONG_NET"                 # untouched
    assert report.conflicts == ["R1.1:WRONG_NET!=VCC"]

    board2 = _board(**{"1": "WRONG_NET"})
    report2 = annotate_board(board2, _sch(), overwrite_conflicts=True)
    r1b = next(c for c in board2.components if c.ref == "R1")
    assert r1b.nets["1"] == "VCC"                      # explicit opt-in only
    assert report2.conflicts == ["R1.1:WRONG_NET!=VCC"]


def test_matching_existing_nets_are_not_conflicts():
    board = _board(**{"1": "VCC"})
    report = annotate_board(board, _sch())
    assert report.conflicts == []
    assert report.annotated_pins == 4
