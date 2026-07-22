"""GOLDEN: copper connectivity — unrouted nets and geometric shorts."""

from __future__ import annotations

from gitcad.ecad import Board, Component, Footprint, Pad, Track, Via, check_connectivity


def _two_resistor_board() -> Board:
    fp = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95), Pad("2", 0.75, 0, 0.9, 0.95)])
    b = Board(name="c", outline=[(0, 0), (20, 0), (20, 10), (0, 10)])
    b.components += [Component("R1", fp, x=6, y=5, nets={"1": "A", "2": "B"}),
                     Component("R2", fp, x=14, y=5, nets={"1": "A", "2": "B"})]
    # A routed over the top, B under the bottom (touching their pads).
    b.tracks += [Track(5.25, 5, 5.25, 8, 0.3, "top", "A"),
                 Track(5.25, 8, 13.25, 8, 0.3, "top", "A"),
                 Track(13.25, 8, 13.25, 5, 0.3, "top", "A"),
                 Track(6.75, 5, 6.75, 2, 0.3, "top", "B"),
                 Track(6.75, 2, 14.75, 2, 0.3, "top", "B"),
                 Track(14.75, 2, 14.75, 5, 0.3, "top", "B")]
    return b


def test_fully_routed_board_is_connected() -> None:
    r = check_connectivity(_two_resistor_board())
    assert r.ok, r.violations


def test_missing_track_reports_unrouted_net() -> None:
    b = _two_resistor_board()
    del b.tracks[1]   # break net A's top run
    r = check_connectivity(b)
    assert any(v.startswith("net-unrouted:A") for v in r.violations)
    assert not any(v.startswith("net-unrouted:B") for v in r.violations)


def test_bridging_track_reports_short() -> None:
    b = _two_resistor_board()
    # A mislabeled track physically bridging the two nets' pads on R1.
    b.tracks.append(Track(5.25, 5, 6.75, 5, 0.3, "top", "A"))
    r = check_connectivity(b)
    assert any(v.startswith("net-short:A+B") for v in r.violations)


def test_layers_do_not_connect_without_a_via() -> None:
    b = Board(name="c", outline=[(0, 0), (20, 0), (20, 10), (0, 10)])
    fp = Footprint("H", pads=[Pad("1", 0, 0, 1.7, 1.7, "circle", 1.0)])
    b.components += [Component("J1", fp, x=4, y=5, nets={"1": "N"}),
                     Component("J2", fp, x=16, y=5, nets={"1": "N"})]
    # Top stub from J1, bottom stub to J2 — geometrically overlapping in XY
    # at x=10 but on different layers: still unrouted without a via.
    b.tracks += [Track(4, 5, 10, 5, 0.4, "top", "N"),
                 Track(10, 5, 16, 5, 0.4, "bottom", "N")]
    r = check_connectivity(b)
    assert any(v.startswith("net-unrouted:N") for v in r.violations)
    # Add the via at the junction: now connected (through pads span layers).
    b.vias.append(Via(10, 5, net="N"))
    assert check_connectivity(b).ok
