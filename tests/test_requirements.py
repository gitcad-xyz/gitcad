"""Golden: requirements-as-code — the traceability matrix that executes.

Kernel-aware but null-friendly (a box has analytic volume everywhere).
Oracles: a mass limit above the box's mass passes with the measured value
shown; below it fails; a requirement with no check is visible debt
("unchecked", never silent green); an envelope requirement fails when the
rail is overvolted.
"""

import pytest

from gitcad.document import Document, Feature
from gitcad.ecad.schematic import Pin, SchComponent, Schematic
from gitcad.errors import GitcadError
from gitcad.requirements import (load_requirements, new_requirements_doc,
                                 to_markdown, verify)


@pytest.fixture()
def design(tmp_path):
    doc = Document()
    doc.add(Feature(op="box", params={"dx": 100, "dy": 50, "dz": 20}))
    (tmp_path / "body.gitcad.json").write_text(doc.dumps(), encoding="utf-8")

    sch = Schematic(name="pwr")
    sch.components = [
        SchComponent(ref="U1", pins=[Pin("VDD", "1", "power_in")],
                     attrs={"pin_specs": {"1": {"v_abs_max": 3.6, "i_draw_ma": 80}}}),
        SchComponent(ref="U2", pins=[Pin("OUT", "1", "power_out")],
                     attrs={"pin_specs": {"1": {"i_source_ma": 100}}}),
    ]
    sch.connect("+3V3", "U1.1", "U2.1")
    (tmp_path / "main.schematic.json").write_text(sch.dumps(), encoding="utf-8")
    return tmp_path


def _doc(reqs):
    return new_requirements_doc(reqs)


def test_mass_and_bbox_requirements_verify_with_measured_values(design):
    # box: 100*50*20 = 100000 mm3 -> 104 g at ABS 1.04
    text = _doc([
        {"id": "REQ-001", "text": "mass under 150 g in ABS",
         "check": {"kind": "mass_max_g", "target": "model:body.gitcad.json",
                   "limit": 150, "density_g_cm3": 1.04}},
        {"id": "REQ-002", "text": "fits 110x60x25 envelope",
         "check": {"kind": "bbox_max_mm", "target": "model:body.gitcad.json",
                   "limit": [110, 60, 25]}},
    ])
    report = verify(text, str(design))
    assert report["ok"], report
    r1, r2 = report["requirements"]
    assert r1["status"] == "pass" and r1["measured"] == pytest.approx(104.0)
    assert r2["status"] == "pass" and r2["measured"] == [100, 50, 20]


def test_failed_limit_shows_measured_vs_limit(design):
    text = _doc([{"id": "REQ-001", "text": "mass under 50 g",
                  "check": {"kind": "mass_max_g", "target": "model:body.gitcad.json",
                            "limit": 50, "density_g_cm3": 1.04}}])
    report = verify(text, str(design))
    assert not report["ok"]
    r = report["requirements"][0]
    assert r["status"] == "fail" and r["measured"] > r["limit"]


def test_unchecked_requirement_is_visible_debt(design):
    text = _doc([{"id": "REQ-900", "text": "shall be intrinsically safe"}])
    report = verify(text, str(design))
    assert not report["ok"]
    assert report["requirements"][0]["status"] == "unchecked"
    assert report["summary"]["unchecked"] == 1


def test_electrical_requirements_bind_to_envelope_and_rails(design):
    text = _doc([
        {"id": "REQ-010", "text": "no electrical envelope violations",
         "check": {"kind": "envelope_clean", "target": "schematic:main.schematic.json"}},
        {"id": "REQ-011", "text": "3V3 rail at most 90% loaded",
         "check": {"kind": "rail_utilization_max",
                   "target": "schematic:main.schematic.json",
                   "net": "+3V3", "limit": 0.9}},
    ])
    report = verify(text, str(design))
    assert report["ok"], report
    assert report["requirements"][1]["measured"] == pytest.approx(0.8)


def test_missing_target_and_unknown_kind_error_loud(design):
    text = _doc([
        {"id": "R1", "text": "x", "check": {"kind": "mass_max_g",
                                            "target": "model:ghost.json", "limit": 1}},
        {"id": "R2", "text": "y", "check": {"kind": "vibes_good",
                                            "target": "model:body.gitcad.json"}},
    ])
    report = verify(text, str(design))
    assert not report["ok"]
    assert all(r["status"] == "error" for r in report["requirements"])


def test_duplicate_ids_rejected():
    with pytest.raises(GitcadError, match="duplicate requirement id"):
        load_requirements(_doc([{"id": "R1", "text": "a"},
                                {"id": "R1", "text": "b"}]))


def test_markdown_matrix(design):
    text = _doc([{"id": "REQ-001", "text": "mass under 150 g",
                  "check": {"kind": "mass_max_g", "target": "model:body.gitcad.json",
                            "limit": 150, "density_g_cm3": 1.04}},
                 {"id": "REQ-900", "text": "unbound requirement"}])
    md = to_markdown(verify(text, str(design)))
    assert "| REQ-001 |" in md and "**pass**" in md
    assert "| REQ-900 |" in md and "**unchecked**" in md
    assert "NOT MET" in md
