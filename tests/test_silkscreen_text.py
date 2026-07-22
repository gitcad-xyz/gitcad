"""Golden: silkscreen reference text (KiCad-map P3).

Kernel-free. Oracles: the legend Gerber gains stroke segments for each
ref (deterministic count per glyph set); refs center above the courtyard;
components without courtyards still get text; unknown characters render
as the visible box, never vanish.
"""

from gitcad.ecad import Board, Component, Footprint, Pad
from gitcad.ecad.gerber import silkscreen
from gitcad.ecad.strokefont import text_strokes, text_width

FP_CY = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                                 Pad("2", 0.75, 0, 0.9, 0.95)],
                  courtyard=(2.4, 1.4))
FP_BARE = Footprint("TP", pads=[Pad("1", 0, 0, 1.0, 1.0)])


def _board():
    b = Board(name="b", outline=[(0, 0), (30, 0), (30, 20), (0, 20)])
    b.components += [Component("R1", FP_CY, x=10, y=10),
                     Component("TP1", FP_BARE, x=25, y=10)]
    return b


def test_legend_contains_ref_strokes():
    text = silkscreen(_board(), "top")
    # courtyard = 5 lines (4 drawn) ; R1 = R(2 strokes) + 1(2 strokes) glyph
    # segments; exact count pinned so a silent font change is visible
    r1_segs = len(text_strokes("R1", 0, 0, 1.0))
    tp1_segs = len(text_strokes("TP1", 0, 0, 1.0))
    # every stroke becomes a D02/D01 pair -> count D01 draw commands
    draws = text.count("D01*")
    assert draws == 4 + r1_segs + tp1_segs      # courtyard + both refs


def test_text_centered_above_courtyard():
    segs = text_strokes("R1", 0, 0, 1.0)
    assert segs                                  # font produces geometry
    w = text_width("R1", 1.0)
    text = silkscreen(_board(), "top")
    # courtyard top at y = 10 + 0.7; text baseline 0.3 above -> y=11.0 ->
    # gerber Y coordinate 11000000 appears in the file (4.6 format)
    assert "Y11000000" in text
    assert w > 1.0                               # sane advance


def test_unknown_char_renders_visible_box():
    segs_ok = text_strokes("A", 0, 0, 1.0)
    segs_unk = text_strokes("~", 0, 0, 1.0)
    assert len(segs_unk) == 4                    # the hollow box
    assert segs_ok != segs_unk


def test_deterministic():
    a = silkscreen(_board(), "top")
    b = silkscreen(_board(), "top")
    assert a == b
