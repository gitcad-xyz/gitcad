"""Demo: a 2-layer LED board, end to end — schematic → ERC → board → parity →
verify → full fab package.

Run:  python examples/blinky.py [outdir]
Pure Python — no geometry kernel needed.
"""

import sys
from pathlib import Path

from gitcad.ecad import (
    Board, Component, Footprint, MountingHole, Pad, Pin, SchComponent,
    Schematic, Track, Via, board_parity, export_fab, run_drc,
)

# -- capture: the schematic IS the electrical source of truth -----------------
sch = Schematic(name="blinky")
sch.components += [
    SchComponent("J1", value="PWR", footprint="HDR-2P-2.54", pins=[
        Pin("VCC", "1", "power_out"), Pin("GND", "2", "power_out")]),
    SchComponent("R1", value="330R", footprint="R0603", pins=[
        Pin("A", "1", "passive"), Pin("B", "2", "passive")]),
    SchComponent("D1", value="RED", footprint="LED0603", pins=[
        Pin("A", "A", "passive"), Pin("K", "K", "passive")]),
]
sch.connect("VCC", "J1.1", "R1.1")
sch.connect("LED_A", "R1.2", "D1.A")
sch.connect("GND", "J1.2", "D1.K")

erc = sch.erc()
assert erc.ok, erc.violations
print("ERC clean:", erc.checks)

out = Path(sys.argv[1] if len(sys.argv) > 1 else "out") / "blinky-fab"

R0603 = Footprint("R0603", pads=[
    Pad("1", -0.75, 0, 0.9, 0.95), Pad("2", 0.75, 0, 0.9, 0.95)], courtyard=(2.4, 1.4))
LED0603 = Footprint("LED0603", pads=[
    Pad("A", -0.75, 0, 0.9, 0.95), Pad("K", 0.75, 0, 0.9, 0.95)], courtyard=(2.4, 1.4))
HDR2 = Footprint("HDR-2P-2.54", pads=[
    Pad("1", 0, -1.27, 1.7, 1.7, shape="circle", drill=1.0),
    Pad("2", 0, 1.27, 1.7, 1.7, shape="circle", drill=1.0)], courtyard=(3.0, 5.6))

board = Board(name="blinky", outline=[(0, 0), (30, 0), (30, 20), (0, 20)])
board.components += [
    Component("J1", HDR2, value="PWR", x=4, y=10, nets={"1": "VCC", "2": "GND"}),
    Component("R1", R0603, value="330R", x=13, y=12, nets={"1": "VCC", "2": "LED_A"}),
    Component("D1", LED0603, value="RED", x=21, y=12, nets={"A": "LED_A", "K": "GND"}),
]
# (DRC caught the original routing here: VCC/GND tracks were swapped at J1 —
# parity can't see that, geometry can. Routed correctly per pad positions:
# J1.1/VCC at (4, 8.73), J1.2/GND at (4, 11.27).)
board.tracks += [
    Track(4, 8.73, 7, 8.73, 0.5, "top", "VCC"),      # J1.1 out
    Track(7, 8.73, 7, 14, 0.5, "top", "VCC"),        # around J1.2
    Track(7, 14, 12.25, 12, 0.5, "top", "VCC"),      # to R1.1
    Track(13.75, 12, 20.25, 12, 0.4, "top", "LED_A"),
    Track(21.75, 12, 26, 12, 0.4, "top", "GND"),     # D1.K to via
    Track(26, 12, 26, 6, 0.5, "bottom", "GND"),
    Track(26, 6, 2, 6, 0.6, "bottom", "GND"),        # bottom return
    Track(2, 6, 2, 11.27, 0.5, "bottom", "GND"),     # around J1.1
    Track(2, 11.27, 4, 11.27, 0.5, "bottom", "GND"), # into J1.2 (through pad)
]
board.vias += [Via(26, 12, net="GND")]
board.mounting_holes += [MountingHole("mnt_1", 3, 3, 3.2, thread="M3"),
                         MountingHole("mnt_2", 27, 17, 3.2, thread="M3")]

report = board.validate()
assert report.ok, report.violations
print("board valid:", report.checks)

# -- parity: the board must implement exactly the schematic -------------------
parity = board_parity(sch, board)
assert parity.ok, parity.violations
print("schematic-board parity:", parity.checks)

# -- DRC: geometric design rules against the default fab profile --------------
drc = run_drc(board)
assert drc.ok, drc.violations
print("DRC clean:", drc.checks)
(Path(sys.argv[1] if len(sys.argv) > 1 else "out")).mkdir(exist_ok=True)
(Path(sys.argv[1] if len(sys.argv) > 1 else "out") / "blinky.sch.json").write_text(
    sch.dumps(), newline="\n")

files = export_fab(board, str(out))
for kind, path in files.items():
    print(f"  {kind:15} {path}")

(out / "blinky.gitcad.json").write_text(board.dumps(), newline="\n")
print(f"board source saved: {out / 'blinky.gitcad.json'}")
