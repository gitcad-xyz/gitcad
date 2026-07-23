"""SW-map P7: GD&T as data — datums, feature control frames, and
dimensional tolerances bound to lineage-stable feature ids, living in
the same reviewable text as the geometry they constrain."""

from __future__ import annotations

import pytest

from gitcad.document import Document, Feature
from gitcad.errors import GitcadError


def _part() -> tuple[Document, str, str]:
    d = Document()
    base = d.add(Feature(op="box", params={"dx": 40, "dy": 30, "dz": 5}))
    hole = d.add(Feature(op="hole", params={"x": 20, "y": 15, "top_z": 5,
                                            "depth": 5, "diameter": 6},
                         inputs=[base]))
    return d, base, hole


def test_tolerances_roundtrip_and_stay_optional() -> None:
    d, base, hole = _part()
    assert "tolerances" not in d.dumps()               # absent until used
    d.add_tolerance({"kind": "datum", "label": "A", "feature": base})
    d.add_tolerance({"kind": "gdt", "symbol": "position", "value": 0.1,
                     "feature": hole, "datum_refs": ["A"]})
    d.add_tolerance({"kind": "dim", "feature": hole, "param": "diameter",
                     "plus": 0.05, "minus": 0.02})
    d2 = Document.loads(d.dumps())
    assert d2.tolerances == d.tolerances
    assert d2.dumps() == d.dumps()


def test_validation_fails_loud() -> None:
    d, base, hole = _part()
    with pytest.raises(GitcadError, match="unknown feature"):
        d.add_tolerance({"kind": "datum", "label": "A", "feature": "ghost"})
    with pytest.raises(GitcadError, match="undefined datum"):
        d.add_tolerance({"kind": "gdt", "symbol": "position", "value": 0.1,
                         "feature": hole, "datum_refs": ["Z"]})
    with pytest.raises(GitcadError, match="symbol"):
        d.add_tolerance({"kind": "gdt", "symbol": "wobble", "value": 0.1,
                         "feature": hole})
    with pytest.raises(GitcadError, match="positive"):
        d.add_tolerance({"kind": "gdt", "symbol": "flatness", "value": 0,
                         "feature": base})
    with pytest.raises(GitcadError, match="no param"):
        d.add_tolerance({"kind": "dim", "feature": hole, "param": "girth",
                         "plus": 0.1})
    d.add_tolerance({"kind": "datum", "label": "A", "feature": base})
    with pytest.raises(GitcadError, match="duplicate"):
        d.add_tolerance({"kind": "datum", "label": "A", "feature": hole})


def test_tolerance_notes_project_the_block() -> None:
    d, base, hole = _part()
    d.add_tolerance({"kind": "datum", "label": "A", "feature": base})
    d.add_tolerance({"kind": "gdt", "symbol": "position", "value": 0.1,
                     "feature": hole, "datum_refs": ["A"]})
    d.add_tolerance({"kind": "dim", "feature": hole, "param": "diameter",
                     "plus": 0.05, "minus": 0.02})
    notes = d.tolerance_notes()
    assert notes[0].startswith("DATUM A")
    assert "⌖ 0.1 |A" in notes[1]
    assert "diameter +0.05/-0.02" in notes[2]


@pytest.mark.occt
def test_drawing_carries_gdt_block_and_toleranced_callout(tmp_path) -> None:
    from gitcad.mcp.server import REGISTRY

    d, base, hole = _part()
    d.add_tolerance({"kind": "datum", "label": "A", "feature": base})
    d.add_tolerance({"kind": "gdt", "symbol": "position", "value": 0.1,
                     "feature": hole, "datum_refs": ["A"]})
    d.add_tolerance({"kind": "dim", "feature": hole, "param": "diameter",
                     "plus": 0.05, "minus": 0.02})
    out = tmp_path / "p7.svg"
    REGISTRY["model_drawing"](model=d.dumps(), path=str(out))
    svg = out.read_text(encoding="utf-8")
    assert "DATUM A" in svg
    assert "0.1 |A" in svg
    assert "+0.05/-0.02" in svg                        # on the hole callout too
