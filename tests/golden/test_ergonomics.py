"""GOLDEN: the dogfood-friction ergonomics release — every finding, fixed."""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.ecad import (
    Board, Component, Footprint, MountingHole, Pad, Track,
    check_connectivity, pad_position, route, run_drc,
)
from gitcad.errors import GitcadError
from gitcad.select import select_entities


def _altair_board() -> Board:
    HDR2 = Footprint("HDR-2P-2.54", pads=[
        Pad("1", 0, -1.27, 1.7, 1.7, "circle", 1.0), Pad("2", 0, 1.27, 1.7, 1.7, "circle", 1.0)])
    QFN = Footprint("QFN8-REP", pads=[
        Pad("1", -3.0, 1.0, 1.2, 0.8), Pad("2", -3.0, -1.0, 1.2, 0.8),
        Pad("3", 3.0, 1.0, 1.2, 0.8), Pad("4", 3.0, -1.0, 1.2, 0.8)], courtyard=(8, 5))
    b = Board(name="altair-main", outline=[(0, 0), (80, 0), (80, 50), (0, 50)])
    b.components += [
        Component("J1", HDR2, value="BATT", x=6, y=25, nets={"1": "3V3", "2": "GND"}),
        Component("U1", QFN, value="ESP32-S3", x=30, y=25,
                  nets={"1": "3V3", "2": "GND", "3": "SCLK", "4": "MOSI"}),
        Component("U2", QFN, value="ADS1220", x=58, y=25,
                  nets={"1": "3V3", "2": "GND", "3": "SCLK", "4": "MOSI"}),
    ]
    b.mounting_holes += [MountingHole(f"mnt_{i+1}", x, y, 2.7, thread="M2.5")
                         for i, (x, y) in enumerate(((4, 4), (76, 4), (76, 46), (4, 46)))]
    return b


# -- pad_position + route (friction #1, #8, #9) -------------------------------

def test_pad_position_resolves_absolute_coords() -> None:
    b = _altair_board()
    p = pad_position(b, "U1.3")
    assert (p["x"], p["y"]) == (33.0, 26.0)
    assert p["side"] == "top" and not p["through"] and p["net"] == "SCLK"
    assert pad_position(b, "J1.1")["through"] is True


def test_route_refuses_wrong_net_pad() -> None:
    b = _altair_board()
    with pytest.raises(GitcadError, match="wrong pad"):
        route(b, "SCLK", [{"pad": "U1.3"}, {"pad": "U2.4"}])   # U2.4 is MOSI


def test_route_enforces_smd_side() -> None:
    b = _altair_board()
    with pytest.raises(GitcadError, match="SMD pad"):
        route(b, "SCLK", [{"pad": "U1.3", "layer": "bottom"}, {"pad": "U2.3"}])


def test_route_auto_via_on_layer_change() -> None:
    b = _altair_board()
    r = route(b, "SCLK", [{"pad": "U1.3"},
                          {"x": 38, "y": 26},
                          {"x": 66, "y": 26, "layer": "bottom"},
                          {"x": 66, "y": 26, "layer": "top"},
                          {"pad": "U2.3"}])
    assert r["vias"] == 2   # down at (66,26)? — one per change
    # (change to bottom at wp3, back to top at wp4)


def test_route_rebuilds_the_altair_board_in_a_fraction_of_the_code() -> None:
    """THE proof: what took ~25 hand-computed tracks and five caught errors in
    the dogfood is now four route() calls — and passes every check first try."""
    b = _altair_board()
    route(b, "3V3", [{"pad": "J1.1"}, {"x": 6, "y": 18}, {"x": 22, "y": 18},
                     {"x": 22, "y": 30}, {"x": 27, "y": 30}, {"pad": "U1.1"}], width=0.5)
    route(b, "3V3", [{"x": 27, "y": 30}, {"x": 55, "y": 30}, {"pad": "U2.1"}], width=0.5)
    route(b, "GND", [{"pad": "J1.2", "layer": "bottom"}, {"x": 6, "y": 34, "layer": "bottom"},
                     {"x": 24, "y": 34, "layer": "bottom"}, {"x": 24, "y": 24, "layer": "bottom"},
                     {"x": 24, "y": 24, "layer": "top"}, {"pad": "U1.2"}], width=0.5)
    route(b, "GND", [{"x": 24, "y": 24, "layer": "bottom"}, {"x": 58, "y": 24, "layer": "bottom"},
                     {"x": 58, "y": 24, "layer": "top"}, {"pad": "U2.2"}], width=0.5)
    route(b, "SCLK", [{"pad": "U1.3"}, {"x": 38, "y": 26},
                      {"x": 38, "y": 26, "layer": "bottom"},
                      {"x": 66, "y": 26, "layer": "bottom"},
                      {"x": 66, "y": 26, "layer": "top"}, {"pad": "U2.3"}])
    route(b, "MOSI", [{"pad": "U1.4"}, {"x": 35, "y": 24}, {"x": 35, "y": 16},
                      {"x": 61, "y": 16}, {"pad": "U2.4"}])
    assert b.validate().ok, b.validate().violations
    assert run_drc(b).ok, run_drc(b).violations
    assert check_connectivity(b).ok, check_connectivity(b).violations


