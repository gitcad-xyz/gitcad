"""Golden: IPC-D-356 export, Eagle schematic import, sheet notes
(KiCad-map tier 2, part 3). Kernel-free.
"""

import pytest

from gitcad.ecad import Board, Component, Footprint, Pad, Via
from gitcad.ecad.ipcd356 import to_ipcd356
from gitcad.ecad.schsvg import sheet_to_svg
from gitcad.ecad.sheetedit import SheetEditor
from gitcad.errors import GitcadError
from gitcad.importers.eagle import import_eagle_sch

FP = Footprint("R0603", pads=[Pad("1", -0.75, 0, 0.9, 0.95),
                              Pad("2", 0.75, 0, 0.9, 0.95)])
FP_TH = Footprint("HDR", pads=[Pad("1", 0, 0, 1.7, 1.7, "circle", 1.0)])


def test_ipcd356_records():
    b = Board(name="t", outline=[(0, 0), (20, 0), (20, 10), (0, 10)])
    b.components += [Component("R1", FP, x=5, y=5, nets={"1": "VCC"}),
                     Component("J1", FP_TH, x=15, y=5, nets={"1": "GND"})]
    b.vias.append(Via(x=10, y=5, drill=0.3, diameter=0.6, net="VCC"))
    text = to_ipcd356(b)
    lines = text.splitlines()
    assert lines[2] == "P  UNITS CUST 1"
    smd = next(ln for ln in lines if ln.startswith("327"))
    assert smd.startswith("327VCC") and "R1" in smd and "A00" in smd
    pth = next(ln for ln in lines if ln.startswith("317GND"))
    assert "D1000" in pth                              # 1.0mm drill in microns
    via = next(ln for ln in lines if "VIA" in ln)
    assert via.startswith("317VCC") and "D0300" in via
    assert lines[-1] == "999"
    # unnetted pads never appear (R1.2 has no net)
    assert sum(1 for ln in lines if ln.startswith(("317", "327"))) == 3


EAGLE = """<?xml version="1.0"?>
<eagle version="9.6.2">
 <drawing><schematic>
  <parts>
   <part name="R1" deviceset="RESISTOR" device="0603" value="10k"/>
   <part name="U1" deviceset="MCU" device="QFN16" value="ESP32"/>
  </parts>
  <sheets><sheet>
   <nets>
    <net name="VCC"><segment>
      <pinref part="R1" gate="G$1" pin="1"/>
      <pinref part="U1" gate="G$1" pin="VDD"/>
    </segment></net>
    <net name="GND"><segment>
      <pinref part="R1" gate="G$1" pin="2"/>
    </segment></net>
   </nets>
  </sheet></sheets>
 </schematic></drawing>
</eagle>
"""


def test_eagle_schematic_imports_netlist(tmp_path):
    p = tmp_path / "demo.sch"
    p.write_text(EAGLE, encoding="utf-8")
    sch, report = import_eagle_sch(str(p))
    assert {c.ref for c in sch.components} == {"R1", "U1"}
    assert sorted(sch.nets["VCC"]) == ["R1.1", "U1.VDD"]
    assert sch.nets["GND"] == ["R1.2"]
    r1 = next(c for c in sch.components if c.ref == "R1")
    assert r1.value == "10k" and r1.footprint == "0603"
    assert report.imported["symbols"] == 2
    assert any("netlist-only" in d for d in report.dropped)   # honest scope


def test_eagle_board_file_refused(tmp_path):
    p = tmp_path / "demo.brd"
    p.write_text('<?xml version="1.0"?><eagle version="9"><drawing>'
                 "<board/></drawing></eagle>", encoding="utf-8")
    with pytest.raises(GitcadError, match="no <schematic>"):
        import_eagle_sch(str(p))


def test_sheet_notes_author_and_render():
    e = SheetEditor("n")
    e.place("R1", "resistor", 100, 100)
    e.note("hand-solder only", 90, 80)
    sch = e.finish()
    svg = sheet_to_svg(sch)
    assert ">hand-solder only</text>" in svg
