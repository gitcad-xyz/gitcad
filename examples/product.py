"""Demo: cross-domain co-design with DERIVED interfaces (ADR-0008 wired in).

Nothing hand-authored: the board's part.json comes from its actual mounting
holes and outline; the bracket's envelope comes from its actual built geometry.
Change the board — the interface, the mate check, and the release gate all
follow automatically.

Run:  python examples/product.py
Uses the OCCT kernel if installed, the null kernel otherwise.
"""

from gitcad.document import Document, Feature
from gitcad.ecad import Board, MountingHole
from gitcad.kernel import get_kernel
from gitcad.part import (
    Assembly, Frame, Port, Workspace, check_release, model_to_part, resolve,
)

# -- the ecad part: interface DERIVED from board geometry ---------------------
board = Board(name="blinky", outline=[(0, 0), (30, 0), (30, 20), (0, 20)])
board.mounting_holes += [MountingHole("mnt_1", 3, 3, 3.2, thread="M3"),
                         MountingHole("mnt_2", 27, 17, 3.2, thread="M3")]
board_part = board.to_part("prt_b0a4d0000000cafe", "1.0.0")
print("board envelope (derived):", board_part.interface.envelope)
print("board ports (derived):   ", sorted(board_part.interface.ports))

# -- the mech part: envelope DERIVED from built geometry ----------------------
doc = Document()
plate = doc.add(Feature(op="box", params={"dx": 60, "dy": 40, "dz": 8}))
kernel = get_kernel()
bracket_part = model_to_part(
    doc, kernel, part_id="prt_facade0000000001", name="bracket", version="1.0.0",
    frames={"boss_1": Frame(origin=(13, 13, 8)), "boss_2": Frame(origin=(37, 27, 8))},
    ports={"boss_1": Port("boss_1", "mech.boss", "boss_1", {"thread": "M3"}),
           "boss_2": Port("boss_2", "mech.boss", "boss_2", {"thread": "M3"})},
)
print("bracket envelope (derived from", kernel.name, "):", bracket_part.interface.envelope)

# -- the product --------------------------------------------------------------
asm = Assembly("product")
asm.add("bracket", bracket_part)
asm.add("board", board_part, translate=(10, 10, 8))
asm.mate("board.mnt_1", "bracket.boss_1")
asm.mate("board.mnt_2", "bracket.boss_2")
report = asm.validate()
print("assembly valid:", report.ok, report.checks)

ws = Workspace()
ws.add(board_part)
ws.add(bracket_part)
manifest = asm.to_manifest("prt_a55e3b1e00000001")
print("lockfile:\n" + resolve(manifest, ws).dumps())

# -- the payoff: move a hole ON THE BOARD, everything downstream reacts -------
board.mounting_holes[1] = MountingHole("mnt_2", 28.5, 17, 3.2, thread="M3")
board_v2 = board.to_part("prt_b0a4d0000000cafe", "1.0.1")   # try to ship as patch
print("release gate:", check_release("1.0.0", "1.0.1",
                                     board_part.interface, board_v2.interface))
asm2 = Assembly("product")
asm2.add("bracket", bracket_part)
asm2.add("board", board_v2, translate=(10, 10, 8))
asm2.mate("board.mnt_1", "bracket.boss_1")
asm2.mate("board.mnt_2", "bracket.boss_2")
print("mate check:", asm2.validate().violations)
