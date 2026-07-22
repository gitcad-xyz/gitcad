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

__all__ = ["Board", "Component", "Footprint", "MountingHole", "Pad", "Track", "Via", "export_fab"]
