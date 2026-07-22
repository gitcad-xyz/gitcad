"""GOLDEN: assembly viewer payload — instances resolved, placed, colored."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.occt


def test_assembly_mesh_payload(tmp_path) -> None:
    from gitcad.document import Document, Feature
    from gitcad.kernel.occt import OcctKernel
    from gitcad.derive import model_to_part
    from gitcad.part import Assembly, PartManifest
    from gitcad.viewer.server import assembly_mesh_payload, detect_kind

    kernel = OcctKernel()

    def publish(name: str, part_id: str, dims) -> PartManifest:
        doc = Document()
        doc.add(Feature(op="box", params={"dx": dims[0], "dy": dims[1], "dz": dims[2]}))
        (tmp_path / f"{name}.gitcad.json").write_text(doc.dumps(), newline="\n")
        part = model_to_part(doc, kernel, part_id=part_id, name=name)
        (tmp_path / f"{name}.part.json").write_text(part.dumps(), newline="\n")
        return part

    base = publish("base", "prt_0000000000000001", (60, 40, 8))
    lid = publish("lid", "prt_0000000000000002", (60, 40, 3))

    asm = Assembly("stack")
    asm.add("base", base)
    asm.add("lid", lid, translate=(0, 0, 8))
    apath = tmp_path / "stack.part.json"
    apath.write_text(asm.to_manifest("prt_00000000000000aa").dumps(), newline="\n")

    assert detect_kind(apath.read_text()) == "assembly"
    payload = assembly_mesh_payload(apath, kernel)
    assert payload["kind"] == "assembly"
    assert [g["name"] for g in payload["groups"]] == ["base", "lid"]
    # Colors: one rgb per vertex, distinct between instances.
    assert len(payload["colors"]) == len(payload["positions"])
    assert payload["groups"][0]["color"] != payload["groups"][1]["color"]
    # Placement applied: combined bbox spans base + stacked lid = z 0..11.
    assert payload["bbox"][0][2] == pytest.approx(0)
    assert payload["bbox"][1][2] == pytest.approx(11)


def test_non_assembly_part_manifest_is_rejected(tmp_path) -> None:
    from gitcad.part import PartManifest
    from gitcad.viewer.server import detect_kind

    m = PartManifest(id="prt_0000000000000003", name="solo", domain="mech", version="0.1.0")
    with pytest.raises(ValueError, match="MODEL file"):
        detect_kind(m.dumps())
