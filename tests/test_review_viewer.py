"""Regression: design-review viewer — schematic discovery + review client.

Kernel-free: discovery renders canonical schematics without geometry, and
the client page is a string whose review features (tabs, measure tool,
raycast picking) must actually be present — a silent lost feature in the
single-file client would otherwise ship unnoticed.
"""

from pathlib import Path

from gitcad.viewer.page import PAGE
from gitcad.viewer.server import discover_schematics


def _write_sch(dirpath: Path, name: str) -> None:
    from gitcad.ecad.schematic import Pin, SchComponent, Schematic

    sch = Schematic(name=name)
    sch.components = [SchComponent(ref="R1", pins=[Pin("1", "1"), Pin("2", "2")])]
    sch.connect("A", "R1.1")
    sch.connect("B", "R1.2")
    (dirpath / f"{name}.schematic.json").write_text(sch.dumps(), encoding="utf-8")


def test_discover_renders_canonical_schematics(tmp_path):
    _write_sch(tmp_path, "power")
    sub = tmp_path / "boards"
    sub.mkdir()
    _write_sch(sub, "sensor")
    sheets = discover_schematics(tmp_path)
    assert sorted(s["name"] for s in sheets) == ["power", "sensor"]
    assert all("<svg" in s["svg"] for s in sheets)


def test_discover_reports_broken_sheet_without_sinking_review(tmp_path):
    _write_sch(tmp_path, "good")
    (tmp_path / "bad.schematic.json").write_text("{not json", encoding="utf-8")
    sheets = discover_schematics(tmp_path)
    by_file = {s["file"]: s for s in sheets}
    assert "svg" in by_file["good.schematic.json"]
    assert "error" in by_file["bad.schematic.json"]


def test_discover_empty_tree_is_empty(tmp_path):
    assert discover_schematics(tmp_path) == []


def test_review_client_ships_tabs_and_measure_tool():
    # tab bar with schematics + measure entries
    assert "schematics (" in PAGE
    assert '"measure", "measure"' in PAGE
    # raycast picking with vertex snap and distance readout
    assert "rayTriangle" in PAGE          # Moller-Trumbore present
    assert "vertex snap" in PAGE
    assert "dist ${" in PAGE and "dx ${" in PAGE
    # deep link for review handoffs
    assert '#sheets' in PAGE
    # escape clears picks
    assert 'e.key === "Escape"' in PAGE
