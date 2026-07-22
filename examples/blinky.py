"""Demo: a 2-layer LED board, end to end — board → verify → full fab package.

Run:  python examples/blinky.py [outdir]
Pure Python — no geometry kernel needed.
"""

import sys
from pathlib import Path

from gitcad.ecad import Board, Component, Footprint, MountingHole, Pad, Track, Via, export_fab

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
board.tracks += [
    Track(4, 11.27, 4, 14, 0.5, "top", "VCC"),
    Track(4, 14, 12.25, 12, 0.5, "top", "VCC"),
    Track(13.75, 12, 20.25, 12, 0.4, "top", "LED_A"),
    Track(21.75, 12, 26, 12, 0.4, "top", "GND"),
    Track(4, 8.73, 4, 6, 0.5, "top", "GND"),
    Track(26, 12, 26, 6, 0.5, "bottom", "GND"),
    Track(26, 6, 4, 6, 0.6, "bottom", "GND"),
]
board.vias += [Via(26, 12, net="GND"), Via(26, 6, net="GND")]
board.mounting_holes += [MountingHole("mnt_1", 3, 3, 3.2, thread="M3"),
                         MountingHole("mnt_2", 27, 17, 3.2, thread="M3")]

report = board.validate()
assert report.ok, report.violations
print("board valid:", report.checks)

files = export_fab(board, str(out))
for kind, path in files.items():
    print(f"  {kind:15} {path}")

(out / "blinky.gitcad.json").write_text(board.dumps(), newline="\n")
print(f"board source saved: {out / 'blinky.gitcad.json'}")
