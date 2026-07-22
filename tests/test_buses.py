"""Golden: buses (KiCad-map tier 2) — visual groups, label-unified members.

KiCad semantics: a bus is drawing, not copper — member connectivity comes
from same-named labels on the wires tapping it, which the shared engine
already unifies by name. Oracles: an imported bus stops being "dropped",
renders blue and thick, and two D3-labeled taps land on ONE net.
"""

from gitcad.ecad.schsvg import sheet_to_svg
from gitcad.ecad.sheetedit import SheetEditor
from gitcad.importers.kicad_sch import import_kicad_sch

BUS_SHEET = """
(kicad_sch (version 20250114) (generator "test")
  (lib_symbols
    (symbol "Device:R"
      (symbol "R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27) (name "~") (number "1"))
        (pin passive line (at 0 -3.81 90) (length 1.27) (name "~") (number "2")))))
  (symbol (lib_id "Device:R") (at 100 100 0)
    (property "Reference" "R1" (at 0 0 0)) (property "Value" "1k" (at 0 0 0)))
  (symbol (lib_id "Device:R") (at 140 100 0)
    (property "Reference" "R2" (at 0 0 0)) (property "Value" "1k" (at 0 0 0)))
  (bus (pts (xy 90 80) (xy 150 80)))
  (bus_entry (at 100 82.54) (size 2.54 -2.54))
  (bus_entry (at 140 82.54) (size 2.54 -2.54))
  (wire (pts (xy 100 96.19) (xy 100 82.54)))
  (wire (pts (xy 140 96.19) (xy 140 82.54)))
  (label "D3" (at 100 90 0))
  (label "D3" (at 140 90 0))
)
"""


def test_bus_members_unify_by_label(tmp_path):
    p = tmp_path / "bus.kicad_sch"
    p.write_text(BUS_SHEET, encoding="utf-8")
    sch, report = import_kicad_sch(str(p))
    assert report.imported["buses"] == 1
    assert not report.dropped                        # buses no longer dropped
    assert sorted(sch.nets["D3"]) == ["R1.1", "R2.1"]   # one net through the bus


def test_bus_renders_thick_blue(tmp_path):
    p = tmp_path / "bus.kicad_sch"
    p.write_text(BUS_SHEET, encoding="utf-8")
    sch, _ = import_kicad_sch(str(p))
    svg = sheet_to_svg(sch)
    assert 'stroke="#0000C2" stroke-width="0.75"' in svg   # the bus
    assert len(sch.graphics["bus_entries"]) == 2


def test_authoring_a_bus_is_visual_only():
    e = SheetEditor("bus")
    e.place("R1", "resistor", 100, 100)
    e.place("R2", "resistor", 140, 100)
    e.bus((90, 80), (150, 80))
    e.wire(e.pin_pos("R1", "1"), (100, 80))
    e.wire(e.pin_pos("R2", "1"), (140, 80))
    e.label("D3", 100, 85)
    e.label("D3", 140, 85)
    sch = e.finish()
    assert sorted(sch.nets["D3"]) == ["R1.1", "R2.1"]
    assert sch.graphics["buses"]                      # drawn, not conductive
