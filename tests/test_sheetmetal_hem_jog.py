"""Sheet-metal hem (180° fold-back) + jog (Z-offset) — flat pattern + text."""

import math

from gitcad.sheetmetal import SheetMetal


def _sm():
    return SheetMetal(name="p", width=100, height=50, thickness=1.0,
                      k_factor=0.44, bend_radius=1.5)


def test_hem_flat_pattern_and_bend() -> None:
    sm = _sm().hem("n", 8, radius=1.5)
    assert sm.validate().ok
    fp = sm.flat_pattern()
    hem_bends = [b for b in fp["bends"] if b.get("hem")]
    assert len(hem_bends) == 1 and hem_bends[0]["angle"] == 180.0
    # flat growth beyond the north edge = BA(180°) + return = π(R+Kt) + 8
    ba = math.pi * (1.5 + 0.44 * 1.0)
    assert abs((fp["bbox"][3] - 50) - (ba + 8)) < 1e-9


def test_jog_is_two_opposite_bends() -> None:
    sm = _sm().jog("e", offset=5, run=20, angle=90)
    assert sm.validate().ok
    bt = sm.bend_table()
    assert len(bt) == 2
    assert all(b["angle"] == 90 for b in bt)
    assert bt[0]["direction"] != bt[1]["direction"]


def test_hem_survives_canonical_text() -> None:
    sm = _sm().hem("s", 6)
    back = SheetMetal.loads(sm.dumps())
    assert any(f.hem for f in back.flanges)
    assert back.flat_pattern()["bbox"] == sm.flat_pattern()["bbox"]


def test_hem_rejects_nonpositive_return() -> None:
    sm = _sm().hem("n", 0)
    assert not sm.validate().ok
