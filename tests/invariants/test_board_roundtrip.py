"""INVARIANT: the board text form round-trips and is canonical (ADR-0004).

Same contract as the mechanical document: semantically equal boards serialize
byte-identically, and fab outputs are deterministic functions of the text.
"""

from __future__ import annotations

import pytest

from gitcad.ecad import Board, Component, Footprint, Pad, Track, Via
from gitcad.ecad import excellon, gerber

pytestmark = pytest.mark.invariant


def _board() -> Board:
    fp = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                                  Pad("2", 0.75, 0, 0.9, 0.95)], courtyard=(2.4, 1.4))
    b = Board(name="t", outline=[(0, 0), (20, 0), (20, 10), (0, 10)])
    b.components.append(Component("R1", fp, value="1k", x=10, y=5, nets={"1": "A", "2": "B"}))
    b.tracks.append(Track(1, 1, 19, 1, 0.4, "top", "A"))
    b.vias.append(Via(19, 5, net="B"))
    return b


def test_roundtrip_is_lossless_and_canonical() -> None:
    b = _board()
    text = b.dumps()
    assert Board.loads(text).dumps() == text
    assert b.dumps() == text  # repeat serialization is byte-stable


def test_fab_outputs_are_deterministic() -> None:
    """Two builds of the same board text yield byte-identical Gerbers/drills —
    the property that makes fab packages reproducible from a git tag."""
    a, b = _board(), Board.loads(_board().dumps())
    assert gerber.copper(a, "top") == gerber.copper(b, "top")
    assert gerber.profile(a) == gerber.profile(b)
    assert excellon.drills(a) == excellon.drills(b)
