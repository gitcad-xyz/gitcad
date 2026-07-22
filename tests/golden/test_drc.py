"""GOLDEN: the DRC engine — geometric rule checking on real board data."""

from __future__ import annotations

import pytest

from gitcad.ecad import Board, Component, Footprint, MountingHole, Pad, Rule, RulePack, Track, Via
from gitcad.ecad.drc import default_rules, run_drc
from gitcad.errors import GitcadError


def _clean_board() -> Board:
    fp = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                                  Pad("2", 0.75, 0, 0.9, 0.95)])
    b = Board(name="t", outline=[(0, 0), (30, 0), (30, 20), (0, 20)])
    b.components.append(Component("R1", fp, x=15, y=10, nets={"1": "A", "2": "B"}))
    b.tracks.append(Track(2, 5, 14.25, 10, 0.3, "top", "A"))
    b.vias.append(Via(2, 5, drill=0.4, diameter=0.8, net="A"))
    b.mounting_holes.append(MountingHole("mnt_1", 27, 17, 3.2))
    return b


def test_clean_board_passes_default_pack() -> None:
    r = run_drc(_clean_board())
    assert r.ok, r.violations
    assert r.checks["method"].startswith("aabb")


def test_clearance_violation_between_nets() -> None:
    b = _clean_board()
    # A track on net B passing 0.05mm from the net-A track.
    b.tracks.append(Track(2, 5.65, 14, 5.65, 0.3, "top", "B"))
    r = run_drc(b)
    assert any(v.startswith("clearance:track[0]<->track[1]") for v in r.violations)


def test_same_net_copper_is_not_flagged() -> None:
    b = _clean_board()
    b.tracks.append(Track(2, 5.2, 14, 5.2, 0.3, "top", "A"))  # same net, touching-ish
    assert run_drc(b).ok


def test_opposite_layers_do_not_interact() -> None:
    b = _clean_board()
    # Overlaps the net-A TOP track in XY, but routed on the bottom layer —
    # and clear of the via (which spans both layers).
    b.tracks.append(Track(6, 6.5, 14, 9.8, 0.3, "bottom", "B"))
    assert run_drc(b).ok, run_drc(b).violations


def test_vias_span_both_layers() -> None:
    b = _clean_board()
    # A bottom-layer track through the (both-layer) via IS a violation.
    b.tracks.append(Track(1, 5, 5, 5, 0.3, "bottom", "B"))
    r = run_drc(b)
    assert any(v.startswith("clearance:") and "via[0]" in v for v in r.violations)


def test_track_width_and_annular_ring_and_drill() -> None:
    b = _clean_board()
    b.tracks.append(Track(5, 15, 10, 15, 0.05, "top", "C"))         # too thin
    b.vias.append(Via(25, 5, drill=0.6, diameter=0.7, net="C"))     # ring 0.05
    b.vias.append(Via(25, 10, drill=0.2, diameter=0.8, net="C"))    # drill too small
    r = run_drc(b)
    assert any(v.startswith("track-width:track[1]") for v in r.violations)
    assert any(v.startswith("annular-ring:via[1]") for v in r.violations)
    assert any(v.startswith("drill-size:via[2]") for v in r.violations)


def test_hole_to_hole_spacing() -> None:
    b = _clean_board()
    b.mounting_holes.append(MountingHole("mnt_2", 27.5, 17, 1.0))  # 0.5mm from mnt_1 edge-ish
    r = run_drc(b)
    assert any(v.startswith("hole-to-hole:") for v in r.violations)


def test_edge_clearance() -> None:
    b = _clean_board()
    b.tracks.append(Track(0.1, 10, 5, 10, 0.3, "top", "D"))
    r = run_drc(b)
    assert any(v.startswith("edge-clearance:track[1]") for v in r.violations)


def test_scoped_rule_tightens_one_net() -> None:
    """A net-scoped rule overrides the global one for that net only."""
    b = _clean_board()
    b.tracks.append(Track(5, 15, 10, 15, 0.2, "top", "HV"))  # 0.2 > global 0.15 min
    pack = default_rules()
    pack.rules.append(Rule("hv-width", "track_width", {"min": 0.5}, scope="HV"))
    r = run_drc(b, pack)
    assert any(v.startswith("track-width:track[1]") for v in r.violations)
    # ...and the net-A track (0.3mm) is untouched by the HV rule.
    assert not any("track[0]" in v for v in r.violations)


def test_rulepack_roundtrips_canonically() -> None:
    pack = default_rules()
    text = pack.dumps()
    assert RulePack.loads(text).dumps() == text


def test_unknown_rule_type_rejected() -> None:
    with pytest.raises(GitcadError):
        Rule("bad", "levitation", {"min": 1})
