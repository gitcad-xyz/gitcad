"""gitcad-ecad — the electrical domain.

v0.1 scope: a text-first board model plus the fabrication outputs that let a
user actually order a PCB — Gerber X2 per layer, Excellon drill, pick-and-place.
Schematic capture, ERC, and the full DRC engine follow (see
docs/research/feature-map.md Part B).

Like the mechanical document, the board is canonical text (ADR-0004): the
model diffs and merges in git, and every generated output is deterministic —
the same board text produces byte-identical Gerbers on any machine.
"""

from gitcad.ecad.board import Board, Component, Footprint, MountingHole, Pad, Track, Via
from gitcad.ecad.fab import export_fab
from gitcad.ecad.component import footprint_from_part, footprint_to_part
from gitcad.ecad.connectivity import check_connectivity
from gitcad.ecad.drc import Rule, RulePack, default_rules, run_drc
from gitcad.ecad.route import pad_position, route
from gitcad.ecad.schematic import Pin, SchComponent, Schematic, board_parity

__all__ = ["Board", "Component", "Footprint", "MountingHole", "Pad", "Track", "Via",
           "export_fab", "Schematic", "SchComponent", "Pin", "board_parity",
           "Rule", "RulePack", "default_rules", "run_drc", "check_connectivity",
           "pad_position", "route", "footprint_to_part", "footprint_from_part"]
