"""Forward annotation: push the schematic netlist onto a board.

The schematic is the electrical source (feature-map B1); the board carries a
copy of the net assignments on its pads. This is the ECO forward path — the
step the real Altair project never ran (its main board is placement-only,
every pad netless). ``annotate_board`` writes schematic nets onto matching
board components and reports every mismatch instead of guessing:

- refs on one side only (board footprint with no symbol, or vice versa)
- pads with no matching schematic pin number
- conflicts where a pad already carries a DIFFERENT net (never silently
  overwritten — an existing assignment disagreeing with the schematic is
  exactly the bug parity exists to catch)

After annotation, ``board_parity`` should be green; run it — this module
writes, that one verifies, and they stay separate on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gitcad.ecad.board import Board
from gitcad.ecad.schematic import Schematic


@dataclass
class SyncReport:
    annotated_pins: int = 0
    refs_missing_on_board: list[str] = field(default_factory=list)
    refs_missing_in_schematic: list[str] = field(default_factory=list)
    pads_without_schematic_pin: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)   # "REF.pad:old!=new"

    @property
    def clean(self) -> bool:
        return not (self.refs_missing_on_board or self.refs_missing_in_schematic
                    or self.conflicts)

    def to_dict(self) -> dict:
        return {"annotated_pins": self.annotated_pins,
                "refs_missing_on_board": self.refs_missing_on_board,
                "refs_missing_in_schematic": self.refs_missing_in_schematic,
                "pads_without_schematic_pin": self.pads_without_schematic_pin,
                "conflicts": self.conflicts, "clean": self.clean}


def back_annotate(sch: Schematic, board: Board) -> dict:
    """Board -> schematic value sync (the reverse ECO path, KiCad-map
    tier 2): a value edited during layout ("changed R5 to 22R on the
    bench") flows back to the electrical source. Refs are matched by
    designator; values differing are written to the schematic and
    reported; board-only refs are reported, never invented into the
    schematic (adding a component is design work, not annotation)."""
    sch_by_ref = {c.ref: c for c in sch.components}
    changed: dict[str, dict] = {}
    board_only: list[str] = []
    for comp in board.components:
        target = sch_by_ref.get(comp.ref)
        if target is None:
            board_only.append(comp.ref)
            continue
        if comp.value and comp.value != target.value:
            changed[comp.ref] = {"old": target.value, "new": comp.value}
            target.value = comp.value
    return {"values_changed": changed, "board_only_refs": sorted(board_only),
            "ok": not board_only}


def annotate_board(board: Board, sch: Schematic, *,
                   overwrite_conflicts: bool = False) -> SyncReport:
    """Write schematic net names onto board pads, matched by ref + pin number.

    Mutates ``board`` in place (the board is the working copy; its text is
    re-dumped by the caller). Conflicting existing assignments are reported
    and left alone unless ``overwrite_conflicts`` — an explicit choice, never
    a default."""
    report = SyncReport()

    pin_net: dict[str, dict[str, str]] = {}    # ref -> pin number -> net
    for net, pin_refs in sch.nets.items():
        for pr in pin_refs:
            ref, num = pr.split(".", 1)
            pin_net.setdefault(ref, {})[num] = net

    sch_refs = {c.ref for c in sch.components}
    board_refs = set()
    for comp in board.components:
        board_refs.add(comp.ref)
        nets = pin_net.get(comp.ref)
        if nets is None:
            if comp.ref in sch_refs:
                continue               # in schematic but fully unconnected
            report.refs_missing_in_schematic.append(comp.ref)
            continue
        for pad in comp.footprint.pads:
            net = nets.get(pad.name)
            if net is None:
                report.pads_without_schematic_pin.append(f"{comp.ref}.{pad.name}")
                continue
            existing = comp.nets.get(pad.name)
            if existing and existing != net:
                report.conflicts.append(f"{comp.ref}.{pad.name}:{existing}!={net}")
                if not overwrite_conflicts:
                    continue
            comp.nets[pad.name] = net
            report.annotated_pins += 1

    report.refs_missing_on_board = sorted(sch_refs - board_refs)
    report.refs_missing_in_schematic.sort()
    report.pads_without_schematic_pin.sort()
    report.conflicts.sort()
    return report
