"""INVARIANT: stable identity survives upstream edits.

This is the topological-naming property (ADR-0003) and it is architecture-
independent — it must hold for ANY kernel or document backend. It therefore
lives in the permanent ``invariants`` tier and may never be auto-deleted by the
bug loop (see CLAUDE.md).
"""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature

pytestmark = pytest.mark.invariant


def test_feature_id_is_not_ordinal() -> None:
    """A feature's id must not change when an unrelated feature is inserted
    before it — the whole point of semantic identity."""
    a = Document()
    box_id = a.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 10}))

    b = Document()
    b.add(Feature(op="cylinder", params={"radius": 2, "height": 5}))
    box_id_2 = b.add(Feature(op="box", params={"dx": 10, "dy": 10, "dz": 10}))

    # Same construction of the box → same id, despite different position/order.
    assert box_id == box_id_2


def test_ids_are_deterministic_across_rebuilds() -> None:
    def build() -> list[str]:
        d = Document()
        b = d.add(Feature(op="box", params={"dx": 1, "dy": 2, "dz": 3}))
        d.add(Feature(op="fillet", params={"radius": 0.5}, inputs=[b]))
        return [f.id for f in d.features]

    assert build() == build()


def test_structural_twins_are_disambiguated() -> None:
    """Two structurally identical siblings must still get distinct ids."""
    d = Document()
    id1 = d.add(Feature(op="box", params={"dx": 1, "dy": 1, "dz": 1}))
    id2 = d.add(Feature(op="box", params={"dx": 1, "dy": 1, "dz": 1}))
    assert id1 != id2