# -- degenerate track gate (friction: zero-length slipped through) ------------

def test_degenerate_track_caught_by_fab_gate() -> None:
    b = _altair_board()
    b.tracks.append(Track(10, 10, 10, 10, 0.4, "top", "X"))
    assert "track-degenerate:0" in b.validate().violations


# -- select DSL (friction: manual centroid filtering) -------------------------

@pytest.mark.occt
def test_select_dsl_picks_the_back_face() -> None:
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    faces = k.entities(k.box(92, 62, 30), "face")
    picks = select_entities(faces, "plane,zmax")
    assert len(picks) == 1
    assert faces[picks[0]]["centroid"][2] == pytest.approx(30)
    assert len(select_entities(faces, "area_max")) == 2   # top+bottom tie at 92x62 (ties kept by design)
    assert len(select_entities(faces, "area_max,zmax")) == 1   # ...and compose to disambiguate
    assert select_entities(faces, "cylinder") == []


# -- axis-aligned cylinders (friction: rotation sign archaeology) -------------

@pytest.mark.occt
def test_cylinder_axis_param() -> None:
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    doc = Document()
    doc.add(Feature(op="cylinder", params={"radius": 9.3, "height": 65, "axis": "y"}))
    (lo, hi) = k.bbox(doc.build(k).final(doc))
    assert hi[1] - lo[1] == pytest.approx(65, abs=1e-4)    # length along Y
    assert hi[0] - lo[0] == pytest.approx(18.6, abs=1e-4)  # diameter across X


# -- boss feature (friction: ports with no geometry) --------------------------

@pytest.mark.occt
def test_boss_with_pilot_volume_oracle() -> None:
    import math

    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    doc = Document()
    plate = doc.add(Feature(op="box", params={"dx": 30, "dy": 30, "dz": 3}))
    doc.add(Feature(op="boss", params={"x": 15, "y": 15, "base_z": 3, "height": 6,
                                       "diameter": 8, "pilot_diameter": 2.5,
                                       "pilot_depth": 5}, inputs=[plate]))
    v = k.measure(doc.build(k).final(doc))["volume"]
    expected = 30 * 30 * 3 + math.pi * 16 * 6 - math.pi * 1.25**2 * 5
    assert v == pytest.approx(expected, rel=1e-6)


# -- missing-inputs guard (friction: silent disconnected features) ------------

def test_subtractive_op_without_inputs_fails_loudly() -> None:
    from gitcad.kernel.null import NullKernel

    doc = Document()
    doc.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 10}))
    doc.add(Feature(op="hole", params={"x": 5, "y": 5, "top_z": 10,
                                       "diameter": 3, "depth": 10}))   # no inputs!
    with pytest.raises(GitcadError, match="requires inputs"):
        doc.build(NullKernel())


# -- board_to_model bridge (friction: hand-extruded board body) ---------------

@pytest.mark.occt
def test_board_to_model_bridge() -> None:
    import math

    from gitcad.bridge import board_to_model
    from gitcad.kernel.occt import OcctKernel

    k = OcctKernel()
    bare_expected = 80 * 50 * 1.6 - 4 * math.pi * 1.35**2 * 1.6
    doc = board_to_model(_altair_board(), components=False)
    v = k.measure(doc.build(k).final(doc))["volume"]
    assert v == pytest.approx(bare_expected, rel=1e-6)
    # populated (default): IDF-style component envelopes ADD volume — the
    # board's real mechanical shape for enclosure interference checks
    populated = board_to_model(_altair_board())
    vp = k.measure(populated.build(k).final(populated))["volume"]
    assert vp > v
