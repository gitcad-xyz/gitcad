"""Golden: net classes (KiCad-map P1) — named net groups binding DRC rules.

Kernel-free. Oracles: a "power" class demanding 0.5 mm tracks flags a
0.2 mm VCC track that passes the default pack; glob patterns scope whole
families (SPI_*); class clearances override defaults for matching nets
only; structure errors are named at validation.
"""

from gitcad.ecad import Board, Component, Footprint, Pad, Track
from gitcad.ecad.drc import expand_net_classes, run_drc

FP = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                              Pad("2", 0.75, 0, 0.9, 0.95)])


def _board(**classes) -> Board:
    b = Board(name="b", outline=[(0, 0), (30, 0), (30, 20), (0, 20)])
    b.components += [Component("R1", FP, x=5, y=10, nets={"1": "VCC", "2": "SIG"}),
                     Component("R2", FP, x=25, y=10, nets={"1": "SPI_CLK", "2": "GND"})]
    b.net_classes = dict(classes)
    return b


def test_class_track_width_overrides_default_for_its_nets():
    b = _board(power={"nets": ["VCC", "GND"], "track_width_min": 0.5})
    # 0.2mm passes the default pack (0.15) but not the power class
    b.tracks += [Track(5, 3, 10, 3, 0.2, "top", "VCC"),      # track[0]
                 Track(5, 17, 10, 17, 0.2, "top", "SIG")]    # track[1]
    r = run_drc(b)
    width = [v for v in r.violations if v.startswith("track-width")]
    assert width == ["track-width:track[0]:w=0.2mm<0.5mm"]   # VCC only, class limit


def test_glob_pattern_scopes_a_net_family():
    b = _board(spi={"nets": ["SPI_*"], "track_width_min": 0.4})
    b.tracks += [Track(20, 3, 24, 3, 0.2, "top", "SPI_CLK")]
    r = run_drc(b)
    assert "track-width:track[0]:w=0.2mm<0.4mm" in r.violations


def test_expansion_produces_scoped_rules():
    b = _board(power={"nets": ["VCC"], "clearance": 0.4, "track_width_min": 0.5})
    rules = expand_net_classes(b)
    assert {r.type for r in rules} == {"clearance", "track_width"}
    assert all(r.scope == "VCC" for r in rules)
    assert all(r.name.startswith("class-power-") for r in rules)


def test_no_classes_changes_nothing():
    b = _board()
    assert expand_net_classes(b) == []
    assert run_drc(b).ok


def test_classes_roundtrip_canonical():
    b = _board(power={"nets": ["VCC"], "clearance": 0.3})
    again = Board.loads(b.dumps())
    assert again.net_classes == {"power": {"nets": ["VCC"], "clearance": 0.3}}


def test_structure_errors_named_at_validation():
    b = _board(bad={"nets": [], "sparkle": 3},
               worse={"nets": ["VCC"], "clearance": -1})
    r = b.validate()
    assert "netclass-empty-nets:bad" in r.violations
    assert "netclass-unknown-param:bad:sparkle" in r.violations
    assert "netclass-bad-value:worse:clearance" in r.violations
