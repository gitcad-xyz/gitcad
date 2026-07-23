"""SW-map P3: sheet metal — the flat pattern is the manufacturing truth.

The unfold math under test is the industry-standard hand calculation:
flat = L1 - OSSB + BA + L2 - OSSB with BA = θ(R + K·t) and
OSSB = (R + t)·tan(θ/2). Numbers below are chosen so the hand values
are exact: t=2, R=2, K=0.5, θ=90° → OSSB=4, BA=(π/2)·3."""

from __future__ import annotations

import math

import pytest

from gitcad.errors import GitcadError
from gitcad.kernel.null import NullKernel
from gitcad.sheetmetal import Flange, SheetMetal, SmHole

BA90 = math.pi / 2 * 3.0        # θ=90°, R=2, K=0.5, t=2
OSSB90 = 4.0                    # (R+t)·tan(45°)


def _bracket(**kw) -> SheetMetal:
    return SheetMetal(name="bracket", width=40, height=50,
                      thickness=2, k_factor=0.5, bend_radius=2, **kw)


def test_roundtrip_is_canonical() -> None:
    sm = _bracket(flanges=[Flange(edge="n", length=20,
                                  holes=[SmHole(u=20, v=12, diameter=5)])])
    sm2 = SheetMetal.loads(sm.dumps())
    assert sm2.dumps() == sm.dumps()
    assert sm2.flanges[0].holes[0].diameter == 5


def test_flat_pattern_matches_hand_calculation() -> None:
    sm = _bracket(flanges=[Flange(edge="n", length=20)])
    fp = sm.flat_pattern()
    minx, miny, maxx, maxy = fp["bbox"]
    # total flat height = 50 - OSSB + BA + 20 - OSSB
    assert maxy - miny == pytest.approx(50 - OSSB90 + BA90 + 20 - OSSB90)
    assert (minx, miny) == (0, 0)
    # bend centerline sits mid-strip: 50 - OSSB + BA/2
    (bend,) = fp["bends"]
    assert bend["p1"][1] == pytest.approx(50 - OSSB90 + BA90 / 2)
    assert bend["direction"] == "up" and bend["angle"] == 90.0


def test_chained_flange_loses_setback_at_both_ends() -> None:
    sm = _bracket(flanges=[Flange(edge="n", length=20,
                                  children=[Flange(edge="end", length=12)])])
    fp = sm.flat_pattern()
    _, miny, _, maxy = fp["bbox"]
    assert maxy - miny == pytest.approx(
        50 - OSSB90 + BA90 + (20 - 2 * OSSB90) + BA90 + 12 - OSSB90)
    assert len(fp["bends"]) == 2


def test_flange_hole_lands_at_flat_position() -> None:
    sm = _bracket(flanges=[Flange(edge="n", length=20,
                                  holes=[SmHole(u=15, v=12, diameter=5)])])
    fp = sm.flat_pattern()
    (hx, hy, d), = [h for h in fp["holes"]]
    assert hx == 15 and d == 5
    # strip end + (v - OSSB) = 50 - OSSB + BA + 12 - OSSB
    assert hy == pytest.approx(50 - OSSB90 + BA90 + 12 - OSSB90)


def test_dfm_violations_fail_loud() -> None:
    sm = _bracket(flanges=[Flange(edge="n", length=3)])          # < OSSB
    assert "flange-shorter-than-setback:base/n" in sm.validate().violations
    sm = _bracket(flanges=[Flange(edge="n", length=20, radius=1)])
    assert "bend-radius-below-thickness:base/n" in sm.validate().violations
    sm = _bracket(flanges=[Flange(edge="n", length=20,
                                  holes=[SmHole(u=5, v=5, diameter=3)])])
    assert any(v.startswith("hole-too-close-to-bend") for v in sm.validate().violations)
    sm = _bracket(flanges=[Flange(edge="n", length=20), Flange(edge="n", length=10)])
    assert "flange-duplicate-edge:n" in sm.validate().violations
    sm = _bracket(flanges=[Flange(edge="n", length=20,
                                  children=[Flange(edge="w", length=10)])])
    assert any("chained-flange-edge-not-end" in v for v in sm.validate().violations)
    with pytest.raises(GitcadError, match="validation"):
        _bracket(flanges=[Flange(edge="n", length=3)]).flat_pattern()


def test_dxf_layers_and_determinism() -> None:
    sm = _bracket(flanges=[Flange(edge="n", length=20, direction="up"),
                           Flange(edge="s", length=15, direction="down")],
                  base_holes=[SmHole(u=20, v=25, diameter=4)])
    dxf = sm.flat_dxf()
    for token in ("CUT", "BEND_UP", "BEND_DOWN", "HOLES", "CIRCLE", "AC1009"):
        assert token in dxf, token
    assert dxf == sm.flat_dxf()
    table = sm.bend_table()
    assert [b["edge"] for b in table] == ["n", "s"]
    assert table[1]["direction"] == "down"


def test_folded_solid_builds_as_ordinary_document() -> None:
    sm = _bracket(flanges=[Flange(edge="n", length=20,
                                  children=[Flange(edge="end", length=12)]),
                           Flange(edge="e", length=10)],
                  base_holes=[SmHole(u=20, v=25, diameter=4)])
    doc = sm.to_document()
    result = doc.build(NullKernel())
    assert doc.features[-1].id in result.shapes
    assert any(f.op == "hole" for f in doc.features)


@pytest.mark.occt
def test_folded_volume_is_sane() -> None:
    from gitcad.kernel.occt import OcctKernel

    sm = _bracket(flanges=[Flange(edge="n", length=20)])
    doc = sm.to_document()
    k = OcctKernel()
    result = doc.build(k)
    vol = k.mass_props(result.final(doc))["volume"]
    slabs = 40 * 50 * 2 + 40 * 20 * 2                 # base + flange, sharp
    # sharp-corner union: within one edge-overlap of the slab sum
    assert slabs - 40 * 2 * 2 <= vol <= slabs + 1e-6
