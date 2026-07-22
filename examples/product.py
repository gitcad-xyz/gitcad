"""Demo: cross-domain co-design — the bracket and the blinky board as Parts,
mated in one assembly, with the interface-semver release gate in action.

Run:  python examples/product.py
Pure Python — no geometry kernel needed.
"""

from gitcad.part import (
    Assembly, Frame, Interface, PartManifest, Port, Workspace,
    check_release, classify_change, new_part_id, resolve,
)

# -- the ecad part: blinky publishes its mech-facing interface ----------------
board = PartManifest(
    id="prt_b0a4d0000000cafe", name="blinky", domain="ecad", version="1.0.0",
    interface=Interface(
        envelope={"origin": [0, 0, 0], "dx": 30, "dy": 20, "dz": 1.6},
        frames={"mnt_1": Frame(origin=(3, 3, 0)), "mnt_2": Frame(origin=(27, 17, 0))},
        ports={"mnt_1": Port("mnt_1", "mech.bolt", "mnt_1", {"thread": "M3"}),
               "mnt_2": Port("mnt_2", "mech.bolt", "mnt_2", {"thread": "M3"})},
        properties={"layers": 2},
    ),
    body={"board": "blinky.gitcad.json"},
)

# -- the mech part: the bracket publishes bosses ------------------------------
bracket = PartManifest(
    id="prt_facade0000000001", name="bracket", domain="mech", version="1.0.0",
    interface=Interface(
        envelope={"origin": [0, 0, 0], "dx": 60, "dy": 40, "dz": 8},
        frames={"boss_1": Frame(origin=(13, 13, 8)), "boss_2": Frame(origin=(37, 27, 8))},
        ports={"boss_1": Port("boss_1", "mech.boss", "boss_1", {"thread": "M3"}),
               "boss_2": Port("boss_2", "mech.boss", "boss_2", {"thread": "M3"})},
    ),
    body={"model": "bracket.gitcad.json"},
)

# -- the product: an assembly is just a part ----------------------------------
asm = Assembly("product")
asm.add("bracket", bracket)
asm.add("board", board, translate=(10, 10, 8))
asm.mate("board.mnt_1", "bracket.boss_1")
asm.mate("board.mnt_2", "bracket.boss_2")

report = asm.validate()
print("assembly valid:", report.ok, report.checks)

manifest = asm.to_manifest(new_part_id())
print("assembly-as-part envelope:", manifest.interface.envelope)
print("assembly deps:", manifest.deps)

# -- lock it: reproducible forever --------------------------------------------
ws = Workspace()
ws.add(board)
ws.add(bracket)
lock = resolve(manifest, ws)
print("lockfile:")
print(lock.dumps())

# -- the board revs with a moved hole: everything catches it ------------------
board_v2 = PartManifest.loads(board.dumps())
board_v2.interface.frames["mnt_2"] = Frame(origin=(28.5, 17, 0))

required, reasons = classify_change(board.interface, board_v2.interface)
print(f"moved hole requires: {required.upper()}  ({reasons[0]})")
print("shipping it as 1.0.1:", check_release("1.0.0", "1.0.1",
                                             board.interface, board_v2.interface))
