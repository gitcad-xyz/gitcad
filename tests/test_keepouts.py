"""Golden: keepout areas + courtyard overlap (KiCad-map P2).

Kernel-free. Oracles: copper crossing a keepout is a named violation per
kind (track/via/zone); copper OUTSIDE it stays green; keepouts never emit
to Gerber and never join the copper item set; two overlapping same-side
courtyards flag, opposite sides don't.
"""

from gitcad.ecad import Board, Component, Footprint, Pad, Track, Via, Zone
from gitcad.ecad.drc import run_drc
from gitcad.ecad.gerber import copper

FP = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                              Pad("2", 0.75, 0, 0.9, 0.95)],
               courtyard=(2.4, 1.4))


def _board() -> Board:
    b = Board(name="b", outline=[(0, 0), (40, 0), (40, 20), (0, 20)])
    b.zones.append(Zone(net="", layer="top", kind="keepout",
                        polygon=[(10, 5), (20, 5), (20, 15), (10, 15)]))
    return b


def test_track_through_keepout_flags_and_outside_does_not():
    b = _board()
    b.tracks += [Track(5, 10, 25, 10, 0.2, "top", "SIG"),    # crosses keepout
                 Track(5, 2, 25, 2, 0.2, "top", "OK")]       # clear of it
    r = run_drc(b)
    keep = [v for v in r.violations if v.startswith("keepout")]
    assert keep == ["keepout:track:track[0]:zone[0]"]


def test_via_and_copper_zone_in_keepout_flag():
    b = _board()
    b.vias.append(Via(x=15, y=10, diameter=0.6, drill=0.3, net="SIG"))
    b.zones.append(Zone(net="GND", layer="top", kind="copper",
                        polygon=[(12, 7), (18, 7), (18, 13), (12, 13)]))
    r = run_drc(b)
    keep = sorted(v for v in r.violations if v.startswith("keepout"))
    assert keep == ["keepout:via:via[0]:zone[0]", "keepout:zone:zone[1]:zone[0]"]


def test_bottom_layer_copper_ignores_top_keepout():
    b = _board()
    b.tracks.append(Track(5, 10, 25, 10, 0.2, "bottom", "SIG"))
    assert not [v for v in run_drc(b).violations if v.startswith("keepout")]


def test_keepouts_never_emit_gerber_copper():
    b = _board()
    assert "G36*" not in copper(b, "top")            # no filled region
    b.zones.append(Zone(net="GND", layer="top", kind="copper",
                        polygon=[(30, 2), (38, 2), (38, 8), (30, 8)]))
    assert copper(b, "top").count("G36*") == 1       # only the copper pour


def test_keepout_with_net_is_a_validation_error():
    b = _board()
    b.zones[0].net = "GND"
    assert "keepout-with-net:0" in b.validate().violations


def test_roundtrip_preserves_kind():
    b = _board()
    again = Board.loads(b.dumps())
    assert again.zones[0].kind == "keepout"


def test_courtyard_overlap_same_side_only():
    b = Board(name="c", outline=[(0, 0), (40, 0), (40, 20), (0, 20)])
    b.components += [
        Component("R1", FP, x=10, y=10),
        Component("R2", FP, x=11, y=10),                 # 1mm apart, 2.4 wide
        Component("R3", FP, x=30, y=10),                 # far away
        Component("R4", FP, x=10.5, y=10, side="bottom"),  # other side
    ]
    r = run_drc(b)
    cy = [v for v in r.violations if v.startswith("courtyard-overlap")]
    assert cy == ["courtyard-overlap:R1<->R2"]
